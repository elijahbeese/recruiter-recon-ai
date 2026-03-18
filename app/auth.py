"""
app/auth.py
-----------
SITREP — Simple authentication
Username/password stored in .env
Session-based — persists until browser close or logout
"""

import os
from functools import wraps
from flask import session, redirect, url_for, request
from dotenv import load_dotenv

load_dotenv()

SITREP_USERNAME = os.getenv("SITREP_USERNAME", "sitrep").strip()
SITREP_PASSWORD = os.getenv("SITREP_PASSWORD", "changeme").strip()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def check_credentials(username: str, password: str) -> bool:
    return username == SITREP_USERNAME and password == SITREP_PASSWORD
