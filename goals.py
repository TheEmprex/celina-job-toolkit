"""
Weekly Goals & Activity Tracking — extends Celina's Job Toolkit.
Blueprint: goals_bp, mount at /goals (or root).
Uses the same SQLite database as tracker.py (~/.celina_tracker.db).
"""

import os
import sqlite3
from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify

DB_PATH = os.path.expanduser("~/.celina_tracker.db")

goals_bp = Blueprint("goals", __name__)


# ---------------------------------------------------------------------------
# Database helpers (mirror tracker.py conventions)
# ---------------------------------------------------------------------------

def _conn():
    """Return a new connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows):
    return [dict(r) for r in rows]


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _today():
    return date.today().isoformat()


def _monday_of_week(d: date = None) -> str:
    """Return the ISO date string of the Monday for the week containing *d*."""
    if d is None:
        d = date.today()
    monday = d - timedelta(days=d.weekday())  # weekday(): Mon=0 … Sun=6
    return monday.isoformat()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_goals_db():
    """Create the weekly_goals and activity_log tables if they do not exist."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS weekly_goals (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start          TEXT NOT NULL,
            applications_target INTEGER DEFAULT 10,
            connections_target  INTEGER DEFAULT 20,
            messages_target     INTEGER DEFAULT 15,
            follow_ups_target   INTEGER DEFAULT 5
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            action_type TEXT NOT NULL,
            company     TEXT DEFAULT '',
            details     TEXT DEFAULT '',
            created_at  TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# Initialise on import so the tables are always ready.
init_goals_db()


# ---------------------------------------------------------------------------
# Core functions — Weekly goals
# ---------------------------------------------------------------------------

VALID_ACTION_TYPES = {
    "applied",
    "connected",
    "messaged",
    "followed_up",
    "searched",
    "interview_scheduled",
}

# Mapping from action_type → the key used in the actuals / targets dicts.
_ACTION_TO_METRIC = {
    "applied": "applications",
    "connected": "connections",
    "messaged": "messages",
    "followed_up": "follow_ups",
    "searched": "searches",
    "interview_scheduled": "interviews_scheduled",
}

# Weights for the weekly score (only the four goal-tracked metrics).
_SCORE_WEIGHTS = {
    "applications": 0.40,
    "connections": 0.25,
    "messages": 0.25,
    "follow_ups": 0.10,
}


