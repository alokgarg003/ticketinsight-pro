"""
Report generator for TicketInsight Pro.

Produces reports in JSON, CSV, and HTML formats from insights data.
Reports range from brief summaries to C-suite ready executive
overviews.
"""

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ticketinsight.utils.logger import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """Generate reports in various formats.

    Parameters
    ----------
    db_manager : DatabaseManager
        Active database manager with an initialised Flask app context.
    insights_generator : InsightsGenerator
        Generator instance for computing analytics data.
    """

    def __init__(self, db_manager, insights_generator):
        self.db = db_manager
        self.insights = insights_generator
        self.logger = get_logger("insights.reporter")

    # ------------------------------------------------------------------
    # JSON reports
    # ------------------------------------------------------------------

    def generate_json_report(self, report_type: str, filters: Optional[Dict] = None) -> dict:
        """Generate a report as a JSON dictionary.

        Parameters
        ----------
        report_type : str
            One of: ``summary``, ``detailed``, ``executive``,
            ``performance``, ``nlp_analysis``.
        filters : dict | None
            Optional filters applied to the underlying data.

        Returns
        -------
        dict
            Complete report data structure.
        """
        filters = filters or {}
        report_type = report_type.lower()

        dispatch = {
            "summary": self._report_summary,
            "detailed": self._report_detailed,
            "executive": self.generate_executive_report,
            "performance": self._report_performance,
            "nlp_analysis": self._report_nlp_analysis,
        }

        generator = dispatch.get(report_type)
        if generator is None:
            available = sorted(dispatch.keys())
            raise ValueError(f"Unknown report_type '{report_type}'. Available: {available}")

        return generator(filters)

    # ------------------------------------------------------------------
    # CSV reports
    # ------------------------------------------------------------------

    def generate_csv_report(self, report_type: str, filters: Optional[Dict] = None) -> str:
        """Generate a report as a CSV string.

        Parameters
        ----------
        report_type : str
            One of: ``summary``, ``detailed``, ``executive``,
            ``performance``, ``nlp_analysis``, ``tickets``.
        filters : dict | None
            Optional filters.

        Returns
        -------
        str
            CSV-formatted string with headers.
        """
        filters = filters or {}
        report_type = report_type.lower()

        if report_type == "tickets":
            return self._csv_tickets(filters)

        # For insight-type reports, generate JSON then flatten to CSV
        try:
            json_report = self.generate_json_report(report_type, filters)
        except ValueError as exc:
            self.logger.error("Cannot generate CSV for unknown report type: %s", exc)
            return f"# Error: {exc}\n"

        output = io.StringIO()
        writer = csv.writer(output)

        if report_type == "summary":
            self._flatten_summary_csv(writer, json_report)
        elif report_type == "performance":
            self._flatten_performance_csv(writer, json_report)
        elif report_type == "executive":
            self._flatten_executive_csv(writer, json_report)
        elif report_type == "nlp_analysis":
            self._flatten_nlp_csv(writer, json_report)
        elif report_type == "detailed":
            self._flatten_detailed_csv(writer, json_report)
        else:
            writer.writerow(["Report Type", report_type])
            writer.writerow(["Key", "Value"])
            for key, value in self._flatten_dict(json_report, prefix=""):
                writer.writerow([key, str(value)])

        return output.getvalue()

    # ------------------------------------------------------------------
    # HTML reports
    # ------------------------------------------------------------------

    def generate_html_report(self, report_type: str, filters: Optional[Dict] = None) -> str:
        """Generate a report as an HTML document with inline CSS.

        Produces a professional, self-contained HTML page with embedded
        styles, data tables, and summary sections.

        Parameters
        ----------
        report_type : str
            One of: ``summary``, ``detailed``, ``executive``,
            ``performance``, ``nlp_analysis``.
        filters : dict | None
            Optional filters.

        Returns
        -------
        str
            Complete HTML document string.
        """
        filters = filters or {}
        report_type = report_type.lower()

        try:
            json_report = self.generate_json_report(report_type, filters)
        except ValueError as exc:
            return f"<html><body><h1>Error</h1><p>{exc}</p></body></html>"

        generated_at = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M UTC")

        title = {
            "summary": "Ticket Insights Summary",
            "detailed": "Detailed Ticket Analysis",
            "executive": "Executive Report",
            "performance": "Team Performance Report",
            "nlp_analysis": "NLP Analysis Report",
        }.get(report_type, "TicketInsight Report")

        # Build HTML sections
        sections_html = self._build_html_sections(report_type, json_report)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — TicketInsight Pro</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #1a365d 0%, #2563eb 100%);
            color: white;
            padding: 30px 40px;
            border-radius: 8px;
            margin-bottom: 24px;
        }}
        .header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 6px; }}
        .header .subtitle {{ font-size: 14px; opacity: 0.85; }}
        .header .meta {{ font-size: 12px; opacity: 0.7; margin-top: 8px; }}
        .section {{
            background: white;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .section h2 {{
            font-size: 18px;
            color: #1a365d;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e2e8f0;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 16px;
        }}
        .kpi-card {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        .kpi-card .value {{
            font-size: 28px;
            font-weight: 700;
            color: #2563eb;
        }}
        .kpi-card .label {{
            font-size: 12px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
        }}
        th {{
            background: #f1f5f9;
            padding: 10px 12px;
            text-align: left;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #475569;
            border-bottom: 2px solid #cbd5e1;
        }}
        td {{
            padding: 8px 12px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 14px;
        }}
        tr:hover {{ background: #f8fafc; }}
        .alert-critical {{ color: #dc2626; font-weight: 600; }}
        .alert-warning {{ color: #d97706; font-weight: 600; }}
        .alert-info {{ color: #2563eb; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge-critical {{ background: #fecaca; color: #991b1b; }}
        .badge-high {{ background: #fed7aa; color: #9a3412; }}
        .badge-medium {{ background: #fef08a; color: #854d0e; }}
        .badge-low {{ background: #bbf7d0; color: #166534; }}
        .bar-chart {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 4px 0;
        }}
        .bar {{
            height: 20px;
            background: #3b82f6;
            border-radius: 4px;
            min-width: 2px;
        }}
        .bar-label {{ min-width: 120px; font-size: 13px; }}
        .bar-value {{ font-size: 13px; color: #64748b; min-width: 60px; text-align: right; }}
        .footer {{
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            margin-top: 24px;
            padding: 16px;
        }}
        @media print {{
            body {{ background: white; }}
            .section {{ box-shadow: none; border: 1px solid #e2e8f0; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="subtitle">TicketInsight Pro — Automated Analytics Report</div>
            <div class="meta">Generated: {generated_at} | Report Type: {report_type}</div>
        </div>
        {sections_html}
        <div class="footer">
            TicketInsight Pro v1.0.0 — Open Source Ticket Analytics Platform
        </div>
    </div>
</body>
</html>"""
        return html

    # ------------------------------------------------------------------
    # Executive report
    # ------------------------------------------------------------------

    def generate_executive_report(self, filters: Optional[Dict] = None) -> dict:
        """Generate a C-suite ready executive report.

        Combines summary, performance, sentiment, and KA recommendation
        data into a single comprehensive overview with actionable
        recommendations and risk alerts.

        Returns
        -------
        dict
            Executive report with KPIs, trends, recommendations, and risks.
        """
        filters = filters or {}

        summary = self.insights.generate_summary(filters)
        performance = self.insights.generate_team_performance()
        ka_recs = self.insights.generate_ka_recommendations()

        # Key performance indicators
        key_metrics = summary.get("key_metrics", {})
        kpis = {
            "total_ticket_volume": key_metrics.get("total_tickets", 0),
            "open_ticket_count": key_metrics.get("open_tickets", 0),
            "resolution_rate_pct": key_metrics.get("resolution_rate", 0),
            "avg_resolution_time_hours": key_metrics.get("avg_resolution_time_hours"),
            "avg_customer_sentiment": key_metrics.get("avg_sentiment_score", 0),
            "anomaly_detection_count": key_metrics.get("anomaly_count", 0),
            "duplicate_ticket_count": key_metrics.get("duplicate_count", 0),
            "nlp_insight_coverage_pct": key_metrics.get("insight_coverage", 0),
        }

        # Risk assessment
        alerts = summary.get("alerts", [])
        risk_alerts = []
        for alert in alerts:
            if alert.get("level") in ("critical", "warning"):
                risk_alerts.append({
                    "severity": alert["level"],
                    "type": alert.get("type", "unknown"),
                    "description": alert["message"],
                    "recommended_action": alert.get("action", ""),
                })

        # Recommendations
        recommendations = []
        ka_items = ka_recs.get("recommendations", [])
        for item in ka_items[:10]:
            recommendations.append({
                "type": item.get("type", ""),
                "priority": item.get("priority", ""),
                "title": item.get("title", ""),
                "reason": item.get("reason", ""),
                "potential_impact": item.get("potential_savings_hours"),
            })

        # Team performance highlights
        team_highlights = []
        groups = performance.get("groups", [])
        for grp in groups[:5]:
            team_highlights.append({
                "team": grp.get("group", ""),
                "tickets_handled": grp.get("total_tickets", 0),
                "resolution_rate": round(
                    grp.get("resolved_tickets", 0) / max(grp.get("total_tickets", 1), 1) * 100, 1
                ),
                "avg_resolution_hours": grp.get("avg_resolution_hours"),
            })

        # Scorecard (0-100)
        scorecard = self._compute_scorecard(summary, performance, ka_recs)

        return {
            "report_type": "executive",
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "kpi_summary": kpis,
            "volume_breakdown": summary.get("volume_breakdown", {}),
            "priority_breakdown": summary.get("priority_breakdown", {}),
            "sentiment_distribution": summary.get("sentiment_distribution", {}),
            "trend": summary.get("trend", []),
            "risk_alerts": risk_alerts,
            "recommendations": recommendations,
            "team_performance_highlights": team_highlights,
            "scorecard": scorecard,
            "estimated_savings_hours": ka_recs.get("estimated_total_savings_hours", 0),
        }

    # ------------------------------------------------------------------
    # Private report generators
    # ------------------------------------------------------------------

    def _report_summary(self, filters: Dict) -> dict:
        """Generate a summary report."""
        return self.insights.generate_summary(filters)

    def _report_detailed(self, filters: Dict) -> dict:
        """Generate a detailed report combining multiple analyses."""
        return {
            "report_type": "detailed",
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "summary": self.insights.generate_summary(filters),
            "category_insights": self.insights.generate_category_insights(),
            "priority_insights": self.insights.generate_priority_insights(),
            "sentiment_trend": self.insights.generate_sentiment_trend(days=30),
            "team_performance": self.insights.generate_team_performance(),
        }

    def _report_performance(self, filters: Dict) -> dict:
        """Generate a performance-focused report."""
        perf = self.insights.generate_team_performance()
        priority = self.insights.generate_priority_insights()
        return {
            "report_type": "performance",
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "team_performance": perf,
            "priority_analysis": priority,
        }

    def _report_nlp_analysis(self, filters: Dict) -> dict:
        """Generate an NLP analysis-focused report."""
        return {
            "report_type": "nlp_analysis",
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "sentiment_trend": self.insights.generate_sentiment_trend(days=30),
            "ka_recommendations": self.insights.generate_ka_recommendations(),
        }

    # ------------------------------------------------------------------
    # CSV helpers
    # ------------------------------------------------------------------

    def _csv_tickets(self, filters: Dict) -> str:
        """Generate CSV of all tickets."""
        try:
            result = self.db.get_tickets(
                filters=filters,
                page=1,
                per_page=50000,
            )
            tickets = result.get("tickets", [])
        except Exception as exc:
            self.logger.error("Failed to get tickets for CSV: %s", exc)
            return "# Error fetching tickets\n"

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "ID", "Ticket ID", "Title", "Priority", "Status", "Category",
            "Assignment Group", "Assignee", "Opened At", "Resolved At",
            "Closed At", "Source System", "Sentiment Score", "Sentiment Label",
            "Predicted Category", "Anomaly Score", "Summary",
        ]
        writer.writerow(headers)

        for t in tickets:
            writer.writerow([
                t.get("id", ""),
                t.get("ticket_id", ""),
                t.get("title", ""),
                t.get("priority", ""),
                t.get("status", ""),
                t.get("category", ""),
                t.get("assignment_group", ""),
                t.get("assignee", ""),
                t.get("opened_at", ""),
                t.get("resolved_at", ""),
                t.get("closed_at", ""),
                t.get("source_system", ""),
                t.get("sentiment_score", ""),
                t.get("sentiment_label", ""),
                t.get("predicted_category", ""),
                t.get("anomaly_score", ""),
                t.get("summary", ""),
            ])

        return output.getvalue()

    def _flatten_summary_csv(self, writer, report: dict):
        """Flatten summary report to CSV rows."""
        writer.writerow(["TicketInsight Summary Report"])
        writer.writerow([])

        km = report.get("key_metrics", {})
        writer.writerow(["Key Metrics"])
        writer.writerow(["Metric", "Value"])
        for key, value in km.items():
            writer.writerow([key, value])
        writer.writerow([])

        writer.writerow(["Status Distribution"])
        writer.writerow(["Status", "Count"])
        for status, count in report.get("volume_breakdown", {}).items():
            writer.writerow([status, count])
        writer.writerow([])

        writer.writerow(["Priority Distribution"])
        writer.writerow(["Priority", "Count"])
        for priority, count in report.get("priority_breakdown", {}).items():
            writer.writerow([priority, count])
        writer.writerow([])

        writer.writerow(["Category Distribution"])
        writer.writerow(["Category", "Count"])
        for cat in report.get("category_distribution", []):
            writer.writerow([cat.get("category", ""), cat.get("count", "")])
        writer.writerow([])

        writer.writerow(["Alerts"])
        writer.writerow(["Level", "Type", "Message", "Action"])
        for alert in report.get("alerts", []):
            writer.writerow([
                alert.get("level", ""),
                alert.get("type", ""),
                alert.get("message", ""),
                alert.get("action", ""),
            ])

    def _flatten_performance_csv(self, writer, report: dict):
        """Flatten performance report to CSV rows."""
        writer.writerow(["Team Performance Report"])
        writer.writerow([])

        writer.writerow(["Team Performance"])
        writer.writerow(["Team", "Total Tickets", "Resolved", "Open", "Team Size", "Avg Resolution Hours"])
        for grp in report.get("team_performance", {}).get("groups", []):
            writer.writerow([
                grp.get("group", ""),
                grp.get("total_tickets", ""),
                grp.get("resolved_tickets", ""),
                grp.get("open_tickets", ""),
                grp.get("team_size", ""),
                grp.get("avg_resolution_hours", ""),
            ])
        writer.writerow([])

        writer.writerow(["Priority SLA Compliance"])
        writer.writerow(["Priority", "Count", "SLA Target (hrs)", "SLA Compliance %"])
        for pri in report.get("priority_analysis", {}).get("priorities", []):
            writer.writerow([
                pri.get("priority", ""),
                pri.get("count", ""),
                pri.get("sla_target_hours", ""),
                pri.get("sla_compliance_pct", ""),
            ])

    def _flatten_executive_csv(self, writer, report: dict):
        """Flatten executive report to CSV rows."""
        writer.writerow(["Executive Report — TicketInsight Pro"])
        writer.writerow([])

        writer.writerow(["Key Performance Indicators"])
        writer.writerow(["KPI", "Value"])
        for kpi, value in report.get("kpi_summary", {}).items():
            writer.writerow([kpi, value])
        writer.writerow([])

        writer.writerow(["Risk Alerts"])
        writer.writerow(["Severity", "Type", "Description", "Recommended Action"])
        for risk in report.get("risk_alerts", []):
            writer.writerow([
                risk.get("severity", ""),
                risk.get("type", ""),
                risk.get("description", ""),
                risk.get("recommended_action", ""),
            ])
        writer.writerow([])

        writer.writerow(["Recommendations"])
        writer.writerow(["Priority", "Type", "Title", "Reason"])
        for rec in report.get("recommendations", []):
            writer.writerow([
                rec.get("priority", ""),
                rec.get("type", ""),
                rec.get("title", ""),
                rec.get("reason", ""),
            ])

    def _flatten_nlp_csv(self, writer, report: dict):
        """Flatten NLP analysis report to CSV rows."""
        writer.writerow(["NLP Analysis Report"])
        writer.writerow([])

        sentiment = report.get("sentiment_trend", {})
        writer.writerow(["Sentiment Trend"])
        writer.writerow(["Date", "Ticket Count", "Avg Sentiment", "Positive", "Negative", "Neutral"])
        for dp in sentiment.get("time_series", []):
            writer.writerow([
                dp.get("date", ""),
                dp.get("ticket_count", ""),
                dp.get("avg_sentiment_score", ""),
                dp.get("positive_count", ""),
                dp.get("negative_count", ""),
                dp.get("neutral_count", ""),
            ])
        writer.writerow([])

        ka = report.get("ka_recommendations", {})
        writer.writerow(["Knowledge Article Recommendations"])
        writer.writerow(["Priority", "Type", "Title", "Reason", "Potential Savings (hrs)"])
        for rec in ka.get("recommendations", []):
            writer.writerow([
                rec.get("priority", ""),
                rec.get("type", ""),
                rec.get("title", ""),
                rec.get("reason", ""),
                rec.get("potential_savings_hours", ""),
            ])

    def _flatten_detailed_csv(self, writer, report: dict):
        """Flatten detailed report to CSV rows."""
        writer.writerow(["Detailed Analysis Report"])
        writer.writerow([])
        self._flatten_summary_csv(writer, report.get("summary", {}))
        writer.writerow([])

        writer.writerow(["Category Analysis"])
        writer.writerow(["Category", "Count", "%", "Resolved", "Open", "Avg Resolution (hrs)"])
        for cat in report.get("category_insights", {}).get("categories", []):
            writer.writerow([
                cat.get("category", ""),
                cat.get("count", ""),
                cat.get("percentage", ""),
                cat.get("resolved_count", ""),
                cat.get("open_count", ""),
                cat.get("avg_resolution_hours", ""),
            ])

    # ------------------------------------------------------------------
    # HTML section builders
    # ------------------------------------------------------------------

    def _build_html_sections(self, report_type: str, data: dict) -> str:
        """Build HTML sections for the report."""
        sections = ""

        if report_type == "summary":
            sections += self._html_kpi_cards(data.get("key_metrics", {}))
            sections += self._html_table("Status Distribution", data.get("volume_breakdown", {}), ["Status", "Count"])
            sections += self._html_table("Priority Distribution", data.get("priority_breakdown", {}), ["Priority", "Count"])
            sections += self._html_bars("Category Distribution", data.get("category_distribution", []), "category", "count")
            sections += self._html_alerts(data.get("alerts", []))

        elif report_type == "executive":
            sections += self._html_kpi_cards(data.get("kpi_summary", {}))
            sections += self._html_scorecard(data.get("scorecard", {}))
            sections += self._html_alerts(data.get("risk_alerts", []))
            sections += self._html_table("Team Performance", data.get("team_performance_highlights", []),
                                         ["Team", "Tickets", "Resolution Rate", "Avg Resolution"])
            sections += self._html_table("Recommendations", data.get("recommendations", []),
                                         ["Priority", "Type", "Title", "Reason"])

        elif report_type == "performance":
            perf = data.get("team_performance", {})
            sections += self._html_table("Team Performance",
                                         perf.get("groups", []),
                                         ["Team", "Total", "Resolved", "Open", "Team Size", "Avg Res (hrs)"])
            pri = data.get("priority_analysis", {})
            sections += self._html_table("Priority SLA Compliance",
                                         pri.get("priorities", []),
                                         ["Priority", "Count", "SLA Target", "SLA %"])

        elif report_type == "nlp_analysis":
            trend = data.get("sentiment_trend", {})
            sections += self._html_table("Daily Sentiment",
                                         trend.get("time_series", []),
                                         ["Date", "Volume", "Avg Sentiment", "Positive", "Negative"])
            ka = data.get("ka_recommendations", {})
            sections += self._html_table("Knowledge Article Recommendations",
                                         ka.get("recommendations", []),
                                         ["Priority", "Type", "Title", "Reason"])

        elif report_type == "detailed":
            summary = data.get("summary", {})
            sections += self._html_kpi_cards(summary.get("key_metrics", {}))
            categories = data.get("category_insights", {}).get("categories", [])
            sections += self._html_table("Category Analysis", categories,
                                         ["Category", "Count", "%", "Resolved", "Open", "Avg Res (hrs)"])
            priorities = data.get("priority_insights", {}).get("priorities", [])
            sections += self._html_table("Priority Analysis", priorities,
                                         ["Priority", "Count", "Resolved", "Open", "SLA %", "Escalation %"])

        return sections

    def _html_kpi_cards(self, metrics: dict) -> str:
        """Generate KPI card grid HTML."""
        if not metrics:
            return ""

        cards = ""
        labels_map = {
            "total_tickets": "Total Tickets",
            "open_tickets": "Open Tickets",
            "resolved_tickets": "Resolved Tickets",
            "resolution_rate": "Resolution Rate",
            "avg_resolution_time_hours": "Avg Resolution (hrs)",
            "avg_sentiment_score": "Avg Sentiment",
            "anomaly_count": "Anomalies",
            "duplicate_count": "Duplicates",
            "insight_coverage": "NLP Coverage",
        }

        for key, value in metrics.items():
            label = labels_map.get(key, key.replace("_", " ").title())
            display_val = f"{value}%" if key in ("resolution_rate", "insight_coverage") else str(value)
            cards += f"""<div class="kpi-card">
                <div class="value">{display_val}</div>
                <div class="label">{label}</div>
            </div>\n"""

        return f'<div class="section"><h2>Key Performance Indicators</h2><div class="kpi-grid">{cards}</div></div>'

    def _html_table(self, title: str, rows: list, headers: list) -> str:
        """Generate a data table HTML section."""
        if not rows:
            return ""

        thead = "".join(f"<th>{h}</th>" for h in headers)
        tbody = ""
        for row in rows:
            if isinstance(row, dict):
                cells = ""
                for h in headers:
                    key = h.lower().replace(" ", "_").replace("(hrs)", "").replace("(%)", "").strip("_")
                    val = row.get(key) or row.get(h.lower().replace(" ", "_")) or ""
                    cells += f"<td>{val}</td>"
                tbody += f"<tr>{cells}</tr>\n"
            else:
                cells = "".join(f"<td>{v}</td>" for v in row)
                tbody += f"<tr>{cells}</tr>\n"

        return f"""<div class="section">
            <h2>{title}</h2>
            <table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
        </div>"""

    def _html_bars(self, title: str, items: list, label_key: str, value_key: str) -> str:
        """Generate a horizontal bar chart as HTML."""
        if not items:
            return ""

        max_val = max((item.get(value_key, 0) or 0 for item in items), default=1) or 1
        bars = ""
        for item in items[:10]:
            label = item.get(label_key, "")
            value = item.get(value_key, 0) or 0
            width = max(2, int(value / max_val * 300))
            bars += f"""<div class="bar-chart">
                <span class="bar-label">{label}</span>
                <div class="bar" style="width:{width}px"></div>
                <span class="bar-value">{value}</span>
            </div>\n"""

        return f'<div class="section"><h2>{title}</h2>{bars}</div>'

    def _html_alerts(self, alerts: list) -> str:
        """Generate alerts section HTML."""
        if not alerts:
            return ""

        items = ""
        for alert in alerts:
            level = alert.get("level", "info")
            cls = f"alert-{level}"
            msg = alert.get("message", "")
            action = alert.get("action", "")
            items += f"""<p class="{cls}">
                <strong>[{level.upper()}]</strong> {msg}
                {f'<br><em>Action: {action}</em>' if action else ''}
            </p>\n"""

        return f'<div class="section"><h2>Alerts &amp; Notifications</h2>{items}</div>'

    def _html_scorecard(self, scorecard: dict) -> str:
        """Generate scorecard section HTML."""
        if not scorecard:
            return ""

        score = scorecard.get("overall_score", 0)
        color = "#16a34a" if score >= 70 else "#d97706" if score >= 40 else "#dc2626"

        items = ""
        for category, value in scorecard.get("categories", {}).items():
            items += f"<tr><td>{category}</td><td>{value}/100</td></tr>\n"

        return f"""<div class="section">
            <h2>Health Scorecard</h2>
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="value" style="color:{color}">{score}</div>
                    <div class="label">Overall Health Score</div>
                </div>
            </div>
            <table><thead><tr><th>Category</th><th>Score</th></tr></thead>
            <tbody>{items}</tbody></table>
        </div>"""

    # ------------------------------------------------------------------
    # Scorecard computation
    # ------------------------------------------------------------------

    def _compute_scorecard(self, summary: dict, performance: dict, ka_recs: dict) -> dict:
        """Compute an overall health scorecard (0-100).

        Categories:
        - Volume health (open ticket ratio)
        - Resolution efficiency (resolution rate, avg time)
        - Sentiment health (negative sentiment rate)
        - NLP coverage (percentage of tickets analysed)
        """
        scores = {}

        # Volume health: lower open rate is better
        km = summary.get("key_metrics", {})
        total = km.get("total_tickets", 0)
        open_count = km.get("open_tickets", 0)
        if total > 0:
            open_rate = open_count / total
            scores["Volume Health"] = max(0, int(100 - open_rate * 150))
        else:
            scores["Volume Health"] = 50

        # Resolution efficiency
        res_rate = km.get("resolution_rate", 0)
        avg_res = km.get("avg_resolution_time_hours")
        res_score = min(100, int(res_rate))
        if avg_res is not None:
            if avg_res <= 4:
                res_score = 100
            elif avg_res <= 8:
                res_score = 85
            elif avg_res <= 24:
                res_score = 70
            elif avg_res <= 48:
                res_score = 50
            else:
                res_score = max(0, 100 - int(avg_res))
        scores["Resolution Efficiency"] = res_score

        # Sentiment health
        sentiment_dist = summary.get("sentiment_distribution", {})
        total_sent = sum(sentiment_dist.values())
        if total_sent > 0:
            neg_rate = sentiment_dist.get("Negative", 0) / total_sent
            pos_rate = sentiment_dist.get("Positive", 0) / total_sent
            scores["Sentiment Health"] = max(0, int(pos_rate * 100 - neg_rate * 50))
        else:
            scores["Sentiment Health"] = 50

        # NLP coverage
        coverage = km.get("insight_coverage", 0)
        scores["NLP Coverage"] = int(coverage)

        # Overall (weighted average)
        overall = int(
            scores["Volume Health"] * 0.25 +
            scores["Resolution Efficiency"] * 0.30 +
            scores["Sentiment Health"] * 0.20 +
            scores["NLP Coverage"] * 0.25
        )

        return {
            "overall_score": overall,
            "grade": "A" if overall >= 85 else "B" if overall >= 70 else "C" if overall >= 55 else "D" if overall >= 40 else "F",
            "categories": scores,
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_dict(d: dict, prefix: str = "") -> List:
        """Recursively flatten a nested dict into (key, value) tuples."""
        items = []
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.extend(ReportGenerator._flatten_dict(v, full_key))
            elif isinstance(v, list):
                items.append((full_key, f"[{len(v)} items]"))
            else:
                items.append((full_key, v))
        return items
