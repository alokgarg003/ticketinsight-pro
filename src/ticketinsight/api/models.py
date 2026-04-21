"""
Request/response schemas for the TicketInsight Pro REST API.

All schemas use Marshmallow for serialisation, deserialisation, and
validation.  Every endpoint validates incoming payloads through the
appropriate schema before processing.

Usage
-----
    from ticketinsight.api.models import TicketFilterSchema

    schema = TicketFilterSchema()
    errors = schema.validate(request.args)
    if errors:
        return jsonify(errors), 400
"""

from marshmallow import Schema, fields, validate, pre_load, post_dump, EXCLUDE


# ===========================================================================
# Request schemas (incoming data)
# ===========================================================================


class TicketFilterSchema(Schema):
    """Schema for ticket filtering and pagination query parameters.

    Used to validate GET /api/v1/tickets query string parameters.
    All fields are optional — sensible defaults are provided.
    """

    class Meta:
        unknown = EXCLUDE

    status = fields.Str(
        required=False,
        metadata={"description": "Filter by ticket status (e.g. Open, Resolved)"},
    )
    priority = fields.Str(
        required=False,
        metadata={"description": "Filter by priority (Critical, High, Medium, Low)"},
    )
    category = fields.Str(
        required=False,
        metadata={"description": "Filter by ticket category"},
    )
    source_system = fields.Str(
        required=False,
        metadata={"description": "Filter by source system (csv, servicenow, jira)"},
    )
    date_from = fields.Date(
        required=False,
        metadata={"description": "Start date filter (YYYY-MM-DD)"},
    )
    date_to = fields.Date(
        required=False,
        metadata={"description": "End date filter (YYYY-MM-DD)"},
    )
    search = fields.Str(
        required=False,
        metadata={"description": "Full-text search on title and description"},
    )
    assignee = fields.Str(
        required=False,
        metadata={"description": "Filter by assignee username"},
    )
    assignment_group = fields.Str(
        required=False,
        metadata={"description": "Filter by assignment group name"},
    )
    page = fields.Int(
        required=False,
        load_default=1,
        metadata={"description": "Page number (1-indexed)"},
    )
    per_page = fields.Int(
        required=False,
        load_default=20,
        validate=validate.Range(min=1, max=100),
        metadata={"description": "Results per page (max 100)"},
    )
    sort_by = fields.Str(
        required=False,
        load_default="opened_at",
        metadata={"description": "Column to sort by"},
    )
    sort_order = fields.Str(
        required=False,
        load_default="desc",
        validate=validate.OneOf(["asc", "desc"]),
        metadata={"description": "Sort direction"},
    )

    @pre_load
    def strip_strings(self, data, **kwargs):
        """Remove leading/trailing whitespace from all string fields."""
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = value.strip()
        return data


class IngestRequestSchema(Schema):
    """Schema for POST /api/v1/ingest requests.

    Validates the adapter type and ingestion parameters.
    """

    class Meta:
        unknown = EXCLUDE

    adapter_type = fields.Str(
        required=True,
        validate=validate.OneOf(["servicenow", "jira", "csv", "universal"]),
        metadata={"description": "Source adapter to use for ingestion"},
    )
    query = fields.Str(
        required=False,
        metadata={"description": "Query/filter for the source system"},
    )
    limit = fields.Int(
        required=False,
        load_default=1000,
        validate=validate.Range(min=1, max=50000),
        metadata={"description": "Maximum tickets to ingest"},
    )
    date_from = fields.Date(
        required=False,
        metadata={"description": "Start date for ingestion range"},
    )
    date_to = fields.Date(
        required=False,
        metadata={"description": "End date for ingestion range"},
    )
    full_sync = fields.Bool(
        required=False,
        load_default=False,
        metadata={"description": "Perform full sync instead of incremental"},
    )


class AnalyzeRequestSchema(Schema):
    """Schema for POST /api/v1/analyze requests.

    Controls which tickets to analyse and which NLP modules to run.
    """

    class Meta:
        unknown = EXCLUDE

    ticket_ids = fields.List(
        fields.Int(),
        required=False,
        metadata={"description": "Specific ticket database IDs to analyse"},
    )
    analysis_types = fields.List(
        fields.Str(
            validate=validate.OneOf([
                "classification",
                "sentiment",
                "topic",
                "duplicate",
                "anomaly",
                "summary",
                "ner",
                "root_cause",
            ])
        ),
        required=False,
        metadata={"description": "Which NLP analysis modules to run"},
    )
    force_refresh = fields.Bool(
        required=False,
        load_default=False,
        metadata={"description": "Force re-analysis even if insights already exist"},
    )


