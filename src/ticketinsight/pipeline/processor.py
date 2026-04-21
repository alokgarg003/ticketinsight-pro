"""
Data processor for TicketInsight Pro.

Processes raw ticket data that has been ingested into the database:
cleaning text fields, normalising priorities/statuses, deduplicating
tickets, and enriching records with derived data.

Implements TF-IDF + cosine similarity for efficient duplicate detection
using scikit-learn.

Usage
-----
    from ticketinsight.pipeline.processor import DataProcessor

    processor = DataProcessor(config, db_manager)
    result = processor.process_tickets()
    duplicates = processor.find_potential_duplicates(threshold=0.85)
"""

import re
import time as _time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import (
    sanitize_text,
    normalize_priority,
    normalize_status,
    parse_date,
    calculate_hash,
    chunk_list,
)

__all__ = ["DataProcessor"]


# ---------------------------------------------------------------------------
# Keyword → category mapping for title-based category derivation
# ---------------------------------------------------------------------------
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Email": [
        "email", "outlook", "exchange", "mailbox", "mail", "smtp",
        "imap", "inbox", "calendar", "meeting invite", "autodiscover",
        "ews", "o365", "office 365", "gmail", "distribution list",
    ],
    "Network": [
        "network", "wifi", "wi-fi", "vpn", "dns", "firewall", "proxy",
        "dhcp", "ip address", "subnet", "router", "switch", "bandwidth",
        "latency", "ping", "connectivity", "internet", "wlan", "lan",
        "vlan", "access point", "cable", "fiber",
    ],
    "Hardware": [
        "laptop", "desktop", "printer", "monitor", "keyboard", "mouse",
        "dock", "docking", "screen", "display", "hard drive", "ram",
        "memory", "ssd", "hdd", "battery", "power supply", "usb",
        "headset", "webcam", "phone", "tablet", "scanner", "workstation",
    ],
    "Software": [
        "software", "install", "uninstall", "update", "upgrade",
        "application", "app ", "crash", "freeze", "hang", "bug",
        "error", "license", "package", "dll", "registry", "patch",
        "version", "compatibility", "plugin", "extension", "addon",
    ],
    "Access Management": [
        "access", "permission", "account", "password", "reset",
        "mfa", "sso", "login", "unlock", "onboard", "offboard",
        "active directory", "ad ", "ldap", "saml", "role",
        "authorization", "credentials", "provision", "deprovision",
    ],
    "Security": [
        "security", "malware", "virus", "phishing", "breach",
        "suspicious", "unauthorized", "intrusion", "audit", "compliance",
        "encryption", "threat", "vulnerability", "incident response",
        "soc", "siem", "endpoint", "antivirus", "ransomware",
    ],
    "Database": [
        "database", "db ", "sql", "query", "timeout", "connection pool",
        "backup", "restore", "replication", "index", "table", "schema",
        "oracle", "mysql", "postgresql", "postgres", "mssql",
    ],
    "Audio/Visual": [
        "audio", "video", "conference", "zoom", "teams", "webex",
        "projector", "speaker", "microphone", "polycom", "av ",
        "teleconference", "screen share", "webcam",
    ],
}

# Keywords mapped to severity estimates for enrichment
_SEVERITY_KEYWORDS: Dict[str, List[str]] = {
    "Critical": [
        "outage", "down", "critical", "emergency", "urgent", "production",
        "security breach", "data loss", "system unavailable", "complete",
        "all users", "company-wide", "enterprise", "total", "severe",
    ],
    "High": [
        "multiple", "several", "team", "department", "failing",
        "degraded", "partial", "escalation", "intermittent", "major",
        "significant", "business impact", "revenue",
    ],
    "Low": [
        "cosmetic", "minor", "trivial", "nice to have", "suggestion",
        "enhancement", "request", "information", "question", "how to",
    ],
}


