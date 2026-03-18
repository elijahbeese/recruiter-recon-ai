from flask import Blueprint, render_template, request, jsonify
import json
from pathlib import Path
import pandas as pd

tracker_bp = Blueprint("tracker", __name__)
TRACKER_PATH = Path("output/tracker.json")
CSV_PATH = Path("output/enriched_jobs.csv")


def load_tracker() -> dict:
    if TRACKER_PATH.exists():
        with open(TRACKER_PATH) as f:
            return json.load(f)
    return {}


def save_tracker(data: dict):
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_jobs():
    if not CSV_PATH.exists():
        return []
    df = pd.read_csv(CSV_PATH).fillna("")
    return df.to_dict(orient="records")


@tracker_bp.route("/tracker")
def tracker():
    tracker_data = load_tracker()
    jobs = load_jobs()

    # Merge tracker status into jobs
    for job in jobs:
        url = job.get("job_url", "")
        if url in tracker_data:
            job["status"] = tracker_data[url].get("status", "discovered")
            job["notes"] = tracker_data[url].get("notes", "")
            job["applied_date"] = tracker_data[url].get("applied_date", "")
        else:
            job["status"] = "discovered"
            job["notes"] = ""
            job["applied_date"] = ""

    statuses = {
        "discovered": [j for j in jobs if j["status"] == "discovered"],
        "targeted":   [j for j in jobs if j["status"] == "targeted"],
        "applied":    [j for j in jobs if j["status"] == "applied"],
        "interviewing": [j for j in jobs if j["status"] == "interviewing"],
        "offer":      [j for j in jobs if j["status"] == "offer"],
        "rejected":   [j for j in jobs if j["status"] == "rejected"],
    }

    return render_template("tracker.html", statuses=statuses, jobs=jobs)


@tracker_bp.route("/api/tracker/update", methods=["POST"])
def update_status():
    data = request.get_json()
    url = data.get("url", "")
    status = data.get("status", "discovered")
    notes = data.get("notes", "")
    applied_date = data.get("applied_date", "")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    tracker_data = load_tracker()
    tracker_data[url] = {
        "status": status,
        "notes": notes,
        "applied_date": applied_date,
    }
    save_tracker(tracker_data)

    return jsonify({"success": True, "url": url, "status": status})


@tracker_bp.route("/api/tracker/stats")
def tracker_stats():
    tracker_data = load_tracker()
    stats = {}
    for url, info in tracker_data.items():
        s = info.get("status", "discovered")
        stats[s] = stats.get(s, 0) + 1
    return jsonify(stats)
