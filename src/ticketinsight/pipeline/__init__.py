"""
Pipeline package for TicketInsight Pro.

Provides the automated processing pipeline components:

- :class:`~ticketinsight.pipeline.ingester.DataIngester` — Orchestrates data
  ingestion from configured adapters into the database.
- :class:`~ticketinsight.pipeline.processor.DataProcessor` — Cleans, enriches,
  and deduplicates ticket data in the database.
- :class:`~ticketinsight.pipeline.scheduler.PipelineScheduler` — Schedules
  periodic ingestion, processing, and NLP analysis runs.

Usage
-----
    from ticketinsight.pipeline import DataIngester, DataProcessor
"""

__all__ = [
    "DataIngester",
    "DataProcessor",
    "PipelineScheduler",
]
