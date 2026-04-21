"""
Utility package for TicketInsight Pro.

Provides common helpers used across the application:
    - :func:`~ticketinsight.utils.logger.get_logger`  — structured logging
    - :func:`~ticketinsight.utils.helpers.sanitize_text` — text cleaning
    - :class:`~ticketinsight.utils.helpers.retry_on_failure` — retry decorator
"""

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import (
    sanitize_text,
    normalize_priority,
    normalize_status,
    parse_date,
    chunk_list,
    calculate_hash,
    time_ago,
    truncate,
    slugify,
    retry_on_failure,
)

__all__ = [
    "get_logger",
    "sanitize_text",
    "normalize_priority",
    "normalize_status",
    "parse_date",
    "chunk_list",
    "calculate_hash",
    "time_ago",
    "truncate",
    "slugify",
    "retry_on_failure",
]
