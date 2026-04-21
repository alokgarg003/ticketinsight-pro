"""
Flask REST API routes for TicketInsight Pro.

Defines all endpoints under the ``/api/v1`` prefix.  Every endpoint
validates input via Marshmallow schemas, queries the database through
:class:`~ticketinsight.storage.database.DatabaseManager`, leverages the
:class:`~ticketinsight.storage.cache.CacheManager` where appropriate,
and returns structured JSON responses with proper HTTP status codes.
"""

import hashlib
import math
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify, current_app

from ticketinsight.api.models import (
    TicketFilterSchema,
    IngestRequestSchema,
    AnalyzeRequestSchema,
    ConfigUpdateSchema,
    AdapterTestSchema,
    ErrorResponseSchema,
    TicketSchema,
    InsightSchema,
    PaginatedResponseSchema,
)
from ticketinsight.utils.logger import get_logger

logger = get_logger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Track ingestion/analysis tasks in-memory
_task_registry: Dict[str, Dict[str, Any]] = {}
_task_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helper decorators
# ---------------------------------------------------------------------------


def _json_error(error: str, message: str, status_code: int = 400, details: Optional[Dict] = None):
    """Build a standardised JSON error response."""
    schema = ErrorResponseSchema()
    payload = {"error": error, "message": message, "status_code": status_code}
    if details:
        payload["details"] = details
    return jsonify(schema.dump(payload)), status_code


def _validate_schema(schema_class, data: Dict, many: bool = False):
    """Validate data against a Marshmallow schema.

    Returns (validated_data, errors).  On validation failure,
    *errors* is a dict of field-level error messages.
    """
    schema = schema_class()
    result = schema.load(data, unknown="exclude", many=many)
    return result


def _get_db():
    """Return the DatabaseManager stored on the Flask app."""
    return current_app.extensions.get("db_manager")


def _get_cache():
    """Return the CacheManager stored on the Flask app."""
    return current_app.extensions.get("cache_manager")


def _get_config():
    """Return the ConfigManager stored on the Flask app."""
    return current_app.extensions.get("config_manager")


