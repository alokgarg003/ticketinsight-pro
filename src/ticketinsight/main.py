"""
TicketInsight Pro — Flask application factory and CLI entry point.

Provides:
- :func:`create_app` — Application factory with full initialisation
- Click CLI commands for running the server, ingesting data, running
  analysis, generating reports, and managing the database.

Usage (CLI)
-----------
    python -m ticketinsight.main run --host 0.0.0.0 --port 5000
    python -m ticketinsight.main ingest --adapter csv --limit 1000
    python -m ticketinsight.main analyze --all
    python -m ticketinsight.main report --type summary --format html
    python -m ticketinsight.main db init
    python -m ticketinsight.main db seed
    python -m ticketinsight.main setup --adapter-type csv
    python -m ticketinsight.main download-models

Usage (programmatic)
---------------------
    from ticketinsight.main import create_app
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional

import click
from flask import Flask, jsonify, render_template

from ticketinsight import __version__

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so sibling packages resolve
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def create_app(config_path: Optional[str] = None) -> Flask:
    """Application factory — create and configure the Flask app.

    Steps performed:
        1. Load configuration via :class:`~ticketinsight.config.ConfigManager`.
        2. Configure Flask ``SECRET_KEY`` and other app-level settings.
        3. Initialise SQLAlchemy via :class:`~ticketinsight.storage.database.DatabaseManager`.
        4. Initialise Redis cache via :class:`~ticketinsight.storage.cache.CacheManager`.
        5. Register the API blueprint (``/api/v1``).
        6. Set up Jinja2 template and static file folders.
        7. Register global error handlers.
        8. Register custom template filters.
        9. Store managers on ``app.extensions`` for access from routes.
       10. Create the data directory if it doesn't exist.

    Parameters
    ----------
    config_path : str | None
        Optional path to a YAML configuration file.

    Returns
    -------
    Flask
        Fully configured application instance.
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent.parent.parent / "web" / "templates"),
        static_folder=str(Path(__file__).resolve().parent.parent.parent / "web" / "static"),
        static_url_path="/static",
    )

    # Record start time for uptime calculations
    app._start_time = time.time()

    # ------------------------------------------------------------------
    # 1. Load configuration
    # ------------------------------------------------------------------
    from ticketinsight.config import ConfigManager
    from ticketinsight.utils.logger import get_logger, configure_logging

    config = ConfigManager(config_path=config_path)
    app.extensions["config_manager"] = config

    log_level = config.get("logging", "level", "INFO")
    log_file = config.get("logging", "file", "logs/ticketinsight.log")
    log_format = config.get("logging", "format")
    date_format = config.get("logging", "date_format")
    console_enabled = config.get("logging", "console_enabled", True)
    file_enabled = config.get("logging", "file_enabled", True)

    configure_logging(
        level=log_level,
        log_file=log_file,
        log_format=log_format,
        date_format=date_format,
        console_enabled=console_enabled,
        file_enabled=file_enabled,
    )

    logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # 2. Flask app config
    # ------------------------------------------------------------------
    app.config["SECRET_KEY"] = config.get("app", "secret_key", "dev-secret-change-me")
    app.config["DEBUG"] = config.get("app", "debug", False)
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

    # ------------------------------------------------------------------
    # 3. Create data / log directories
    # ------------------------------------------------------------------
    for directory in ("data", "data/samples", "logs"):
        Path(directory).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 4. Initialise database
    # ------------------------------------------------------------------
    from ticketinsight.storage.database import DatabaseManager, db

    db_manager = DatabaseManager()
    db_manager.init_app(app)
    app.extensions["db_manager"] = db_manager
    app.extensions["db"] = db

    with app.app_context():
        db.create_all()
        logger.info("Database tables verified")

    # ------------------------------------------------------------------
    # 5. Initialise cache
    # ------------------------------------------------------------------
    from ticketinsight.storage.cache import CacheManager

    cache_manager = CacheManager()
    full_config = config.get_all()
    cache_manager.init_app(full_config)
    app.extensions["cache_manager"] = cache_manager

    # ------------------------------------------------------------------
    # 6. Initialise CORS
    # ------------------------------------------------------------------
    try:
        from flask_cors import CORS

        cors_origins = config.get("cors", "origins", ["*"])
        cors_methods = config.get("cors", "methods", ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        cors_headers = config.get("cors", "allow_headers", ["Content-Type", "Authorization"])
        CORS(
            app,
            origins=cors_origins,
            methods=cors_methods,
            allow_headers=cors_headers,
            supports_credentials=config.get("cors", "supports_credentials", True),
            max_age=config.get("cors", "max_age", 3600),
        )
        logger.info("CORS configured for origins: %s", cors_origins)
    except ImportError:
        logger.warning("flask-cors not installed — CORS will not be enabled")

    # ------------------------------------------------------------------
    # 7. Register API blueprint
    # ------------------------------------------------------------------
    try:
        from ticketinsight.api import create_blueprint
        api_bp = create_blueprint()
        app.register_blueprint(api_bp)
        logger.info("API blueprint registered at /api/v1")
    except Exception as exc:
        logger.error("Failed to register API blueprint: %s", exc)

    # ------------------------------------------------------------------
    # 8. Register web routes (dashboard)
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        """Render the main dashboard page."""
        try:
            return render_template("index.html", config=config.get_all())
        except Exception as exc:
            logger.error("Template rendering failed: %s", exc)
            return (
                "<h1>TicketInsight Pro</h1>"
                "<p>Dashboard template not found. "
                f"Error: {exc}</p>"
                '<p>API is available at <a href="/api/v1/health">/api/v1/health</a></p>'
            )

    # ------------------------------------------------------------------
    # 9. Register error handlers
    # ------------------------------------------------------------------

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "bad_request", "message": str(error), "status_code": 400}), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "not_found", "message": "Resource not found", "status_code": 404}), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({"error": "method_not_allowed", "message": "Method not allowed", "status_code": 405}), 405

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": "payload_too_large", "message": "Request body exceeds 16 MB limit", "status_code": 413}), 413

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "internal_error", "message": "Internal server error", "status_code": 500}), 500

    # ------------------------------------------------------------------
    # 10. Register template filters
    # ------------------------------------------------------------------

    @app.template_filter("round")
    def template_round(value, precision=1):
        """Jinja2 filter: round a number to given precision."""
        try:
            return round(float(value), precision)
        except (TypeError, ValueError):
            return value

    @app.template_filter("percentage")
    def template_percentage(value, total):
        """Jinja2 filter: compute percentage."""
        try:
            return round(float(value) / float(total) * 100, 1)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0

    @app.template_filter("time_ago")
    def template_time_ago(dt_str):
        """Jinja2 filter: human-readable time ago."""
        try:
            from ticketinsight.utils.helpers import time_ago
            from datetime import datetime

            if not dt_str:
                return "unknown"
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return time_ago(dt)
        except Exception:
            return "unknown"

    # ------------------------------------------------------------------
    # 11. Shell context for Flask shell
    # ------------------------------------------------------------------

    @app.shell_context_processor
    def shell_context():
        """Make common objects available in the Flask shell."""
        return {
            "app": app,
            "db": db,
            "db_manager": db_manager,
            "cache": cache_manager,
            "config": config,
        }

    logger.info("TicketInsight Pro v%s initialised", __version__)
    return app


