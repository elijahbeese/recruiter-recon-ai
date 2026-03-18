from flask import Blueprint, render_template, jsonify, request
from app.auth import login_required
from app.data import load_outreach_history, load_lookup_history, update_outreach_entry

history_bp = Blueprint("history", __name__)


@history_bp.route("/history")
@login_required
def history():
    outreach = load_outreach_history()
    lookups  = load_lookup_history()
    return render_template("history.html", outreach=outreach, lookups=lookups)


@history_bp.route("/api/history/outreach")
@login_required
def api_outreach_history():
    return jsonify(load_outreach_history())


@history_bp.route("/api/history/lookup")
@login_required
def api_lookup_history():
    return jsonify(load_lookup_history())


@history_bp.route("/api/history/outreach/mark-sent", methods=["POST"])
@login_required
def mark_sent():
    data     = request.get_json()
    entry_id = data.get("id", "")
    from app.data import now_iso
    update_outreach_entry(entry_id, {"status": "sent", "sent_at": now_iso()})
    return jsonify({"success": True})


@history_bp.route("/api/history/outreach/mark-response", methods=["POST"])
@login_required
def mark_response():
    data     = request.get_json()
    entry_id = data.get("id", "")
    update_outreach_entry(entry_id, {"response_received": True})
    return jsonify({"success": True})
