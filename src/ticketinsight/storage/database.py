"""
Database layer for TicketInsight Pro.

Defines SQLAlchemy ORM models and the :class:`DatabaseManager` façade for
all data-access operations.  Uses Flask-SQLAlchemy and falls back to
SQLite when PostgreSQL is unavailable (development mode).

Models
------
- :class:`Ticket` — canonical ticket record with NLP enrichment fields.
- :class:`TicketInsight` — per-ticket analytical results.
- :class:`AuditLog` — immutable audit trail.
- :class:`DashboardConfig` — user-defined dashboard layouts.

Usage
-----
    from ticketinsight.storage.database import db, DatabaseManager

    db_mgr = DatabaseManager()
    db_mgr.init_app(app)
    db_mgr.create_all()
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from flask import Flask, current_app
from flask_sqlalchemy import SQLAlchemy

from ticketinsight.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# SQLAlchemy extension (initialised properly in DatabaseManager.init_app)
# ---------------------------------------------------------------------------
db = SQLAlchemy()

# ---------------------------------------------------------------------------
# JSON column type (compatible with both PostgreSQL and SQLite)
# ---------------------------------------------------------------------------

try:
    from sqlalchemy import JSON as _SaJsonType

    class JSONColumn(_SaJsonType):
        """JSON column type that serialises Python objects to JSON strings."""

        pass

except ImportError:
    # Extremely old SQLAlchemy fallback (should not happen with our deps)
    from sqlalchemy import Text

    class JSONColumn(Text):  # type: ignore[no-redef, misc]
        """Fallback JSON column that stores serialised JSON as text."""

        pass


# ===========================================================================
# ORM Models
# ===========================================================================


class Ticket(db.Model):  # type: ignore[name-defined]
    """Canonical ticket record with NLP-enrichment fields.

    Each row represents a single ITSM ticket ingested from an external
    source system (ServiceNow, Jira, CSV).
    """

    __tablename__ = "tickets"

    # --- Primary key ---
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # --- External identifiers ---
    ticket_id = db.Column(db.String(255), nullable=False, index=True, unique=True)
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, default="")
    priority = db.Column(db.String(50), default="Medium", index=True)
    status = db.Column(db.String(50), default="Open", index=True)
    category = db.Column(db.String(255), default="", index=True)
    assignment_group = db.Column(db.String(255), default="")
    assignee = db.Column(db.String(255), default="")

    # --- Timestamps (external) ---
    opened_at = db.Column(db.DateTime, nullable=True, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)

    # --- Internal timestamps ---
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

    # --- Source provenance ---
    source_system = db.Column(db.String(100), default="csv", index=True)
    raw_data = db.Column(JSONColumn, default=dict)

    # --- NLP enrichment fields ---
    sentiment_score = db.Column(db.Float, default=0.0, index=True)
    sentiment_label = db.Column(db.String(50), default="Neutral", index=True)
    predicted_category = db.Column(db.String(255), default="", index=True)
    topic_cluster = db.Column(db.Integer, nullable=True, index=True)
    duplicate_of_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=True)
    priority_predicted = db.Column(db.Boolean, default=False)
    anomaly_score = db.Column(db.Float, default=0.0, index=True)
    summary = db.Column(db.Text, default="")
    named_entities = db.Column(JSONColumn, default=dict)
    root_cause_cluster = db.Column(db.Integer, nullable=True, index=True)

    # --- Relationships ---
    insights = db.relationship(
        "TicketInsight",
        backref="ticket",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the ticket to a plain dictionary."""
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "category": self.category,
            "assignment_group": self.assignment_group,
            "assignee": self.assignee,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "source_system": self.source_system,
            "sentiment_score": self.sentiment_score,
            "sentiment_label": self.sentiment_label,
            "predicted_category": self.predicted_category,
            "topic_cluster": self.topic_cluster,
            "duplicate_of_id": self.duplicate_of_id,
            "priority_predicted": self.priority_predicted,
            "anomaly_score": self.anomaly_score,
            "summary": self.summary,
            "named_entities": self.named_entities or {},
            "root_cause_cluster": self.root_cause_cluster,
        }

    def __repr__(self) -> str:
        return (
            f"<Ticket id={self.id} ticket_id={self.ticket_id!r} "
            f"status={self.status!r} priority={self.priority!r}>"
        )


