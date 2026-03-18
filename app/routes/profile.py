from flask import Blueprint, render_template, request, jsonify
import json
from pathlib import Path

profile_bp = Blueprint("profile", __name__)
PROFILE_PATH = Path("candidate_profile_generated.json")
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
def profile():
    data = load_profile()
    return render_template("profile.html", profile=data)


@profile_bp.route("/api/profile", methods=["GET"])
def get_profile():
    return jsonify(load_profile())


@profile_bp.route("/api/profile", methods=["POST"])
def update_profile():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    save_profile(data)
    return jsonify({"success": True})
