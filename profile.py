"""
Profile system for Celina's Job Application Toolkit.
Stores profile as JSON at ~/.celina_profile.json.
Provides a Flask Blueprint with CRUD routes.
"""

import json
import os
from pathlib import Path
from flask import Blueprint, jsonify, request, render_template

PROFILE_PATH = Path.home() / ".celina_profile.json"

DEFAULT_PROFILE = {
    "name": "Celina",
    "last_name": "",
    "email": "",
    "phone": "",
    "linkedin_url": "",
    "summary": "",
    "skills": [],
    "experience": [],      # list of {title, company, duration, highlights}
    "education": [],       # list of {degree, school, year}
    "languages": [],
    "location": "",
    "target_roles": [],
    "tone": "professional",  # "professional" | "friendly" | "casual"
}


def load_profile() -> dict:
    """Load the profile from disk, returning defaults for any missing fields."""
    if not PROFILE_PATH.exists():
        return dict(DEFAULT_PROFILE)
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults so new fields are always present
        merged = dict(DEFAULT_PROFILE)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_PROFILE)


def save_profile(data: dict) -> None:
    """Save profile dict to disk as JSON."""
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def has_profile() -> bool:
    """Return True if a profile file exists and has at least a non-empty email or summary."""
    if not PROFILE_PATH.exists():
        return False
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("email") or data.get("summary") or data.get("last_name"))
    except (json.JSONDecodeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile", methods=["GET"])
def get_profile():
    """Return the current profile as JSON."""
    return jsonify(load_profile())


@profile_bp.route("/profile", methods=["POST"])
def post_profile():
    """Save the profile from the request JSON body."""
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid data"}), 400
    # Only keep known fields (plus anything extra the user might add)
    save_profile(data)
    return jsonify({"success": True})


@profile_bp.route("/profile/page")
def profile_page():
    """Render the profile editor page."""
    return render_template("profile.html")


@profile_bp.route("/profile/check")
def profile_check():
    """Quick check: has the user filled in their profile?"""
    return jsonify({"has_profile": has_profile()})
