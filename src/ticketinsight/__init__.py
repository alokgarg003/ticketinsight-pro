"""
TicketInsight Pro — Open-source, zero-cost ticket analytics platform.

Core package providing ticket ingestion, NLP-based analysis, categorization,
sentiment analysis, topic modeling, duplicate detection, and dashboard-ready
insights for IT service management (ITSM) ticket data.

Modules
-------
config      : Centralized configuration management (YAML + env vars + .env)
utils       : Logging, helpers, and common utilities
storage     : Database models, caching, and data access layer
adapters    : Ticket source adapters (ServiceNow, Jira, CSV)
nlp         : NLP pipeline (classification, sentiment, NER, topic modeling)
api         : Flask REST API endpoints
insights    : Analytics, dashboards, and reporting
pipeline    : Automated processing pipeline

Usage
-----
    from ticketinsight import create_app, Config
    app = create_app()
    app.run()
"""

__version__ = "1.0.0"
__author__ = "TicketInsight Team"
__license__ = "MIT"