# ===========================================================================
# CLI commands
# ===========================================================================

@click.group()
@click.version_option(version=__version__, prog_name="ticketinsight")
def cli():
    """TicketInsight Pro — Open Source Ticket Analytics Platform.

    Analyse, classify, and gain insights from IT service management
    ticket data using NLP-powered analytics.
    """


@cli.command()
@click.option("--host", default=None, help="Host to bind to (default from config)")
@click.option("--port", default=None, type=int, help="Port to bind to (default from config)")
@click.option("--debug", is_flag=True, default=None, help="Enable debug mode")
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def run(host, port, debug, config_path):
    """Start the TicketInsight Pro development server."""
    from ticketinsight.config import ConfigManager
    from ticketinsight.utils.logger import get_logger

    config = ConfigManager(config_path=config_path)

    if host is None:
        host = config.get("app", "host", "0.0.0.0")
    if port is None:
        port = config.get("app", "port", 5000)
    if debug is None:
        debug = config.get("app", "debug", False)

    # Ensure data directory exists
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(parents=True, exist_ok=True)

    _print_banner(config)

    app = create_app(config_path=config_path)

    with app.app_context():
        # Seed sample data if database is empty
        try:
            db_mgr = app.extensions.get("db_manager")
            if db_mgr:
                count = db_mgr.seed_sample_data()
                if count > 0:
                    click.secho(f"  Seeded {count} sample tickets", fg="green")
        except Exception as exc:
            click.secho(f"  Warning: Could not seed data: {exc}", fg="yellow")

    click.secho(f"\n  Server starting on http://{host}:{port}", fg="cyan", bold=True)
    click.secho(f"  Dashboard: http://{host}:{port}/", fg="cyan")
    click.secho(f"  API:       http://{host}:{port}/api/v1/health", fg="cyan")
    if debug:
        click.secho("  Debug mode: ON", fg="yellow")
    click.echo()

    app.run(host=host, port=port, debug=debug, use_reloader=False)


