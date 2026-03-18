"""
SITREP — run_app.py
Entry point for both local development and production (Railway/Gunicorn)

Local:      python run_app.py
Production: gunicorn run_app:app
"""

import os
import webbrowser
import threading
from app import create_app

app = create_app()


def open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.2, open_browser).start()
    print("\n" + "=" * 50)
    print("  SITREP — Job Intelligence Platform")
    print("  -> http://127.0.0.1:5000")
    print("=" * 50 + "\n")
    app.run(
        host="0.0.0.0",
        debug=True,
        use_reloader=False,
        port=int(os.getenv("PORT", 5000)),
    )
