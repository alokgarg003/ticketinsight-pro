"""
Pipeline scheduler for TicketInsight Pro.

Schedules periodic data ingestion, processing, and NLP analysis using a
background thread.  Supports graceful shutdown, on-demand runs, and
comprehensive status reporting.

Uses the ``schedule`` library for job scheduling and ``threading`` for
background execution.

Configuration keys
------------------
``pipeline.interval_minutes`` (int) — Default interval for all scheduled
    jobs (default 30).

Usage
-----
    from ticketinsight.pipeline.scheduler import PipelineScheduler

    scheduler = PipelineScheduler(config, ingester, processor)
    scheduler.schedule_ingestion(interval_minutes=30)
    scheduler.schedule_processing(interval_minutes=60)
    scheduler.start()
    # ... application runs ...
    scheduler.stop()
"""

import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from ticketinsight.utils.logger import get_logger

__all__ = ["PipelineScheduler"]


class PipelineScheduler:
    """Schedules periodic data ingestion and processing.

    Runs each job in its own background thread with error isolation — a
    failure in one job does not prevent other jobs from executing.

    Parameters
    ----------
    config : ConfigManager
        Application configuration manager.
    ingester : DataIngester
        Data ingester instance for ingestion jobs.
    processor : DataProcessor
        Data processor instance for processing jobs.
    nlp_engine : Any | None
        Optional NLP engine for analysis jobs.

    Attributes
    ----------
    running : bool
        Whether the scheduler is currently active.
    """

    def __init__(self, config: Any, ingester: Any, processor: Any, nlp_engine: Any = None) -> None:
        self.config = config
        self.ingester = ingester
        self.processor = processor
        self.nlp_engine = nlp_engine
        self.logger = get_logger(__name__)

        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()
        self._lock: threading.Lock = threading.Lock()

        # Default interval from config
        self._default_interval: int = 30
        if hasattr(config, "get"):
            self._default_interval = int(
                config.get("pipeline", "interval_minutes", 30)
            )

        # Scheduled jobs: list of {"name": str, "interval_minutes": int, "job": Callable}
        self._jobs: List[Dict[str, Any]] = []

        # Run history
        self._last_runs: Dict[str, Dict[str, Any]] = {}
        self._next_runs: Dict[str, Optional[datetime]] = {}

        # Cumulative statistics
        self._stats: Dict[str, Any] = {
            "total_ingestion_runs": 0,
            "total_processing_runs": 0,
            "total_nlp_runs": 0,
            "total_errors": 0,
            "started_at": None,
            "uptime_seconds": 0,
        }

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler in a background daemon thread.

        The scheduler loop checks for pending jobs every 60 seconds and
        executes them when their interval has elapsed.  The thread is
        marked as daemon so it does not prevent the main process from
        exiting.
        """
        with self._lock:
            if self._running:
                self.logger.warning("Scheduler is already running")
                return

            self._running = True
            self._stop_event.clear()
            self._stats["started_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

            self._thread = threading.Thread(
                target=self._scheduler_loop,
                name="PipelineScheduler",
                daemon=True,
            )
            self._thread.start()
            self.logger.info("Pipeline scheduler started (default interval: %d min)", self._default_interval)

    def stop(self, timeout: float = 30.0) -> None:
        """Stop the scheduler gracefully.

        Signals the background thread to stop and waits up to *timeout*
        seconds for it to finish the current job.

        Parameters
        ----------
        timeout : float
            Maximum seconds to wait for the thread to exit (default 30).
        """
        with self._lock:
            if not self._running:
                self.logger.warning("Scheduler is not running")
                return

            self.logger.info("Stopping pipeline scheduler ...")
            self._stop_event.set()
            self._running = False

            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=timeout)
                if self._thread.is_alive():
                    self.logger.warning("Scheduler thread did not stop within %.1fs", timeout)
                else:
                    self.logger.info("Pipeline scheduler stopped")

            # Record final uptime
            if self._stats.get("started_at"):
                uptime = (
                    datetime.now(timezone.utc).replace(tzinfo=None)
                    - self._stats["started_at"]
                ).total_seconds()
                self._stats["uptime_seconds"] = round(uptime, 1)

    def restart(self) -> None:
        """Stop and immediately restart the scheduler."""
        self.stop(timeout=10.0)
        _time.sleep(0.5)
        self.start()

    # ------------------------------------------------------------------
    # Job scheduling
    # ------------------------------------------------------------------

    def schedule_ingestion(self, interval_minutes: Optional[int] = None) -> None:
        """Schedule periodic data ingestion.

        Parameters
        ----------
        interval_minutes : int | None
            Interval between runs in minutes.  Defaults to the configured
            ``pipeline.interval_minutes``.
        """
        interval = interval_minutes or self._default_interval
        self._add_job("ingestion", interval, self._run_ingestion)
        self.logger.info("Scheduled ingestion every %d minutes", interval)

    def schedule_processing(self, interval_minutes: Optional[int] = None) -> None:
        """Schedule periodic data processing.

        Parameters
        ----------
        interval_minutes : int | None
            Interval between runs in minutes.
        """
        interval = interval_minutes or self._default_interval
        self._add_job("processing", interval, self._run_processing)
        self.logger.info("Scheduled processing every %d minutes", interval)

    def schedule_nlp_analysis(self, interval_minutes: Optional[int] = None) -> None:
        """Schedule periodic NLP analysis.

        Parameters
        ----------
        interval_minutes : int | None
            Interval between runs in minutes.
        """
        interval = interval_minutes or self._default_interval
        self._add_job("nlp_analysis", interval, self._run_nlp_analysis)
        self.logger.info("Scheduled NLP analysis every %d minutes", interval)

    # ------------------------------------------------------------------
    # On-demand execution
    # ------------------------------------------------------------------

    def run_once(self, pipeline_type: str = "full") -> Dict[str, Any]:
        """Run a pipeline once immediately.

        Parameters
        ----------
        pipeline_type : str
            One of ``"ingestion"``, ``"processing"``, ``"nlp"``, or ``"full"``.
            ``"full"`` runs all three in sequence.

        Returns
        -------
        dict
            Combined results from all executed pipelines.
        """
        self.logger.info("Running on-demand pipeline: %s", pipeline_type)
        results: Dict[str, Any] = {}

        if pipeline_type in ("ingestion", "full"):
            results["ingestion"] = self._run_ingestion()

        if pipeline_type in ("processing", "full"):
            results["processing"] = self._run_processing()

        if pipeline_type in ("nlp", "nlp_analysis", "full"):
            results["nlp_analysis"] = self._run_nlp_analysis()

        return results

    # ------------------------------------------------------------------
    # Status reporting
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return the current scheduler status.

        Returns
        -------
        dict
            ``{
                "running": bool,
                "thread_alive": bool,
                "jobs": list[dict],
                "next_runs": dict,
                "last_runs": dict,
                "stats": dict,
            }``
        """
        # Update uptime if running
        if self._running and self._stats.get("started_at"):
            uptime = (
                datetime.now(timezone.utc).replace(tzinfo=None)
                - self._stats["started_at"]
            ).total_seconds()
            self._stats["uptime_seconds"] = round(uptime, 1)

        jobs_info = []
        for job in self._jobs:
            jobs_info.append({
                "name": job["name"],
                "interval_minutes": job["interval_minutes"],
                "enabled": job.get("enabled", True),
                "next_run": self._next_runs.get(job["name"]),
                "last_run": self._last_runs.get(job["name"]),
            })

        return {
            "running": self._running,
            "thread_alive": self._thread.is_alive() if self._thread else False,
            "jobs": jobs_info,
            "next_runs": dict(self._next_runs),
            "last_runs": dict(self._last_runs),
            "stats": dict(self._stats),
        }

    # ------------------------------------------------------------------
    # Internal — scheduler loop
    # ------------------------------------------------------------------

    def _scheduler_loop(self) -> None:
        """Main scheduler loop executed in the background thread.

        Checks each job every 60 seconds to see if its interval has
        elapsed since the last run.  Runs the job if due.
        """
        self.logger.debug("Scheduler loop started")

        # Initialize next run times
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for job in self._jobs:
            self._next_runs[job["name"]] = now + timedelta(minutes=job["interval_minutes"])

        while not self._stop_event.is_set():
            try:
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                for job in self._jobs:
                    if not job.get("enabled", True):
                        continue

                    if self._stop_event.is_set():
                        break

                    next_run = self._next_runs.get(job["name"])
                    if next_run is None or now >= next_run:
                        # Run the job
                        job_fn = job["job"]
                        job_name = job["name"]

                        try:
                            self.logger.info("Executing scheduled job: %s", job_name)
                            result = job_fn()
                            self._last_runs[job_name] = {
                                "result": result,
                                "timestamp": now,
                                "status": "success",
                            }

                            # Update cumulative stats
                            if job_name == "ingestion":
                                self._stats["total_ingestion_runs"] += 1
                            elif job_name == "processing":
                                self._stats["total_processing_runs"] += 1
                            elif job_name == "nlp_analysis":
                                self._stats["total_nlp_runs"] += 1

                        except Exception as exc:
                            self.logger.error(
                                "Scheduled job '%s' failed: %s",
                                job_name,
                                exc,
                                exc_info=True,
                            )
                            self._last_runs[job_name] = {
                                "result": None,
                                "timestamp": now,
                                "status": "error",
                                "error": str(exc),
                            }
                            self._stats["total_errors"] += 1

                        # Schedule next run
                        self._next_runs[job_name] = now + timedelta(
                            minutes=job["interval_minutes"]
                        )

            except Exception as exc:
                self.logger.error("Scheduler loop error: %s", exc, exc_info=True)
                self._stats["total_errors"] += 1

            # Sleep in small increments to respond to stop events promptly
            self._stop_event.wait(timeout=60.0)

        self.logger.debug("Scheduler loop exited")

    # ------------------------------------------------------------------
    # Internal — job implementations
    # ------------------------------------------------------------------

    def _run_ingestion(self) -> Dict[str, Any]:
        """Execute the ingestion pipeline.

        Returns
        -------
        dict
            Ingestion statistics from :meth:`DataIngester.ingest`.
        """
        self.logger.info("Running scheduled ingestion")
        start = _time.monotonic()

        try:
            result = self.ingester.ingest()
            result["trigger"] = "scheduled"
            result["duration_seconds"] = round(_time.monotonic() - start, 3)
            return result
        except Exception as exc:
            self.logger.error("Scheduled ingestion failed: %s", exc, exc_info=True)
            return {
                "trigger": "scheduled",
                "status": "error",
                "error": str(exc),
                "duration_seconds": round(_time.monotonic() - start, 3),
            }

    def _run_processing(self) -> Dict[str, Any]:
        """Execute the data processing pipeline.

        Returns
        -------
        dict
            Processing statistics from :meth:`DataProcessor.process_tickets`.
        """
        self.logger.info("Running scheduled processing")
        start = _time.monotonic()

        try:
            result = self.processor.process_tickets()
            result["trigger"] = "scheduled"
            result["duration_seconds"] = round(_time.monotonic() - start, 3)
            return result
        except Exception as exc:
            self.logger.error("Scheduled processing failed: %s", exc, exc_info=True)
            return {
                "trigger": "scheduled",
                "status": "error",
                "error": str(exc),
                "duration_seconds": round(_time.monotonic() - start, 3),
            }

    def _run_nlp_analysis(self) -> Dict[str, Any]:
        """Execute the NLP analysis pipeline (if an NLP engine is available).

        Returns
        -------
        dict
            NLP analysis results, or a status dict if no engine is configured.
        """
        self.logger.info("Running scheduled NLP analysis")
        start = _time.monotonic()

        if self.nlp_engine is None:
            msg = "No NLP engine configured — skipping NLP analysis"
            self.logger.warning(msg)
            return {
                "trigger": "scheduled",
                "status": "skipped",
                "message": msg,
                "duration_seconds": round(_time.monotonic() - start, 3),
            }

        try:
            # The NLP engine is expected to have an `analyze_all` or `run` method.
            # We support multiple common interfaces.
            if hasattr(self.nlp_engine, "run_pipeline"):
                result = self.nlp_engine.run_pipeline()
            elif hasattr(self.nlp_engine, "analyze_all"):
                result = self.nlp_engine.analyze_all()
            elif callable(self.nlp_engine):
                result = self.nlp_engine()
            else:
                result = {
                    "status": "error",
                    "message": "NLP engine has no callable interface "
                              "(expected run_pipeline, analyze_all, or __call__)",
                }

            if isinstance(result, dict):
                result["trigger"] = "scheduled"
            else:
                result = {"trigger": "scheduled", "result": result}

            result["duration_seconds"] = round(_time.monotonic() - start, 3)
            return result

        except Exception as exc:
            self.logger.error("Scheduled NLP analysis failed: %s", exc, exc_info=True)
            return {
                "trigger": "scheduled",
                "status": "error",
                "error": str(exc),
                "duration_seconds": round(_time.monotonic() - start, 3),
            }

    # ------------------------------------------------------------------
    # Internal — job management
    # ------------------------------------------------------------------

    def _add_job(self, name: str, interval_minutes: int, job_fn: Callable) -> None:
        """Add or update a scheduled job.

        If a job with the same name already exists, its interval and
        function are updated.

        Parameters
        ----------
        name : str
            Unique job name (e.g. ``"ingestion"``).
        interval_minutes : int
            Execution interval in minutes.
        job_fn : callable
            Function to execute.  Must accept no arguments and return a
            dict result.
        """
        with self._lock:
            # Check for existing job with the same name
            for job in self._jobs:
                if job["name"] == name:
                    job["interval_minutes"] = interval_minutes
                    job["job"] = job_fn
                    job["enabled"] = True
                    # Reset next run time
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    self._next_runs[name] = now + timedelta(minutes=interval_minutes)
                    return

            # New job
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            self._jobs.append({
                "name": name,
                "interval_minutes": interval_minutes,
                "job": job_fn,
                "enabled": True,
            })
            self._next_runs[name] = now + timedelta(minutes=interval_minutes)

    def remove_job(self, name: str) -> bool:
        """Remove a scheduled job by name.

        Parameters
        ----------
        name : str
            Job name to remove.

        Returns
        -------
        bool
            ``True`` if the job was found and removed.
        """
        with self._lock:
            for i, job in enumerate(self._jobs):
                if job["name"] == name:
                    self._jobs.pop(i)
                    self._next_runs.pop(name, None)
                    self._last_runs.pop(name, None)
                    self.logger.info("Removed scheduled job: %s", name)
                    return True
        return False

    def enable_job(self, name: str, enabled: bool = True) -> bool:
        """Enable or disable a scheduled job.

        Parameters
        ----------
        name : str
            Job name.
        enabled : bool
            ``True`` to enable, ``False`` to disable.

        Returns
        -------
        bool
            ``True`` if the job was found and updated.
        """
        with self._lock:
            for job in self._jobs:
                if job["name"] == name:
                    job["enabled"] = enabled
                    self.logger.info("Job '%s' %s", name, "enabled" if enabled else "disabled")
                    return True
        return False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """Return whether the scheduler is currently running."""
        return self._running

    @property
    def job_count(self) -> int:
        """Return the number of registered jobs."""
        return len(self._jobs)

    def __repr__(self) -> str:
        return (
            f"<PipelineScheduler running={self._running} "
            f"jobs={len(self._jobs)}>"
        )