# ---------------------------------------------------------------------------
# Health / Status
# ---------------------------------------------------------------------------


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint.

    Returns service status, version, uptime, and individual dependency
    health (database, cache, adapter).
    """
    try:
        from ticketinsight import __version__

        version = __version__
    except Exception:
        version = "unknown"

    # Uptime from app start time
    start_time = getattr(current_app, "_start_time", time.time())
    uptime_seconds = round(time.time() - start_time, 2)

    services = {}

    # Database health
    db_mgr = _get_db()
    try:
        if db_mgr and db_mgr._app is not None:
            from ticketinsight.storage.database import Ticket
            count = Ticket.query.count()
            services["database"] = {
                "status": "healthy",
                "backend": db_mgr._db_url or "unknown",
                "ticket_count": count,
            }
        else:
            services["database"] = {"status": "unhealthy", "error": "Not initialised"}
    except Exception as exc:
        services["database"] = {"status": "unhealthy", "error": str(exc)}

    # Cache health
    cache = _get_cache()
    try:
        if cache:
            health = cache.health_check()
            services["cache"] = {
                "status": "healthy" if health.get("healthy") else "degraded",
                "backend": health.get("backend", "unknown"),
                "latency_ms": health.get("latency_ms", 0),
            }
        else:
            services["cache"] = {"status": "not_configured"}
    except Exception as exc:
        services["cache"] = {"status": "unhealthy", "error": str(exc)}

    # Adapter health
    try:
        config = _get_config()
        adapter_type = config.get("adapter", "type", "csv") if config else "csv"
        services["adapter"] = {
            "status": "configured",
            "type": adapter_type,
        }
    except Exception as exc:
        services["adapter"] = {"status": "unknown", "error": str(exc)}

    # Determine overall status
    statuses = [s.get("status", "unknown") for s in services.values()]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return jsonify({
        "status": overall,
        "version": version,
        "uptime_seconds": uptime_seconds,
        "services": services,
    })


# ---------------------------------------------------------------------------
# Tickets CRUD
# ---------------------------------------------------------------------------


@api_bp.route("/tickets", methods=["GET"])
def get_tickets():
    """Get tickets with filtering, search, sorting, and pagination.

    Query Parameters
    ----------------
    All parameters are optional.  See :class:`TicketFilterSchema`.
    """
    try:
        params = dict(request.args)
        data = _validate_schema(TicketFilterSchema, params)
    except Exception as exc:
        logger.warning("Ticket filter validation error: %s", exc)
        return _json_error("validation_error", str(exc.messages) if hasattr(exc, "messages") else str(exc), 400)

    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    # Build filters dict for DatabaseManager.get_tickets
    filters = {}
    for key in ["status", "priority", "category", "source_system", "search", "assignee", "assignment_group"]:
        if key in data and data[key]:
            filters[key] = data[key]

    if data.get("date_from"):
        filters["date_from"] = datetime.combine(data["date_from"], datetime.min.time())
    if data.get("date_to"):
        filters["date_to"] = datetime.combine(data["date_to"], datetime.max.time())

    # Check cache first
    cache = _get_cache()
    cache_key = f"tickets:{hashlib.md5(str(sorted(filters.items()) + [(data.get('page')), (data.get('per_page')), (data.get('sort_by')), (data.get('sort_order'))]).encode()).hexdigest()}"
    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return jsonify(cached)

    try:
        result = db_mgr.get_tickets(
            filters=filters,
            page=data.get("page", 1),
            per_page=data.get("per_page", 20),
            sort_by=data.get("sort_by", "opened_at"),
            sort_order=data.get("sort_order", "desc"),
        )
    except Exception as exc:
        logger.error("Failed to query tickets: %s", exc)
        return _json_error("database_error", f"Failed to query tickets: {exc}", 500)

    # Cache for 5 minutes
    if cache:
        cache.set(cache_key, result, ttl=300)

    return jsonify(result)


@api_bp.route("/tickets/<int:ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    """Get a single ticket by its database ID with all NLP insights."""
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    try:
        from ticketinsight.storage.database import Ticket, TicketInsight

        ticket = Ticket.query.get(ticket_id)
        if ticket is None:
            return _json_error("not_found", f"Ticket with id {ticket_id} not found", 404)

        result = ticket.to_dict()
        result["insights"] = [i.to_dict() for i in ticket.insights.all()]
    except Exception as exc:
        logger.error("Failed to fetch ticket %s: %s", ticket_id, exc)
        return _json_error("database_error", f"Failed to fetch ticket: {exc}", 500)

    return jsonify(result)


@api_bp.route("/tickets/<int:ticket_id>/insights", methods=["GET"])
def get_ticket_insights(ticket_id):
    """Get all NLP insights for a specific ticket."""
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    try:
        from ticketinsight.storage.database import Ticket, TicketInsight

        ticket = Ticket.query.get(ticket_id)
        if ticket is None:
            return _json_error("not_found", f"Ticket with id {ticket_id} not found", 404)

        insights = TicketInsight.query.filter_by(ticket_id=ticket_id).all()
        result = {
            "ticket_id": ticket_id,
            "ticket_number": ticket.ticket_id,
            "total_insights": len(insights),
            "insights": [i.to_dict() for i in insights],
        }
    except Exception as exc:
        logger.error("Failed to fetch insights for ticket %s: %s", ticket_id, exc)
        return _json_error("database_error", f"Failed to fetch insights: {exc}", 500)

    return jsonify(result)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


@api_bp.route("/ingest", methods=["POST"])
def trigger_ingestion():
    """Trigger data ingestion from a configured adapter.

    Runs ingestion in a background thread and returns a task ID
    for tracking progress.
    """
    try:
        payload = request.get_json(silent=True) or {}
        data = _validate_schema(IngestRequestSchema, payload)
    except Exception as exc:
        msg = exc.messages if hasattr(exc, "messages") else str(exc)
        return _json_error("validation_error", f"Invalid request: {msg}", 400)

    task_id = str(uuid.uuid4())
    adapter_type = data["adapter_type"]

    with _task_lock:
        _task_registry[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "adapter_type": adapter_type,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "progress": 0,
            "message": "Ingestion task queued",
        }

    def _run_ingestion():
        with _task_lock:
            _task_registry[task_id]["status"] = "running"
            _task_registry[task_id]["message"] = f"Ingesting from {adapter_type}..."

        try:
            with current_app.app_context():
                try:
                    from ticketinsight.pipeline import DataIngester
                except ImportError:
                    _task_registry[task_id].update({
                        "status": "failed",
                        "message": "Pipeline module not available. Install full dependencies.",
                    })
                    return

                ingester = DataIngester()
                config = _get_config()
                ingest_config = {
                    "adapter_type": adapter_type,
                    "limit": data.get("limit", 1000),
                    "full_sync": data.get("full_sync", False),
                    "query": data.get("query"),
                    "date_from": data.get("date_from"),
                    "date_to": data.get("date_to"),
                }

                if config:
                    ingest_config["adapter_config"] = config.get_section("adapter")

                result = ingester.ingest(ingest_config)

                with _task_lock:
                    _task_registry[task_id].update({
                        "status": "completed",
                        "message": f"Ingestion completed: {result.get('inserted', 0)} tickets processed",
                        "progress": 100,
                        "result": result,
                    })

                # Invalidate ticket caches
                cache = _get_cache()
                if cache:
                    cache.invalidate_pattern("tickets:*")
                    cache.invalidate_pattern("stats:*")

                # Audit log
                db_mgr = _get_db()
                if db_mgr:
                    db_mgr.create_audit_log(
                        action="ingest.complete",
                        entity_type="ticket",
                        details={"adapter_type": adapter_type, "result": result},
                    )

        except Exception as exc:
            logger.error("Ingestion task %s failed: %s", task_id, exc)
            with _task_lock:
                _task_registry[task_id].update({
                    "status": "failed",
                    "message": f"Ingestion failed: {str(exc)}",
                })

    thread = threading.Thread(target=_run_ingestion, daemon=True)
    thread.start()

    return jsonify({
        "task_id": task_id,
        "status": "queued",
        "adapter_type": adapter_type,
        "message": f"Ingestion task started for {adapter_type}",
    }), 202


@api_bp.route("/analyze", methods=["POST"])
def trigger_analysis():
    """Trigger NLP analysis on tickets.

    Runs analysis synchronously for small batches or in a background
    thread for larger datasets.  Returns a task ID for tracking.
    """
    try:
        payload = request.get_json(silent=True) or {}
        data = _validate_schema(AnalyzeRequestSchema, payload)
    except Exception as exc:
        msg = exc.messages if hasattr(exc, "messages") else str(exc)
        return _json_error("validation_error", f"Invalid request: {msg}", 400)

    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    task_id = str(uuid.uuid4())
    analysis_types = data.get("analysis_types") or [
        "classification", "sentiment", "topic", "duplicate",
        "anomaly", "summary", "ner", "root_cause",
    ]
    force_refresh = data.get("force_refresh", False)

    # Determine which tickets to analyse
    ticket_ids = data.get("ticket_ids")
    if not ticket_ids:
        # Analyse all tickets that haven't been analysed yet (or all if force_refresh)
        try:
            from ticketinsight.storage.database import Ticket, TicketInsight

            query = Ticket.query
            if not force_refresh:
                analysed_subquery = db_mgr._app.app_context() and (
                    db_mgr._app.app_context() or True
                )
                # Get tickets with no insights
                sub = TicketInsight.query.with_entities(
                    TicketInsight.ticket_id
                ).distinct().subquery()
                query = Ticket.query.outerjoin(
                    sub, Ticket.id == sub.c.ticket_id
                ).filter(sub.c.ticket_id.is_(None))

            tickets = query.limit(500).all()
            ticket_ids = [t.id for t in tickets]
        except Exception as exc:
            logger.error("Failed to get ticket list for analysis: %s", exc)
            return _json_error("database_error", f"Failed to get tickets: {exc}", 500)

    with _task_lock:
        _task_registry[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "analysis_types": analysis_types,
            "tickets_to_analyze": len(ticket_ids),
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "message": f"Analysis queued for {len(ticket_ids)} tickets",
        }

    def _run_analysis():
        with _task_lock:
            _task_registry[task_id]["status"] = "running"

        try:
            with current_app.app_context():
                try:
                    from ticketinsight.nlp import NLPEngine
                except ImportError:
                    with _task_lock:
                        _task_registry[task_id].update({
                            "status": "failed",
                            "message": "NLP module not available. Install spaCy and other NLP dependencies.",
                        })
                    return

                nlp = NLPEngine()
                config = _get_config()
                if config:
                    nlp_config = config.get_section("nlp")
                    nlp.configure(nlp_config)

                analyzed = 0
                errors = 0
                for tid in ticket_ids:
                    try:
                        from ticketinsight.storage.database import Ticket
                        ticket = Ticket.query.get(tid)
                        if ticket is None:
                            continue

                        text = f"{ticket.title} {ticket.description}"
                        result = nlp.analyze(text)

                        if result:
                            update_data = {
                                "insight_type": "classification",
                                "insight_data": result,
                                "confidence": result.get("confidence", 0.0),
                            }
                            # Map NLP results to ticket fields
                            if "sentiment" in result:
                                update_data["sentiment_score"] = result["sentiment"].get("score", 0.0)
                                update_data["sentiment_label"] = result["sentiment"].get("label", "Neutral")
                            if "classification" in result:
                                update_data["predicted_category"] = result["classification"].get("category", "")
                            if "topic" in result:
                                update_data["topic_cluster"] = result["topic"].get("cluster")
                            if "anomaly" in result:
                                update_data["anomaly_score"] = result["anomaly"].get("score", 0.0)
                            if "summary" in result:
                                update_data["summary"] = result["summary"].get("text", "")
                            if "ner" in result:
                                update_data["named_entities"] = result["ner"].get("entities", {})
                            if "root_cause" in result:
                                update_data["root_cause_cluster"] = result["root_cause"].get("cluster")

                            db_mgr.update_ticket_insights(str(ticket.ticket_id), update_data)
                            analyzed += 1

                    except Exception as e:
                        errors += 1
                        logger.warning("Failed to analyze ticket %s: %s", tid, e)

                    # Update progress periodically
                    if analyzed % 10 == 0:
                        progress = int((analyzed + errors) / len(ticket_ids) * 100)
                        with _task_lock:
                            _task_registry[task_id]["progress"] = progress

                with _task_lock:
                    _task_registry[task_id].update({
                        "status": "completed",
                        "message": f"Analysis completed: {analyzed} analyzed, {errors} errors",
                        "progress": 100,
                        "analyzed": analyzed,
                        "errors": errors,
                    })

                # Invalidate caches
                cache = _get_cache()
                if cache:
                    cache.invalidate_pattern("tickets:*")
                    cache.invalidate_pattern("stats:*")
                    cache.invalidate_pattern("insights:*")

        except Exception as exc:
            logger.error("Analysis task %s failed: %s", task_id, exc)
            with _task_lock:
                _task_registry[task_id].update({
                    "status": "failed",
                    "message": f"Analysis failed: {str(exc)}",
                })

    thread = threading.Thread(target=_run_analysis, daemon=True)
    thread.start()

    return jsonify({
        "task_id": task_id,
        "status": "queued",
        "tickets_analyzed": len(ticket_ids),
        "analysis_types": analysis_types,
        "message": f"Analysis queued for {len(ticket_ids)} tickets",
    }), 202


# ---------------------------------------------------------------------------
# Insights endpoints
# ---------------------------------------------------------------------------


@api_bp.route("/insights/summary", methods=["GET"])
def get_insights_summary():
    """Get high-level insights summary for the dashboard.

    Returns aggregate statistics, distributions, and key metrics.
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    # Try cache first
    cache = _get_cache()
    if cache:
        cached = cache.get("insights:summary")
        if cached is not None:
            return jsonify(cached)

    try:
        stats = db_mgr.get_statistics()
        summary = {
            "total_tickets": stats.get("total_tickets", 0),
            "open_tickets": stats.get("by_status", {}).get("Open", 0),
            "in_progress_tickets": stats.get("by_status", {}).get("In Progress", 0),
            "on_hold_tickets": stats.get("by_status", {}).get("On Hold", 0),
            "resolved_tickets": stats.get("by_status", {}).get("Resolved", 0),
            "closed_tickets": stats.get("by_status", {}).get("Closed", 0),
            "critical_tickets": stats.get("by_priority", {}).get("Critical", 0),
            "high_tickets": stats.get("by_priority", {}).get("High", 0),
            "avg_resolution_time_hours": stats.get("avg_resolution_time_hours"),
            "avg_sentiment_score": stats.get("avg_sentiment_score", 0.0),
            "anomaly_count": stats.get("anomaly_count", 0),
            "duplicate_count": stats.get("duplicate_count", 0),
            "opened_today": stats.get("opened_today", 0),
            "resolved_today": stats.get("resolved_today", 0),
            "category_distribution": stats.get("by_category", {}),
            "priority_distribution": stats.get("by_priority", {}),
            "status_distribution": stats.get("by_status", {}),
            "sentiment_distribution": stats.get("sentiment_distribution", {}),
            "assignment_group_distribution": stats.get("by_assignment_group", {}),
            "source_system_distribution": stats.get("by_source_system", {}),
            "tickets_with_insights": stats.get("tickets_with_insights", 0),
        }

        # Compute additional derived metrics
        total = summary["total_tickets"]
        if total > 0:
            summary["resolution_rate"] = round(
                (summary["resolved_tickets"] + summary["closed_tickets"]) / total * 100, 1
            )
            summary["open_rate"] = round(summary["open_tickets"] / total * 100, 1)
        else:
            summary["resolution_rate"] = 0.0
            summary["open_rate"] = 0.0

    except Exception as exc:
        logger.error("Failed to generate insights summary: %s", exc)
        return _json_error("database_error", f"Failed to generate summary: {exc}", 500)

    if cache:
        cache.set("insights:summary", summary, ttl=300)

    return jsonify(summary)


