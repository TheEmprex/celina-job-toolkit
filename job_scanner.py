"""
Automatic job scanner for Celina's Job Application Toolkit.

Periodically searches for new job postings matching Celina's profile,
tracks already-seen jobs, and sends push notifications via ntfy.sh.
Exposes a Flask Blueprint with control and status endpoints.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from flask import Blueprint, jsonify, request as flask_request

from finder import web_search
from profile import load_profile

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("job_scanner")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SEEN_JOBS_PATH = Path.home() / ".celina_seen_jobs.json"
CONFIG_PATH = Path.home() / ".celina_scanner_config.json"

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "ntfy_topic": "celina-jobs",
    "interval_minutes": 60,
    "enabled": False,
    "max_results_per_role": 5,
}

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    """Load scanner configuration from disk, filling in defaults."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read config file: %s", exc)
    return dict(DEFAULT_CONFIG)


def _save_config(cfg: dict) -> None:
    """Persist scanner configuration to disk."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Seen-jobs store
# ---------------------------------------------------------------------------


def _load_seen_jobs() -> dict:
    """Load the mapping of URL -> metadata for previously seen jobs."""
    if SEEN_JOBS_PATH.exists():
        try:
            with open(SEEN_JOBS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read seen-jobs file: %s", exc)
    return {}


def _save_seen_jobs(data: dict) -> None:
    """Persist the seen-jobs mapping."""
    with open(SEEN_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


def send_notification(
    title: str,
    message: str,
    url: str = "",
    priority: str = "default",
    topic: Optional[str] = None,
) -> bool:
    """
    Send a push notification via ntfy.sh.

    Returns True on success, False on failure.
    """
    if topic is None:
        topic = _load_config().get("ntfy_topic", "celina-jobs")

    ntfy_url = f"https://ntfy.sh/{topic}"
    # Sanitize title for HTTP headers (ASCII only)
    safe_title = title.encode("ascii", errors="replace").decode("ascii")[:80]
    headers = {
        "Title": safe_title,
        "Priority": priority,
    }
    if url:
        headers["Click"] = url
        headers["Actions"] = f"view, Open Job, {url}"

    try:
        resp = requests.post(ntfy_url, data=message.encode("utf-8"), headers=headers, timeout=10)
        resp.raise_for_status()
        logger.info("Notification sent: %s", title)
        return True
    except Exception as exc:
        logger.error("Failed to send notification: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------


def _build_queries(profile: dict, max_results_per_role: int) -> list[tuple[str, int]]:
    """
    Build a list of (query_string, max_results) tuples based on the profile.
    """
    target_roles = profile.get("target_roles") or []
    skills = profile.get("skills") or []
    location = (profile.get("location") or "").strip()

    queries: list[tuple[str, int]] = []

    if target_roles:
        for role in target_roles:
            role = role.strip()
            if not role:
                continue
            # Simple hiring search
            queries.append((f'"{role}" hiring', max_results_per_role))
            # With location
            if location:
                queries.append((f'"{role}" job {location}', max_results_per_role))
            # Foundation / nonprofit focus
            queries.append((f'"{role}" foundation OR nonprofit OR NGO job', max_results_per_role))
    elif skills:
        skill_str = " ".join(skills[:3])
        queries.append((f'{skill_str} job opening hiring', max_results_per_role))
        if location:
            queries.append((f'{skill_str} job {location}', max_results_per_role))

    return queries


def run_scan() -> list[dict]:
    """
    Execute a single scan cycle.

    Returns a list of *new* job dicts (unseen before this scan).
    Each dict: {title, url, snippet, role_query, first_seen, notified}
    """
    config = _load_config()
    profile = load_profile()
    max_per_role = config.get("max_results_per_role", 5)
    topic = config.get("ntfy_topic", "celina-jobs")

    queries = _build_queries(profile, max_per_role)
    if not queries:
        logger.warning("No search queries could be built — check target_roles or skills in profile.")
        return []

    seen_jobs = _load_seen_jobs()
    new_jobs: list[dict] = []

    for query, max_results in queries:
        try:
            logger.info("Searching: %s (max %d)", query, max_results)
            results = web_search(query, max_results=max_results)
        except Exception as exc:
            logger.error("Search failed for query '%s': %s", query, exc)
            continue

        for result in results:
            job_url = result.get("url", "").strip()
            if not job_url:
                continue

            # Skip already-seen URLs
            if job_url in seen_jobs:
                continue

            job_title = result.get("title", "").strip() or "Untitled"
            snippet = result.get("snippet", "").strip()

            # Try to extract a company name from the title/snippet heuristically
            company = _guess_company(job_title, snippet)

            now_iso = datetime.now(timezone.utc).isoformat()

            job_record = {
                "title": job_title,
                "url": job_url,
                "snippet": snippet,
                "company": company,
                "role_query": query,
                "first_seen": now_iso,
                "notified": False,
            }

            # Mark as seen immediately so duplicates within the same scan
            # are not double-counted.
            seen_jobs[job_url] = job_record

            # Send notification
            notif_title = f"New job: {job_title}"
            notif_body = f"Company: {company}\n{snippet[:200]}" if company else snippet[:280]
            success = send_notification(
                title=notif_title,
                message=notif_body,
                url=job_url,
                priority="high",
                topic=topic,
            )
            job_record["notified"] = success

            new_jobs.append(job_record)
            logger.info("New job found: %s (%s)", job_title, job_url)

        # Small polite delay between queries
        time.sleep(1.0)

    # Persist seen jobs
    _save_seen_jobs(seen_jobs)

    logger.info("Scan complete. %d new job(s) found.", len(new_jobs))
    return new_jobs


def _guess_company(title: str, snippet: str) -> str:
    """
    Very simple heuristic to pull a company name from a job listing title.
    Common patterns:
      "Software Engineer at Acme Corp"
      "Software Engineer - Acme Corp"
      "Acme Corp | Software Engineer"
    Returns empty string if nothing obvious found.
    """
    import re

    # Pattern: "... at Company"
    m = re.search(r"\bat\s+(.+)$", title, re.IGNORECASE)
    if m:
        return m.group(1).strip(" -|")

    # Pattern: "Title - Company" or "Title | Company"
    parts = re.split(r"\s*[\-\u2013\u2014|]\s*", title)
    if len(parts) >= 2:
        # Usually the company is the last segment
        candidate = parts[-1].strip()
        # If it looks like a site name, skip
        if "." not in candidate and len(candidate) > 1:
            return candidate

    return ""


# ---------------------------------------------------------------------------
# Scanner scheduler (background thread)
# ---------------------------------------------------------------------------


class _ScannerState:
    """Mutable singleton holding scanner runtime state."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.timer: Optional[threading.Timer] = None
        self.last_scan: Optional[str] = None        # ISO timestamp
        self.next_scan: Optional[str] = None         # ISO timestamp
        self.jobs_found_today: int = 0
        self.today_date: Optional[str] = None        # YYYY-MM-DD
        self.recent_results: list[dict] = []         # last N scan results

    # -- helpers --

    def _reset_daily_counter(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.today_date != today:
            self.today_date = today
            self.jobs_found_today = 0

    def _schedule_next(self, interval_seconds: float):
        """Schedule the next scan after *interval_seconds*."""
        self.timer = threading.Timer(interval_seconds, self._tick)
        self.timer.daemon = True
        self.timer.start()
        self.next_scan = datetime.fromtimestamp(
            time.time() + interval_seconds, tz=timezone.utc
        ).isoformat()

    def _tick(self):
        """Called by the timer — runs a scan then reschedules."""
        with self.lock:
            if not self.running:
                return

        self._do_scan()

        with self.lock:
            if not self.running:
                return
            config = _load_config()
            interval = max(config.get("interval_minutes", 60), 1) * 60
            self._schedule_next(interval)

    def _do_scan(self):
        """Run a scan and update internal bookkeeping."""
        try:
            new_jobs = run_scan()
        except Exception as exc:
            logger.error("Scan cycle failed: %s", exc)
            new_jobs = []

        with self.lock:
            self.last_scan = datetime.now(timezone.utc).isoformat()
            self._reset_daily_counter()
            self.jobs_found_today += len(new_jobs)
            # Keep the most recent 200 results
            self.recent_results = (new_jobs + self.recent_results)[:200]

    # -- public API --

    def start(self, interval_minutes: Optional[int] = None):
        with self.lock:
            if self.running:
                return
            self.running = True

            config = _load_config()
            if interval_minutes is not None:
                config["interval_minutes"] = interval_minutes
                _save_config(config)

            config["enabled"] = True
            _save_config(config)

            interval = max(config.get("interval_minutes", 60), 1) * 60

            logger.info("Scanner started. Interval: %d min", interval // 60)

            # Run the first scan immediately in a background thread
            t = threading.Thread(target=self._first_run, args=(interval,), daemon=True)
            t.start()

    def _first_run(self, interval_seconds: float):
        self._do_scan()
        with self.lock:
            if not self.running:
                return
            self._schedule_next(interval_seconds)

    def stop(self):
        with self.lock:
            self.running = False
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            self.next_scan = None

            config = _load_config()
            config["enabled"] = False
            _save_config(config)

            logger.info("Scanner stopped.")

    def scan_now(self):
        """Trigger an immediate scan (non-blocking). Does NOT affect the schedule."""
        t = threading.Thread(target=self._do_scan, daemon=True)
        t.start()

    def status(self) -> dict:
        with self.lock:
            config = _load_config()
            self._reset_daily_counter()
            return {
                "running": self.running,
                "interval_minutes": config.get("interval_minutes", 60),
                "last_scan": self.last_scan,
                "jobs_found_today": self.jobs_found_today,
                "today_count": self.jobs_found_today,  # alias for backwards compat
                "next_scan": self.next_scan,
            }

    def get_recent_results(self) -> list[dict]:
        with self.lock:
            return list(self.recent_results)


# Module-level singleton
_scanner = _ScannerState()

# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

scanner_bp = Blueprint("scanner", __name__)


@scanner_bp.route("/api/scanner/status", methods=["GET"])
def scanner_status():
    """Return current scanner status."""
    return jsonify(_scanner.status())


@scanner_bp.route("/api/scanner/start", methods=["POST"])
def scanner_start():
    """Start the background scanner. Optional JSON body: {interval_minutes: N}."""
    body = flask_request.get_json(silent=True) or {}
    interval = body.get("interval_minutes")
    if interval is not None:
        try:
            interval = int(interval)
        except (ValueError, TypeError):
            return jsonify({"error": "interval_minutes must be an integer"}), 400
        if interval < 1:
            return jsonify({"error": "interval_minutes must be >= 1"}), 400

    _scanner.start(interval_minutes=interval)
    return jsonify({"success": True, "message": "Scanner started.", **_scanner.status()})


@scanner_bp.route("/api/scanner/stop", methods=["POST"])
def scanner_stop():
    """Stop the background scanner."""
    _scanner.stop()
    return jsonify({"success": True, "message": "Scanner stopped.", **_scanner.status()})


@scanner_bp.route("/api/scanner/scan-now", methods=["POST"])
def scanner_scan_now():
    """Trigger an immediate scan without affecting the schedule."""
    _scanner.scan_now()
    return jsonify({"success": True, "message": "Scan triggered. Results will appear shortly."})


@scanner_bp.route("/api/scanner/results", methods=["GET"])
def scanner_results():
    """Return recently found jobs."""
    results = _scanner.get_recent_results()
    return jsonify({"count": len(results), "jobs": results})


@scanner_bp.route("/api/scanner/config", methods=["PUT"])
def scanner_config_update():
    """
    Update scanner configuration.
    Accepts JSON body with any of: ntfy_topic, interval_minutes, enabled, max_results_per_role.
    """
    body = flask_request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    config = _load_config()
    allowed_keys = {"ntfy_topic", "interval_minutes", "enabled", "max_results_per_role"}
    updated_keys = []

    for key in allowed_keys:
        if key in body:
            value = body[key]
            # Type validation
            if key == "ntfy_topic":
                if not isinstance(value, str) or not value.strip():
                    return jsonify({"error": f"{key} must be a non-empty string"}), 400
                config[key] = value.strip()
            elif key == "interval_minutes":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    return jsonify({"error": f"{key} must be an integer"}), 400
                if value < 1:
                    return jsonify({"error": f"{key} must be >= 1"}), 400
                config[key] = value
            elif key == "enabled":
                if not isinstance(value, bool):
                    return jsonify({"error": f"{key} must be a boolean"}), 400
                config[key] = value
            elif key == "max_results_per_role":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    return jsonify({"error": f"{key} must be an integer"}), 400
                if value < 1:
                    return jsonify({"error": f"{key} must be >= 1"}), 400
                config[key] = value
            updated_keys.append(key)

    _save_config(config)

    # If 'enabled' was explicitly toggled, start/stop accordingly
    if "enabled" in updated_keys:
        if config["enabled"] and not _scanner.running:
            _scanner.start(interval_minutes=config.get("interval_minutes"))
        elif not config["enabled"] and _scanner.running:
            _scanner.stop()

    return jsonify({
        "success": True,
        "updated": updated_keys,
        "config": config,
    })
