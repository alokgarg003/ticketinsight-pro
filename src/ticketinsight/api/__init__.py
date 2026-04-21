"""
API package for TicketInsight Pro.

Provides the Flask REST API blueprint with all endpoint routes,
request/response schemas, and validation logic.

Modules
-------
models   : Marshmallow request/response schemas
routes   : Flask blueprint with all API endpoints
"""

from ticketinsight.api.models import (
    TicketFilterSchema,
    IngestRequestSchema,
    AnalyzeRequestSchema,
    TicketSchema,
    InsightSchema,
    PaginatedResponseSchema,
    ErrorResponseSchema,
)


def create_blueprint():
    """Create and return the API blueprint.

    Imports the routes module (which registers endpoints on the blueprint)
    and returns the fully-configured ``api_bp``.

    Returns
    -------
    flask.Blueprint
        The API blueprint with URL prefix ``/api/v1``.
    """
    from ticketinsight.api.routes import api_bp
    return api_bp


__all__ = [
    "create_blueprint",
    "TicketFilterSchema",
    "IngestRequestSchema",
    "AnalyzeRequestSchema",
    "TicketSchema",
    "InsightSchema",
    "PaginatedResponseSchema",
    "ErrorResponseSchema",
]
