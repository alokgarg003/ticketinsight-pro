"""
NLP Insights Engine for TicketInsight Pro.

Unified NLP engine that orchestrates all analysis modules to provide
comprehensive ticket intelligence: classification, topic modeling,
sentiment analysis, duplicate detection, anomaly detection, text
summarization, named entity recognition, and root cause analysis.

Usage
-----
    from ticketinsight.nlp import NLPEngine, create_nlp_engine

    engine = create_nlp_engine(config, db_manager)
    engine.warm_up()

    # Analyze a single ticket
    insights = engine.analyze_ticket(ticket_dict)

    # Analyze a batch
    results = engine.analyze_batch(ticket_list)

    # Generate comprehensive insights report
    report = engine.generate_insights_report()
"""

from typing import Any, Dict, List, Optional

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text, chunk_list

from ticketinsight.nlp.classifier import TicketClassifier
from ticketinsight.nlp.topic_modeler import TopicModeler
from ticketinsight.nlp.sentiment import SentimentAnalyzer
from ticketinsight.nlp.duplicate_detector import DuplicateDetector
from ticketinsight.nlp.anomaly_detector import AnomalyDetector
from ticketinsight.nlp.summarizer import TicketSummarizer
from ticketinsight.nlp.ner_extractor import NERExtractor
from ticketinsight.nlp.root_cause import RootCauseAnalyzer


__all__ = [
    "NLPEngine",
    "create_nlp_engine",
    "TicketClassifier",
    "TopicModeler",
    "SentimentAnalyzer",
    "DuplicateDetector",
    "AnomalyDetector",
    "TicketSummarizer",
    "NERExtractor",
    "RootCauseAnalyzer",
]


