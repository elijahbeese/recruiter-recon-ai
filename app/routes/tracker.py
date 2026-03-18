from flask import Blueprint, render_template, request, jsonify
from app.auth import login_required
from app.data import load_jobs, load_tracker, update_tracker_entry, get_tracker_stats
from datetime import datetime

tracker_bp = Blueprint("tracker", __name__)


@tracker_bp.route("/tracker")
@login_required
def tracker():
    jobs    = load_jobs()
    tracker_data = load_tracker()

    for job in jobs:
        url = job.get("job_url", "")
        if url in tracker_data:
            job["status"]       = tracker_data[url].get("status", "discovered")
            job["notes"]        = tracker_data[url].get("notes", "")
            job["applied_date"] = tracker_data[url].get("applied_date", "")
            job["updated_at"]   = tracker_data[url].get("updated_at", "")
        else:
            job["status"]       = "discovered"
            job["notes"]        = ""
            job["applied_date"] = ""
            job["updated_at"]   = ""

    statuses = {
        "discovered":   [j for j in jobs if j["status"] == "discovered"],
        "targeted":     [j for j in jobs if j["status"] == "targeted"],
        "applied":      [j for j in jobs if j["status"] == "applied"],
        "interviewing": [j for j in jobs if j["status"] == "interviewing"],
        "offer":        [j for j in jobs if j["status"] == "offer"],
        "rejected":     [j for j in jobs if j["status"] == "rejected"],
    }

    # Timeline data — jobs with applied_date
    timeline = [
        j for j in jobs
        if j.get("applied_date") and j["status"] in ["applied","interviewing","offer","rejected"]
    ]
    timeline.sort(key=lambda x: x.get("applied_date",""), reverse=True)

    stats = get_tracker_stats()

    return render_template("tracker.html", statuses=statuses, jobs=jobs, timeline=timeline, stats=stats)


@tracker_bp.route("/api/tracker/update", methods=["POST"])
@login_required
def update_status():
    data         = request.get_json()
    url          = data.get("url", "")
    status       = data.get("status", "discovered")
    notes        = data.get("notes", "")
    applied_date = data.get("applied_date", "")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    update_tracker_entry(url, status, notes, applied_date)
    return jsonify({"success": True, "url": url, "status": status})


@tracker_bp.route("/api/tracker/stats")
@login_required
def tracker_stats():
    return jsonify(get_tracker_stats())
