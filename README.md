<div align="center">

# TicketInsight Pro

**Open-Source, Zero-Cost Ticket Analytics Platform for IT Support Teams**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)](https://www.docker.com/)
[![No Paid APIs](https://img.shields.io/badge/Zero_Cost-100%25_Free-success.svg)]()
[![Flask](https://img.shields.io/badge/Flask-Web_Framework-blue)](https://flask.palletsprojects.com/)
[![spaCy](https://img.shields.io/badge/spaCy-NLP-orange)](https://spacy.io/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-green)](https://scikit-learn.org/)

Transform IT support tickets into actionable insights using NLP, Machine Learning, and Analytics.
Supports ServiceNow, Jira, CSV import, REST API integration — no API keys required.
Perfect for help desk analytics, incident management, ticket classification, sentiment analysis, duplicate detection, and trend forecasting.

**Keywords:** ticket analytics, IT support, help desk, incident management, NLP, machine learning, Flask, Python, open source, zero cost, ServiceNow, Jira, CSV, REST API, sentiment analysis, duplicate detection, anomaly detection, root cause analysis, topic modeling, dashboard, reporting.

[Features](#features) • [Quick Start](#quick-start) • [Architecture](#architecture) •
[API Reference](#api-reference) • [Configuration](#configuration) • [Deployment](#deployment]

</div>

---

## Table of Contents

- [Features](#features)
- [NLP/ML Capabilities](#nlpml-capabilities)
- [Supported Ticketing Systems](#supported-ticketing-systems)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Docker Deployment](#docker-deployment)
- [Development](#development)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Features

TicketInsight Pro is a fully self-hosted analytics engine designed for IT operations,
help desk, and support teams who want deep visibility into their ticket data without
paying for expensive SaaS analytics add-ons or proprietary AI features.

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Multi-Source Ingestion** | Pull tickets from ServiceNow, Jira, CSV files, or any REST API with a configurable adapter |
| **NLP Text Analysis** | Automatic categorization, summarization, keyword extraction, and sentiment analysis on ticket descriptions |
| **Duplicate Detection** | ML-powered identification of duplicate or near-duplicate tickets to reduce noise |
| **Anomaly Detection** | Statistical and ML-based anomaly detection on ticket volume, resolution time, and escalation rates |
| **Priority Prediction** | Predict ticket priority at creation time using trained classification models |
| **Assignment Recommendation** | Suggest the best team or agent for new tickets based on historical patterns |
| **Trend Forecasting** | Time-series forecasting of ticket volume and category distribution |
| **Custom Dashboards** | JSON-configurable dashboards with auto-generated charts and KPI cards |
| **Alerting & Webhooks** | Threshold-based alerting with Slack, Teams, email, and generic webhook support |
| **Scheduled Reports** | Cron-based scheduled report generation and delivery |
| **Role-Based Access** | Fine-grained RBAC with API key and JWT authentication |
| **Full REST API** | 22+ RESTful endpoints for programmatic access to every feature |
| **CLI Interface** | Rich command-line interface for automation, scripting, and CI/CD pipelines |
| **Plugin System** | Extend functionality with custom adapters, processors, and output formatters |

### Why TicketInsight Pro?

- **Zero Cost Analytics**: No paid APIs, no cloud dependencies, no per-seat licensing. Everything runs locally or on your own infrastructure for ticket analytics.
- **Privacy First**: Your ticket data never leaves your environment. No data is sent to external services in IT support analytics.
- **Vendor Agnostic**: Works with any ticketing system via adapters including ServiceNow, Jira, Zendesk, CSV files, REST APIs. Not locked into specific platforms.
- **Extensible**: Write custom adapters, processors, or output plugins in Python with a simple interface for machine learning on tickets.
- **Production Ready**: Docker support, health checks, graceful shutdown, structured logging, and comprehensive error handling for enterprise IT operations.
- **Well Documented**: Every endpoint, CLI command, configuration option, and extension point is documented for NLP and ML applications.
- **Advanced Features**: Includes sentiment analysis, duplicate detection, anomaly detection, root cause analysis, topic modeling, priority prediction, assignment recommendation, trend forecasting, and custom dashboards.

**Perfect for:** IT operations, help desk teams, support analytics, incident management, ticket classification, NLP processing, machine learning models, Flask applications, Python projects, open source software.

---

## NLP/ML Capabilities

TicketInsight Pro includes a complete NLP and machine learning pipeline that operates
entirely on-device with no external API calls. All models are lightweight and optimized
for CPU inference.

### 1. Automatic Ticket Categorization

Tickets are automatically classified into categories and subcategories using a
hierarchical text classifier. The system supports both pre-trained categories and
custom category taxonomies defined in your configuration.

```
Input:  "My laptop screen goes black when I close and open the lid"
Output: {
    "category": "Hardware",
    "subcategory": "Display",
    "confidence": 0.94,
    "alternatives": [
        {"category": "Hardware", "subcategory": "Laptop", "confidence": 0.03},
        {"category": "Software", "subcategory": "Graphics Driver", "confidence": 0.02}
    ]
}
```

- Uses TF-IDF + Naive Bayes by default (fast, no GPU required)
- Optional upgrade to sentence-transformer embeddings + gradient boosting
- Supports custom training on your historical ticket data
- Handles multi-label classification (tickets can belong to multiple categories)

### 2. Ticket Summarization

Generates concise summaries of long ticket descriptions and comment threads using
extractive and abstractive summarization techniques.

```
Input:  [500-word ticket description with multiple comment updates]
Output: "User reports intermittent laptop display issues since Windows update.
        Troubleshooting steps taken include driver rollback and BIOS update.
        Issue persists. Hardware replacement recommended."
```

- Extractive mode: Selects the most informative sentences (fast, deterministic)
- Abstractive mode: Generates human-like summaries using transformer models
- Configurable summary length (short, medium, long)
- Batch processing for large ticket backlogs

### 3. Keyword and Entity Extraction

Identifies key terms, named entities, and technical concepts from ticket text.

```json
{
    "keywords": ["laptop", "display", "black screen", "lid close", "Windows update"],
    "entities": {
        "hardware": ["laptop", "screen", "display adapter"],
        "software": ["Windows 11", "graphics driver v31.0"],
        "locations": ["Building A", "Floor 3"],
        "people": ["John Smith", "IT Support Team"]
    },
    "technical_terms": ["hibernate", "lid switch", "display driver", "BIOS"]
}
```

- Customizable entity types for your domain
- Frequency analysis across ticket corpus
- Trending keyword detection (keywords gaining frequency over time)

### 4. Sentiment Analysis

Analyzes the emotional tone of ticket descriptions and comments to identify
frustrated users, escalating situations, or satisfied resolutions.

```json
{
    "sentiment": "negative",
    "score": -0.72,
    "magnitude": 0.85,
    "emotions": {
        "frustration": 0.65,
        "urgency": 0.40,
        "confusion": 0.20,
        "satisfaction": 0.05
    },
    "escalation_risk": "high"
}
```

- Five-class classification: very negative, negative, neutral, positive, very positive
- Emotion sub-categories for nuanced understanding
- Escalation risk scoring based on sentiment trajectory
- Comment-thread sentiment tracking over ticket lifecycle

### 5. Duplicate Detection

Identifies duplicate or near-duplicate tickets to prevent redundant work and
improve reporting accuracy.

```json
{
    "is_duplicate": true,
    "confidence": 0.91,
    "original_ticket": "INC0012345",
    "similarity_score": 0.89,
    "matching_fields": ["description", "category", "affected_user"],
    "recommended_action": "merge"
}
```

- Cosine similarity on TF-IDF or embedding vectors
- Configurable similarity threshold (default: 0.85)
- Field-weighted matching (description weighted higher than subject)
- Time-window filtering (only compare against recent tickets)
- Batch deduplication for historical data cleanup

### 6. Anomaly Detection

Detects unusual patterns in ticket metrics that may indicate emerging issues,
security incidents, or process breakdowns.

```json
{
    "anomalies": [
        {
            "type": "volume_spike",
            "metric": "tickets_created_per_hour",
            "value": 47,
            "expected": 12,
            "deviation": 3.9,
            "severity": "high",
            "description": "Ticket creation rate is 3.9x above normal for this time window",
            "related_categories": ["Network", "Email"]
        }
    ]
}
```

- Statistical methods: Z-score, IQR, STL decomposition
- ML methods: Isolation Forest, One-Class SVM
- Time-series aware: Accounts for daily/weekly seasonality
- Multi-variate: Detects correlated anomalies across metrics
- Configurable sensitivity and alerting thresholds

### 7. Priority Prediction

Predicts the likely priority of a ticket at creation time, enabling proactive
resource allocation and SLA management.

```json
{
    "predicted_priority": "High",
    "confidence": 0.87,
    "probabilities": {
        "Critical": 0.02,
        "High": 0.87,
        "Medium": 0.09,
        "Low": 0.02
    },
    "key_factors": [
        {"feature": "mentions_outage", "weight": 0.35},
        {"feature": "affected_users_count", "weight": 0.28},
        {"feature": "category_network", "weight": 0.22},
        {"feature": "sentiment_score", "weight": 0.15}
    ]
}
```

- Multi-class classification: Critical, High, Medium, Low
- Feature importance explanation for transparency
- Retraining support as priority patterns evolve
- Custom priority schemes supported

### 8. Team Assignment Recommendation

Suggests the optimal team or individual agent for new tickets based on historical
resolution patterns, expertise areas, and current workload.

```json
{
    "recommendations": [
        {
            "team": "Network Operations",
            "confidence": 0.82,
            "reason": "95% resolution rate on similar tickets",
            "avg_resolution_time": "2.3 hours",
            "current_workload": "moderate"
        },
        {
            "team": "Infrastructure",
            "confidence": 0.15,
            "reason": "Secondary expertise in this area",
            "avg_resolution_time": "4.1 hours",
            "current_workload": "high"
        }
    ]
}
```

- Workload-aware recommendations (considers current queue depth)
- Expertise matching based on historical resolution data
- Escalation path suggestions
- Agent-level or team-level recommendations

---

## Supported Ticketing Systems

TicketInsight Pro connects to your existing ticketing systems through a pluggable
adapter architecture. Each adapter handles authentication, data mapping, and
incremental synchronization.

### ServiceNow

```yaml
# config.yaml
adapters:
  servicenow:
    type: servicenow
    instance: "https://yourcompany.service-now.com"
    auth:
      method: basic  # or oauth2
      username: "${SNOW_USER}"
      password: "${SNOW_PASS}"
    tables:
      - incident
      - change_request
      - problem
    fields:
      - number
      - short_description
      - description
      - state
      - priority
      - assignment_group
      - opened_at
      - resolved_at
      - closed_at
      - category
      - subcategory
      - cmdb_ci
    sync:
      incremental: true
      lookback_days: 30
      poll_interval_minutes: 15
    rate_limit:
      requests_per_minute: 100
```

**Features:**
- Full table API support with configurable field selection
- Incremental sync using `sys_updated_on` watermark
- Supports all ServiceNow table types (incidents, changes, problems, RITMs)
- Rate limiting and automatic retry with backoff
- Proxy support for environments with egress restrictions

### Jira

```yaml
adapters:
  jira:
    type: jira
    server: "https://yourcompany.atlassian.net"
    auth:
      method: token  # or basic, api_token
      token: "${JIRA_TOKEN}"
    projects:
      - "IT"
      - "HELPDESK"
      - "INFRA"
    jql_filters:
      - 'issuetype = "IT Help"'
      - 'status != Deleted'
    fields:
      - key
      - summary
      - description
      - status
      - priority
      - assignee
      - reporter
      - created
      - updated
      - resolved
      - labels
      - components
    sync:
      incremental: true
      poll_interval_minutes: 10
    rate_limit:
      requests_per_minute: 50
```

**Features:**
- JQL query support for flexible filtering
- Multi-project aggregation
- Custom field mapping
- Transition history tracking
- Sprint/epic link resolution
- Attachment metadata extraction

### CSV Import

```yaml
adapters:
  csv_import:
    type: csv
    path: "/data/tickets/"
    file_pattern: "*.csv"
    encoding: "utf-8"
    delimiter: ","
    field_mapping:
      ticket_id: "Ticket ID"
      title: "Subject"
      description: "Description"
      status: "Status"
      priority: "Priority"
      category: "Category"
      created_at: "Created Date"
      resolved_at: "Resolved Date"
      assigned_to: "Assignee"
    date_format: "%Y-%m-%d %H:%M:%S"
    watch: true  # Auto-import new files
```

**Features:**
- Automatic field mapping with column name detection
- Multiple date format support
- Encoding detection (UTF-8, Latin-1, Windows-1252)
- File watching for continuous import
- Batch processing for large files (100k+ rows)
- Validation and error reporting with row-level detail

### Universal REST Adapter

```yaml
adapters:
  custom_system:
    type: rest
    base_url: "https://api.yourcompany.com/tickets"
    auth:
      method: bearer
      token: "${CUSTOM_API_TOKEN}"
    endpoints:
      list: "/api/v1/tickets"
      detail: "/api/v1/tickets/{id}"
      comments: "/api/v1/tickets/{id}/comments"
    pagination:
      type: cursor  # or offset, link_header
      page_param: "cursor"
      size_param: "limit"
      page_size: 100
    response_mapping:
      results_path: "data.items"
      total_path: "data.total"
      id_field: "id"
      field_map:
        ticket_id: "id"
        title: "subject"
        description: "body"
        status: "state"
        created_at: "created_timestamp"
    sync:
      incremental: true
      watermark_field: "updated_at"
      poll_interval_minutes: 30
```

**Features:**
- Works with any REST API — no vendor lock-in
- Configurable pagination strategies (offset, cursor, link header)
- Response path mapping for any JSON structure
- Custom header support
- Webhook receiver for push-based sync

---

## Quick Start

Get TicketInsight Pro running in under 5 minutes with Docker.

### Prerequisites

- **Docker** 20.10+ and Docker Compose 2.0+ (recommended)
- **OR** Python 3.9+ with pip

### Option 1: Docker (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/yourorg/ticketinsight-pro.git
cd ticketinsight-pro

# 2. Copy the example configuration
cp config.example.yaml config.yaml

# 3. Edit the configuration with your ticketing system details
nano config.yaml

# 4. Start the platform
docker compose up -d

# 5. Verify it's running
curl http://localhost:8000/health
```

Expected response:
```json
{
    "status": "healthy",
    "version": "1.0.0",
    "uptime_seconds": 12.4,
    "components": {
        "database": "connected",
        "ml_engine": "loaded",
        "adapters": {
            "servicenow": "configured",
            "csv_import": "configured"
        }
    }
}
```

### Option 2: Python (Development)

```bash
# 1. Clone the repository
git clone https://github.com/yourorg/ticketinsight-pro.git
cd ticketinsight-pro

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Copy and edit configuration
cp config.example.yaml config.yaml
nano config.yaml

# 5. Initialize the database
ticketinsight db init

# 6. Start the server
ticketinsight serve --host 0.0.0.0 --port 8000

# 7. In another terminal, trigger initial data sync
ticketinsight sync --all
```

### Option 3: CSV Quick Start (No Backend Required)

If you just want to analyze a CSV file without connecting to a ticketing system:

```bash
# 1. Install
pip install ticketinsight-pro

# 2. Analyze a CSV file directly
ticketinsight analyze tickets.csv \
    --title-col "Subject" \
    --desc-col "Description" \
    --date-col "Created Date" \
    --output report/

# 3. View the results
ls report/
# categories.json  duplicates.json  sentiment.json  trends.json  summary.html
```

### Your First API Call

Once the server is running, try these commands:

```bash
# Check system health
curl http://localhost:8000/health

# View available adapters
curl http://localhost:8000/api/v1/adapters | jq

# Trigger a sync
curl -X POST http://localhost:8000/api/v1/sync/servicenow

# Get ticket statistics
curl http://localhost:8000/api/v1/analytics/summary?period=30d | jq

# Categorize a ticket
curl -X POST http://localhost:8000/api/v1/nlp/categorize \
    -H "Content-Type: application/json" \
    -d '{"text": "My laptop screen is flickering after the latest update"}' | jq

# Detect duplicates
curl -X POST http://localhost:8000/api/v1/nlp/duplicates \
    -H "Content-Type: application/json" \
    -d '{"ticket_id": "INC0012345"}' | jq

# Get dashboard data
curl http://localhost:8000/api/v1/dashboards/default | jq
```

---

## Architecture

TicketInsight Pro follows a **six-layer pipeline architecture** designed for
reliability, extensibility, and performance.

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                           │
│   REST API  │  CLI  │  Web UI  │  Scheduled Jobs  │  Webhooks  │
├─────────────────────────────────────────────────────────────────┤
│                    ANALYTICS LAYER                              │
│   Dashboards  │  Reports  │  Alerts  │  KPI Engine  │  Export  │
├─────────────────────────────────────────────────────────────────┤
│                    ML / NLP LAYER                               │
│   Categorizer  │  Summarizer  │  Detector  │  Predictor  │     │
│   Sentiment    │  Dedup       │  Embeddings │  Models     │     │
├─────────────────────────────────────────────────────────────────┤
│                    PROCESSING LAYER                             │
│   Pipeline Orchestrator  │  ETL  │  Batch Processor  │        │
│   Task Queue  │  Job Scheduler  │  Error Handler       │        │
├─────────────────────────────────────────────────────────────────┤
│                    DATA LAYER                                   │
│   SQLite/PostgreSQL  │  Ticket Store  │  Model Store  │ Cache  │
├─────────────────────────────────────────────────────────────────┤
│                    INGESTION LAYER                              │
│   ServiceNow Adapter  │  Jira Adapter  │  CSV Adapter  │       │
│   REST Adapter  │  Webhook Receiver  │  File Watcher   │       │
└─────────────────────────────────────────────────────────────────┘
```

### Layer Details

| Layer | Components | Technology |
|-------|-----------|------------|
| **Presentation** | REST API, CLI, Web UI, Webhooks | FastAPI, Typer, Jinja2 |
| **Analytics** | Dashboards, Reports, Alerts, KPIs | Pandas, Plotly, Jinja2 |
| **ML/NLP** | NLP pipeline, ML models, embeddings | scikit-learn, spaCy, NLTK |
| **Processing** | Pipeline orchestrator, task queue | APScheduler, asyncio |
| **Data** | Database, cache, model storage | SQLite/PostgreSQL, Redis |
| **Ingestion** | Adapters, sync engine, file watcher | HTTP clients, watchdog |

### Data Flow

```
[External System] → [Adapter] → [Raw Ticket Store] → [ETL Pipeline]
                                                       ↓
                                              [Processed Ticket Store]
                                                       ↓
                              ┌────────────────────────┼────────────────────────┐
                              ↓                        ↓                        ↓
                     [NLP Pipeline]            [ML Pipeline]             [Analytics Engine]
                              ↓                        ↓                        ↓
                     [Enriched Data]            [Predictions]             [Aggregations]
                              └────────────────────────┼────────────────────────┘
                                                       ↓
                                              [Dashboard/Report/API]
```

For detailed architecture documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## API Reference

The TicketInsight Pro API follows RESTful conventions with JSON request/response
bodies. All endpoints are prefixed with `/api/v1`.

### Authentication

```bash
# Using API key in header
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/tickets

# Using JWT token (after login)
curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": "changeme"}'
# Response: {"access_token": "eyJ...", "refresh_token": "eyJ..."}
```

### Base URL

```
Production:  https://your-domain.com/api/v1
Development: http://localhost:8000/api/v1
```

### Endpoint Categories

| Category | Prefix | Description |
|----------|--------|-------------|
| **Authentication** | `/api/v1/auth` | Login, token refresh, user management |
| **Tickets** | `/api/v1/tickets` | CRUD operations on ticket data |
| **Analytics** | `/api/v1/analytics` | Statistical summaries and aggregations |
| **NLP** | `/api/v1/nlp` | Text analysis and processing |
| **ML** | `/api/v1/ml` | Machine learning predictions |
| **Sync** | `/api/v1/sync` | Data synchronization triggers |
| **Dashboards** | `/api/v1/dashboards` | Dashboard configuration and data |
| **Alerts** | `/api/v1/alerts` | Alert rules and notifications |
| **Adapters** | `/api/v1/adapters` | Adapter management |
| **System** | `/api/v1/system` | Health, config, and admin |

### Core Endpoints

#### Tickets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/tickets` | List tickets with filtering and pagination |
| `GET` | `/tickets/{id}` | Get ticket by ID |
| `GET` | `/tickets/{id}/comments` | Get ticket comments/thread |
| `GET` | `/tickets/{id}/timeline` | Get ticket lifecycle timeline |
| `POST` | `/tickets/search` | Advanced search with full-text query |
| `DELETE` | `/tickets/{id}` | Remove a ticket from the local store |

#### Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/analytics/summary` | Overall ticket summary (KPIs) |
| `GET` | `/analytics/trends` | Time-series trend data |
| `GET` | `/analytics/categories` | Category distribution analysis |
| `GET` | `/analytics/performance` | Team and agent performance metrics |
| `GET` | `/analytics/sla` | SLA compliance reporting |
| `GET` | `/analytics/anomalies` | Detected anomalies |

#### NLP

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/nlp/categorize` | Classify ticket text into categories |
| `POST` | `/nlp/summarize` | Generate ticket summary |
| `POST` | `/nlp/sentiment` | Analyze sentiment of ticket text |
| `POST` | `/nlp/keywords` | Extract keywords and entities |
| `POST` | `/nlp/duplicates` | Find duplicate tickets |
| `POST` | `/nlp/batch` | Batch NLP processing |

#### ML

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ml/predict-priority` | Predict ticket priority |
| `POST` | `/ml/recommend-assignee` | Recommend team/agent assignment |
| `POST` | `/ml/forecast` | Forecast ticket volumes |
| `GET` | `/ml/models` | List trained models |
| `POST` | `/ml/models/{id}/retrain` | Retrain a specific model |

#### Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sync/{adapter_name}` | Trigger sync for a specific adapter |
| `POST` | `/sync/all` | Trigger sync for all configured adapters |
| `GET` | `/sync/{adapter_name}/status` | Get sync status and history |
| `GET` | `/sync/{adapter_name}/logs` | Get sync execution logs |

For the complete API reference with request/response examples, see
[docs/API_REFERENCE.md](docs/API_REFERENCE.md).

---

## CLI Reference

The CLI provides full access to all TicketInsight Pro features from the command line.

### Installation

```bash
pip install ticketinsight-pro
```

### Global Options

```
ticketinsight [OPTIONS] COMMAND [ARGS]

Options:
  --config PATH    Path to config file (default: config.yaml)
  --verbose, -v    Enable verbose output
  --quiet, -q      Suppress non-error output
  --format TEXT    Output format: json, table, yaml (default: table)
  --help           Show this message and exit
```

### Commands

#### `ticketinsight serve`

Start the API server.

```bash
ticketinsight serve --host 0.0.0.0 --port 8000 --workers 4
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8000` | Bind port |
| `--workers` | `1` | Number of worker processes |
| `--reload` | `false` | Enable auto-reload for development |
| `--ssl-keyfile` | - | Path to SSL key file |
| `--ssl-certfile` | - | Path to SSL certificate file |

#### `ticketinsight sync`

Synchronize data from configured adapters.

```bash
# Sync all adapters
ticketinsight sync --all

# Sync a specific adapter
ticketinsight sync servicenow

# Sync with options
ticketinsight sync --adapter jira --full --verbose
```

| Option | Default | Description |
|--------|---------|-------------|
| `--adapter` | - | Specific adapter to sync |
| `--all` | `false` | Sync all adapters |
| `--full` | `false` | Full sync (ignore incremental watermark) |
| `--dry-run` | `false` | Preview changes without applying |

#### `ticketinsight analyze`

Run NLP and ML analysis on ticket data.

```bash
# Analyze all unprocessed tickets
ticketinsight analyze --all

# Analyze specific tickets
ticketinsight analyze --ticket-ids INC001,INC002,INC003

# Analyze from CSV file
ticketinsight analyze tickets.csv --output report/
```

| Option | Default | Description |
|--------|---------|-------------|
| `--all` | `false` | Analyze all tickets |
| `--ticket-ids` | - | Comma-separated ticket IDs |
| `--category` | - | Filter by category |
| `--date-from` | - | Start date (YYYY-MM-DD) |
| `--date-to` | - | End date (YYYY-MM-DD) |
| `--output` | - | Output directory for reports |
| `--format` | `json` | Output format (json, csv, html) |

#### `ticketinsight report`

Generate and export reports.

```bash
# Generate weekly summary report
ticketinsight report weekly --output reports/weekly.pdf

# Generate custom report
ticketinsight report custom \
    --period 30d \
    --include categories,trends,anomalies \
    --format html \
    --output reports/monthly.html
```

#### `ticketinsight db`

Database management commands.

```bash
# Initialize the database
ticketinsight db init

# Run migrations
ticketinsight db migrate

# Check database status
ticketinsight db status

# Backup database
ticketinsight db backup --output backups/db_backup.sql

# Reset database (WARNING: deletes all data)
ticketinsight db reset --confirm
```

#### `ticketinsight model`

Machine learning model management.

```bash
# List trained models
ticketinsight model list

# Train a new model
ticketinsight model train --type categorizer --data tickets.csv

# Evaluate model performance
ticketinsight model evaluate --model categorizer_v2

# Export model for deployment
ticketinsight model export --model categorizer_v2 --output models/
```

#### `ticketinsight adapter`

Adapter management commands.

```bash
# List configured adapters
ticketinsight adapter list

# Test adapter connection
ticketinsight adapter test servicenow

# Show adapter status
ticketinsight adapter status --all
```

#### `ticketinsight config`

Configuration management.

```bash
# Validate current configuration
ticketinsight config validate

# Show current configuration (secrets redacted)
ticketinsight config show

# Generate example configuration
ticketinsight config generate > config.yaml
```

---

## Configuration

TicketInsight Pro uses a single YAML configuration file (`config.yaml` by default)
for all settings. Configuration can also be provided via environment variables.

### Configuration File Structure

```yaml
# ─── Server ───────────────────────────────────────────────────────
server:
  host: "0.0.0.0"
  port: 8000
  workers: 2
  debug: false
  cors_origins:
    - "http://localhost:3000"
    - "https://your-domain.com"
  rate_limiting:
    enabled: true
    requests_per_minute: 60
    burst: 10

# ─── Authentication ──────────────────────────────────────────────
auth:
  method: api_key          # api_key or jwt
  api_keys:
    admin: "${ADMIN_API_KEY}"
    readonly: "${READONLY_API_KEY}"
  jwt:
    secret_key: "${JWT_SECRET}"
    algorithm: HS256
    access_token_expire_minutes: 30
    refresh_token_expire_days: 7
  users:
    - username: admin
      password: "${ADMIN_PASSWORD}"
      role: admin
    - username: analyst
      password: "${ANALYST_PASSWORD}"
      role: analyst

# ─── Database ─────────────────────────────────────────────────────
database:
  type: sqlite             # sqlite or postgresql
  sqlite:
    path: "./data/ticketinsight.db"
  postgresql:
    host: "${DB_HOST}"
    port: 5432
    database: ticketinsight
    username: "${DB_USER}"
    password: "${DB_PASSWORD}"
    ssl_mode: require
    pool_size: 10
    max_overflow: 20

# ─── Cache ────────────────────────────────────────────────────────
cache:
  enabled: true
  type: memory             # memory or redis
  redis:
    url: "${REDIS_URL}"
    ttl_seconds: 3600
  memory:
    max_size: 1000
    ttl_seconds: 1800

# ─── Adapters ─────────────────────────────────────────────────────
adapters:
  servicenow:
    type: servicenow
    enabled: true
    instance: "${SNOW_INSTANCE}"
    auth:
      method: basic
      username: "${SNOW_USER}"
      password: "${SNOW_PASS}"
    # ... (see Supported Ticketing Systems section)

# ─── NLP Pipeline ────────────────────────────────────────────────
nlp:
  categorizer:
    model: tfidf_nb        # tfidf_nb or transformer
    language: en
    custom_categories: []
    confidence_threshold: 0.6
  summarizer:
    mode: extractive       # extractive or abstractive
    max_sentences: 3
  sentiment:
    model: default
    include_emotions: true
  duplicate_detector:
    similarity_threshold: 0.85
    time_window_days: 7
    model: tfidf           # tfidf or embedding
  keyword_extractor:
    max_keywords: 15
    method: rake           # rake, tfidf, yake

# ─── ML Pipeline ─────────────────────────────────────────────────
ml:
  priority_predictor:
    enabled: true
    model: gradient_boosting
    retraining_interval_days: 7
    min_samples_for_training: 500
  assignee_recommender:
    enabled: true
    consider_workload: true
    fallback_strategy: round_robin
  forecaster:
    enabled: true
    model: prophet          # prophet, arima, holtwinters
    forecast_horizon_days: 14
    confidence_interval: 0.95
  anomaly_detector:
    enabled: true
    methods:
      - zscore
      - isolation_forest
    sensitivity: medium    # low, medium, high
    seasonality: weekly

# ─── Analytics ────────────────────────────────────────────────────
analytics:
  default_period: 30d
  timezones:
    - America/New_York
    - Europe/London
  business_hours:
    start: "09:00"
    end: "17:00"
    days: monday-friday
  sla_definitions:
    - name: "Critical"
      response_minutes: 15
      resolution_hours: 4
    - name: "High"
      response_minutes: 30
      resolution_hours: 8
    - name: "Medium"
      response_minutes: 120
      resolution_hours: 24
    - name: "Low"
      response_minutes: 480
      resolution_hours: 72

# ─── Dashboards ──────────────────────────────────────────────────
dashboards:
  default_layout:
    - type: kpi_card
      title: "Open Tickets"
      metric: tickets_open_count
    - type: kpi_card
      title: "Avg Resolution Time"
      metric: avg_resolution_time_hours
    - type: time_series
      title: "Ticket Volume Trend"
      metric: tickets_created_per_day
    - type: bar_chart
      title: "Tickets by Category"
      metric: category_distribution
    - type: pie_chart
      title: "Priority Distribution"
      metric: priority_distribution

# ─── Alerts ───────────────────────────────────────────────────────
alerts:
  enabled: true
  rules:
    - name: "Volume Spike"
      condition: "tickets_created_per_hour > 2 * baseline"
      severity: high
      channels:
        - type: slack
          webhook_url: "${SLACK_WEBHOOK}"
        - type: email
          to: "it-ops@company.com"
    - name: "SLA Breach Risk"
      condition: "tickets_at_risk_of_sla_breach > 0"
      severity: medium
      channels:
        - type: teams
          webhook_url: "${TEAMS_WEBHOOK}"
  channels:
    slack:
      webhook_url: "${SLACK_WEBHOOK}"
      mention_users: true
    teams:
      webhook_url: "${TEAMS_WEBHOOK}"
    email:
      smtp_host: "${SMTP_HOST}"
      smtp_port: 587
      smtp_user: "${SMTP_USER}"
      smtp_pass: "${SMTP_PASS}"
      from_address: "ticketinsight@company.com"

# ─── Reports ──────────────────────────────────────────────────────
reports:
  scheduled:
    - name: "Daily Summary"
      cron: "0 9 * * MON-FRI"
      period: 1d
      format: html
      output: "./reports/daily/"
      recipients:
        - type: email
          to: "it-managers@company.com"
    - name: "Weekly Report"
      cron: "0 8 * * MON"
      period: 7d
      format: pdf
      output: "./reports/weekly/"
      recipients:
        - type: email
          to: "it-directors@company.com"

# ─── Logging ──────────────────────────────────────────────────────
logging:
  level: INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: json             # json or text
  output: stdout           # stdout, file, both
  file:
    path: "./logs/ticketinsight.log"
    max_size_mb: 100
    backup_count: 5
  sensitive_fields:
    - password
    - token
    - api_key
    - secret

# ─── Sync ─────────────────────────────────────────────────────────
sync:
  schedule:
    enabled: true
    interval_minutes: 15
  retry:
    max_attempts: 3
    backoff_seconds: 30
  batch_size: 500
  concurrent_adapters: 3
```

### Environment Variables

All values prefixed with `${}` in the config are resolved from environment variables.
You can also override any config key using the `TIP_` prefix:

```bash
# Override database type
export TIP_DATABASE__TYPE=postgresql

# Override server port
export TIP_SERVER__PORT=9000

# Set API key directly
export TIP_AUTH__API_KEYS__ADMIN=my-secret-key
```

### Configuration Validation

```bash
# Validate configuration without starting the server
ticketinsight config validate

# Show resolved configuration (secrets redacted)
ticketinsight config show
```

---

## Docker Deployment

### Quick Start with Docker Compose

```bash
# Clone and configure
git clone https://github.com/yourorg/ticketinsight-pro.git
cd ticketinsight-pro
cp config.example.yaml config.yaml
nano config.yaml

# Start all services
docker compose up -d

# View logs
docker compose logs -f ticketinsight

# Stop
docker compose down
```

### Docker Compose (Full Stack)

```yaml
# docker-compose.yml
version: '3.8'

services:
  ticketinsight:
    image: ticketinsight/ticketinsight-pro:latest
    container_name: ticketinsight-pro
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data
      - ./reports:/app/reports
      - ./logs:/app/logs
      - ./models:/app/models
    environment:
      - TIP_DATABASE__TYPE=postgresql
      - TIP_DATABASE__POSTGRESQL__HOST=db
      - TIP_DATABASE__POSTGRESQL__PASSWORD=${DB_PASSWORD}
      - TIP_CACHE__TYPE=redis
      - TIP_CACHE__REDIS__URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 512M
          cpus: '0.5'

  db:
    image: postgres:15-alpine
    container_name: ticketinsight-db
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ticketinsight
      POSTGRES_USER: tip
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tip -d ticketinsight"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: ticketinsight-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

### Environment File

```bash
# .env
DB_PASSWORD=change_me_please_use_a_long_random_string
ADMIN_API_KEY=tkp_admin_xxxxxxxxxxxxxxxxxxxx
READONLY_API_KEY=tkp_readonly_xxxxxxxxxxxxxxxx
JWT_SECRET=change_me_to_a_random_64_char_string
ADMIN_PASSWORD=changeme_on_first_login
ANALYST_PASSWORD=changeme_on_first_login
SNOW_INSTANCE=https://yourcompany.service-now.com
SNOW_USER=api_user
SNOW_PASS=api_password
JIRA_TOKEN=your_jira_api_token
SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
TEAMS_WEBHOOK=https://yourcompany.webhook.office.com/webhook/XXX
SMTP_HOST=smtp.company.com
SMTP_USER=noreply@company.com
SMTP_PASS=smtp_password
REDIS_URL=redis://redis:6379/0
```

### Building from Source

```bash
# Build the Docker image
docker build -t ticketinsight/ticketinsight-pro:latest .

# Build with a specific version tag
docker build -t ticketinsight/ticketinsight-pro:v1.0.0 .

# Run with custom configuration
docker run -d \
    --name ticketinsight-pro \
    -p 8000:8000 \
    -v ./config.yaml:/app/config.yaml:ro \
    -v ./data:/app/data \
    ticketinsight/ticketinsight-pro:latest
```

### Dockerfile

```dockerfile
FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 tip && chown -R tip:tip /app
USER tip

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["ticketinsight", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

For comprehensive deployment instructions including Kubernetes, systemd,
reverse proxy setup, and production hardening, see
[docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md).

---

## Development

### Setting Up the Development Environment

```bash
# Clone the repository
git clone https://github.com/yourorg/ticketinsight-pro.git
cd ticketinsight-pro

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with development dependencies
pip install -e ".[dev]"

# Copy and configure
cp config.example.yaml config.yaml

# Initialize database
ticketinsight db init

# Run tests
pytest

# Start development server with auto-reload
ticketinsight serve --reload
```

### Project Structure

```
ticketinsight-pro/
├── config.example.yaml          # Example configuration
├── config.yaml                  # Active configuration (gitignored)
├── docker-compose.yml           # Docker Compose configuration
├── Dockerfile                   # Docker build file
├── pyproject.toml               # Python project metadata
├── requirements.txt             # Python dependencies
├── setup.py                     # Package setup
├── Makefile                     # Build automation
├── README.md                    # This file
├── docs/
│   ├── ARCHITECTURE.md          # Architecture documentation
│   ├── API_REFERENCE.md         # Complete API reference
│   ├── DEPLOYMENT_GUIDE.md      # Deployment instructions
│   ├── CONTRIBUTING.md          # Contributing guidelines
│   ├── CHANGELOG.md             # Version changelog
│   └── ADAPTER_GUIDE.md         # Adapter development guide
├── src/
│   └── ticketinsight/
│       ├── __init__.py
│       ├── app.py               # FastAPI application
│       ├── config.py            # Configuration management
│       ├── database.py          # Database connection and models
│       ├── api/                 # API route handlers
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   ├── tickets.py
│       │   ├── analytics.py
│       │   ├── nlp.py
│       │   ├── ml.py
│       │   ├── sync.py
│       │   ├── dashboards.py
│       │   ├── alerts.py
│       │   ├── adapters.py
│       │   └── system.py
│       ├── adapters/            # Data source adapters
│       │   ├── __init__.py
│       │   ├── base.py          # Abstract adapter interface
│       │   ├── servicenow.py
│       │   ├── jira.py
│       │   ├── csv_adapter.py
│       │   └── rest_adapter.py
│       ├── nlp/                 # NLP pipeline components
│       │   ├── __init__.py
│       │   ├── categorizer.py
│       │   ├── summarizer.py
│       │   ├── sentiment.py
│       │   ├── keywords.py
│       │   ├── dedup.py
│       │   └── pipeline.py
│       ├── ml/                  # Machine learning models
│       │   ├── __init__.py
│       │   ├── priority.py
│       │   ├── assignee.py
│       │   ├── forecaster.py
│       │   ├── anomaly.py
│       │   └── trainer.py
│       ├── analytics/           # Analytics engine
│       │   ├── __init__.py
│       │   ├── aggregator.py
│       │   ├── trends.py
│       │   ├── sla.py
│       │   └── kpi.py
│       ├── processing/          # Pipeline orchestration
│       │   ├── __init__.py
│       │   ├── orchestrator.py
│       │   ├── scheduler.py
│       │   └── tasks.py
│       ├── models/              # Database ORM models
│       │   ├── __init__.py
│       │   ├── ticket.py
│       │   ├── sync_log.py
│       │   ├── analysis.py
│       │   └── user.py
│       ├── utils/               # Shared utilities
│       │   ├── __init__.py
│       │   ├── logging.py
│       │   ├── auth.py
│       │   ├── cache.py
│       │   └── dates.py
│       └── cli/                 # CLI interface
│           ├── __init__.py
│           └── commands.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api/
│   ├── test_nlp/
│   ├── test_ml/
│   ├── test_adapters/
│   └── test_analytics/
├── data/                        # Local data directory (gitignored)
│   ├── ticketinsight.db
│   └── models/
├── logs/                        # Log files (gitignored)
└── reports/                     # Generated reports (gitignored)
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/ticketinsight --cov-report=html

# Run specific test category
pytest tests/test_api/
pytest tests/test_nlp/
pytest tests/test_ml/
pytest tests/test_adapters/

# Run with verbose output
pytest -v -s

# Run only failing tests
pytest --lf

# Run tests in parallel
pytest -n auto
```

### Code Quality

```bash
# Lint with ruff
ruff check src/ tests/

# Format with ruff
ruff format src/ tests/

# Type checking with mypy
mypy src/ticketinsight

# Security check with bandit
bandit -r src/ticketinsight

# All checks at once (via Makefile)
make lint
```

### Makefile Targets

```makefile
.PHONY: help install test lint format clean docker

help:           ## Show this help message
install:        ## Install development dependencies
test:           ## Run all tests
lint:           ## Run all linters and type checkers
format:         ## Auto-format code
clean:          ## Remove generated files
docker:         ## Build and run with Docker
migrate:        ## Run database migrations
seed:           ## Seed database with sample data
report:         ## Generate test coverage report
```

---

## Roadmap

### v1.0 (Current)

- [x] Core NLP pipeline (categorization, summarization, sentiment, keywords)
- [x] Duplicate detection
- [x] Priority prediction
- [x] Assignee recommendation
- [x] ServiceNow adapter
- [x] Jira adapter
- [x] CSV import
- [x] Universal REST adapter
- [x] Anomaly detection
- [x] Dashboard engine
- [x] Alert system (Slack, Teams, email)
- [x] Scheduled reports
- [x] CLI interface
- [x] Docker support
- [x] SQLite and PostgreSQL support
- [x] Role-based access control

### v1.1 (Planned)

- [ ] Web UI dashboard with interactive charts
- [ ] Real-time streaming sync (WebSocket-based)
- [ ] Zendesk adapter
- [ ] Freshservice adapter
- [ ] Multi-language NLP support (Spanish, French, German)
- [ ] Custom model training UI
- [ ] Export to PowerPoint and Google Slides
- [ ] Ticket correlation analysis (identify related incidents)

### v1.2 (Planned)

- [ ] Knowledge base article suggestions
- [ ] Auto-resolution detection
- [ ] Customer satisfaction (CSAT) prediction
- [ ] Cost estimation per ticket category
- [ ] Capacity planning recommendations
- [ ] Grafana/Prometheus metrics export
- [ ] SSO integration (SAML, OIDC)

### v2.0 (Future)

- [ ] Distributed processing for large-scale deployments
- [ ] Kubernetes operator for managed deployment
- [ ] Fine-tuned LLM integration for complex analysis
- [ ] Conversational analytics (natural language queries)
- [ ] Multi-tenant architecture for MSPs
- [ ] Marketplace for community adapters and plugins
- [ ] Mobile app for on-the-go insights

---

## Contributing

We welcome contributions from the community! Whether it's a bug fix, a new feature,
documentation improvements, or a new adapter, we'd love to have your help.

### Quick Contribution Guide

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/my-new-feature`)
3. **Commit** your changes with descriptive messages
4. **Push** to your fork (`git push origin feature/my-new-feature`)
5. **Open** a Pull Request with a clear description

### Contribution Areas

| Area | Description | Difficulty |
|------|-------------|------------|
| **Bug Fixes** | Fix issues reported in the issue tracker | Beginner |
| **Documentation** | Improve docs, add examples, fix typos | Beginner |
| **Adapters** | Create adapters for new ticketing systems | Intermediate |
| **NLP Models** | Improve categorization, sentiment, summarization | Advanced |
| **ML Models** | Improve priority prediction, anomaly detection | Advanced |
| **API Endpoints** | Add new API endpoints or improve existing ones | Intermediate |
| **Tests** | Add test coverage for untested code paths | Intermediate |
| **Dashboards** | Create new dashboard templates and widgets | Intermediate |

For detailed contribution guidelines, see [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

---

## Topics & Keywords

**Technologies:** Python, Flask, spaCy, scikit-learn, NLTK, Gensim, Pandas, NumPy, SQLAlchemy, Redis, PostgreSQL, Docker, REST API, Machine Learning, Natural Language Processing.

**Domains:** IT Support, Help Desk, Ticket Analytics, Incident Management, Service Desk, ITSM, IT Operations, Support Analytics, Ticket Classification, Sentiment Analysis, Duplicate Detection, Anomaly Detection, Root Cause Analysis, Topic Modeling, Priority Prediction, Assignment Recommendation, Trend Forecasting, Dashboard, Reporting, Webhooks, Alerts.

**Platforms:** ServiceNow, Jira, Zendesk, CSV Import, REST API, Universal Adapter, Open Source, Zero Cost, Self-Hosted, On-Premise.

**Use Cases:** IT ticket analysis, support team insights, help desk optimization, incident response, customer support analytics, operational intelligence, data visualization, automated reporting.

---

## License

TicketInsight Pro is released under the **MIT License**.

```
MIT License

Copyright (c) 2024 TicketInsight Pro Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

<div align="center">

**Built with purpose. Open by design. Free forever.**

Made with ❤️ by the TicketInsight Pro community

</div>
