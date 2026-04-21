"""
Insights package for TicketInsight Pro.

Provides analytics, reporting, and executive-summary generation from
analysed ticket data.

Modules
-------
generator : InsightsGenerator — computes aggregate statistics and KPIs
reporter  : ReportGenerator — produces JSON, CSV, and HTML reports
"""

from ticketinsight.insights.generator import InsightsGenerator
from ticketinsight.insights.reporter import ReportGenerator


__all__ = [
    "InsightsGenerator",
    "ReportGenerator",
]