@cli.command()
@click.option("--adapter", type=click.Choice(["servicenow", "jira", "csv", "universal"]), required=True,
              help="Source adapter type")
@click.option("--limit", default=1000, type=int, help="Maximum tickets to ingest")
@click.option("--full-sync", is_flag=True, help="Perform full sync (ignore incremental)")
@click.option("--query", default=None, help="Optional query filter")
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def ingest(adapter, limit, full_sync, query, config_path):
    """Ingest tickets from a configured source adapter."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()
    logger = get_logger(__name__)

    click.secho(f"Ingesting tickets from {adapter}...", fg="cyan")

    app = create_app(config_path=config_path)

    try:
        from ticketinsight.pipeline import DataIngester
    except ImportError:
        click.secho("Error: Pipeline module not available.", fg="red")
        click.secho("Install dependencies: pip install -e '.[all]'", fg="yellow")
        sys.exit(1)

    with app.app_context():
        config = app.extensions.get("config_manager")
        ingest_config = {
            "adapter_type": adapter,
            "limit": limit,
            "full_sync": full_sync,
            "query": query,
        }
        if config:
            ingest_config["adapter_config"] = config.get_section("adapter")

        try:
            ingester = DataIngester()
            result = ingester.ingest(ingest_config)
            inserted = result.get("inserted", 0)
            errors = result.get("errors", 0)
            click.secho(f"  Ingestion complete: {inserted} tickets inserted, {errors} errors", fg="green")

            # Invalidate caches
            cache = app.extensions.get("cache_manager")
            if cache:
                cache.invalidate_pattern("*")

        except Exception as exc:
            logger.error("Ingestion failed: %s", exc)
            click.secho(f"  Ingestion failed: {exc}", fg="red")
            sys.exit(1)


@cli.command()
@click.option("--ticket-ids", default=None, help="Comma-separated ticket database IDs")
@click.option("--types", default=None, help="Comma-separated analysis types")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all unanalyzed tickets")
@click.option("--force", is_flag=True, help="Force re-analysis of existing insights")
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def analyze(ticket_ids, types, analyze_all, force, config_path):
    """Run NLP analysis on tickets."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()
    logger = get_logger(__name__)

    try:
        from ticketinsight.nlp import NLPEngine
    except ImportError:
        click.secho("Error: NLP module not available.", fg="red")
        click.secho("Install NLP dependencies: pip install spacy && python -m spacy download en_core_web_sm", fg="yellow")
        sys.exit(1)

    app = create_app(config_path=config_path)

    analysis_types = None
    if types:
        analysis_types = [t.strip() for t in types.split(",")]

    with app.app_context():
        db_mgr = app.extensions.get("db_manager")
        nlp = NLPEngine()

        config = app.extensions.get("config_manager")
        if config:
            nlp_config = config.get_section("nlp")
            nlp.configure(nlp_config)

        # Determine which tickets to analyse
        from ticketinsight.storage.database import Ticket, TicketInsight

        if ticket_ids:
            ids = [int(t.strip()) for t in ticket_ids.split(",")]
            tickets = Ticket.query.filter(Ticket.id.in_(ids)).all()
            click.secho(f"Analyzing {len(tickets)} specified ticket(s)...", fg="cyan")
        elif analyze_all or force:
            query = Ticket.query
            if not force:
                sub = TicketInsight.query.with_entities(TicketInsight.ticket_id).distinct().subquery()
                query = Ticket.query.outerjoin(sub, Ticket.id == sub.c.ticket_id).filter(sub.c.ticket_id.is_(None))
            tickets = query.limit(500).all()
            click.secho(f"Analyzing {len(tickets)} ticket(s)...", fg="cyan")
        else:
            click.secho("No tickets specified. Use --all or --ticket-ids.", fg="yellow")
            sys.exit(0)

        if not tickets:
            click.secho("No tickets found to analyze.", fg="yellow")
            return

        analyzed = 0
        errors = 0
        with click.progressbar(tickets, label="Analyzing") as bar:
            for ticket in bar:
                try:
                    text = f"{ticket.title} {ticket.description}"
                    result = nlp.analyze(text, types=analysis_types)

                    if result:
                        update_data = {
                            "insight_type": "classification",
                            "insight_data": result,
                            "confidence": result.get("confidence", 0.0),
                        }
                        if "sentiment" in result:
                            update_data["sentiment_score"] = result["sentiment"].get("score", 0.0)
                            update_data["sentiment_label"] = result["sentiment"].get("label", "Neutral")
                        if "classification" in result:
                            update_data["predicted_category"] = result["classification"].get("category", "")
                        if "topic" in result:
                            update_data["topic_cluster"] = result["topic"].get("cluster")
                        if "anomaly" in result:
                            update_data["anomaly_score"] = result["anomaly"].get("score", 0.0)
                        if "summary" in result:
                            update_data["summary"] = result["summary"].get("text", "")
                        if "ner" in result:
                            update_data["named_entities"] = result["ner"].get("entities", {})
                        if "root_cause" in result:
                            update_data["root_cause_cluster"] = result["root_cause"].get("cluster")

                        db_mgr.update_ticket_insights(str(ticket.ticket_id), update_data)
                        analyzed += 1

                except Exception as exc:
                    errors += 1
                    logger.warning("Failed to analyze ticket %s: %s", ticket.id, exc)

        click.echo()
        click.secho(f"  Analysis complete: {analyzed} analyzed, {errors} errors", fg="green")

        # Invalidate caches
        cache = app.extensions.get("cache_manager")
        if cache:
            cache.invalidate_pattern("*")


