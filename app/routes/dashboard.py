from flask import Blueprint, render_template, jsonify, request
import pandas as pd
from pathlib import Path

dashboard_bp = Blueprint("dashboard", __name__)

CSV_PATH = Path("output/enriched_jobs.csv")


def load_jobs():
    if not CSV_PATH.exists():
        return []
    try:
        df = pd.read_csv(CSV_PATH).fillna("")
        df = df.sort_values("overall_fit_score", ascending=False)
        return df.to_dict(orient="records")
    except Exception:
        return []


@dashboard_bp.route("/")
def dashboard():
    jobs = load_jobs()
    total = len(jobs)
    strong = sum(1 for j in jobs if int(j.get("overall_fit_score", 0)) >= 70)
    entry = sum(1 for j in jobs if j.get("entry_level_fit") == "yes")
    contacts = sum(1 for j in jobs if j.get("recruiter_contact_email", ""))
    sources = {}
    for j in jobs:
        s = j.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1
    score_dist = {
        "strong": sum(1 for j in jobs if int(j.get("overall_fit_score", 0)) >= 70),
        "good": sum(1 for j in jobs if 40 <= int(j.get("overall_fit_score", 0)) < 70),
        "low": sum(1 for j in jobs if int(j.get("overall_fit_score", 0)) < 40),
    }
    clearance_dist = {}
    for j in jobs:
        c = j.get("clearance_fit", "unknown")
        clearance_dist[c] = clearance_dist.get(c, 0) + 1

    return render_template(
        "dashboard.html",
        jobs=jobs,
        total=total,
        strong=strong,
        entry=entry,
        contacts=contacts,
        sources=sources,
        score_dist=score_dist,
        clearance_dist=clearance_dist,
    )


@dashboard_bp.route("/api/jobs")
def api_jobs():
    jobs = load_jobs()
    min_score = int(request.args.get("min_score", 0))
    entry_filter = request.args.get("entry_level_fit", "")
    clearance_filter = request.args.get("clearance_fit", "")
    source_filter = request.args.get("source", "")
    search = request.args.get("search", "").lower()

    filtered = []
    for j in jobs:
        if int(j.get("overall_fit_score", 0)) < min_score:
            continue
        if entry_filter and j.get("entry_level_fit") != entry_filter:
            continue
        if clearance_filter and j.get("clearance_fit") != clearance_filter:
            continue
        if source_filter and j.get("source") != source_filter:
            continue
        if search:
            searchable = f"{j.get('job_title','')} {j.get('company_name','')} {j.get('job_location','')} {j.get('fit_reasoning','')}".lower()
            if search not in searchable:
                continue
        filtered.append(j)

    return jsonify(filtered)
