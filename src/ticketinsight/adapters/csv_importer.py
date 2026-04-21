"""
CSV / Excel importer adapter for TicketInsight Pro.

Reads ticket data from CSV (``.csv``, ``.tsv``, ``.txt``) or Excel
(``.xlsx``, ``.xls``) files and normalises it into the canonical schema.
Supports custom column mappings, encoding auto-detection, and configurable
date formats.

Configuration keys
------------------
``file_path``    (str, required) — Path to the CSV or Excel file.
``column_map``   (dict, optional) — Mapping of source columns to canonical
    field names, e.g. ``{"Incident Number": "ticket_id", "Description": "description"}``.
``date_format``  (str, optional) — ``strftime`` format string for parsing dates.
``delimiter``    (str, optional) — CSV delimiter (default auto-detect via ``csv.Sniffer``).
``encoding``     (str, optional) — File encoding (default auto-detect).
``sheet_name``   (str | int, optional) — Excel sheet name or index (default 0).
``skip_rows``    (int, optional) — Number of header rows to skip (default 0).
``batch_size``   (int, optional) — Rows to process per batch (default 1000).

Usage
-----
    from ticketinsight.adapters import CSVImporterAdapter

    adapter = CSVImporterAdapter({
        "file_path": "data/tickets.csv",
        "column_map": {
            "Ticket #": "ticket_id",
            "Short Desc": "title",
            "Long Desc": "description",
            "Priority": "priority",
            "Status": "status",
        },
    })
    adapter.connect()
    tickets = adapter.fetch_tickets()
    adapter.close()
"""

import csv
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ticketinsight.adapters.base import BaseAdapter
from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import (
    sanitize_text,
    normalize_priority,
    normalize_status,
    parse_date,
)

__all__ = ["CSVImporterAdapter"]