@cli.command()
@click.option("--type", "report_type", default="summary", type=click.Choice(["summary", "detailed", "executive", "performance", "nlp_analysis"]),
              help="Report type")
@click.option("--format", "output_format", default="json", type=click.Choice(["json", "csv", "html"]),
              help="Output format")
@click.option("--output", default=None, help="Output file path (default: stdout)")
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def report(report_type, output_format, output, config_path):
    """Generate an insights report."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()
    logger = get_logger(__name__)

    app = create_app(config_path=config_path)

    with app.app_context():
        db_mgr = app.extensions.get("db_manager")
        from ticketinsight.insights.generator import InsightsGenerator
        from ticketinsight.insights.reporter import ReportGenerator

        generator = InsightsGenerator(db_mgr)
        reporter = ReportGenerator(db_mgr, generator)

        click.secho(f"Generating {report_type} report in {output_format} format...", fg="cyan")

        try:
            if output_format == "json":
                result = reporter.generate_json_report(report_type)
                content = _format_json(result)
            elif output_format == "csv":
                content = reporter.generate_csv_report(report_type)
            else:
                content = reporter.generate_html_report(report_type)
        except ValueError as exc:
            click.secho(f"Error: {exc}", fg="red")
            sys.exit(1)
        except Exception as exc:
            logger.error("Report generation failed: %s", exc)
            click.secho(f"Error: Report generation failed: {exc}", fg="red")
            sys.exit(1)

        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            click.secho(f"  Report saved to {output}", fg="green")
        else:
            click.echo(content)


@cli.command()
@click.option("--adapter-type", prompt=True, type=click.Choice(["servicenow", "jira", "csv", "universal"]),
              help="Adapter type to configure")
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def setup(adapter_type, config_path):
    """Interactive setup wizard for first-time configuration."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()

    click.secho("\n  TicketInsight Pro — Setup Wizard\n", fg="cyan", bold=True)
    click.echo("  This wizard will guide you through initial configuration.\n")

    config_updates = {}

    # Adapter-specific configuration
    if adapter_type == "servicenow":
        config_updates["adapter"] = {"type": "servicenow"}
        click.secho("  ServiceNow Configuration:", fg="yellow")
        instance = click.prompt("  ServiceNow instance URL (e.g. yourcompany.service-now.com)")
        username = click.prompt("  Username")
        password = click.prompt("  Password", hide_input=True)
        config_updates["adapter"].update({
            "snow_instance": instance,
            "snow_username": username,
            "snow_password": password,
        })

    elif adapter_type == "jira":
        config_updates["adapter"] = {"type": "jira"}
        click.secho("  Jira Configuration:", fg="yellow")
        server = click.prompt("  Jira server URL (e.g. https://yourcompany.atlassian.net)")
        username = click.prompt("  Email / Username")
        token = click.prompt("  API Token", hide_input=True)
        config_updates["adapter"].update({
            "jira_server": server,
            "jira_username": username,
            "jira_api_token": token,
        })

    elif adapter_type == "csv":
        config_updates["adapter"] = {"type": "csv"}
        csv_path = click.prompt("  CSV file path", default="data/samples/tickets_sample.csv")
        config_updates["adapter"]["csv_file_path"] = csv_path

        # Check if file exists, offer to create sample
        if not Path(csv_path).exists():
            if click.confirm(f"  File '{csv_path}' not found. Create a sample?", default=True):
                _create_sample_csv(csv_path)

    elif adapter_type == "universal":
        config_updates["adapter"] = {"type": "universal"}

    # Create config file
    from ticketinsight.config import ConfigManager

    config = ConfigManager(config_path=config_path)
    for section, values in config_updates.items():
        for key, value in values.items():
            config.set(section, key, value)

    # Determine where to save
    config_file = config_path or "config.yaml"
    if not Path(config_file).exists():
        if click.confirm(f"  Save configuration to {config_file}?", default=True):
            _save_config_yaml(config_file, config)
            click.secho(f"  Configuration saved to {config_file}", fg="green")

    # Initialise database
    if click.confirm("  Initialise the database now?", default=True):
        app = create_app(config_path=config_path)
        with app.app_context():
            db_mgr = app.extensions.get("db_manager")
            if db_mgr:
                db_mgr.create_all()
                count = db_mgr.seed_sample_data()
                click.secho(f"  Database initialised with {count} sample tickets", fg="green")

    click.secho("\n  Setup complete!", fg="green", bold=True)
    click.secho("  Run 'ticketinsight run' to start the server.\n", fg="cyan")


