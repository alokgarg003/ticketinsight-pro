# Changelog

All notable changes to the TicketInsight Pro project are documented in this file.
This project follows [Semantic Versioning](https://semver.org/) and
[Conventional Commits](https://www.conventionalcommits.org/).

The format is based on [Keep a Changelog](https://keepachangelog.com/).

---

## [1.1.0] - 2024-06-01

### Added

- **Web UI Dashboard**: Interactive web-based dashboard with real-time charts, filterable tables, and export options. Built with Jinja2 templates and served at `/dashboard`.
- **Real-time Streaming Sync**: WebSocket-based push sync that receives ticket updates from source systems in real time, eliminating polling delays for supported adapters.
- **Zendesk Adapter**: Full Zendesk support including ticket ingestion, comment threading, custom field mapping, and webhook-based push sync.
- **Freshservice Adapter**: Native adapter for Freshservice with support for tickets, assets, changes, and problems.
- **Multi-language NLP**: Support for Spanish, French, and German text analysis in the categorizer, sentiment analyzer, and keyword extractor. Uses language-specific spaCy models.
- **Custom Model Training UI**: API endpoint `POST /api/v1/ml/models/train-custom` for training models on user-provided CSV data with automatic feature extraction.
- **PowerPoint Export**: Export dashboards and reports to `.pptx` format with configurable slide layouts.
- **Google Slides Export**: Direct export to Google Slides via the Google Drive API.
- **Ticket Correlation Analysis**: New `POST /api/v1/analytics/correlations` endpoint that identifies statistically related tickets (e.g., tickets opened around the same time with similar categories that may indicate a root cause).
- **Enhanced Deduplication**: Cross-source duplicate detection that finds matching tickets across different adapters (e.g., a ServiceNow incident and Jira issue describing the same problem).

### Changed

- Improved categorizer accuracy by 3.2% with upgraded TF-IDF features including bigram and trigram support.
- Reduced memory consumption of the NLP pipeline by 25% through lazy model loading.
- Increased default sync polling interval from 10 minutes to 15 minutes to reduce API load.
- Updated the FastAPI dependency to version 0.115+ for improved performance.
- Improved error messages for adapter connection failures with actionable troubleshooting steps.

### Fixed

- Fixed a bug where duplicate detection could produce false positives for tickets with very short descriptions.
- Fixed ServiceNow adapter failing on tables with custom fields containing null values.
- Fixed CSV import not correctly detecting UTF-16 encoded files.
- Fixed priority predictor confidence scores occasionally exceeding 1.0 due to floating-point precision.
- Fixed dashboard KPI cards showing stale data when cache was invalidated during request processing.
- Fixed the `--dry-run` flag on `ticketinsight sync` not correctly previewing the number of changes.
- Fixed race condition in batch NLP processing that could cause duplicate analysis records.
- Fixed WebSocket connections not being properly closed on server shutdown.

### Deprecated

- The `ticketinsight report --format xlsx` flag is deprecated in favor of `ticketinsight report --format excel`. Support will be removed in v2.0.

### Security

- Added rate limiting bypass protection to prevent header injection attacks.
- Updated all Python dependencies to address CVE-2024-xxxx.
- Added Content-Security-Policy headers to the web UI.
- Fixed potential information disclosure in error responses for unauthenticated requests.

---

## [1.0.0] - 2024-03-15

### Added

- **Core NLP Pipeline**: Full NLP processing including categorization (TF-IDF + Naive Bayes), extractive and abstractive summarization, sentiment analysis with emotion detection, keyword extraction (RAKE, TF-IDF, YAKE), and duplicate detection.
- **ML Models**: Priority prediction (Gradient Boosting), assignee/team recommendation (with workload awareness), ticket volume forecasting (Prophet, ARIMA, Holt-Winters), and anomaly detection (Z-Score, Isolation Forest).
- **ServiceNow Adapter**: Complete ServiceNow integration with table API support, incremental sync using `sys_updated_on` watermark, rate limiting, and configurable field selection.
- **Jira Adapter**: Jira Cloud and Server support with JQL filtering, multi-project aggregation, custom field mapping, and transition history tracking.
- **CSV Import**: Batch CSV import with automatic field mapping, multiple date format support, encoding detection, file watching for continuous import, and validation with row-level error reporting.
- **Universal REST Adapter**: Configurable adapter for any REST API with cursor/offset/link-header pagination, response path mapping, custom headers, and webhook receiver for push-based sync.
- **REST API**: 22+ RESTful endpoints covering tickets, analytics, NLP, ML, sync, dashboards, alerts, adapters, reports, and system management.
- **CLI Interface**: Full-featured CLI with commands for serving, syncing, analyzing, reporting, database management, model management, adapter management, and configuration validation.
- **Dashboard Engine**: JSON-configurable dashboards with KPI cards, time-series charts, bar charts, pie charts, heatmaps, and tables. Auto-generated and customizable layouts.
- **Alert System**: Threshold-based alerting with Slack, Microsoft Teams, email, and generic webhook notification channels. Cooldown periods and acknowledgment support.
- **Scheduled Reports**: Cron-based report generation and delivery with HTML and PDF output formats.
- **Role-Based Access Control**: Four roles (admin, analyst, operator, readonly) with fine-grained permission mapping. API key and JWT authentication.
- **Docker Support**: Production-ready Dockerfile with multi-stage build, non-root user, health checks, and resource limits. Docker Compose configuration for full-stack deployment.
- **Database Support**: SQLite for development and PostgreSQL for production. SQLAlchemy ORM with connection pooling, migration support, and optimized indexing.
- **Caching**: In-memory and Redis cache backends with configurable TTL, cache warming, and selective invalidation.
- **Structured Logging**: JSON-formatted structured logging with sensitive field redaction, request ID tracking, and configurable log levels.
- **Comprehensive Documentation**: README, architecture guide, API reference, deployment guide, contributing guide, and adapter development guide.

### Security

- All NLP and ML processing runs entirely on-device with no external API calls.
- No data is transmitted to external services.
- API key and JWT authentication with configurable expiration.
- Sensitive configuration values support environment variable injection.
- Structured logging with automatic redaction of sensitive fields.

---

## [0.9.0] - 2024-01-15

### Added

- Beta release with core ticket ingestion from ServiceNow and CSV.
- Basic categorization using TF-IDF + Naive Bayes.
- Sentiment analysis pipeline.
- REST API for ticket listing and basic analytics.
- Docker Compose configuration for development.
- Initial project documentation.

### Changed

- Migrated from Flask to FastAPI for async support and automatic OpenAPI docs.
- Switched from raw SQL to SQLAlchemy ORM for database abstraction.
- Replaced cron-based scheduling with APScheduler for in-process job management.

### Fixed

- Fixed memory leak in long-running sync processes.
- Fixed CSV import failing on files with mixed line endings.
- Fixed API pagination returning incorrect total counts.

---

## [0.5.0] - 2023-10-01

### Added

- Initial alpha release.
- Basic ticket ingestion from CSV files.
- Simple text categorization using keyword matching.
- SQLite database for ticket storage.
- Basic CLI with `serve` and `analyze` commands.
- Project scaffolding and CI/CD pipeline.

### Known Limitations

- No external adapter support (CSV only).
- Categorization limited to keyword matching (no ML).
- No authentication or authorization.
- No caching layer.
- No Docker support.

---

## [0.1.0] - 2023-07-01

### Added

- Project initialization.
- Core data models and database schema.
- Basic FastAPI application skeleton.
- Initial test suite.
- GitHub Actions CI pipeline.
- Contribution guidelines.

---

## Version History Summary

| Version | Date | Type | Tickets | Endpoints | Adapters |
|---------|------|------|---------|-----------|----------|
| 0.1.0 | 2023-07-01 | Alpha | - | 0 | 0 (CSV) |
| 0.5.0 | 2023-10-01 | Alpha | Basic | 5 | 1 |
| 0.9.0 | 2024-01-15 | Beta | 10K+ | 12 | 2 |
| 1.0.0 | 2024-03-15 | Stable | 100K+ | 22+ | 4 |
| 1.1.0 | 2024-06-01 | Stable | 100K+ | 28+ | 6 |