@api_bp.route("/insights/sentiment", methods=["GET"])
def get_sentiment_insights():
    """Get sentiment analysis insights and trends.

    Query Parameters
    ----------------
    date_from : str  (YYYY-MM-DD)
    date_to   : str  (YYYY-MM-DD)
    group_by  : str  (category, priority, assignee, status)
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    date_from_str = request.args.get("date_from")
    date_to_str = request.args.get("date_to")
    group_by = request.args.get("group_by", "category")

    valid_groups = ["category", "priority", "assignee", "status"]
    if group_by not in valid_groups:
        return _json_error(
            "validation_error",
            f"group_by must be one of {valid_groups}",
            400,
        )

    try:
        from ticketinsight.storage.database import Ticket, db

        query = Ticket.query
        if date_from_str:
            query = query.filter(Ticket.opened_at >= datetime.combine(
                datetime.strptime(date_from_str, "%Y-%m-%d").date(),
                datetime.min.time(),
            ))
        if date_to_str:
            query = query.filter(Ticket.opened_at <= datetime.combine(
                datetime.strptime(date_to_str, "%Y-%m-%d").date(),
                datetime.max.time(),
            ))

        tickets = query.all()

        # Overall sentiment stats
        sentiments = [t.sentiment_score for t in tickets if t.sentiment_score != 0.0]
        avg_sentiment = round(sum(sentiments) / len(sentiments), 4) if sentiments else 0.0

        sentiment_dist = {"Positive": 0, "Neutral": 0, "Negative": 0}
        for t in tickets:
            label = t.sentiment_label or "Neutral"
            if label in sentiment_dist:
                sentiment_dist[label] += 1

        # Grouped sentiment
        group_map = {
            "category": "category",
            "priority": "priority",
            "assignee": "assignee",
            "status": "status",
        }
        group_field = group_map[group_by]

        grouped = {}
        for t in tickets:
            key = getattr(t, group_field) or "Unknown"
            if key not in grouped:
                grouped[key] = {"scores": [], "count": 0}
            if t.sentiment_score != 0.0:
                grouped[key]["scores"].append(t.sentiment_score)
            grouped[key]["count"] += 1

        by_group = {}
        for key, val in grouped.items():
            scores = val["scores"]
            by_group[key] = {
                "count": val["count"],
                "avg_sentiment": round(sum(scores) / len(scores), 4) if scores else 0.0,
                "min_sentiment": round(min(scores), 4) if scores else 0.0,
                "max_sentiment": round(max(scores), 4) if scores else 0.0,
                "analyzed_count": len(scores),
            }

        result = {
            "total_analyzed": len(tickets),
            "avg_sentiment_score": avg_sentiment,
            "sentiment_distribution": sentiment_dist,
            "grouped_by": group_by,
            "by_group": by_group,
            "date_range": {
                "from": date_from_str,
                "to": date_to_str,
            },
        }

    except ValueError as exc:
        return _json_error("validation_error", f"Invalid date format: {exc}", 400)
    except Exception as exc:
        logger.error("Failed to generate sentiment insights: %s", exc)
        return _json_error("database_error", f"Failed to generate sentiment insights: {exc}", 500)

    return jsonify(result)


@api_bp.route("/insights/topics", methods=["GET"])
def get_topic_insights():
    """Get topic modeling insights.

    Returns topic distribution across all analysed tickets, top keywords
    per topic, and any available topic trend data.
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    try:
        from ticketinsight.storage.database import Ticket, TicketInsight, db

        # Get tickets that have topic clusters assigned
        tickets_with_topics = Ticket.query.filter(
            Ticket.topic_cluster.isnot(None)
        ).all()

        topic_dist = {}
        topic_examples = {}
        for t in tickets_with_topics:
            cluster = t.topic_cluster
            topic_dist[cluster] = topic_dist.get(cluster, 0) + 1
            if cluster not in topic_examples:
                topic_examples[cluster] = []
            if len(topic_examples[cluster]) < 3:
                topic_examples[cluster].append({
                    "ticket_id": t.ticket_id,
                    "title": t.title,
                    "category": t.category,
                })

        # Get topic insight data for keywords
        topic_insights = TicketInsight.query.filter_by(
            insight_type="topic"
        ).all()

        topic_keywords = {}
        for insight in topic_insights:
            data = insight.insight_data or {}
            cluster = data.get("cluster")
            if cluster is not None:
                topic_keywords[cluster] = data.get("keywords", [])

        # Format for response
        topics = []
        for cluster_id in sorted(topic_dist.keys()):
            topics.append({
                "cluster_id": cluster_id,
                "ticket_count": topic_dist[cluster_id],
                "percentage": round(topic_dist[cluster_id] / len(tickets_with_topics) * 100, 1)
                if tickets_with_topics else 0,
                "keywords": topic_keywords.get(cluster_id, []),
                "example_tickets": topic_examples.get(cluster_id, []),
            })

        total_ticket_count = Ticket.query.count()

        result = {
            "total_tickets_analyzed": total_ticket_count,
            "tickets_with_topics": len(tickets_with_topics),
            "coverage_rate": round(len(tickets_with_topics) / total_ticket_count * 100, 1)
            if total_ticket_count else 0,
            "num_topics": len(topic_dist),
            "topics": topics,
        }

    except Exception as exc:
        logger.error("Failed to generate topic insights: %s", exc)
        return _json_error("database_error", f"Failed to generate topic insights: {exc}", 500)

    return jsonify(result)


