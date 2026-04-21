# Architecture

> Comprehensive architectural documentation for TicketInsight Pro.
> This document covers system design decisions, component interactions,
> data models, and extension points.

## Table of Contents

- [Design Philosophy](#design-philosophy)
- [High-Level Architecture](#high-level-architecture)
- [Layer 1: Ingestion](#layer-1-ingestion)
- [Layer 2: Data Storage](#layer-2-data-storage)
- [Layer 3: Processing Pipeline](#layer-3-processing-pipeline)
- [Layer 4: ML/NLP Engine](#layer-4-mlnlp-engine)
- [Layer 5: Analytics Engine](#layer-5-analytics-engine)
- [Layer 6: Presentation](#layer-6-presentation)
- [Data Models](#data-models)
- [Authentication & Authorization](#authentication--authorization)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)
- [Scaling Strategy](#scaling-strategy)
- [Security Architecture](#security-architecture)

---

## Design Philosophy

TicketInsight Pro is built around five core principles that guide every
architectural decision:

### 1. Zero External Dependencies for Core Features

All NLP and ML capabilities run entirely on-device. No data leaves the system.
No API keys are required for core functionality. This ensures privacy, cost
predictability, and operational independence.

### 2. Adapter-Based Extensibility

Every external system integration is implemented as a pluggable adapter behind
a common interface. Adding support for a new ticketing system requires only
implementing the `BaseAdapter` protocol — no changes to core code.

### 3. Pipeline-First Processing

All data flows through a composable pipeline of discrete processing stages.
Each stage is independently testable, configurable, and can be enabled or
disabled without affecting other stages.

### 4. Configuration Over Code

Behavior is controlled through YAML configuration files and environment variables,
not by modifying source code. This makes the system portable, versionable, and
easy to operate across environments.

### 5. Graceful Degradation

The system is designed to continue operating with reduced functionality when
individual components fail. If the ML models are unavailable, the API still
serves cached analytics. If an adapter fails, others continue syncing.

---

## High-Level Architecture

TicketInsight Pro is organized as a six-layer pipeline, where data flows
from external sources through ingestion, storage, processing, intelligence,
analytics, and finally to user-facing interfaces.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                        LAYER 6: PRESENTATION                       │
│                                                                     │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│   │REST API  │ │   CLI    │ │ Web UI   │ │Webhooks  │ │Reports │  │
│   │(FastAPI) │ │ (Typer)  │ │(Jinja2)  │ │(Inbound) │ │(PDF/   │  │
│   │          │ │          │ │          │ │          │ │HTML)   │  │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                        LAYER 5: ANALYTICS                          │
│                                                                     │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│   │Dashboard │ │  KPI     │ │  Trend   │ │   SLA    │ │Export  │  │
│   │  Engine  │ │ Engine   │ │ Engine   │ │ Engine   │ │Engine  │  │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                        LAYER 4: ML / NLP                            │
│                                                                     │
│   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐│
│   │Categ.  │ │Summar. │ │Sentim. │ │Keywd.  │ │Dedup   │ │Anom. ││
│   │Engine  │ │Engine  │ │Engine  │ │Engine  │ │Engine  │ │Detect││
│   └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └──────┘│
│   ┌────────┐ ┌────────┐ ┌────────┐                                 │
│   │Priority│ │Assign. │ │Forecast│                                 │
│   │Predict.│ │Recommend│ │ Engine │                                 │
│   └────────┘ └────────┘ └────────┘                                 │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                     LAYER 3: PROCESSING                            │
│                                                                     │
│   ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│   │  Pipeline    │ │  Task    │ │  Job     │ │   Error          │  │
│   │ Orchestrator │ │  Queue   │ │Scheduler │ │   Handler        │  │
│   └──────────────┘ └──────────┘ └──────────┘ └──────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                       LAYER 2: DATA STORAGE                         │
│                                                                     │
│   ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│   │  Ticket      │ │  Model   │ │  Cache   │ │   File           │  │
│   │  Store       │ │  Store   │ │  Layer   │ │   Store          │  │
│   │ (SQLAlchemy) │ │ (Joblib) │ │ (Redis/  │ │   (Local FS)     │  │
│   │              │ │          │ │  Memory) │ │                  │  │
│   └──────────────┘ └──────────┘ └──────────┘ └──────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                      LAYER 1: INGESTION                             │
│                                                                     │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│   │ServiceNow│ │   Jira   │ │   CSV    │ │  REST    │ │Webhook │  │
│   │ Adapter  │ │ Adapter  │ │ Adapter  │ │ Adapter  │ │Receiver│  │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Cross-Cutting Concerns

These concerns apply across all layers:

| Concern | Implementation |
|---------|---------------|
| **Logging** | Structured JSON logging via Python `logging` with context injection |
| **Configuration** | Centralized YAML config with env var resolution and validation |
| **Authentication** | API key + JWT auth with RBAC middleware |
| **Error Handling** | Layered exception hierarchy with context propagation |
| **Metrics** | Optional Prometheus metrics export for monitoring |
| **Health Checks** | Component-level health probes at `/health` endpoint |

---

## Layer 1: Ingestion

The ingestion layer is responsible for connecting to external data sources,
fetching ticket data, and normalizing it into a unified internal format.

### Adapter Architecture

All adapters implement the `BaseAdapter` protocol, which defines a common
interface for data extraction:

```python
from typing import Protocol, Iterator, Optional
from datetime import datetime

class TicketData:
    """Normalized ticket data structure."""
    ticket_id: str
    title: str
    description: str
    status: str
    priority: str
    category: Optional[str]
    subcategory: Optional[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]
    assigned_to: Optional[str]
    assigned_group: Optional[str]
    reporter: Optional[str]
    tags: list[str]
    custom_fields: dict
    comments: list[CommentData]
    source_system: str
    raw_data: dict

class BaseAdapter(Protocol):
    """Protocol that all adapters must implement."""

    @property
    def name(self) -> str:
        """Unique adapter identifier."""
        ...

    @property
    def source_system(self) -> str:
        """Human-readable source system name."""
        ...

    async def connect(self) -> None:
        """Establish connection to the data source."""
        ...

    async def disconnect(self) -> None:
        """Close connection to the data source."""
        ...

    async def test_connection(self) -> bool:
        """Verify that the adapter can reach the data source."""
        ...

    async def fetch_tickets(
        self,
        since: Optional[datetime] = None,
        limit: int = 500,
        offset: int = 0
    ) -> Iterator[TicketData]:
        """Fetch tickets from the data source."""
        ...

    async def fetch_ticket(self, ticket_id: str) -> TicketData:
        """Fetch a single ticket by its ID."""
        ...

    async def fetch_comments(
        self, ticket_id: str
    ) -> list[CommentData]:
        """Fetch comments for a specific ticket."""
        ...

    async def get_sync_watermark(self) -> Optional[datetime]:
        """Get the timestamp of the last synced record."""
        ...

    async def health_check(self) -> dict:
        """Return adapter health status."""
        ...
```

### Adapter Lifecycle

```
[Config Loaded] → [Adapter Instantiated] → [connect()]
                                            ↓
                                     [fetch_tickets()]
                                            ↓
                                     [Normalize to TicketData]
                                            ↓
                                     [Store in Ticket Store]
                                            ↓
                                     [Update Watermark]
                                            ↓
                                     [disconnect()]
```

### Sync Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **Incremental** | Fetches only records modified since the last sync watermark | Ongoing operation |
| **Full** | Fetches all records regardless of watermark | Initial load, recovery |
| **Polling** | Adapter is called on a schedule (configurable interval) | Most adapters |
| **Push (Webhook)** | External system pushes data via webhook endpoint | Real-time needs |

### Rate Limiting

All adapters implement configurable rate limiting to avoid overwhelming
external systems:

```python
class RateLimiter:
    """Token bucket rate limiter for adapter requests."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst: int = 10
    ):
        self.rate = requests_per_minute / 60.0
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        while self.tokens < 1:
            await asyncio.sleep(self._wait_time())
            self._refill()
        self.tokens -= 1

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(
            self.burst,
            self.tokens + elapsed * self.rate
        )
        self.last_update = now
```

### Built-in Adapters

| Adapter | Auth Methods | Pagination | Incremental Sync | Batch Size |
|---------|-------------|------------|------------------|------------|
| ServiceNow | Basic, OAuth2 | Offset + sysparm | Yes (sys_updated_on) | 10,000 |
| Jira | API Token, Basic | Offset, Cursor | Yes (updated) | 100 |
| CSV | N/A | Chunked file read | File mtime | 5,000 |
| REST | Bearer, Basic, API Key | Offset, Cursor, Link | Yes (configurable) | 100 |

---

## Layer 2: Data Storage

The data layer provides persistent storage for tickets, analysis results,
ML models, and application metadata.

### Database Architecture

TicketInsight Pro supports two database backends:

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| **Deployment** | Zero-config, single file | Requires external service |
| **Concurrency** | Write-locked (WAL mode helps) | Full MVCC concurrency |
| **Scalability** | Up to ~1M tickets | Unlimited |
| **Full-Text Search** | FTS5 extension | pg_trgm + tsvector |
| **JSON Queries** | Limited | Full JSONB support |
| **Recommended For** | Development, small teams, edge | Production, large teams |

### SQLAlchemy Models

```python
# Core ticket model
class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(String(100), unique=True, nullable=False, index=True)
    source_system = Column(String(50), nullable=False, index=True)
    source_adapter = Column(String(50), nullable=False)

    # Ticket content
    title = Column(Text, nullable=False)
    description = Column(Text)
    status = Column(String(50), index=True)
    priority = Column(String(20), index=True)
    category = Column(String(100), index=True)
    subcategory = Column(String(100), index=True)

    # People
    reporter = Column(String(200))
    assigned_to = Column(String(200), index=True)
    assigned_group = Column(String(200), index=True)

    # Timestamps
    source_created_at = Column(DateTime, index=True)
    source_updated_at = Column(DateTime, index=True)
    resolved_at = Column(DateTime)
    closed_at = Column(DateTime)
    ingested_at = Column(DateTime, default=func.now())
    synced_at = Column(DateTime, default=func.now())

    # Tags and metadata
    tags = Column(JSON, default=list)
    custom_fields = Column(JSON, default=dict)
    raw_data = Column(JSON)

    # Relationships
    comments = relationship("Comment", back_populates="ticket")
    analysis = relationship("Analysis", back_populates="ticket", uselist=False)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    author = Column(String(200))
    body = Column(Text, nullable=False)
    source_created_at = Column(DateTime)
    is_internal = Column(Boolean, default=False)

    ticket = relationship("Ticket", back_populates="comments")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), unique=True)

    # NLP results
    predicted_category = Column(String(100))
    predicted_subcategory = Column(String(100))
    category_confidence = Column(Float)
    summary = Column(Text)
    sentiment = Column(String(20))
    sentiment_score = Column(Float)
    keywords = Column(JSON, default=list)
    entities = Column(JSON, default=dict)

    # ML results
    predicted_priority = Column(String(20))
    priority_confidence = Column(Float)
    recommended_assignee = Column(String(200))
    assignee_confidence = Column(Float)
    is_duplicate = Column(Boolean)
    duplicate_of = Column(String(100))
    duplicate_confidence = Column(Float)

    # Metadata
    analyzed_at = Column(DateTime, default=func.now())
    model_version = Column(String(50))

    ticket = relationship("Ticket", back_populates="analysis")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True)
    adapter_name = Column(String(50), nullable=False, index=True)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
    status = Column(String(20))  # running, completed, failed
    tickets_fetched = Column(Integer, default=0)
    tickets_created = Column(Integer, default=0)
    tickets_updated = Column(Integer, default=0)
    error_message = Column(Text)
    duration_seconds = Column(Float)
```

### Indexing Strategy

```sql
-- Primary query patterns and their supporting indexes

-- 1. Ticket lookup by source ID
CREATE INDEX idx_tickets_source_id ON tickets(source_system, ticket_id);

-- 2. Ticket listing with filters
CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_priority ON tickets(priority);
CREATE INDEX idx_tickets_category ON tickets(category);
CREATE INDEX idx_tickets_created ON tickets(source_created_at);

-- 3. Assignment queries
CREATE INDEX idx_tickets_assigned_to ON tickets(assigned_to);
CREATE INDEX idx_tickets_assigned_group ON tickets(assigned_group);

-- 4. Sync watermark queries
CREATE INDEX idx_tickets_sync ON tickets(source_adapter, source_updated_at);

-- 5. Full-text search (PostgreSQL)
CREATE INDEX idx_tickets_fts ON tickets
    USING gin(to_tsvector('english', title || ' ' || COALESCE(description, '')));

-- 6. Analysis result queries
CREATE INDEX idx_analyses_category ON analyses(predicted_category);
CREATE INDEX idx_analyses_sentiment ON analyses(sentiment);
CREATE INDEX idx_analyses_duplicate ON analyses(is_duplicate) WHERE is_duplicate = TRUE;
```

### Cache Layer

The cache layer sits in front of the database for frequently accessed data:

```python
class CacheManager:
    """Manages caching across memory and Redis backends."""

    def __init__(self, config: CacheConfig):
        self.backend = self._create_backend(config)

    async def get(self, key: str) -> Optional[Any]:
        """Get a cached value. Returns None on miss."""

    async def set(self, key: str, value: Any, ttl: int = 1800) -> None:
        """Set a cached value with TTL in seconds."""

    async def invalidate(self, pattern: str) -> int:
        """Invalidate all cache keys matching a pattern."""

    async def warm(self, keys: list[str]) -> None:
        """Pre-populate cache for known hot keys."""
```

Cache is used for:

| Data | TTL | Reason |
|------|-----|--------|
| Dashboard data | 5 minutes | Expensive aggregations |
| Ticket summaries | 30 minutes | NLP results don't change often |
| Category counts | 15 minutes | Aggregate query |
| Adapter health | 1 minute | Frequent polling |
| Model predictions | 10 minutes | Deterministic for same input |

---

## Layer 3: Processing Pipeline

The processing layer orchestrates the flow of data through the system,
managing task scheduling, batch processing, and error recovery.

### Pipeline Architecture

```python
class PipelineOrchestrator:
    """Coordinates the execution of processing pipelines."""

    def __init__(self, config: ProcessingConfig):
        self.stages: list[PipelineStage] = []
        self.error_handler = ErrorHandler()

    def add_stage(self, stage: PipelineStage) -> None:
        """Add a processing stage to the pipeline."""

    async def process(self, ticket: TicketData) -> TicketData:
        """Run a ticket through all pipeline stages."""
        processed = ticket
        for stage in self.stages:
            try:
                processed = await stage.execute(processed)
            except StageError as e:
                await self.error_handler.handle(e, processed, stage)
                if stage.blocking:
                    raise
        return processed

    async def process_batch(
        self, tickets: list[TicketData], batch_size: int = 100
    ) -> BatchResult:
        """Process a batch of tickets with progress tracking."""
```

### Pipeline Stages

```
[Raw Ticket] → [Validator] → [Normalizer] → [Enricher] → [NLP Stage] → [ML Stage] → [Store]
                    │              │              │              │            │           │
                    ▼              ▼              ▼              ▼            ▼           ▼
               Schema check   Field mapping  Geo/lookup    Categorize   Predict     Persist
               Type coerce    Date parsing   Tag cleanup   Summarize    Recommend  Index
               Dedup check    Status map     Resolve IDs   Sentiment    Forecast   Cache
```

### Stage Definitions

```python
class PipelineStage(Protocol):
    """Interface for pipeline processing stages."""

    @property
    def name(self) -> str:
        """Unique stage identifier."""
        ...

    @property
    def blocking(self) -> bool:
        """Whether failure should halt the pipeline."""
        ...

    async def execute(self, ticket: TicketData) -> TicketData:
        """Process a ticket through this stage."""
        ...

    async def health_check(self) -> dict:
        """Return stage health status."""
        ...
```

| Stage | Description | Blocking | Default |
|-------|-------------|----------|---------|
| **Validator** | Validates ticket schema and required fields | Yes | Enabled |
| **Normalizer** | Maps fields, normalizes statuses, parses dates | Yes | Enabled |
| **Deduplicator** | Checks for existing duplicate tickets | No | Enabled |
| **Enricher** | Adds metadata (location, department, CI lookup) | No | Optional |
| **NLPProcessor** | Runs full NLP pipeline (categorize, summarize, etc.) | No | Enabled |
| **MLProcessor** | Runs ML predictions (priority, assignee) | No | Enabled |
| **Persister** | Saves processed ticket to database | Yes | Enabled |
| **CacheWarmer** | Updates cache entries for the ticket | No | Enabled |

### Task Scheduling

```python
class TaskScheduler:
    """Manages scheduled and async tasks."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.task_queue = asyncio.Queue()

    def schedule_periodic(
        self,
        func: Callable,
        interval_minutes: int,
        name: str
    ) -> None:
        """Schedule a function to run at a fixed interval."""

    async def submit_task(
        self,
        func: Callable,
        *args,
        priority: int = 5,
        timeout: int = 300
    ) -> TaskResult:
        """Submit a task for async execution."""

    def register_cron_job(
        self,
        func: Callable,
        cron_expression: str,
        name: str
    ) -> None:
        """Schedule a function using cron expression."""
```

### Built-in Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `sync_all_adapters` | Every 15 min | Sync data from all configured adapters |
| `run_nlp_pipeline` | Every 30 min | Run NLP on unprocessed tickets |
| `run_ml_pipeline` | Every hour | Run ML predictions on analyzed tickets |
| `check_anomalies` | Every 10 min | Run anomaly detection on recent data |
| `generate_daily_report` | Weekdays 9:00 AM | Generate and deliver daily report |
| `cleanup_old_logs` | Daily 2:00 AM | Rotate and clean up old log files |
| `retrain_models` | Weekly Sunday 3:00 AM | Retrain ML models with new data |
| `check_sla_compliance` | Every 30 min | Check for SLA breach risks |

### Error Handling

```python
class ErrorHandler:
    """Centralized error handling with recovery strategies."""

    def __init__(self, config: ErrorConfig):
        self.strategies: dict[type, ErrorStrategy] = {
            ConnectionError: RetryStrategy(max_attempts=3, backoff=30),
            ValidationError: SkipStrategy(log_level="warning"),
            ProcessingError: DeadLetterStrategy(queue="failed_tickets"),
            TimeoutError: RetryStrategy(max_attempts=2, backoff=60),
        }

    async def handle(
        self,
        error: Exception,
        context: dict,
        stage: Optional[PipelineStage] = None
    ) -> ErrorAction:
        """Handle an error and return the appropriate action."""
        strategy = self.strategies.get(type(error), LogStrategy())
        return await strategy.execute(error, context, stage)
```

---

## Layer 4: ML/NLP Engine

The intelligence layer provides all NLP and machine learning capabilities.
All models run locally with no external API dependencies.

### NLP Pipeline

```
[Ticket Text]
     │
     ▼
┌─────────────┐
│  Preprocess  │  Lowercase, tokenize, remove stopwords, lemmatize
└──────┬──────┘
       │
       ├──────────────────────┬──────────────────────┐
       ▼                      ▼                      ▼
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│ Categorizer │       │ Summarizer  │       │ Sentiment   │
│             │       │             │       │ Analyzer    │
└──────┬──────┘       └──────┬──────┘       └──────┬──────┘
       │                      │                      │
       ├──────────────────────┼──────────────────────┤
       ▼                      ▼                      ▼
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  Keywords   │       │   Entity    │       │   Dup       │
│  Extractor  │       │  Recognizer │       │  Detector   │
└──────┬──────┘       └──────┬──────┘       └──────┬──────┘
       │                      │                      │
       └──────────────────────┼──────────────────────┘
                              ▼
                     [Enriched Analysis]
```

### Text Preprocessing

```python
class TextPreprocessor:
    """Prepares raw text for NLP processing."""

    def __init__(self, config: NLPConfig):
        self.nlp = spacy.load("en_core_web_sm")
        self.stop_words = set(nltk.corpus.stopwords.words("english"))

    def preprocess(self, text: str) -> PreprocessedText:
        """Full preprocessing pipeline."""
        cleaned = self._clean(text)
        tokens = self._tokenize(cleaned)
        lemmas = self._lemmatize(tokens)
        filtered = self._remove_stopwords(lemmas)
        return PreprocessedText(
            original=text,
            cleaned=cleaned,
            tokens=tokens,
            lemmas=lemmas,
            filtered=filtered
        )

    def _clean(self, text: str) -> str:
        """Remove HTML, special characters, and normalize whitespace."""
        text = html.unescape(text)
        text = re.sub(r'<[^>]+>', '', text)  # Strip HTML tags
        text = re.sub(r'[^\w\s\.\,\-\!\?]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text.lower()
```

### Categorization Model

The default categorizer uses TF-IDF vectorization with a Multinomial Naive Bayes
classifier, chosen for its speed and effectiveness on short-to-medium text:

```python
class TicketCategorizer:
    """Hierarchical text classifier for ticket categorization."""

    def __init__(self, config: CategorizerConfig):
        self.vectorizer = TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 3),
            min_df=2,
            max_df=0.95,
            sublinear_tf=True
        )
        self.category_model = MultinomialNB(alpha=0.1)
        self.subcategory_models: dict[str, MultinomialNB] = {}
        self.is_trained = False

    def train(self, tickets: list[TrainingSample]) -> TrainingMetrics:
        """Train the categorizer on labeled ticket data."""
        texts = [t.text for t in tickets]
        categories = [t.category for t in tickets]

        # Train category-level model
        X = self.vectorizer.fit_transform(texts)
        self.category_model.fit(X, categories)

        # Train subcategory models per category
        for category in set(categories):
            mask = [c == category for c in categories]
            if sum(mask) >= 50:  # Minimum samples for subcategory model
                sub_model = MultinomialNB(alpha=0.1)
                sub_labels = [t.subcategory for t, m in zip(tickets, mask) if m]
                sub_model.fit(X[mask], sub_labels)
                self.subcategory_models[category] = sub_model

        self.is_trained = True
        return self._evaluate(X, categories)

    def predict(self, text: str) -> CategoryPrediction:
        """Predict category and subcategory for a ticket."""
        if not self.is_trained:
            raise ModelNotTrainedError("Categorizer must be trained before prediction")

        X = self.vectorizer.transform([text])

        # Category prediction
        cat_proba = self.category_model.predict_proba(X)[0]
        cat_idx = cat_proba.argmax()
        category = self.category_model.classes_[cat_idx]
        confidence = cat_proba[cat_idx]

        # Subcategory prediction
        subcategory = None
        sub_confidence = 0.0
        if category in self.subcategory_models:
            sub_model = self.subcategory_models[category]
            sub_proba = sub_model.predict_proba(X)[0]
            sub_idx = sub_proba.argmax()
            subcategory = sub_model.classes_[sub_idx]
            sub_confidence = sub_proba[sub_idx]

        return CategoryPrediction(
            category=category,
            subcategory=subcategory,
            confidence=confidence,
            subcategory_confidence=sub_confidence
        )
```

### Sentiment Analysis

```python
class SentimentAnalyzer:
    """Analyzes sentiment and emotion in ticket text."""

    def __init__(self, config: SentimentConfig):
        self.model = self._load_model(config.model)
        self.emotion_lexicon = self._load_emotion_lexicon()

    def analyze(self, text: str) -> SentimentResult:
        """Analyze sentiment of ticket text."""
        # Base sentiment classification
        sentiment, score = self._classify_sentiment(text)

        # Emotion detection using lexicon-based approach
        emotions = self._detect_emotions(text)

        # Escalation risk assessment
        escalation_risk = self._assess_escalation_risk(
            sentiment, score, emotions
        )

        return SentimentResult(
            sentiment=sentiment,
            score=score,
            magnitude=abs(score),
            emotions=emotions,
            escalation_risk=escalation_risk
        )
```

### Duplicate Detection

```python
class DuplicateDetector:
    """Detects duplicate and near-duplicate tickets."""

    def __init__(self, config: DedupConfig):
        self.threshold = config.similarity_threshold
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            stop_words='english'
        )
        self.ticket_vectors: dict[str, np.ndarray] = {}

    async def check_duplicate(
        self,
        ticket: TicketData,
        recent_tickets: list[TicketData]
    ) -> DuplicateResult:
        """Check if a ticket is a duplicate of any recent ticket."""
        if not recent_tickets:
            return DuplicateResult(is_duplicate=False)

        # Build combined text for comparison
        ticket_text = self._normalize_text(
            f"{ticket.title} {ticket.description}"
        )

        # Vectorize and compare
        all_texts = [ticket_text] + [
            self._normalize_text(f"{t.title} {t.description}")
            for t in recent_tickets
        ]
        vectors = self.vectorizer.fit_transform(all_texts)
        similarities = cosine_similarity(vectors[0:1], vectors[1:])[0]

        # Find best match above threshold
        best_idx = similarities.argmax()
        best_score = similarities[best_idx]

        if best_score >= self.threshold:
            return DuplicateResult(
                is_duplicate=True,
                confidence=best_score,
                original_ticket_id=recent_tickets[best_idx].ticket_id,
                similarity_score=best_score
            )

        return DuplicateResult(is_duplicate=False)
```

### ML Models

#### Priority Prediction

```python
class PriorityPredictor:
    """Predicts ticket priority using gradient boosting."""

    FEATURES = [
        "description_length",
        "category_encoded",
        "subcategory_encoded",
        "sentiment_score",
        "keywords_count",
        "mentions_outage",
        "mentions_multiple_users",
        "time_of_day",
        "day_of_week",
        "reporter_historical_priority_avg",
        "category_historical_priority_avg",
        "description_has_urgency_words",
        "description_has_exec_mention",
    ]

    def __init__(self, config: PriorityConfig):
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            min_samples_leaf=20
        )
        self.encoder = OrdinalEncoder(handle_unknown='use_encoded_value',
                                       unknown_value=-1)
        self.feature_names = self.FEATURES

    def extract_features(self, ticket: EnrichedTicket) -> np.ndarray:
        """Extract ML features from an enriched ticket."""
        return np.array([
            len(ticket.description or ""),
            self._encode_category(ticket.predicted_category),
            self._encode_subcategory(ticket.predicted_subcategory),
            ticket.sentiment_score or 0.0,
            len(ticket.keywords or []),
            float(self._has_keyword(ticket, ["outage", "down", "unavailable"])),
            float(self._has_keyword(ticket, ["multiple", "everyone", "all users"])),
            ticket.source_created_at.hour,
            ticket.source_created_at.weekday(),
            ticket.reporter_avg_priority or 2.0,
            ticket.category_avg_priority or 2.0,
            float(self._has_keyword(ticket, ["urgent", "asap", "critical", "emergency"])),
            float(self._has_keyword(ticket, ["ceo", "vp", "director", "executive"])),
        ])

    def predict(self, features: np.ndarray) -> PriorityPrediction:
        """Predict priority and return probabilities."""
        probabilities = self.model.predict_proba(features.reshape(1, -1))[0]
        predicted_idx = probabilities.argmax()

        return PriorityPrediction(
            priority=self.model.classes_[predicted_idx],
            confidence=probabilities[predicted_idx],
            probabilities=dict(zip(self.model.classes_, probabilities)),
            feature_importance=self._get_feature_importance(features)
        )
```

#### Anomaly Detection

```python
class AnomalyDetector:
    """Multi-method anomaly detection for ticket metrics."""

    def __init__(self, config: AnomalyConfig):
        self.methods = {
            "zscore": ZScoreDetector(threshold=config.zscore_threshold),
            "isolation_forest": IsolationForestDetector(
                contamination=config.contamination
            ),
        }

    def detect(
        self,
        metric_series: pd.Series,
        timestamps: pd.Series
    ) -> list[Anomaly]:
        """Run all configured detection methods."""
        anomalies = []

        for method_name, detector in self.methods.items():
            method_anomalies = detector.detect(metric_series, timestamps)
            anomalies.extend(method_anomalies)

        # Deduplicate overlapping anomalies
        anomalies = self._merge_overlapping(anomalies)

        # Score severity
        for anomaly in anomalies:
            anomaly.severity = self._calculate_severity(anomaly)

        return sorted(anomalies, key=lambda a: a.timestamp, reverse=True)
```

---

## Layer 5: Analytics Engine

The analytics layer transforms raw ticket data and ML/NLP results into
actionable insights, aggregations, and visualizations.

### KPI Engine

```python
class KPIEngine:
    """Calculates key performance indicators from ticket data."""

    async def calculate(
        self,
        period: str = "30d",
        filters: Optional[dict] = None
    ) -> KPIDashboard:
        """Calculate all KPIs for the given period."""
        tickets = await self._fetch_tickets(period, filters)

        return KPIDashboard(
            total_tickets=len(tickets),
            open_tickets=self._count_by_status(tickets, "open"),
            resolved_tickets=self._count_by_status(tickets, "resolved"),
            avg_resolution_time=self._avg_resolution_time(tickets),
            median_resolution_time=self._median_resolution_time(tickets),
            first_contact_resolution_rate=self._fcr_rate(tickets),
            sla_compliance_rate=self._sla_compliance(tickets),
            avg_customer_satisfaction=self._avg_csat(tickets),
            ticket_backlog=self._backlog_count(tickets),
            tickets_by_priority=self._group_by(tickets, "priority"),
            tickets_by_category=self._group_by(tickets, "category"),
            tickets_by_team=self._group_by(tickets, "assigned_group"),
            top_reporters=self._top_n(tickets, "reporter", 10),
            trending_categories=self._trending_categories(tickets),
            resolution_trend=self._resolution_trend(tickets),
            volume_forecast=self._volume_forecast(tickets),
        )
```

### Trend Engine

```python
class TrendEngine:
    """Computes time-series trends and patterns."""

    def compute_trends(
        self,
        tickets: list[Ticket],
        granularity: str = "daily"
    ) -> TrendData:
        """Compute trend data at the specified granularity."""
        df = pd.DataFrame([t.__dict__ for t in tickets])
        df['date'] = df['source_created_at'].dt.floor(granularity)

        trends = TrendData(
            volume=self._volume_trend(df),
            category_mix=self._category_trend(df),
            priority_mix=self._priority_trend(df),
            resolution_time=self._resolution_time_trend(df),
            backlog=self._backlog_trend(df),
        )

        # Add statistical annotations
        trends.volume.change_pct = self._pct_change(trends.volume)
        trends.volume.moving_avg = self._moving_average(trends.volume, 7)
        trends.volume.forecast = self._simple_forecast(trends.volume)

        return trends
```

### SLA Engine

```python
class SLAEngine:
    """Calculates SLA compliance metrics."""

    def __init__(self, config: SLAConfig):
        self.definitions = {
            d["name"]: SLADefinition(**d)
            for d in config.definitions
        }

    def calculate_compliance(
        self,
        tickets: list[Ticket]
    ) -> SLAReport:
        """Calculate SLA compliance for all tickets."""
        results = []

        for ticket in tickets:
            if ticket.priority not in self.definitions:
                continue

            sla = self.definitions[ticket.priority]
            response_time = self._time_to_first_response(ticket)
            resolution_time = self._time_to_resolution(ticket)

            results.append(SLACompliance(
                ticket_id=ticket.ticket_id,
                priority=ticket.priority,
                response_time_minutes=response_time.total_seconds() / 60,
                resolution_time_hours=resolution_time.total_seconds() / 3600,
                response_sla_met=response_time <= sla.response_time,
                resolution_sla_met=resolution_time <= sla.resolution_time,
                response_breach_by=response_time - sla.response_time,
                resolution_breach_by=resolution_time - sla.resolution_time,
            ))

        return SLAReport(
            total=len(results),
            response_compliance_rate=sum(
                1 for r in results if r.response_sla_met
            ) / max(len(results), 1),
            resolution_compliance_rate=sum(
                1 for r in results if r.resolution_sla_met
            ) / max(len(results), 1),
            by_priority=self._group_by_priority(results),
            breaches=[r for r in results if not r.resolution_sla_met],
            at_risk=self._find_at_risk(results),
        )
```

### Dashboard Engine

```python
class DashboardEngine:
    """Renders configurable dashboards."""

    async def render(
        self,
        dashboard_config: DashboardConfig,
        period: str = "30d"
    ) -> DashboardData:
        """Render a dashboard with all configured widgets."""
        widgets = []

        for widget_config in dashboard_config.widgets:
            widget = await self._render_widget(widget_config, period)
            widgets.append(widget)

        return DashboardData(
            name=dashboard_config.name,
            title=dashboard_config.title,
            period=period,
            generated_at=datetime.utcnow(),
            widgets=widgets,
        )

    async def _render_widget(
        self, config: WidgetConfig, period: str
    ) -> WidgetData:
        """Render a single widget based on its type."""
        renderers = {
            "kpi_card": self._render_kpi_card,
            "time_series": self._render_time_series,
            "bar_chart": self._render_bar_chart,
            "pie_chart": self._render_pie_chart,
            "table": self._render_table,
            "heatmap": self._render_heatmap,
        }
        renderer = renderers.get(config.type)
        if renderer is None:
            raise ValueError(f"Unknown widget type: {config.type}")
        return await renderer(config, period)
```

---

## Layer 6: Presentation

The presentation layer provides multiple interfaces for users and systems
to interact with TicketInsight Pro.

### REST API (FastAPI)

```python
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

app = FastAPI(
    title="TicketInsight Pro",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware stack
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
```

### Request Lifecycle

```
[HTTP Request]
     │
     ▼
┌─────────────┐
│  CORS Check │
└──────┬──────┘
       ▼
┌─────────────┐
│ Rate Limit  │
└──────┬──────┘
       ▼
┌─────────────┐
│ Auth Check  │  API Key or JWT validation
└──────┬──────┘
       ▼
┌─────────────┐
│ RBAC Check  │  Role-based access control
└──────┬──────┘
       ▼
┌─────────────┐
│  Route      │  Request dispatched to handler
│  Handler    │
└──────┬──────┘
       ▼
┌─────────────┐
│  Business   │  Core logic execution
│  Logic      │
└──────┬──────┘
       ▼
┌─────────────┐
│  Response   │  JSON serialization, caching
│  Serialize  │
└──────┬──────┘
       ▼
[HTTP Response]
```

### CLI (Typer)

```python
import typer

app = typer.Typer(
    name="ticketinsight",
    help="TicketInsight Pro - Open-Source Ticket Analytics",
    no_args_is_help=True,
)

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Bind port"),
    workers: int = typer.Option(1, help="Number of workers"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
):
    """Start the TicketInsight Pro API server."""
    uvicorn.run(
        "ticketinsight.app:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
    )

@app.command()
def sync(
    adapter: Optional[str] = typer.Argument(None),
    all_adapters: bool = typer.Option(False, "--all", help="Sync all adapters"),
    full: bool = typer.Option(False, "--full", help="Force full sync"),
    dry_run: bool = typer.Option(False, help="Preview only"),
):
    """Synchronize data from configured adapters."""
    ...
```

### Webhook Receiver

```python
@app.post("/webhooks/{source}")
async def receive_webhook(
    source: str,
    payload: dict = Body(...),
    signature: Optional[str] = Header(None),
):
    """Receive webhook notifications from external systems."""
    # Verify signature
    adapter = get_adapter(source)
    if not adapter.verify_webhook(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Process the webhook payload
    ticket_data = adapter.parse_webhook(payload)
    await pipeline.process(ticket_data)

    return {"status": "accepted", "ticket_id": ticket_data.ticket_id}
```

---

## Data Models

### Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   tickets    │       │   comments   │       │   analyses   │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)      │──┐    │ id (PK)      │       │ id (PK)      │
│ ticket_id    │  │    │ ticket_id(FK)│──┐    │ ticket_id(FK)│──┐
│ source_system│  │    │ author       │  │    │ pred_cat     │  │
│ source_adapt │  │    │ body         │  │    │ pred_subcat  │  │
│ title        │  │    │ created_at   │  │    │ sentiment    │  │
│ description  │  │    │ is_internal  │  │    │ keywords     │  │
│ status       │  │    └──────────────┘  │    │ summary      │  │
│ priority     │  │                      │    │ pred_priority│  │
│ category     │  │                      │    │ rec_assignee │  │
│ subcategory  │  │                      │    │ is_duplicate │  │
│ reporter     │  │                      │    │ analyzed_at  │  │
│ assigned_to  │  │                      │    └──────────────┘  │
│ assigned_grp │  │                      │                      │
│ tags (JSON)  │  │                      │                      │
│ custom (JSON)│  │                      │                      │
│ timestamps   │  │                      │                      │
└──────┬───────┘  │                      │                      │
       │          │                      │                      │
       │    ┌─────┘                      │                      │
       │    │                            │                      │
       ▼    ▼                            ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                        sync_logs                                 │
├──────────────────────────────────────────────────────────────────┤
│ id (PK) │ adapter_name │ started_at │ completed_at │ status     │
│ tickets_fetched │ tickets_created │ tickets_updated │ error_msg │
└──────────────────────────────────────────────────────────────────┘
```

---

## Authentication & Authorization

### Authentication Methods

| Method | Header | Description | Use Case |
|--------|--------|-------------|----------|
| **API Key** | `X-API-Key: <key>` | Static key authentication | Service-to-service, scripts |
| **JWT** | `Authorization: Bearer <token>` | Time-limited token with claims | Interactive sessions, UI |

### Role-Based Access Control

```python
class Role:
    ADMIN = "admin"           # Full access to all features
    ANALYST = "analyst"       # Read access + analytics + NLP
    OPERATOR = "operator"     # Read access + sync triggers
    READONLY = "readonly"     # Read-only access to all endpoints

PERMISSIONS = {
    Role.ADMIN: ["*"],
    Role.ANALYST: [
        "tickets:read", "tickets:search",
        "analytics:*", "nlp:*", "ml:read",
        "dashboards:*", "reports:*",
        "sync:read",
    ],
    Role.OPERATOR: [
        "tickets:read", "tickets:search",
        "analytics:read", "dashboards:read",
        "sync:*",
        "adapters:*",
    ],
    Role.READONLY: [
        "tickets:read", "tickets:search",
        "analytics:read", "dashboards:read",
        "sync:read",
    ],
}
```

---

## Error Handling

### Error Hierarchy

```python
class TicketInsightError(Exception):
    """Base exception for all TicketInsight Pro errors."""
    def __init__(self, message: str, code: str, http_status: int = 500):
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(message)

class AdapterError(TicketInsightError):
    """Errors from data source adapters."""
    def __init__(self, adapter: str, message: str):
        super().__init__(
            f"Adapter '{adapter}': {message}",
            code="ADAPTER_ERROR",
            http_status=502
        )

class AuthenticationError(TicketInsightError):
    """Authentication and authorization failures."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message, code="AUTH_ERROR", http_status=401
        )

class ValidationError(TicketInsightError):
    """Request validation failures."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message, code="VALIDATION_ERROR", http_status=422
        )
        self.details = details or {}

class ModelError(TicketInsightError):
    """ML/NLP model errors."""
    def __init__(self, model: str, message: str):
        super().__init__(
            f"Model '{model}': {message}",
            code="MODEL_ERROR",
            http_status=500
        )

class SyncError(TicketInsightError):
    """Data synchronization errors."""
    def __init__(self, adapter: str, message: str):
        super().__init__(
            f"Sync failed for '{adapter}': {message}",
            code="SYNC_ERROR",
            http_status=500
        )
```

### API Error Response Format

```json
{
    "error": {
        "code": "ADAPTER_ERROR",
        "message": "Adapter 'servicenow': Connection timed out after 30s",
        "details": {
            "adapter": "servicenow",
            "timeout_seconds": 30,
            "last_successful_sync": "2024-01-15T10:30:00Z"
        },
        "request_id": "req_abc123def456",
        "timestamp": "2024-01-15T11:00:00Z"
    }
}
```

---

## Performance Considerations

### Database Optimization

| Strategy | Impact | Implementation |
|----------|--------|---------------|
| Connection pooling | 3-5x query throughput | SQLAlchemy pool with `pool_size=10` |
| Query batching | Reduce round trips | Batch INSERT/UPDATE in chunks of 500 |
| Partial indexes | Faster queries, less storage | Index only active tickets |
| Read replicas | Scale reads | Route analytics queries to replica |
| WAL mode (SQLite) | 2x write throughput | `PRAGMA journal_mode=WAL` |

### Cache Strategy

```
Request → [L1: In-memory cache] → [L2: Redis cache] → [Database]

L1 Cache (Process-local):
  - TTL: 60 seconds
  - Size: 1000 entries
  - Hit rate target: 40%

L2 Cache (Redis):
  - TTL: 300-1800 seconds (varies by data type)
  - Hit rate target: 80% (combined with L1)
```

### Batch Processing

```python
# Tickets are processed in configurable batch sizes
class BatchProcessor:
    """Processes tickets in optimized batches."""

    async def process_unanalyzed(self):
        """Find and process tickets that haven't been analyzed yet."""
        while True:
            batch = await self._fetch_unanalyzed(limit=self.batch_size)
            if not batch:
                break

            # Parallel processing within batch
            results = await asyncio.gather(
                *[self._analyze_ticket(t) for t in batch],
                return_exceptions=True
            )

            # Bulk persist
            await self._bulk_save_results(results)

            self.logger.info(
                f"Processed batch of {len(batch)} tickets"
            )
```

---

## Scaling Strategy

### Vertical Scaling

| Resource | Minimum | Recommended | High Volume |
|----------|---------|-------------|-------------|
| **CPU** | 2 cores | 4 cores | 8+ cores |
| **Memory** | 2 GB | 4 GB | 8+ GB |
| **Disk** | 10 GB SSD | 50 GB SSD | 200+ GB SSD |
| **Tickets** | Up to 10K | Up to 100K | 100K+ |

### Horizontal Scaling

For deployments processing 100K+ tickets or serving multiple teams:

```
                    ┌──────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼────┐  ┌───▼────┐  ┌───▼────┐
         │Worker 1 │  │Worker 2│  │Worker N│
         └────┬────┘  └───┬────┘  └───┬────┘
              │            │            │
              └────────────┼────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼────┐  ┌───▼────┐  ┌───▼────┐
         │PostgreSQL│  │ Redis  │  │ Object │
         │  (Primary)│ │ Cluster│  │Storage │
         └─────────┘  └────────┘  └────────┘
```

Key scaling considerations:
- Use PostgreSQL for shared database with read replicas
- Use Redis cluster for distributed caching
- Share ML models via shared file system (NFS/EFS)
- Use message queue (RabbitMQ/Celery) for task distribution
- Sticky sessions not required (stateless API)

---

## Security Architecture

### Security Layers

| Layer | Control | Implementation |
|-------|---------|---------------|
| **Transport** | TLS encryption | HTTPS via reverse proxy |
| **Authentication** | API keys, JWT | FastAPI security middleware |
| **Authorization** | RBAC | Role-permission mapping |
| **Input Validation** | Schema validation | Pydantic models |
| **Output Filtering** | Field filtering | Response serialization |
| **Secrets** | Env var injection | `${VAR}` config resolution |
| **Logging** | Sensitive field masking | Structured log redaction |
| **Dependencies** | Pinned versions | `requirements.txt` with hashes |
| **Container** | Non-root, read-only | Dockerfile hardening |

### Secret Management

```python
class SecretResolver:
    """Resolves ${VAR} placeholders in configuration."""

    SENSITIVE_KEYS = {
        "password", "secret", "token", "api_key", "key",
        "credential", "auth", "private",
    }

    def resolve(self, value: str) -> str:
        """Resolve environment variable references."""
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            resolved = os.environ.get(var_name)
            if resolved is None:
                raise ConfigurationError(
                    f"Environment variable '{var_name}' is not set"
                )
            return resolved
        return value

    def is_sensitive(self, key_path: str) -> bool:
        """Check if a config key contains sensitive data."""
        parts = key_path.lower().split(".")
        return any(
            sensitive in part
            for part in parts
            for sensitive in self.SENSITIVE_KEYS
        )
```