class DataProcessor:
    """Processes raw ticket data: cleaning, enrichment, deduplication.

    Parameters
    ----------
    config : ConfigManager
        Application configuration manager.
    db_manager : DatabaseManager
        Initialized database manager with an active Flask app context.

    Attributes
    ----------
    _tfidf_vectorizer : TfidfVectorizer | None
        Cached TF-IDF vectorizer for duplicate detection.
    """

    def __init__(self, config: Any, db_manager: Any) -> None:
        self.config = config
        self.db_manager = db_manager
        self.logger = get_logger(__name__)
        self._tfidf_vectorizer: Any = None
        self._last_process_stats: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_tickets(
        self,
        ticket_ids: Optional[List[int]] = None,
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """Process all or specified tickets through the processing pipeline.

        Steps for each ticket:
            1. Fetch ticket from DB.
            2. Clean text fields (title, description).
            3. Normalise priority and status to canonical values.
            4. Calculate text hash for deduplication (stored in raw_data).
            5. Enrich missing fields (derive category from title, estimate severity).
            6. Mark potential duplicates via post-processing pass.

        Parameters
        ----------
        ticket_ids : list[int] | None
            Specific ticket DB IDs to process.  If ``None``, processes all.
        batch_size : int
            Number of tickets to process per database transaction.

        Returns
        -------
        dict
            ``{
                "processed": int,
                "cleaned": int,
                "enriched": int,
                "duplicates_found": int,
                "errors": list[str],
                "duration_seconds": float,
            }``
        """
        start_time = _time.monotonic()

        stats: Dict[str, Any] = {
            "processed": 0,
            "cleaned": 0,
            "enriched": 0,
            "duplicates_found": 0,
            "errors": [],
            "duration_seconds": 0.0,
        }

        self._log("info", "Starting data processing pipeline")

        # Fetch tickets
        try:
            tickets = self._fetch_tickets(ticket_ids)
            self._log("info", "Fetched %d tickets for processing", len(tickets))
        except Exception as exc:
            msg = f"Error fetching tickets: {exc}"
            self._log("error", msg)
            stats["errors"].append(msg)
            stats["duration_seconds"] = round(_time.monotonic() - start_time, 3)
            return stats

        if not tickets:
            self._log("info", "No tickets to process")
            stats["duration_seconds"] = round(_time.monotonic() - start_time, 3)
            return stats

        # Process in batches
        for batch in chunk_list(tickets, batch_size):
            batch_result = self._process_batch(batch)
            stats["processed"] += batch_result["processed"]
            stats["cleaned"] += batch_result["cleaned"]
            stats["enriched"] += batch_result["enriched"]
            stats["errors"].extend(batch_result["errors"])

        # Duplicate detection pass
        try:
            duplicates = self.find_potential_duplicates(
                threshold=float(
                    self.config.get("nlp", "duplicate_threshold", 0.85)
                    if hasattr(self.config, "get")
                    else 0.85
                )
            )
            stats["duplicates_found"] = len(duplicates)

            # Mark duplicates in the database
            marked = self._mark_duplicates(duplicates)
            self._log("info", "Marked %d duplicate pairs", marked)

        except Exception as exc:
            msg = f"Error during duplicate detection: {exc}"
            self._log("error", msg)
            stats["errors"].append(msg)

        stats["duration_seconds"] = round(_time.monotonic() - start_time, 3)
        self._log(
            "info",
            "Processing complete: %d processed, %d cleaned, %d enriched, "
            "%d duplicates (%.2fs)",
            stats["processed"],
            stats["cleaned"],
            stats["enriched"],
            stats["duplicates_found"],
            stats["duration_seconds"],
        )

        self._last_process_stats = stats
        return stats

    def clean_ticket(self, ticket: Any) -> Dict[str, Any]:
        """Clean and standardize a single ticket.

        Parameters
        ----------
        ticket : Ticket
            Ticket ORM model instance.

        Returns
        -------
        dict
            ``{"cleaned_fields": list[str], "changes": dict}``
        """
        changes: Dict[str, Any] = {}
        cleaned_fields: List[str] = []

        # Clean title
        raw_title = ticket.title or ""
        clean_title = sanitize_text(raw_title)
        if clean_title != raw_title:
            changes["title"] = {"old": raw_title, "new": clean_title}
            ticket.title = clean_title
            cleaned_fields.append("title")

        # Clean description
        raw_desc = ticket.description or ""
        clean_desc = sanitize_text(raw_desc)
        if clean_desc != raw_desc:
            changes["description"] = {"old": raw_desc[:100], "new": clean_desc[:100]}
            ticket.description = clean_desc
            cleaned_fields.append("description")

        # Normalise priority
        raw_priority = ticket.priority or ""
        norm_priority = normalize_priority(raw_priority)
        if norm_priority != raw_priority:
            changes["priority"] = {"old": raw_priority, "new": norm_priority}
            ticket.priority = norm_priority
            cleaned_fields.append("priority")

        # Normalise status
        raw_status = ticket.status or ""
        norm_status = normalize_status(raw_status)
        if norm_status != raw_status:
            changes["status"] = {"old": raw_status, "new": norm_status}
            ticket.status = norm_status
            cleaned_fields.append("status")

        # Normalise assignee
        raw_assignee = ticket.assignee or ""
        if raw_assignee:
            clean_assignee = sanitize_text(raw_assignee)
            if clean_assignee != raw_assignee:
                changes["assignee"] = {"old": raw_assignee, "new": clean_assignee}
                ticket.assignee = clean_assignee
                cleaned_fields.append("assignee")

        # Normalise assignment_group
        raw_group = ticket.assignment_group or ""
        if raw_group:
            clean_group = sanitize_text(raw_group)
            if clean_group != raw_group:
                changes["assignment_group"] = {"old": raw_group, "new": clean_group}
                ticket.assignment_group = clean_group
                cleaned_fields.append("assignment_group")

        # Calculate text hash for deduplication
        text_for_hash = f"{ticket.title or ''} {ticket.description or ''}"
        text_hash = calculate_hash(text_for_hash)
        raw_data = ticket.raw_data or {}
        if raw_data.get("text_hash") != text_hash:
            raw_data["text_hash"] = text_hash
            ticket.raw_data = raw_data
            cleaned_fields.append("text_hash")

        return {"cleaned_fields": cleaned_fields, "changes": changes}

    def enrich_ticket(self, ticket: Any) -> Dict[str, Any]:
        """Enrich a ticket with derived data.

        Enrichment strategies:
            - **Category derivation**: If ``category`` is empty, scan the
              title and description for known keywords and assign the best
              matching category.
            - **Severity estimation**: Estimate a severity level based on
              keyword patterns in the title.

        Parameters
        ----------
        ticket : Ticket
            Ticket ORM model instance.

        Returns
        -------
        dict
            ``{"enriched_fields": list[str], "enrichments": dict}``
        """
        enrichments: Dict[str, Any] = {}
        enriched_fields: List[str] = []

        title = (ticket.title or "").lower()
        description = (ticket.description or "").lower()
        combined_text = f"{title} {description}"

        # Derive category if missing
        if not ticket.category or ticket.category.strip() == "":
            derived_category = self._derive_category(title, description)
            if derived_category:
                ticket.category = derived_category
                enrichments["category"] = derived_category
                enriched_fields.append("category")

        # Estimate severity / priority refinement
        if not ticket.priority or ticket.priority == "Medium":
            severity = self._estimate_severity(title, description)
            if severity:
                enrichments["estimated_severity"] = severity
                enriched_fields.append("estimated_severity")

        return {"enriched_fields": enriched_fields, "enrichments": enrichments}

    def find_potential_duplicates(
        self,
        threshold: float = 0.85,
        source_system: Optional[str] = None,
    ) -> List[Tuple[int, int, float]]:
        """Find potential duplicate tickets using TF-IDF + cosine similarity.

        Vectorises the concatenation of title and description for all tickets,
        computes the pairwise cosine similarity matrix, and returns pairs
        whose similarity exceeds *threshold*.

        Parameters
        ----------
        threshold : float
            Minimum cosine similarity to consider a pair as duplicate
            (0.0–1.0, default 0.85).
        source_system : str | None
            If provided, only search within tickets from this source.

        Returns
        -------
        list[tuple]
            List of ``(ticket_db_id_1, ticket_db_id_2, similarity_score)``
            tuples where ``id_1 < id_2``.
        """
        from ticketinsight.storage.database import db, Ticket

        app = self.db_manager._app
        if app is None:
            raise RuntimeError("DatabaseManager not initialised")

        with app.app_context():
            # Build query
            query = Ticket.query.filter(
                db.or_(
                    Ticket.title.isnot(None),
                    Ticket.description.isnot(None),
                )
            )

            if source_system:
                query = query.filter(Ticket.source_system == source_system)

            tickets = query.all()

        if len(tickets) < 2:
            self._log("info", "Not enough tickets for duplicate detection (%d)", len(tickets))
            return []

        self._log("info", "Running duplicate detection on %d tickets (threshold=%.2f)", len(tickets), threshold)

        # Build text corpus
        ticket_ids: List[int] = []
        texts: List[str] = []

        for t in tickets:
            text = f"{t.title or ''} {(t.description or '')[:500]}"
            text = sanitize_text(text)
            if text:
                ticket_ids.append(t.id)
                texts.append(text)

        if len(texts) < 2:
            return []

        # TF-IDF vectorization
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
        except ImportError as exc:
            self._log("error", "scikit-learn or numpy not available: %s", exc)
            return []

        vectorizer = TfidfVectorizer(
            max_features=10000,
            stop_words="english",
            min_df=1,
            max_df=0.95,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(texts)
        except ValueError as exc:
            self._log("warning", "TF-IDF vectorization failed: %s", exc)
            return []

        # Compute cosine similarity matrix
        similarity_matrix = cosine_similarity(tfidf_matrix)

        # Extract pairs above threshold
        duplicates: List[Tuple[int, int, float]] = []
        n = len(ticket_ids)

        for i in range(n):
            for j in range(i + 1, n):
                score = float(similarity_matrix[i, j])
                if score >= threshold:
                    # Ensure consistent ordering (lower id first)
                    id_a, id_b = ticket_ids[i], ticket_ids[j]
                    if id_a > id_b:
                        id_a, id_b = id_b, id_a
                    duplicates.append((id_a, id_b, round(score, 4)))

        self._log(
            "info",
            "Duplicate detection found %d potential pairs above %.2f",
            len(duplicates),
            threshold,
        )

        return duplicates

    def get_last_stats(self) -> Dict[str, Any]:
        """Return statistics from the most recent processing run.

        Returns
        -------
        dict
        """
        return self._last_process_stats

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _fetch_tickets(self, ticket_ids: Optional[List[int]] = None) -> list:
        """Fetch ticket ORM objects from the database.

        Parameters
        ----------
        ticket_ids : list[int] | None
            If provided, fetch only these specific IDs.

        Returns
        -------
        list[Ticket]
        """
        from ticketinsight.storage.database import Ticket

        app = self.db_manager._app
        if app is None:
            raise RuntimeError("DatabaseManager not initialised")

        with app.app_context():
            if ticket_ids is not None:
                return Ticket.query.filter(Ticket.id.in_(ticket_ids)).all()
            else:
                return Ticket.query.all()

    def _process_batch(self, batch: list) -> Dict[str, Any]:
        """Process a batch of ticket ORM objects.

        Parameters
        ----------
        batch : list[Ticket]
            Ticket ORM instances.

        Returns
        -------
        dict
            Batch statistics.
        """
        result: Dict[str, Any] = {
            "processed": 0,
            "cleaned": 0,
            "enriched": 0,
            "errors": [],
        }

        from ticketinsight.storage.database import db

        app = self.db_manager._app
        if app is None:
            raise RuntimeError("DatabaseManager not initialised")

        with app.app_context():
            for ticket in batch:
                try:
                    # Clean
                    clean_result = self.clean_ticket(ticket)
                    if clean_result["cleaned_fields"]:
                        result["cleaned"] += 1

                    # Enrich
                    enrich_result = self.enrich_ticket(ticket)
                    if enrich_result["enriched_fields"]:
                        result["enriched"] += 1

                    result["processed"] += 1

                except Exception as exc:
                    tid = getattr(ticket, "id", "?")
                    msg = f"Error processing ticket ID {tid}: {exc}"
                    self._log("error", msg)
                    result["errors"].append(msg)

            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                msg = f"Batch commit error: {exc}"
                self._log("error", msg)
                result["errors"].append(msg)

        return result

    def _mark_duplicates(self, duplicates: List[Tuple[int, int, float]]) -> int:
        """Mark duplicate pairs in the database.

        For each pair, the older ticket (by ``id``) is set as the canonical
        record, and the newer ticket's ``duplicate_of_id`` is set to the
        older ticket's ``id``.

        Parameters
        ----------
        duplicates : list[tuple]
            List of ``(id_a, id_b, score)`` tuples.

        Returns
        -------
        int
            Number of tickets marked as duplicates.
        """
        from ticketinsight.storage.database import db, Ticket

        if not duplicates:
            return 0

        app = self.db_manager._app
        if app is None:
            return 0

        marked = 0

        with app.app_context():
            for id_a, id_b, score in duplicates:
                try:
                    # id_a < id_b, so id_a is the canonical ticket
                    newer = Ticket.query.get(id_b)
                    if newer is not None and newer.duplicate_of_id is None:
                        newer.duplicate_of_id = id_a
                        marked += 1
                except Exception as exc:
                    self._log(
                        "warning",
                        "Failed to mark duplicate %d→%d: %s",
                        id_b,
                        id_a,
                        exc,
                    )

            if marked > 0:
                try:
                    db.session.commit()
                except Exception as exc:
                    db.session.rollback()
                    self._log("error", "Failed to commit duplicate marks: %s", exc)

        return marked

    @staticmethod
    def _derive_category(title: str, description: str) -> Optional[str]:
        """Derive a category from ticket title and description keywords.

        Scans the combined text for known keywords associated with each
        category and returns the category with the most keyword matches.

        Parameters
        ----------
        title : str
            Lowercase ticket title.
        description : str
            Lowercase ticket description.

        Returns
        -------
        str | None
            Best-matching category, or ``None`` if no match found.
        """
        combined = f"{title} {description}".lower()

        best_category = None
        best_score = 0

        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    @staticmethod
    def _estimate_severity(title: str, description: str) -> Optional[str]:
        """Estimate severity from ticket text keywords.

        Parameters
        ----------
        title : str
            Lowercase ticket title.
        description : str
            Lowercase ticket description.

        Returns
        -------
        str | None
            Estimated severity level, or ``None`` if uncertain.
        """
        combined = f"{title} {description}".lower()

        for severity, keywords in _SEVERITY_KEYWORDS.items():
            for kw in keywords:
                if kw in combined:
                    return severity

        return None

    def _log(self, level: str, msg: str, *args: Any) -> None:
        """Internal logging helper."""
        getattr(self.logger, level)(msg, *args)
