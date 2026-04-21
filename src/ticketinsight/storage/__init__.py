"""
Storage package for TicketInsight Pro.

Provides the persistence layer:

- :class:`~ticketinsight.storage.database.DatabaseManager` — Flask-SQLAlchemy
  models and data-access methods for tickets, insights, audit logs, and
  dashboard configurations.
- :class:`~ticketinsight.storage.cache.CacheManager` — Redis-backed caching
  with automatic fallback to an in-memory dictionary.
"""

from ticketinsight.storage.database import (
    db,
    Ticket,
    TicketInsight,
    AuditLog,
    DashboardConfig,
    DatabaseManager,
)
from ticketinsight.storage.cache import CacheManager

__all__ = [
    "db",
    "Ticket",
    "TicketInsight",
    "AuditLog",
    "DashboardConfig",
    "DatabaseManager",
    "CacheManager",
]