@api_bp.route("/insights/duplicates", methods=["GET"])
def get_duplicate_insights():
    """Get duplicate ticket analysis.

    Returns duplicate pairs, duplicate rate, and potential time savings.
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    try:
        from ticketinsight.storage.database import Ticket, TicketInsight, db

        total_tickets = Ticket.query.count()
        duplicates = Ticket.query.filter(Ticket.duplicate_of_id.isnot(None)).all()

        duplicate_pairs = []
        for dup in duplicates:
            original = Ticket.query.get(dup.duplicate_of_id)
            if original:
                duplicate_pairs.append({
                    "duplicate_id": dup.id,
                    "duplicate_ticket_id": dup.ticket_id,
                    "duplicate_title": dup.title,
                    "original_id": original.id,
                    "original_ticket_id": original.ticket_id,
                    "original_title": original.title,
                    "status": dup.status,
                })

        # Get duplicate insight data for similarity scores
        dup_insights = TicketInsight.query.filter_by(insight_type="duplicate").all()
        similarity_scores = [i.insight_data.get("similarity_score", 0.0) for i in dup_insights if i.insight_data]
        avg_similarity = round(sum(similarity_scores) / len(similarity_scores), 4) if similarity_scores else 0.0

        duplicate_rate = round(len(duplicates) / total_tickets * 100, 1) if total_tickets else 0

        # Estimate time savings (assume 30 min avg handling time per ticket)
        estimated_savings_hours = round(len(duplicates) * 0.5, 1)

        result = {
            "total_tickets": total_tickets,
            "duplicate_count": len(duplicates),
            "duplicate_rate": duplicate_rate,
            "average_similarity_score": avg_similarity,
            "estimated_time_savings_hours": estimated_savings_hours,
            "duplicate_pairs": duplicate_pairs[:100],  # Limit response size
        }

    except Exception as exc:
        logger.error("Failed to generate duplicate insights: %s", exc)
        return _json_error("database_error", f"Failed to generate duplicate insights: {exc}", 500)

    return jsonify(result)


@api_bp.route("/insights/anomalies", methods=["GET"])
def get_anomaly_insights():
    """Get anomaly detection results.

    Query Parameters
    ----------------
    threshold : float  (0.0 to 1.0, default 0.5)
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    try:
        threshold = float(request.args.get("threshold", 0.5))
        if not (0.0 <= threshold <= 1.0):
            return _json_error("validation_error", "threshold must be between 0.0 and 1.0", 400)
    except ValueError:
        return _json_error("validation_error", "threshold must be a valid float", 400)

    try:
        from ticketinsight.storage.database import Ticket, TicketInsight, db

        anomalies = Ticket.query.filter(Ticket.anomaly_score >= threshold).order_by(
            db.desc(Ticket.anomaly_score)
        ).all()

        anomaly_tickets = []
        for a in anomalies:
            anomaly_tickets.append({
                "id": a.id,
                "ticket_id": a.ticket_id,
                "title": a.title,
                "priority": a.priority,
                "status": a.status,
                "category": a.category,
                "anomaly_score": a.anomaly_score,
                "opened_at": a.opened_at.isoformat() if a.opened_at else None,
            })

        # Anomaly type distribution from insight data
        anomaly_insights = TicketInsight.query.filter_by(insight_type="anomaly").all()
        anomaly_types = {}
        for ins in anomaly_insights:
            data = ins.insight_data or {}
            atype = data.get("anomaly_type", "unknown")
            anomaly_types[atype] = anomaly_types.get(atype, 0) + 1

        total_tickets = Ticket.query.count()
        anomaly_rate = round(len(anomalies) / total_tickets * 100, 2) if total_tickets else 0

        # Score distribution
        score_ranges = {"0.5-0.6": 0, "0.6-0.7": 0, "0.7-0.8": 0, "0.8-0.9": 0, "0.9-1.0": 0}
        for a in anomalies:
            s = a.anomaly_score
            if 0.5 <= s < 0.6:
                score_ranges["0.5-0.6"] += 1
            elif 0.6 <= s < 0.7:
                score_ranges["0.6-0.7"] += 1
            elif 0.7 <= s < 0.8:
                score_ranges["0.7-0.8"] += 1
            elif 0.8 <= s < 0.9:
                score_ranges["0.8-0.9"] += 1
            else:
                score_ranges["0.9-1.0"] += 1

        result = {
            "threshold": threshold,
            "total_anomalies": len(anomalies),
            "anomaly_rate": anomaly_rate,
            "anomaly_types_distribution": anomaly_types,
            "score_distribution": score_ranges,
            "anomalies": anomaly_tickets[:200],
        }

    except Exception as exc:
        logger.error("Failed to generate anomaly insights: %s", exc)
        return _json_error("database_error", f"Failed to generate anomaly insights: {exc}", 500)

    return jsonify(result)


