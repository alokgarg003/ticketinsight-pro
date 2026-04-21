#!/usr/bin/env python
"""
TicketInsight Pro — Complete Demo Pipeline Runner

Runs a full demonstration of the NLP analytics platform including:
  1. Sample ticket display
  2. Classification
  3. Sentiment analysis
  4. Topic modeling
  5. Duplicate detection
  6. Anomaly detection
  7. Text summarization
  8. NER extraction
  9. Root cause analysis
  10. Insights report generation

Usage:
    python scripts/run_demo.py
    python scripts/run_demo.py --tickets 5
    python scripts/run_demo.py --skip-db-init
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------
class C:
    """ANSI color constants for terminal output."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    BG_RED    = "\033[41m"
    BG_GREEN  = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE   = "\033[44m"

    def header(text: str) -> str:
        return f"\n{C.BOLD}{C.BLUE}{'━' * 72}{C.RESET}\n{C.BOLD}{C.BLUE}  {text}{C.RESET}\n{C.BOLD}{C.BLUE}{'━' * 72}{C.RESET}\n"

    def section(text: str, step: int = 0, total: int = 0) -> str:
        prefix = f"  {C.BOLD}{C.YELLOW}[{step}/{total}]{C.RESET} " if step else "  "
        return f"\n{prefix}{C.BOLD}{C.CYAN}▸ {text}{C.RESET}\n"

    def success(text: str) -> str:
        return f"  {C.GREEN}✓ {text}{C.RESET}"

    def error(text: str) -> str:
        return f"  {C.RED}✗ {text}{C.RESET}"

    def warn(text: str) -> str:
        return f"  {C.YELLOW}⚠ {text}{C.RESET}"

    def info(text: str) -> str:
        return f"  {C.DIM}  {text}{C.RESET}"

    def key_val(key: str, value: Any) -> str:
        return f"    {C.DIM}{key}:{C.RESET} {value}"

    def json(data: Any) -> str:
        return f"    {C.DIM}{json.dumps(data, indent=6, default=str, ensure_ascii=False)}{C.RESET}"


# ---------------------------------------------------------------------------
# Model download helper
# ---------------------------------------------------------------------------
def ensure_nlp_models() -> None:
    """Check and download required NLP models if not present."""
    print(C.section("Checking NLP Models", 0, 0))

    # spaCy
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        print(C.success(f"spaCy en_core_web_sm loaded (v{nlp.meta['version']})"))
    except Exception:
        print(C.warn("Downloading spaCy en_core_web_sm..."))
        try:
            spacy.cli.download("en_core_web_sm")
            print(C.success("spaCy model downloaded"))
        except Exception as exc:
            print(C.error(f"Failed to download spaCy model: {exc}"))

    # NLTK
    try:
        import nltk
        packages = ["punkt", "punkt_tab", "stopwords", "wordnet",
                     "averaged_perceptron_tagger", "vader_lexicon"]
        for pkg in packages:
            try:
                nltk.download(pkg, quiet=True)
            except Exception:
                pass
        print(C.success("NLTK data packages verified"))
    except ImportError:
        print(C.error("NLTK not installed — sentiment analysis may be limited"))


# ---------------------------------------------------------------------------
# Demo Pipeline
# ---------------------------------------------------------------------------
class DemoPipeline:
    """Runs the complete TicketInsight Pro demo pipeline."""

    TOTAL_STEPS = 10

    def __init__(self, max_tickets: int = 5, skip_db_init: bool = False):
        self.max_tickets = max_tickets
        self.skip_db_init = skip_db_init
        self.app = None
        self.db_manager = None
        self.nlp_engine = None
        self.start_time = time.time()
        self.results: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def setup(self) -> None:
        """Initialize the Flask app, database, and NLP engine."""
        print(C.header("TicketInsight Pro — Demo Pipeline"))
        print(C.info(f"Timestamp:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
        print(C.info(f"Project root:    {_PROJECT_ROOT}"))
        print(C.info(f"Max tickets:     {self.max_tickets}"))

        # Create Flask app
        print(C.section("Initializing Application", 0, 0))
        try:
            from ticketinsight.main import create_app
            os.environ["TICKETINSIGHT_CONFIG"] = str(_PROJECT_ROOT / "config.yaml")
            self.app = create_app()
            print(C.success("Flask application created"))
        except Exception as exc:
            print(C.error(f"Failed to create Flask app: {exc}"))
            sys.exit(1)

        with self.app.app_context():
            # Database
            self.db_manager = self.app.extensions.get("db_manager")
            if self.db_manager:
                print(C.success("Database manager initialized"))
            else:
                print(C.error("Database manager not available"))

            # Cache
            cache = self.app.extensions.get("cache_manager")
            if cache:
                print(C.success("Cache manager initialized"))

            # Seed if needed
            if not self.skip_db_init:
                try:
                    count = self.db_manager.seed_sample_data()
                    if count > 0:
                        print(C.success(f"Seeded {count} sample tickets"))
                    else:
                        print(C.info("Database already has data"))
                except Exception as exc:
                    print(C.warn(f"Could not seed data: {exc}"))

            # Initialize NLP engine
            try:
                from ticketinsight.nlp import NLPEngine
                config = self.app.extensions.get("config_manager")
                self.nlp_engine = NLPEngine(config=config, db_manager=self.db_manager)

                # Warm up
                warmup = self.nlp_engine.warm_up()
                ready = sum(1 for v in warmup.values() if v.startswith("ready"))
                total = len(warmup)
                print(C.success(f"NLP engine ready ({ready}/{total} modules)"))
                for module, status in warmup.items():
                    if status.startswith("ready"):
                        print(C.info(f"  {module}: {status}"))
                    else:
                        print(C.warn(f"  {module}: {status}"))
            except Exception as exc:
                print(C.error(f"Failed to initialize NLP engine: {exc}"))
                sys.exit(1)

    # ------------------------------------------------------------------
    # Step 1: Show sample tickets
    # ------------------------------------------------------------------
    def show_sample_tickets(self) -> List[Dict]:
        """Load and display sample tickets from the database."""
        step = 1
        print(C.section("Sample Tickets from Database", step, self.TOTAL_STEPS))

        with self.app.app_context():
            result = self.db_manager.get_tickets(
                per_page=self.max_tickets, sort_by="opened_at", sort_order="desc"
            )
            tickets = result.get("tickets", [])
            total = result.get("total", 0)

        print(C.info(f"Total tickets in database: {total}"))
        print(C.info(f"Showing: {len(tickets)} ticket(s)\n"))

        for i, ticket in enumerate(tickets, 1):
            status_color = C.GREEN if ticket.get("status") in ("Resolved", "Closed") else C.YELLOW
            priority_colors = {
                "Critical": C.RED, "High": C.YELLOW,
                "Medium": C.BLUE, "Low": C.DIM,
            }
            pri_color = priority_colors.get(ticket.get("priority", ""), C.WHITE)

            print(f"  {C.BOLD}{C.CYAN}Ticket #{i}: {ticket.get('ticket_id', 'N/A')}{C.RESET}")
            print(f"    {C.BOLD}Title:{C.RESET}     {ticket.get('title', 'N/A')}")
            print(f"    {C.BOLD}Priority:{C.RESET}  {pri_color}{ticket.get('priority', 'N/A')}{C.RESET}")
            print(f"    {C.BOLD}Status:{C.RESET}    {status_color}{ticket.get('status', 'N/A')}{C.RESET}")
            print(f"    {C.BOLD}Category:{C.RESET}  {ticket.get('category', 'N/A')}")
            desc = ticket.get("description", "")
            if desc:
                print(f"    {C.BOLD}Description:{C.RESET} {desc[:120]}{'...' if len(desc) > 120 else ''}")
            print()

        self.results["tickets_shown"] = len(tickets)
        self.results["total_tickets"] = total
        return tickets

    # ------------------------------------------------------------------
    # Step 2: Classification
    # ------------------------------------------------------------------
    def run_classification(self, tickets: List[Dict]) -> None:
        """Run ticket classification on sample tickets."""
        step = 2
        print(C.section("Ticket Classification", step, self.TOTAL_STEPS))

        classifications = []
        for ticket in tickets:
            text = f"{ticket.get('title', '')} {ticket.get('description', '')}"
            try:
                result = self.nlp_engine.classifier.classify(text)
                category = result.get("category", "Unknown")
                confidence = result.get("confidence", 0.0)
                method = result.get("method", "N/A")
                classifications.append(category)

                conf_color = C.GREEN if confidence > 0.8 else (C.YELLOW if confidence > 0.5 else C.RED)
                print(f"    {ticket.get('ticket_id', 'N/A'):15s} → "
                      f"{C.BOLD}{category:25s}{C.RESET} "
                      f"({conf_color}{confidence:.1%}{C.RESET} confidence, {method})")
            except Exception as exc:
                print(C.error(f"  {ticket.get('ticket_id', 'N/A')}: {exc}"))
                classifications.append("Error")

        # Summary
        from collections import Counter
        dist = Counter(classifications)
        print(f"\n  {C.BOLD}Classification Distribution:{C.RESET}")
        for cat, count in dist.most_common():
            bar = "█" * (count * 4) + "░" * ((max(dist.values()) - count) * 4)
            print(f"    {cat:25s} {C.CYAN}{bar}{C.RESET} {count}")

        self.results["classification"] = dict(dist)

    # ------------------------------------------------------------------
    # Step 3: Sentiment Analysis
    # ------------------------------------------------------------------
    def run_sentiment_analysis(self, tickets: List[Dict]) -> None:
        """Run sentiment analysis on sample tickets."""
        step = 3
        print(C.section("Sentiment Analysis", step, self.TOTAL_STEPS))

        sentiments = []
        for ticket in tickets:
            text = f"{ticket.get('title', '')} {ticket.get('description', '')}"
            try:
                result = self.nlp_engine.sentiment_analyzer.analyze(text)
                label = result.get("label", "Neutral")
                polarity = result.get("polarity", 0.0)
                urgency = result.get("urgency_score", 0.0)
                sentiments.append(label)

                label_colors = {
                    "Positive": C.GREEN, "Negative": C.RED,
                    "Neutral": C.YELLOW, "Mixed": C.MAGENTA,
                }
                lc = label_colors.get(label, C.WHITE)

                # Sentiment indicator
                if polarity > 0.2:
                    indicator = "😊"
                elif polarity < -0.2:
                    indicator = "😠"
                else:
                    indicator = "😐"

                print(f"    {ticket.get('ticket_id', 'N/A'):15s} "
                      f"{lc}{label:10s}{C.RESET} "
                      f"(polarity: {polarity:+.3f}, urgency: {urgency:.2f}) {indicator}")
            except Exception as exc:
                print(C.error(f"  {ticket.get('ticket_id', 'N/A')}: {exc}"))
                sentiments.append("Error")

        # Summary
        from collections import Counter
        dist = Counter(sentiments)
        print(f"\n  {C.BOLD}Sentiment Distribution:{C.RESET}")
        for label, count in dist.most_common():
            pct = count / max(1, len(tickets)) * 100
            print(f"    {label:15s} {count} ({pct:.0f}%)")

        self.results["sentiment"] = dict(dist)

    # ------------------------------------------------------------------
    # Step 4: Topic Modeling
    # ------------------------------------------------------------------
    def run_topic_modeling(self, tickets: List[Dict]) -> None:
        """Run topic extraction on sample tickets."""
        step = 4
        print(C.section("Topic Modeling", step, self.TOTAL_STEPS))

        topics_found = []
        for ticket in tickets:
            text = f"{ticket.get('title', '')} {ticket.get('description', '')}"
            try:
                result = self.nlp_engine.topic_modeler.extract_topics(text)
                topic_label = result.get("topic_label", "N/A")
                topic_id = result.get("topic_id", -1)
                keywords = result.get("keywords", [])
                method = result.get("method", "keyword")
                topics_found.append(topic_label)

                kw_str = ", ".join(keywords[:5]) if keywords else "N/A"
                print(f"    {ticket.get('ticket_id', 'N/A'):15s} → "
                      f"{C.BOLD}{topic_label}{C.RESET} "
                      f"(cluster: {topic_id}, method: {method})")
                print(C.info(f"      Keywords: {kw_str}"))
            except Exception as exc:
                print(C.error(f"  {ticket.get('ticket_id', 'N/A')}: {exc}"))
                topics_found.append("N/A")

        # Summary
        from collections import Counter
        dist = Counter(topics_found)
        print(f"\n  {C.BOLD}Topic Distribution:{C.RESET}")
        for topic, count in dist.most_common():
            print(f"    {topic:30s} {count}")

        self.results["topics"] = dict(dist)

    # ------------------------------------------------------------------
    # Step 5: Duplicate Detection
    # ------------------------------------------------------------------
    def run_duplicate_detection(self, tickets: List[Dict]) -> None:
        """Run duplicate detection across sample tickets."""
        step = 5
        print(C.section("Duplicate Detection", step, self.TOTAL_STEPS))

        texts = [
            f"{t.get('title', '')} {t.get('description', '')}"
            for t in tickets
        ]
        tids = [t.get("ticket_id", str(i)) for i, t in enumerate(tickets)]

        try:
            duplicates = self.nlp_engine.duplicate_detector.find_duplicates(texts, tids)

            if not duplicates:
                print(C.success("No significant duplicate pairs found"))
                print(C.info("  All tickets appear to be unique"))
            else:
                print(C.warn(f"Found {len(duplicates)} potential duplicate pair(s):\n"))
                for dup in duplicates[:10]:
                    t1 = dup.get("ticket_1", "?")
                    t2 = dup.get("ticket_2", "?")
                    sim = dup.get("similarity", 0.0)
                    sim_color = C.RED if sim > 0.95 else (C.YELLOW if sim > 0.85 else C.GREEN)
                    print(f"    {t1} ↔ {t2}  "
                          f"({sim_color}similarity: {sim:.1%}{C.RESET})")
        except Exception as exc:
            print(C.error(f"Duplicate detection failed: {exc}"))

        self.results["duplicates_found"] = len(duplicates) if 'duplicates' in dir() else 0

    # ------------------------------------------------------------------
    # Step 6: Anomaly Detection
    # ------------------------------------------------------------------
    def run_anomaly_detection(self, tickets: List[Dict]) -> None:
        """Run anomaly detection on sample tickets."""
        step = 6
        print(C.section("Anomaly Detection", step, self.TOTAL_STEPS))

        anomaly_count = 0
        for ticket in tickets:
            try:
                baseline = self.nlp_engine._compute_quick_baseline(ticket)
                result = self.nlp_engine.anomaly_detector.detect_single(ticket, baseline)

                score = result.get("score", 0.0)
                is_anomaly = result.get("is_anomaly", False)
                reasons = result.get("reasons", [])
                anomaly_types = result.get("anomaly_types", [])

                if is_anomaly:
                    anomaly_count += 1
                    print(f"    {C.RED}{C.BOLD}⚠ ANOMALY{C.RESET}  "
                          f"{ticket.get('ticket_id', 'N/A'):15s} "
                          f"(score: {score:.3f})")
                    for reason in reasons[:3]:
                        print(C.info(f"      Reason: {reason}"))
                else:
                    print(f"    {C.GREEN}✓ Normal{C.RESET}   "
                          f"{ticket.get('ticket_id', 'N/A'):15s} "
                          f"(score: {score:.3f})")
            except Exception as exc:
                print(C.error(f"  {ticket.get('ticket_id', 'N/A')}: {exc}"))

        print(f"\n  {C.BOLD}Summary:{C.RESET} {anomaly_count}/{len(tickets)} "
              f"tickets flagged as anomalous")
        self.results["anomalies_found"] = anomaly_count

    # ------------------------------------------------------------------
    # Step 7: Text Summarization
    # ------------------------------------------------------------------
    def run_summarization(self, tickets: List[Dict]) -> None:
        """Run text summarization on sample tickets."""
        step = 7
        print(C.section("Text Summarization", step, self.TOTAL_STEPS))

        for i, ticket in enumerate(tickets[:3], 1):  # Limit to 3 for readability
            text = f"{ticket.get('title', '')} {ticket.get('description', '')}"
            try:
                result = self.nlp_engine.summarizer.summarize(text)
                summary = result.get("summary", "")
                compression = result.get("compression_ratio", 1.0)
                key_phrases = result.get("key_phrases", [])

                print(f"  {C.BOLD}{C.CYAN}Ticket {ticket.get('ticket_id', 'N/A')}{C.RESET}")
                print(C.info(f"  Original ({len(text)} chars) → "
                            f"Summary ({len(summary)} chars, "
                            f"{compression:.1f}x compression)"))
                print(f"    {C.GREEN}{summary}{C.RESET}")
                if key_phrases:
                    print(C.info(f"  Key phrases: {', '.join(key_phrases[:5])}"))
                print()
            except Exception as exc:
                print(C.error(f"  {ticket.get('ticket_id', 'N/A')}: {exc}"))

        self.results["summarized"] = min(3, len(tickets))

    # ------------------------------------------------------------------
    # Step 8: Named Entity Recognition
    # ------------------------------------------------------------------
    def run_ner(self, tickets: List[Dict]) -> None:
        """Run NER extraction on sample tickets."""
        step = 8
        print(C.section("Named Entity Recognition (NER)", step, self.TOTAL_STEPS))

        all_entities = {}
        for ticket in tickets:
            text = f"{ticket.get('title', '')} {ticket.get('description', '')}"
            try:
                result = self.nlp_engine.ner_extractor.extract(text)
                entities = result.get("entities", [])
                it_specific = result.get("it_specific", {})

                print(f"  {C.BOLD}{ticket.get('ticket_id', 'N/A')}{C.RESET}")

                # Standard entities
                if entities:
                    for ent in entities[:5]:
                        label = ent.get("label", "?")
                        text_ent = ent.get("text", "?")
                        label_colors = {
                            "PERSON": C.GREEN, "ORG": C.BLUE,
                            "PRODUCT": C.MAGENTA, "GPE": C.YELLOW,
                            "DATE": C.CYAN, "CARDINAL": C.DIM,
                        }
                        lc = label_colors.get(label, C.WHITE)
                        print(f"    {lc}{label:12s}{C.RESET} {text_ent}")
                        all_entities[label] = all_entities.get(label, 0) + 1
                else:
                    print(C.info("    No standard entities found"))

                # IT-specific entities
                if it_specific:
                    for key, value in list(it_specific.items())[:5]:
                        if isinstance(value, list):
                            value = ", ".join(str(v) for v in value[:3])
                        print(C.info(f"    IT: {key}: {value}"))

                print()
            except Exception as exc:
                print(C.error(f"  {ticket.get('ticket_id', 'N/A')}: {exc}"))

        # Entity summary
        if all_entities:
            print(f"  {C.BOLD}Entity Summary:{C.RESET}")
            for label, count in sorted(all_entities.items(), key=lambda x: x[1], reverse=True):
                print(f"    {label:15s} {count} occurrence(s)")

        self.results["ner_entities"] = all_entities

    # ------------------------------------------------------------------
    # Step 9: Root Cause Analysis
    # ------------------------------------------------------------------
    def run_root_cause_analysis(self, tickets: List[Dict]) -> None:
        """Run root cause analysis on sample tickets."""
        step = 9
        print(C.section("Root Cause Analysis", step, self.TOTAL_STEPS))

        causes = []
        for ticket in tickets:
            try:
                result = self.nlp_engine.root_cause_analyzer.analyze_single(ticket)
                predicted = result.get("predicted_cause", "Unknown")
                confidence = result.get("confidence", 0.0)
                recommendation = result.get("recommendation", "")
                matched_kw = result.get("matched_keywords", [])

                causes.append(predicted)

                conf_color = C.GREEN if confidence > 0.7 else (C.YELLOW if confidence > 0.4 else C.RED)
                print(f"    {ticket.get('ticket_id', 'N/A'):15s} → "
                      f"{C.BOLD}{predicted}{C.RESET} "
                      f"({conf_color}{confidence:.1%}{C.RESET})")
                if matched_kw:
                    print(C.info(f"      Keywords: {', '.join(matched_kw[:4])}"))
                if recommendation:
                    print(C.info(f"      Rec: {recommendation[:100]}{'...' if len(recommendation) > 100 else ''}"))
            except Exception as exc:
                print(C.error(f"  {ticket.get('ticket_id', 'N/A')}: {exc}"))
                causes.append("Unknown")

        # Cause distribution
        from collections import Counter
        dist = Counter(causes)
        print(f"\n  {C.BOLD}Root Cause Distribution:{C.RESET}")
        for cause, count in dist.most_common():
            print(f"    {cause:35s} {count}")

        self.results["root_causes"] = dict(dist)

    # ------------------------------------------------------------------
    # Step 10: Insights Report
    # ------------------------------------------------------------------
    def run_insights_report(self) -> None:
        """Generate a comprehensive insights report."""
        step = 10
        print(C.section("Insights Report Generation", step, self.TOTAL_STEPS))

        try:
            from ticketinsight.insights.generator import InsightsGenerator
            from ticketinsight.insights.reporter import ReportGenerator

            with self.app.app_context():
                generator = InsightsGenerator(self.db_manager)
                reporter = ReportGenerator(self.db_manager, generator)

                # Generate summary
                print(C.info("  Generating executive summary..."))
                summary = generator.generate_summary()

                km = summary.get("key_metrics", {})
                print(f"\n  {C.BOLD}{C.CYAN}── Executive Summary ──{C.RESET}")
                print(C.key_val("Total Tickets", km.get("total_tickets", 0)))
                print(C.key_val("Open Tickets", km.get("open_tickets", 0)))
                print(C.key_val("Resolved Tickets", km.get("resolved_tickets", 0)))
                print(C.key_val("Resolution Rate", f"{km.get('resolution_rate', 0):.1f}%"))
                print(C.key_val("Avg Resolution", f"{km.get('avg_resolution_time_hours', 'N/A')} hours"))
                print(C.key_val("Avg Sentiment", f"{km.get('avg_sentiment_score', 0):.3f}"))
                print(C.key_val("Anomalies", km.get("anomaly_count", 0)))
                print(C.key_val("Insight Coverage", f"{km.get('insight_coverage', 0):.1f}%"))

                # Alerts
                alerts = summary.get("alerts", [])
                if alerts:
                    print(f"\n  {C.BOLD}{C.RED}── Alerts ──{C.RESET}")
                    for alert in alerts[:5]:
                        level = alert.get("level", "info")
                        msg = alert.get("message", "")
                        action = alert.get("action", "")
                        level_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(level, "⚪")
                        print(f"    {level_icon} {msg}")
                        if action:
                            print(C.info(f"      Action: {action}"))

                # Category distribution
                categories = summary.get("category_distribution", [])
                if categories:
                    print(f"\n  {C.BOLD}── Category Distribution ──{C.RESET}")
                    for cat in categories[:8]:
                        name = cat.get("category", "N/A")
                        count = cat.get("count", 0)
                        print(f"    {name:30s} {C.CYAN}{'█' * (count // 2)}{C.RESET} {count}")

                # NLP insights report
                print(C.info("\n  Generating NLP insights report..."))
                report = self.nlp_engine.generate_insights_report()

                sections = report.get("sections", {})
                for section_name, section_data in sections.items():
                    summary_text = section_data.get("summary", "")
                    if summary_text:
                        print(f"  {C.BOLD}  {section_name.title()}:{C.RESET} {summary_text}")

                self.results["insights_report"] = True

        except Exception as exc:
            print(C.error(f"Failed to generate insights report: {exc}"))
            import traceback
            traceback.print_exc()
            self.results["insights_report"] = False

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    def print_final_summary(self) -> None:
        """Print the final demo summary with timing and results."""
        elapsed = time.time() - self.start_time

        print(C.header("Demo Pipeline Complete!"))
        print()
        print(f"  {C.BOLD}Results Summary:{C.RESET}")
        print(C.key_val("Total Tickets", self.results.get("total_tickets", 0)))
        print(C.key_val("Tickets Shown", self.results.get("tickets_shown", 0)))
        print(C.key_val("Categories Found", len(self.results.get("classification", {}))))
        print(C.key_val("Sentiment Labels", len(self.results.get("sentiment", {}))))
        print(C.key_val("Topics Found", len(self.results.get("topics", {}))))
        print(C.key_val("Duplicates", self.results.get("duplicates_found", 0)))
        print(C.key_val("Anomalies", self.results.get("anomalies_found", 0)))
        print(C.key_val("Tickets Summarized", self.results.get("summarized", 0)))
        print(C.key_val("NER Entity Types", len(self.results.get("ner_entities", {}))))
        print(C.key_val("Root Causes", len(self.results.get("root_causes", {}))))
        print(C.key_val("Insights Report", "✓ Generated" if self.results.get("insights_report") else "✗ Failed"))
        print()
        print(f"  {C.BOLD}Total Execution Time:{C.RESET} {elapsed:.2f}s")
        print()
        print(f"  {C.BOLD}{C.GREEN}Access your dashboard at:{C.RESET}")
        print(f"    {C.CYAN}http://localhost:5000/{C.RESET}")
        print(f"    {C.CYAN}http://localhost:5000/api/v1/health{C.RESET}")
        print()

    # ------------------------------------------------------------------
    # Run all
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Execute the complete demo pipeline."""
        # Setup
        ensure_nlp_models()
        self.setup()

        # Step 1: Show sample tickets
        tickets = self.show_sample_tickets()
        if not tickets:
            print(C.error("No tickets found in database. Check database setup."))
            sys.exit(1)

        # Steps 2-9: NLP analysis
        self.run_classification(tickets)
        self.run_sentiment_analysis(tickets)
        self.run_topic_modeling(tickets)
        self.run_duplicate_detection(tickets)
        self.run_anomaly_detection(tickets)
        self.run_summarization(tickets)
        self.run_ner(tickets)
        self.run_root_cause_analysis(tickets)

        # Step 10: Insights report
        self.run_insights_report()

        # Final summary
        self.print_final_summary()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="TicketInsight Pro — Demo Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_demo.py
  python scripts/run_demo.py --tickets 10
  python scripts/run_demo.py --skip-db-init
        """,
    )
    parser.add_argument(
        "--tickets", "-n",
        type=int,
        default=5,
        help="Maximum number of tickets to analyze (default: 5)",
    )
    parser.add_argument(
        "--skip-db-init",
        action="store_true",
        help="Skip database initialization and seeding",
    )

    args = parser.parse_args()

    pipeline = DemoPipeline(
        max_tickets=args.tickets,
        skip_db_init=args.skip_db_init,
    )
    pipeline.run()


if __name__ == "__main__":
    main()
