# Adapter Development Guide

> Step-by-step guide for building custom data source adapters for TicketInsight Pro.

## Table of Contents

- [Overview](#overview)
- [Adapter Architecture](#adapter-architecture)
- [BaseAdapter Protocol](#baseadapter-protocol)
- [Building Your First Adapter](#building-your-first-adapter)
- [Advanced Topics](#advanced-topics)
- [Testing Adapters](#testing-adapters)
- [Registering Custom Adapters](#registering-custom-adapters)
- [Reference: ServiceNow Adapter](#reference-servicenow-adapter)
- [Reference: Jira Adapter](#reference-jira-adapter)
- [Reference: CSV Adapter](#reference-csv-adapter)
- [Reference: REST Adapter](#reference-rest-adapter)
- [Common Patterns](#common-patterns)
- [Troubleshooting](#troubleshooting)

---

## Overview

Adapters are the bridge between TicketInsight Pro and external ticketing systems.
Each adapter is responsible for:

1. **Connecting** to the external system (authentication, session management)
2. **Fetching** ticket data (API calls, file reading, webhook handling)
3. **Normalizing** data into the unified `TicketData` format
4. **Handling pagination** for large result sets
5. **Supporting incremental sync** via watermark tracking
6. **Reporting health** and sync status

### Built-in Adapters

| Adapter | Source | Auth Methods | Sync Mode |
|---------|--------|-------------|-----------|
| ServiceNow | ServiceNow CMDB | Basic, OAuth2 | Polling, Incremental |
| Jira | Jira Cloud/Server | API Token, Basic | Polling, Incremental |
| CSV | Local files | N/A | File watching |
| REST | Any REST API | Bearer, Basic, API Key | Polling, Incremental, Push |

---

## Adapter Architecture

### Adapter Lifecycle

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Configure   │────▶│  Instantiate  │────▶│  Connect     │────▶│  Health Check│
│  (YAML)      │     │  (Python)     │     │  (Auth)      │     │  (Test)      │
└─────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                       │
                                                                       ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Disconnect  │◀────│  Process     │◀────│  Normalize   │◀────│  Fetch       │
│  (Cleanup)   │     │  (Pipeline)  │     │  (Transform) │     │  (API Call)  │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Data Flow

```
[External System]
       │
       ▼
[Adapter.fetch_tickets()]     ← Raw API response (JSON/XML/CSV)
       │
       ▼
[Adapter.normalize()]         ← Convert to TicketData format
       │
       ▼
[Pipeline.process()]          ← Run through NLP/ML pipeline
       │
       ▼
[Ticket Store]                ← Persist to database
       │
       ▼
[Analysis Results]            ← NLP/ML results available
```

### Adapter Plugin Discovery

TicketInsight Pro discovers adapters through a plugin registry:

```python
# Adapters are auto-registered when their module is imported
ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {}

def register_adapter(name: str):
    """Decorator to register an adapter class."""
    def decorator(cls):
        ADAPTER_REGISTRY[name] = cls
        return cls
    return decorator

# Usage
@register_adapter("my_custom")
class MyCustomAdapter(BaseAdapter):
    ...
```

---

## BaseAdapter Protocol

All adapters must implement the `BaseAdapter` protocol. This is defined in
`src/ticketinsight/adapters/base.py`.

```python
from typing import Protocol, Iterator, Optional, AsyncIterator
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class SyncMode(Enum):
    """Supported synchronization modes."""
    POLLING = "polling"
    INCREMENTAL = "incremental"
    PUSH = "push"
    FULL = "full"


class AdapterHealthStatus(Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class CommentData:
    """Normalized comment/thread data."""
    comment_id: str
    author: str
    body: str
    source_created_at: Optional[datetime] = None
    is_internal: bool = False
    attachments: list[dict] = field(default_factory=list)


@dataclass
class TicketData:
    """Normalized ticket data structure.

    This is the universal format that all adapters must produce.
    The processing pipeline consumes this format exclusively.
    """
    ticket_id: str
    title: str
    description: str
    status: str
    priority: str
    source_system: str
    source_adapter: str

    # Optional fields
    category: Optional[str] = None
    subcategory: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    reporter: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_group: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    custom_fields: dict = field(default_factory=dict)
    comments: list[CommentData] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """Result of an adapter health check."""
    status: AdapterHealthStatus
    response_time_ms: Optional[float] = None
    details: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class SyncWatermark:
    """Tracks the last sync position for incremental updates."""
    adapter_name: str
    last_sync_at: datetime
    last_record_id: Optional[str] = None
    last_record_timestamp: Optional[datetime] = None
    total_synced: int = 0


class BaseAdapter(Protocol):
    """Protocol that all ticket adapters must implement.

    This protocol defines the contract for connecting to external
    ticketing systems, fetching data, and normalizing it into the
    TicketData format.
    """

    # ─── Properties ────────────────────────────────────────────

    @property
    def name(self) -> str:
        """Unique identifier for this adapter instance.

        Must match the key used in the configuration file.
        Example: 'servicenow', 'jira', 'my_custom_system'
        """
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for display purposes.
        Example: 'ServiceNow', 'Jira Cloud'
        """
        ...

    @property
    def supported_sync_modes(self) -> list[SyncMode]:
        """List of sync modes this adapter supports."""
        ...

    # ─── Connection Management ────────────────────────────────

    async def connect(self) -> None:
        """Establish a connection to the external system.

        Implement authentication, session creation, and any
        initial setup required before fetching data.

        Raises:
            AdapterConnectionError: If connection cannot be established.
        """
        ...

    async def disconnect(self) -> None:
        """Close the connection and release resources.

        Clean up sessions, HTTP clients, file handles, etc.
        """
        ...

    # ─── Health Check ─────────────────────────────────────────

    async def test_connection(self) -> HealthCheckResult:
        """Verify that the adapter can reach the external system.

        Should attempt a lightweight operation (e.g., API ping,
        file existence check) and report response time.

        Returns:
            HealthCheckResult with status and optional details.
        """
        ...

    # ─── Data Fetching ────────────────────────────────────────

    async def fetch_tickets(
        self,
        since: Optional[datetime] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> AsyncIterator[TicketData]:
        """Fetch tickets from the external system.

        Args:
            since: Only fetch tickets modified after this timestamp.
                Used for incremental sync.
            limit: Maximum number of tickets to return.
            offset: Number of records to skip (for offset pagination).

        Yields:
            Normalized TicketData objects.

        Raises:
            AdapterFetchError: If fetching fails after retries.
        """
        yield  # type: ignore[misc]

    async def fetch_ticket(self, ticket_id: str) -> TicketData:
        """Fetch a single ticket by its external ID.

        Args:
            ticket_id: The external ticket ID.

        Returns:
            Normalized TicketData for the requested ticket.

        Raises:
            TicketNotFoundError: If the ticket does not exist.
        """
        ...

    async def fetch_comments(
        self, ticket_id: str
    ) -> list[CommentData]:
        """Fetch all comments for a specific ticket.

        Args:
            ticket_id: The external ticket ID.

        Returns:
            List of normalized CommentData objects.
        """
        ...

    # ─── Sync Support ─────────────────────────────────────────

    async def get_watermark(self) -> Optional[SyncWatermark]:
        """Get the current sync watermark position.

        Returns:
            The last sync position, or None if never synced.
        """
        ...

    async def update_watermark(
        self,
        watermark: SyncWatermark
    ) -> None:
        """Update the sync watermark after a successful sync.

        Args:
            watermark: The new watermark position.
        """
        ...

    # ─── Webhook Support (Optional) ───────────────────────────

    def verify_webhook(
        self, payload: dict, signature: Optional[str] = None
    ) -> bool:
        """Verify the authenticity of an incoming webhook payload.

        Args:
            payload: The raw webhook payload.
            signature: Optional signature header for verification.

        Returns:
            True if the webhook is authentic.
        """
        return True

    def parse_webhook(self, payload: dict) -> TicketData:
        """Parse a webhook payload into a TicketData object.

        Args:
            payload: The raw webhook payload.

        Returns:
            Normalized TicketData.
        """
        ...
```

---

## Building Your First Adapter

Let's build a complete adapter for a hypothetical ticketing system called
"BugTracker" that has a REST API.

### Step 1: Define the Adapter Class

```python
"""Adapter for BugTracker ticketing system."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Optional, AsyncIterator

import httpx

from ticketinsight.adapters.base import (
    BaseAdapter,
    TicketData,
    CommentData,
    HealthCheckResult,
    SyncWatermark,
    SyncMode,
    AdapterHealthStatus,
)
from ticketinsight.utils.exceptions import AdapterError

logger = logging.getLogger(__name__)


class BugTrackerAdapter:
    """Adapter for the BugTracker REST API.

    Supports:
    - Incremental sync via last_modified timestamp
    - Offset-based pagination
    - Webhook push notifications
    - API key authentication

    Configuration example:
        adapters:
            bugtracker:
                type: bugtracker
                base_url: "https://bugtracker.company.com/api/v2"
                auth:
                    api_key: "${BT_API_KEY}"
                project_id: 42
                sync:
                    poll_interval_minutes: 15
    """

    def __init__(self, config: dict):
        self._config = config
        self._base_url = config["base_url"].rstrip("/")
        self._api_key = config["auth"]["api_key"]
        self._project_id = config.get("project_id")
        self._client: Optional[httpx.AsyncClient] = None
        self._page_size = config.get("page_size", 100)
        self._timeout = config.get("timeout", 30)

    # ─── Properties ────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "bugtracker"

    @property
    def display_name(self) -> str:
        return "BugTracker"

    @property
    def supported_sync_modes(self) -> list[SyncMode]:
        return [SyncMode.POLLING, SyncMode.INCREMENTAL, SyncMode.PUSH]

    # ─── Connection Management ────────────────────────────────

    async def connect(self) -> None:
        """Create HTTP client and verify API key."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(self._timeout),
        )
        logger.info(f"Connected to BugTracker at {self._base_url}")

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Disconnected from BugTracker")

    # ─── Health Check ─────────────────────────────────────────

    async def test_connection(self) -> HealthCheckResult:
        """Verify API connectivity by hitting the /status endpoint."""
        try:
            start = datetime.utcnow()
            response = await self._client.get("/status")
            elapsed = (datetime.utcnow() - start).total_seconds() * 1000

            if response.status_code == 200:
                data = response.json()
                return HealthCheckResult(
                    status=AdapterHealthStatus.HEALTHY,
                    response_time_ms=elapsed,
                    details={
                        "api_version": data.get("version"),
                        "authenticated": data.get("auth", False),
                    },
                )
            else:
                return HealthCheckResult(
                    status=AdapterHealthStatus.UNHEALTHY,
                    response_time_ms=elapsed,
                    error=f"API returned status {response.status_code}",
                )
        except httpx.ConnectError as e:
            return HealthCheckResult(
                status=AdapterHealthStatus.UNHEALTHY,
                error=f"Connection failed: {e}",
            )
        except Exception as e:
            return HealthCheckResult(
                status=AdapterHealthStatus.UNKNOWN,
                error=str(e),
            )

    # ─── Data Fetching ────────────────────────────────────────

    async def fetch_tickets(
        self,
        since: Optional[datetime] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> AsyncIterator[TicketData]:
        """Fetch tickets from BugTracker API with pagination."""
        params: dict = {
            "project_id": self._project_id,
            "limit": min(self._page_size, limit),
            "offset": offset,
            "sort": "updated_at",
            "order": "desc",
        }

        if since:
            params["updated_since"] = since.isoformat()

        total_fetched = 0
        current_offset = offset

        while total_fetched < limit:
            params["offset"] = current_offset

            response = await self._make_request(
                "GET", "/tickets", params=params
            )

            data = response.json()
            tickets = data.get("items", [])

            if not tickets:
                break

            for ticket_raw in tickets:
                yield self._normalize_ticket(ticket_raw)
                total_fetched += 1
                if total_fetched >= limit:
                    break

            # Check for more pages
            total_available = data.get("total", 0)
            if current_offset + len(tickets) >= total_available:
                break

            current_offset += len(tickets)

    async def fetch_ticket(self, ticket_id: str) -> TicketData:
        """Fetch a single ticket by ID."""
        response = await self._make_request(
            "GET", f"/tickets/{ticket_id}"
        )
        return self._normalize_ticket(response.json())

    async def fetch_comments(
        self, ticket_id: str
    ) -> list[CommentData]:
        """Fetch comments for a ticket."""
        response = await self._make_request(
            "GET", f"/tickets/{ticket_id}/comments"
        )
        comments = []
        for comment_raw in response.json().get("items", []):
            comments.append(self._normalize_comment(comment_raw))
        return comments

    # ─── Webhook Support ──────────────────────────────────────

    def verify_webhook(
        self, payload: bytes, signature: Optional[str] = None
    ) -> bool:
        """Verify webhook signature using HMAC-SHA256."""
        if not signature:
            return False

        webhook_secret = self._config.get("webhook_secret", "")
        expected = hmac.new(
            webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    def parse_webhook(self, payload: dict) -> TicketData:
        """Parse a webhook event payload into TicketData."""
        event_type = payload.get("event")

        if event_type in ("ticket.created", "ticket.updated"):
            return self._normalize_ticket(payload["data"])
        elif event_type == "ticket.deleted":
            # Handle deletion by returning minimal data
            return TicketData(
                ticket_id=payload["data"]["id"],
                title="[DELETED]",
                description="",
                status="Deleted",
                priority="None",
                source_system="bugtracker",
                source_adapter="bugtracker",
            )
        else:
            raise AdapterError(
                f"Unknown webhook event type: {event_type}"
            )

    # ─── Normalization ────────────────────────────────────────

    def _normalize_ticket(self, raw: dict) -> TicketData:
        """Convert BugTracker API response to TicketData."""
        return TicketData(
            ticket_id=str(raw["id"]),
            title=raw.get("title", ""),
            description=raw.get("description", "") or raw.get("body", ""),
            status=self._map_status(raw.get("status", "open")),
            priority=self._map_priority(raw.get("priority", "normal")),
            source_system="bugtracker",
            source_adapter="bugtracker",
            category=raw.get("category", {}).get("name"),
            subcategory=raw.get("component", {}).get("name"),
            created_at=self._parse_datetime(raw.get("created_at")),
            updated_at=self._parse_datetime(raw.get("updated_at")),
            resolved_at=self._parse_datetime(raw.get("resolved_at")),
            closed_at=self._parse_datetime(raw.get("closed_at")),
            reporter=raw.get("reporter", {}).get("email") or raw.get("reporter", {}).get("username"),
            assigned_to=raw.get("assignee", {}).get("email") or raw.get("assignee", {}).get("username"),
            assigned_group=raw.get("team", {}).get("name"),
            tags=[t["name"] for t in raw.get("tags", [])],
            custom_fields={
                "project": raw.get("project", {}).get("name"),
                "version": raw.get("version"),
                "environment": raw.get("environment"),
                "severity": raw.get("severity"),
            },
            raw_data=raw,
        )

    def _normalize_comment(self, raw: dict) -> CommentData:
        """Convert a comment API response to CommentData."""
        return CommentData(
            comment_id=str(raw["id"]),
            author=raw.get("author", {}).get("email") or raw.get("author", {}).get("username"),
            body=raw.get("body", ""),
            source_created_at=self._parse_datetime(raw.get("created_at")),
            is_internal=raw.get("visibility") == "internal",
        )

    # ─── Field Mapping ────────────────────────────────────────

    @staticmethod
    def _map_status(status: str) -> str:
        """Map BugTracker statuses to TicketInsight statuses."""
        mapping = {
            "new": "Open",
            "in_progress": "In Progress",
            "feedback": "Pending",
            "resolved": "Resolved",
            "closed": "Closed",
            "rejected": "Closed",
            "deferred": "Pending",
        }
        return mapping.get(status.lower(), status.title())

    @staticmethod
    def _map_priority(priority: str) -> str:
        """Map BugTracker priorities to TicketInsight priorities."""
        mapping = {
            "blocker": "Critical",
            "critical": "Critical",
            "major": "High",
            "normal": "Medium",
            "minor": "Low",
            "trivial": "Low",
        }
        return mapping.get(priority.lower(), priority.title())

    # ─── Utilities ────────────────────────────────────────────

    async def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> httpx.Response:
        """Make an HTTP request with error handling and retries."""
        if not self._client:
            raise AdapterError("Adapter is not connected")

        try:
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json_body,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited - retry after delay
                retry_after = int(e.response.headers.get("Retry-After", 30))
                logger.warning(f"Rate limited. Retrying after {retry_after}s")
                import asyncio
                await asyncio.sleep(retry_after)
                return await self._make_request(method, path, params, json_body)
            raise AdapterError(
                f"HTTP {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.TimeoutException as e:
            raise AdapterError(
                f"Request timed out after {self._timeout}s: {e}"
            ) from e

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        """Parse various datetime formats into Python datetime."""
        if not value:
            return None
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        logger.warning(f"Could not parse datetime: {value}")
        return None
```

### Step 2: Register the Adapter

```python
# src/ticketinsight/adapters/bugtracker.py (at the end of the file)

from ticketinsight.adapters.registry import register_adapter

# Auto-register when module is imported
register_adapter("bugtracker", BugTrackerAdapter)
```

### Step 3: Add Configuration

```yaml
# config.yaml
adapters:
  bugtracker:
    type: bugtracker
    base_url: "https://bugtracker.company.com/api/v2"
    auth:
      api_key: "${BT_API_KEY}"
    project_id: 42
    page_size: 100
    timeout: 30
    sync:
      incremental: true
      poll_interval_minutes: 15
    webhook:
      secret: "${BT_WEBHOOK_SECRET}"
      path: "/webhooks/bugtracker"
```

### Step 4: Test the Adapter

```python
# tests/test_adapters/test_bugtracker.py

import pytest
from unittest.mock import AsyncMock, patch
from ticketinsight.adapters.bugtracker import BugTrackerAdapter


@pytest.fixture
def adapter_config():
    return {
        "base_url": "https://bugtracker.example.com/api/v2",
        "auth": {"api_key": "test_key"},
        "project_id": 1,
    }


@pytest.fixture
def adapter(adapter_config):
    return BugTrackerAdapter(adapter_config)


class TestBugTrackerAdapter:
    @pytest.mark.asyncio
    async def test_connect(self, adapter):
        with patch.object(adapter, "_client", None):
            await adapter.connect()
            assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_normalize_ticket(self, adapter):
        raw = {
            "id": "BT-123",
            "title": "Login page broken",
            "description": "Users cannot log in",
            "status": "in_progress",
            "priority": "major",
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T12:00:00Z",
            "reporter": {"email": "user@example.com", "username": "jdoe"},
            "assignee": {"email": "admin@example.com", "username": "admin"},
            "tags": [{"name": "auth"}, {"name": "urgent"}],
            "category": {"name": "Authentication"},
        }

        ticket = adapter._normalize_ticket(raw)

        assert ticket.ticket_id == "BT-123"
        assert ticket.title == "Login page broken"
        assert ticket.status == "In Progress"
        assert ticket.priority == "High"
        assert ticket.category == "Authentication"
        assert ticket.tags == ["auth", "urgent"]

    def test_map_status(self):
        assert BugTrackerAdapter._map_status("new") == "Open"
        assert BugTrackerAdapter._map_status("in_progress") == "In Progress"
        assert BugTrackerAdapter._map_status("closed") == "Closed"
        assert BugTrackerAdapter._map_status("unknown") == "Unknown"

    def test_map_priority(self):
        assert BugTrackerAdapter._map_priority("blocker") == "Critical"
        assert BugTrackerAdapter._map_priority("major") == "High"
        assert BugTrackerAdapter._map_priority("normal") == "Medium"
        assert BugTrackerAdapter._map_priority("trivial") == "Low"
```

---

## Advanced Topics

### Rate Limiting

Implement exponential backoff for rate-limited APIs:

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class RateLimitedAdapter:
    """Base class for adapters that need rate limit handling."""

    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 60.0   # seconds

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(
            multiplier=BASE_DELAY,
            max=MAX_DELAY,
            exp_base=2,
        ),
        retry=retry_if_exception_type(RateLimitError),
    )
    async def _make_rate_limited_request(self, *args, **kwargs):
        """Make a request with automatic retry on rate limit."""
        response = await self._client.request(*args, **kwargs)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", self.BASE_DELAY))
            raise RateLimitError(
                f"Rate limited. Retry after {retry_after}s"
            )

        return response
```

### Cursor-Based Pagination

```python
async def fetch_tickets_cursor(
    self,
    since: Optional[datetime] = None,
    limit: int = 500,
) -> AsyncIterator[TicketData]:
    """Fetch using cursor-based pagination."""
    cursor = None
    total_fetched = 0

    while total_fetched < limit:
        params = {"limit": min(100, limit - total_fetched)}
        if cursor:
            params["cursor"] = cursor
        if since:
            params["updated_since"] = since.isoformat()

        response = await self._make_request("GET", "/tickets", params=params)
        data = response.json()

        for item in data["items"]:
            yield self._normalize_ticket(item)
            total_fetched += 1

        # Check for next page
        cursor = data.get("pagination", {}).get("next_cursor")
        if not cursor or not data.get("items"):
            break
```

### Batch Operations

For APIs that support batch queries:

```python
async def fetch_tickets_batch(self, ticket_ids: list[str]) -> list[TicketData]:
    """Fetch multiple tickets in a single batch request."""
    # Split into chunks if the API has a batch size limit
    BATCH_SIZE = 50
    results = []

    for i in range(0, len(ticket_ids), BATCH_SIZE):
        batch = ticket_ids[i:i + BATCH_SIZE]
        response = await self._make_request(
            "POST",
            "/tickets/batch",
            json_body={"ids": batch},
        )
        for raw in response.json()["items"]:
            results.append(self._normalize_ticket(raw))

    return results
```

---

## Testing Adapters

### Mock Server Testing

Use `pytest-httpx` or `respx` to mock HTTP responses:

```python
import pytest
import respx
from httpx import Response

@pytest.mark.asyncio
@respx.mock
async def test_fetch_tickets_with_mock_api(adapter_config):
    # Arrange: Mock the API responses
    respx.get("https://bugtracker.example.com/api/v2/tickets").mock(
        return_value=Response(200, json={
            "items": [
                {
                    "id": "BT-1",
                    "title": "Test ticket",
                    "status": "open",
                    "priority": "normal",
                }
            ],
            "total": 1,
        })
    )

    adapter = BugTrackerAdapter(adapter_config)
    await adapter.connect()

    # Act
    tickets = []
    async for ticket in adapter.fetch_tickets(limit=100):
        tickets.append(ticket)

    # Assert
    assert len(tickets) == 1
    assert tickets[0].ticket_id == "BT-1"
```

### Recording and Replaying

For integration tests, record real API responses and replay them:

```python
@pytest.fixture
def recorded_responses():
    """Load recorded API responses from JSON files."""
    import json
    with open("tests/fixtures/bugtracker/responses.json") as f:
        return json.load(f)

class TestWithRecordedData:
    def test_normalize_various_tickets(self, adapter, recorded_responses):
        for ticket_raw in recorded_responses["tickets"]:
            ticket = adapter._normalize_ticket(ticket_raw)
            assert ticket.ticket_id is not None
            assert ticket.title is not None
            assert ticket.source_system == "bugtracker"
```

---

## Registering Custom Adapters

### Method 1: Plugin Package

Create a Python package that registers your adapter:

```python
# my_ticketinsight_adapters/__init__.py

from ticketinsight.adapters.registry import register_adapter
from .my_adapter import MyCustomAdapter

register_adapter("my_custom", MyCustomAdapter)
```

Install alongside TicketInsight Pro:

```bash
pip install ticketinsight-pro my-ticketinsight-adapters
```

### Method 2: Entry Points (Recommended)

Add an entry point in your `pyproject.toml`:

```toml
[project.entry-points."ticketinsight.adapters"]
my_custom = "my_adapters:MyCustomAdapter"
```

This allows automatic discovery without importing:

```bash
pip install my-ticketinsight-adapters
# Adapter is now available in TicketInsight Pro
```

### Method 3: Configuration-Based Registration

Register via configuration:

```yaml
# config.yaml
adapters:
  my_custom:
    type: python
    module: "my_adapters.adapter"
    class: "MyCustomAdapter"
    config:
      base_url: "https://..."
```

---

## Reference: ServiceNow Adapter

Key implementation details:

- **Authentication**: Basic auth or OAuth2 client credentials
- **API**: ServiceNow Table API (`/api/now/table/{table}`)
- **Pagination**: Offset-based with `sysparm_offset` and `sysparm_limit`
- **Incremental Sync**: Uses `sysparm_query=ORDERBYsys_updated_on^sys_updated_on>javascript:gs.dateGenerate('{watermark}')`
- **Fields**: Configurable via `sysparm_fields` parameter
- **Rate Limiting**: Respects `X-Total-Count` and `Retry-After` headers

---

## Reference: Jira Adapter

Key implementation details:

- **Authentication**: API Token (personal access token) or Basic auth
- **API**: Jira REST API v3 (`/rest/api/3/search`)
- **Pagination**: Offset-based with `startAt` and `maxResults`
- **Incremental Sync**: JQL query with `updated >= "{watermark}"`
- **Filtering**: Full JQL support for flexible ticket filtering
- **Fields**: Configurable field selection via `fields` parameter
- **Expansion**: Comment expansion via `fields=comment`

---

## Reference: CSV Adapter

Key implementation details:

- **Source**: Local filesystem CSV files
- **Detection**: Auto-detects encoding (chardet), delimiter, and date formats
- **Mapping**: Configurable column-to-field mapping with auto-detection fallback
- **Watching**: Uses `watchdog` library for file system monitoring
- **Batching**: Processes large files in configurable chunk sizes
- **Validation**: Row-level validation with detailed error reporting

---

## Reference: REST Adapter

Key implementation details:

- **Source**: Any REST API
- **Authentication**: Bearer token, Basic auth, API key header
- **Pagination**: Supports offset, cursor, and link-header strategies
- **Response Mapping**: JSON path-based extraction (`data.items`, `data.total`)
- **Field Mapping**: Flexible source-to-target field mapping
- **Webhooks**: Inbound webhook receiver with signature verification

---

## Common Patterns

### Handling Authentication Errors

```python
async def _handle_auth_error(self, response: httpx.Response) -> None:
    """Detect and handle authentication failures."""
    if response.status_code in (401, 403):
        error_detail = response.json().get("error", "Unknown auth error")
        logger.error(f"Authentication failed: {error_detail}")

        # For OAuth2 adapters, try to refresh the token
        if self._config["auth"]["method"] == "oauth2":
            await self._refresh_token()

        # For API key adapters, this is a configuration issue
        elif self._config["auth"]["method"] == "api_key":
            raise AdapterError(
                f"Invalid API key. Please check your configuration. "
                f"Error: {error_detail}"
            )
```

### Handling Large Datasets

```python
async def fetch_all_tickets(
    self, since: Optional[datetime] = None
) -> AsyncIterator[TicketData]:
    """Efficiently fetch all tickets with memory-safe iteration."""
    batch_size = 500
    offset = 0

    while True:
        batch = []
        async for ticket in self.fetch_tickets(
            since=since, limit=batch_size, offset=offset
        ):
            batch.append(ticket)

        if not batch:
            break

        for ticket in batch:
            yield ticket

        if len(batch) < batch_size:
            break  # No more results

        offset += batch_size

        # Yield control to event loop
        await asyncio.sleep(0)
```

### Logging Best Practices

```python
logger.info(
    "Fetching tickets from adapter",
    extra={
        "adapter": self.name,
        "operation": "fetch_tickets",
        "since": since.isoformat() if since else "beginning",
        "limit": limit,
    }
)

logger.info(
    "Ticket fetch completed",
    extra={
        "adapter": self.name,
        "operation": "fetch_tickets",
        "tickets_fetched": total_fetched,
        "duration_ms": elapsed_ms,
    }
)
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|---------|
| `AdapterConnectionError` | Cannot reach API | Check URL, network, proxy settings |
| `401 Unauthorized` | Invalid credentials | Verify API key/token, check expiration |
| `429 Too Many Requests` | Rate limit exceeded | Increase `poll_interval_minutes`, check rate limit config |
| `Timeout after 30s` | API is slow | Increase `timeout` in config |
| `No tickets fetched` | Wrong query/filter | Check JQL, date range, project IDs |
| `Field mapping errors` | API response changed | Update field mapping in config, check raw data |
| `Encoding issues` | Wrong character set | Specify `encoding` in CSV adapter config |
| `Memory errors on large syncs` | Too many tickets in memory | Reduce `batch_size`, use streaming fetch |

For additional help, open an issue on GitHub with your adapter configuration
(secrets redacted) and the relevant log output.
