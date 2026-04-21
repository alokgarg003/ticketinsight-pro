"""
Data ingester for TicketInsight Pro.

Orchestrates ticket data ingestion from a configured adapter into the
database.  Supports full and incremental synchronisation with batch
processing, upsert semantics (insert-or-update by ``ticket_id``), and
comprehensive error handling and progress logging.

Usage
-----
    from ticketinsight.pipeline.ingester import DataIngester
    from ticketinsight.adapters import create_adapter

    adapter = create_adapter("csv", config={"file_path": "data/tickets.csv"})
    ingester = DataIngester(config, db_manager, adapter)
    result = ingester.ingest(limit=500)
"""

import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import chunk_list

__all__ = ["DataIngester"]


class DataIngester:
    """Orchestrates ticket data ingestion from a configured adapter.

    Reads tickets from the adapter, normalises them, and writes them to the
    database.  Existing tickets (matched by ``ticket_id``) are updated if
    the source ``updated_at`` is newer than the stored value.

    Parameters
    ----------
    config : ConfigManager
        Application configuration manager.
    db_manager : DatabaseManager
        Initialized database manager with an active Flask app context.
    adapter : BaseAdapter
        A connected adapter instance (ServiceNow, Jira, CSV, etc.).

    Attributes
    ----------
    batch_size : int
        Number of tickets to process per database transaction batch.
    last_sync_time : datetime | None
        Timestamp of the most recent successful sync.
    """

    def __init__(self, config: Any, db_manager: Any, adapter: Any) -> None:
        self.config = config
        self.db_manager = db_manager
        self.adapter = adapter
        self.logger = get_logger(__name__)

        # Configuration
        self.batch_size: int = int(
            config.get("adapter", "batch_size", 500)
            if hasattr(config, "get")
            else 500
        )
        self.last_sync_time: Optional[datetime] = None
        self._stats: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        query: Optional[str] = None,
        limit: int = 1000,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        full_sync: bool = False,
    ) -> Dict[str, Any]:
        """Run the ingestion pipeline.

        Steps:
            1. Connect the adapter (if not already connected).
            2. Fetch tickets from the adapter.
            3. Normalise each ticket (delegated to the adapter).
            4. For each ticket, check if it already exists in the DB.
            5. Insert new tickets; update existing tickets if newer.
            6. Record sync metadata and return statistics.

        Parameters
        ----------
        query : str | None
            Adapter-native query filter.
        limit : int
            Maximum number of tickets to ingest.
        date_from : datetime | None
            Ingest only tickets opened on or after this date.
        date_to : datetime | None
            Ingest only tickets opened on or before this date.
        full_sync : bool
            If ``True``, re-ingest all available tickets regardless of
            date range.  Overrides ``date_from``/``date_to``.

        Returns
        -------
        dict
            ``{
                "total_fetched": int,
                "total_inserted": int,
                "total_updated": int,
                "total_skipped": int,
                "errors": list[str],
                "duration_seconds": float,
            }``
        """
        start_time = _time.monotonic()

        stats: Dict[str, Any] = {
            "total_fetched": 0,
            "total_inserted": 0,
            "total_updated": 0,
            "total_skipped": 0,
            "errors": [],
            "duration_seconds": 0.0,
        }

        self._log("info", "Starting ingestion pipeline (limit=%d, full_sync=%s)", limit, full_sync)

        # Step 1: Connect adapter
        try:
            connected = self.adapter.connect()
            if not connected:
                raise ConnectionError("Adapter connection failed")
        except Exception as exc:
            msg = f"Adapter connection error: {exc}"
            self._log("error", msg)
            stats["errors"].append(msg)
            stats["duration_seconds"] = round(_time.monotonic() - start_time, 3)
            return stats

        # Step 2: Fetch tickets
        fetch_date_from = date_from
        if not full_sync and fetch_date_from is None:
            fetch_date_from = self._get_last_sync_time()

        try:
            self._log("info", "Fetching tickets from adapter (query=%s, limit=%d)", query, limit)
            raw_tickets = self.adapter.fetch_tickets(
                query=query,
                limit=limit,
                offset=0,
                date_from=None if full_sync else fetch_date_from,
                date_to=date_to,
            )
            stats["total_fetched"] = len(raw_tickets)
            self._log("info", "Fetched %d tickets from adapter", len(raw_tickets))
        except Exception as exc:
            msg = f"Error fetching tickets: {exc}"
            self._log("error", msg)
            stats["errors"].append(msg)
            stats["duration_seconds"] = round(_time.monotonic() - start_time, 3)
            return stats

        if not raw_tickets:
            self._log("info", "No tickets fetched from adapter")
            stats["duration_seconds"] = round(_time.monotonic() - start_time, 3)
            self._record_sync(stats)
            return stats

        # Step 3–5: Process in batches
        batch_idx = 0
        for batch in chunk_list(raw_tickets, self.batch_size):
            batch_idx += 1
            self._log(
                "info",
                "Processing batch %d (%d tickets)",
                batch_idx,
                len(batch),
            )
            batch_result = self._process_batch(batch)
            stats["total_inserted"] += batch_result["inserted"]
            stats["total_updated"] += batch_result["updated"]
            stats["total_skipped"] += batch_result["skipped"]
            stats["errors"].extend(batch_result["errors"])

        # Step 6: Record sync and finalise
        self._record_sync(stats)
        stats["duration_seconds"] = round(_time.monotonic() - start_time, 3)
        self._log(
            "info",
            "Ingestion complete: %d fetched, %d inserted, %d updated, "
            "%d skipped, %d errors (%.2fs)",
            stats["total_fetched"],
            stats["total_inserted"],
            stats["total_updated"],
            stats["total_skipped"],
            len(stats["errors"]),
            stats["duration_seconds"],
        )

        self._stats = stats
        return stats

    def incremental_sync(self) -> Dict[str, Any]:
        """Fetch only tickets updated since the last successful sync.

        Returns
        -------
        dict
            Ingestion statistics (same format as :meth:`ingest`).
        """
        date_from, date_to = self._calculate_sync_range()
        self._log("info", "Running incremental sync: %s → %s", date_from, date_to)

        return self.ingest(
            date_from=date_from,
            date_to=date_to,
            full_sync=False,
        )

    def get_last_stats(self) -> Dict[str, Any]:
        """Return the statistics from the most recent ingestion run.

        Returns
        -------
        dict
        """
        return self._stats

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _process_batch(self, batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process a batch of normalised tickets into the database.

        Parameters
        ----------
        batch : list[dict]
            List of normalised ticket dictionaries.

        Returns
        -------
        dict
            ``{"inserted": int, "updated": int, "skipped": int, "errors": list[str]}``
        """
        result: Dict[str, Any] = {
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
        }

        try:
            from ticketinsight.storage.database import db, Ticket

            app = self.db_manager._app
            if app is None:
                raise RuntimeError("DatabaseManager not initialised")

            with app.app_context():
                for ticket_data in batch:
                    try:
                        ticket_id = ticket_data.get("ticket_id")
                        if not ticket_id:
                            result["skipped"] += 1
                            continue

                        # Check for existing ticket
                        existing = Ticket.query.filter_by(ticket_id=ticket_id).first()

                        if existing is None:
                            # Insert new ticket
                            self._insert_ticket(ticket_data)
                            result["inserted"] += 1
                        else:
                            # Check if update is needed
                            if self._should_update(existing, ticket_data):
                                self._update_ticket(existing, ticket_data)
                                result["updated"] += 1
                            else:
                                result["skipped"] += 1

                    except Exception as exc:
                        error_msg = f"Error processing ticket {ticket_data.get('ticket_id', '?')}: {exc}"
                        self._log("error", error_msg)
                        result["errors"].append(error_msg)

                # Commit the entire batch
                db.session.commit()

        except Exception as exc:
            error_msg = f"Batch processing error: {exc}"
            self._log("error", error_msg)
            result["errors"].append(error_msg)

            # Try to roll back on failure
            try:
                from ticketinsight.storage.database import db
                db.session.rollback()
            except Exception:
                pass

        return result

    @staticmethod
    def _insert_ticket(ticket_data: Dict[str, Any]) -> None:
        """Create a new Ticket ORM object and add it to the session.

        Parameters
        ----------
        ticket_data : dict
            Normalised ticket dictionary.
        """
        from ticketinsight.storage.database import Ticket

        # Convert datetime strings back to datetime objects if needed
        opened_at = ticket_data.get("opened_at")
        if isinstance(opened_at, str):
            from ticketinsight.utils.helpers import parse_date
            opened_at = parse_date(opened_at)

        resolved_at = ticket_data.get("resolved_at")
        if isinstance(resolved_at, str):
            from ticketinsight.utils.helpers import parse_date
            resolved_at = parse_date(resolved_at)

        closed_at = ticket_data.get("closed_at")
        if isinstance(closed_at, str):
            from ticketinsight.utils.helpers import parse_date
            closed_at = parse_date(closed_at)

        updated_at = ticket_data.get("updated_at")
        if isinstance(updated_at, str):
            from ticketinsight.utils.helpers import parse_date
            updated_at = parse_date(updated_at)

        ticket = Ticket(
            ticket_id=ticket_data.get("ticket_id", ""),
            title=ticket_data.get("title", "Untitled"),
            description=ticket_data.get("description", ""),
            priority=ticket_data.get("priority", "Medium"),
            status=ticket_data.get("status", "Open"),
            category=ticket_data.get("category", ""),
            assignment_group=ticket_data.get("assignment_group", ""),
            assignee=ticket_data.get("assignee", ""),
            opened_at=opened_at,
            resolved_at=resolved_at,
            closed_at=closed_at,
            updated_at=updated_at,
            source_system=ticket_data.get("source_system", "unknown"),
            raw_data=ticket_data.get("raw_data", {}),
        )

        from ticketinsight.storage.database import db
        db.session.add(ticket)

    @staticmethod
    def _update_ticket(existing: Any, ticket_data: Dict[str, Any]) -> None:
        """Update an existing Ticket with new data.

        Parameters
        ----------
        existing : Ticket
            Existing ORM model instance.
        ticket_data : dict
            Normalised ticket dictionary with updated values.
        """
        # Update mutable fields
        fields_to_update = [
            "title", "description", "priority", "status", "category",
            "assignment_group", "assignee", "opened_at", "resolved_at",
            "closed_at", "updated_at", "raw_data",
        ]

        for field in fields_to_update:
            new_value = ticket_data.get(field)
            if new_value is not None:
                # Convert datetime strings
                if field in ("opened_at", "resolved_at", "closed_at", "updated_at"):
                    if isinstance(new_value, str):
                        from ticketinsight.utils.helpers import parse_date
                        new_value = parse_date(new_value)
                setattr(existing, field, new_value)

    @staticmethod
    def _should_update(existing: Any, ticket_data: Dict[str, Any]) -> bool:
        """Determine whether an existing ticket should be updated.

        A ticket is updated if:
            - The source ``updated_at`` is newer than the stored ``updated_at``, OR
            - The stored ``updated_at`` is ``None`` and the source has a value, OR
            - The status or priority has changed.

        Parameters
        ----------
        existing : Ticket
            Existing ORM model instance.
        ticket_data : dict
            New normalised ticket data.

        Returns
        -------
        bool
        """
        source_updated = ticket_data.get("updated_at")

        # Handle string dates
        if isinstance(source_updated, str):
            from ticketinsight.utils.helpers import parse_date
            source_updated = parse_date(source_updated)

        stored_updated = existing.updated_at

        # If source has a newer updated_at, we should update
        if source_updated is not None:
            if stored_updated is None:
                return True
            if source_updated > stored_updated:
                return True

        # Check for status or priority changes
        new_status = ticket_data.get("status", "")
        new_priority = ticket_data.get("priority", "")

        if new_status and new_status != existing.status:
            return True
        if new_priority and new_priority != existing.priority:
            return True

        return False

    def _get_last_sync_time(self) -> Optional[datetime]:
        """Return the timestamp of the last successful sync.

        Returns
        -------
        datetime | None
        """
        if self.last_sync_time is not None:
            return self.last_sync_time
        return None

    def _calculate_sync_range(self) -> tuple:
        """Determine the date range for incremental sync.

        Returns
        -------
        tuple
            ``(date_from, date_to)`` where each element is a ``datetime``
            or ``None``.  ``date_from`` is set to the last sync time if
            available; ``date_to`` is always ``None`` (up to now).
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        date_from = self._get_last_sync_time()
        date_to = now
        return date_from, date_to

    def _record_sync(self, stats: Dict[str, Any]) -> None:
        """Record the sync metadata for future incremental syncs.

        Parameters
        ----------
        stats : dict
            Ingestion statistics.
        """
        self.last_sync_time = datetime.now(timezone.utc).replace(tzinfo=None)
        self._stats = stats

    def _log(self, level: str, msg: str, *args: Any) -> None:
        """Internal logging helper."""
        getattr(self.logger, level)(msg, *args)
