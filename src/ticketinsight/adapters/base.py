"""
Abstract base class for all ticket system adapters.

Every concrete adapter (ServiceNow, Jira, CSV, Universal) must inherit from
:class:`BaseAdapter` and implement the four abstract methods:
    - :meth:`connect`
    - :meth:`fetch_tickets`
    - :meth:`fetch_ticket`
    - :meth:`health_check`

The base class also provides a comprehensive :meth:`normalize_ticket` that
maps ~50 common field-name variations from different ticket systems into the
canonical TicketInsight schema.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import (
    sanitize_text,
    normalize_priority,
    normalize_status,
    parse_date,
    calculate_hash,
)

__all__ = ["BaseAdapter"]

# ---------------------------------------------------------------------------
# Canonical field-name → list of common source variations
# ---------------------------------------------------------------------------
_FIELD_ALIASES: Dict[str, List[str]] = {
    "ticket_id": [
        "ticket_id", "number", "sys_id", "incident_id", "issue_id",
        "id", "key", "case_number", "case_id", "request_id", "req_id",
        "ticket_number", "ticket no", "ticket no.", "ticket #",
        "ref", "reference", "external_id", "ext_id",
        "inc_number", "problem_id", "change_id", "task_id", "item_id",
        "record_id", "object_id", "uid", "code", "num",
    ],
    "title": [
        "title", "short_description", "subject", "summary", "name",
        "heading", "headline", "issue_title", "ticket_title",
        "problem_title", "brief_description", "ticket_name",
        "case_title", "request_title", "incident_title", "item_title",
        "issue subject", "case subject", "topic",
    ],
    "description": [
        "description", "comments", "body", "content", "text",
        "details", "narrative", "full_description", "long_description",
        "problem_description", "issue_description", "ticket_description",
        "description_text", "notes", "work_notes", "additional_comments",
        "resolution_notes", "root_cause", "message", "body_text",
        "detail", "explanation", "info", "comment", "remark",
    ],
    "priority": [
        "priority", "urgency", "impact", "severity", "importance",
        "ticket_priority", "issue_priority", "case_priority", "level",
    ],
    "status": [
        "status", "state", "workflow_state", "ticket_status",
        "issue_status", "case_status", "incident_state", "request_state",
        "life_cycle_state", "current_state", "progress", "stage",
        "current status",
    ],
    "category": [
        "category", "subcategory", "type", "issue_type", "ticket_type",
        "case_type", "incident_type", "classification", "service_type",
        "request_type", "problem_type", "topic", "area", "group_type",
    ],
    "assignment_group": [
        "assignment_group", "team", "group", "assigned_group",
        "support_group", "assigned_team", "owner_group", "department",
        "workgroup", "responsible_group", "service_team", "queue",
        "support team", "support group",
    ],
    "assignee": [
        "assignee", "assigned_to", "owner", "responsible", "technician",
        "agent", "handler", "worker", "contact", "support_engineer",
        "assigned_user", "developer", "resolver",
    ],
    "opened_at": [
        "opened_at", "opened", "created", "created_at", "sys_created_on",
        "open_time", "reported_at", "submitted_at", "submitted",
        "date_opened", "creation_date", "created_date", "opened_on",
        "reported_on", "submit_date", "open_date", "start_date",
        "date_created", "sys_created", "opened_date",
    ],
    "resolved_at": [
        "resolved_at", "resolved", "resolution_date", "closed_at",
        "close_time", "date_resolved", "resolved_on", "resolved_date",
        "completion_date", "finish_date", "end_date", "date_closed",
        "sys_resolved", "resolution_time", "fix_date", "fix_time",
    ],
    "closed_at": [
        "closed_at", "closed", "close_time", "date_closed", "closed_on",
        "closure_date", "sys_closed", "close_date", "date_completed",
    ],
    "updated_at": [
        "updated_at", "updated", "sys_updated_on", "last_modified",
        "last_update", "modified_at", "last_modified_date", "change_date",
        "modified_on", "sys_updated", "last_changed", "date_updated",
    ],
    "source_system": [
        "source_system", "source", "origin", "system", "provider",
        "import_source", "data_source", "source_name",
    ],
    "affected_service": [
        "affected_service", "cmdb_ci", "service", "configuration_item",
        "ci_name", "service_name", "affected_item", "asset",
    ],
    "caller": [
        "caller", "caller_id", "caller_name", "opened_by",
        "reported_by", "requester", "customer", "user", "requestor",
        "end_user", "contact_name", "created_by", "initiator", "submitter",
    ],
}


class BaseAdapter(ABC):
    """Abstract base class for all ticket system adapters.

    Parameters
    ----------
    config : dict
        Adapter-specific configuration.  Concrete adapters document which
        keys they require.

    Attributes
    ----------
    config : dict
        Raw configuration dictionary.
    logger : logging.Logger | None
        Set via :meth:`set_logger`; used for structured logging.
    _session : requests.Session | None
        Internal HTTP session (used by API-based adapters).
    """

    def __init__(self, config: dict):
        self.config = config
        self.logger: Any = None
        self._session: Any = None

    def set_logger(self, logger: Any) -> None:
        """Attach a logger instance to this adapter.

        Parameters
        ----------
        logger : logging.Logger
            A named logger obtained from :func:`~ticketinsight.utils.logger.get_logger`.
        """
        self.logger = logger

    def _log(self, level: str, msg: str, *args: Any) -> None:
        """Internal helper that safely logs even if no logger is attached."""
        if self.logger is None:
            self.logger = get_logger(self.__class__.__module__ + "." + self.__class__.__name__)
        getattr(self.logger, level)(msg, *args)

    # ------------------------------------------------------------------
    # Abstract methods — every adapter MUST implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the ticket system.

        Returns
        -------
        bool
            ``True`` if the connection was successful, ``False`` otherwise.
        """

    @abstractmethod
    def fetch_tickets(
        self,
        query: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch tickets from the source system.

        Parameters
        ----------
        query : str | None
            Optional filter / search query native to the source system.
        limit : int
            Maximum number of tickets to return.
        offset : int
            Number of tickets to skip (for pagination).
        date_from : datetime | None
            Include only tickets opened on or after this date.
        date_to : datetime | None
            Include only tickets opened on or before this date.
        **kwargs
            Additional adapter-specific parameters.

        Returns
        -------
        list[dict]
            List of normalised ticket dictionaries.
        """

    @abstractmethod
    def fetch_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single ticket by its external ID.

        Parameters
        ----------
        ticket_id : str
            The external ticket identifier.

        Returns
        -------
        dict | None
            Normalised ticket dictionary, or ``None`` if not found.
        """

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Check connection health.

        Returns
        -------
        dict
            ``{"status": "ok"|"error", "latency_ms": float, "message": str}``
        """

    # ------------------------------------------------------------------
    # Shared normalisation logic
    # ------------------------------------------------------------------

    def normalize_ticket(self, raw_ticket: dict) -> dict:
        """Transform raw ticket data into the canonical TicketInsight format.

        This implementation probes the raw dictionary for common field-name
        aliases (see :data:`_FIELD_ALIASES`) and maps them to canonical
        field names.  Text fields are sanitised, priorities/statuses are
        normalised, and dates are parsed flexibly.

        Subclasses may override this to add source-specific mappings
        (e.g. ServiceNow ``cmdb_ci`` → ``affected_service``) before
        delegating to ``super().normalize_ticket(raw_ticket)``.

        Parameters
        ----------
        raw_ticket : dict
            Raw ticket dictionary from the source system.

        Returns
        -------
        dict
            Normalised ticket with canonical field names.
        """
        if raw_ticket is None or not isinstance(raw_ticket, dict):
            return {}

        normalized: Dict[str, Any] = {}

        # ---- Map each canonical field from its aliases ----
        for canonical_field, aliases in _FIELD_ALIASES.items():
            value = self._find_field_value(raw_ticket, aliases)

            if value is None:
                normalized[canonical_field] = "" if canonical_field != "source_system" else ""
                continue

            # Field-specific transformations
            if canonical_field == "title":
                normalized[canonical_field] = sanitize_text(str(value))
            elif canonical_field == "description":
                normalized[canonical_field] = sanitize_text(str(value))
            elif canonical_field == "priority":
                normalized[canonical_field] = normalize_priority(str(value))
            elif canonical_field == "status":
                normalized[canonical_field] = normalize_status(str(value))
            elif canonical_field in ("opened_at", "resolved_at", "closed_at", "updated_at"):
                normalized[canonical_field] = parse_date(str(value))
            elif canonical_field in ("ticket_id", "assignee", "assignment_group", "category"):
                normalized[canonical_field] = sanitize_text(str(value))
            elif canonical_field == "source_system":
                normalized[canonical_field] = sanitize_text(str(value)) or "unknown"
            elif canonical_field == "caller":
                normalized[canonical_field] = sanitize_text(str(value))
            elif canonical_field == "affected_service":
                normalized[canonical_field] = sanitize_text(str(value))
            else:
                normalized[canonical_field] = value

        # ---- Defaults ----
        if not normalized.get("ticket_id"):
            # Fall back to generating a hash-based ID from title+description
            combined = (normalized.get("title") or "") + (normalized.get("description") or "")
            if combined:
                normalized["ticket_id"] = calculate_hash(combined)[:16]
            else:
                normalized["ticket_id"] = calculate_hash(str(raw_ticket))[:16]

        if not normalized.get("title"):
            normalized["title"] = "Untitled"

        if not normalized.get("priority"):
            normalized["priority"] = "Medium"

        if not normalized.get("status"):
            normalized["status"] = "Open"

        # ---- Store raw data for auditability ----
        normalized["raw_data"] = raw_ticket

        return normalized

    @staticmethod
    def _find_field_value(data: dict, aliases: List[str]) -> Any:
        """Return the first non-empty value found in *data* for any of *aliases*.

        Search is case-insensitive and also checks for nested keys using
        dot-notation (e.g. ``priority.name``).

        Parameters
        ----------
        data : dict
            The source ticket dictionary.
        aliases : list[str]
            Candidate field names to try.

        Returns
        -------
        Any | None
            The first non-empty value, or ``None``.
        """
        # Build a lowercase-keyed lookup for case-insensitive matching.
        # Also build a "normalised" key map that replaces spaces/underscores
        # so that "Ticket Number" matches "ticket_number" and vice versa.
        def _normalise_key(key: str) -> str:
            return key.lower().replace(" ", "_").replace("-", "_")

        lower_keys = {k.lower(): k for k in data.keys()}
        norm_keys = {_normalise_key(k): k for k in data.keys()}

        for alias in aliases:
            # Direct match (case-insensitive)
            lower_alias = alias.lower()
            if lower_alias in lower_keys:
                real_key = lower_keys[lower_alias]
                val = data[real_key]
                if val is not None and val != "":
                    return val

            # Normalised match (case-insensitive + space/underscore interchangeable)
            norm_alias = _normalise_key(alias)
            if norm_alias in norm_keys:
                real_key = norm_keys[norm_alias]
                val = data[real_key]
                if val is not None and val != "":
                    return val

            # Dot-notation nested lookup
            if "." in alias:
                parts = alias.split(".")
                obj = data
                for part in parts:
                    if not isinstance(obj, dict):
                        obj = None
                        break
                    # Try case-insensitive
                    part_lower = part.lower()
                    matched = False
                    for k, v in obj.items():
                        if k.lower() == part_lower:
                            obj = v
                            matched = True
                            break
                    if not matched:
                        obj = None
                        break
                if obj is not None and obj != "":
                    return obj

        return None

    def close(self) -> None:
        """Clean up connections and release resources."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            finally:
                self._session = None
