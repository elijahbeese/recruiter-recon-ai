from flask import Blueprint, render_template, jsonify
from app.auth import login_required
from app.data import load_alerts, mark_alerts_read, get_unread_alert_count

alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.route("/alerts")
@login_required
def alerts():
    all_alerts = load_alerts()
    mark_alerts_read()
    return render_template("alerts.html", alerts=all_alerts)


@alerts_bp.route("/api/alerts/unread")
@login_required
def unread_count():
    return jsonify({"count": get_unread_alert_count()})


@alerts_bp.route("/api/alerts")
@login_required
def api_alerts():
    return jsonify(load_alerts())
