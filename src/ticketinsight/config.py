"""
Centralized configuration manager for TicketInsight Pro.

Loads configuration from multiple sources in priority order (highest wins):
    1. Environment variables
    2. .env file (via python-dotenv)
    3. YAML config file (TICKETINSIGHT_CONFIG or config.yaml)
    4. Built-in defaults

Usage
-----
    from ticketinsight.config import ConfigManager

    config = ConfigManager()
    config.load()

    db_url = config.get("database", "url")
    debug  = config.get("app", "debug")
"""

import copy
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# ---------------------------------------------------------------------------
# Default configuration — every key that the application may reference must
# have a sensible default defined here.
# ---------------------------------------------------------------------------
_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "app": {
        "env": "development",
        "debug": True,
        "host": "0.0.0.0",
        "port": 5000,
        "secret_key": "dev-secret-change-me",
        "testing": False,
    },
    "database": {
        "url": "sqlite:///data/ticketinsight.db",
        "pool_size": 10,
        "pool_timeout": 30,
        "max_overflow": 20,
        "echo": False,
        "track_modifications": True,
    },
    "redis": {
        "url": "redis://localhost:6379/0",
        "cache_ttl": 3600,
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
        "retry_on_timeout": True,
    },
    "logging": {
        "level": "INFO",
        "file": "logs/ticketinsight.log",
        "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        "date_format": "%Y-%m-%d %H:%M:%S",
        "max_bytes": 10485760,   # 10 MB
        "backup_count": 5,
        "console_enabled": True,
        "file_enabled": True,
    },
    "adapter": {
        "type": "csv",
        "csv_file_path": "data/samples/tickets_sample.csv",
        "batch_size": 500,
        "timeout": 60,
        "retry_attempts": 3,
        "retry_delay": 5,
        "snow_instance": "",
        "snow_username": "",
        "snow_password": "",
        "jira_server": "",
        "jira_username": "",
        "jira_api_token": "",
    },
    "nlp": {
        "model": "en_core_web_sm",
        "batch_size": 32,
        "disable_pipes": ["parser", "tagger"],
        "min_confidence": 0.6,
        "max_text_length": 10000,
        "sentiment_model": "textblob",
        "classification_model": "logistic_regression",
        "topic_num_topics": 8,
        "topic_num_keywords": 6,
        "duplicate_threshold": 0.92,
        "anomaly_contamination": 0.05,
    },
    "pipeline": {
        "interval_minutes": 30,
        "max_concurrent_workers": 2,
        "ticket_limit_per_run": 1000,
        "enable_sentiment": True,
        "enable_classification": True,
        "enable_topic_modeling": True,
        "enable_duplicate_detection": True,
        "enable_anomaly_detection": True,
        "enable_summarization": True,
        "enable_ner": True,
        "enable_root_cause": True,
    },
    "insights": {
        "dashboard_refresh_interval": 300,
        "top_n_categories": 10,
        "trend_window_days": 30,
        "heatmap_resolution": "daily",
    },
    "cors": {
        "origins": ["http://localhost:3000", "http://localhost:5000"],
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "supports_credentials": True,
        "max_age": 3600,
    },
    "metabase": {
        "url": "",
        "api_key": "",
        "sync_interval_minutes": 60,
        "dashboard_ids": [],
    },
}


