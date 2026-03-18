from flask import Blueprint, render_template, jsonify, request
from app.auth import login_required
from app.data import load_jobs, load_tracker, get_unread_alert_count
from collections import Counter

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def dashboard():
    jobs = load_jobs()
    tracker = load_tracker()

    # Merge tracker status
    for job in jobs:
        url = job.get("job_url", "")
        if url in tracker:
            job["status"] = tracker[url].get("status", "discovered")
            job["applied_date"] = tracker[url].get("applied_date", "")
        else:
            job["status"] = "discovered"
            job["applied_date"] = ""

    total     = len(jobs)
    strong    = sum(1 for j in jobs if int(j.get("overall_fit_score", 0)) >= 70)
    entry     = sum(1 for j in jobs if j.get("entry_level_fit") == "yes")
    contacts  = sum(1 for j in jobs if j.get("recruiter_contact_email", ""))
    applied   = sum(1 for j in jobs if j.get("status") == "applied")
    sources   = dict(Counter(j.get("source", "unknown") for j in jobs))
    unread_alerts = get_unread_alert_count()

    score_dist = {
        "strong": sum(1 for j in jobs if int(j.get("overall_fit_score", 0)) >= 70),
        "good":   sum(1 for j in jobs if 40 <= int(j.get("overall_fit_score", 0)) < 70),
        "low":    sum(1 for j in jobs if int(j.get("overall_fit_score", 0)) < 40),
    }

    clearance_dist = {}
    for j in jobs:
        c = j.get("clearance_fit", "unknown")
        clearance_dist[c] = clearance_dist.get(c, 0) + 1

    return render_template(
        "dashboard.html",
        jobs=jobs,
        total=total, strong=strong, entry=entry,
        contacts=contacts, applied=applied,
        sources=sources, score_dist=score_dist,
        clearance_dist=clearance_dist,
        unread_alerts=unread_alerts,
    )


@dashboard_bp.route("/api/jobs")
@login_required
def api_jobs():
    jobs = load_jobs()
    tracker = load_tracker()

    min_score       = int(request.args.get("min_score", 0))
    entry_filter    = request.args.get("entry_level_fit", "")
    clearance_filter= request.args.get("clearance_fit", "")
    source_filter   = request.args.get("source", "")
    search          = request.args.get("search", "").lower()

    filtered = []
    for j in jobs:
        url = j.get("job_url", "")
        if url in tracker:
            j["status"] = tracker[url].get("status", "discovered")
        else:
            j["status"] = "discovered"

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
