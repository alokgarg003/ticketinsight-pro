"""
Insights generator for TicketInsight Pro.

Computes aggregate statistics, KPIs, trend analyses, and actionable
recommendations from ticket data stored in the database.  Designed to be
called from API endpoints and CLI commands.
"""

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ticketinsight.utils.logger import get_logger

logger = get_logger(__name__)


class InsightsGenerator:
    """Generates comprehensive ticket insights from analysed data.

    Wraps database queries with business-logic calculations to produce
    dashboard-ready metrics and executive summaries.

    Parameters
    ----------
    db_manager : DatabaseManager
        Active database manager with an initialised Flask app context.
    nlp_engine : NLPEngine or None
        Optional NLP engine for on-demand text analysis.
    """

    def __init__(self, db_manager, nlp_engine=None):
        self.db = db_manager
        self.nlp = nlp_engine
        self.logger = get_logger("insights.generator")

    # ------------------------------------------------------------------
    # Executive summary
    # ------------------------------------------------------------------

    def generate_summary(self, filters: Optional[Dict[str, Any]] = None) -> dict:
        """Generate executive summary of ticket data.

        Computes total volume, open/resolved breakdown, key metrics,
        sentiment overview, and priority alerts.

        Parameters
        ----------
        filters : dict | None
            Optional filter dict passed to :meth:`DatabaseManager.get_tickets`.

        Returns
        -------
        dict
            Comprehensive summary with the following top-level keys:
            - ``total_tickets`` (int)
            - ``volume_breakdown`` (dict by status)
            - ``priority_breakdown`` (dict by priority)
            - ``key_metrics`` (avg resolution time, sentiment, etc.)
            - ``category_distribution`` (dict by category)
            - ``trend`` (7-day volume trend)
            - ``alerts`` (list of items requiring attention)
        """
        filters = filters or {}
        stats = self._safe_get_statistics()

        total = stats.get("total_tickets", 0)
        by_status = stats.get("by_status", {})
        by_priority = stats.get("by_priority", {})
        by_category = stats.get("by_category", {})
        sentiment_dist = stats.get("sentiment_distribution", {})

        open_count = by_status.get("Open", 0) + by_status.get("In Progress", 0)
        resolved_count = by_status.get("Resolved", 0) + by_status.get("Closed", 0)

        # Key metrics
        key_metrics = {
            "total_tickets": total,
            "open_tickets": open_count,
            "resolved_tickets": resolved_count,
            "resolution_rate": round(resolved_count / total * 100, 1) if total else 0,
            "avg_resolution_time_hours": stats.get("avg_resolution_time_hours"),
            "avg_sentiment_score": stats.get("avg_sentiment_score", 0.0),
            "anomaly_count": stats.get("anomaly_count", 0),
            "duplicate_count": stats.get("duplicate_count", 0),
            "tickets_with_insights": stats.get("tickets_with_insights", 0),
            "insight_coverage": round(
                stats.get("tickets_with_insights", 0) / total * 100, 1
            ) if total else 0,
        }

        # 7-day volume trend
        trend = self._compute_volume_trend(days=7)

        # Generate alerts based on data patterns
        alerts = self._generate_alerts(stats, by_status, by_priority)

        # Top categories
        sorted_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        top_categories = [
            {"category": cat, "count": cnt}
            for cat, cnt in sorted_categories[:10]
        ]

        return {
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "total_tickets": total,
            "volume_breakdown": by_status,
            "priority_breakdown": by_priority,
            "key_metrics": key_metrics,
            "category_distribution": top_categories,
            "sentiment_distribution": sentiment_dist,
            "trend": trend,
            "alerts": alerts,
        }

    # ------------------------------------------------------------------
    # Category analysis
    # ------------------------------------------------------------------

    def generate_category_insights(self) -> dict:
        """Deep analysis of ticket categories.

        Returns distribution, trend, average resolution time per
        category, and recommendations for the top categories.
        """
        tickets = self._get_all_tickets()

        if not tickets:
            return self._empty_result("No ticket data available")

        category_data = defaultdict(lambda: {
            "count": 0,
            "resolved": 0,
            "open": 0,
            "resolution_times": [],
            "sentiment_scores": [],
            "priorities": Counter(),
        })

        for t in tickets:
            cat = t.get("category", "Uncategorized") or "Uncategorized"
            cd = category_data[cat]
            cd["count"] += 1

            status = t.get("status", "")
            if status in ("Resolved", "Closed"):
                cd["resolved"] += 1
            elif status in ("Open", "In Progress"):
                cd["open"] += 1

            # Resolution time
            opened = t.get("opened_at")
            resolved = t.get("resolved_at")
            if opened and resolved:
                opened_dt = self._parse_dt(opened)
                resolved_dt = self._parse_dt(resolved)
                if opened_dt and resolved_dt:
                    hours = (resolved_dt - opened_dt).total_seconds() / 3600.0
                    cd["resolution_times"].append(hours)

            # Sentiment
            score = t.get("sentiment_score", 0.0)
            if score != 0.0:
                cd["sentiment_scores"].append(score)

            # Priority
            pri = t.get("priority", "Unknown")
            cd["priorities"][pri] += 1

        categories = []
        total = len(tickets)
        for cat, cd in sorted(category_data.items(), key=lambda x: x[1]["count"], reverse=True):
            avg_res = round(sum(cd["resolution_times"]) / len(cd["resolution_times"]), 2) if cd["resolution_times"] else None
            avg_sent = round(sum(cd["sentiment_scores"]) / len(cd["sentiment_scores"]), 4) if cd["sentiment_scores"] else None
            top_priority = cd["priorities"].most_common(1)[0][0] if cd["priorities"] else "Unknown"

            categories.append({
                "category": cat,
                "count": cd["count"],
                "percentage": round(cd["count"] / total * 100, 1),
                "resolved_count": cd["resolved"],
                "open_count": cd["open"],
                "avg_resolution_hours": avg_res,
                "avg_sentiment_score": avg_sent,
                "top_priority": top_priority,
                "recommendation": self._category_recommendation(cat, cd["count"], cd["open"], avg_res),
            })

        return {
            "total_categories": len(categories),
            "categories": categories,
        }

    # ------------------------------------------------------------------
    # Priority analysis
    # ------------------------------------------------------------------

    def generate_priority_insights(self) -> dict:
        """Analysis of priority distribution and handling performance.

        Returns P1-P4 breakdown, escalation rates, SLA compliance,
        and resolution time by priority.
        """
        tickets = self._get_all_tickets()

        if not tickets:
            return self._empty_result("No ticket data available")

        priority_data = defaultdict(lambda: {
            "count": 0,
            "resolved": 0,
            "open": 0,
            "resolution_times": [],
        })

        for t in tickets:
            pri = t.get("priority", "Unknown") or "Unknown"
            pd = priority_data[pri]
            pd["count"] += 1

            status = t.get("status", "")
            if status in ("Resolved", "Closed"):
                pd["resolved"] += 1
            elif status in ("Open", "In Progress"):
                pd["open"] += 1

            opened = t.get("opened_at")
            resolved = t.get("resolved_at")
            if opened and resolved:
                opened_dt = self._parse_dt(opened)
                resolved_dt = self._parse_dt(resolved)
                if opened_dt and resolved_dt:
                    hours = (resolved_dt - opened_dt).total_seconds() / 3600.0
                    pd["resolution_times"].append(hours)

        # SLA targets (hours)
        sla_targets = {"Critical": 4, "High": 8, "Medium": 24, "Low": 72}

        priorities = []
        order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Unknown": 4}
        for pri in sorted(priority_data.keys(), key=lambda p: order.get(p, 99)):
            pd = priority_data[pri]
            avg_res = round(sum(pd["resolution_times"]) / len(pd["resolution_times"]), 2) if pd["resolution_times"] else None
            target = sla_targets.get(pri)

            # SLA compliance
            sla_pct = None
            if target and pd["resolution_times"]:
                within_sla = sum(1 for h in pd["resolution_times"] if h <= target)
                sla_pct = round(within_sla / len(pd["resolution_times"]) * 100, 1)

            # Escalation rate (Critical + High that are still open)
            escalation_rate = 0.0
            if pri in ("Critical", "High") and pd["count"] > 0:
                escalation_rate = round(pd["open"] / pd["count"] * 100, 1)

            priorities.append({
                "priority": pri,
                "count": pd["count"],
                "resolved": pd["resolved"],
                "open": pd["open"],
                "avg_resolution_hours": avg_res,
                "sla_target_hours": target,
                "sla_compliance_pct": sla_pct,
                "escalation_rate_pct": escalation_rate,
            })

        return {
            "total_tickets": len(tickets),
            "sla_targets_hours": sla_targets,
            "priorities": priorities,
        }

    # ------------------------------------------------------------------
    # Sentiment trend
    # ------------------------------------------------------------------

    def generate_sentiment_trend(self, days: int = 30) -> dict:
        """Sentiment analysis trends over time.

        Computes daily sentiment scores, correlates with ticket volume,
        and breaks down by category.

        Parameters
        ----------
        days : int
            Number of days to include in the trend (default 30).

        Returns
        -------
        dict
            Daily sentiment time series with volume correlation.
        """
        tickets = self._get_all_tickets()
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        daily_data = defaultdict(lambda: {"scores": [], "count": 0, "positive": 0, "negative": 0, "neutral": 0})

        for t in tickets:
            opened_str = t.get("opened_at")
            if not opened_str:
                continue
            opened_dt = self._parse_dt(opened_str)
            if opened_dt is None or opened_dt < since:
                continue

            day_key = opened_dt.strftime("%Y-%m-%d")
            dd = daily_data[day_key]
            dd["count"] += 1

            score = t.get("sentiment_score", 0.0)
            if score != 0.0:
                dd["scores"].append(score)

            label = t.get("sentiment_label", "Neutral")
            if label == "Positive":
                dd["positive"] += 1
            elif label == "Negative":
                dd["negative"] += 1
            else:
                dd["neutral"] += 1

        time_series = []
        for day_key in sorted(daily_data.keys()):
            dd = daily_data[day_key]
            avg_score = round(sum(dd["scores"]) / len(dd["scores"]), 4) if dd["scores"] else None
            time_series.append({
                "date": day_key,
                "ticket_count": dd["count"],
                "avg_sentiment_score": avg_score,
                "analyzed_count": len(dd["scores"]),
                "positive_count": dd["positive"],
                "negative_count": dd["negative"],
                "neutral_count": dd["neutral"],
            })

        # Overall stats for the period
        all_scores = []
        for dd in daily_data.values():
            all_scores.extend(dd["scores"])

        overall_avg = round(sum(all_scores) / len(all_scores), 4) if all_scores else None

        # Sentiment categories
        total_labeled = sum(dd["positive"] + dd["negative"] + dd["neutral"] for dd in daily_data.values())

        return {
            "period_days": days,
            "total_tickets": sum(dd["count"] for dd in daily_data.values()),
            "overall_avg_sentiment": overall_avg,
            "positive_rate": round(sum(dd["positive"] for dd in daily_data.values()) / total_labeled * 100, 1) if total_labeled else 0,
            "negative_rate": round(sum(dd["negative"] for dd in daily_data.values()) / total_labeled * 100, 1) if total_labeled else 0,
            "time_series": time_series,
        }

    # ------------------------------------------------------------------
    # Team performance
    # ------------------------------------------------------------------

    def generate_team_performance(self) -> dict:
        """Team and assignee performance metrics.

        Computes tickets resolved, average resolution time, workload
        distribution, and individual assignee statistics.
        """
        tickets = self._get_all_tickets()

        if not tickets:
            return self._empty_result("No ticket data available")

        # By assignment group
        group_data = defaultdict(lambda: {
            "total": 0,
            "resolved": 0,
            "open": 0,
            "resolution_times": [],
            "assignees": set(),
            "categories": Counter(),
        })

        # By assignee
        assignee_data = defaultdict(lambda: {
            "total": 0,
            "resolved": 0,
            "open": 0,
            "resolution_times": [],
        })

        for t in tickets:
            grp = t.get("assignment_group", "Unassigned") or "Unassigned"
            assignee = t.get("assignee", "Unassigned") or "Unassigned"
            status = t.get("status", "")

            gd = group_data[grp]
            gd["total"] += 1
            gd["assignees"].add(assignee)
            gd["categories"][t.get("category", "Unknown") or "Unknown"] += 1

            ad = assignee_data[assignee]
            ad["total"] += 1

            if status in ("Resolved", "Closed"):
                gd["resolved"] += 1
                ad["resolved"] += 1
            elif status in ("Open", "In Progress"):
                gd["open"] += 1
                ad["open"] += 1

            opened = t.get("opened_at")
            resolved = t.get("resolved_at")
            if opened and resolved:
                opened_dt = self._parse_dt(opened)
                resolved_dt = self._parse_dt(resolved)
                if opened_dt and resolved_dt:
                    hours = (resolved_dt - opened_dt).total_seconds() / 3600.0
                    gd["resolution_times"].append(hours)
                    ad["resolution_times"].append(hours)

        groups = []
        for grp, gd in sorted(group_data.items(), key=lambda x: x[1]["total"], reverse=True):
            avg_res = round(sum(gd["resolution_times"]) / len(gd["resolution_times"]), 2) if gd["resolution_times"] else None
            top_cat = gd["categories"].most_common(3)

            groups.append({
                "group": grp,
                "total_tickets": gd["total"],
                "resolved_tickets": gd["resolved"],
                "open_tickets": gd["open"],
                "team_size": len(gd["assignees"]),
                "avg_resolution_hours": avg_res,
                "top_categories": [{"category": c, "count": n} for c, n in top_cat],
            })

        assignees = []
        for assignee, ad in sorted(assignee_data.items(), key=lambda x: x[1]["total"], reverse=True):
            avg_res = round(sum(ad["resolution_times"]) / len(ad["resolution_times"]), 2) if ad["resolution_times"] else None
            assignees.append({
                "assignee": assignee,
                "total_tickets": ad["total"],
                "resolved_tickets": ad["resolved"],
                "open_tickets": ad["open"],
                "avg_resolution_hours": avg_res,
            })

        # Unassigned tickets
        unassigned = group_data.get("Unassigned", {})
        unassigned_count = unassigned.get("open", 0)

        return {
            "total_groups": len(groups),
            "total_assignees": len(assignees),
            "unassigned_open_tickets": unassigned_count,
            "groups": groups[:20],
            "top_assignees": assignees[:20],
        }

    # ------------------------------------------------------------------
    # Knowledge article recommendations
    # ------------------------------------------------------------------

    def generate_ka_recommendations(self) -> dict:
        """Generate knowledge article recommendations from tickets.

        Identifies recurring issues that should have knowledge articles
        based on duplicate detection, topic clustering, and category
        frequency analysis.
        """
        tickets = self._get_all_tickets()

        if not tickets:
            return self._empty_result("No ticket data available")

        # 1. Identify high-frequency categories
        category_counter = Counter(t.get("category", "Unknown") or "Unknown" for t in tickets)
        high_freq_categories = [
            cat for cat, cnt in category_counter.most_common(5) if cnt >= 2
        ]

        # 2. Identify duplicate clusters
        duplicate_clusters = defaultdict(list)
        for t in tickets:
            dup_id = t.get("duplicate_of_id")
            if dup_id is not None:
                duplicate_clusters[dup_id].append(t)

        # 3. Identify tickets with similar titles (simple word-overlap heuristic)
        title_words = defaultdict(list)
        for t in tickets:
            title = t.get("title", "")
            if title:
                words = set(w.lower() for w in title.split() if len(w) > 3)
                # Use first 2 meaningful words as a signature
                sig = " ".join(sorted(w for w in words if len(w) > 4)[:2])
                if sig:
                    title_words[sig].append(t)

        # Generate recommendations
        recommendations = []

        # From duplicate clusters
        for master_id, dup_tickets in duplicate_clusters.items():
            if len(dup_tickets) >= 1:
                master = next((t for t in tickets if t.get("id") == master_id), dup_tickets[0])
                recommendations.append({
                    "type": "duplicate_reduction",
                    "priority": "high" if len(dup_tickets) >= 3 else "medium",
                    "title": f"Knowledge Article: {master.get('title', 'Untitled')[:80]}",
                    "reason": f"{len(dup_tickets) + 1} duplicate tickets found",
                    "category": master.get("category", ""),
                    "suggested_ka_title": f"How to resolve: {master.get('title', 'common issue')[:60]}",
                    "potential_savings_hours": round((len(dup_tickets) + 1) * 0.5, 1),
                    "source_tickets": [t.get("ticket_id") for t in [master] + dup_tickets[:5]],
                })

        # From high-frequency categories
        for cat in high_freq_categories:
            cat_tickets = [t for t in tickets if (t.get("category") or "") == cat and t.get("status") in ("Resolved", "Closed")]
            if len(cat_tickets) >= 2:
                # Get the most common words in titles for this category
                words = Counter()
                for t in cat_tickets[:20]:
                    title = t.get("title", "")
                    for w in title.lower().split():
                        if len(w) > 3:
                            words[w] += 1

                top_words = [w for w, _ in words.most_common(5) if w not in ("cannot", "issue", "ticket", "request")]
                kw_str = ", ".join(top_words[:3]) if top_words else cat

                recommendations.append({
                    "type": "category_guide",
                    "priority": "medium",
                    "title": f"Knowledge Article: {cat} Troubleshooting Guide",
                    "reason": f"{len(cat_tickets)} resolved tickets in {cat}",
                    "category": cat,
                    "suggested_ka_title": f"{cat} troubleshooting guide ({kw_str})",
                    "keywords": top_words[:5],
                    "source_tickets": [t.get("ticket_id") for t in cat_tickets[:5]],
                })

        # From title word clusters
        for sig, sig_tickets in title_words.items():
            if len(sig_tickets) >= 3:
                first = sig_tickets[0]
                recommendations.append({
                    "type": "recurring_issue",
                    "priority": "low",
                    "title": f"FAQ: {first.get('title', 'Common issue')[:80]}",
                    "reason": f"{len(sig_tickets)} tickets with similar titles",
                    "category": first.get("category", ""),
                    "suggested_ka_title": f"FAQ: What to do when {sig.replace(' ', ' ')}",
                    "source_tickets": [t.get("ticket_id") for t in sig_tickets[:5]],
                })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda r: priority_order.get(r["priority"], 3))

        # Summary
        total_savings = sum(r.get("potential_savings_hours", 0) for r in recommendations)

        return {
            "total_recommendations": len(recommendations),
            "high_priority_count": sum(1 for r in recommendations if r["priority"] == "high"),
            "medium_priority_count": sum(1 for r in recommendations if r["priority"] == "medium"),
            "estimated_total_savings_hours": round(total_savings, 1),
            "recommendations": recommendations[:50],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _safe_get_statistics(self) -> Dict[str, Any]:
        """Call db.get_statistics() safely, returning empty dict on failure."""
        try:
            return self.db.get_statistics()
        except Exception as exc:
            self.logger.error("Failed to get statistics: %s", exc)
            return {}

    def _get_all_tickets(self) -> List[Dict[str, Any]]:
        """Fetch all tickets from the database."""
        try:
            result = self.db.get_tickets(page=1, per_page=50000)
            return result.get("tickets", [])
        except Exception as exc:
            self.logger.error("Failed to get tickets: %s", exc)
            return []

    def _compute_volume_trend(self, days: int = 7) -> List[Dict[str, Any]]:
        """Compute daily ticket volume trend for the last N days."""
        from collections import defaultdict

        tickets = self._get_all_tickets()
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        daily = defaultdict(int)
        for t in tickets:
            opened_str = t.get("opened_at")
            if not opened_str:
                continue
            dt = self._parse_dt(opened_str)
            if dt and dt >= since:
                daily[dt.strftime("%Y-%m-%d")] += 1

        trend = []
        for day_key in sorted(daily.keys()):
            trend.append({
                "date": day_key,
                "count": daily[day_key],
            })

        return trend

    def _generate_alerts(self, stats: Dict, by_status: Dict, by_priority: Dict) -> List[Dict]:
        """Generate actionable alerts based on current data patterns."""
        alerts = []

        # Critical tickets open
        critical_open = 0
        for status in ("Open", "In Progress"):
            # We need to cross-reference, so use total Critical minus resolved/closed
            pass
        critical_total = by_priority.get("Critical", 0)
        if critical_total > 0:
            alerts.append({
                "level": "critical",
                "type": "priority",
                "message": f"{critical_total} Critical priority ticket(s) in system",
                "action": "Review and escalate Critical tickets immediately",
            })

        # High open ticket count
        open_count = by_status.get("Open", 0) + by_status.get("In Progress", 0)
        total = stats.get("total_tickets", 0)
        if total > 0 and open_count / total > 0.6:
            alerts.append({
                "level": "warning",
                "type": "volume",
                "message": f"{open_count / total * 100:.0f}% of tickets are still open",
                "action": "Consider allocating additional resources",
            })

        # Negative sentiment spike
        sentiment_dist = stats.get("sentiment_distribution", {})
        neg_count = sentiment_dist.get("Negative", 0)
        total_labeled = sum(sentiment_dist.values())
        if total_labeled > 0 and neg_count / total_labeled > 0.3:
            alerts.append({
                "level": "warning",
                "type": "sentiment",
                "message": f"{neg_count / total_labeled * 100:.0f}% of analyzed tickets have negative sentiment",
                "action": "Investigate common causes of user dissatisfaction",
            })

        # Anomalies detected
        anomaly_count = stats.get("anomaly_count", 0)
        if anomaly_count > 0:
            alerts.append({
                "level": "info",
                "type": "anomaly",
                "message": f"{anomaly_count} anomalous ticket(s) detected",
                "action": "Review anomaly details for potential systemic issues",
            })

        # Duplicate opportunities
        dup_count = stats.get("duplicate_count", 0)
        if dup_count > 0:
            alerts.append({
                "level": "info",
                "type": "duplicates",
                "message": f"{dup_count} duplicate ticket(s) found",
                "action": "Create knowledge articles to reduce recurring tickets",
            })

        return alerts

    @staticmethod
    def _parse_dt(dt_str) -> Optional[datetime]:
        """Parse an ISO format datetime string to a datetime object."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def _category_recommendation(category: str, count: int, open_count: int, avg_res: Optional[float]) -> str:
        """Generate a brief recommendation for a ticket category."""
        open_rate = round(open_count / count * 100, 1) if count else 0

        recs = {
            "Network": "Implement network monitoring and proactive alerting to reduce network-related tickets.",
            "Hardware": "Consider hardware lifecycle management and preventive maintenance schedules.",
            "Software": "Create software installation guides and self-service troubleshooting articles.",
            "Email": "Standardise email provisioning and implement automated account management.",
            "Security": "Strengthen security training and implement automated threat detection.",
            "Access Management": "Automate provisioning workflows with role-based access controls.",
            "Database": "Implement query performance monitoring and schedule regular maintenance.",
            "Audio/Visual": "Schedule regular equipment maintenance and firmware updates.",
        }

        base = recs.get(category, f"Analyze '{category}' ticket patterns to identify root causes.")
        if open_rate > 50:
            base += f" ({open_rate}% of {category} tickets are still open — consider additional staffing.)"
        elif avg_res and avg_res > 24:
            base += f" (Average resolution time is {avg_res}h — look for process improvements.)"

        return base

    @staticmethod
    def _empty_result(message: str) -> dict:
        """Return a standardised empty result dict."""
        return {
            "message": message,
            "total_items": 0,
            "data": [],
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
