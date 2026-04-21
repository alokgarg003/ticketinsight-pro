"""
ServiceNow adapter for TicketInsight Pro.

Connects to a ServiceNow instance via its REST Table API (``/api/now/table/``)
and retrieves incident records.  Supports full CRUD, date-range filtering,
custom queries, pagination, and automatic field normalisation.

Configuration keys
------------------
``instance``  (str, required) — Full ServiceNow URL, e.g.
    ``https://mycompany.service-now.com``
``username``  (str, required) — ServiceNow username.
``password``  (str, required) — ServiceNow password.
``timeout``   (int, optional) — HTTP request timeout in seconds (default 60).
``table``     (str, optional) — Table to query (default ``"incident"``).
``batch_size`` (int, optional) — Records per page (default 500, max 10 000).
``retry_attempts`` (int, optional) — Retry count on transient errors (default 3).
``retry_delay`` (float, optional) — Seconds between retries (default 5).

Usage
-----
    from ticketinsight.adapters import ServiceNowAdapter

    adapter = ServiceNowAdapter({
        "instance": "https://mycompany.service-now.com",
        "username": "admin",
        "password": "secret",
    })
    if adapter.connect():
        tickets = adapter.fetch_tickets(limit=200)
        adapter.close()
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

from ticketinsight.adapters.base import BaseAdapter
from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import (
    sanitize_text,
    normalize_priority,
    normalize_status,
    parse_date,
)

__all__ = ["ServiceNowAdapter"]


class ServiceNowAdapter(BaseAdapter):
    """Adapter for ServiceNow REST Table API.

    Retrieves incidents (or records from any configured table) and
    normalises them into the canonical TicketInsight schema.
    """

    # Default fields to request from the incident table
    DEFAULT_FIELDS = (
        "number,short_description,description,priority,state,category,"
        "assignment_group,assigned_to,opened_at,resolved_at,closed_at,"
        "sys_updated_on,cmdb_ci,caller_id,impact,urgency,sys_created_on,"
        "close_code,close_notes,work_notes,correlation_id,incident_state,"
        "active,hold_reason,escalation"
    )

    def __init__(self, config: dict):
        super().__init__(config)
        self.instance: str = config.get("instance", "").rstrip("/")
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.timeout: int = int(config.get("timeout", 60))
        self.table: str = config.get("table", "incident")
        self.batch_size: int = min(int(config.get("batch_size", 500)), 10000)
        self.retry_attempts: int = int(config.get("retry_attempts", 3))
        self.retry_delay: float = float(config.get("retry_delay", 5.0))
        self._connected: bool = False
        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Validate ServiceNow credentials by calling a lightweight endpoint.

        Returns
        -------
        bool
            ``True`` if credentials are valid and the instance is reachable.
        """
        self._log("info", "Connecting to ServiceNow at %s ...", self.instance)

        if not self.instance:
            self._log("error", "ServiceNow instance URL is not configured")
            return False

        if not self.username or not self.password:
            self._log("error", "ServiceNow credentials (username/password) are not configured")
            return False

        try:
            session = self._get_session()
            url = urljoin(self.instance + "/", "/api/now/table/sys_db_object")
            params = {"sysparm_limit": 1, "sysparm_fields": "name"}
            response = session.get(
                url, params=params, timeout=self.timeout
            )
            response.raise_for_status()
            self._connected = True
            self._log("info", "ServiceNow connection established successfully")
            return True

        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            if status_code == 401:
                self._log("error", "ServiceNow authentication failed (HTTP 401)")
            else:
                self._log("error", "ServiceNow HTTP error: %s — %s", status_code, exc)
            return False

        except requests.exceptions.ConnectionError as exc:
            self._log("error", "ServiceNow connection error: %s", exc)
            return False

        except requests.exceptions.Timeout as exc:
            self._log("error", "ServiceNow connection timed out: %s", exc)
            return False

        except Exception as exc:
            self._log("error", "ServiceNow connection failed: %s", exc)
            return False

    def _get_session(self) -> requests.Session:
        """Return (or create) the HTTP session with Basic Auth configured."""
        if self._session is None:
            self._session = requests.Session()
            self._session.auth = HTTPBasicAuth(self.username, self.password)
            self._session.headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
            })
        return self._session

    # ------------------------------------------------------------------
    # Ticket fetching
    # ------------------------------------------------------------------

    def fetch_tickets(
        self,
        query: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch tickets from the ServiceNow incident table.

        Parameters
        ----------
        query : str | None
            An encoded ServiceNow query string (e.g. ``"active=true"``).
            Passed as ``sysparm_query``.
        limit : int
            Maximum tickets to return.
        offset : int
            Number of records to skip.
        date_from : datetime | None
            Filter for ``opened_at >= date_from``.
        date_to : datetime | None
            Filter for ``opened_at <= date_to``.
        **kwargs
            Additional ``sysparm_*`` parameters forwarded to the API.

        Returns
        -------
        list[dict]
            List of normalised ticket dictionaries.
        """
        if not self._connected:
            self._log("warning", "Adapter not connected — attempting connect()")
            if not self.connect():
                self._log("error", "Cannot fetch tickets: not connected")
                return []

        session = self._get_session()
        all_tickets: List[Dict[str, Any]] = []
        total_fetched = 0

        # Build the query string
        query_parts = []
        if query:
            query_parts.append(query)
        if date_from:
            dt_str = date_from.strftime("javascript:gs.dateGenerate('%Y-%m-%d','%H:%M:%S')")
            query_parts.append(f"opened_at>={dt_str}")
        if date_to:
            dt_str = date_to.strftime("javascript:gs.dateGenerate('%Y-%m-%d','%H:%M:%S')")
            query_parts.append(f"opened_at<={dt_str}")

        combined_query = "^".join(query_parts) if query_parts else None

        # Determine fields
        fields = kwargs.pop("sysparm_fields", self.DEFAULT_FIELDS)

        # Paginate
        current_offset = offset
        remaining = limit

        while remaining > 0:
            page_size = min(self.batch_size, remaining)
            params: Dict[str, Any] = {
                "sysparm_query": combined_query,
                "sysparm_fields": fields,
                "sysparm_limit": page_size,
                "sysparm_offset": current_offset,
                "sysparm_display_value": "true",
                "sysparm_exclude_reference_link": "true",
            }

            # Merge any extra sysparm_ parameters from kwargs
            for key, value in kwargs.items():
                if key.startswith("sysparm_"):
                    params[key] = value

            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}

            response = self._request_with_retry(
                session, "GET", self._table_url(), params=params
            )

            if response is None:
                self._log("warning", "No response received — stopping pagination")
                break

            data = response.json()
            result = data.get("result", [])

            if not result:
                self._log("info", "No more results from ServiceNow")
                break

            for raw in result:
                normalized = self.normalize_ticket(raw)
                normalized["source_system"] = "servicenow"
                all_tickets.append(normalized)
                total_fetched += 1

            remaining -= len(result)
            current_offset += len(result)

            # If we got fewer results than requested, there are no more pages
            if len(result) < page_size:
                break

            # Check rate limiting header
            remaining_limit = response.headers.get("X-Total-Count")
            if remaining_limit is not None:
                try:
                    total_available = int(remaining_limit)
                    if current_offset >= total_available:
                        break
                except ValueError:
                    pass

        self._log(
            "info",
            "Fetched %d tickets from ServiceNow (table=%s)",
            total_fetched,
            self.table,
        )
        return all_tickets

    def fetch_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single incident by its number.

        Parameters
        ----------
        ticket_id : str
            The ServiceNow incident number (e.g. ``"INC0010001"``).

        Returns
        -------
        dict | None
            Normalised ticket, or ``None`` if not found.
        """
        if not self._connected:
            if not self.connect():
                return None

        session = self._get_session()
        params = {
            "sysparm_query": f"number={ticket_id}",
            "sysparm_limit": 1,
            "sysparm_display_value": "true",
            "sysparm_fields": self.DEFAULT_FIELDS,
        }

        response = self._request_with_retry(
            session, "GET", self._table_url(), params=params
        )
        if response is None:
            return None

        data = response.json()
        results = data.get("result", [])
        if not results:
            self._log("info", "Ticket %s not found in ServiceNow", ticket_id)
            return None

        normalized = self.normalize_ticket(results[0])
        normalized["source_system"] = "servicenow"
        return normalized

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Test the ServiceNow API endpoint and return latency.

        Returns
        -------
        dict
            ``{"status": "ok"|"error", "latency_ms": float, "message": str}``
        """
        import time as _time

        start = _time.monotonic()
        try:
            session = self._get_session()
            url = urljoin(self.instance + "/", "/api/now/table/sys_db_object")
            params = {"sysparm_limit": 1, "sysparm_fields": "name"}
            response = session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            elapsed_ms = (_time.monotonic() - start) * 1000
            return {
                "status": "ok",
                "latency_ms": round(elapsed_ms, 2),
                "message": "ServiceNow API is reachable",
            }
        except Exception as exc:
            elapsed_ms = (_time.monotonic() - start) * 1000
            return {
                "status": "error",
                "latency_ms": round(elapsed_ms, 2),
                "message": f"ServiceNow health check failed: {exc}",
            }

    # ------------------------------------------------------------------
    # ServiceNow-specific normalisation
    # ------------------------------------------------------------------

    def normalize_ticket(self, raw_ticket: dict) -> dict:
        """Apply ServiceNow-specific field mappings, then delegate to the base.

        ServiceNow-specific mappings beyond the base aliases:
            - ``number`` → ``ticket_id``
            - ``short_description`` → ``title``
            - ``cmdb_ci`` → ``affected_service``
            - ``state`` → ``status`` (with numeric→label conversion)
            - ``assigned_to`` → ``assignee`` (handles display_value objects)
            - ``caller_id`` → ``caller``
            - ``impact`` + ``urgency`` → ``priority`` (derived)
            - ``sys_updated_on`` → ``updated_at``
            - ``sys_created_on`` → ``opened_at`` (fallback)
            - ``resolution_date`` → ``resolved_at`` (fallback)
            - ``close_code`` / ``close_notes`` → merged into ``description``
        """
        if not raw_ticket or not isinstance(raw_ticket, dict):
            return {}

        # Flatten display_value objects from ServiceNow
        flattened: Dict[str, Any] = {}
        for key, value in raw_ticket.items():
            if isinstance(value, dict):
                # ServiceNow returns reference fields as {"display_value": ..., "link": ...}
                display_val = value.get("display_value", value.get("value", ""))
                if display_val is not None:
                    flattened[key] = display_val
                else:
                    flattened[key] = str(value)
            elif value is not None:
                flattened[key] = value

        # Map ServiceNow numeric state codes to status labels
        sn_state = flattened.get("state")
        if sn_state is not None:
            _SN_STATE_MAP = {
                "1": "New",
                "2": "In Progress",
                "3": "On Hold",
                "4": "Open",
                "5": "Resolved",
                "6": "Closed",
                "7": "Closed",
                "8": "Cancelled",
            }
            state_str = str(sn_state)
            if state_str in _SN_STATE_MAP:
                flattened["state"] = _SN_STATE_MAP[state_str]

        # Derive priority from impact + urgency if priority is missing
        if not flattened.get("priority") and (flattened.get("impact") or flattened.get("urgency")):
            impact = int(flattened.get("impact", 3))
            urgency = int(flattened.get("urgency", 3))
            # ServiceNow priority = (impact + urgency) / 2, rounded up
            calculated = max(1, min(4, -(- (impact + urgency) // 2)))
            flattened["priority"] = str(calculated)

        # Merge close_notes / work_notes into description if present
        description = flattened.get("description", "")
        close_notes = flattened.get("close_notes", "")
        work_notes = flattened.get("work_notes", "")
        if close_notes and close_notes not in description:
            description = f"{description}\n\nResolution Notes:\n{close_notes}"
        if work_notes and work_notes not in description:
            description = f"{description}\n\nWork Notes:\n{work_notes}"
        flattened["description"] = description

        # Map cmdb_ci to affected_service
        if flattened.get("cmdb_ci") and not flattened.get("affected_service"):
            flattened["affected_service"] = flattened["cmdb_ci"]

        # Map caller_id to caller
        if flattened.get("caller_id") and not flattened.get("caller"):
            flattened["caller"] = flattened["caller_id"]

        # Defer to the base normaliser for canonical field mapping
        normalized = super().normalize_ticket(flattened)
        return normalized

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _table_url(self) -> str:
        """Return the full REST Table API URL for the configured table."""
        return f"{self.instance}/api/now/table/{self.table}"

    def _request_with_retry(
        self,
        session: requests.Session,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[requests.Response]:
        """Execute an HTTP request with retry logic and rate-limit handling.

        Parameters
        ----------
        session : requests.Session
            Authenticated session.
        method : str
            HTTP method (``"GET"``, ``"POST"``, etc.).
        url : str
            Target URL.
        params : dict | None
            Query parameters.
        json_data : dict | None
            JSON request body.

        Returns
        -------
        requests.Response | None
            Response object, or ``None`` after all retries are exhausted.
        """
        import time as _time

        last_exc: Optional[Exception] = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = session.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    timeout=self.timeout,
                )

                # Handle rate limiting (HTTP 429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", self.retry_delay))
                    self._log(
                        "warning",
                        "ServiceNow rate limit hit (attempt %d/%d). "
                        "Retrying after %ds ...",
                        attempt,
                        self.retry_attempts,
                        retry_after,
                    )
                    _time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response is not None else "unknown"
                if status in (401, 403):
                    self._log("error", "ServiceNow auth error (HTTP %s): %s", status, exc)
                    return None
                self._log(
                    "warning",
                    "ServiceNow HTTP error (attempt %d/%d, HTTP %s): %s",
                    attempt,
                    self.retry_attempts,
                    status,
                    exc,
                )

            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "ServiceNow connection error (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            except requests.exceptions.Timeout as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "ServiceNow timeout (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "ServiceNow request error (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            # Exponential back-off before retry
            if attempt < self.retry_attempts:
                delay = self.retry_delay * (2 ** (attempt - 1))
                _time.sleep(delay)

        self._log(
            "error",
            "ServiceNow request failed after %d attempts: %s",
            self.retry_attempts,
            last_exc,
        )
        return None

    def close(self) -> None:
        """Close the HTTP session."""
        super().close()
        self._connected = False
        self._log("info", "ServiceNow adapter closed")