@api_bp.route("/insights/root-causes", methods=["GET"])
def get_root_cause_insights():
    """Get root cause analysis results.

    Returns root cause cluster distribution, top causes, and recommendations.
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    try:
        from ticketinsight.storage.database import Ticket, TicketInsight, db

        # Tickets with root cause clusters
        tickets_with_rc = Ticket.query.filter(
            Ticket.root_cause_cluster.isnot(None)
        ).all()

        cluster_dist = {}
        cluster_examples = {}
        for t in tickets_with_rc:
            cid = t.root_cause_cluster
            cluster_dist[cid] = cluster_dist.get(cid, 0) + 1
            if cid not in cluster_examples:
                cluster_examples[cid] = []
            if len(cluster_examples[cid]) < 3:
                cluster_examples[cid].append({
                    "ticket_id": t.ticket_id,
                    "title": t.title,
                    "category": t.category,
                })

        # Get root cause insight data for keywords/descriptions
        rc_insights = TicketInsight.query.filter_by(insight_type="root_cause").all()
        rc_details = {}
        for ins in rc_insights:
            data = ins.insight_data or {}
            cluster = data.get("cluster")
            if cluster is not None and cluster not in rc_details:
                rc_details[cluster] = {
                    "keywords": data.get("keywords", []),
                    "description": data.get("description", ""),
                    "recommendation": data.get("recommendation", ""),
                }

        # Build response sorted by frequency
        sorted_clusters = sorted(cluster_dist.items(), key=lambda x: x[1], reverse=True)
        root_causes = []
        for cid, count in sorted_clusters:
            details = rc_details.get(cid, {})
            root_causes.append({
                "cluster_id": cid,
                "ticket_count": count,
                "percentage": round(count / len(tickets_with_rc) * 100, 1)
                if tickets_with_rc else 0,
                "keywords": details.get("keywords", []),
                "description": details.get("description", f"Root cause cluster {cid}"),
                "recommendation": details.get("recommendation", ""),
                "example_tickets": cluster_examples.get(cid, []),
            })

        # Generate recommendations based on category frequency
        from collections import Counter
        categories = Counter(t.category for t in tickets_with_rc if t.category)
        recommendations = []
        for cat, cnt in categories.most_common(5):
            recommendations.append({
                "category": cat,
                "occurrences": cnt,
                "recommendation": _generate_root_cause_recommendation(cat, cnt, len(tickets_with_rc)),
            })

        result = {
            "total_tickets_analyzed": Ticket.query.count(),
            "tickets_with_root_causes": len(tickets_with_rc),
            "num_clusters": len(cluster_dist),
            "root_causes": root_causes,
            "recommendations": recommendations,
        }

    except Exception as exc:
        logger.error("Failed to generate root cause insights: %s", exc)
        return _json_error("database_error", f"Failed to generate root cause insights: {exc}", 500)

    return jsonify(result)


@api_bp.route("/insights/performance", methods=["GET"])
def get_performance_insights():
    """Get team/service performance insights.

    Returns resolution times by group, priority, SLA compliance,
    backlog trends, and workload distribution.
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    # Try cache first
    cache = _get_cache()
    if cache:
        cached = cache.get("insights:performance")
        if cached is not None:
            return jsonify(cached)

    try:
        from ticketinsight.storage.database import Ticket, db

        tickets = Ticket.query.all()

        # Resolution time by assignment group
        group_resolution = {}
        group_counts = {}
        for t in tickets:
            grp = t.assignment_group or "Unassigned"
            if grp not in group_resolution:
                group_resolution[grp] = []
                group_counts[grp] = 0
            group_counts[grp] += 1
            if t.opened_at and t.resolved_at:
                hours = (t.resolved_at - t.opened_at).total_seconds() / 3600.0
                group_resolution[grp].append(hours)

        by_group = {}
        for grp, times in group_resolution.items():
            avg = round(sum(times) / len(times), 2) if times else None
            median_time = sorted(times)[len(times) // 2] if times else None
            by_group[grp] = {
                "total_tickets": group_counts[grp],
                "resolved_tickets": len(times),
                "avg_resolution_hours": avg,
                "median_resolution_hours": round(median_time, 2) if median_time else None,
                "min_resolution_hours": round(min(times), 2) if times else None,
                "max_resolution_hours": round(max(times), 2) if times else None,
            }

        # Resolution time by priority
        priority_resolution = {}
        for t in tickets:
            pri = t.priority or "Unknown"
            if pri not in priority_resolution:
                priority_resolution[pri] = []
            if t.opened_at and t.resolved_at:
                hours = (t.resolved_at - t.opened_at).total_seconds() / 3600.0
                priority_resolution[pri].append(hours)

        by_priority = {}
        for pri, times in priority_resolution.items():
            by_priority[pri] = {
                "avg_resolution_hours": round(sum(times) / len(times), 2) if times else None,
                "resolved_count": len(times),
            }

        # SLA compliance (target: Critical < 4h, High < 8h, Medium < 24h, Low < 72h)
        sla_targets = {"Critical": 4, "High": 8, "Medium": 24, "Low": 72}
        sla_compliance = {}
        for pri, target_hours in sla_targets.items():
            resolved = priority_resolution.get(pri, [])
            if resolved:
                within_sla = sum(1 for h in resolved if h <= target_hours)
                sla_compliance[pri] = round(within_sla / len(resolved) * 100, 1)
            else:
                sla_compliance[pri] = None

        # Workload distribution (open tickets per group)
        open_by_group = {}
        for t in tickets:
            if t.status in ("Open", "In Progress"):
                grp = t.assignment_group or "Unassigned"
                open_by_group[grp] = open_by_group.get(grp, 0) + 1

        result = {
            "by_assignment_group": by_group,
            "by_priority": by_priority,
            "sla_compliance": sla_compliance,
            "sla_targets_hours": sla_targets,
            "workload_distribution": open_by_group,
            "total_teams": len(by_group),
        }

    except Exception as exc:
        logger.error("Failed to generate performance insights: %s", exc)
        return _json_error("database_error", f"Failed to generate performance insights: {exc}", 500)

    if cache:
        cache.set("insights:performance", result, ttl=300)

    return jsonify(result)


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@api_bp.route("/dashboard/statistics", methods=["GET"])
def get_dashboard_stats():
    """Get all statistics for the main dashboard display.

    Aggregates data from multiple sources for a single comprehensive response.
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    cache = _get_cache()
    if cache:
        cached = cache.get("dashboard:stats")
        if cached is not None:
            return jsonify(cached)

    try:
        stats = db_mgr.get_statistics()
        recent = db_mgr.get_recent_tickets(limit=10)

        result = {
            "statistics": stats,
            "recent_tickets": recent,
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    except Exception as exc:
        logger.error("Failed to generate dashboard stats: %s", exc)
        return _json_error("database_error", f"Failed to generate dashboard stats: {exc}", 500)

    if cache:
        cache.set("dashboard:stats", result, ttl=120)

    return jsonify(result)


@api_bp.route("/dashboard/trends", methods=["GET"])
def get_dashboard_trends():
    """Get trend data for charts.

    Query Parameters
    ----------------
    metric  : str  (volume, resolution_time, sentiment)
    period  : str  (daily, weekly, monthly)
    days    : int  (default 30)
    """
    db_mgr = _get_db()
    if db_mgr is None:
        return _json_error("service_unavailable", "Database not initialised", 503)

    metric = request.args.get("metric", "volume")
    period = request.args.get("period", "daily")
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return _json_error("validation_error", "days must be an integer", 400)

    valid_metrics = ["volume", "resolution_time", "sentiment"]
    valid_periods = ["daily", "weekly", "monthly"]

    if metric not in valid_metrics:
        return _json_error("validation_error", f"metric must be one of {valid_metrics}", 400)
    if period not in valid_periods:
        return _json_error("validation_error", f"period must be one of {valid_periods}", 400)

    cache = _get_cache()
    cache_key = f"trends:{metric}:{period}:{days}"
    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return jsonify(cached)

    try:
        from ticketinsight.storage.database import Ticket, db
        from collections import defaultdict

        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        if metric == "volume":
            tickets = Ticket.query.filter(Ticket.opened_at >= since).order_by(Ticket.opened_at).all()

            data_points = defaultdict(lambda: {"count": 0, "value": 0.0})
            for t in tickets:
                if t.opened_at is None:
                    continue
                if period == "daily":
                    key = t.opened_at.strftime("%Y-%m-%d")
                elif period == "weekly":
                    key = t.opened_at.strftime("%Y-W%W")
                else:
                    key = t.opened_at.strftime("%Y-%m")
                data_points[key]["count"] += 1

            result_data = [
                {"date": k, "value": v["count"], "count": v["count"]}
                for k, v in sorted(data_points.items())
            ]

        elif metric == "resolution_time":
            tickets = Ticket.query.filter(
                Ticket.opened_at >= since,
                Ticket.resolved_at.isnot(None),
            ).all()

            data_points = defaultdict(lambda: {"count": 0, "hours": []})
            for t in tickets:
                if t.opened_at and t.resolved_at:
                    hours = (t.resolved_at - t.opened_at).total_seconds() / 3600.0
                    if period == "daily":
                        key = t.resolved_at.strftime("%Y-%m-%d")
                    elif period == "weekly":
                        key = t.resolved_at.strftime("%Y-W%W")
                    else:
                        key = t.resolved_at.strftime("%Y-%m")
                    data_points[key]["count"] += 1
                    data_points[key]["hours"].append(hours)

            result_data = [
                {"date": k, "value": round(sum(v["hours"]) / len(v["hours"]), 2) if v["hours"] else 0, "count": v["count"]}
                for k, v in sorted(data_points.items())
            ]

        elif metric == "sentiment":
            tickets = Ticket.query.filter(
                Ticket.opened_at >= since,
                Ticket.sentiment_score != 0.0,
            ).all()

            data_points = defaultdict(lambda: {"count": 0, "scores": []})
            for t in tickets:
                if t.opened_at is None:
                    continue
                if period == "daily":
                    key = t.opened_at.strftime("%Y-%m-%d")
                elif period == "weekly":
                    key = t.opened_at.strftime("%Y-W%W")
                else:
                    key = t.opened_at.strftime("%Y-%m")
                data_points[key]["count"] += 1
                data_points[key]["scores"].append(t.sentiment_score)

            result_data = [
                {"date": k, "value": round(sum(v["scores"]) / len(v["scores"]), 4) if v["scores"] else 0, "count": v["count"]}
                for k, v in sorted(data_points.items())
            ]

        result = {
            "metric": metric,
            "period": period,
            "days": days,
            "data_points": result_data,
        }

    except Exception as exc:
        logger.error("Failed to generate trend data: %s", exc)
        return _json_error("database_error", f"Failed to generate trends: {exc}", 500)

    if cache:
        cache.set(cache_key, result, ttl=600)

    return jsonify(result)


# ---------------------------------------------------------------------------
# Adapter endpoints
# ---------------------------------------------------------------------------


@api_bp.route("/adapter/status", methods=["GET"])
def get_adapter_status():
    """Get current adapter connection status."""
    config = _get_config()
    if config is None:
        return _json_error("service_unavailable", "Configuration not initialised", 503)

    try:
        configured_type = config.get("adapter", "type", "csv")

        status_info = {
            "configured_type": configured_type,
            "available_adapters": ["servicenow", "jira", "csv", "universal"],
            "connection_status": "not_configured",
            "last_error": None,
        }

        # Check adapter configuration completeness
        if configured_type == "servicenow":
            has_instance = bool(config.get("adapter", "snow_instance"))
            has_user = bool(config.get("adapter", "snow_username"))
            if has_instance and has_user:
                status_info["connection_status"] = "configured"
            else:
                status_info["connection_status"] = "incomplete"
                status_info["last_error"] = "Missing ServiceNow instance or credentials"

        elif configured_type == "jira":
            has_server = bool(config.get("adapter", "jira_server"))
            has_token = bool(config.get("adapter", "jira_api_token"))
            if has_server and has_token:
                status_info["connection_status"] = "configured"
            else:
                status_info["connection_status"] = "incomplete"
                status_info["last_error"] = "Missing Jira server URL or API token"

        elif configured_type == "csv":
            csv_path = config.get("adapter", "csv_file_path", "")
            if csv_path:
                status_info["connection_status"] = "configured"
                status_info["csv_file_path"] = csv_path
            else:
                status_info["connection_status"] = "incomplete"
                status_info["last_error"] = "No CSV file path configured"

        elif configured_type == "universal":
            status_info["connection_status"] = "configured"

    except Exception as exc:
        logger.error("Failed to get adapter status: %s", exc)
        return _json_error("internal_error", str(exc), 500)

    return jsonify(status_info)


@api_bp.route("/adapter/test", methods=["POST"])
def test_adapter():
    """Test adapter connection.

    Returns success status, latency in milliseconds, and a count of
    sample data items retrieved.
    """
    try:
        payload = request.get_json(silent=True) or {}
        data = _validate_schema(AdapterTestSchema, payload)
    except Exception as exc:
        msg = exc.messages if hasattr(exc, "messages") else str(exc)
        return _json_error("validation_error", str(msg), 400)

    adapter_type = data["adapter_type"]
    config = _get_config()
    if config is None:
        return _json_error("service_unavailable", "Configuration not initialised", 503)

    start_time = time.time()
    sample_count = 0
    success = False
    error_msg = None

    try:
        if adapter_type == "csv":
            csv_path = config.get("adapter", "csv_file_path", "")
            import os
            if csv_path and os.path.exists(csv_path):
                with open(csv_path, "r") as f:
                    sample_count = sum(1 for _ in f) - 1  # minus header
                    if sample_count < 0:
                        sample_count = 0
                success = True
            else:
                error_msg = f"CSV file not found: {csv_path}"

        elif adapter_type == "servicenow":
            instance = config.get("adapter", "snow_instance")
            if not instance:
                error_msg = "ServiceNow instance not configured"
            else:
                # Attempt a basic connectivity check
                import requests
                url = f"https://{instance}/api/now/table/incident?sysparm_limit=1"
                user = config.get("adapter", "snow_username", "")
                pwd = config.get("adapter", "snow_password", "")
                resp = requests.get(url, auth=(user, pwd), timeout=10)
                if resp.status_code == 200:
                    sample_count = resp.json().get("result", [])
                    success = True
                else:
                    error_msg = f"ServiceNow returned HTTP {resp.status_code}"

        elif adapter_type == "jira":
            server = config.get("adapter", "jira_server")
            if not server:
                error_msg = "Jira server not configured"
            else:
                import requests
                token = config.get("adapter", "jira_api_token", "")
                user = config.get("adapter", "jira_username", "")
                url = f"{server}/rest/api/2/search?maxResults=1"
                resp = requests.get(
                    url,
                    headers={"Authorization": f"Basic {_encode_basic(user, token)}"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    sample_count = data.get("total", 0)
                    success = True
                else:
                    error_msg = f"Jira returned HTTP {resp.status_code}"

        elif adapter_type == "universal":
            success = True
            sample_count = 0

    except Exception as exc:
        error_msg = str(exc)

    latency_ms = round((time.time() - start_time) * 1000, 2)

    return jsonify({
        "success": success,
        "adapter_type": adapter_type,
        "latency_ms": latency_ms,
        "sample_data_count": sample_count,
        "error": error_msg,
    })


# ---------------------------------------------------------------------------
# Configuration endpoints
# ---------------------------------------------------------------------------


@api_bp.route("/config", methods=["GET"])
def get_config():
    """Get non-sensitive configuration values.

    Returns all configuration sections except those containing
    credentials or secrets.
    """
    config = _get_config()
    if config is None:
        return _json_error("service_unavailable", "Configuration not initialised", 503)

    try:
        all_config = config.get_all()

        # Redact sensitive fields
        sensitive_keys = {
            "password", "secret", "token", "api_key", "api_token",
            "snow_password", "jira_api_token", "secret_key",
        }

        safe_config = {}
        for section, values in all_config.items():
            safe_section = {}
            for key, value in values.items():
                if any(sk in key.lower() for sk in sensitive_keys):
                    if value:
                        safe_section[key] = "********"
                    else:
                        safe_section[key] = value
                else:
                    safe_section[key] = value
            safe_config[section] = safe_section

    except Exception as exc:
        logger.error("Failed to get config: %s", exc)
        return _json_error("internal_error", str(exc), 500)

    return jsonify(safe_config)


@api_bp.route("/config", methods=["PUT"])
def update_config():
    """Update non-sensitive configuration fields at runtime.

    Does not persist changes to disk.  Only allows updating a safe
    whitelist of fields.
    """
    try:
        payload = request.get_json(silent=True) or {}
        data = _validate_schema(ConfigUpdateSchema, payload)
    except Exception as exc:
        msg = exc.messages if hasattr(exc, "messages") else str(exc)
        return _json_error("validation_error", str(msg), 400)

    config = _get_config()
    if config is None:
        return _json_error("service_unavailable", "Configuration not initialised", 503)

    updated_fields = []

    try:
        if "adapter_type" in data:
            config.set("adapter", "type", data["adapter_type"])
            updated_fields.append("adapter.type")

        if "pipeline_interval_minutes" in data:
            config.set("pipeline", "interval_minutes", data["pipeline_interval_minutes"])
            updated_fields.append("pipeline.interval_minutes")

        if "cache_ttl" in data:
            config.set("redis", "cache_ttl", data["cache_ttl"])
            updated_fields.append("redis.cache_ttl")

        if "log_level" in data:
            config.set("logging", "level", data["log_level"])
            updated_fields.append("logging.level")
            # Also update the logger level at runtime
            from ticketinsight.utils.logger import configure_logging
            configure_logging(level=data["log_level"])

        if "csv_file_path" in data:
            config.set("adapter", "csv_file_path", data["csv_file_path"])
            updated_fields.append("adapter.csv_file_path")

        if "batch_size" in data:
            config.set("adapter", "batch_size", data["batch_size"])
            updated_fields.append("adapter.batch_size")

    except Exception as exc:
        return _json_error("internal_error", f"Failed to update config: {exc}", 500)

    # Audit log
    db_mgr = _get_db()
    if db_mgr and updated_fields:
        db_mgr.create_audit_log(
            action="config.update",
            entity_type="config",
            details={"updated_fields": updated_fields},
        )

    return jsonify({
        "message": "Configuration updated",
        "updated_fields": updated_fields,
    })


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------


@api_bp.route("/pipeline/status", methods=["GET"])
def get_pipeline_status():
    """Get pipeline scheduler status."""
    scheduler = current_app.extensions.get("pipeline_scheduler")

    if scheduler is None:
        return jsonify({
            "running": False,
            "interval_minutes": 0,
            "last_run": None,
            "next_run": None,
            "total_runs": 0,
            "last_run_status": None,
            "enabled_modules": [],
            "message": "Pipeline scheduler not initialised",
        })

    try:
        config = _get_config()
        enabled_modules = []
        if config:
            pipeline_config = config.get_section("pipeline")
            module_map = {
                "enable_sentiment": "sentiment",
                "enable_classification": "classification",
                "enable_topic_modeling": "topic_modeling",
                "enable_duplicate_detection": "duplicate_detection",
                "enable_anomaly_detection": "anomaly_detection",
                "enable_summarization": "summarization",
                "enable_ner": "ner",
                "enable_root_cause": "root_cause",
            }
            for key, name in module_map.items():
                if pipeline_config.get(key, False):
                    enabled_modules.append(name)

        status = {
            "running": getattr(scheduler, "running", False),
            "interval_minutes": getattr(scheduler, "interval_minutes",
                                        config.get("pipeline", "interval_minutes", 30) if config else 30),
            "last_run": getattr(scheduler, "last_run", None),
            "next_run": getattr(scheduler, "next_run", None),
            "total_runs": getattr(scheduler, "total_runs", 0),
            "last_run_status": getattr(scheduler, "last_run_status", None),
            "enabled_modules": enabled_modules,
        }

    except Exception as exc:
        logger.error("Failed to get pipeline status: %s", exc)
        return _json_error("internal_error", str(exc), 500)

    return jsonify(status)


@api_bp.route("/pipeline/run", methods=["POST"])
def run_pipeline():
    """Manually trigger a pipeline execution."""
    try:
        from ticketinsight.pipeline import PipelineScheduler
    except ImportError:
        return _json_error(
            "service_unavailable",
            "Pipeline module not available. Install full dependencies.",
            503,
        )

    task_id = str(uuid.uuid4())

    with _task_lock:
        _task_registry[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "type": "pipeline_run",
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "message": "Pipeline run queued",
        }

    def _run_pipeline_task():
        with _task_lock:
            _task_registry[task_id]["status"] = "running"

        try:
            with current_app.app_context():
                config = _get_config()
                pipeline = PipelineScheduler()
                if config:
                    pipeline.configure(config.get_section("pipeline"))
                pipeline.run_once()

                with _task_lock:
                    _task_registry[task_id].update({
                        "status": "completed",
                        "message": "Pipeline run completed successfully",
                        "progress": 100,
                    })

                # Invalidate caches
                cache = _get_cache()
                if cache:
                    cache.invalidate_pattern("*")

                db_mgr = _get_db()
                if db_mgr:
                    db_mgr.create_audit_log(
                        action="pipeline.run",
                        entity_type="pipeline",
                    )

        except Exception as exc:
            logger.error("Pipeline task %s failed: %s", task_id, exc)
            with _task_lock:
                _task_registry[task_id].update({
                    "status": "failed",
                    "message": f"Pipeline run failed: {str(exc)}",
                })

    thread = threading.Thread(target=_run_pipeline_task, daemon=True)
    thread.start()

    return jsonify({
        "task_id": task_id,
        "status": "queued",
        "message": "Pipeline run triggered",
    }), 202


# ---------------------------------------------------------------------------
# Task tracking
# ---------------------------------------------------------------------------


@api_bp.route("/tasks/<task_id>", methods=["GET"])
def get_task_status(task_id):
    """Check the status of a background task (ingestion, analysis, pipeline)."""
    with _task_lock:
        task = _task_registry.get(task_id)

    if task is None:
        return _json_error("not_found", f"Task {task_id} not found", 404)

    return jsonify(task)


@api_bp.route("/tasks", methods=["GET"])
def list_tasks():
    """List all background tasks."""
    with _task_lock:
        tasks = list(_task_registry.values())

    # Sort by created_at descending
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)

    return jsonify({
        "total_tasks": len(tasks),
        "tasks": tasks,
    })


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _generate_root_cause_recommendation(category: str, count: int, total: int) -> str:
    """Generate a simple recommendation based on root cause category frequency."""
    pct = round(count / total * 100, 1) if total else 0

    recommendations = {
        "Network": f"{pct}% of root-caused tickets relate to network issues. "
                   "Consider investing in network infrastructure upgrades, "
                   "implementing proactive monitoring, and creating self-service "
                   "VPN troubleshooting guides.",
        "Hardware": f"{pct}% of root-caused tickets are hardware-related. "
                    "Evaluate hardware lifecycle management, implement predictive "
                    "maintenance, and standardise equipment to reduce variety.",
        "Software": f"{pct}% of root-caused tickets involve software issues. "
                    "Review software deployment processes, improve compatibility "
                    "testing, and create knowledge articles for common issues.",
        "Email": f"{pct}% of root-caused tickets are email-related. "
                 "Review email system configuration, improve user training, "
                 "and implement automated provisioning/deprovisioning.",
        "Security": f"{pct}% of root-caused tickets involve security. "
                    "Strengthen security awareness training, implement MFA "
                    "across all systems, and enhance phishing detection.",
        "Access Management": f"{pct}% of root-caused tickets involve access issues. "
                             "Automate account provisioning workflows, implement "
                             "role-based access controls, and streamline approval processes.",
        "Database": f"{pct}% of root-caused tickets involve database issues. "
                    "Review query optimisation, implement connection pooling, "
                    "and schedule regular maintenance windows.",
    }

    return recommendations.get(category, f"{pct}% of root-caused tickets fall under '{category}'. "
                                       "Investigate patterns and create targeted knowledge articles.")


def _encode_basic(username: str, token: str) -> str:
    """Encode username:token for HTTP Basic Auth."""
    import base64
    return base64.b64encode(f"{username}:{token}".encode()).decode()