class TicketInsight(db.Model):  # type: ignore[name-defined]
    """Per-ticket analytical insight produced by the NLP pipeline.

    Each row stores one type of analysis result (sentiment, classification,
    topic, duplicate, anomaly, summary, NER, or root-cause) for a single
    ticket.
    """

    __tablename__ = "ticket_insights"

    # Valid insight types
    _VALID_TYPES = (
        "classification",
        "sentiment",
        "topic",
        "duplicate",
        "anomaly",
        "summary",
        "ner",
        "root_cause",
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    insight_type = db.Column(db.String(50), nullable=False, index=True)
    insight_data = db.Column(JSONColumn, default=dict)
    confidence = db.Column(db.Float, default=0.0)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the insight to a plain dictionary."""
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "insight_type": self.insight_type,
            "insight_data": self.insight_data or {},
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<TicketInsight id={self.id} ticket_id={self.ticket_id} "
            f"type={self.insight_type!r}>"
        )


class AuditLog(db.Model):  # type: ignore[name-defined]
    """Immutable audit log for tracking significant application actions.

    Every user-facing mutation (create, update, delete, pipeline run,
    config change) should produce a corresponding audit-log entry.
    """

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    entity_type = db.Column(db.String(100), nullable=False, index=True)
    entity_id = db.Column(db.String(255), nullable=True, index=True)
    user_id = db.Column(db.String(255), default="system")
    details = db.Column(JSONColumn, default=dict)
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
        index=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the audit log to a plain dictionary."""
        return {
            "id": self.id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "user_id": self.user_id,
            "details": self.details or {},
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"entity={self.entity_type!r}:{self.entity_id!r}>"
        )


class DashboardConfig(db.Model):  # type: ignore[name-defined]
    """User-defined dashboard configuration persisted in the database."""

    __tablename__ = "dashboard_configs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    config = db.Column(JSONColumn, default=dict)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the dashboard config to a plain dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "config": self.config or {},
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<DashboardConfig id={self.id} name={self.name!r}>"


# ===========================================================================
# Database Manager
# ===========================================================================


class DatabaseManager:
    """High-level façade for database initialisation and common operations.

    Wraps Flask-SQLAlchemy and provides convenience methods for seeding,
    bulk-importing, querying, and analytics.

    Usage
    -----
        db_mgr = DatabaseManager()
        db_mgr.init_app(flask_app)
        db_mgr.create_all()
    """

    def __init__(self) -> None:
        self._app: Optional[Flask] = None
        self._db_url: Optional[str] = None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_app(self, app: Flask) -> None:
        """Bind the database extension to a Flask application.

        Reads the ``database.url`` config key.  If the configured URL
        starts with ``postgresql`` and the driver cannot connect (e.g.
        PostgreSQL is not installed), the manager automatically falls
        back to a local SQLite database at ``data/ticketinsight.db``.

        Parameters
        ----------
        app : Flask
            The Flask application instance.
        """
        self._app = app

        # Resolve database URL from config
        try:
            from ticketinsight.config import ConfigManager
            config = ConfigManager()
            self._db_url = config.get("database", "url", "sqlite:///data/ticketinsight.db")
            pool_size = config.get("database", "pool_size", 10)
            echo = config.get("database", "echo", False)
            track_mod = config.get("database", "track_modifications", True)
        except Exception:
            self._db_url = "sqlite:///data/ticketinsight.db"
            pool_size = 10
            echo = False
            track_mod = True

        # Try PostgreSQL first; fall back to SQLite
        if self._db_url and "postgresql" in self._db_url:
            if not self._check_postgresql(self._db_url):
                logger.warning(
                    "PostgreSQL unavailable — falling back to SQLite for development"
                )
                self._db_url = "sqlite:///data/ticketinsight.db"
                # Create data directory if needed
                self._ensure_data_dir()

        app.config["SQLALCHEMY_DATABASE_URI"] = self._db_url
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = track_mod
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_size": pool_size,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "echo": echo,
        }

        db.init_app(app)

        logger.info("Database initialised with %s", self._db_url)

    @staticmethod
    def _check_postgresql(db_url: str) -> bool:
        """Attempt to connect to PostgreSQL; return ``True`` on success."""
        try:
            from sqlalchemy import create_engine
            engine = create_engine(db_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(db.text("SELECT 1"))
            engine.dispose()
            return True
        except Exception:
            return False

    @staticmethod
    def _ensure_data_dir() -> None:
        """Create the ``data/`` directory if it doesn't exist."""
        from pathlib import Path
        data_dir = Path("data")
        data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_all(self) -> None:
        """Create all tables in the database (no-op if they exist)."""
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")
        with self._app.app_context():
            db.create_all()
            logger.info("Database tables created/verified")

    def drop_all(self) -> None:
        """Drop **all** tables.  Use with extreme caution."""
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")
        with self._app.app_context():
            db.drop_all()
            logger.warning("All database tables have been dropped")

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------

    def seed_sample_data(self) -> int:
        """Populate the database with sample ticket data if it is empty.

        Creates 20 representative tickets spanning common IT support
        scenarios so that the dashboard has data to display immediately.

        Returns
        -------
        int
            Number of tickets inserted (0 if data already existed).
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            existing = Ticket.query.count()
            if existing > 0:
                logger.info("Database already has %d tickets — skipping seed", existing)
                return 0

            sample_tickets = self._generate_sample_tickets()
            self.bulk_insert_tickets(sample_tickets)
            logger.info("Seeded %d sample tickets", len(sample_tickets))
            return len(sample_tickets)

    @staticmethod
    def _generate_sample_tickets() -> List[Dict[str, Any]]:
        """Create a list of representative sample ticket dicts."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        samples = [
            {
                "ticket_id": "INC0010001",
                "title": "Cannot access email after password reset",
                "description": "User reports being unable to access Outlook Web App after resetting their password via the self-service portal. They receive 'incorrect password' error despite confirming the new password.",
                "priority": "High",
                "status": "In Progress",
                "category": "Email",
                "assignment_group": "IT Support",
                "assignee": "john.doe",
                "opened_at": now - timedelta(hours=4),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010002",
                "title": "VPN connection drops intermittently",
                "description": "Remote worker experiencing VPN disconnections every 20-30 minutes. Issue started after recent network infrastructure upgrade. User has tried restarting the VPN client and laptop.",
                "priority": "High",
                "status": "Open",
                "category": "Network",
                "assignment_group": "Network Operations",
                "assignee": "jane.smith",
                "opened_at": now - timedelta(hours=2),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010003",
                "title": "Printer on 3rd floor jamming",
                "description": "The HP LaserJet on the 3rd floor near reception keeps jamming. Paper trays have been refilled and the rollers cleaned but the issue persists.",
                "priority": "Medium",
                "status": "Resolved",
                "category": "Hardware",
                "assignment_group": "IT Support",
                "assignee": "bob.wilson",
                "opened_at": now - timedelta(days=1),
                "resolved_at": now - timedelta(hours=6),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010004",
                "title": "New employee onboarding — account setup",
                "description": "Please create accounts for new hire Sarah Chen (Department: Marketing, Start Date: Monday). Needs Active Directory, email, Slack, and access to the marketing SharePoint.",
                "priority": "Medium",
                "status": "In Progress",
                "category": "Access Management",
                "assignment_group": "IT Operations",
                "assignee": "admin.team",
                "opened_at": now - timedelta(hours=8),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010005",
                "title": "Laptop running extremely slow",
                "description": "Dell Latitude 5520 takes over 10 minutes to boot and applications freeze frequently. Task manager shows 95% disk usage at idle. User suspects it may have a failing hard drive.",
                "priority": "Medium",
                "status": "Open",
                "category": "Hardware",
                "assignment_group": "IT Support",
                "assignee": "",
                "opened_at": now - timedelta(days=2),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010006",
                "title": "Software license renewal for Adobe Creative Suite",
                "description": "Annual Adobe Creative Suite licenses for the Design department (12 seats) expire in 15 days. Please process the renewal before expiration to avoid disruption.",
                "priority": "Low",
                "status": "On Hold",
                "category": "Software",
                "assignment_group": "IT Procurement",
                "assignee": "procurement.team",
                "opened_at": now - timedelta(days=3),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010007",
                "title": "Unable to install required Python packages",
                "description": "Data analyst getting 'Permission denied' errors when trying to pip install pandas and numpy in their virtual environment. Corporate proxy may be blocking the package index.",
                "priority": "Medium",
                "status": "In Progress",
                "category": "Software",
                "assignment_group": "DevOps",
                "assignee": "devops.team",
                "opened_at": now - timedelta(hours=12),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010008",
                "title": "Security alert — suspicious login from foreign IP",
                "description": "Multiple failed login attempts detected for user mike.jones from IP addresses in Eastern Europe. Account has been temporarily locked as a precaution.",
                "priority": "Critical",
                "status": "In Progress",
                "category": "Security",
                "assignment_group": "Security Operations",
                "assignee": "security.team",
                "opened_at": now - timedelta(minutes=30),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010009",
                "title": "Shared drive access request for contractor",
                "description": "External contractor working on the Q4 project needs read-only access to \\\\fileserver\\projects\\Q4-Report. Manager approval attached.",
                "priority": "Low",
                "status": "Resolved",
                "category": "Access Management",
                "assignment_group": "IT Operations",
                "assignee": "admin.team",
                "opened_at": now - timedelta(days=2),
                "resolved_at": now - timedelta(days=1),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010010",
                "title": "Dual monitor setup not working",
                "description": "After IT replaced the docking station, the external monitors are not being detected. Only the laptop screen works. User has a Dell docking station and two Dell 24-inch monitors.",
                "priority": "Low",
                "status": "Open",
                "category": "Hardware",
                "assignment_group": "IT Support",
                "assignee": "",
                "opened_at": now - timedelta(hours=6),
                "source_system": "csv",
            },
            {
                "ticket_id": "REQ0010001",
                "title": "Upgrade RAM to 32GB for development workstations",
                "description": "Engineering team requests RAM upgrade from 16GB to 32GB for 15 Dell Precision workstations running Docker containers and local Kubernetes clusters.",
                "priority": "Medium",
                "status": "On Hold",
                "category": "Hardware",
                "assignment_group": "IT Procurement",
                "assignee": "",
                "opened_at": now - timedelta(days=5),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010011",
                "title": "WiFi not working in conference room B",
                "description": "Staff report no WiFi connectivity in conference room B on the 2nd floor. Other floors appear unaffected. Conference is scheduled there in 2 hours.",
                "priority": "High",
                "status": "Resolved",
                "category": "Network",
                "assignment_group": "Network Operations",
                "assignee": "network.team",
                "opened_at": now - timedelta(days=1, hours=3),
                "resolved_at": now - timedelta(days=1),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010012",
                "title": "Outlook calendar not syncing with mobile",
                "description": "Calendar events created on the desktop Outlook client do not appear on the user's iPhone. Meetings accepted via mobile also don't show on desktop. ActiveSync seems broken.",
                "priority": "Medium",
                "status": "Open",
                "category": "Email",
                "assignment_group": "IT Support",
                "assignee": "",
                "opened_at": now - timedelta(hours=10),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010013",
                "title": "Database query timeout in CRM application",
                "description": "Sales team experiencing 30-second timeouts when running customer search queries in the CRM system. The issue occurs intermittently but is more frequent during peak hours (10 AM - 2 PM).",
                "priority": "Critical",
                "status": "In Progress",
                "category": "Database",
                "assignment_group": "DBA Team",
                "assignee": "dba.team",
                "opened_at": now - timedelta(hours=1),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010014",
                "title": "Request for additional monitor for home office",
                "description": "Employee transitioning to hybrid work schedule needs a second monitor for their home office setup. Manager has approved the request.",
                "priority": "Low",
                "status": "Closed",
                "category": "Hardware",
                "assignment_group": "IT Procurement",
                "assignee": "procurement.team",
                "opened_at": now - timedelta(days=7),
                "resolved_at": now - timedelta(days=3),
                "closed_at": now - timedelta(days=2),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010015",
                "title": "Malware detected on employee workstation",
                "description": "Endpoint protection flagged suspicious activity on workstation WS-042. Quarantine action was taken. User clicked on a phishing email link disguised as a FedEx delivery notification.",
                "priority": "Critical",
                "status": "Resolved",
                "category": "Security",
                "assignment_group": "Security Operations",
                "assignee": "security.team",
                "opened_at": now - timedelta(days=4),
                "resolved_at": now - timedelta(days=3),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010016",
                "title": "Video conferencing audio issues in meeting rooms",
                "description": "Multiple meeting rooms report echo and feedback issues during video calls. Polycom units may need firmware update. Affects rooms 201, 305, and 410.",
                "priority": "Medium",
                "status": "Open",
                "category": "Audio/Visual",
                "assignment_group": "AV Team",
                "assignee": "",
                "opened_at": now - timedelta(days=3),
                "source_system": "csv",
            },
            {
                "ticket_id": "REQ0010002",
                "title": "Deploy new wireless access points in warehouse",
                "description": "Operations team reports poor WiFi coverage in the warehouse area. Need to install 4 additional enterprise-grade access points to ensure reliable connectivity for barcode scanners and tablets.",
                "priority": "High",
                "status": "On Hold",
                "category": "Network",
                "assignment_group": "Network Operations",
                "assignee": "",
                "opened_at": now - timedelta(days=10),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010017",
                "title": "Auto-update caused application compatibility issue",
                "description": "After Windows auto-update last night, the proprietary inventory management application crashes on launch. Rollback of the specific update resolves the issue.",
                "priority": "High",
                "status": "In Progress",
                "category": "Software",
                "assignment_group": "IT Support",
                "assignee": "john.doe",
                "opened_at": now - timedelta(hours=3),
                "source_system": "csv",
            },
            {
                "ticket_id": "INC0010018",
                "title": "Need to reset MFA for locked-out user",
                "description": "User lost their phone and cannot authenticate with MFA to access any company resources. Identity verification has been completed via manager.",
                "priority": "High",
                "status": "Resolved",
                "category": "Access Management",
                "assignment_group": "IT Operations",
                "assignee": "admin.team",
                "opened_at": now - timedelta(hours=5),
                "resolved_at": now - timedelta(hours=3),
                "source_system": "csv",
            },
        ]

        return samples

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def bulk_insert_tickets(self, tickets: Sequence[Dict[str, Any]]) -> int:
        """Efficiently insert multiple tickets in a single transaction.

        Parameters
        ----------
        tickets : sequence[dict]
            Each dict must contain at least ``ticket_id`` and ``title``.
            Other fields default if omitted.

        Returns
        -------
        int
            Number of tickets inserted.
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        inserted = 0
        with self._app.app_context():
            for ticket_data in tickets:
                ticket_id = ticket_data.get("ticket_id")
                if not ticket_id:
                    logger.warning("Skipping ticket without ticket_id: %s", ticket_data)
                    continue

                # Skip duplicates
                existing = Ticket.query.filter_by(ticket_id=ticket_id).first()
                if existing:
                    logger.debug("Ticket %s already exists — skipping", ticket_id)
                    continue

                ticket = Ticket(
                    ticket_id=ticket_id,
                    title=ticket_data.get("title", "Untitled"),
                    description=ticket_data.get("description", ""),
                    priority=ticket_data.get("priority", "Medium"),
                    status=ticket_data.get("status", "Open"),
                    category=ticket_data.get("category", ""),
                    assignment_group=ticket_data.get("assignment_group", ""),
                    assignee=ticket_data.get("assignee", ""),
                    opened_at=ticket_data.get("opened_at"),
                    resolved_at=ticket_data.get("resolved_at"),
                    closed_at=ticket_data.get("closed_at"),
                    updated_at=ticket_data.get("updated_at"),
                    source_system=ticket_data.get("source_system", "csv"),
                    raw_data=ticket_data.get("raw_data", {}),
                    sentiment_score=ticket_data.get("sentiment_score", 0.0),
                    sentiment_label=ticket_data.get("sentiment_label", "Neutral"),
                    predicted_category=ticket_data.get("predicted_category", ""),
                    topic_cluster=ticket_data.get("topic_cluster"),
                    duplicate_of_id=ticket_data.get("duplicate_of_id"),
                    priority_predicted=ticket_data.get("priority_predicted", False),
                    anomaly_score=ticket_data.get("anomaly_score", 0.0),
                    summary=ticket_data.get("summary", ""),
                    named_entities=ticket_data.get("named_entities", {}),
                    root_cause_cluster=ticket_data.get("root_cause_cluster"),
                )
                db.session.add(ticket)
                inserted += 1

            db.session.commit()
            logger.info("Bulk-inserted %d tickets (total attempted: %d)", inserted, len(tickets))

        return inserted

    def get_tickets(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        per_page: int = 25,
        sort_by: str = "opened_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """Query tickets with filtering, sorting, and pagination.

        Parameters
        ----------
        filters : dict | None
            Supported filter keys:
            - ``status`` (str or list[str])
            - ``priority`` (str or list[str])
            - ``category`` (str or list[str])
            - ``assignment_group`` (str)
            - ``source_system`` (str)
            - ``search`` (str) — full-text search on title and description
            - ``date_from`` (datetime) — opened_at >= date_from
            - ``date_to`` (datetime) — opened_at <= date_to
            - ``sentiment_label`` (str)
            - ``topic_cluster`` (int)
            - ``has_anomaly`` (bool) — anomaly_score > threshold
        page : int
            1-indexed page number.
        per_page : int
            Number of results per page (max 500).
        sort_by : str
            Column name to sort by (default: ``opened_at``).
        sort_order : str
            ``asc`` or ``desc`` (default).

        Returns
        -------
        dict
            ``{"tickets": [...], "total": int, "page": int, "per_page": int,
            "total_pages": int}``
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        filters = filters or {}
        page = max(1, page)
        per_page = max(1, min(per_page, 500))

        with self._app.app_context():
            query = Ticket.query

            # Apply filters
            if "status" in filters:
                status_val = filters["status"]
                if isinstance(status_val, list):
                    query = query.filter(Ticket.status.in_(status_val))
                else:
                    query = query.filter(Ticket.status == status_val)

            if "priority" in filters:
                priority_val = filters["priority"]
                if isinstance(priority_val, list):
                    query = query.filter(Ticket.priority.in_(priority_val))
                else:
                    query = query.filter(Ticket.priority == priority_val)

            if "category" in filters:
                cat_val = filters["category"]
                if isinstance(cat_val, list):
                    query = query.filter(Ticket.category.in_(cat_val))
                else:
                    query = query.filter(Ticket.category == cat_val)

            if "assignment_group" in filters:
                query = query.filter(Ticket.assignment_group == filters["assignment_group"])

            if "source_system" in filters:
                query = query.filter(Ticket.source_system == filters["source_system"])

            if "search" in filters and filters["search"]:
                search_term = f"%{filters['search']}%"
                query = query.filter(
                    db.or_(
                        Ticket.title.ilike(search_term),
                        Ticket.description.ilike(search_term),
                    )
                )

            if "date_from" in filters and filters["date_from"]:
                query = query.filter(Ticket.opened_at >= filters["date_from"])

            if "date_to" in filters and filters["date_to"]:
                query = query.filter(Ticket.opened_at <= filters["date_to"])

            if "sentiment_label" in filters:
                query = query.filter(Ticket.sentiment_label == filters["sentiment_label"])

            if "topic_cluster" in filters and filters["topic_cluster"] is not None:
                query = query.filter(Ticket.topic_cluster == filters["topic_cluster"])

            if filters.get("has_anomaly"):
                query = query.filter(Ticket.anomaly_score > 0.5)

            # Sorting
            sort_column = getattr(Ticket, sort_by, Ticket.opened_at)
            if sort_order.lower() == "asc":
                query = query.order_by(db.asc(sort_column))
            else:
                query = query.order_by(db.desc(sort_column))

            # Pagination
            total = query.count()
            total_pages = max(1, math.ceil(total / per_page))
            tickets = query.offset((page - 1) * per_page).limit(per_page).all()

            return {
                "tickets": [t.to_dict() for t in tickets],
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
            }

    def get_ticket_by_id(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single ticket by its external ``ticket_id``."""
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=ticket_id).first()
            if ticket is None:
                return None
            result = ticket.to_dict()
            result["insights"] = [i.to_dict() for i in ticket.insights.all()]
            return result

    def update_ticket_insights(
        self,
        ticket_id: str,
        insights: Dict[str, Any],
    ) -> bool:
        """Update NLP-derived fields on a ticket and create insight records.

        Parameters
        ----------
        ticket_id : str
            External ticket identifier.
        insights : dict
            Keys may include:
            - ``sentiment_score`` (float)
            - ``sentiment_label`` (str)
            - ``predicted_category`` (str)
            - ``topic_cluster`` (int)
            - ``anomaly_score`` (float)
            - ``summary`` (str)
            - ``named_entities`` (dict)
            - ``root_cause_cluster`` (int)
            - ``confidence`` (float, for the insight record)
            - ``duplicate_of_id`` (int)
            - ``priority_predicted`` (bool)
            - ``insight_type`` (str, e.g. "classification")
            - ``insight_data`` (dict, extra data for the insight record)

        Returns
        -------
        bool
            ``True`` if the ticket was found and updated.
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=ticket_id).first()
            if ticket is None:
                logger.warning("Cannot update insights — ticket %s not found", ticket_id)
                return False

            # Update direct fields on the Ticket model
            field_mapping = {
                "sentiment_score": "sentiment_score",
                "sentiment_label": "sentiment_label",
                "predicted_category": "predicted_category",
                "topic_cluster": "topic_cluster",
                "anomaly_score": "anomaly_score",
                "summary": "summary",
                "named_entities": "named_entities",
                "root_cause_cluster": "root_cause_cluster",
                "duplicate_of_id": "duplicate_of_id",
                "priority_predicted": "priority_predicted",
            }
            for insight_key, model_attr in field_mapping.items():
                if insight_key in insights:
                    setattr(ticket, model_attr, insights[insight_key])

            ticket.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create a TicketInsight record if type is specified
            insight_type = insights.get("insight_type")
            if insight_type and insight_type in TicketInsight._VALID_TYPES:
                insight_record = TicketInsight(
                    ticket_id=ticket.id,
                    insight_type=insight_type,
                    insight_data=insights.get("insight_data", {}),
                    confidence=insights.get("confidence", 0.0),
                )
                db.session.add(insight_record)

            db.session.commit()
            logger.info("Updated insights for ticket %s", ticket_id)
            return True

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def create_audit_log(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        user_id: str = "system",
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Create an audit log entry.

        Parameters
        ----------
        action : str
            Descriptive action (e.g. ``"ticket.insert"``, ``"pipeline.run"``).
        entity_type : str
            Type of entity affected (e.g. ``"ticket"``, ``"config"``).
        entity_id : str | None
            ID of the affected entity.
        user_id : str
            Who performed the action.
        details : dict | None
            Additional structured metadata.

        Returns
        -------
        int
            Primary key of the created audit log entry.
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            entry = AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=user_id,
                details=details or {},
            )
            db.session.add(entry)
            db.session.commit()
            return entry.id

    # ------------------------------------------------------------------
    # Dashboard config
    # ------------------------------------------------------------------

    def save_dashboard_config(
        self,
        name: str,
        config: Dict[str, Any],
        is_default: bool = False,
    ) -> int:
        """Persist a dashboard configuration.

        Parameters
        ----------
        name : str
            Unique dashboard name.
        config : dict
            Dashboard layout and widget configuration.
        is_default : bool
            Mark as the default dashboard.

        Returns
        -------
        int
            Primary key of the upserted config.
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            existing = DashboardConfig.query.filter_by(name=name).first()
            if existing:
                existing.config = config
                existing.is_default = is_default
                existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.session.commit()
                return existing.id

            if is_default:
                DashboardConfig.query.filter_by(is_default=True).update({"is_default": False})

            new_config = DashboardConfig(
                name=name,
                config=config,
                is_default=is_default,
            )
            db.session.add(new_config)
            db.session.commit()
            return new_config.id

    # ------------------------------------------------------------------
    # Statistics / Analytics
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """Compute aggregate statistics across all tickets.

        Returns
        -------
        dict
            A dictionary containing:
            - ``total_tickets`` (int)
            - ``by_status`` (dict[str, int])
            - ``by_priority`` (dict[str, int])
            - ``by_category`` (dict[str, int])
            - ``by_assignment_group`` (dict[str, int])
            - ``by_source_system`` (dict[str, int])
            - ``avg_sentiment_score`` (float)
            - ``sentiment_distribution`` (dict[str, int])
            - ``tickets_with_insights`` (int)
            - ``anomaly_count`` (int)
            - ``duplicate_count`` (int)
            - ``resolved_today`` (int)
            - ``opened_today`` (int)
            - ``avg_resolution_time_hours`` (float | None)
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            import math

            total = Ticket.query.count()

            # Count by status
            status_counts = (
                db.session.query(Ticket.status, db.func.count(Ticket.id))
                .group_by(Ticket.status)
                .all()
            )
            by_status = {status: count for status, count in status_counts}

            # Count by priority
            priority_counts = (
                db.session.query(Ticket.priority, db.func.count(Ticket.id))
                .group_by(Ticket.priority)
                .all()
            )
            by_priority = {priority: count for priority, count in priority_counts}

            # Count by category
            category_counts = (
                db.session.query(Ticket.category, db.func.count(Ticket.id))
                .group_by(Ticket.category)
                .all()
            )
            by_category = {cat: count for cat, count in category_counts if cat}

            # Count by assignment group
            group_counts = (
                db.session.query(Ticket.assignment_group, db.func.count(Ticket.id))
                .group_by(Ticket.assignment_group)
                .all()
            )
            by_assignment_group = {grp: count for grp, count in group_counts if grp}

            # Count by source system
            source_counts = (
                db.session.query(Ticket.source_system, db.func.count(Ticket.id))
                .group_by(Ticket.source_system)
                .all()
            )
            by_source_system = {src: count for src, count in source_counts}

            # Sentiment stats
            avg_sentiment = db.session.query(
                db.func.avg(Ticket.sentiment_score)
            ).scalar() or 0.0

            sentiment_counts = (
                db.session.query(Ticket.sentiment_label, db.func.count(Ticket.id))
                .group_by(Ticket.sentiment_label)
                .all()
            )
            sentiment_distribution = {
                label: count for label, count in sentiment_counts
            }

            # NLP enrichment stats
            tickets_with_insights = TicketInsight.query.distinct(
                TicketInsight.ticket_id
            ).count()
            anomaly_count = Ticket.query.filter(Ticket.anomaly_score > 0.5).count()
            duplicate_count = Ticket.query.filter(
                Ticket.duplicate_of_id.isnot(None)
            ).count()

            # Time-based stats
            today = datetime.now(timezone.utc).replace(tzinfo=None).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            opened_today = Ticket.query.filter(Ticket.opened_at >= today).count()
            resolved_today = Ticket.query.filter(
                Ticket.resolved_at >= today
            ).count()

            # Average resolution time (hours)
            avg_resolution_result = db.session.query(
                db.func.avg(
                    db.func.extract(
                        "epoch",
                        Ticket.resolved_at - Ticket.opened_at,
                    ) / 3600.0
                )
            ).filter(
                Ticket.resolved_at.isnot(None),
                Ticket.opened_at.isnot(None),
            ).scalar()
            avg_resolution_hours = (
                round(float(avg_resolution_result), 2)
                if avg_resolution_result is not None
                else None
            )

            return {
                "total_tickets": total,
                "by_status": by_status,
                "by_priority": by_priority,
                "by_category": by_category,
                "by_assignment_group": by_assignment_group,
                "by_source_system": by_source_system,
                "avg_sentiment_score": round(float(avg_sentiment), 4),
                "sentiment_distribution": sentiment_distribution,
                "tickets_with_insights": tickets_with_insights,
                "anomaly_count": anomaly_count,
                "duplicate_count": duplicate_count,
                "resolved_today": resolved_today,
                "opened_today": opened_today,
                "avg_resolution_time_hours": avg_resolution_hours,
            }

    def get_recent_tickets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recently opened tickets.

        Parameters
        ----------
        limit : int
            Maximum tickets to return.

        Returns
        -------
        list[dict]
        """
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            tickets = (
                Ticket.query
                .order_by(db.desc(Ticket.opened_at))
                .limit(limit)
                .all()
            )
            return [t.to_dict() for t in tickets]

    def get_ticket_count(self) -> int:
        """Return the total number of tickets in the database."""
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            return Ticket.query.count()

    def delete_ticket(self, ticket_id: str) -> bool:
        """Delete a ticket by external ticket_id. Returns True if found and deleted."""
        if self._app is None:
            raise RuntimeError("DatabaseManager has not been initialised. Call init_app() first.")

        with self._app.app_context():
            ticket = Ticket.query.filter_by(ticket_id=ticket_id).first()
            if ticket is None:
                return False
            db.session.delete(ticket)
            db.session.commit()
            logger.info("Deleted ticket %s", ticket_id)
            return True


# Need math import for get_statistics
import math  # noqa: E402
