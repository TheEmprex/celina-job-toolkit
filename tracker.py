"""
Application Tracker — SQLite-backed Kanban board for Celina's Job Toolkit.
Blueprint: tracker_bp, mount at /tracker.
"""

import os
import sqlite3
import json
from datetime import datetime, date
from flask import Blueprint, render_template, request, jsonify

DB_PATH = os.path.expanduser("~/.celina_tracker.db")

tracker_bp = Blueprint("tracker", __name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _conn():
    """Return a new connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they do not exist. Called on import."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS applications (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            company       TEXT NOT NULL,
            title         TEXT NOT NULL DEFAULT '',
            department    TEXT DEFAULT '',
            url           TEXT DEFAULT '',
            status        TEXT DEFAULT 'applied',
            date_applied  TEXT DEFAULT '',
            date_updated  TEXT DEFAULT '',
            notes         TEXT DEFAULT '',
            cover_letter  TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            name            TEXT NOT NULL DEFAULT '',
            job_title       TEXT DEFAULT '',
            linkedin_url    TEXT DEFAULT '',
            email           TEXT DEFAULT '',
            category        TEXT DEFAULT '',
            message_sent    INTEGER DEFAULT 0,
            date_contacted  TEXT DEFAULT '',
            follow_up_date  TEXT DEFAULT '',
            follow_up_sent  INTEGER DEFAULT 0,
            notes           TEXT DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()


# Initialise on import so the DB is always ready.
init_db()


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


# ---------------------------------------------------------------------------
# CRUD — Applications
# ---------------------------------------------------------------------------

def list_applications():
    """Return all applications, newest first."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM applications ORDER BY id DESC"
    ).fetchall()
    conn.close()
    result = _rows_to_list(rows)
    # Attach contact count to each application
    conn = _conn()
    for app in result:
        count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM contacts WHERE application_id = ?",
            (app["id"],),
        ).fetchone()["cnt"]
        app["contact_count"] = count
    conn.close()
    return result


def create_application(data: dict) -> dict:
    """Insert a new application and return it."""
    now = _now()
    today = _today()
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO applications
           (company, title, department, url, status, date_applied, date_updated, notes, cover_letter)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("company", ""),
            data.get("title", ""),
            data.get("department", ""),
            data.get("url", ""),
            data.get("status", "applied"),
            data.get("date_applied", today),
            now,
            data.get("notes", ""),
            data.get("cover_letter", ""),
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    conn.close()
    result = _row_to_dict(row)
    result["contact_count"] = 0
    return result


def update_application(app_id: int, data: dict) -> dict | None:
    """Update an existing application. Only the provided keys are changed."""
    conn = _conn()
    existing = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if existing is None:
        conn.close()
        return None

    existing = _row_to_dict(existing)
    allowed = {
        "company", "title", "department", "url", "status",
        "date_applied", "notes", "cover_letter",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["date_updated"] = _now()

    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [app_id]
    conn.execute(f"UPDATE applications SET {sets} WHERE id = ?", vals)
    conn.commit()

    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM contacts WHERE application_id = ?",
        (app_id,),
    ).fetchone()["cnt"]
    conn.close()
    result = _row_to_dict(row)
    result["contact_count"] = count
    return result


