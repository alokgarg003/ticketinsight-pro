"""
Jira adapter for TicketInsight Pro.

Connects to Jira Cloud or Jira Server/Data Center via the REST API v3
(``/rest/api/3/``) and retrieves issues.  Supports JQL queries,
date-range filtering, pagination, and automatic field normalisation.

Configuration keys
------------------
``server``     (str, required) — Jira base URL, e.g.
    ``https://mycompany.atlassian.net`` (Cloud) or
    ``https://jira.mycompany.com`` (Server/DC).
``username``   (str, required for Cloud) — Jira email address.
``api_token``  (str, required for Cloud) — Jira API token.
``pat``        (str, optional) — Personal Access Token (Server/DC).
``password``   (str, optional for Server) — Jira password (Server/DC only).
``timeout``    (int, optional) — HTTP request timeout in seconds (default 60).
``retry_attempts`` (int, optional) — Retry count (default 3).
``retry_delay`` (float, optional) — Seconds between retries (default 5).
``jql``        (str, optional) — Default JQL query filter.
``project``    (str, str list, optional) — Project key(s) to scope queries.

Usage
-----
    from ticketinsight.adapters import JiraAdapter

    # Jira Cloud
    adapter = JiraAdapter({
        "server": "https://mycompany.atlassian.net",
        "username": "admin@example.com",
        "api_token": "my-api-token",
    })
    adapter.connect()
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

__all__ = ["JiraAdapter"]


class JiraAdapter(BaseAdapter):
    """Adapter for Jira REST API v3.

    Supports both Jira Cloud (email + API token) and Jira Server/Data Center
    (username + password or Personal Access Token).
    """

    # Default fields to request from the Jira search API
    DEFAULT_FIELDS = (
        "key,summary,description,status,priority,issuetype,created,updated,"
        "resolutiondate,assignee,reporter,labels,components,project,comment,"
        "duedate,fixVersions,versions,environment,timetracking,aggregateprogress,"
        "worklog"
    )

    def __init__(self, config: dict):
        super().__init__(config)
        self.server: str = config.get("server", "").rstrip("/")
        self.username: str = config.get("username", "")
        self.api_token: str = config.get("api_token", "")
        self.password: str = config.get("password", "")
        self.pat: str = config.get("pat", "")
        self.timeout: int = int(config.get("timeout", 60))
        self.retry_attempts: int = int(config.get("retry_attempts", 3))
        self.retry_delay: float = float(config.get("retry_delay", 5.0))
        self.default_jql: str = config.get("jql", "")
        self.project: Optional[Any] = config.get("project")
        self.max_results: int = min(int(config.get("max_results", 100)), 100)
        self._connected: bool = False
        self._is_cloud: Optional[bool] = None
        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Validate Jira credentials by calling ``/rest/api/3/myself``.

        Returns
        -------
        bool
            ``True`` if authentication succeeds.
        """
        self._log("info", "Connecting to Jira at %s ...", self.server)

        if not self.server:
            self._log("error", "Jira server URL is not configured")
            return False

        has_cloud_creds = bool(self.username and self.api_token)
        has_server_creds = bool(self.username and self.password) or bool(self.pat)

        if not has_cloud_creds and not has_server_creds:
            self._log(
                "error",
                "Jira credentials not configured. Provide (username + api_token) "
                "for Cloud or (username + password) or (pat) for Server/DC.",
            )
            return False

        try:
            session = self._get_session()
            response = session.get(
                self._api_url("myself"), timeout=self.timeout
            )
            response.raise_for_status()

            user_data = response.json()
            display_name = user_data.get("displayName", "unknown")
            self._connected = True

            # Auto-detect Cloud vs Server
            self._is_cloud = ".atlassian.net" in self.server
            cloud_label = "Cloud" if self._is_cloud else "Server/DC"
            self._log(
                "info",
                "Jira connection established (%s) as user '%s'",
                cloud_label,
                display_name,
            )
            return True

        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            if status_code == 401:
                self._log("error", "Jira authentication failed (HTTP 401)")
            elif status_code == 403:
                self._log("error", "Jira permission denied (HTTP 403)")
            else:
                self._log("error", "Jira HTTP error: %s — %s", status_code, exc)
            return False

        except requests.exceptions.ConnectionError as exc:
            self._log("error", "Jira connection error: %s", exc)
            return False

        except requests.exceptions.Timeout as exc:
            self._log("error", "Jira connection timed out: %s", exc)
            return False

        except Exception as exc:
            self._log("error", "Jira connection failed: %s", exc)
            return False

    def _get_session(self) -> requests.Session:
        """Return (or create) the HTTP session with authentication configured."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
            })

            if self.pat:
                # Personal Access Token for Server/DC
                self._session.headers["Authorization"] = f"Bearer {self.pat}"
            elif self.api_token:
                # API token for Jira Cloud
                self._session.auth = HTTPBasicAuth(self.username, self.api_token)
            elif self.password:
                # Username + password for Server/DC
                self._session.auth = HTTPBasicAuth(self.username, self.password)

        return self._session

    def _api_url(self, path: str) -> str:
        """Return a full Jira REST API v3 URL."""
        base = self.server.rstrip("/")
        if not base.endswith("/rest/api/3"):
            base = f"{base}/rest/api/3"
        return f"{base}/{path.lstrip('/')}"

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
        """Fetch issues from Jira using the search API.

        Parameters
        ----------
        query : str | None
            A JQL query string.  If ``None``, the default JQL from config
            is used (or all issues if no default is configured).
        limit : int
            Maximum issues to return.
        offset : int
            Starting index for pagination (Jira ``startAt`` parameter).
        date_from : datetime | None
            Filter for ``updated >= date_from``.
        date_to : datetime | None
            Filter for ``updated <= date_to``.
        **kwargs
            Additional parameters.  Supported keys:
            - ``fields`` (str) — comma-separated list of Jira fields
            - ``expand`` (str) — Jira expand options
            - ``jql_override`` (str) — override any generated JQL

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

        # Build JQL query
        jql = kwargs.get("jql_override") or query or self.default_jql

        if jql:
            jql_parts = [jql]
        else:
            jql_parts = []

        # Add project filter
        if self.project and not jql:
            if isinstance(self.project, list):
                project_clause = ", ".join(f'"{p}"' for p in self.project)
                jql_parts.append(f"project in ({project_clause})")
            elif isinstance(self.project, str) and self.project:
                jql_parts.append(f'project = "{self.project}"')

        # Add date filters
        if date_from:
            date_str = date_from.strftime("%Y-%m-%d %H:%M")
            jql_parts.append(f'updated >= "{date_str}"')
        if date_to:
            date_str = date_to.strftime("%Y-%m-%d %H:%M")
            jql_parts.append(f'updated <= "{date_str}"')

        combined_jql = " AND ".join(jql_parts) if jql_parts else None

        # Fields
        fields = kwargs.get("fields", self.DEFAULT_FIELDS)
        expand = kwargs.get("expand", "")

        # Paginate using startAt / maxResults
        current_start = offset
        remaining = limit

        while remaining > 0:
            page_size = min(self.max_results, remaining)

            payload: Dict[str, Any] = {
                "jql": combined_jql,
                "startAt": current_start,
                "maxResults": page_size,
                "fields": fields.split(",") if isinstance(fields, str) else fields,
            }
            if expand:
                payload["expand"] = expand.split(",") if isinstance(expand, str) else expand

            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}

            response = self._request_with_retry(
                session, "POST", self._api_url("search"), json_data=payload
            )

            if response is None:
                self._log("warning", "No response received — stopping pagination")
                break

            data = response.json()
            issues = data.get("issues", [])

            if not issues:
                self._log("info", "No more results from Jira")
                break

            for issue in issues:
                normalized = self.normalize_ticket(issue)
                normalized["source_system"] = "jira"
                all_tickets.append(normalized)

            remaining -= len(issues)
            current_start += len(issues)

            # Check if there are more pages
            total = data.get("total", 0)
            if current_start >= total:
                break

        self._log("info", "Fetched %d tickets from Jira", len(all_tickets))
        return all_tickets

    def fetch_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single issue by its key (e.g. ``"PROJ-123"``).

        Parameters
        ----------
        ticket_id : str
            The Jira issue key.

        Returns
        -------
        dict | None
            Normalised ticket, or ``None`` if not found.
        """
        if not self._connected:
            if not self.connect():
                return None

        session = self._get_session()
        url = self._api_url(f"issue/{ticket_id}")
        params = {"fields": self.DEFAULT_FIELDS}

        response = self._request_with_retry(session, "GET", url, params=params)
        if response is None:
            return None

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            if response.status_code == 404:
                self._log("info", "Jira issue %s not found", ticket_id)
                return None
            raise

        normalized = self.normalize_ticket(response.json())
        normalized["source_system"] = "jira"
        return normalized

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Test the Jira serverInfo endpoint and return latency.

        Returns
        -------
        dict
            ``{"status": "ok"|"error", "latency_ms": float, "message": str}``
        """
        import time as _time

        start = _time.monotonic()
        try:
            session = self._get_session()
            url = self._api_url("serverInfo")
            response = session.get(url, timeout=self.timeout)
            response.raise_for_status()
            elapsed_ms = (_time.monotonic() - start) * 1000

            server_info = response.json()
            version = server_info.get("version", "unknown")
            title = server_info.get("serverTitle", "unknown")

            return {
                "status": "ok",
                "latency_ms": round(elapsed_ms, 2),
                "message": f"Jira {title} (v{version}) is reachable",
            }
        except Exception as exc:
            elapsed_ms = (_time.monotonic() - start) * 1000
            return {
                "status": "error",
                "latency_ms": round(elapsed_ms, 2),
                "message": f"Jira health check failed: {exc}",
            }

    # ------------------------------------------------------------------
    # Jira-specific normalisation
    # ------------------------------------------------------------------

    def normalize_ticket(self, raw_ticket: dict) -> dict:
        """Apply Jira-specific field mappings and delegate to the base normaliser.

        Jira-specific mappings:
            - ``key`` → ``ticket_id``
            - ``fields.summary`` → ``title``
            - ``fields.description`` → ``description`` (strips Atlassian Document
              Format markup)
            - ``fields.issuetype.name`` → ``category``
            - ``fields.priority.name`` → ``priority``
            - ``fields.status.name`` → ``status``
            - ``fields.assignee.displayName`` → ``assignee``
            - ``fields.reporter.displayName`` → ``caller``
            - ``fields.created`` → ``opened_at``
            - ``fields.resolutiondate`` → ``resolved_at``
            - ``fields.updated`` → ``updated_at``
            - ``fields.labels`` → ``tags`` (comma-separated)
            - ``fields.components`` → ``category`` (supplemental)
        """
        if not raw_ticket or not isinstance(raw_ticket, dict):
            return {}

        # Flatten the nested "fields" structure
        flattened: Dict[str, Any] = {}
        fields = raw_ticket.get("fields", {})

        # Top-level fields
        flattened["key"] = raw_ticket.get("key", "")
        flattened["id"] = raw_ticket.get("id", "")

        # Map Jira fields to flat keys with display-value extraction
        if isinstance(fields, dict):
            # Simple fields
            for simple_key in ("summary", "description", "environment"):
                val = fields.get(simple_key)
                if val is not None:
                    flattened[simple_key] = val

            # Date fields
            for date_key, target_key in [
                ("created", "created"),
                ("updated", "updated"),
                ("resolutiondate", "resolutiondate"),
                ("duedate", "duedate"),
            ]:
                val = fields.get(date_key)
                if val is not None:
                    flattened[target_key] = val

            # Nested display-value fields
            for nested_key, target_key in [
                ("priority", "priority"),
                ("status", "status"),
                ("issuetype", "issuetype"),
                ("assignee", "assignee"),
                ("reporter", "reporter"),
                ("project", "project"),
            ]:
                nested_val = fields.get(nested_key)
                if isinstance(nested_val, dict):
                    display_value = nested_val.get("displayName") or nested_val.get("name", "")
                    flattened[target_key] = display_value
                    # Also store the raw name for priority
                    if nested_key == "priority":
                        flattened["priority_raw"] = nested_val.get("name", display_value)
                    elif nested_key == "status":
                        flattened["status_raw"] = nested_val.get("name", display_value)
                    elif nested_key == "issuetype":
                        flattened["issuetype_name"] = nested_val.get("name", "")
                elif nested_val is not None:
                    flattened[target_key] = str(nested_val)

            # Labels
            labels = fields.get("labels", [])
            if isinstance(labels, list):
                flattened["labels"] = ", ".join(labels)

            # Components
            components = fields.get("components", [])
            if isinstance(components, list):
                comp_names = []
                for comp in components:
                    if isinstance(comp, dict):
                        name = comp.get("name", "")
                        if name:
                            comp_names.append(name)
                    elif isinstance(comp, str):
                        comp_names.append(comp)
                if comp_names:
                    flattened["components"] = ", ".join(comp_names)

            # Comment count for enrichment
            comment_data = fields.get("comment", {})
            if isinstance(comment_data, dict):
                comments = comment_data.get("comments", [])
                if isinstance(comments, list):
                    flattened["comment_count"] = len(comments)

        # Strip Atlassian Document Format from description if it's a dict
        desc = flattened.get("description")
        if isinstance(desc, dict):
            flattened["description"] = self._extract_text_from_adf(desc)

        # Map Jira-specific keys to canonical aliases that the base normaliser expects
        flattened["ticket_id"] = flattened.get("key", "")
        flattened["title"] = flattened.get("summary", "")
        flattened["assignee"] = flattened.get("assignee", "")
        flattened["caller"] = flattened.get("reporter", "")
        flattened["category"] = flattened.get("issuetype_name", "") or flattened.get("issuetype", "")
        flattened["priority"] = flattened.get("priority_raw", "") or flattened.get("priority", "")
        flattened["status"] = flattened.get("status_raw", "") or flattened.get("status", "")
        flattened["opened_at"] = flattened.get("created", "")
        flattened["resolved_at"] = flattened.get("resolutiondate", "")
        flattened["updated_at"] = flattened.get("updated", "")

        # Add components as supplemental category info
        components_val = flattened.get("components", "")
        if components_val and not flattened.get("category"):
            flattened["category"] = components_val

        # Add labels as tags in the raw data
        tags = flattened.get("labels", "")
        if tags:
            flattened["tags"] = tags

        # Defer to base normaliser
        normalized = super().normalize_ticket(flattened)
        return normalized

    @staticmethod
    def _extract_text_from_adf(adf_node: dict, _top_level: bool = True) -> str:
        """Recursively extract plain text from an Atlassian Document Format tree.

        ADF uses a node structure where text content lives in ``text`` keys
        inside leaf nodes.

        Parameters
        ----------
        adf_node : dict
            An ADF document, block, or inline node.
        _top_level : bool
            Internal flag — ``True`` only for the initial call.  Controls
            whether leading/trailing whitespace is stripped.

        Returns
        -------
        str
            Concatenated plain-text content.
        """
        if not adf_node or not isinstance(adf_node, dict):
            return ""

        parts: List[str] = []

        # Check if this node has direct text
        if "text" in adf_node:
            text = str(adf_node["text"])
            if text:
                parts.append(text)

        # Recurse into content children
        content = adf_node.get("content")
        if isinstance(content, list):
            for child in content:
                if isinstance(child, dict):
                    child_text = JiraAdapter._extract_text_from_adf(
                        child, _top_level=False
                    )
                    if child_text:
                        # Add space between sibling blocks, but not within text runs
                        if child.get("type") in (
                            "paragraph", "heading", "bulletList",
                            "orderedList", "listItem",
                        ):
                            parts.append(" " + child_text.strip())
                        else:
                            parts.append(child_text)
                elif isinstance(child, str):
                    parts.append(child)

        result = "".join(parts)

        # Only strip at the outermost level
        if _top_level:
            result = result.strip()
            # Collapse multiple spaces into single space
            import re
            result = re.sub(r"  +", " ", result)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request_with_retry(
        self,
        session: requests.Session,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[requests.Response]:
        """Execute an HTTP request with retry logic and rate-limit handling.

        Returns
        -------
        requests.Response | None
            Response, or ``None`` after all retries exhausted.
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
                    retry_after = int(
                        response.headers.get("Retry-After", self.retry_delay)
                    )
                    self._log(
                        "warning",
                        "Jira rate limit hit (attempt %d/%d). "
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
                    self._log("error", "Jira auth error (HTTP %s): %s", status, exc)
                    return None
                self._log(
                    "warning",
                    "Jira HTTP error (attempt %d/%d, HTTP %s): %s",
                    attempt,
                    self.retry_attempts,
                    status,
                    exc,
                )

            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "Jira connection error (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            except requests.exceptions.Timeout as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "Jira timeout (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "Jira request error (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            if attempt < self.retry_attempts:
                delay = self.retry_delay * (2 ** (attempt - 1))
                _time.sleep(delay)

        self._log(
            "error",
            "Jira request failed after %d attempts: %s",
            self.retry_attempts,
            last_exc,
        )
        return None

    def close(self) -> None:
        """Close the HTTP session."""
        super().close()
        self._connected = False
        self._log("info", "Jira adapter closed")