class NLPEngine:
    """Unified NLP engine that orchestrates all analysis modules.

    Provides a single interface for running all NLP analyses on tickets.
    Each sub-module can be used independently or through this orchestrator.

    Parameters
    ----------
    config : ConfigManager
        Application configuration manager.
    db_manager : DatabaseManager, optional
        Database manager for persisting results.

    Attributes
    ----------
    classifier : TicketClassifier
        Multi-label ticket classification.
    topic_modeler : TopicModeler
        Topic modeling using LDA.
    sentiment_analyzer : SentimentAnalyzer
        Sentiment analysis with urgency scoring.
    duplicate_detector : DuplicateDetector
        Duplicate detection via cosine similarity.
    anomaly_detector : AnomalyDetector
        Anomaly detection using Isolation Forest.
    summarizer : TicketSummarizer
        Extractive text summarization.
    ner_extractor : NERExtractor
        Named entity recognition.
    root_cause_analyzer : RootCauseAnalyzer
        Root cause analysis using clustering.
    """

    def __init__(self, config: Any, db_manager: Any = None):
        self.classifier = TicketClassifier(config)
        self.topic_modeler = TopicModeler(config)
        self.sentiment_analyzer = SentimentAnalyzer(config)
        self.duplicate_detector = DuplicateDetector(config)
        self.anomaly_detector = AnomalyDetector(config)
        self.summarizer = TicketSummarizer(config)
        self.ner_extractor = NERExtractor(config)
        self.root_cause_analyzer = RootCauseAnalyzer(config)
        self.db = db_manager
        self.config = config
        self.logger = get_logger("nlp.engine")
        self.logger.info("NLPEngine initialized with all sub-modules")

    # ------------------------------------------------------------------ #
    #  Core analysis methods                                              #
    # ------------------------------------------------------------------ #

    def analyze_ticket(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Run all NLP analyses on a single ticket.

        Orchestrates all sub-modules to produce a comprehensive analysis
        of a single ticket.  Each module is called independently and
        failures are caught so that partial results are always returned.

        Parameters
        ----------
        ticket : dict
            Ticket dictionary with at least ``title`` and ``description``
            fields.  May also contain ``priority``, ``status``, ``category``,
            ``ticket_id``, ``opened_at``, ``resolved_at``, etc.

        Returns
        -------
        dict
            Comprehensive analysis result:
            ``{
                "ticket_id": str,
                "classification": {category, confidence, all_scores, method},
                "sentiment": {polarity, subjectivity, label, urgency_score, ...},
                "topics": {topic_id, topic_label, keywords, probability, method},
                "summary": {summary, original_length, summary_length, ...},
                "entities": {entities: [...], it_specific: {...}, entity_summary},
                "anomaly_score": float,
                "root_cause": {predicted_cause, confidence, recommendation, ...},
                "metadata": {processing_time_ms, modules_run, modules_failed}
            }``
        """
        import time
        start_time = time.time()

        ticket_id = ticket.get("ticket_id", ticket.get("id", "unknown"))

        # Extract text for analysis
        title = ticket.get("title", "") or ""
        description = ticket.get("description", "") or ""
        text = sanitize_text(f"{title} {description}")

        result = {
            "ticket_id": ticket_id,
        }

        modules_run = []
        modules_failed = []

        # 1. Classification
        try:
            result["classification"] = self.classifier.classify(text)
            modules_run.append("classification")
        except Exception as exc:
            self.logger.error("Classification failed for %s: %s", ticket_id, exc)
            result["classification"] = {
                "category": "Other",
                "confidence": 0.0,
                "all_scores": {},
                "method": "keyword",
                "error": str(exc),
            }
            modules_failed.append("classification")

        # 2. Sentiment Analysis
        try:
            result["sentiment"] = self.sentiment_analyzer.analyze(text)
            modules_run.append("sentiment")
        except Exception as exc:
            self.logger.error("Sentiment analysis failed for %s: %s", ticket_id, exc)
            result["sentiment"] = self.sentiment_analyzer._empty_result()
            result["sentiment"]["error"] = str(exc)
            modules_failed.append("sentiment")

        # 3. Topic Extraction
        try:
            result["topics"] = self.topic_modeler.extract_topics(text)
            modules_run.append("topics")
        except Exception as exc:
            self.logger.error("Topic extraction failed for %s: %s", ticket_id, exc)
            result["topics"] = {
                "topic_id": -1,
                "topic_label": "N/A",
                "keywords": [],
                "probability": 0.0,
                "method": "keyword",
                "error": str(exc),
            }
            modules_failed.append("topics")

        # 4. Summarization
        try:
            result["summary"] = self.summarizer.summarize(text)
            modules_run.append("summary")
        except Exception as exc:
            self.logger.error("Summarization failed for %s: %s", ticket_id, exc)
            result["summary"] = {
                "summary": text[:200] if text else "",
                "original_length": len(text),
                "summary_length": min(len(text), 200),
                "compression_ratio": 1.0,
                "key_phrases": [],
                "error": str(exc),
            }
            modules_failed.append("summary")

        # 5. Named Entity Recognition
        try:
            result["entities"] = self.ner_extractor.extract(text)
            modules_run.append("entities")
        except Exception as exc:
            self.logger.error("NER failed for %s: %s", ticket_id, exc)
            result["entities"] = {
                "entities": [],
                "it_specific": {},
                "entity_summary": "",
                "error": str(exc),
            }
            modules_failed.append("entities")

        # 6. Root Cause Analysis (single ticket)
        try:
            result["root_cause"] = self.root_cause_analyzer.analyze_single(ticket)
            modules_run.append("root_cause")
        except Exception as exc:
            self.logger.error("Root cause analysis failed for %s: %s", ticket_id, exc)
            result["root_cause"] = {
                "predicted_cause": "Unknown",
                "confidence": 0.0,
                "matched_keywords": [],
                "similar_tickets": [],
                "historical_resolution_time": 0.0,
                "recommendation": "",
                "error": str(exc),
            }
            modules_failed.append("root_cause")

        # 7. Anomaly detection (single ticket — needs baseline)
        result["anomaly_score"] = 0.0
        try:
            # Use a minimal baseline for single-ticket check
            baseline = self._compute_quick_baseline(ticket)
            anomaly = self.anomaly_detector.detect_single(ticket, baseline)
            result["anomaly_score"] = anomaly["score"]
            result["anomaly_details"] = {
                "is_anomaly": anomaly["is_anomaly"],
                "reasons": anomaly["reasons"],
                "anomaly_types": anomaly["anomaly_types"],
            }
            modules_run.append("anomaly")
        except Exception as exc:
            self.logger.error("Anomaly detection failed for %s: %s", ticket_id, exc)
            result["anomaly_details"] = {"error": str(exc)}
            modules_failed.append("anomaly")

        # Processing metadata
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        result["metadata"] = {
            "processing_time_ms": elapsed_ms,
            "modules_run": modules_run,
            "modules_failed": modules_failed,
            "total_modules": 7,
            "success_rate": round(
                len(modules_run) / 7 * 100, 1
            ) if modules_run else 0.0,
        }

        # Persist to database if manager is available
        if self.db is not None:
            try:
                self._persist_ticket_insights(ticket_id, result)
            except Exception as exc:
                self.logger.error("Failed to persist insights for %s: %s", ticket_id, exc)

        self.logger.info(
            "Ticket %s analyzed: %d/%d modules in %.1fms",
            ticket_id,
            len(modules_run),
            7,
            elapsed_ms,
        )

        return result

    def analyze_batch(
        self, tickets: List[Dict[str, Any]], batch_size: int = 50
    ) -> Dict[str, Any]:
        """Analyze a batch of tickets.

        Processes tickets in chunks for memory efficiency.  Runs each
        NLP module across the entire batch and returns aggregate results
        along with per-ticket details.

        Parameters
        ----------
        tickets : list[dict]
            List of ticket dictionaries.
        batch_size : int
            Number of tickets to process per batch.

        Returns
        -------
        dict
            ``{
                "total_tickets": int,
                "successful": int,
                "failed": int,
                "ticket_results": [dict, ...],
                "aggregate": {
                    "classification_distribution": {category: count},
                    "sentiment_distribution": {label: count},
                    "avg_urgency": float,
                    "avg_frustration": float,
                    "avg_csat": float,
                    "top_topics": [{label, count}, ...],
                    "top_root_causes": [{cause, count}, ...],
                    "anomaly_count": int,
                    "anomaly_rate": float,
                    "duplicate_pairs": [dict, ...]
                }
            }``
        """
        import time
        start_time = time.time()

        if not tickets:
            return {
                "total_tickets": 0,
                "successful": 0,
                "failed": 0,
                "ticket_results": [],
                "aggregate": {},
            }

        ticket_results = []
        failed_count = 0

        # Process tickets individually (can be parallelized in future)
        for ticket in tickets:
            try:
                result = self.analyze_ticket(ticket)
                ticket_results.append(result)
            except Exception as exc:
                self.logger.error(
                    "Batch analysis failed for ticket %s: %s",
                    ticket.get("ticket_id", "unknown"),
                    exc,
                )
                failed_count += 1

        # Compute aggregate statistics
        aggregate = self._compute_aggregate_stats(ticket_results)

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "total_tickets": len(tickets),
            "successful": len(ticket_results),
            "failed": failed_count,
            "ticket_results": ticket_results,
            "aggregate": aggregate,
            "processing_time_ms": elapsed_ms,
        }

    def generate_insights_report(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate comprehensive insights report across all tickets.

        If a database manager is available, loads tickets from the database.
        Otherwise, returns a report structure indicating no data.

        Parameters
        ----------
        filters : dict, optional
            Filters to apply when loading tickets (status, priority, date range, etc.)

        Returns
        -------
        dict
            Comprehensive insights report including:
            - Classification distribution
            - Sentiment trends
            - Top topics
            - Root cause analysis
            - Anomaly summary
            - Duplicate tickets
            - Recommendations
        """
        import time
        start_time = time.time()

        report: Dict[str, Any] = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "filters_applied": filters or {},
            "sections": {},
        }

        # Load tickets from database if available
        tickets = []
        if self.db is not None:
            try:
                result = self.db.get_tickets(filters=filters, per_page=5000)
                tickets = result.get("tickets", [])
                report["total_tickets"] = result.get("total", 0)
            except Exception as exc:
                self.logger.error("Failed to load tickets from DB: %s", exc)
                report["total_tickets"] = 0
                report["error"] = str(exc)
                report["sections"]["error"] = f"Could not load tickets: {exc}"
        else:
            report["total_tickets"] = 0
            report["sections"]["note"] = "No database manager configured; provide tickets via analyze_batch()."

        if not tickets:
            report["sections"]["classification"] = {"distribution": {}, "summary": "No tickets to analyze."}
            report["sections"]["sentiment"] = {"distribution": {}, "summary": "No tickets to analyze."}
            report["sections"]["topics"] = {"top_topics": [], "summary": "No tickets to analyze."}
            report["sections"]["root_cause"] = {"distribution": {}, "recommendations": []}
            report["sections"]["anomalies"] = {"count": 0, "rate": 0.0}
            report["sections"]["duplicates"] = {"pairs": []}
            return report

        # --- Classification Distribution ---
        try:
            class_dist: Dict[str, int] = {}
            for ticket in tickets:
                cat = ticket.get("predicted_category") or ticket.get("category") or "Uncategorized"
                class_dist[cat] = class_dist.get(cat, 0) + 1

            sorted_classes = sorted(class_dist.items(), key=lambda x: x[1], reverse=True)
            report["sections"]["classification"] = {
                "distribution": dict(sorted_classes),
                "top_category": sorted_classes[0][0] if sorted_classes else "N/A",
                "unique_categories": len(sorted_classes),
                "summary": (
                    f"Most common category: '{sorted_classes[0][0]}' "
                    f"with {sorted_classes[0][1]} tickets ({sorted_classes[0][1] / max(1, len(tickets)) * 100:.1f}%)"
                    if sorted_classes else "No classification data available."
                ),
            }
        except Exception as exc:
            report["sections"]["classification"] = {"error": str(exc)}

        # --- Sentiment Distribution ---
        try:
            sentiment_dist: Dict[str, int] = {}
            urgency_scores = []
            frustration_scores = []
            csat_scores = []

            for ticket in tickets:
                label = ticket.get("sentiment_label") or "Neutral"
                sentiment_dist[label] = sentiment_dist.get(label, 0) + 1

                if ticket.get("sentiment_score") is not None:
                    score = ticket.get("sentiment_score", 0)
                    if score < -0.1:
                        csat_scores.append(max(1.0, 3.0 + score * 2.0))
                    elif score > 0.1:
                        csat_scores.append(min(5.0, 3.0 + score * 2.0))
                    else:
                        csat_scores.append(3.0)

            sorted_sentiments = sorted(
                sentiment_dist.items(), key=lambda x: x[1], reverse=True
            )

            avg_csat = sum(csat_scores) / len(csat_scores) if csat_scores else 3.0

            report["sections"]["sentiment"] = {
                "distribution": dict(sorted_sentiments),
                "average_csat_estimate": round(avg_csat, 2),
                "summary": (
                    f"Sentiment breakdown: {dict(sorted_sentiments)}. "
                    f"Estimated average CSAT: {avg_csat:.2f}/5.0."
                ),
            }
        except Exception as exc:
            report["sections"]["sentiment"] = {"error": str(exc)}

        # --- Topic Analysis ---
        try:
            texts = [
                sanitize_text(f"{t.get('title', '')} {t.get('description', '')}")
                for t in tickets
            ]
            texts = [t for t in texts if t]
            topic_result = self.topic_modeler.extract_topics_batch(texts)

            report["sections"]["topics"] = {
                "top_topics": topic_result.get("topics", [])[:10],
                "method": topic_result.get("method", "keyword"),
                "summary": (
                    f"Identified {len(topic_result.get('topics', []))} topic clusters "
                    f"using {topic_result.get('method', 'keyword')} analysis."
                ),
            }
        except Exception as exc:
            report["sections"]["topics"] = {"error": str(exc)}

        # --- Root Cause Analysis ---
        try:
            # Use stored tickets for root cause analysis
            root_cause_result = self.root_cause_analyzer.analyze(tickets)
            report["sections"]["root_cause"] = {
                "distribution": root_cause_result.get("root_cause_distribution", {}),
                "clusters": root_cause_result.get("clusters", [])[:10],
                "recommendations": root_cause_result.get("recommendations", []),
                "summary": (
                    f"Identified {len(root_cause_result.get('root_cause_distribution', {}))} "
                    f"root cause categories with "
                    f"{len(root_cause_result.get('recommendations', []))} recommendations."
                ),
            }
        except Exception as exc:
            report["sections"]["root_cause"] = {"error": str(exc), "distribution": {}, "recommendations": []}

        # --- Anomaly Summary ---
        try:
            anomaly_tickets = [
                t for t in tickets
                if t.get("anomaly_score", 0) > 0.5
            ]
            report["sections"]["anomalies"] = {
                "count": len(anomaly_tickets),
                "rate": round(len(anomaly_tickets) / max(1, len(tickets)), 4),
                "summary": (
                    f"Detected {len(anomaly_tickets)} anomalous tickets "
                    f"({len(anomaly_tickets) / max(1, len(tickets)) * 100:.1f}% of total)."
                ),
            }
        except Exception as exc:
            report["sections"]["anomalies"] = {"error": str(exc), "count": 0, "rate": 0.0}

        # --- Duplicate Summary ---
        try:
            texts = [
                sanitize_text(f"{t.get('title', '')} {t.get('description', '')}")
                for t in tickets
            ]
            tids = [t.get("ticket_id", str(i)) for i, t in enumerate(tickets)]
            dupes = self.duplicate_detector.find_duplicates(texts, tids)
            report["sections"]["duplicates"] = {
                "pairs": dupes[:20],  # Top 20 duplicate pairs
                "total_pairs": len(dupes),
                "summary": (
                    f"Found {len(dupes)} potential duplicate pairs."
                    if dupes else "No significant duplicates detected."
                ),
            }
        except Exception as exc:
            report["sections"]["duplicates"] = {"error": str(exc), "pairs": [], "total_pairs": 0}

        # --- Processing time ---
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        report["processing_time_ms"] = elapsed_ms

        return report

    def warm_up(self) -> Dict[str, Any]:
        """Pre-load models and prepare all NLP modules for use.

        Call this at application startup to avoid cold-start latency
        on the first ticket analysis.

        Returns
        -------
        dict
            Warm-up status for each module:
            ``{
                "classifier": "ready",
                "sentiment_analyzer": "ready",
                "topic_modeler": "not_trained",
                "duplicate_detector": "ready",
                "anomaly_detector": "not_trained",
                "summarizer": "ready",
                "ner_extractor": "loading" | "ready" | "unavailable",
                "root_cause_analyzer": "not_trained"
            }``
        """
        self.logger.info("Warming up NLP engine...")

        status = {}

        # Classifier — always ready (keyword fallback)
        status["classifier"] = "ready" if self.classifier else "error"

        # Sentiment — check TextBlob availability
        try:
            from textblob import TextBlob  # noqa: F401
            status["sentiment_analyzer"] = "ready"
        except ImportError:
            status["sentiment_analyzer"] = "degraded (TextBlob unavailable, using rules)"

        # Topic modeler — check Gensim availability
        try:
            import gensim  # noqa: F401
            status["topic_modeler"] = "not_trained (Gensim available, needs training data)"
        except ImportError:
            status["topic_modeler"] = "degraded (Gensim unavailable, using keyword fallback)"

        # Duplicate detector — always ready
        status["duplicate_detector"] = "ready"

        # Anomaly detector — check sklearn
        try:
            from sklearn.ensemble import IsolationForest  # noqa: F401
            status["anomaly_detector"] = "not_trained (sklearn available, needs training data)"
        except ImportError:
            status["anomaly_detector"] = "degraded (sklearn unavailable, using statistical methods only)"

        # Summarizer — check TextBlob
        try:
            from textblob import TextBlob  # noqa: F401
            status["summarizer"] = "ready"
        except ImportError:
            status["summarizer"] = "degraded (using regex tokenization)"

        # NER — load spaCy model
        try:
            loaded = self.ner_extractor.load_model()
            status["ner_extractor"] = "ready" if loaded else "unavailable (spaCy model could not be loaded)"
        except Exception as exc:
            status["ner_extractor"] = f"error: {exc}"

        # Root cause analyzer — check sklearn
        try:
            from sklearn.cluster import KMeans  # noqa: F401
            status["root_cause_analyzer"] = "not_trained (sklearn available, needs training data)"
        except ImportError:
            status["root_cause_analyzer"] = "degraded (using pattern matching only)"

        # Summary
        ready_count = sum(1 for v in status.values() if v.startswith("ready"))
        total_count = len(status)
        self.logger.info(
            "NLP engine warm-up complete: %d/%d modules ready", ready_count, total_count
        )

        status["_summary"] = f"{ready_count}/{total_count} modules ready"
        return status

    # ------------------------------------------------------------------ #
    #  Helper methods                                                     #
    # ------------------------------------------------------------------ #

    def _compute_aggregate_stats(
        self, ticket_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compute aggregate statistics from a list of per-ticket results.

        Parameters
        ----------
        ticket_results : list[dict]
            Results from analyze_ticket calls.

        Returns
        -------
        dict
            Aggregate statistics across all analyzed tickets.
        """
        aggregate: Dict[str, Any] = {}

        if not ticket_results:
            return aggregate

        # --- Classification distribution ---
        class_dist: Dict[str, int] = {}
        for result in ticket_results:
            classification = result.get("classification", {})
            category = classification.get("category", "Unknown")
            class_dist[category] = class_dist.get(category, 0) + 1

        sorted_classes = sorted(class_dist.items(), key=lambda x: x[1], reverse=True)
        aggregate["classification_distribution"] = dict(sorted_classes)

        # --- Sentiment distribution ---
        sentiment_dist: Dict[str, int] = {}
        urgency_scores = []
        frustration_scores = []
        csat_scores = []
        escalation_risks = []

        for result in ticket_results:
            sentiment = result.get("sentiment", {})
            label = sentiment.get("label", "Unknown")
            sentiment_dist[label] = sentiment_dist.get(label, 0) + 1

            urg = sentiment.get("urgency_score", 0)
            if urg:
                urgency_scores.append(urg)

            frust = sentiment.get("frustration_score", 0)
            if frust:
                frustration_scores.append(frust)

            csat = sentiment.get("customer_satisfaction_predict", 3.0)
            if csat:
                csat_scores.append(csat)

            esc = sentiment.get("escalation_risk", 0)
            if esc:
                escalation_risks.append(esc)

        sorted_sentiments = sorted(
            sentiment_dist.items(), key=lambda x: x[1], reverse=True
        )
        aggregate["sentiment_distribution"] = dict(sorted_sentiments)
        aggregate["avg_urgency"] = (
            round(sum(urgency_scores) / len(urgency_scores), 4)
            if urgency_scores else 0.0
        )
        aggregate["avg_frustration"] = (
            round(sum(frustration_scores) / len(frustration_scores), 4)
            if frustration_scores else 0.0
        )
        aggregate["avg_csat"] = (
            round(sum(csat_scores) / len(csat_scores), 2)
            if csat_scores else 3.0
        )
        aggregate["avg_escalation_risk"] = (
            round(sum(escalation_risks) / len(escalation_risks), 4)
            if escalation_risks else 0.0
        )

        # --- Top topics ---
        topic_dist: Dict[str, int] = {}
        for result in ticket_results:
            topics = result.get("topics", {})
            label = topics.get("topic_label", "Unknown")
            topic_dist[label] = topic_dist.get(label, 0) + 1

        sorted_topics = sorted(topic_dist.items(), key=lambda x: x[1], reverse=True)
        aggregate["top_topics"] = [
            {"label": label, "count": count}
            for label, count in sorted_topics[:10]
        ]

        # --- Top root causes ---
        cause_dist: Dict[str, int] = {}
        for result in ticket_results:
            rc = result.get("root_cause", {})
            cause = rc.get("predicted_cause", "Unknown")
            if cause and cause != "Unknown":
                cause_dist[cause] = cause_dist.get(cause, 0) + 1

        sorted_causes = sorted(cause_dist.items(), key=lambda x: x[1], reverse=True)
        aggregate["top_root_causes"] = [
            {"cause": cause, "count": count}
            for cause, count in sorted_causes[:10]
        ]

        # --- Anomaly stats ---
        anomaly_scores = [
            result.get("anomaly_score", 0)
            for result in ticket_results
            if result.get("anomaly_score", 0) > 0
        ]
        anomaly_count = sum(1 for s in anomaly_scores if s > 0.5)
        aggregate["anomaly_count"] = anomaly_count
        aggregate["anomaly_rate"] = round(
            anomaly_count / max(1, len(ticket_results)), 4
        )

        # --- Processing stats ---
        processing_times = [
            result.get("metadata", {}).get("processing_time_ms", 0)
            for result in ticket_results
        ]
        if processing_times:
            aggregate["avg_processing_time_ms"] = round(
                sum(processing_times) / len(processing_times), 2
            )
            aggregate["max_processing_time_ms"] = round(max(processing_times), 2)
            aggregate["min_processing_time_ms"] = round(min(processing_times), 2)

        return aggregate

    def _compute_quick_baseline(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Compute a minimal baseline for single-ticket anomaly detection.

        Uses heuristic defaults when no historical data is available.

        Parameters
        ----------
        ticket : dict
            Single ticket.

        Returns
        -------
        dict
            Baseline statistics.
        """
        title = ticket.get("title", "") or ""
        description = ticket.get("description", "") or ""
        text = sanitize_text(f"{title} {description}")
        text_length = len(text)

        return {
            "desc_length_mean": float(max(100, text_length)),
            "desc_length_std": float(max(50, text_length * 0.5)),
            "desc_length_median": float(text_length),
            "resolution_mean": 24.0,  # Default 24h average
            "resolution_std": 48.0,   # Default 48h std
            "resolution_median": 8.0,
            "urgency_density_mean": 0.05,
            "urgency_density_std": 0.05,
        }

    def _persist_ticket_insights(
        self, ticket_id: str, result: Dict[str, Any]
    ) -> None:
        """Persist analysis results to the database.

        Updates the Ticket model's NLP enrichment fields and creates
        TicketInsight records for each analysis type.

        Parameters
        ----------
        ticket_id : str
            External ticket identifier.
        result : dict
            Analysis results from analyze_ticket.
        """
        if self.db is None:
            return

        try:
            # Update direct fields on the ticket
            insights_update = {}

            classification = result.get("classification", {})
            if classification.get("category"):
                insights_update["predicted_category"] = classification["category"]
                insights_update["confidence"] = classification.get("confidence", 0.0)

            sentiment = result.get("sentiment", {})
            if sentiment.get("label"):
                insights_update["sentiment_label"] = sentiment["label"]
                insights_update["sentiment_score"] = sentiment.get("polarity", 0.0)

            topics = result.get("topics", {})
            if topics.get("topic_id") is not None and topics["topic_id"] >= 0:
                insights_update["topic_cluster"] = topics["topic_id"]

            summary = result.get("summary", {})
            if summary.get("summary"):
                insights_update["summary"] = summary["summary"]

            entities = result.get("entities", {})
            if entities.get("entities") or entities.get("it_specific"):
                insights_update["named_entities"] = {
                    "entities": entities.get("entities", []),
                    "it_specific": entities.get("it_specific", {}),
                    "entity_summary": entities.get("entity_summary", ""),
                }

            anomaly_score = result.get("anomaly_score", 0.0)
            if anomaly_score:
                insights_update["anomaly_score"] = anomaly_score

            root_cause = result.get("root_cause", {})
            # No direct root_cause_cluster field mapping needed here

            # Persist to database
            self.db.update_ticket_insights(ticket_id, insights_update)

        except Exception as exc:
            self.logger.error("Error persisting insights: %s", exc)


def create_nlp_engine(config: Any, db_manager: Any = None) -> NLPEngine:
    """Convenience factory function for creating an NLPEngine instance.

    Parameters
    ----------
    config : ConfigManager
        Application configuration manager.
    db_manager : DatabaseManager, optional
        Database manager for persisting results.

    Returns
    -------
    NLPEngine
        Configured and ready-to-use NLP engine instance.

    Example
    -------
    >>> from ticketinsight.config import ConfigManager
    >>> from ticketinsight.nlp import create_nlp_engine
    >>> config = ConfigManager()
    >>> engine = create_nlp_engine(config)
    >>> engine.warm_up()
    """
    return NLPEngine(config=config, db_manager=db_manager)
