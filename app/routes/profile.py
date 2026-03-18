from flask import Blueprint, render_template, request, jsonify
import json
from pathlib import Path
from app.auth import login_required

profile_bp = Blueprint("profile", __name__)
PROFILE_PATH  = Path("candidate_profile_generated.json")
FALLBACK_PATH = Path("candidate_profile.json")


def load_profile():
    for path in [PROFILE_PATH, FALLBACK_PATH]:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return {}


def save_profile(data: dict):
    PROFILE_PATH.write_text(json.dumps(data, indent=2))


@profile_bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", profile=load_profile())


@profile_bp.route("/api/profile", methods=["GET"])
@login_required
def get_profile():
    return jsonify(load_profile())


@profile_bp.route("/api/profile", methods=["POST"])
@login_required
def update_profile():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    save_profile(data)
    return jsonify({"success": True})
