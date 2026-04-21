"""
Structured logging setup for TicketInsight Pro.

Features
--------
- Custom coloured console output
- Rotating file handler (10 MB, 5 backups)
- Log level driven by :class:`~ticketinsight.config.ConfigManager`
- :func:`get_logger` factory that returns named ``logging.Logger`` instances

Usage
-----
    from ticketinsight.utils.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Application started")
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# ANSI colour codes for coloured console output
# ---------------------------------------------------------------------------
class _Colours:
    """Terminal escape sequences for log-level colours."""

    RESET = "\033[0m"
    BOLD = "\033[1m"

    GREY = "\033[90m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"

    @staticmethod
    def disabled():
        """Return a colour map where every colour is the empty string."""
        return {attr: "" for attr in dir(_Colours) if attr.isupper()}


# Level → colour mapping
_LEVEL_COLOURS = {
    logging.DEBUG: _Colours.CYAN,
    logging.INFO: _Colours.GREEN,
    logging.WARNING: _Colours.YELLOW,
    logging.ERROR: _Colours.RED,
    logging.CRITICAL: _Colours.RED + _Colours.BOLD,
}


class ColourFormatter(logging.Formatter):
    """``Formatter`` subclass that injects ANSI colour escapes into the
    level name for readable console output."""

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt=fmt, datefmt=datefmt)
        # Detect non-TTY and disable colours automatically
        self._colours = _Colours() if self._is_tty() else _Colours.disabled()

    @staticmethod
    def _is_tty() -> bool:
        """Return ``True`` when stdout/stderr is a terminal."""
        if os.environ.get("NO_COLOR"):
            return False
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format *record* with a coloured level name."""
        original_levelname = record.levelname
        colour = _LEVEL_COLOURS.get(record.levelno, self._colours.RESET)
        record.levelname = f"{colour}{original_levelname:<8}{self._colours.RESET}"
        result = super().format(record)
        record.levelname = original_levelname
        return result


class DetailedFormatter(logging.Formatter):
    """Plain-text formatter for file output — includes the full pathname."""

    def format(self, record: logging.LogRecord) -> str:
        record.pathname = getattr(record, "pathname", record.module)
        return super().format(record)


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_loggers_configured: bool = False


def _ensure_log_directory(log_file: str) -> None:
    """Create parent directories for the log file if they do not exist."""
    log_path = Path(log_file)
    parent = log_path.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)


def configure_logging(
    level: str = "INFO",
    log_file: str = "logs/ticketinsight.log",
    log_format: Optional[str] = None,
    date_format: Optional[str] = None,
    max_bytes: int = 10_485_760,
    backup_count: int = 5,
    console_enabled: bool = True,
    file_enabled: bool = True,
) -> None:
    """Set up the root ``ticketinsight`` logger with handlers.

    This function is safe to call multiple times — subsequent calls are
    no-ops once the logging has been configured.

    Parameters
    ----------
    level : str
        Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    log_file : str
        Path to the rotating log file.
    log_format : str | None
        Format string.  Uses a sensible default when ``None``.
    date_format : str | None
        ``strftime`` date format string.
    max_bytes : int
        Maximum size of each log file before rotation.
    backup_count : int
        Number of rotated backup files to keep.
    console_enabled : bool
        Whether to attach the coloured console handler.
    file_enabled : bool
        Whether to attach the rotating file handler.
    """
    global _loggers_configured
    if _loggers_configured:
        return
    _loggers_configured = True

    if log_format is None:
        log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    if date_format is None:
        date_format = "%Y-%m-%d %H:%M:%S"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger for the package
    root_logger = logging.getLogger("ticketinsight")
    root_logger.setLevel(numeric_level)

    # Prevent propagation to the root (avoid duplicate logs)
    root_logger.propagate = False

    # -- Console handler --
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)
        console_formatter = ColourFormatter(fmt=log_format, datefmt=date_format)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # -- File handler (rotating) --
    if file_enabled:
        _ensure_log_directory(log_file)
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=False,
        )
        file_handler.setLevel(numeric_level)
        file_formatter = DetailedFormatter(fmt=log_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``ticketinsight`` namespace.

    The first call automatically triggers :func:`configure_logging` with
    sensible defaults.  If you need custom settings, call
    ``configure_logging(...)`` **before** invoking ``get_logger``.

    Parameters
    ----------
    name : str
        Typically ``__name__`` from the calling module.

    Returns
    -------
    logging.Logger
        A named logger instance.
    """
    if not _loggers_configured:
        configure_logging()

    # Ensure all ticketinsight loggers share the "ticketinsight" prefix
    if name.startswith("ticketinsight"):
        full_name = name
    else:
        full_name = f"ticketinsight.{name}"

    return logging.getLogger(full_name)