class CSVImporterAdapter(BaseAdapter):
    """Adapter for importing ticket data from CSV and Excel files.

    Handles encoding issues gracefully by trying ``utf-8``, ``latin-1``,
    and ``cp1252`` in sequence.  Empty rows are skipped and required
    fields (``ticket_id``, ``title``) are validated.
    """

    # Canonical fields that are considered required for a valid ticket
    REQUIRED_FIELDS = {"ticket_id", "title"}

    # The set of canonical field names
    CANONICAL_FIELDS = {
        "ticket_id", "title", "description", "priority", "status",
        "category", "assignment_group", "assignee", "opened_at",
        "resolved_at", "closed_at", "updated_at", "source_system",
        "affected_service", "caller",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.file_path: str = config.get("file_path", "")
        self.column_map: Dict[str, str] = config.get("column_map", {})
        self.date_format: Optional[str] = config.get("date_format")
        self.delimiter: Optional[str] = config.get("delimiter")
        self.encoding: Optional[str] = config.get("encoding")
        self.sheet_name: Any = config.get("sheet_name", 0)
        self.skip_rows: int = int(config.get("skip_rows", 0))
        self.batch_size: int = int(config.get("batch_size", 1000))
        self._connected: bool = False
        self._file_handle: Any = None
        self._dataframe: Any = None
        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Validate that the configured file exists and is readable.

        Returns
        -------
        bool
            ``True`` if the file exists and can be read.
        """
        self._log("info", "Connecting to CSV/Excel file at %s ...", self.file_path)

        if not self.file_path:
            self._log("error", "File path is not configured")
            return False

        path = Path(self.file_path)
        if not path.exists():
            self._log("error", "File not found: %s", self.file_path)
            return False

        if not path.is_file():
            self._log("error", "Path is not a file: %s", self.file_path)
            return False

        # Check readability by attempting to read the first bytes
        try:
            file_size = path.stat().st_size
            if file_size == 0:
                self._log("error", "File is empty: %s", self.file_path)
                return False

            self._connected = True
            self._log(
                "info",
                "File connection established: %s (%s bytes, %s)",
                self.file_path,
                file_size,
                path.suffix.lower(),
            )
            return True

        except PermissionError:
            self._log("error", "Permission denied: %s", self.file_path)
            return False
        except OSError as exc:
            self._log("error", "OS error reading file: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Ticket fetching
    # ------------------------------------------------------------------

    def fetch_tickets(
        self,
        query: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Read the file, normalise columns, and return a list of ticket dicts.

        Parameters
        ----------
        query : str | None
            Ignored for file-based adapters (kept for API compatibility).
        limit : int
            Maximum number of tickets to return.
        offset : int
            Number of rows to skip.
        date_from : datetime | None
            If provided, filter tickets where ``opened_at >= date_from``.
        date_to : datetime | None
            If provided, filter tickets where ``opened_at <= date_to``.
        **kwargs
            Ignored.

        Returns
        -------
        list[dict]
            List of normalised ticket dictionaries.
        """
        if not self._connected:
            if not self.connect():
                self._log("error", "Cannot fetch tickets: file not connected")
                return []

        suffix = Path(self.file_path).suffix.lower()
        is_excel = suffix in (".xlsx", ".xls")

        if is_excel:
            rows = self._read_excel()
        else:
            rows = self._read_csv()

        if rows is None:
            return []

        total_rows = len(rows)
        self._log("info", "Read %d raw rows from file", total_rows)

        # Apply offset and limit
        rows = rows[offset: offset + limit]

        normalised_tickets: List[Dict[str, Any]] = []
        skipped = 0
        processed = 0

        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                skipped += 1
                continue

            # Skip completely empty rows
            if all(
                v is None or (isinstance(v, str) and v.strip() == "")
                for v in row.values()
            ):
                skipped += 1
                continue

            ticket = self.normalize_ticket(row)
            ticket["source_system"] = "csv"

            # Validate required fields
            if not ticket.get("ticket_id") or not ticket.get("title"):
                skipped += 1
                self._log(
                    "debug",
                    "Skipping row %d: missing ticket_id or title",
                    offset + idx,
                )
                continue

            # Apply date range filters
            opened_at = ticket.get("opened_at")
            if opened_at is not None:
                if date_from and opened_at < date_from:
                    skipped += 1
                    continue
                if date_to and opened_at > date_to:
                    skipped += 1
                    continue

            normalised_tickets.append(ticket)
            processed += 1

        self._log(
            "info",
            "Normalised %d tickets (skipped %d, total file rows %d)",
            processed,
            skipped,
            total_rows,
        )

        # Store progress info for callers that need it
        self._last_fetch_stats = {
            "total_rows": total_rows,
            "processed": processed,
            "skipped": skipped,
            "offset": offset,
            "limit": limit,
        }

        return normalised_tickets

    def fetch_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Search the file for a ticket matching the given ticket_id.

        Parameters
        ----------
        ticket_id : str
            The external ticket identifier to search for.

        Returns
        -------
        dict | None
            Normalised ticket, or ``None`` if not found.
        """
        # Fetch all tickets and find the match
        all_tickets = self.fetch_tickets(limit=100000)
        for ticket in all_tickets:
            if ticket.get("ticket_id") == ticket_id:
                return ticket
        self._log("info", "Ticket %s not found in file", ticket_id)
        return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Check file stats and readability.

        Returns
        -------
        dict
            ``{"status": "ok"|"error", "latency_ms": float, "message": str,
            "file_size": int, "file_path": str}``
        """
        import time as _time

        start = _time.monotonic()
        try:
            path = Path(self.file_path)
            if not path.exists():
                return {
                    "status": "error",
                    "latency_ms": 0.0,
                    "message": f"File not found: {self.file_path}",
                    "file_size": 0,
                    "file_path": self.file_path,
                }

            stat = path.stat()
            elapsed_ms = (_time.monotonic() - start) * 1000

            # Try to determine row/column count
            rows = 0
            columns = 0
            suffix = path.suffix.lower()
            is_excel = suffix in (".xlsx", ".xls")

            if is_excel:
                try:
                    df = self._load_excel_dataframe()
                    if df is not None:
                        rows, columns = df.shape
                except Exception:
                    pass
            else:
                try:
                    encoding = self._detect_encoding()
                    with open(path, "r", encoding=encoding, errors="replace") as f:
                        reader = csv.reader(f)
                        header = next(reader, None)
                        if header:
                            columns = len(header)
                        for _ in reader:
                            rows += 1
                except Exception:
                    pass

            return {
                "status": "ok",
                "latency_ms": round(elapsed_ms, 2),
                "message": (
                    f"File is readable ({rows} rows, {columns} columns, "
                    f"{stat.st_size:,} bytes)"
                ),
                "file_size": stat.st_size,
                "file_path": self.file_path,
                "rows": rows,
                "columns": columns,
            }

        except Exception as exc:
            elapsed_ms = (_time.monotonic() - start) * 1000
            return {
                "status": "error",
                "latency_ms": round(elapsed_ms, 2),
                "message": f"Health check failed: {exc}",
                "file_size": 0,
                "file_path": self.file_path,
            }

    # ------------------------------------------------------------------
    # CSV/Excel-specific normalisation
    # ------------------------------------------------------------------

    def normalize_ticket(self, raw_ticket: dict) -> dict:
        """Apply configured column mapping and normalise.

        If ``column_map`` is configured, source column names are mapped to
        canonical field names using it.  Otherwise, the base normaliser's
        alias-based detection is used.
        """
        if not raw_ticket or not isinstance(raw_ticket, dict):
            return {}

        # Apply custom column mapping first
        if self.column_map:
            mapped: Dict[str, Any] = {}
            for source_col, target_field in self.column_map.items():
                value = self._find_column_value(raw_ticket, source_col)
                if value is not None:
                    mapped[target_field] = value

            # Copy any columns that already use canonical names
            for key, value in raw_ticket.items():
                if key in self.CANONICAL_FIELDS and key not in mapped:
                    mapped[key] = value

            normalized = super().normalize_ticket(mapped)
        else:
            normalized = super().normalize_ticket(raw_ticket)

        # Apply custom date format if configured
        if self.date_format:
            for date_field in ("opened_at", "resolved_at", "closed_at", "updated_at"):
                val = normalized.get(date_field)
                if val is None:
                    # Try to find the raw value from the source
                    raw_val = raw_ticket.get(date_field) or raw_ticket.get(
                        self._reverse_column_map(date_field), None
                    )
                    if raw_val:
                        normalized[date_field] = parse_date(
                            str(raw_val), formats=[self.date_format]
                        )

        return normalized

    # ------------------------------------------------------------------
    # Internal helpers — file reading
    # ------------------------------------------------------------------

    def _detect_encoding(self) -> str:
        """Detect file encoding by trying common encodings in order.

        Returns
        -------
        str
            The first encoding that successfully decodes the file.
        """
        if self.encoding:
            return self.encoding

        encodings_to_try = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
        path = Path(self.file_path)

        for enc in encodings_to_try:
            try:
                with open(path, "r", encoding=enc) as f:
                    f.read(8192)
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue

        return "utf-8"

    def _detect_delimiter(self, sample: str) -> str:
        """Detect the CSV delimiter from a sample string.

        Parameters
        ----------
        sample : str
            A sample of the CSV content (typically the first few KB).

        Returns
        -------
        str
            Detected delimiter character.
        """
        if self.delimiter:
            return self.delimiter

        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except csv.Error:
            # Default to comma
            return ","

    def _read_csv(self) -> Optional[List[Dict[str, Any]]]:
        """Read a CSV/TSV file and return a list of row dictionaries.

        Returns
        -------
        list[dict] | None
            List of row dicts, or ``None`` on failure.
        """
        try:
            encoding = self._detect_encoding()
            path = Path(self.file_path)

            # Read a sample for delimiter detection
            with open(path, "r", encoding=encoding, errors="replace") as f:
                sample = f.read(8192)

            delimiter = self._detect_delimiter(sample)

            with open(path, "r", encoding=encoding, errors="replace") as f:
                reader = csv.DictReader(f, delimiter=delimiter)

                # Skip rows if configured
                skipped = 0
                rows: List[Dict[str, Any]] = []
                for row in reader:
                    if skipped < self.skip_rows:
                        skipped += 1
                        continue
                    # Strip whitespace from keys and values
                    cleaned_row = {}
                    for key, value in row.items():
                        if key is not None:
                            clean_key = key.strip()
                            if isinstance(value, str):
                                clean_value = value.strip()
                            else:
                                clean_value = value
                            cleaned_row[clean_key] = clean_value
                    rows.append(cleaned_row)

                return rows

        except FileNotFoundError:
            self._log("error", "File not found: %s", self.file_path)
            return None
        except PermissionError:
            self._log("error", "Permission denied: %s", self.file_path)
            return None
        except csv.Error as exc:
            self._log("error", "CSV parsing error: %s", exc)
            return None
        except Exception as exc:
            self._log("error", "Error reading CSV file: %s", exc)
            return None

    def _read_excel(self) -> Optional[List[Dict[str, Any]]]:
        """Read an Excel file and return a list of row dictionaries.

        Returns
        -------
        list[dict] | None
            List of row dicts, or ``None`` on failure.
        """
        try:
            df = self._load_excel_dataframe()
            if df is None:
                return None

            # Convert DataFrame to list of dicts, handling NaN values
            import math

            rows = []
            for record in df.to_dict(orient="records"):
                cleaned = {}
                for key, value in record.items():
                    # Skip NaN / infinite values
                    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                        cleaned[key] = None
                    else:
                        cleaned[key] = value
                rows.append(cleaned)

            return rows

        except Exception as exc:
            self._log("error", "Error reading Excel file: %s", exc)
            return None

    def _load_excel_dataframe(self):
        """Load an Excel file into a pandas DataFrame.

        Returns
        -------
        pandas.DataFrame | None
        """
        try:
            import pandas as pd

            read_kwargs: Dict[str, Any] = {
                "sheet_name": self.sheet_name,
                "dtype": str,
            }

            df = pd.read_excel(self.file_path, **read_kwargs)

            # Skip rows if configured
            if self.skip_rows > 0:
                df = df.iloc[self.skip_rows:]

            return df

        except ImportError:
            self._log(
                "error",
                "pandas and/or openpyxl are required to read Excel files. "
                "Install with: pip install pandas openpyxl",
            )
            return None
        except Exception as exc:
            self._log("error", "Error loading Excel file: %s", exc)
            return None

    @staticmethod
    def _find_column_value(data: dict, column_name: str) -> Any:
        """Find a value in a dict by column name (case-insensitive).

        Parameters
        ----------
        data : dict
            Source row dictionary.
        column_name : str
            Column name to look up.

        Returns
        -------
        Any | None
            The value, or ``None`` if not found or empty.
        """
        if not data or not column_name:
            return None

        # Direct case-insensitive lookup
        lower_map = {k.lower().strip(): v for k, v in data.items()}
        val = lower_map.get(column_name.lower().strip())
        if val is not None:
            str_val = str(val).strip()
            if str_val:
                return str_val
        return None

    def _reverse_column_map(self, canonical_field: str) -> Optional[str]:
        """Look up the source column name for a canonical field name.

        Parameters
        ----------
        canonical_field : str
            A canonical field name.

        Returns
        -------
        str | None
            The source column name from ``column_map``, or ``None``.
        """
        for source_col, target_field in self.column_map.items():
            if target_field == canonical_field:
                return source_col
        return None

    def close(self) -> None:
        """Clean up file handles."""
        if self._file_handle is not None:
            try:
                self._file_handle.close()
            except Exception:
                pass
            finally:
                self._file_handle = None
        self._connected = False
        self._log("info", "CSV importer adapter closed")
