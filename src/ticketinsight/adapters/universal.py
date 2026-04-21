"""
Universal / JSON adapter for TicketInsight Pro.

A fully configurable adapter for generic REST APIs and JSON data sources.
All behaviour — endpoint URLs, authentication, field mapping, pagination,
and response structure — is controlled through the configuration dictionary.

Configuration keys
------------------
``base_url``         (str, required) — Base URL of the API.
``endpoint``         (str, required) — Path or full URL for ticket retrieval.
``auth_type``        (str, optional) — One of ``"none"``, ``"basic"``,
    ``"bearer"``, ``"api_key_header"``, ``"api_key_query"`` (default ``"none"``).
``auth_credentials`` (dict, optional) — Auth parameters:
    - ``username`` / ``password`` (for ``"basic"``)
    - ``token`` (for ``"bearer"``)
    - ``header_name`` / ``key`` (for ``"api_key_header"``)
    - ``param_name`` / ``key`` (for ``"api_key_query"``)
``field_mapping``    (dict, optional) — Maps canonical field names to JSON
    dot-path expressions, e.g.
    ``{"ticket_id": "id", "title": "attributes.subject"}``.
``response_items_path``  (str, optional) — Dot-path to the items array in
    the response (default ``"result"``).
``response_total_path``  (str, optional) — Dot-path to the total count in
    the response (default ``"total"``).
``pagination_type``  (str, optional) — ``"offset"``, ``"page"``, or
    ``"cursor"`` (default ``"offset"``).
``pagination_params`` (dict, optional) — Pagination parameter names:
    - ``limit_key`` (default ``"limit"``)
    - ``offset_key`` (default ``"offset"``)
    - ``page_key`` (default ``"page"``)
    - ``per_page_key`` (default ``"per_page"``)
    - ``cursor_key`` (default ``"cursor"``)
``default_params``   (dict, optional) — Extra query params sent with every request.
``headers``          (dict, optional) — Extra HTTP headers.
``timeout``          (int, optional) — Request timeout in seconds (default 60).
``retry_attempts``   (int, optional) — Retry count (default 3).
``retry_delay``      (float, optional) — Seconds between retries (default 5).
``date_fields``      (list[str], optional) — Field names that contain dates.
``date_format``      (str, optional) — Expected date format string.

Usage
-----
    from ticketinsight.adapters import UniversalAdapter

    adapter = UniversalAdapter({
        "base_url": "https://api.example.com/v1",
        "endpoint": "/tickets",
        "auth_type": "bearer",
        "auth_credentials": {"token": "my-token"},
        "field_mapping": {
            "ticket_id": "id",
            "title": "subject",
            "description": "body",
        },
        "response_items_path": "data.items",
        "pagination_type": "page",
    })
    adapter.connect()
    tickets = adapter.fetch_tickets(limit=100)
    adapter.close()
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlencode

import requests
from requests.auth import HTTPBasicAuth

from ticketinsight.adapters.base import BaseAdapter
from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import parse_date

__all__ = ["UniversalAdapter"]


class UniversalAdapter(BaseAdapter):
    """Configurable adapter for generic REST APIs and JSON data.

    Every aspect of the API interaction is driven by the configuration
    dictionary, making this adapter suitable for any JSON-returning API.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url: str = config.get("base_url", "").rstrip("/")
        self.endpoint: str = config.get("endpoint", "")
        self.auth_type: str = config.get("auth_type", "none")
        self.auth_credentials: Dict[str, Any] = config.get("auth_credentials", {})
        self.field_mapping: Dict[str, str] = config.get("field_mapping", {})
        self.response_items_path: str = config.get("response_items_path", "result")
        self.response_total_path: str = config.get("response_total_path", "total")
        self.pagination_type: str = config.get("pagination_type", "offset")
        self.pagination_params: Dict[str, str] = config.get("pagination_params", {})
        self.default_params: Dict[str, Any] = config.get("default_params", {})
        self.extra_headers: Dict[str, str] = config.get("headers", {})
        self.timeout: int = int(config.get("timeout", 60))
        self.retry_attempts: int = int(config.get("retry_attempts", 3))
        self.retry_delay: float = float(config.get("retry_delay", 5.0))
        self.date_fields: List[str] = config.get("date_fields", [])
        self.date_format: Optional[str] = config.get("date_format")
        self.batch_size: int = int(config.get("batch_size", 100))
        self._connected: bool = False
        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Validate that the API base URL is reachable.

        Performs a HEAD request to the base URL.

        Returns
        -------
        bool
            ``True`` if the URL is reachable.
        """
        self._log("info", "Connecting to universal API at %s ...", self.base_url)

        if not self.base_url:
            self._log("error", "Base URL is not configured")
            return False

        try:
            session = self._get_session()
            response = session.head(self.base_url, timeout=self.timeout)

            # Accept any 2xx, 3xx, or even 405 (method not allowed on HEAD)
            if response.status_code < 500:
                self._connected = True
                self._log("info", "Universal API connection established (HTTP %d)", response.status_code)
                return True
            else:
                self._log("error", "API returned server error: HTTP %d", response.status_code)
                return False

        except requests.exceptions.ConnectionError as exc:
            self._log("error", "API connection error: %s", exc)
            return False
        except requests.exceptions.Timeout as exc:
            self._log("error", "API connection timed out: %s", exc)
            return False
        except Exception as exc:
            self._log("error", "API connection failed: %s", exc)
            return False

    def _get_session(self) -> requests.Session:
        """Create and configure the HTTP session with authentication."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
            })

            # Apply extra headers
            for key, value in self.extra_headers.items():
                self._session.headers[key] = value

            # Configure authentication
            self._configure_auth(self._session)

        return self._session

    def _configure_auth(self, session: requests.Session) -> None:
        """Configure authentication on the session based on ``auth_type``.

        Parameters
        ----------
        session : requests.Session
            HTTP session to configure.
        """
        auth_type = self.auth_type.lower()
        creds = self.auth_credentials

        if auth_type == "basic":
            username = creds.get("username", "")
            password = creds.get("password", "")
            session.auth = HTTPBasicAuth(username, password)

        elif auth_type == "bearer":
            token = creds.get("token", "")
            session.headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "api_key_header":
            header_name = creds.get("header_name", "X-API-Key")
            key = creds.get("key", "")
            session.headers[header_name] = key

        elif auth_type == "api_key_query":
            # Query-param auth is handled in _build_url
            pass

        elif auth_type != "none":
            self._log("warning", "Unknown auth_type '%s' — using no auth", auth_type)

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
        """Fetch tickets from the configured API endpoint.

        Parameters
        ----------
        query : str | None
            Appended as a ``q`` or ``search`` query parameter.
        limit : int
            Maximum tickets to return.
        offset : int
            Number of records to skip (for offset-based pagination).
        date_from : datetime | None
            If ``date_fields`` is configured, filters where the first date
            field is >= date_from.
        date_to : datetime | None
            If ``date_fields`` is configured, filters where the first date
            field is <= date_to.
        **kwargs
            Extra query parameters merged into the request.

        Returns
        -------
        list[dict]
            List of normalised ticket dictionaries.
        """
        if not self._connected:
            if not self.connect():
                self._log("error", "Cannot fetch tickets: not connected")
                return []

        session = self._get_session()
        all_tickets: List[Dict[str, Any]] = []
        total_fetched = 0
        page_size = min(self.batch_size, limit)

        # Build base query parameters
        params: Dict[str, Any] = {}
        params.update(self.default_params)

        # Add search query
        if query:
            # Try common query parameter names
            for qp in ("q", "search", "query", "filter", "searchQuery"):
                params[qp] = query
                break

        # Merge kwargs into params
        params.update(kwargs)

        # Date filtering via params (best-effort: use first configured date field)
        if self.date_fields and (date_from or date_to):
            date_field = self.date_fields[0]
            if date_from:
                params[f"{date_field}_from"] = date_from.strftime("%Y-%m-%d")
                params[f"{date_field}[gte]"] = date_from.isoformat()
            if date_to:
                params[f"{date_field}_to"] = date_to.strftime("%Y-%m-%d")
                params[f"{date_field}[lte]"] = date_to.isoformat()

        # Pagination state
        current_offset = offset
        current_page = 1
        cursor: Optional[str] = kwargs.get("cursor")

        while total_fetched < limit:
            # Configure pagination parameters
            page_params = dict(params)
            self._apply_pagination(
                page_params,
                page_size=page_size,
                offset=current_offset,
                page=current_page,
                cursor=cursor,
            )

            # Build URL
            url = self._build_url(page_params)

            response = self._request_with_retry(session, "GET", url)

            if response is None:
                self._log("warning", "No response received — stopping pagination")
                break

            try:
                data = response.json()
            except ValueError as exc:
                self._log("error", "Failed to parse JSON response: %s", exc)
                break

            # Extract items array using configured dot-path
            items = self._extract_path(data, self.response_items_path)

            if not items or not isinstance(items, list):
                self._log("info", "No items found in response at path '%s'", self.response_items_path)
                break

            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized = self.normalize_ticket(item)
                normalized["source_system"] = "universal"
                all_tickets.append(normalized)
                total_fetched += 1

                if total_fetched >= limit:
                    break

            # Extract total count
            total_count = self._extract_path(data, self.response_total_path)
            if isinstance(total_count, (int, float)):
                if total_fetched + current_offset >= int(total_count):
                    break

            # If fewer items than page_size, assume no more pages
            if len(items) < page_size:
                break

            # Advance pagination state
            if self.pagination_type == "offset":
                current_offset += len(items)
            elif self.pagination_type == "page":
                current_page += 1
            elif self.pagination_type == "cursor":
                # Try to extract next cursor from common response patterns
                cursor = self._extract_next_cursor(data)
                if cursor is None:
                    break

        self._log("info", "Fetched %d tickets from universal API", total_fetched)
        return all_tickets

    def fetch_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single ticket by ID.

        Attempts to call ``{endpoint}/{ticket_id}``.

        Parameters
        ----------
        ticket_id : str
            External ticket identifier.

        Returns
        -------
        dict | None
        """
        if not self._connected:
            if not self.connect():
                return None

        session = self._get_session()
        url = self._resolve_endpoint(f"{self.endpoint}/{ticket_id}")

        response = self._request_with_retry(session, "GET", url)
        if response is None:
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        normalized = self.normalize_ticket(data)
        normalized["source_system"] = "universal"
        return normalized

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Test the API base URL and return latency.

        Returns
        -------
        dict
            ``{"status": "ok"|"error", "latency_ms": float, "message": str}``
        """
        import time as _time

        start = _time.monotonic()
        try:
            session = self._get_session()
            response = session.head(self.base_url, timeout=self.timeout)
            elapsed_ms = (_time.monotonic() - start) * 1000

            if response.status_code < 500:
                return {
                    "status": "ok",
                    "latency_ms": round(elapsed_ms, 2),
                    "message": f"API is reachable (HTTP {response.status_code})",
                }
            else:
                return {
                    "status": "error",
                    "latency_ms": round(elapsed_ms, 2),
                    "message": f"API returned HTTP {response.status_code}",
                }
        except Exception as exc:
            elapsed_ms = (_time.monotonic() - start) * 1000
            return {
                "status": "error",
                "latency_ms": round(elapsed_ms, 2),
                "message": f"Health check failed: {exc}",
            }

    # ------------------------------------------------------------------
    # Configurable normalisation
    # ------------------------------------------------------------------

    def normalize_ticket(self, raw_ticket: dict) -> dict:
        """Apply the configured field_mapping to extract canonical fields.

        If ``field_mapping`` is configured, each canonical field is extracted
        from the raw ticket using the dot-path expression specified in the
        mapping.  Otherwise, delegates to the base normaliser.
        """
        if not raw_ticket or not isinstance(raw_ticket, dict):
            return {}

        if self.field_mapping:
            flattened: Dict[str, Any] = {}
            for canonical_field, path_expr in self.field_mapping.items():
                value = self._extract_path(raw_ticket, path_expr)
                if value is not None:
                    flattened[canonical_field] = value

            normalized = super().normalize_ticket(flattened)
        else:
            normalized = super().normalize_ticket(raw_ticket)

        # Parse date fields with configured format
        if self.date_format:
            for field in self.date_fields:
                if field in normalized:
                    val = normalized[field]
                    if val is not None and not isinstance(val, datetime):
                        parsed = parse_date(str(val), formats=[self.date_format])
                        if parsed is not None:
                            normalized[field] = parsed

        return normalized

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_endpoint(self, endpoint: Optional[str] = None) -> str:
        """Build a full URL from base_url and endpoint path.

        Parameters
        ----------
        endpoint : str | None
            Endpoint path. Uses ``self.endpoint`` if ``None``.

        Returns
        -------
        str
        """
        ep = endpoint or self.endpoint
        if not ep:
            return self.base_url
        if ep.startswith("http://") or ep.startswith("https://"):
            return ep
        return urljoin(self.base_url + "/", ep.lstrip("/"))

    def _build_url(self, params: Dict[str, Any]) -> str:
        """Build the full URL with query parameters.

        Parameters
        ----------
        params : dict
            Query parameters.

        Returns
        -------
        str
        """
        url = self._resolve_endpoint()

        # Add API key as query parameter if configured
        if self.auth_type.lower() == "api_key_query":
            param_name = self.auth_credentials.get("param_name", "api_key")
            params[param_name] = self.auth_credentials.get("key", "")

        # Filter out None values
        clean_params = {k: v for k, v in params.items() if v is not None}

        if clean_params:
            return f"{url}?{urlencode(clean_params)}"
        return url

    def _apply_pagination(
        self,
        params: Dict[str, Any],
        page_size: int,
        offset: int = 0,
        page: int = 1,
        cursor: Optional[str] = None,
    ) -> None:
        """Add pagination parameters to the query.

        Parameters
        ----------
        params : dict
            Query parameters to modify in-place.
        page_size : int
            Number of results per page.
        offset : int
            Offset for offset-based pagination.
        page : int
            Page number for page-based pagination.
        cursor : str | None
            Cursor for cursor-based pagination.
        """
        pp = self.pagination_params
        pag_type = self.pagination_type.lower()

        if pag_type == "offset":
            params[pp.get("limit_key", "limit")] = page_size
            params[pp.get("offset_key", "offset")] = offset

        elif pag_type == "page":
            params[pp.get("per_page_key", "per_page")] = page_size
            params[pp.get("page_key", "page")] = page

        elif pag_type == "cursor":
            params[pp.get("limit_key", "limit")] = page_size
            if cursor:
                params[pp.get("cursor_key", "cursor")] = cursor

        else:
            # Default: offset-based
            params["limit"] = page_size
            params["offset"] = offset

    def _extract_path(self, data: Any, path: str) -> Any:
        """Extract a value from a nested dict/list using a dot-separated path.

        Supports:
            - ``"key"`` — top-level key
            - ``"key.subkey"`` — nested dict
            - ``"key.0"`` — list index access
            - ``"key.0.name"`` — combined

        Parameters
        ----------
        data : Any
            The data structure to traverse.
        path : str
            Dot-separated path expression.

        Returns
        -------
        Any | None
            The value at the path, or ``None`` if not found.
        """
        if not path or not isinstance(path, str):
            return data

        parts = path.split(".")
        current = data

        for part in parts:
            if current is None:
                return None

            if isinstance(current, dict):
                # Case-insensitive key lookup
                found = False
                part_lower = part.lower()
                for key, value in current.items():
                    if str(key).lower() == part_lower:
                        current = value
                        found = True
                        break
                if not found:
                    return None
            elif isinstance(current, (list, tuple)):
                try:
                    index = int(part)
                    current = current[index]
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return current

    def _extract_next_cursor(self, data: Any) -> Optional[str]:
        """Try to extract the next cursor/continuation token from common patterns.

        Checks: ``next_cursor``, ``next_page_token``, ``next``,
        ``pagination.next_cursor``, ``links.next``, ``_links.next.href``.

        Parameters
        ----------
        data : Any
            The API response data.

        Returns
        -------
        str | None
            The next cursor value, or ``None``.
        """
        if not isinstance(data, dict):
            return None

        # Direct paths
        for path in (
            "next_cursor",
            "next_page_token",
            "next",
            "cursor",
            "continuation_token",
            "pagination.next_cursor",
            "pagination.next",
            "pagination.cursor",
        ):
            val = self._extract_path(data, path)
            if val and isinstance(val, str):
                return val

        # HATEOAS-style links
        links = self._extract_path(data, "links")
        if isinstance(links, dict):
            next_link = links.get("next")
            if isinstance(next_link, str):
                return next_link
            if isinstance(next_link, dict):
                href = next_link.get("href")
                if href:
                    return href

        _links = self._extract_path(data, "_links")
        if isinstance(_links, dict):
            next_link = _links.get("next")
            if isinstance(next_link, dict):
                href = next_link.get("href")
                if href:
                    return href

        return None

    def _request_with_retry(
        self,
        session: requests.Session,
        method: str,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[requests.Response]:
        """Execute an HTTP request with retry logic.

        Returns
        -------
        requests.Response | None
        """
        import time as _time

        last_exc: Optional[Exception] = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = session.request(
                    method, url, json=json_data, timeout=self.timeout
                )

                if response.status_code == 429:
                    retry_after = int(
                        response.headers.get("Retry-After", self.retry_delay)
                    )
                    self._log(
                        "warning",
                        "Rate limited (attempt %d/%d). Retrying after %ds ...",
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
                    self._log("error", "Auth error (HTTP %s): %s", status, exc)
                    return None
                self._log(
                    "warning",
                    "HTTP error (attempt %d/%d, HTTP %s): %s",
                    attempt,
                    self.retry_attempts,
                    status,
                    exc,
                )

            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "Connection error (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            except requests.exceptions.Timeout as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "Timeout (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                self._log(
                    "warning",
                    "Request error (attempt %d/%d): %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )

            if attempt < self.retry_attempts:
                delay = self.retry_delay * (2 ** (attempt - 1))
                _time.sleep(delay)

        self._log(
            "error",
            "Request failed after %d attempts: %s",
            self.retry_attempts,
            last_exc,
        )
        return None

    def close(self) -> None:
        """Close the HTTP session."""
        super().close()
        self._connected = False
        self._log("info", "Universal adapter closed")
