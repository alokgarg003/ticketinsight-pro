"""
Ticket system adapters for TicketInsight Pro.

Provides concrete adapter implementations for various ticket/issue-tracking
systems:

- :class:`~ticketinsight.adapters.servicenow.ServiceNowAdapter` — ServiceNow REST API
- :class:`~ticketinsight.adapters.jira.JiraAdapter` — Jira REST API v3
- :class:`~ticketinsight.adapters.csv_importer.CSVImporterAdapter` — CSV / Excel files
- :class:`~ticketinsight.adapters.universal.UniversalAdapter` — Generic REST / JSON APIs

Usage
-----
    from ticketinsight.adapters import create_adapter

    adapter = create_adapter("servicenow", config={
        "instance": "https://mycompany.service-now.com",
        "username": "admin",
        "password": "secret",
    })
    adapter.connect()
    tickets = adapter.fetch_tickets(limit=100)
    adapter.close()
"""

from typing import Any, Dict

from ticketinsight.adapters.base import BaseAdapter

__all__ = [
    "BaseAdapter",
    "ServiceNowAdapter",
    "JiraAdapter",
    "CSVImporterAdapter",
    "UniversalAdapter",
    "ADAPTER_REGISTRY",
    "create_adapter",
]

# ---------------------------------------------------------------------------
# Adapter registry — maps string type names to adapter classes
# ---------------------------------------------------------------------------
ADAPTER_REGISTRY: Dict[str, type] = {}


def _register_adapter(name: str, cls: type) -> None:
    """Register an adapter class under the given type name."""
    ADAPTER_REGISTRY[name.lower()] = cls


def create_adapter(adapter_type: str, config: Dict[str, Any]) -> BaseAdapter:
    """Factory function that creates the appropriate adapter instance.

    Parameters
    ----------
    adapter_type : str
        One of ``"servicenow"``, ``"jira"``, ``"csv"``, ``"universal"``.
        Matching is case-insensitive.
    config : dict
        Adapter-specific configuration dictionary.

    Returns
    -------
    BaseAdapter
        An initialised adapter instance.

    Raises
    ------
    ValueError
        If *adapter_type* is not recognised.
    """
    adapter_cls = ADAPTER_REGISTRY.get(adapter_type.lower())
    if adapter_cls is None:
        supported = ", ".join(sorted(ADAPTER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown adapter type '{adapter_type}'. "
            f"Supported types: {supported}"
        )
    return adapter_cls(config)


# ---------------------------------------------------------------------------
# Lazy imports so the package can be imported without heavy dependencies
# ---------------------------------------------------------------------------
def __getattr__(name: str):  # noqa: D401
    """Lazy-load adapter classes on first access."""
    _lazy_map = {
        "ServiceNowAdapter": ("ticketinsight.adapters.servicenow", "servicenow"),
        "JiraAdapter": ("ticketinsight.adapters.jira", "jira"),
        "CSVImporterAdapter": ("ticketinsight.adapters.csv_importer", "csv"),
        "UniversalAdapter": ("ticketinsight.adapters.universal", "universal"),
    }
    if name in _lazy_map:
        import importlib
        module_path, registry_name = _lazy_map[name]
        module = importlib.import_module(module_path)
        cls = getattr(module, name)
        # Auto-register with the correct short name
        _register_adapter(registry_name, cls)
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
# Pre-register known adapter types so the registry is populated even
# before the first lazy import.
# ---------------------------------------------------------------------------
_REGISTERED_NAMES = {
    "servicenow": "ticketinsight.adapters.servicenow.ServiceNowAdapter",
    "jira": "ticketinsight.adapters.jira.JiraAdapter",
    "csv": "ticketinsight.adapters.csv_importer.CSVImporterAdapter",
    "universal": "ticketinsight.adapters.universal.UniversalAdapter",
}

# Populate registry eagerly on import so that ``create_adapter`` works
# immediately without depending on the lazy-loading mechanism above.
try:
    _cls = __getattr__("ServiceNowAdapter")
except Exception:
    pass

try:
    _cls = __getattr__("JiraAdapter")
except Exception:
    pass

try:
    _cls = __getattr__("CSVImporterAdapter")
except Exception:
    pass

try:
    _cls = __getattr__("UniversalAdapter")
except Exception:
    pass
