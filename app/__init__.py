"""
SITREP — Situation Report Job Intelligence Platform
Flask application factory
"""

from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = "sitrep-v3-secret-key-change-in-production"

    from app.routes.dashboard import dashboard_bp
    from app.routes.lookup import lookup_bp
    from app.routes.recruiter import recruiter_bp
    from app.routes.pipeline import pipeline_bp
    from app.routes.tracker import tracker_bp
    from app.routes.outreach import outreach_bp
    from app.routes.profile import profile_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(lookup_bp)
    app.register_blueprint(recruiter_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(tracker_bp)
    app.register_blueprint(outreach_bp)
    app.register_blueprint(profile_bp)

    return app
