"""
SITREP — Flask application factory v3.1
"""

import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("SECRET_KEY", "sitrep-dev-secret-change-in-prod")

    from app.routes.auth      import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.lookup    import lookup_bp
    from app.routes.recruiter import recruiter_bp
    from app.routes.pipeline  import pipeline_bp
    from app.routes.tracker   import tracker_bp
    from app.routes.outreach  import outreach_bp
    from app.routes.profile   import profile_bp
    from app.routes.history   import history_bp
    from app.routes.alerts    import alerts_bp
    from app.routes.gap       import gap_bp
    from app.routes.interview import interview_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(lookup_bp)
    app.register_blueprint(recruiter_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(tracker_bp)
    app.register_blueprint(outreach_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(gap_bp)
    app.register_blueprint(interview_bp)

    return app
