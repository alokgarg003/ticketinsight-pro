"""
General-purpose helper utilities for TicketInsight Pro.

Provides text processing, normalisation, date parsing, hashing, and a
robust retry decorator used throughout the application.

All functions are pure (side-effect-free) unless explicitly noted.
"""

import hashlib
import html
import math
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Generator, List, Optional, Sequence, Tuple, Type, TypeVar, Union
from urllib.parse import quote as url_quote

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
_T = TypeVar("_T")
DateResult = Union[datetime, None]
DateString = Optional[str]


# ---------------------------------------------------------------------------
# Text sanitisation
# ---------------------------------------------------------------------------

# Precompiled patterns for performance
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+", re.UNICODE)
_NULL_BYTE_RE = re.compile(r"\x00")
_NON_PRINTABLE_RE = re.compile(
    r"[^\x20-\x7E\xA0-\uFFFF]"  # keep printable ASCII + common unicode
)


def sanitize_text(text: str) -> str:
    """Clean and normalise raw text from ticket data.

    Steps performed (in order):
        1. Strip HTML tags.
        2. HTML-entity-decode remaining entities (``&amp;`` → ``&``, etc.).
        3. Remove null bytes and other control characters.
        4. Normalise Unicode to NFC form.
        5. Collapse consecutive whitespace to a single space.
        6. Strip leading/trailing whitespace.

    Parameters
    ----------
    text : str
        Raw text input (may contain HTML, weird Unicode, etc.).

    Returns
    -------
    str
        Cleaned, human-readable text.

    Examples
    --------
    >>> sanitize_text("<p>Hello  &amp;  World</p>")
    'Hello & World'
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Strip HTML tags
    text = _HTML_TAG_RE.sub(" ", text)

    # 2. Decode HTML entities
    text = html.unescape(text)

    # 3. Remove null bytes and control characters (keep \t, \n, \r)
    text = _NULL_BYTE_RE.sub("", text)
    text = _CONTROL_CHAR_RE.sub("", text)

    # 4. Normalise Unicode to composed form (NFC)
    text = unicodedata.normalize("NFC", text)

    # 5. Collapse whitespace
    text = _WHITESPACE_RE.sub(" ", text)

    # 6. Strip
    text = text.strip()

    return text


# ---------------------------------------------------------------------------
# Priority / Status normalisation
# ---------------------------------------------------------------------------

_PRIORITY_MAP: dict[str, str] = {
    # ServiceNow-style
    "1": "Critical",
    "2": "High",
    "3": "Medium",
    "4": "Low",
    # Jira-style
    "highest": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "lowest": "Low",
    # Common abbreviations and synonyms
    "critical": "Critical",
    "crit": "Critical",
    "urgent": "Critical",
    "p1": "Critical",
    "p2": "High",
    "p3": "Medium",
    "p4": "Low",
    "p5": "Low",
    "important": "High",
    "normal": "Medium",
    "minor": "Low",
    "trivial": "Low",
}


def normalize_priority(priority_str: str) -> str:
    """Map any priority representation to a canonical label.

    Canonical values: ``Critical``, ``High``, ``Medium``, ``Low``.

    Parameters
    ----------
    priority_str : str
        Raw priority string from the source system.

    Returns
    -------
    str
        One of the four canonical priority labels.  Defaults to ``"Medium"``
        when the input cannot be recognised.

    Examples
    --------
    >>> normalize_priority("P1")
    'Critical'
    >>> normalize_priority("high")
    'High'
    >>> normalize_priority("unknown")
    'Medium'
    """
    if not priority_str or not isinstance(priority_str, str):
        return "Medium"

    key = priority_str.strip().lower()
    return _PRIORITY_MAP.get(key, "Medium")


_STATUS_MAP: dict[str, str] = {
    # Canonical forms (identity mappings)
    "open": "Open",
    "in progress": "In Progress",
    "on hold": "On Hold",
    "resolved": "Resolved",
    "closed": "Closed",
    # ServiceNow states
    "new": "Open",
    "1": "Open",
    "2": "In Progress",
    "3": "On Hold",
    "6": "Resolved",
    "7": "Closed",
    "active": "In Progress",
    "awaiting": "On Hold",
    "awaiting user info": "On Hold",
    "awaiting vendor": "On Hold",
    # Jira states
    "to do": "Open",
    "in progress": "In Progress",
    "done": "Closed",
    "todo": "Open",
    "selected for development": "In Progress",
    "waiting for customer": "On Hold",
    "pending": "On Hold",
    # Common synonyms
    "backlog": "Open",
    "submitted": "Open",
    "assigned": "In Progress",
    "work in progress": "In Progress",
    "wip": "In Progress",
    "suspended": "On Hold",
    "cancelled": "Closed",
    "canceled": "Closed",
    "complete": "Closed",
    "completed": "Closed",
    "fulfilled": "Closed",
    "resolved - fixed": "Resolved",
    "resolved - duplicate": "Resolved",
    "resolved - wontfix": "Resolved",
}


def normalize_status(status_str: str) -> str:
    """Map any status representation to a canonical label.

    Canonical values: ``Open``, ``In Progress``, ``On Hold``,
    ``Resolved``, ``Closed``.

    Parameters
    ----------
    status_str : str
        Raw status string from the source system.

    Returns
    -------
    str
        One of the five canonical status labels.  Defaults to ``"Open"``
        when the input cannot be recognised.

    Examples
    --------
    >>> normalize_status("2")
    'In Progress'
    >>> normalize_status("DONE")
    'Closed'
    >>> normalize_status("awaiting vendor")
    'On Hold'
    """
    if not status_str or not isinstance(status_str, str):
        return "Open"

    key = status_str.strip().lower()
    return _STATUS_MAP.get(key, "Open")


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

# Common date formats encountered in ticket systems
_COMMON_DATE_FORMATS: list[str] = [
    "%Y-%m-%d %H:%M:%S",       # 2024-01-15 14:30:00
    "%Y-%m-%dT%H:%M:%S",       # ISO without Z
    "%Y-%m-%dT%H:%M:%SZ",      # ISO with Z (UTC)
    "%Y-%m-%dT%H:%M:%S%z",     # ISO with timezone offset
    "%Y-%m-%d %H:%M:%S.%f",    # With microseconds
    "%Y-%m-%dT%H:%M:%S.%fZ",   # ISO micro + Z
    "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO micro + offset
    "%Y-%m-%d",                  # Date only
    "%m/%d/%Y %H:%M:%S",       # US-style with time
    "%m/%d/%Y",                  # US-style date only
    "%d/%m/%Y %H:%M:%S",       # EU-style with time
    "%d/%m/%Y",                  # EU-style date only
    "%d-%b-%Y %H:%M:%S",       # 15-Jan-2024 14:30:00
    "%d-%b-%Y",                  # 15-Jan-2024
    "%b %d, %Y %H:%M:%S",      # Jan 15, 2024 14:30:00
    "%b %d, %Y",                 # Jan 15, 2024
    "%B %d, %Y %H:%M:%S",      # January 15, 2024 14:30:00
    "%B %d, %Y",                 # January 15, 2024
    "%Y%m%d%H%M%S",            # Compact: 20240115143000
    "%Y%m%d",                    # Compact date: 20240115
    "%Y-%m-%d %H:%M %p",       # 2024-01-15 02:30 PM
    "%m/%d/%Y %I:%M:%S %p",    # 01/15/2024 02:30:00 PM
]


def parse_date(
    date_str: DateString,
    formats: Optional[Sequence[str]] = None,
) -> DateResult:
    """Flexibly parse a date string using a sequence of format patterns.

    Tries each format in order and returns the first successful parse.
    If ``formats`` is ``None``, the built-in list of common ticket-system
    formats is used.

    Parameters
    ----------
    date_str : str | None
        The date string to parse.
    formats : sequence[str] | None
        ``strftime`` format strings to try.  Falls back to the internal
        defaults when ``None``.

    Returns
    -------
    datetime | None
        Parsed :class:`datetime`, or ``None`` if no format matches.
        Timezone-aware datetimes are normalised to UTC and converted to
        naive UTC datetimes for consistency.

    Examples
    --------
    >>> parse_date("2024-01-15 14:30:00")
    datetime.datetime(2024, 1, 15, 14, 30)
    >>> parse_date("15-Jan-2024")
    datetime.datetime(2024, 1, 15, 0, 0)
    >>> parse_date(None) is None
    True
    """
    if not date_str or not isinstance(date_str, str):
        return None

    date_str = date_str.strip()
    if not date_str:
        return None

    fmt_list = list(formats) if formats else _COMMON_DATE_FORMATS

    # Also try the dateutil parser if available, but not as first resort
    for fmt in fmt_list:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Normalise timezone-aware to naive UTC
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except (ValueError, TypeError):
            continue

    # Attempt ISO 8601 parsing as a last resort (handles extra precision)
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------


def chunk_list(lst: Sequence[_T], chunk_size: int) -> Generator[List[_T], None, None]:
    """Yield successive sub-lists of *chunk_size* from *lst*.

    Parameters
    ----------
    lst : sequence
        The source sequence.
    chunk_size : int
        Maximum elements per chunk.  Must be >= 1.

    Yields
    ------
    list
        Sub-lists containing at most *chunk_size* elements each.

    Examples
    --------
    >>> list(chunk_list([1, 2, 3, 4, 5], 2))
    [[1, 2], [3, 4], [5]]
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    total = len(lst)
    for start in range(0, total, chunk_size):
        yield list(lst[start : start + chunk_size])


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def calculate_hash(text: str) -> str:
    """Return the SHA-256 hex digest of *text*.

    This is used for ticket deduplication — identical tickets from
    different sources should produce the same hash.

    Parameters
    ----------
    text : str
        Text to hash.

    Returns
    -------
    str
        64-character lowercase hex string.

    Examples
    --------
    >>> calculate_hash("hello")
    '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    if not text or not isinstance(text, str):
        return hashlib.sha256(b"").hexdigest()

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Human-readable time
# ---------------------------------------------------------------------------

# Thresholds for human-readable time display (in seconds)
_TIME_UNITS: list[Tuple[str, float]] = [
    ("year", 365.25 * 24 * 3600),
    ("month", 30 * 24 * 3600),
    ("week", 7 * 24 * 3600),
    ("day", 24 * 3600),
    ("hour", 3600),
    ("minute", 60),
    ("second", 1),
]


def time_ago(dt: datetime) -> str:
    """Return a human-readable string describing how long ago *dt* was.

    Parameters
    ----------
    dt : datetime
        A naive or timezone-aware datetime (compared to ``now(UTC)``).

    Returns
    -------
    str
        E.g. ``"3 hours ago"``, ``"2 days ago"``, ``"just now"``.

    Examples
    --------
    >>> import datetime as _dt
    >>> time_ago(_dt.datetime.utcnow() - _dt.timedelta(minutes=5))
    '5 minutes ago'
    """
    if not isinstance(dt, datetime):
        return "unknown"

    # Normalise to naive UTC
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    delta_seconds = (now - dt).total_seconds()
    if delta_seconds < 0:
        # Future time — describe positively
        delta_seconds = abs(delta_seconds)
        return _format_timedelta(delta_seconds, future=True)

    return _format_timedelta(delta_seconds, future=False)


def _format_timedelta(seconds: float, future: bool = False) -> str:
    """Format a number of seconds as a human-readable string."""
    for unit_name, unit_seconds in _TIME_UNITS:
        if seconds >= unit_seconds:
            count = math.floor(seconds / unit_seconds)
            if count == 1:
                unit_str = unit_name
            else:
                unit_str = f"{unit_name}s"
            if future:
                return f"in {count} {unit_str}"
            return f"{count} {unit_str} ago"

    return "just now"


# ---------------------------------------------------------------------------
# Text truncation
# ---------------------------------------------------------------------------


def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """Safely truncate *text* to *max_len* characters, appending *suffix*.

    When ``len(text) <= max_len`` the original string is returned unchanged.

    Parameters
    ----------
    text : str
        Input text.
    max_len : int
        Maximum total length (including *suffix*).  Must be > 0.
    suffix : str
        Appended when truncation occurs.

    Returns
    -------
    str

    Examples
    --------
    >>> truncate("Hello World", max_len=8)
    'Hello...'
    >>> truncate("Hi", max_len=10)
    'Hi'
    """
    if not isinstance(text, str):
        return ""

    if max_len <= 0:
        return ""

    if len(text) <= max_len:
        return text

    available = max_len - len(suffix)
    if available <= 0:
        return suffix[:max_len]

    # Try to break at a word boundary
    truncated = text[:available]
    last_space = truncated.rfind(" ")
    if last_space > available // 2:
        truncated = truncated[:last_space]

    return truncated + suffix


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------

_SLUG_UNWANTED_RE = re.compile(r"[^\w\s-]")
_SLUG_HYPHEN_RE = re.compile(r"[-\s]+")


def slugify(text: str, max_length: int = 80) -> str:
    """Convert *text* into a URL-safe slug.

    Steps: lowercase → normalise Unicode → strip non-alphanumeric → collapse
    whitespace/hyphens → trim.

    Parameters
    ----------
    text : str
        Input string.
    max_length : int
        Maximum slug length (truncated without breaking words where possible).

    Returns
    -------
    str
        URL-safe slug.

    Examples
    --------
    >>> slugify("Hello World! This is a Test.")
    'hello-world-this-is-a-test'
    >>> slugify("File #123 — Résumé.pdf")
    'file-123-resume-pdf'
    """
    if not text or not isinstance(text, str):
        return ""

    # Normalise Unicode (NFKD decomposes, then we strip combining chars)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    # Lowercase and strip
    text = text.lower().strip()

    # Replace non-word chars with hyphens
    text = _SLUG_UNWANTED_RE.sub("-", text)

    # Collapse multiple hyphens / whitespace
    text = _SLUG_HYPHEN_RE.sub("-", text)

    # Strip leading/trailing hyphens
    text = text.strip("-")

    if max_length and len(text) > max_length:
        text = text[:max_length].rstrip("-")

    return text


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


def retry_on_failure(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = Exception,
    logger: Optional[Any] = None,
) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Decorator to retry a function on specified exceptions.

    Parameters
    ----------
    retries : int
        Maximum number of retry attempts (total calls = retries + 1).
    delay : float
        Initial delay in seconds before the first retry.
    backoff : float
        Multiplier applied to *delay* after each retry.
    exceptions : type | tuple[type, ...]
        Exception type(s) that should trigger a retry.
    logger : logging.Logger | None
        Optional logger.  Retries are logged at WARNING level.
        Falls back to :func:`logging.warning` when ``None``.

    Returns
    -------
    Callable
        Decorated function that retries on failure.

    Examples
    --------
    >>> @retry_on_failure(retries=3, delay=0.5, exceptions=(ConnectionError,))
    ... def fetch_data(url):
    ...     return requests.get(url).json()
    """
    def decorator(func: Callable[..., _T]) -> Callable[..., _T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> _T:
            current_delay = delay
            last_exception: Optional[BaseException] = None

            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < retries:
                        msg = (
                            f"{func.__name__} failed (attempt {attempt + 1}/{retries + 1}): "
                            f"{exc}. Retrying in {current_delay:.1f}s..."
                        )
                        if logger is not None:
                            logger.warning(msg)
                        else:
                            logging.warning(msg)
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        msg = (
                            f"{func.__name__} failed after {retries + 1} attempts: {exc}"
                        )
                        if logger is not None:
                            logger.error(msg)
                        else:
                            logging.error(msg)

            # If we exhausted retries, raise the last exception
            if last_exception is not None:
                raise last_exception

            # This should be unreachable, but satisfy type-checkers
            raise RuntimeError(f"{func.__name__} exhausted retries without raising")

        return wrapper
    return decorator


# Import logging at module level for the fallback in retry_on_failure
import logging  # noqa: E402