def delete_application(app_id: int) -> bool:
    """Delete an application and its contacts. Returns True if it existed."""
    conn = _conn()
    existing = conn.execute(
        "SELECT id FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if existing is None:
        conn.close()
        return False
    conn.execute("DELETE FROM contacts WHERE application_id = ?", (app_id,))
    conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()
    return True


# ---------------------------------------------------------------------------
# CRUD — Contacts
# ---------------------------------------------------------------------------

def get_contacts(app_id: int):
    """Return contacts for an application."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM contacts WHERE application_id = ? ORDER BY id",
        (app_id,),
    ).fetchall()
    conn.close()
    return _rows_to_list(rows)


def create_contact(app_id: int, data: dict) -> dict:
    """Insert a contact linked to an application."""
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO contacts
           (application_id, name, job_title, linkedin_url, email, category,
            message_sent, date_contacted, follow_up_date, follow_up_sent, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            app_id,
            data.get("name", ""),
            data.get("job_title", ""),
            data.get("linkedin_url", ""),
            data.get("email", ""),
            data.get("category", ""),
            int(data.get("message_sent", 0)),
            data.get("date_contacted", ""),
            data.get("follow_up_date", ""),
            int(data.get("follow_up_sent", 0)),
            data.get("notes", ""),
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def update_contact(contact_id: int, data: dict) -> dict | None:
    """Update a contact row. Only provided keys are changed."""
    conn = _conn()
    existing = conn.execute(
        "SELECT * FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    if existing is None:
        conn.close()
        return None

    allowed = {
        "name", "job_title", "linkedin_url", "email", "category",
        "message_sent", "date_contacted", "follow_up_date",
        "follow_up_sent", "notes",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        conn.close()
        return _row_to_dict(existing)

    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [contact_id]
    conn.execute(f"UPDATE contacts SET {sets} WHERE id = ?", vals)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    """Aggregate statistics for the dashboard."""
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) AS cnt FROM applications").fetchone()["cnt"]

    statuses = conn.execute(
        "SELECT status, COUNT(*) AS cnt FROM applications GROUP BY status"
    ).fetchall()
    by_status = {r["status"]: r["cnt"] for r in statuses}

    total_contacts = conn.execute(
        "SELECT COUNT(*) AS cnt FROM contacts"
    ).fetchone()["cnt"]

    contacted = conn.execute(
        "SELECT COUNT(*) AS cnt FROM contacts WHERE message_sent = 1"
    ).fetchone()["cnt"]

    # Response rate: apps with status beyond 'applied' vs total
    responded_statuses = ("contacted", "interviewing", "offered")
    placeholders = ",".join("?" for _ in responded_statuses)
    responded = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM applications WHERE status IN ({placeholders})",
        responded_statuses,
    ).fetchone()["cnt"]

    conn.close()
    return {
        "total_applications": total,
        "by_status": by_status,
        "total_contacts": total_contacts,
        "contacts_messaged": contacted,
        "response_rate": round(responded / total * 100, 1) if total else 0,
    }


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

def save_pipeline_result(pipeline_data: dict) -> dict:
    """
    Create an application (+ contacts) from a pipeline run.
    Expects keys: company, title, department, url, cover_letter, people (list).
    Returns the created application dict.
    """
    app = create_application({
        "company": pipeline_data.get("company", ""),
        "title": pipeline_data.get("title", ""),
        "department": pipeline_data.get("department", ""),
        "url": pipeline_data.get("url", ""),
        "status": "applied",
        "cover_letter": pipeline_data.get("cover_letter", ""),
    })

    people = pipeline_data.get("people", [])
    for person in people:
        emails = person.get("emails", [])
        primary_email = ""
        if emails:
            primary_email = emails[0].get("email", "") if isinstance(emails[0], dict) else str(emails[0])
        create_contact(app["id"], {
            "name": person.get("name", ""),
            "job_title": person.get("job_title", ""),
            "linkedin_url": person.get("linkedin_url", ""),
            "email": primary_email,
            "category": person.get("category", ""),
        })

    app["contact_count"] = len(people)
    return app


# ---------------------------------------------------------------------------
# Flask Blueprint routes
# ---------------------------------------------------------------------------

@tracker_bp.route("/tracker")
def tracker_page():
    return render_template("tracker.html")


# --- Applications API ---

@tracker_bp.route("/api/applications", methods=["GET"])
def api_list_applications():
    return jsonify(list_applications())


@tracker_bp.route("/api/applications", methods=["POST"])
def api_create_application():
    data = request.get_json(force=True)
    if not data.get("company"):
        return jsonify({"error": "Company is required."}), 400
    return jsonify(create_application(data)), 201


@tracker_bp.route("/api/applications/<int:app_id>", methods=["PUT"])
def api_update_application(app_id):
    data = request.get_json(force=True)
    result = update_application(app_id, data)
    if result is None:
        return jsonify({"error": "Not found."}), 404
    return jsonify(result)


@tracker_bp.route("/api/applications/<int:app_id>", methods=["DELETE"])
def api_delete_application(app_id):
    if delete_application(app_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Not found."}), 404


# --- Contacts API ---

@tracker_bp.route("/api/applications/<int:app_id>/contacts", methods=["GET"])
def api_get_contacts(app_id):
    return jsonify(get_contacts(app_id))


@tracker_bp.route("/api/contacts/<int:contact_id>", methods=["PUT"])
def api_update_contact(contact_id):
    data = request.get_json(force=True)
    result = update_contact(contact_id, data)
    if result is None:
        return jsonify({"error": "Not found."}), 404
    return jsonify(result)


# --- Stats API ---

@tracker_bp.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(get_stats())
