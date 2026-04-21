"""
Root cause analysis module for TicketInsight Pro.

Provides root cause identification using text clustering (KMeans) and
pattern matching for IT ticket data.  Supports both batch analysis
across multiple tickets and single-ticket prediction.

Usage
-----
    from ticketinsight.nlp.root_cause import RootCauseAnalyzer
    analyzer = RootCauseAnalyzer(config)
    result = analyzer.analyze(tickets)
"""

import math
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.root_cause")


class RootCauseAnalyzer:
    """Root cause analysis using text clustering and pattern recognition.

    Combines unsupervised clustering (KMeans on TF-IDF vectors) with
    rule-based pattern matching to identify common root causes across
    IT support tickets and generate actionable recommendations.
    """

    # ------------------------------------------------------------------ #
    #  Root cause patterns and configuration                              #
    # ------------------------------------------------------------------ #

    ROOT_CAUSE_PATTERNS: Dict[str, List[str]] = {
        "network": [
            "connectivity", "network", "dns", "firewall", "timeout",
            "latency", "bandwidth", "packet loss", "intermittent connection",
            "vpn disconnect", "wifi", "wireless", "access point",
            "dns resolution", "name resolution", "routing", "subnet",
            "gateway", "proxy", "load balancer",
        ],
        "authentication": [
            "login", "password", "credential", "authentication",
            "sso", "ldap", "active directory", "mfa", "two-factor",
            "locked out", "lockout", "expired password", "token",
            "certificate", "kerberos", "oauth", "saml",
        ],
        "software_bug": [
            "crash", "bug", "error", "exception", "fault", "defect",
            "stack trace", "null pointer", "segmentation fault",
            "unhandled exception", "application error", "runtime error",
            "compatibility issue", "version conflict", "regression",
        ],
        "hardware_failure": [
            "broken", "faulty", "damaged", "not working", "dead",
            "failed", "defective", "malfunctioning", "hardware fault",
            "physical damage", "overheating", "power failure",
            "bad sector", "disk error", "memory error", "replacement",
        ],
        "configuration": [
            "misconfigured", "configuration", "setting", "parameter",
            "registry", "group policy", "gpo", "wrong setting",
            "incorrect setting", "config file", "environment variable",
            "setup issue", "initialization", "provisioning error",
        ],
        "capacity": [
            "capacity", "space", "memory", "disk full", "storage",
            "performance", "out of memory", "oom", "low disk space",
            "resource exhaustion", "high cpu", "high memory",
            "disk usage", "quota exceeded", "storage full",
        ],
        "permission": [
            "permission", "denied", "unauthorized", "access denied",
            "forbidden", "insufficient privilege", "access control",
            "role", "security group", "acl", "not authorized",
        ],
        "third_party": [
            "vendor", "supplier", "external", "third-party", "api",
            "integration", "external service", "provider", "outage",
            "service degradation", "sla", "contract", "dependency",
        ],
        "user_error": [
            "accidentally", "mistake", "deleted", "wrong", "accident",
            "unaware", "misunderstanding", "user error", "human error",
            "inadvertently", "unintentionally", "training needed",
            "confused", "didn't know", "forgot",
        ],
        "scheduled": [
            "maintenance", "scheduled", "planned", "upgrade",
            "migration", "downtime", "change window", "patch tuesday",
            "scheduled outage", "planned maintenance", "rollout",
        ],
    }

    # Actionable recommendations per root cause
    _RECOMMENDATIONS: Dict[str, List[str]] = {
        "network": [
            "Review network infrastructure for recurring connectivity issues.",
            "Consider implementing network monitoring tools (Nagios, Zabbix).",
            "Evaluate WiFi coverage and access point placement.",
            "Schedule regular network health assessments.",
        ],
        "authentication": [
            "Implement self-service password reset to reduce authentication tickets.",
            "Review SSO/MFA policies for usability improvements.",
            "Ensure Active Directory/LDAP is properly synchronized.",
            "Provide user training on credential management best practices.",
        ],
        "software_bug": [
            "Escalate recurring software bugs to the vendor with detailed reproduction steps.",
            "Establish a software testing and QA process before deployments.",
            "Maintain a known issues knowledge base for common software bugs.",
            "Consider alternative software if bugs are persistent.",
        ],
        "hardware_failure": [
            "Review hardware age and plan proactive replacement cycles.",
            "Implement hardware monitoring for predictive failure detection.",
            "Maintain adequate spare hardware inventory for critical devices.",
            "Consider warranty extensions or maintenance contracts for aging equipment.",
        ],
        "configuration": [
            "Standardize configuration management using tools like Ansible or Puppet.",
            "Implement configuration drift detection.",
            "Create documented configuration baselines for all systems.",
            "Review Group Policy changes before deployment.",
        ],
        "capacity": [
            "Implement disk space and resource monitoring with alerting thresholds.",
            "Plan capacity upgrades based on growth projections.",
            "Implement automated cleanup policies for temporary files and logs.",
            "Review resource allocation for underutilized systems.",
        ],
        "permission": [
            "Review and simplify access control policies.",
            "Implement role-based access control (RBAC) where applicable.",
            "Automate common access provisioning/deprovisioning workflows.",
            "Conduct periodic access reviews.",
        ],
        "third_party": [
            "Review SLA compliance with third-party vendors.",
            "Establish redundancy for critical third-party dependencies.",
            "Implement circuit breaker patterns for external service integrations.",
            "Maintain vendor contact escalation procedures.",
        ],
        "user_error": [
            "Invest in user training and documentation.",
            "Improve application UI/UX to reduce user confusion.",
            "Create self-service knowledge base articles for common issues.",
            "Implement confirmation dialogs for destructive actions.",
        ],
        "scheduled": [
            "Improve change management communication to users.",
            "Schedule maintenance during low-impact windows.",
            "Provide advance notice of planned outages.",
            "Implement automated maintenance notifications.",
        ],
    }

    def __init__(self, config: Any = None):
        self.config = config
        self.vectorizer = None
        self.clusterer = None
        self.num_clusters = 10
        self.is_trained = False
        self._cluster_labels: Dict[int, str] = {}
        self._cluster_keywords: Dict[int, List[str]] = {}

        if config is not None:
            try:
                self.num_clusters = int(
                    config.get("nlp", "topic_num_topics", 10)
                )
            except (ValueError, TypeError):
                self.num_clusters = 10

        logger.info(
            "RootCauseAnalyzer initialized (num_clusters=%d)", self.num_clusters
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def analyze(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze root causes across multiple tickets.

        Clusters tickets by their text content and identifies the dominant
        root cause patterns in each cluster.

        Parameters
        ----------
        tickets : list[dict]
            List of ticket dictionaries with title, description, etc.

        Returns
        -------
        dict
            ``{
                "clusters": [{id, label, count, percentage, keywords, sample_tickets}, ...],
                "root_cause_distribution": {cause: count},
                "recommendations": [str, ...]
            }``
        """
        if not tickets:
            return {
                "clusters": [],
                "root_cause_distribution": {},
                "recommendations": [],
            }

        # Combine text from each ticket
        ticket_texts = []
        ticket_ids = []
        for ticket in tickets:
            title = ticket.get("title", "") or ""
            description = ticket.get("description", "") or ""
            resolution = ticket.get("resolution_notes", "") or ""
            text = sanitize_text(f"{title} {description} {resolution}")
            ticket_texts.append(text)
            ticket_ids.append(ticket.get("ticket_id", ticket.get("id", str(len(ticket_ids)))))

        # If we have a trained model, use it
        if self.is_trained and self.clusterer is not None and self.vectorizer is not None:
            try:
                return self._clustered_analysis(ticket_texts, ticket_ids, tickets)
            except Exception as exc:
                logger.warning("Clustered analysis failed, using pattern matching: %s", exc)

        # Fall back to pattern matching
        return self._pattern_based_analysis(ticket_texts, ticket_ids, tickets)

    def analyze_single(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Predict root cause for a single ticket.

        Parameters
        ----------
        ticket : dict
            Ticket dictionary.

        Returns
        -------
        dict
            ``{
                "predicted_cause": str,
                "confidence": float,
                "matched_keywords": [str, ...],
                "similar_tickets": [str, ...],
                "historical_resolution_time": float,
                "recommendation": str
            }``
        """
        title = ticket.get("title", "") or ""
        description = ticket.get("description", "") or ""
        text = sanitize_text(f"{title} {description}")

        if not text:
            return {
                "predicted_cause": "Unknown",
                "confidence": 0.0,
                "matched_keywords": [],
                "similar_tickets": [],
                "historical_resolution_time": 0.0,
                "recommendation": "",
            }

        # Use pattern matching for single ticket
        pattern_result = self._pattern_match(text)

        # Get recommendation
        cause = pattern_result["cause"]
        recommendations = self._RECOMMENDATIONS.get(cause, [])
        recommendation = recommendations[0] if recommendations else ""

        # Estimate resolution time based on root cause
        avg_resolution = self._estimate_resolution_time(cause)

        return {
            "predicted_cause": pattern_result["cause"],
            "confidence": pattern_result["confidence"],
            "matched_keywords": pattern_result["matched_keywords"],
            "similar_tickets": [],
            "historical_resolution_time": avg_resolution,
            "recommendation": recommendation,
        }

    def train(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train clustering model on resolved tickets.

        Parameters
        ----------
        tickets : list[dict]
            List of ticket dictionaries.

        Returns
        -------
        dict
            Training info: ``{"samples": int, "clusters": int, "method": str}``
        """
        if not tickets:
            raise ValueError("tickets must be non-empty")

        # Combine text from each ticket
        ticket_texts = []
        for ticket in tickets:
            title = ticket.get("title", "") or ""
            description = ticket.get("description", "") or ""
            resolution = ticket.get("resolution_notes", "") or ""
            text = sanitize_text(f"{title} {description} {resolution}")
            if text and len(text) > 10:
                ticket_texts.append(text)

        if len(ticket_texts) < max(3, self.num_clusters):
            logger.warning(
                "Too few valid tickets (%d) for %d clusters",
                len(ticket_texts),
                self.num_clusters,
            )
            # Reduce clusters
            self.num_clusters = max(2, len(ticket_texts) // 3)

        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans

        # Vectorize
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),
            stop_words="english",
            sublinear_tf=True,
            min_df=2,
            max_df=0.9,
        )

        X = self.vectorizer.fit_transform(ticket_texts)

        # Cluster
        actual_clusters = min(self.num_clusters, len(ticket_texts))
        self.clusterer = KMeans(
            n_clusters=actual_clusters,
            random_state=42,
            max_iter=300,
            n_init=10,
        )
        self.clusterer.fit(X)
        self.is_trained = True

        # Label clusters by examining top terms in each cluster
        self._label_clusters(self.vectorizer, self.clusterer, actual_clusters)

        info = {
            "samples": len(ticket_texts),
            "clusters": actual_clusters,
            "method": "kmeans_tfidf",
        }
        logger.info("RootCauseAnalyzer trained: %s", info)
        return info

    # ------------------------------------------------------------------ #
    #  Clustered analysis                                                 #
    # ------------------------------------------------------------------ #

    def _clustered_analysis(
        self,
        texts: List[str],
        ticket_ids: List[str],
        tickets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analyze using the trained clustering model."""
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        X = self.vectorizer.transform(texts)

        # Predict cluster assignments
        cluster_assignments = self.clusterer.predict(X)

        # Build cluster summaries
        total = len(texts)
        clusters = []
        root_cause_counts: Counter = Counter()

        for cluster_id in range(self.num_clusters):
            # Find tickets in this cluster
            indices = [
                i for i, c in enumerate(cluster_assignments) if c == cluster_id
            ]

            if not indices:
                continue

            # Get top keywords for this cluster
            keywords = self._cluster_keywords.get(cluster_id, [])
            label = self._cluster_labels.get(cluster_id, f"Cluster {cluster_id}")

            # Get sample tickets (top 3)
            sample_tickets = [ticket_ids[i] for i in indices[:3]]

            count = len(indices)
            percentage = round(count / max(1, total) * 100, 1)

            clusters.append({
                "id": int(cluster_id),
                "label": label,
                "count": count,
                "percentage": percentage,
                "keywords": keywords,
                "sample_tickets": sample_tickets,
            })

            # Map cluster to root cause
            cause = self._map_label_to_cause(label, keywords)
            if cause:
                root_cause_counts[cause] += count

        # Sort clusters by count descending
        clusters.sort(key=lambda c: c["count"], reverse=True)

        # Generate recommendations
        recommendations = self._generate_recommendations_from_distribution(
            root_cause_counts, total
        )

        return {
            "clusters": clusters,
            "root_cause_distribution": dict(root_cause_counts.most_common()),
            "recommendations": recommendations,
        }

    def _label_clusters(
        self, vectorizer, clusterer, num_clusters: int
    ) -> None:
        """Label each cluster by examining the most important terms."""
        feature_names = vectorizer.get_feature_names_out()

        for cluster_id in range(num_clusters):
            # Get cluster center
            center = clusterer.cluster_centers_[cluster_id]

            # Get top terms by weight in this cluster's centroid
            top_indices = center.argsort()[-10:][::-1]
            top_terms = [feature_names[i] for i in top_indices if i < len(feature_names)]

            self._cluster_keywords[cluster_id] = top_terms[:6]

            # Map to a root cause label
            best_cause = "Other"
            best_overlap = 0

            terms_lower = [t.lower() for t in top_terms]

            for cause, keywords in self.ROOT_CAUSE_PATTERNS.items():
                overlap = len(set(terms_lower) & set(keywords))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_cause = cause

            self._cluster_labels[cluster_id] = best_cause.capitalize()

    def _map_label_to_cause(self, label: str, keywords: List[str]) -> Optional[str]:
        """Map a cluster label to a root cause key."""
        label_lower = label.lower()

        for cause in self.ROOT_CAUSE_PATTERNS:
            if cause in label_lower or cause.replace("_", " ") in label_lower:
                return cause

        # Check keyword overlap
        keywords_lower = set(k.lower() for k in keywords)
        best_cause = None
        best_overlap = 0

        for cause, cause_keywords in self.ROOT_CAUSE_PATTERNS.items():
            overlap = len(keywords_lower & set(cause_keywords))
            if overlap > best_overlap:
                best_overlap = overlap
                best_cause = cause

        return best_cause if best_overlap >= 2 else None

    # ------------------------------------------------------------------ #
    #  Pattern-based analysis (fallback)                                  #
    # ------------------------------------------------------------------ #

    def _pattern_based_analysis(
        self,
        texts: List[str],
        ticket_ids: List[str],
        tickets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analyze root causes using keyword pattern matching."""
        total = len(texts)
        cause_assignments: List[Tuple[str, float, List[str]]] = []

        for text in texts:
            result = self._pattern_match(text)
            cause_assignments.append((
                result["cause"],
                result["confidence"],
                result["matched_keywords"],
            ))

        # Count root causes
        root_cause_counts: Counter = Counter()
        cause_ticket_groups: Dict[str, List[str]] = {}

        for i, (cause, confidence, keywords) in enumerate(cause_assignments):
            root_cause_counts[cause] += 1
            if cause not in cause_ticket_groups:
                cause_ticket_groups[cause] = []
            cause_ticket_groups[cause].append(ticket_ids[i])

        # Build clusters from pattern results
        clusters = []
        for cause, count in root_cause_counts.most_common():
            # Get aggregated keywords for this cause
            all_keywords: Counter = Counter()
            for i, (c, _, kws) in enumerate(cause_assignments):
                if c == cause:
                    all_keywords.update(kws)

            clusters.append({
                "id": len(clusters),
                "label": cause.replace("_", " ").title(),
                "count": count,
                "percentage": round(count / max(1, total) * 100, 1),
                "keywords": [kw for kw, _ in all_keywords.most_common(6)],
                "sample_tickets": cause_ticket_groups.get(cause, [])[:3],
            })

        # Generate recommendations
        recommendations = self._generate_recommendations_from_distribution(
            root_cause_counts, total
        )

        return {
            "clusters": clusters,
            "root_cause_distribution": dict(root_cause_counts.most_common()),
            "recommendations": recommendations,
        }

    def _pattern_match(self, text: str) -> Dict[str, Any]:
        """Rule-based root cause matching from text patterns.

        Scores each root cause category by the number and weight of
        matching keywords.  Returns the best match.

        Parameters
        ----------
        text : str
            Cleaned ticket text.

        Returns
        -------
        dict
            ``{cause: str, confidence: float, matched_keywords: [str, ...]}``
        """
        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        cause_scores: Dict[str, Tuple[float, List[str]]] = {}

        for cause, keywords in self.ROOT_CAUSE_PATTERNS.items():
            matched = []
            score = 0.0

            for keyword in keywords:
                keyword_lower = keyword.lower()
                # Check multi-word phrases
                if " " in keyword_lower:
                    if keyword_lower in text_lower:
                        matched.append(keyword)
                        score += 1.5  # Multi-word matches are more specific
                else:
                    # Single-word match
                    if keyword_lower in words:
                        matched.append(keyword)
                        score += 1.0

            cause_scores[cause] = (score, matched)

        # Find the best matching cause
        best_cause = "Unknown"
        best_score = 0.0
        best_keywords = []

        for cause, (score, matched) in cause_scores.items():
            if score > best_score:
                best_score = score
                best_cause = cause
                best_keywords = matched

        # Calculate confidence
        if best_score <= 0:
            confidence = 0.0
            best_cause = "Unknown"
            best_keywords = []
        else:
            # Confidence based on how much the best cause stands out
            all_scores = [s for s, _ in cause_scores.values() if s > 0]
            if all_scores:
                total_score = sum(all_scores)
                confidence = best_score / max(1, total_score)
                # Boost confidence for high absolute matches
                confidence = min(1.0, confidence * (1 + best_score * 0.1))
            else:
                confidence = 0.0

        return {
            "cause": best_cause,
            "confidence": round(confidence, 4),
            "matched_keywords": best_keywords,
        }

    # ------------------------------------------------------------------ #
    #  Recommendations                                                    #
    # ------------------------------------------------------------------ #

    def _generate_recommendations_from_distribution(
        self,
        root_cause_counts: Counter,
        total_tickets: int,
    ) -> List[str]:
        """Generate actionable recommendations based on root cause analysis.

        For each significant root cause (>5% of tickets), generates
        targeted recommendations.  Also generates a high-level summary.

        Parameters
        ----------
        root_cause_counts : Counter
            Root cause -> ticket count mapping.
        total_tickets : int
            Total number of tickets analyzed.

        Returns
        -------
        list[str]
            List of recommendation strings.
        """
        recommendations = []

        # Sort by frequency descending
        for cause, count in root_cause_counts.most_common():
            percentage = count / max(1, total_tickets) * 100

            if percentage < 5:
                continue

            cause_title = cause.replace("_", " ").title()
            recommendations.append(
                f"{cause_title} issues account for {percentage:.1f}% of tickets "
                f"({count} tickets)."
            )

            # Add specific recommendations for this cause
            cause_recs = self._RECOMMENDATIONS.get(cause, [])
            if cause_recs:
                # Add the top 2 recommendations
                for rec in cause_recs[:2]:
                    recommendations.append(f"  → {rec}")

        # Add a summary recommendation if there are clear top issues
        if root_cause_counts:
            top_cause, top_count = root_cause_counts.most_common(1)[0]
            top_percentage = top_count / max(1, total_tickets) * 100

            if top_percentage > 25:
                top_title = top_cause.replace("_", " ").title()
                recommendations.append(
                    f"Priority recommendation: Focus on {top_title} issues, "
                    f"which represent the largest share of tickets at "
                    f"{top_percentage:.1f}%."
                )

        if not recommendations:
            recommendations.append(
                "Ticket volume is distributed across many root causes. "
                "Consider collecting more data for a targeted analysis."
            )

        return recommendations

    def _estimate_resolution_time(self, cause: str) -> float:
        """Estimate average resolution time in hours based on root cause.

        Uses typical resolution time ranges for each root cause category
        based on industry benchmarks.

        Parameters
        ----------
        cause : str
            Root cause key.

        Returns
        -------
        float
            Estimated average resolution time in hours.
        """
        # Average resolution times in hours (based on ITSM benchmarks)
        _RESOLUTION_ESTIMATES = {
            "network": 8.0,
            "authentication": 2.0,
            "software_bug": 16.0,
            "hardware_failure": 24.0,
            "configuration": 4.0,
            "capacity": 6.0,
            "permission": 3.0,
            "third_party": 48.0,
            "user_error": 1.5,
            "scheduled": 2.0,
            "unknown": 8.0,
        }

        return _RESOLUTION_ESTIMATES.get(cause, 8.0)