@cli.command("download-models")
def download_models():
    """Download required NLP models (spaCy, NLTK data)."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()
    logger = get_logger(__name__)

    click.secho("  Downloading NLP models...\n", fg="cyan")

    # spaCy model
    try:
        import spacy
        click.echo("  [1/2] Downloading spaCy model (en_core_web_sm)...")
        spacy.cli.download("en_core_web_sm")
        click.secho("  spaCy model downloaded successfully", fg="green")
    except ImportError:
        click.secho("  spaCy not installed. Run: pip install spacy", fg="red")
        sys.exit(1)
    except Exception as exc:
        click.secho(f"  Failed to download spaCy model: {exc}", fg="red")
        sys.exit(1)

    # NLTK data
    try:
        import nltk
        click.echo("  [2/2] Downloading NLTK data...")
        for package in ["vader_lexicon", "punkt", "stopwords", "wordnet"]:
            try:
                nltk.download(package, quiet=True)
            except Exception:
                pass
        click.secho("  NLTK data downloaded successfully", fg="green")
    except ImportError:
        click.secho("  NLTK not installed. Run: pip install nltk", fg="yellow")
    except Exception as exc:
        click.secho(f"  Failed to download NLTK data: {exc}", fg="yellow")

    click.secho("\n  All models downloaded!", fg="green", bold=True)


# ===========================================================================
# Database management commands
# ===========================================================================


@cli.group()
def db():
    """Database management commands."""


@db.command()
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def init(config_path):
    """Initialise database tables."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()

    click.secho("  Initialising database...", fg="cyan")

    app = create_app(config_path=config_path)

    with app.app_context():
        db_mgr = app.extensions.get("db_manager")
        if db_mgr:
            db_mgr.create_all()
            click.secho("  Database tables created successfully", fg="green")
        else:
            click.secho("  Error: Database manager not initialised", fg="red")
            sys.exit(1)