def get_current_week_goals() -> dict:
    """
    Return the goals row for the current week.
    If no row exists yet, create one with default targets and return it.
    """
    week_start = _monday_of_week()
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM weekly_goals WHERE week_start = ?", (week_start,)
    ).fetchone()

    if row is None:
        conn.execute(
            """INSERT INTO weekly_goals
               (week_start, applications_target, connections_target,
                messages_target, follow_ups_target)
               VALUES (?, 10, 20, 15, 5)""",
            (week_start,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM weekly_goals WHERE week_start = ?", (week_start,)
        ).fetchone()

    conn.close()
    return _row_to_dict(row)


def set_weekly_goals(targets: dict) -> dict:
    """
    Update the current week's targets.
    Accepted keys: applications_target, connections_target,
                   messages_target, follow_ups_target.
    Returns the updated goals row.
    """
    # Ensure a row exists first.
    current = get_current_week_goals()
    week_start = current["week_start"]

    allowed = {
        "applications_target",
        "connections_target",
        "messages_target",
        "follow_ups_target",
    }
    updates = {k: int(v) for k, v in targets.items() if k in allowed}
    if not updates:
        return current

    conn = _conn()
    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [week_start]
    conn.execute(
        f"UPDATE weekly_goals SET {sets} WHERE week_start = ?", vals
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM weekly_goals WHERE week_start = ?", (week_start,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Core functions — Activity logging
# ---------------------------------------------------------------------------

def log_activity(action_type: str, company: str = "", details: str = "") -> dict:
    """
    Record a single activity event.
    action_type must be one of VALID_ACTION_TYPES.
    Returns the newly created activity_log row.
    """
    if action_type not in VALID_ACTION_TYPES:
        raise ValueError(
            f"Invalid action_type '{action_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ACTION_TYPES))}"
        )

    today = _today()
    now = _now()
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO activity_log (date, action_type, company, details, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (today, action_type, company, details, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM activity_log WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def get_activity_feed(limit: int = 20) -> list[dict]:
    """Return the most recent activity log entries, newest first."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return _rows_to_list(rows)


# ---------------------------------------------------------------------------
# Core functions — Weekly stats & score
# ---------------------------------------------------------------------------

def get_weekly_stats() -> dict:
    """
    Build the full weekly stats payload:
      - week_start
      - goals   (target values)
      - actuals (counts per metric for this week)
      - daily_breakdown  (list of {date, counts} dicts, Mon→Sun)
      - streak  (consecutive days ending today that have at least 1 activity)
      - score   (0–100 weighted average)
    """
    goals = get_current_week_goals()
    week_start = goals["week_start"]
    monday = date.fromisoformat(week_start)
    sunday = monday + timedelta(days=6)

    conn = _conn()

    # -- Actuals for the week ------------------------------------------------
    rows = conn.execute(
        """SELECT action_type, COUNT(*) AS cnt
           FROM activity_log
           WHERE date >= ? AND date <= ?
           GROUP BY action_type""",
        (week_start, sunday.isoformat()),
    ).fetchall()

    actuals = {
        "applications": 0,
        "connections": 0,
        "messages": 0,
        "follow_ups": 0,
        "searches": 0,
        "interviews_scheduled": 0,
    }
    for r in rows:
        metric = _ACTION_TO_METRIC.get(r["action_type"])
        if metric:
            actuals[metric] = r["cnt"]

    # -- Daily breakdown (Mon–Sun) ------------------------------------------
    day_rows = conn.execute(
        """SELECT date, action_type, COUNT(*) AS cnt
           FROM activity_log
           WHERE date >= ? AND date <= ?
           GROUP BY date, action_type
           ORDER BY date""",
        (week_start, sunday.isoformat()),
    ).fetchall()

    daily_map: dict[str, dict] = {}
    for r in day_rows:
        d = r["date"]
        if d not in daily_map:
            daily_map[d] = {
                "applications": 0,
                "connections": 0,
                "messages": 0,
                "follow_ups": 0,
                "searches": 0,
                "interviews_scheduled": 0,
            }
        metric = _ACTION_TO_METRIC.get(r["action_type"])
        if metric:
            daily_map[d][metric] = r["cnt"]

    daily_breakdown = []
    for i in range(7):
        d = (monday + timedelta(days=i)).isoformat()
        counts = daily_map.get(d, {
            "applications": 0,
            "connections": 0,
            "messages": 0,
            "follow_ups": 0,
            "searches": 0,
            "interviews_scheduled": 0,
        })
        daily_breakdown.append({"date": d, "counts": counts})

    # -- Streak (consecutive days with >=1 activity, ending today) -----------
    streak = 0
    check_date = date.today()
    while True:
        cnt = conn.execute(
            "SELECT COUNT(*) AS cnt FROM activity_log WHERE date = ?",
            (check_date.isoformat(),),
        ).fetchone()["cnt"]
        if cnt > 0:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    conn.close()

    # -- Score (weighted average, capped at 100) -----------------------------
    goal_targets = {
        "applications": goals["applications_target"],
        "connections": goals["connections_target"],
        "messages": goals["messages_target"],
        "follow_ups": goals["follow_ups_target"],
    }

    score = 0.0
    for metric, weight in _SCORE_WEIGHTS.items():
        target = goal_targets[metric]
        actual = actuals.get(metric, 0)
        ratio = (actual / target) if target > 0 else 0.0
        # Cap individual metric contribution at 1.0 (100 %)
        score += weight * min(ratio, 1.0)

    score = round(score * 100, 1)  # 0–100 scale
    score = min(score, 100.0)

    return {
        "week_start": week_start,
        "goals": {
            "applications_target": goals["applications_target"],
            "connections_target": goals["connections_target"],
            "messages_target": goals["messages_target"],
            "follow_ups_target": goals["follow_ups_target"],
        },
        "actuals": actuals,
        "daily_breakdown": daily_breakdown,
        "streak": streak,
        "score": score,
    }


# ---------------------------------------------------------------------------
# Pipeline auto-logging
# ---------------------------------------------------------------------------

def auto_log_pipeline_result(data: dict) -> list[dict]:
    """
    Automatically log activities after a pipeline run completes.
    Expects the same dict shape as tracker.save_pipeline_result():
        {company, title, department, url, people, ...}

    Logs:
      - 1 x "searched"  activity  (the pipeline searched for contacts)
      - 1 x "applied"   activity  (the pipeline created an application)

    Returns the list of created activity_log entries.
    """
    company = data.get("company", "")
    title = data.get("title", "")
    logged: list[dict] = []

    # Log the search action
    search_details = f"Pipeline search for {title} at {company}" if title else f"Pipeline search at {company}"
    logged.append(log_activity("searched", company=company, details=search_details))

    # Log the application action
    apply_details = f"Applied for {title} at {company}" if title else f"Applied at {company}"
    logged.append(log_activity("applied", company=company, details=apply_details))

    return logged


# ---------------------------------------------------------------------------
# Flask Blueprint routes
# ---------------------------------------------------------------------------

@goals_bp.route("/api/goals", methods=["GET"])
def api_get_goals():
    """Return current week goals combined with weekly stats."""
    stats = get_weekly_stats()
    return jsonify(stats)


@goals_bp.route("/api/goals", methods=["PUT"])
def api_update_goals():
    """Update weekly goal targets."""
    data = request.get_json(force=True)
    updated = set_weekly_goals(data)
    return jsonify(updated)


@goals_bp.route("/api/activity", methods=["POST"])
def api_log_activity():
    """Manually log an activity."""
    data = request.get_json(force=True)
    action_type = data.get("action_type", "")
    company = data.get("company", "")
    details = data.get("details", "")

    if action_type not in VALID_ACTION_TYPES:
        return jsonify({
            "error": f"Invalid action_type '{action_type}'. "
                     f"Must be one of: {', '.join(sorted(VALID_ACTION_TYPES))}"
        }), 400

    entry = log_activity(action_type, company=company, details=details)
    return jsonify(entry), 201


@goals_bp.route("/api/activity", methods=["GET"])
def api_get_activity():
    """Return the activity feed."""
    limit = request.args.get("limit", 20, type=int)
    feed = get_activity_feed(limit=limit)
    return jsonify(feed)