class ConfigUpdateSchema(Schema):
    """Schema for PUT /api/v1/config requests.

    Only allows updating non-sensitive configuration fields.
    """

    class Meta:
        unknown = EXCLUDE

    adapter_type = fields.Str(
        required=False,
        validate=validate.OneOf(["servicenow", "jira", "csv", "universal"]),
    )
    pipeline_interval_minutes = fields.Int(
        required=False,
        validate=validate.Range(min=1, max=1440),
    )
    cache_ttl = fields.Int(
        required=False,
        validate=validate.Range(min=60, max=86400),
    )
    log_level = fields.Str(
        required=False,
        validate=validate.OneOf(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    )
    csv_file_path = fields.Str(required=False)
    batch_size = fields.Int(
        required=False,
        validate=validate.Range(min=10, max=10000),
    )


class AdapterTestSchema(Schema):
    """Schema for POST /api/v1/adapter/test requests."""

    class Meta:
        unknown = EXCLUDE

    adapter_type = fields.Str(
        required=True,
        validate=validate.OneOf(["servicenow", "jira", "csv", "universal"]),
    )


# ===========================================================================
# Response schemas (outgoing data)
# ===========================================================================


class TicketSchema(Schema):
    """Schema for a single ticket in API responses.

    Includes all ticket fields plus NLP enrichment data.
    """

    class Meta:
        unknown = EXCLUDE

    id = fields.Int(metadata={"description": "Database primary key"})
    ticket_id = fields.Str(metadata={"description": "External ticket identifier"})
    title = fields.Str(metadata={"description": "Ticket title"})
    description = fields.Str(metadata={"description": "Full ticket description"})
    priority = fields.Str(metadata={"description": "Canonical priority label"})
    status = fields.Str(metadata={"description": "Canonical status label"})
    category = fields.Str(metadata={"description": "Ticket category"})
    assignment_group = fields.Str(metadata={"description": "Team assigned"})
    assignee = fields.Str(metadata={"description": "Individual assignee"})
    opened_at = fields.DateTime(
        metadata={"description": "When the ticket was opened"},
    )
    resolved_at = fields.DateTime(
        metadata={"description": "When the ticket was resolved"},
    )
    closed_at = fields.DateTime(
        metadata={"description": "When the ticket was closed"},
    )
    updated_at = fields.DateTime(
        metadata={"description": "Last update timestamp from source"},
    )
    source_system = fields.Str(
        metadata={"description": "Source system (csv, servicenow, jira)"},
    )
    sentiment_score = fields.Float(
        metadata={"description": "NLP sentiment score (-1.0 to 1.0)"},
    )
    sentiment_label = fields.Str(
        metadata={"description": "Sentiment classification (Positive, Neutral, Negative)"},
    )
    predicted_category = fields.Str(
        metadata={"description": "NLP-predicted category"},
    )
    topic_cluster = fields.Int(
        allow_none=True,
        metadata={"description": "Topic model cluster assignment"},
    )
    duplicate_of_id = fields.Int(
        allow_none=True,
        metadata={"description": "ID of the master ticket if this is a duplicate"},
    )
    anomaly_score = fields.Float(
        metadata={"description": "Anomaly detection score (0.0 to 1.0)"},
    )
    summary = fields.Str(
        metadata={"description": "NLP-generated ticket summary"},
    )
    named_entities = fields.Dict(
        metadata={"description": "Named entities extracted from ticket text"},
    )
    root_cause_cluster = fields.Int(
        allow_none=True,
        metadata={"description": "Root cause analysis cluster assignment"},
    )


class InsightSchema(Schema):
    """Schema for a single insight record in API responses."""

    class Meta:
        unknown = EXCLUDE

    id = fields.Int()
    ticket_id = fields.Int(metadata={"description": "Database ID of the associated ticket"})
    insight_type = fields.Str(
        metadata={
            "description": "Type of insight (classification, sentiment, topic, "
                          "duplicate, anomaly, summary, ner, root_cause)"
        },
    )
    insight_data = fields.Dict(
        metadata={"description": "Structured data specific to this insight type"},
    )
    confidence = fields.Float(
        metadata={"description": "Confidence score of the insight (0.0 to 1.0)"},
    )
    created_at = fields.DateTime(metadata={"description": "When the insight was created"})


class PaginatedResponseSchema(Schema):
    """Schema for paginated ticket list responses."""

    tickets = fields.List(
        fields.Nested(TicketSchema),
        metadata={"description": "List of tickets on this page"},
    )
    total = fields.Int(metadata={"description": "Total matching tickets across all pages"})
    page = fields.Int(metadata={"description": "Current page number (1-indexed)"})
    per_page = fields.Int(metadata={"description": "Items per page"})
    total_pages = fields.Int(metadata={"description": "Total number of pages"})


class ErrorResponseSchema(Schema):
    """Schema for error responses returned by the API."""

    error = fields.Str(metadata={"description": "Short error code (e.g. not_found)"})
    message = fields.Str(metadata={"description": "Human-readable error description"})
    status_code = fields.Int(metadata={"description": "HTTP status code"})
    details = fields.Dict(
        required=False,
        metadata={"description": "Additional error context or field-level errors"},
    )


class HealthResponseSchema(Schema):
    """Schema for the health check endpoint response."""

    status = fields.Str(metadata={"description": "overall status (healthy, degraded, unhealthy)"})
    version = fields.Str(metadata={"description": "Application version"})
    uptime_seconds = fields.Float(metadata={"description": "Seconds since server start"})
    services = fields.Dict(
        metadata={"description": "Status of each dependency (db, redis, adapter)"},
    )


class IngestResponseSchema(Schema):
    """Schema for ingestion trigger response."""

    task_id = fields.Str(metadata={"description": "Unique task identifier for tracking"})
    status = fields.Str(metadata={"description": "Task status (queued, running, completed)"})
    adapter_type = fields.Str(metadata={"description": "Adapter used for ingestion"})
    message = fields.Str(metadata={"description": "Human-readable status message"})


class AnalyzeResponseSchema(Schema):
    """Schema for analysis trigger response."""

    task_id = fields.Str(metadata={"description": "Unique task identifier"})
    status = fields.Str(metadata={"description": "Task status"})
    tickets_analyzed = fields.Int(metadata={"description": "Number of tickets queued for analysis"})
    analysis_types = fields.List(
        fields.Str(),
        metadata={"description": "NLP analysis types requested"},
    )


class DashboardStatsSchema(Schema):
    """Schema for dashboard statistics response."""

    total_tickets = fields.Int()
    open_tickets = fields.Int()
    in_progress_tickets = fields.Int()
    resolved_tickets = fields.Int()
    closed_tickets = fields.Int()
    critical_tickets = fields.Int()
    avg_resolution_time_hours = fields.Float(allow_none=True)
    avg_sentiment_score = fields.Float()
    anomaly_count = fields.Int()
    duplicate_count = fields.Int()
    opened_today = fields.Int()
    resolved_today = fields.Int()
    by_status = fields.Dict()
    by_priority = fields.Dict()
    by_category = fields.Dict()
    sentiment_distribution = fields.Dict()


class TrendDataPointSchema(Schema):
    """Schema for a single data point in a time series."""

    date = fields.Str(metadata={"description": "Date label (YYYY-MM-DD)"})
    value = fields.Float(metadata={"description": "Metric value"})
    count = fields.Int(metadata={"description": "Number of tickets in this period"})


class TrendResponseSchema(Schema):
    """Schema for trend data responses."""

    metric = fields.Str(metadata={"description": "Metric name (volume, resolution_time, sentiment)"})
    period = fields.Str(metadata={"description": "Aggregation period (daily, weekly, monthly)"})
    data_points = fields.List(
        fields.Nested(TrendDataPointSchema),
        metadata={"description": "Time series data points"},
    )


class PipelineStatusSchema(Schema):
    """Schema for pipeline scheduler status response."""

    running = fields.Bool(metadata={"description": "Whether the scheduler is active"})
    interval_minutes = fields.Int(metadata={"description": "Minutes between scheduled runs"})
    last_run = fields.DateTime(allow_none=True, metadata={"description": "Timestamp of last pipeline run"})
    next_run = fields.DateTime(allow_none=True, metadata={"description": "Estimated timestamp of next run"})
    total_runs = fields.Int(metadata={"description": "Total number of pipeline runs executed"})
    last_run_status = fields.Str(
        allow_none=True,
        metadata={"description": "Status of the most recent run (success, failed)"},
    )
    enabled_modules = fields.List(
        fields.Str(),
        metadata={"description": "NLP modules enabled in the pipeline"},
    )


class AdapterStatusSchema(Schema):
    """Schema for adapter connection status response."""

    configured_type = fields.Str(metadata={"description": "Currently configured adapter type"})
    available_adapters = fields.List(
        fields.Str(),
        metadata={"description": "List of all available adapter types"},
    )
    connection_status = fields.Str(
        metadata={"description": "Connection status (connected, disconnected, not_configured)"},
    )
    last_error = fields.Str(
        allow_none=True,
        metadata={"description": "Most recent connection error message"},
    )


__all__ = [
    "TicketFilterSchema",
    "IngestRequestSchema",
    "AnalyzeRequestSchema",
    "ConfigUpdateSchema",
    "AdapterTestSchema",
    "TicketSchema",
    "InsightSchema",
    "PaginatedResponseSchema",
    "ErrorResponseSchema",
    "HealthResponseSchema",
    "IngestResponseSchema",
    "AnalyzeResponseSchema",
    "DashboardStatsSchema",
    "TrendDataPointSchema",
    "TrendResponseSchema",
    "PipelineStatusSchema",
    "AdapterStatusSchema",
]