class ConfigManager:
    """Singleton configuration manager with layered loading.

    Configuration is resolved from (highest priority first):
        1. OS environment variables (e.g. ``APP_ENV``, ``DATABASE_URL``)
        2. ``.env`` file at the project root (via ``python-dotenv``)
        3. YAML config file at the path in ``TICKETINSIGHT_CONFIG`` env var,
           falling back to ``config.yaml`` in the project root.
        4. Built-in ``_DEFAULTS`` dictionary.

    Attributes
    ----------
    _data : dict[str, dict[str, Any]]
        Fully-resolved, flat configuration keyed by section.
    _config_path : str | None
        Path from which the YAML file was loaded (if any).
    """

    _instance: Optional["ConfigManager"] = None

    def __new__(cls, config_path: Optional[str] = None) -> "ConfigManager":
        """Enforce singleton pattern — only one ConfigManager per process."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        if config_path is not None:
            cls._instance._custom_config_path = config_path
        return cls._instance

    def __init__(self, config_path: Optional[str] = None) -> None:
        if self._initialized:
            return
        self._custom_config_path: Optional[str] = config_path
        self._config_path: Optional[str] = None
        self._data: Dict[str, Dict[str, Any]] = copy.deepcopy(_DEFAULTS)
        self._load_dotenv()
        self._load_yaml()
        self._load_env_overrides()
        self._initialized = True

    # ------------------------------------------------------------------
    # Private loading helpers
    # ------------------------------------------------------------------

    def _project_root(self) -> Path:
        """Return the project root directory (parent of src/)."""
        # Walk up from this file to find the project root marker.
        current = Path(__file__).resolve().parent
        for parent in [current, *current.parents]:
            if (parent / "setup.py").exists() or (parent / "pyproject.toml").exists():
                return parent
            if parent.name == "src":
                return parent.parent
        # Fallback: two levels up from this file (src/ticketinsight/ -> src/ -> root)
        return current.parent.parent

    def _load_dotenv(self) -> None:
        """Load a ``.env`` file from the project root using *python-dotenv*."""
        try:
            from dotenv import load_dotenv

            env_path = self._project_root() / ".env"
            if env_path.exists():
                load_dotenv(dotenv_path=env_path, override=False)
        except ImportError:
            # python-dotenv is optional — silently skip
            pass

    def _load_yaml(self) -> None:
        """Merge settings from a YAML config file into ``_data``."""
        config_path = self._resolve_config_path()
        if config_path is None:
            return

        self._config_path = str(config_path)
        try:
            with open(config_path, encoding="utf-8") as fh:
                yaml_data = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            raise RuntimeError(
                f"Failed to load YAML config from {config_path}: {exc}"
            ) from exc

        if not isinstance(yaml_data, dict):
            return

        for section, values in yaml_data.items():
            if section in self._data and isinstance(values, dict):
                self._data[section].update(values)
            elif isinstance(values, dict):
                self._data[section] = values

    def _resolve_config_path(self) -> Optional[Path]:
        """Determine the YAML config file path.

        Priority:
            1. ``TICKETINSIGHT_CONFIG`` environment variable
            2. Explicit ``config_path`` constructor argument
            3. ``config.yaml`` in the project root
        """
        env_path = os.environ.get("TICKETINSIGHT_CONFIG")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return path
            raise FileNotFoundError(
                f"TICKETINSIGHT_CONFIG points to non-existent file: {env_path}"
            )

        if self._custom_config_path:
            path = Path(self._custom_config_path)
            if path.exists():
                return path
            raise FileNotFoundError(
                f"Config file not found: {self._custom_config_path}"
            )

        default_path = self._project_root() / "config.yaml"
        if default_path.exists():
            return default_path

        return None

    def _load_env_overrides(self) -> None:
        """Overlay individual environment variables onto the config sections.

        Mapping convention (case-insensitive):
            - ``APP_ENV``      → app.env
            - ``APP_DEBUG``    → app.debug
            - ``DATABASE_URL`` → database.url
            - ``REDIS_URL``    → redis.url
            - ``LOG_LEVEL``    → logging.level
            - ``LOG_FILE``     → logging.file
            - ``SECRET_KEY``   → app.secret_key
            - etc.
        """
        env_map = {
            "APP_ENV": ("app", "env"),
            "APP_DEBUG": ("app", "debug"),
            "APP_HOST": ("app", "host"),
            "APP_PORT": ("app", "port"),
            "SECRET_KEY": ("app", "secret_key"),
            "DATABASE_URL": ("database", "url"),
            "DATABASE_POOL_SIZE": ("database", "pool_size"),
            "REDIS_URL": ("redis", "url"),
            "REDIS_CACHE_TTL": ("redis", "cache_ttl"),
            "LOG_LEVEL": ("logging", "level"),
            "LOG_FILE": ("logging", "file"),
            "CORS_ORIGINS": ("cors", "origins"),
            "METABASE_URL": ("metabase", "url"),
            "METABASE_API_KEY": ("metabase", "api_key"),
            "ADAPTER_TYPE": ("adapter", "type"),
            "SNOW_INSTANCE": ("adapter", "snow_instance"),
            "SNOW_USERNAME": ("adapter", "snow_username"),
            "SNOW_PASSWORD": ("adapter", "snow_password"),
            "JIRA_SERVER": ("adapter", "jira_server"),
            "JIRA_USERNAME": ("adapter", "jira_username"),
            "JIRA_API_TOKEN": ("adapter", "jira_api_token"),
            "CSV_FILE_PATH": ("adapter", "csv_file_path"),
            "NLP_MODEL": ("nlp", "model"),
            "NLP_BATCH_SIZE": ("nlp", "batch_size"),
            "PIPELINE_INTERVAL_MINUTES": ("pipeline", "interval_minutes"),
        }

        for env_var, (section, key) in env_map.items():
            value = os.environ.get(env_var)
            if value is None:
                continue

            # Cast booleans and integers automatically
            value = self._auto_cast(value)

            if section not in self._data:
                self._data[section] = {}
            self._data[section][key] = value

    @staticmethod
    def _auto_cast(value: str) -> Any:
        """Attempt to cast a string value to bool / int / float."""
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        if value.lower() in ("false", "no", "0", "off"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Retrieve a single configuration value.

        Parameters
        ----------
        section : str
            Top-level section name (e.g. ``"app"``, ``"database"``).
        key : str
            Key within the section (e.g. ``"port"``, ``"url"``).
        default : Any, optional
            Returned when the section or key does not exist.

        Returns
        -------
        Any
            The resolved configuration value.
        """
        section_data = self._data.get(section)
        if section_data is None:
            return default
        return section_data.get(key, default)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Return a deep copy of the entire resolved configuration."""
        return copy.deepcopy(self._data)

    def get_section(self, section: str) -> Dict[str, Any]:
        """Return a deep copy of a single configuration section."""
        return copy.deepcopy(self._data.get(section, {}))

    def set(self, section: str, key: str, value: Any) -> None:
        """Override a configuration value at runtime.

        This does **not** persist the change to disk.
        """
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value

    def reload(self) -> None:
        """Re-read configuration from all sources (YAML, env, .env)."""
        self._data = copy.deepcopy(_DEFAULTS)
        self._initialized = False
        self._load_dotenv()
        self._load_yaml()
        self._load_env_overrides()
        self._initialized = True

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Validate the current configuration and return a list of issues.

        Returns
        -------
        list[str]
            Human-readable issue descriptions.  Empty list means the
            configuration is valid.
        """
        issues: list[str] = []

        # --- App ---
        env = self.get("app", "env")
        if env not in ("development", "staging", "production", "testing"):
            issues.append(f"app.env must be development|staging|production|testing, got '{env}'")

        port = self.get("app", "port")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            issues.append(f"app.port must be an integer in [1, 65535], got {port!r}")

        secret = self.get("app", "secret_key")
        if env == "production" and secret in ("dev-secret-change-me", "", None):
            issues.append("app.secret_key must be changed from default in production")

        # --- Database ---
        db_url = self.get("database", "url")
        if not db_url or not isinstance(db_url, str):
            issues.append("database.url is required and must be a non-empty string")
        elif db_url.startswith("postgresql") or db_url.startswith("postgres"):
            pool = self.get("database", "pool_size")
            if not isinstance(pool, int) or pool < 1:
                issues.append(f"database.pool_size must be a positive integer, got {pool!r}")

        # --- Adapter ---
        adapter_type = self.get("adapter", "type")
        if adapter_type not in ("servicenow", "jira", "csv"):
            issues.append(f"adapter.type must be servicenow|jira|csv, got '{adapter_type}'")

        if adapter_type == "servicenow":
            if not self.get("adapter", "snow_instance"):
                issues.append("adapter.snow_instance is required when adapter.type is 'servicenow'")
            if not self.get("adapter", "snow_username"):
                issues.append("adapter.snow_username is required when adapter.type is 'servicenow'")
            if not self.get("adapter", "snow_password"):
                issues.append("adapter.snow_password is required when adapter.type is 'servicenow'")

        if adapter_type == "jira":
            if not self.get("adapter", "jira_server"):
                issues.append("adapter.jira_server is required when adapter.type is 'jira'")
            if not self.get("adapter", "jira_api_token"):
                issues.append("adapter.jira_api_token is required when adapter.type is 'jira'")

        if adapter_type == "csv":
            csv_path = self.get("adapter", "csv_file_path")
            if not csv_path:
                issues.append("adapter.csv_file_path is required when adapter.type is 'csv'")

        # --- NLP ---
        nlp_model = self.get("nlp", "model")
        if not nlp_model or not isinstance(nlp_model, str):
            issues.append("nlp.model must be a non-empty string (e.g. 'en_core_web_sm')")

        # --- Pipeline ---
        interval = self.get("pipeline", "interval_minutes")
        if not isinstance(interval, (int, float)) or interval < 0:
            issues.append(f"pipeline.interval_minutes must be a non-negative number, got {interval!r}")

        return issues

    def validate_or_raise(self) -> None:
        """Call :meth:`validate` and raise :class:`ValueError` on issues."""
        issues = self.validate()
        if issues:
            raise ValueError(
                "Configuration validation failed:\n  - " + "\n  - ".join(issues)
            )

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        env = self.get("app", "env")
        return f"<ConfigManager env={env} config_file={self._config_path!r}>"

    def __getitem__(self, section: str) -> Dict[str, Any]:
        """Dict-style access by section: ``config["database"]["url"]``."""
        return copy.deepcopy(self._data.get(section, {}))
