"""
SITREP — run_app.py
Entry point: python run_app.py
Opens at http://localhost:5000
"""

import webbrowser
import threading
from app import create_app

app = create_app()


def open_browser():
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    threading.Timer(1.2, open_browser).start()
    print("\n" + "═" * 50)
    print("  SITREP — Job Intelligence Platform")
    print("  http://127.0.0.1:5000")
    print("═" * 50 + "\n")
    app.run(debug=True, use_reloader=False, port=5000)
