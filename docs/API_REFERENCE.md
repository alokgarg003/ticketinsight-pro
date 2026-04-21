# API Reference

> Complete REST API reference for TicketInsight Pro.
> Base URL: `http://localhost:8000/api/v1`

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Common Patterns](#common-patterns)
- [System Endpoints](#system-endpoints)
- [Authentication Endpoints](#authentication-endpoints)
- [Ticket Endpoints](#ticket-endpoints)
- [Analytics Endpoints](#analytics-endpoints)
- [NLP Endpoints](#nlp-endpoints)
- [ML Endpoints](#ml-endpoints)
- [Sync Endpoints](#sync-endpoints)
- [Dashboard Endpoints](#dashboard-endpoints)
- [Alert Endpoints](#alert-endpoints)
- [Adapter Endpoints](#adapter-endpoints)
- [Report Endpoints](#report-endpoints)
- [Websocket Events](#websocket-events)
- [Error Codes](#error-codes)
- [Rate Limiting](#rate-limiting)
- [SDK Examples](#sdk-examples)

---

## Overview

The TicketInsight Pro API is a RESTful JSON API served by FastAPI. All endpoints
are versioned under `/api/v1/` and follow consistent conventions for request
formatting, response structures, error handling, and pagination.

### Content Type

All requests and responses use `Content-Type: application/json` unless otherwise
specified. File download endpoints may return `application/pdf`,
`text/csv`, or `text/html`.

### Base URLs

| Environment | URL |
|-------------|-----|
| **Local Development** | `http://localhost:8000/api/v1` |
| **Docker Default** | `http://localhost:8000/api/v1` |
| **Production** | `https://your-domain.com/api/v1` |

### API Documentation

Interactive API documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## Authentication

All API endpoints (except `/health`, `/auth/login`, and `/docs`) require
authentication. TicketInsight Pro supports two authentication methods.

### Method 1: API Key

Pass your API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: tkp_admin_your_key_here" \
    http://localhost:8000/api/v1/tickets
```

### Method 2: JWT Bearer Token

First, obtain a token by logging in, then pass it in the `Authorization` header:

```bash
# Step 1: Login
curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": "your_password"}'

# Response: {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 1800}

# Step 2: Use the token
curl -H "Authorization: Bearer eyJ..." \
    http://localhost:8000/api/v1/tickets
```

---

## Common Patterns

### Pagination

List endpoints support cursor-based pagination:

```bash
GET /api/v1/tickets?cursor=eyJpZCI6MTAwfQ&limit=50
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | - | Cursor from previous page's `next_cursor` |
| `limit` | integer | 50 | Items per page (max: 200) |

**Response:**

```json
{
    "items": [...],
    "total": 15423,
    "cursor": "eyJpZCI6MTAwfQ",
    "next_cursor": "eyJpZCI6MTUwfQ",
    "has_more": true,
    "limit": 50
}
```

### Filtering

Most list endpoints support filtering via query parameters:

```bash
GET /api/v1/tickets?status=open&priority=High,Critical&category=Network
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status (comma-separated for multiple) |
| `priority` | string | Filter by priority |
| `category` | string | Filter by category |
| `assigned_to` | string | Filter by assignee |
| `date_from` | string | Start date (ISO 8601) |
| `date_to` | string | End date (ISO 8601) |
| `source` | string | Filter by source system |

### Sorting

```bash
GET /api/v1/tickets?sort=-created_at,priority
```

- Prefix with `-` for descending order
- Multiple sort fields are comma-separated
- Applied in order specified

### Date Formats

All timestamps use ISO 8601 format: `2024-01-15T10:30:00Z`

Period shortcuts are supported for analytics endpoints:

| Shortcut | Meaning |
|----------|---------|
| `1d` | Last 1 day |
| `7d` | Last 7 days |
| `30d` | Last 30 days |
| `90d` | Last 90 days |
| `1y` | Last 1 year |

---

## System Endpoints

### Health Check

```bash
GET /health
```

Returns system health status. Does not require authentication.

**Response (200 OK):**

```json
{
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 86400,
    "components": {
        "database": {
            "status": "connected",
            "type": "postgresql",
            "pool_size": 10,
            "active_connections": 3
        },
        "cache": {
            "status": "connected",
            "type": "redis",
            "hit_rate": 0.87
        },
        "ml_engine": {
            "status": "loaded",
            "models": {
                "categorizer": "trained (v2, 95.2% accuracy)",
                "sentiment": "trained (v1, 89.1% accuracy)",
                "priority_predictor": "trained (v3, 88.7% accuracy)"
            }
        },
        "adapters": {
            "servicenow": "connected",
            "jira": "configured",
            "csv_import": "idle"
        }
    },
    "timestamp": "2024-01-15T10:30:00Z"
}
```

### Get Version

```bash
GET /api/v1/system/version
```

**Response (200 OK):**

```json
{
    "version": "1.0.0",
    "build": "20240115.1",
    "python_version": "3.11.7",
    "api_version": "v1"
}
```

### Get Configuration

```bash
GET /api/v1/system/config
```

Returns the current configuration with all secrets redacted. Requires admin role.

**Response (200 OK):**

```json
{
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "workers": 2,
        "debug": false
    },
    "database": {
        "type": "postgresql",
        "host": "db.internal"
    },
    "adapters": {
        "servicenow": {
            "enabled": true,
            "instance": "https://***.service-now.com",
            "auth": {
                "method": "basic",
                "username": "***"
            }
        }
    },
    "nlp": {
        "categorizer": {
            "model": "tfidf_nb",
            "confidence_threshold": 0.6
        }
    }
}
```

### Get System Metrics

```bash
GET /api/v1/system/metrics
```

Returns Prometheus-compatible metrics for monitoring. Requires admin role.

**Response (200 OK):**

```json
{
    "process": {
        "cpu_percent": 12.5,
        "memory_mb": 345,
        "memory_percent": 8.6,
        "open_file_descriptors": 42,
        "threads": 8
    },
    "api": {
        "total_requests": 15432,
        "requests_per_minute": 23.5,
        "avg_response_time_ms": 45.2,
        "error_rate_percent": 0.3,
        "active_connections": 7
    },
    "database": {
        "pool_size": 10,
        "active_connections": 3,
        "idle_connections": 7,
        "total_queries": 89432,
        "avg_query_time_ms": 3.2
    },
    "queue": {
        "pending_tasks": 12,
        "completed_tasks": 4521,
        "failed_tasks": 3
    },
    "storage": {
        "tickets_count": 45210,
        "analyses_count": 38900,
        "disk_usage_mb": 234
    }
}
```

---

## Authentication Endpoints

### Login

```bash
POST /api/v1/auth/login
```

Authenticate with username and password to obtain JWT tokens.

**Request Body:**

```json
{
    "username": "admin",
    "password": "your_password"
}
```

**Response (200 OK):**

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
        "username": "admin",
        "role": "admin",
        "created_at": "2024-01-01T00:00:00Z"
    }
}
```

**Error Responses:**

| Status | Code | Description |
|--------|------|-------------|
| 401 | `AUTH_INVALID_CREDENTIALS` | Username or password is incorrect |
| 403 | `AUTH_ACCOUNT_DISABLED` | Account has been disabled |
| 422 | `VALIDATION_ERROR` | Missing required fields |

### Refresh Token

```bash
POST /api/v1/auth/refresh
```

Obtain a new access token using a refresh token.

**Request Body:**

```json
{
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 1800
}
```

### Get Current User

```bash
GET /api/v1/auth/me
```

Returns information about the currently authenticated user.

**Response (200 OK):**

```json
{
    "username": "admin",
    "role": "admin",
    "permissions": [
        "tickets:read", "tickets:write", "tickets:delete",
        "analytics:*", "nlp:*", "ml:*",
        "sync:*", "adapters:*", "dashboards:*",
        "alerts:*", "reports:*", "system:*"
    ],
    "created_at": "2024-01-01T00:00:00Z",
    "last_login": "2024-01-15T10:00:00Z"
}
```

### List Users (Admin Only)

```bash
GET /api/v1/auth/users
```

**Response (200 OK):**

```json
{
    "items": [
        {
            "username": "admin",
            "role": "admin",
            "created_at": "2024-01-01T00:00:00Z",
            "last_login": "2024-01-15T10:00:00Z"
        },
        {
            "username": "analyst",
            "role": "analyst",
            "created_at": "2024-01-05T00:00:00Z",
            "last_login": "2024-01-14T15:30:00Z"
        }
    ],
    "total": 2
}
```

### Create User (Admin Only)

```bash
POST /api/v1/auth/users
```

**Request Body:**

```json
{
    "username": "new_analyst",
    "password": "secure_password_here",
    "role": "analyst"
}
```

**Response (201 Created):**

```json
{
    "username": "new_analyst",
    "role": "analyst",
    "created_at": "2024-01-15T10:30:00Z"
}
```

---

## Ticket Endpoints

### List Tickets

```bash
GET /api/v1/tickets
```

Retrieve a paginated list of tickets with optional filtering and sorting.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | - | Pagination cursor |
| `limit` | integer | 50 | Results per page (max: 200) |
| `status` | string | - | Filter by status (comma-separated) |
| `priority` | string | - | Filter by priority (comma-separated) |
| `category` | string | - | Filter by category |
| `subcategory` | string | - | Filter by subcategory |
| `assigned_to` | string | - | Filter by assignee username |
| `assigned_group` | string | - | Filter by assigned group |
| `source` | string | - | Filter by source system |
| `date_from` | string | - | Start date (ISO 8601) |
| `date_to` | string | - | End date (ISO 8601) |
| `sort` | string | `-created_at` | Sort field(s) |
| `include` | string | - | Include related data: `analysis`, `comments` |
| `search` | string | - | Full-text search in title and description |

**Response (200 OK):**

```json
{
    "items": [
        {
            "id": 1,
            "ticket_id": "INC0012345",
            "source_system": "servicenow",
            "title": "Laptop screen flickering after latest update",
            "description": "After installing the latest Windows update...",
            "status": "In Progress",
            "priority": "High",
            "category": "Hardware",
            "subcategory": "Display",
            "reporter": "john.smith@company.com",
            "assigned_to": "it.support@company.com",
            "assigned_group": "Hardware Support",
            "tags": ["laptop", "display", "windows-update"],
            "created_at": "2024-01-15T08:30:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
            "resolved_at": null,
            "closed_at": null
        }
    ],
    "total": 45210,
    "cursor": null,
    "next_cursor": "eyJpZCI6NTB9",
    "has_more": true,
    "limit": 50
}
```

### Get Ticket by ID

```bash
GET /api/v1/tickets/{ticket_id}
```

Retrieve a single ticket with full details.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `ticket_id` | string | Source ticket ID (e.g., `INC0012345`) |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include` | string | - | Related data to include: `analysis`, `comments`, `timeline` |

**Response (200 OK):**

```json
{
    "id": 1,
    "ticket_id": "INC0012345",
    "source_system": "servicenow",
    "source_adapter": "servicenow",
    "title": "Laptop screen flickering after latest update",
    "description": "After installing the latest Windows update (KB5034441), my Dell Latitude 5540 screen started flickering intermittently. The issue occurs approximately every 5 minutes and lasts for 2-3 seconds. I have tried updating the display driver to the latest version from Dell's website, but the issue persists. This is affecting my ability to work as I use the laptop for design work.\n\nSteps taken:\n1. Updated display driver to v31.0.15.5121\n2. Ran Windows display troubleshooter (no issues found)\n3. Connected external monitor (works fine)\n4. Booted into safe mode (no flickering in safe mode)",
    "status": "In Progress",
    "priority": "High",
    "category": "Hardware",
    "subcategory": "Display",
    "reporter": "john.smith@company.com",
    "assigned_to": "it.support@company.com",
    "assigned_group": "Hardware Support",
    "tags": ["laptop", "display", "windows-update", "dell"],
    "custom_fields": {
        "location": "Building A, Floor 3",
        "department": "Design",
        "impact": "1 - High",
        "urgency": "1 - High"
    },
    "created_at": "2024-01-15T08:30:00Z",
    "updated_at": "2024-01-15T10:00:00Z",
    "resolved_at": null,
    "closed_at": null,
    "ingested_at": "2024-01-15T08:31:00Z",
    "analysis": {
        "predicted_category": "Hardware",
        "predicted_subcategory": "Display",
        "category_confidence": 0.94,
        "summary": "User reports screen flickering on Dell Latitude 5540 after Windows update KB5034441. Troubleshooting steps taken include driver update, troubleshooter, external monitor test, and safe mode boot. Issue persists in normal mode. External monitor works fine.",
        "sentiment": "negative",
        "sentiment_score": -0.45,
        "keywords": ["laptop", "screen", "flickering", "windows update", "display driver", "dell latitude", "safe mode", "external monitor"],
        "is_duplicate": false,
        "predicted_priority": "High",
        "priority_confidence": 0.87,
        "recommended_assignee": "Hardware Support",
        "assignee_confidence": 0.82,
        "analyzed_at": "2024-01-15T08:32:00Z"
    },
    "comments": [
        {
            "id": 1,
            "author": "it.support@company.com",
            "body": "Hi John, I've seen similar issues with this Windows update. Let me check if there's a known workaround. In the meantime, can you try rolling back the update?",
            "created_at": "2024-01-15T09:00:00Z",
            "is_internal": false
        },
        {
            "id": 2,
            "author": "john.smith@company.com",
            "body": "I rolled back the update and the flickering stopped. But I need this update for security compliance. Is there a fix coming?",
            "created_at": "2024-01-15T09:30:00Z",
            "is_internal": false
        }
    ]
}
```

**Error Responses:**

| Status | Code | Description |
|--------|------|-------------|
| 404 | `TICKET_NOT_FOUND` | No ticket with the specified ID exists |

### Get Ticket Comments

```bash
GET /api/v1/tickets/{ticket_id}/comments
```

**Response (200 OK):**

```json
{
    "ticket_id": "INC0012345",
    "comments": [
        {
            "id": 1,
            "author": "it.support@company.com",
            "body": "Acknowledged. Investigating...",
            "created_at": "2024-01-15T09:00:00Z",
            "is_internal": true,
            "sentiment": "neutral"
        }
    ],
    "total": 1
}
```

### Get Ticket Timeline

```bash
GET /api/v1/tickets/{ticket_id}/timeline
```

Returns the full lifecycle timeline of a ticket including status changes,
assignments, comments, and analysis events.

**Response (200 OK):**

```json
{
    "ticket_id": "INC0012345",
    "events": [
        {
            "timestamp": "2024-01-15T08:30:00Z",
            "event_type": "created",
            "description": "Ticket created by john.smith@company.com",
            "actor": "john.smith@company.com",
            "details": {"priority": "High", "category": "Hardware"}
        },
        {
            "timestamp": "2024-01-15T08:31:00Z",
            "event_type": "analyzed",
            "description": "NLP analysis completed",
            "actor": "system",
            "details": {
                "category": "Hardware/Display",
                "sentiment": "negative",
                "is_duplicate": false
            }
        },
        {
            "timestamp": "2024-01-15T08:35:00Z",
            "event_type": "assigned",
            "description": "Assigned to Hardware Support group",
            "actor": "system",
            "details": {"from": null, "to": "Hardware Support"}
        },
        {
            "timestamp": "2024-01-15T09:00:00Z",
            "event_type": "comment",
            "description": "Comment added by it.support@company.com",
            "actor": "it.support@company.com"
        }
    ]
}
```

### Search Tickets

```bash
POST /api/v1/tickets/search
```

Advanced full-text search with complex query syntax.

**Request Body:**

```json
{
    "query": "laptop screen display issue",
    "filters": {
        "status": ["open", "in_progress"],
        "priority": ["High", "Critical"],
        "category": ["Hardware"],
        "date_from": "2024-01-01T00:00:00Z",
        "date_to": "2024-01-15T23:59:59Z"
    },
    "sort": "-relevance",
    "limit": 20
}
```

**Query Syntax:**

| Syntax | Description | Example |
|--------|-------------|---------|
| Plain text | Full-text search | `laptop screen` |
| Quoted | Exact phrase | `"screen flickering"` |
| NOT | Exclude term | `laptop NOT desktop` |
| OR | Either term | `screen OR display` |
| field: | Field-specific | `status:open category:Network` |

**Response (200 OK):**

```json
{
    "items": [
        {
            "ticket_id": "INC0012345",
            "title": "Laptop screen flickering after latest update",
            "status": "In Progress",
            "priority": "High",
            "category": "Hardware",
            "relevance_score": 0.95,
            "highlighted_description": "...<em>laptop screen</em> <em>flickering</em> after latest update..."
        }
    ],
    "total": 47,
    "search_time_ms": 23,
    "query": "laptop screen display issue"
}
```

### Delete Ticket

```bash
DELETE /api/v1/tickets/{ticket_id}
```

Remove a ticket from the local store. This does not affect the source system.

**Response (200 OK):**

```json
{
    "message": "Ticket INC0012345 deleted successfully",
    "ticket_id": "INC0012345"
}
```

---

## Analytics Endpoints

### Get Summary

```bash
GET /api/v1/analytics/summary
```

Retrieve an overall summary of ticket data for the specified period.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `30d` | Time period (e.g., `7d`, `30d`, `90d`) |
| `date_from` | string | - | Start date (overrides period) |
| `date_to` | string | - | End date (overrides period) |
| `source` | string | - | Filter by source system |

**Response (200 OK):**

```json
{
    "period": {
        "start": "2023-12-16T00:00:00Z",
        "end": "2024-01-15T23:59:59Z",
        "label": "Last 30 days"
    },
    "kpis": {
        "total_tickets": 4521,
        "new_tickets": 3210,
        "resolved_tickets": 2890,
        "open_tickets": 890,
        "avg_resolution_time_hours": 18.5,
        "median_resolution_time_hours": 12.3,
        "first_contact_resolution_rate": 0.62,
        "sla_compliance_rate": 0.91,
        "avg_customer_satisfaction": 4.1,
        "ticket_backlog": 890,
        "escalation_rate": 0.08,
        "reopen_rate": 0.05
    },
    "trend_comparison": {
        "vs_previous_period": {
            "volume_change_percent": -5.2,
            "resolution_time_change_percent": -8.1,
            "sla_compliance_change_percent": 2.3,
            "satisfaction_change_percent": 0.3
        }
    },
    "priority_distribution": {
        "Critical": 120,
        "High": 680,
        "Medium": 1890,
        "Low": 1831
    },
    "status_distribution": {
        "Open": 340,
        "In Progress": 350,
        "Resolved": 2890,
        "Closed": 941
    },
    "category_distribution": {
        "Hardware": 1230,
        "Software": 1560,
        "Network": 780,
        "Access": 450,
        "Email": 321,
        "Other": 180
    },
    "top_categories": [
        {"category": "Software", "count": 1560, "change_percent": -3.2},
        {"category": "Hardware", "count": 1230, "change_percent": 7.1},
        {"category": "Network", "count": 780, "change_percent": 12.5}
    ],
    "generated_at": "2024-01-15T10:30:00Z"
}
```

### Get Trends

```bash
GET /api/v1/analytics/trends
```

Get time-series trend data for ticket metrics.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `30d` | Time period |
| `granularity` | string | `daily` | Data point granularity: `hourly`, `daily`, `weekly` |
| `metric` | string | `volume` | Metric to trend: `volume`, `resolution_time`, `backlog` |
| `include_forecast` | boolean | `false` | Include forecast data |

**Response (200 OK):**

```json
{
    "metric": "volume",
    "granularity": "daily",
    "period": {"start": "...", "end": "..."},
    "data": [
        {
            "date": "2024-01-01",
            "value": 120,
            "breakdown": {
                "Critical": 5, "High": 22, "Medium": 53, "Low": 40
            }
        },
        {
            "date": "2024-01-02",
            "value": 98,
            "breakdown": {
                "Critical": 3, "High": 18, "Medium": 45, "Low": 32
            }
        }
    ],
    "statistics": {
        "mean": 107,
        "stddev": 15.3,
        "min": 78,
        "max": 156,
        "trend": "decreasing",
        "trend_slope": -1.2
    },
    "moving_average": [
        {"date": "2024-01-07", "value": 105.3}
    ],
    "forecast": [
        {
            "date": "2024-01-16",
            "value": 95,
            "lower_bound": 78,
            "upper_bound": 112,
            "confidence": 0.95
        }
    ]
}
```

### Get Category Analysis

```bash
GET /api/v1/analytics/categories
```

Detailed category-level analysis.

**Response (200 OK):**

```json
{
    "categories": [
        {
            "name": "Hardware",
            "count": 1230,
            "percentage": 27.2,
            "avg_resolution_time_hours": 22.1,
            "sla_compliance_rate": 0.88,
            "top_subcategories": [
                {"name": "Laptop", "count": 520, "avg_resolution_hours": 18.3},
                {"name": "Display", "count": 310, "avg_resolution_hours": 24.1},
                {"name": "Peripheral", "count": 200, "avg_resolution_hours": 8.2},
                {"name": "Other", "count": 200, "avg_resolution_hours": 30.5}
            ],
            "trend": "increasing",
            "trend_change_percent": 7.1,
            "top_keywords": ["laptop", "screen", "keyboard", "mouse", "dock"],
            "sentiment_avg": -0.15
        }
    ],
    "category_correlations": [
        {"category_a": "Hardware", "category_b": "Software", "correlation": 0.23}
    ]
}
```

### Get Performance Metrics

```bash
GET /api/v1/analytics/performance
```

Team and agent performance metrics.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `30d` | Time period |
| `group_by` | string | `team` | Group by: `team`, `agent`, `category` |
| `top_n` | integer | 20 | Number of top entries to return |

**Response (200 OK):**

```json
{
    "group_by": "team",
    "period": {"start": "...", "end": "..."},
    "teams": [
        {
            "name": "Hardware Support",
            "total_tickets": 456,
            "resolved": 410,
            "open": 46,
            "resolution_rate": 0.899,
            "avg_resolution_time_hours": 18.3,
            "median_resolution_time_hours": 14.2,
            "sla_compliance_rate": 0.92,
            "avg_csat": 4.3,
            "first_contact_resolution_rate": 0.65,
            "escalation_rate": 0.06,
            "top_categories": [
                {"name": "Laptop", "count": 220},
                {"name": "Display", "count": 136}
            ]
        }
    ],
    "rankings": {
        "by_resolution_rate": [
            {"name": "Access Management", "value": 0.95},
            {"name": "Hardware Support", "value": 0.899}
        ],
        "by_avg_resolution_time": [
            {"name": "Access Management", "value": 4.2},
            {"name": "Email Support", "value": 8.1}
        ]
    }
}
```

### Get SLA Report

```bash
GET /api/v1/analytics/sla
```

SLA compliance reporting.

**Response (200 OK):**

```json
{
    "period": {"start": "...", "end": "..."},
    "overall": {
        "response_compliance_rate": 0.95,
        "resolution_compliance_rate": 0.91,
        "total_breaches": 45,
        "at_risk": 12
    },
    "by_priority": {
        "Critical": {
            "total": 120,
            "response_met": 112,
            "response_rate": 0.933,
            "resolution_met": 105,
            "resolution_rate": 0.875,
            "avg_response_time_minutes": 8.5,
            "avg_resolution_time_hours": 3.2,
            "breaches": [
                {
                    "ticket_id": "INC0011000",
                    "breach_type": "resolution",
                    "sla_target_hours": 4,
                    "actual_hours": 5.3,
                    "breach_by_hours": 1.3
                }
            ]
        }
    },
    "trends": {
        "compliance_trend": [
            {"date": "2024-01-08", "response_rate": 0.94, "resolution_rate": 0.89},
            {"date": "2024-01-15", "response_rate": 0.95, "resolution_rate": 0.91}
        ]
    }
}
```

### Get Anomalies

```bash
GET /api/v1/analytics/anomalies
```

Get detected anomalies in ticket metrics.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `7d` | Time period to check |
| `severity` | string | `all` | Filter: `low`, `medium`, `high`, `critical`, `all` |
| `type` | string | `all` | Filter: `volume`, `resolution_time`, `escalation`, `all` |

**Response (200 OK):**

```json
{
    "anomalies": [
        {
            "id": "anom_001",
            "type": "volume_spike",
            "severity": "high",
            "detected_at": "2024-01-15T09:00:00Z",
            "metric": "tickets_created_per_hour",
            "actual_value": 47,
            "expected_value": 12,
            "deviation_score": 3.9,
            "description": "Ticket creation rate 3.9x above normal for Monday 9AM",
            "related_categories": ["Network", "Email"],
            "related_keywords": ["outage", "cannot connect", "timeout"],
            "time_window": {
                "start": "2024-01-15T08:00:00Z",
                "end": "2024-01-15T09:00:00Z"
            },
            "status": "active",
            "acknowledged": false
        }
    ],
    "summary": {
        "total": 3,
        "by_severity": {"high": 1, "medium": 2},
        "by_type": {"volume_spike": 1, "resolution_time": 2}
    }
}
```

---

## NLP Endpoints

### Categorize Text

```bash
POST /api/v1/nlp/categorize
```

Classify text into ticket categories.

**Request Body:**

```json
{
    "text": "My laptop screen goes black when I close and open the lid",
    "include_confidence": true,
    "include_alternatives": true,
    "max_alternatives": 3
}
```

**Response (200 OK):**

```json
{
    "category": "Hardware",
    "subcategory": "Display",
    "confidence": 0.94,
    "subcategory_confidence": 0.87,
    "alternatives": [
        {"category": "Hardware", "subcategory": "Laptop", "confidence": 0.03},
        {"category": "Software", "subcategory": "Power Management", "confidence": 0.02},
        {"category": "Hardware", "subcategory": "Hinge", "confidence": 0.01}
    ],
    "model_version": "categorizer_v2",
    "processing_time_ms": 12
}
```

### Summarize Text

```bash
POST /api/v1/nlp/summarize
```

Generate a summary of ticket text.

**Request Body:**

```json
{
    "text": "After installing the latest Windows update (KB5034441)...\n\n[Long description follows]",
    "mode": "extractive",
    "max_sentences": 3,
    "max_words": 100
}
```

**Response (200 OK):**

```json
{
    "summary": "User reports screen flickering on Dell Latitude 5540 after Windows update KB5034441. Troubleshooting steps taken include driver update, display troubleshooter, and external monitor testing. Issue persists in normal mode but not in safe mode.",
    "mode": "extractive",
    "original_length": 312,
    "summary_length": 45,
    "compression_ratio": 0.144,
    "key_sentences": [
        "User reports screen flickering on Dell Latitude 5540 after Windows update KB5034441.",
        "Troubleshooting steps taken include driver update, display troubleshooter, and external monitor testing."
    ],
    "processing_time_ms": 8
}
```

### Analyze Sentiment

```bash
POST /api/v1/nlp/sentiment
```

Analyze the sentiment of ticket text.

**Request Body:**

```json
{
    "text": "This is the third time I'm reporting this issue and nobody has fixed it yet. Very frustrated with the lack of support.",
    "include_emotions": true
}
```

**Response (200 OK):**

```json
{
    "sentiment": "very_negative",
    "score": -0.82,
    "magnitude": 0.92,
    "label": "Very Negative",
    "emotions": {
        "frustration": 0.78,
        "anger": 0.45,
        "urgency": 0.60,
        "disappointment": 0.55,
        "confusion": 0.10,
        "satisfaction": 0.01
    },
    "escalation_risk": "high",
    "escalation_risk_score": 0.85,
    "processing_time_ms": 6
}
```

### Extract Keywords

```bash
POST /api/v1/nlp/keywords
```

Extract keywords and entities from text.

**Request Body:**

```json
{
    "text": "John Smith in Building A Floor 3 reports that his Dell Latitude 5540 laptop screen is flickering after installing Windows update KB5034441. The issue started yesterday at 2pm.",
    "max_keywords": 15,
    "include_entities": true
}
```

**Response (200 OK):**

```json
{
    "keywords": [
        {"word": "dell latitude 5540", "score": 0.89, "frequency": 1},
        {"word": "screen flickering", "score": 0.85, "frequency": 1},
        {"word": "windows update kb5034441", "score": 0.82, "frequency": 1},
        {"word": "laptop", "score": 0.78, "frequency": 1},
        {"word": "building a floor 3", "score": 0.65, "frequency": 1}
    ],
    "entities": {
        "person": [{"text": "John Smith", "start": 0, "end": 10}],
        "location": [{"text": "Building A Floor 3", "start": 19, "end": 37}],
        "product": [{"text": "Dell Latitude 5540", "start": 46, "end": 64}],
        "software": [{"text": "Windows update KB5034441", "start": 87, "end": 112}],
        "date": [{"text": "yesterday at 2pm", "start": 126, "end": 143}]
    },
    "technical_terms": ["screen flickering", "windows update", "kb5034441"],
    "processing_time_ms": 15
}
```

### Find Duplicates

```bash
POST /api/v1/nlp/duplicates
```

Find duplicate or near-duplicate tickets.

**Request Body:**

```json
{
    "ticket_id": "INC0012345",
    "threshold": 0.85,
    "time_window_days": 7,
    "max_results": 10
}
```

**Response (200 OK):**

```json
{
    "ticket_id": "INC0012345",
    "duplicates": [
        {
            "ticket_id": "INC0011000",
            "title": "Screen flickers on Dell laptop after update",
            "similarity_score": 0.91,
            "status": "Resolved",
            "resolved_at": "2024-01-10T15:00:00Z",
            "resolution_summary": "Rolled back Windows update and applied fix from Dell",
            "matching_fields": ["description", "category"],
            "recommended_action": "link"
        }
    ],
    "total_checked": 245,
    "above_threshold": 1,
    "processing_time_ms": 45
}
```

### Batch NLP Processing

```bash
POST /api/v1/nlp/batch
```

Run multiple NLP operations on a batch of tickets.

**Request Body:**

```json
{
    "ticket_ids": ["INC0012345", "INC0012346", "INC0012347"],
    "operations": ["categorize", "summarize", "sentiment", "keywords", "duplicates"],
    "options": {
        "summarize": {"mode": "extractive", "max_sentences": 3},
        "duplicates": {"threshold": 0.85}
    }
}
```

**Response (200 OK):**

```json
{
    "batch_id": "batch_abc123",
    "status": "completed",
    "total_tickets": 3,
    "results": [
        {
            "ticket_id": "INC0012345",
            "status": "success",
            "categorization": { "category": "Hardware", "confidence": 0.94 },
            "summary": { "summary": "...", "mode": "extractive" },
            "sentiment": { "sentiment": "negative", "score": -0.45 },
            "keywords": { "keywords": [...] },
            "duplicates": { "is_duplicate": false }
        }
    ],
    "processing_time_ms": 230,
    "errors": []
}
```

---

## ML Endpoints

### Predict Priority

```bash
POST /api/v1/ml/predict-priority
```

Predict the priority of a ticket.

**Request Body:**

```json
{
    "text": "Critical: Email system is completely down for all users in the company. No one can send or receive emails. This is affecting all business operations.",
    "category": "Email",
    "reporter": "jane.doe@company.com"
}
```

**Response (200 OK):**

```json
{
    "predicted_priority": "Critical",
    "confidence": 0.92,
    "probabilities": {
        "Critical": 0.92,
        "High": 0.05,
        "Medium": 0.02,
        "Low": 0.01
    },
    "key_factors": [
        {"feature": "mentions_outage", "value": true, "weight": 0.35},
        {"feature": "mentions_all_users", "value": true, "weight": 0.25},
        {"feature": "category_email", "value": true, "weight": 0.20},
        {"feature": "urgency_words", "value": true, "weight": 0.15},
        {"feature": "sentiment", "value": -0.70, "weight": 0.05}
    ],
    "model_version": "priority_v3",
    "processing_time_ms": 5
}
```

### Recommend Assignee

```bash
POST /api/v1/ml/recommend-assignee
```

Get assignment recommendations for a ticket.

**Request Body:**

```json
{
    "text": "VPN connection drops every 10 minutes when working remotely",
    "category": "Network",
    "priority": "High",
    "location": "Building A"
}
```

**Response (200 OK):**

```json
{
    "recommendations": [
        {
            "team": "Network Operations",
            "confidence": 0.85,
            "reason": "95% resolution rate on similar VPN tickets",
            "avg_resolution_time_hours": 2.3,
            "current_workload": "moderate",
            "active_tickets": 8,
            "agents": [
                {"name": "net.admin@company.com", "expertise_score": 0.95, "workload": "low"},
                {"name": "net.senior@company.com", "expertise_score": 0.88, "workload": "moderate"}
            ]
        },
        {
            "team": "Infrastructure",
            "confidence": 0.12,
            "reason": "Secondary expertise in VPN infrastructure",
            "avg_resolution_time_hours": 6.1,
            "current_workload": "high",
            "active_tickets": 22
        }
    ],
    "model_version": "assignee_v2",
    "processing_time_ms": 18
}
```

### Forecast Volumes

```bash
POST /api/v1/ml/forecast
```

Generate ticket volume forecasts.

**Request Body:**

```json
{
    "metric": "ticket_volume",
    "horizon_days": 14,
    "confidence_level": 0.95,
    "granularity": "daily",
    "category": null
}
```

**Response (200 OK):**

```json
{
    "metric": "ticket_volume",
    "historical": {
        "period": {"start": "2023-12-16", "end": "2024-01-15"},
        "data_points": 31,
        "mean": 107,
        "trend": "stable"
    },
    "forecast": [
        {
            "date": "2024-01-16",
            "predicted": 105,
            "lower_bound": 85,
            "upper_bound": 125,
            "day_of_week": "Tuesday"
        },
        {
            "date": "2024-01-17",
            "predicted": 98,
            "lower_bound": 78,
            "upper_bound": 118,
            "day_of_week": "Wednesday"
        }
    ],
    "model_version": "forecast_v1",
    "accuracy_metrics": {
        "mape": 8.5,
        "rmse": 9.2,
        "last_training_date": "2024-01-14T03:00:00Z"
    }
}
```

### List Models

```bash
GET /api/v1/ml/models
```

List all trained ML models with their metadata.

**Response (200 OK):**

```json
{
    "models": [
        {
            "id": "categorizer_v2",
            "type": "categorizer",
            "algorithm": "tfidf_multinomial_nb",
            "trained_at": "2024-01-14T03:00:00Z",
            "training_samples": 15000,
            "accuracy": 0.952,
            "status": "active",
            "features": ["description_text", "title_text"]
        },
        {
            "id": "priority_v3",
            "type": "priority_predictor",
            "algorithm": "gradient_boosting",
            "trained_at": "2024-01-14T03:00:00Z",
            "training_samples": 20000,
            "accuracy": 0.887,
            "status": "active",
            "features": ["description_length", "category", "sentiment", "urgency_words"]
        }
    ]
}
```

### Retrain Model

```bash
POST /api/v1/ml/models/{model_id}/retrain
```

Trigger retraining of a specific model with latest data.

**Request Body (optional):**

```json
{
    "sample_size": null,
    "parameters": {
        "n_estimators": 150,
        "max_depth": 6
    }
}
```

**Response (202 Accepted):**

```json
{
    "message": "Model retraining initiated",
    "model_id": "priority_v3",
    "task_id": "task_retrain_priority_v3",
    "status": "queued",
    "estimated_time_minutes": 5
}
```

---

## Sync Endpoints

### Trigger Sync

```bash
POST /api/v1/sync/{adapter_name}
```

Trigger data synchronization for a specific adapter.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `adapter_name` | string | Name of the adapter (e.g., `servicenow`) |

**Request Body (optional):**

```json
{
    "full_sync": false,
    "dry_run": false
}
```

**Response (202 Accepted):**

```json
{
    "message": "Sync initiated for adapter 'servicenow'",
    "adapter": "servicenow",
    "task_id": "sync_snow_20240115_103000",
    "mode": "incremental",
    "status": "running"
}
```

### Sync All Adapters

```bash
POST /api/v1/sync/all
```

**Response (202 Accepted):**

```json
{
    "message": "Sync initiated for all adapters",
    "tasks": [
        {"adapter": "servicenow", "task_id": "sync_snow_...", "status": "running"},
        {"adapter": "jira", "task_id": "sync_jira_...", "status": "queued"},
        {"adapter": "csv_import", "task_id": "sync_csv_...", "status": "skipped", "reason": "no new files"}
    ]
}
```

### Get Sync Status

```bash
GET /api/v1/sync/{adapter_name}/status
```

**Response (200 OK):**

```json
{
    "adapter": "servicenow",
    "status": "idle",
    "last_sync": {
        "started_at": "2024-01-15T10:00:00Z",
        "completed_at": "2024-01-15T10:02:30Z",
        "duration_seconds": 150,
        "status": "completed",
        "mode": "incremental",
        "tickets_fetched": 245,
        "tickets_created": 12,
        "tickets_updated": 98,
        "tickets_skipped": 135,
        "watermark": "2024-01-15T09:55:00Z",
        "error_count": 0
    },
    "next_scheduled": "2024-01-15T10:15:00Z",
    "historical_success_rate": 0.98
}
```

### Get Sync Logs

```bash
GET /api/v1/sync/{adapter_name}/logs
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Number of log entries |
| `status` | string | `all` | Filter: `completed`, `failed`, `all` |

**Response (200 OK):**

```json
{
    "logs": [
        {
            "id": 42,
            "adapter": "servicenow",
            "started_at": "2024-01-15T10:00:00Z",
            "completed_at": "2024-01-15T10:02:30Z",
            "duration_seconds": 150,
            "status": "completed",
            "mode": "incremental",
            "tickets_fetched": 245,
            "tickets_created": 12,
            "tickets_updated": 98,
            "errors": []
        }
    ],
    "total": 150,
    "adapter": "servicenow"
}
```

---

## Dashboard Endpoints

### Get Dashboard

```bash
GET /api/v1/dashboards/{dashboard_id}
```

**Response (200 OK):**

```json
{
    "id": "default",
    "name": "Default Dashboard",
    "title": "IT Support Overview",
    "period": "30d",
    "generated_at": "2024-01-15T10:30:00Z",
    "widgets": [
        {
            "id": "kpi_open",
            "type": "kpi_card",
            "title": "Open Tickets",
            "value": 890,
            "change_percent": -5.2,
            "change_direction": "down",
            "subtitle": "vs previous 30 days"
        },
        {
            "id": "volume_trend",
            "type": "time_series",
            "title": "Ticket Volume",
            "data": {
                "labels": ["Jan 1", "Jan 2", ...],
                "datasets": [
                    {"label": "Created", "data": [120, 98, ...]},
                    {"label": "Resolved", "data": [110, 95, ...]}
                ]
            }
        },
        {
            "id": "category_dist",
            "type": "bar_chart",
            "title": "Tickets by Category",
            "data": {
                "labels": ["Hardware", "Software", "Network", ...],
                "values": [1230, 1560, 780, ...]
            }
        },
        {
            "id": "priority_pie",
            "type": "pie_chart",
            "title": "Priority Distribution",
            "data": {
                "labels": ["Critical", "High", "Medium", "Low"],
                "values": [120, 680, 1890, 1831],
                "colors": ["#ef4444", "#f97316", "#eab308", "#22c55e"]
            }
        },
        {
            "id": "recent_anomalies",
            "type": "table",
            "title": "Recent Anomalies",
            "data": {
                "headers": ["Time", "Type", "Severity", "Description"],
                "rows": [
                    ["09:00", "Volume Spike", "High", "3.9x above normal"],
                    ["14:00", "Resolution Time", "Medium", "Avg 2x above baseline"]
                ]
            }
        }
    ]
}
```

### List Dashboards

```bash
GET /api/v1/dashboards
```

**Response (200 OK):**

```json
{
    "dashboards": [
        {"id": "default", "name": "Default Dashboard", "title": "IT Support Overview"},
        {"id": "sla_tracking", "name": "SLA Tracking", "title": "SLA Compliance Dashboard"},
        {"id": "team_performance", "name": "Team Performance", "title": "Team Metrics"}
    ]
}
```

---

## Alert Endpoints

### List Alert Rules

```bash
GET /api/v1/alerts/rules
```

**Response (200 OK):**

```json
{
    "rules": [
        {
            "id": "rule_001",
            "name": "Volume Spike",
            "condition": "tickets_created_per_hour > 2 * baseline",
            "severity": "high",
            "enabled": true,
            "channels": ["slack", "email"],
            "last_triggered": "2024-01-15T09:00:00Z",
            "trigger_count": 5
        }
    ]
}
```

### Create Alert Rule

```bash
POST /api/v1/alerts/rules
```

**Request Body:**

```json
{
    "name": "High Priority Backlog",
    "condition": "tickets.priority == 'High' AND status == 'Open' AND age_hours > 4",
    "severity": "medium",
    "channels": [
        {"type": "slack", "webhook_url": "${SLACK_WEBHOOK}"},
        {"type": "email", "to": "team-lead@company.com"}
    ],
    "cooldown_minutes": 60
}
```

### Get Alert History

```bash
GET /api/v1/alerts/history
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Number of alerts to return |
| `severity` | string | `all` | Filter by severity |
| `date_from` | string | - | Start date |

**Response (200 OK):**

```json
{
    "alerts": [
        {
            "id": "alert_001",
            "rule_id": "rule_001",
            "rule_name": "Volume Spike",
            "severity": "high",
            "triggered_at": "2024-01-15T09:00:00Z",
            "message": "Ticket volume is 3.9x above normal (47/hr vs expected 12/hr)",
            "channels_sent": ["slack", "email"],
            "acknowledged": true,
            "acknowledged_by": "admin",
            "acknowledged_at": "2024-01-15T09:05:00Z"
        }
    ],
    "total": 23
}
```

---

## Adapter Endpoints

### List Adapters

```bash
GET /api/v1/adapters
```

**Response (200 OK):**

```json
{
    "adapters": [
        {
            "name": "servicenow",
            "type": "servicenow",
            "enabled": true,
            "status": "connected",
            "last_sync": "2024-01-15T10:00:00Z",
            "total_tickets": 35000
        },
        {
            "name": "jira",
            "type": "jira",
            "enabled": true,
            "status": "connected",
            "last_sync": "2024-01-15T10:05:00Z",
            "total_tickets": 10210
        }
    ]
}
```

### Test Adapter Connection

```bash
POST /api/v1/adapters/{adapter_name}/test
```

**Response (200 OK):**

```json
{
    "adapter": "servicenow",
    "status": "success",
    "response_time_ms": 245,
    "details": {
        "authentication": "valid",
        "api_accessible": true,
        "tables_accessible": ["incident", "change_request", "problem"],
        "rate_limit_remaining": 9850
    }
}
```

---

## Report Endpoints

### Generate Report

```bash
POST /api/v1/reports/generate
```

**Request Body:**

```json
{
    "name": "Weekly IT Summary",
    "period": "7d",
    "format": "html",
    "sections": [
        {"type": "summary", "title": "Overview"},
        {"type": "trends", "title": "Volume Trends"},
        {"type": "categories", "title": "Category Breakdown"},
        {"type": "performance", "title": "Team Performance"},
        {"type": "anomalies", "title": "Anomalies Detected"},
        {"type": "top_tickets", "title": "Notable Tickets"}
    ]
}
```

**Response (202 Accepted):**

```json
{
    "report_id": "rpt_20240115_weekly",
    "status": "generating",
    "estimated_time_seconds": 10
}
```

### Download Report

```bash
GET /api/v1/reports/{report_id}/download
```

Downloads a generated report. The `Content-Type` header varies based on format.

### List Reports

```bash
GET /api/v1/reports
```

**Response (200 OK):**

```json
{
    "reports": [
        {
            "id": "rpt_20240115_weekly",
            "name": "Weekly IT Summary",
            "period": "7d",
            "format": "html",
            "status": "completed",
            "generated_at": "2024-01-15T10:30:00Z",
            "file_size_kb": 245,
            "download_url": "/api/v1/reports/rpt_20240115_weekly/download"
        }
    ]
}
```

---

## Websocket Events

TicketInsight Pro supports WebSocket connections for real-time updates.

### Connect

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`[${data.type}]`, data.payload);
};
```

### Event Types

| Event | Description | Payload |
|-------|-------------|---------|
| `sync.completed` | Adapter sync finished | `{adapter, tickets_fetched, tickets_created}` |
| `sync.failed` | Adapter sync failed | `{adapter, error}` |
| `ticket.new` | New ticket ingested | `{ticket_id, title, category, priority}` |
| `ticket.updated` | Ticket data updated | `{ticket_id, changes}` |
| `analysis.completed` | NLP analysis completed | `{ticket_id, results}` |
| `anomaly.detected` | New anomaly detected | `{anomaly_id, type, severity}` |
| `alert.triggered` | Alert rule triggered | `{alert_id, rule_name, severity}` |
| `model.retrained` | Model retraining completed | `{model_id, accuracy}` |

---

## Error Codes

All error responses follow a consistent format:

```json
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable description",
        "details": {},
        "request_id": "req_abc123",
        "timestamp": "2024-01-15T10:30:00Z"
    }
}
```

### Complete Error Code Reference

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_REQUIRED` | 401 | Authentication is required |
| `AUTH_INVALID_CREDENTIALS` | 401 | Invalid username or password |
| `AUTH_TOKEN_EXPIRED` | 401 | JWT token has expired |
| `AUTH_INVALID_TOKEN` | 401 | JWT token is malformed or invalid |
| `FORBIDDEN` | 403 | Insufficient permissions for this action |
| `TICKET_NOT_FOUND` | 404 | Ticket with specified ID not found |
| `RESOURCE_NOT_FOUND` | 404 | Requested resource does not exist |
| `VALIDATION_ERROR` | 422 | Request body or parameters are invalid |
| `ADAPTER_ERROR` | 502 | External adapter connection or processing error |
| `ADAPTER_NOT_CONFIGURED` | 400 | Requested adapter is not configured |
| `ADAPTER_CONNECTION_FAILED` | 502 | Cannot connect to external system |
| `SYNC_ALREADY_RUNNING` | 409 | A sync is already in progress for this adapter |
| `MODEL_ERROR` | 500 | ML/NLP model processing error |
| `MODEL_NOT_TRAINED` | 500 | Required model has not been trained |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
| `DATABASE_ERROR` | 500 | Database operation failed |
| `CONFIGURATION_ERROR` | 500 | Server configuration issue |

---

## Rate Limiting

API requests are rate-limited to ensure fair usage and system stability.

| Plan | Requests/Minute | Burst | Concurrent |
|------|----------------|-------|------------|
| **Default** | 60 | 10 | 5 |
| **API Key (Admin)** | 120 | 20 | 10 |

Rate limit headers are included in every response:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
X-RateLimit-Reset: 1642245060
Retry-After: 30  (only present when rate limited)
```

When rate limited, the API returns:

```json
{
    "error": {
        "code": "RATE_LIMIT_EXCEEDED",
        "message": "Rate limit exceeded. Retry after 30 seconds.",
        "retry_after_seconds": 30
    }
}
```

---

## SDK Examples

### Python

```python
import requests

class TicketInsightClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'X-API-Key': api_key,
            'Content-Type': 'application/json',
        })

    def health(self) -> dict:
        return self.session.get(f'{self.base_url}/health').json()

    def get_tickets(self, **filters) -> dict:
        return self.session.get(
            f'{self.base_url}/api/v1/tickets',
            params=filters
        ).json()

    def categorize(self, text: str) -> dict:
        return self.session.post(
            f'{self.base_url}/api/v1/nlp/categorize',
            json={'text': text}
        ).json()

    def get_summary(self, period: str = '30d') -> dict:
        return self.session.get(
            f'{self.base_url}/api/v1/analytics/summary',
            params={'period': period}
        ).json()

    def trigger_sync(self, adapter: str) -> dict:
        return self.session.post(
            f'{self.base_url}/api/v1/sync/{adapter}'
        ).json()

# Usage
client = TicketInsightClient(
    base_url='http://localhost:8000',
    api_key='tkp_admin_your_key_here'
)

print(client.health())
print(client.get_summary(period='7d'))
print(client.categorize('My laptop will not turn on'))
```

### JavaScript

```javascript
class TicketInsightClient {
    constructor(baseUrl, apiKey) {
        this.baseUrl = baseUrl;
        this.headers = {
            'X-API-Key': apiKey,
            'Content-Type': 'application/json',
        };
    }

    async getTickets(filters = {}) {
        const params = new URLSearchParams(filters);
        const res = await fetch(
            `${this.baseUrl}/api/v1/tickets?${params}`,
            { headers: this.headers }
        );
        return res.json();
    }

    async categorize(text) {
        const res = await fetch(
            `${this.baseUrl}/api/v1/nlp/categorize`,
            {
                method: 'POST',
                headers: this.headers,
                body: JSON.stringify({ text }),
            }
        );
        return res.json();
    }

    async getSummary(period = '30d') {
        const res = await fetch(
            `${this.baseUrl}/api/v1/analytics/summary?period=${period}`,
            { headers: this.headers }
        );
        return res.json();
    }
}

// Usage
const client = new TicketInsightClient(
    'http://localhost:8000',
    'tkp_admin_your_key_here'
);

const summary = await client.getSummary('7d');
console.log(summary);
```

### cURL

```bash
# Set base variables
BASE_URL="http://localhost:8000/api/v1"
API_KEY="tkp_admin_your_key_here"

# Health check
curl -s "$BASE_URL/../health" | jq

# Get ticket summary
curl -s -H "X-API-Key: $API_KEY" \
    "$BASE_URL/analytics/summary?period=7d" | jq

# Categorize text
curl -s -X POST -H "X-API-Key: $API_KEY" \
    "$BASE_URL/nlp/categorize" \
    -d '{"text": "Cannot connect to VPN from home office"}' | jq

# Trigger sync
curl -s -X POST -H "X-API-Key: $API_KEY" \
    "$BASE_URL/sync/servicenow" | jq

# Search tickets
curl -s -X POST -H "X-API-Key: $API_KEY" \
    "$BASE_URL/tickets/search" \
    -d '{"query": "network outage", "filters": {"status": ["open"]}}' | jq
```