@db.command()
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def seed(config_path):
    """Seed database with sample ticket data."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()

    click.secho("  Seeding database with sample data...", fg="cyan")

    app = create_app(config_path=config_path)

    with app.app_context():
        db_mgr = app.extensions.get("db_manager")
        if db_mgr:
            count = db_mgr.seed_sample_data()
            if count > 0:
                click.secho(f"  Seeded {count} sample tickets", fg="green")
            else:
                click.secho("  Database already contains data — skipping seed", fg="yellow")
        else:
            click.secho("  Error: Database manager not initialised", fg="red")
            sys.exit(1)


@db.command("drop")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def drop_tables(yes, config_path):
    """Drop ALL database tables. Use with extreme caution!"""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()

    if not yes:
        if not click.confirm("  Are you sure you want to drop ALL tables?", default=False):
            click.echo("  Cancelled.")
            return

    app = create_app(config_path=config_path)

    with app.app_context():
        db_mgr = app.extensions.get("db_manager")
        if db_mgr:
            db_mgr.drop_all()
            click.secho("  All database tables have been dropped", fg="red")
        else:
            click.secho("  Error: Database manager not initialised", fg="red")
            sys.exit(1)


@db.command("reset")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--config", "config_path", default=None, help="Path to YAML config file")
def reset_db(yes, config_path):
    """Drop and recreate all tables, then seed with sample data."""
    from ticketinsight.utils.logger import get_logger, configure_logging

    configure_logging()

    if not yes:
        if not click.confirm("  This will DROP all data and reseed. Continue?", default=False):
            click.echo("  Cancelled.")
            return

    app = create_app(config_path=config_path)

    with app.app_context():
        db_mgr = app.extensions.get("db_manager")
        if db_mgr:
            db_mgr.drop_all()
            click.secho("  Tables dropped", fg="red")
            db_mgr.create_all()
            click.secho("  Tables recreated", fg="green")
            count = db_mgr.seed_sample_data()
            click.secho(f"  Seeded {count} sample tickets", fg="green")
        else:
            click.secho("  Error: Database manager not initialised", fg="red")
            sys.exit(1)


# ===========================================================================
# Helper functions
# ===========================================================================


def _print_banner(config):
    """Print the welcome banner on startup."""
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║        █████╗  ██████╗ ███╗   ██╗████████╗███████╗██████╗     ║
║       ██╔══██╗██╔═══██╗████╗  ██║╚══██╔══╝██╔════╝██╔══██╗    ║
║       ███████║██║   ██║██╔██╗ ██║   ██║   █████╗  ██║  ██║    ║
║       ██╔══██║██║   ██║██║╚██╗██║   ██║   ██╔══╝  ██║  ██║    ║
║       ██║  ██║╚██████╔╝██║ ╚████║   ██║   ███████╗██████╔╝    ║
║       ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═════╝     ║
║                                                              ║
║        Open Source Ticket Analytics Platform                  ║
║        Version {__version__:>43s}║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    click.secho(banner, fg="blue")

    env = config.get("app", "env", "development")
    db_url = config.get("database", "url", "sqlite:///data/ticketinsight.db")
    adapter = config.get("adapter", "type", "csv")

    click.echo(f"  Environment:  {env}")
    click.echo(f"  Database:     {db_url}")
    click.echo(f"  Adapter:      {adapter}")
    click.echo()


def _format_json(data: dict, indent: int = 2) -> str:
    """Format a dict as a JSON string."""
    import json
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def _create_sample_csv(path: str):
    """Create a sample CSV file with sample ticket data."""
    csv_content = """ticket_id,title,description,priority,status,category,assignment_group,assignee,opened_at,resolved_at,source_system
INC0001,Cannot access email,User cannot access email after password reset,High,Open,Email,IT Support,john.doe,2024-01-15 09:00:00,,csv
INC0002,VPN connection issues,VPN drops every 20 minutes,High,In Progress,Network,Network Ops,jane.smith,2024-01-15 10:30:00,,csv
INC0003,Printer jamming,Printer on 3rd floor keeps jamming,Medium,Resolved,Hardware,IT Support,bob.wilson,2024-01-14 14:00:00,2024-01-15 08:00:00,csv
INC0004,Software install error,Cannot install Python packages due to proxy,Medium,Open,Software,DevOps,devops.team,2024-01-15 11:00:00,,csv
INC0005,New account setup,Onboarding for new hire Sarah Chen,Medium,In Progress,Access Management,IT Operations,admin.team,2024-01-15 07:00:00,,csv
"""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(csv_content)
    click.secho(f"  Sample CSV created at {path}", fg="green")


def _save_config_yaml(path: str, config):
    """Save current configuration to a YAML file."""
    import yaml

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = config.get_all()

    # Redact sensitive values
    sensitive_keys = {"password", "secret", "token", "api_key", "secret_key"}
    for section in data.values():
        if isinstance(section, dict):
            for key in section:
                if any(sk in key.lower() for sk in sensitive_keys):
                    section[key] = "********"

    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
