"""
app/data.py
-----------
SITREP — Centralized data persistence layer

Handles all file-based storage:
  - Enriched jobs CSV
  - Application tracker (kanban status)
  - Outreach history
  - Job lookup history
  - Recruiter finder cache
  - Seen URLs (delta detection)
  - Alert state
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ENRICHED_CSV        = OUTPUT_DIR / "enriched_jobs.csv"
TRACKER_JSON        = OUTPUT_DIR / "tracker.json"
OUTREACH_HISTORY    = OUTPUT_DIR / "outreach_history.json"
LOOKUP_HISTORY      = OUTPUT_DIR / "lookup_history.json"
RECRUITER_CACHE     = OUTPUT_DIR / "recruiter_cache.json"
SEEN_URLS           = OUTPUT_DIR / "seen_urls.json"
ALERTS_JSON         = OUTPUT_DIR / "alerts.json"


# ── Generic helpers ────────────────────────────────────────────────────────────

def _load_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def now_iso() -> str:
    return datetime.now().isoformat()


# ── Enriched jobs ──────────────────────────────────────────────────────────────

def load_jobs() -> List[Dict[str, Any]]:
    if not ENRICHED_CSV.exists():
        return []
    try:
        df = pd.read_csv(ENRICHED_CSV).fillna("")
        df = df.sort_values("overall_fit_score", ascending=False)
        return df.to_dict(orient="records")
    except Exception:
        return []


def get_job_by_url(url: str) -> Optional[Dict[str, Any]]:
    for job in load_jobs():
        if job.get("job_url", "") == url:
            return job
    return None


# ── Application tracker ────────────────────────────────────────────────────────

def load_tracker() -> Dict[str, Any]:
    return _load_json(TRACKER_JSON, {})


def save_tracker(data: Dict[str, Any]):
    _save_json(TRACKER_JSON, data)


def update_tracker_entry(url: str, status: str, notes: str = "", applied_date: str = ""):
    data = load_tracker()
    data[url] = {
        "status": status,
        "notes": notes,
        "applied_date": applied_date,
        "updated_at": now_iso(),
    }
    save_tracker(data)


def get_tracker_stats() -> Dict[str, int]:
    data = load_tracker()
    stats = {}
    for entry in data.values():
        s = entry.get("status", "discovered")
        stats[s] = stats.get(s, 0) + 1
    return stats


# ── Outreach history ───────────────────────────────────────────────────────────

def load_outreach_history() -> List[Dict[str, Any]]:
    return _load_json(OUTREACH_HISTORY, [])


def save_outreach_entry(
    job: Dict[str, Any],
    subject: str,
    body: str,
    follow_up: str,
    recruiter_name: str,
    recruiter_email: str,
    tone: str,
    hooks: List[str],
):
    history = load_outreach_history()
    history.insert(0, {
        "id": f"outreach_{len(history)+1}_{now_iso()}",
        "created_at": now_iso(),
        "job_title": job.get("job_title", ""),
        "company_name": job.get("company_name", ""),
        "job_url": job.get("job_url", ""),
        "fit_score": job.get("overall_fit_score", ""),
        "recruiter_name": recruiter_name,
        "recruiter_email": recruiter_email,
        "tone": tone,
        "subject_line": subject,
        "email_body": body,
        "follow_up_line": follow_up,
        "key_hooks": hooks,
        "status": "drafted",
        "sent_at": None,
        "response_received": False,
        "follow_up_sent": False,
        "notes": "",
    })
    _save_json(OUTREACH_HISTORY, history)
    return history[0]


def update_outreach_entry(entry_id: str, updates: Dict[str, Any]):
    history = load_outreach_history()
    for entry in history:
        if entry.get("id") == entry_id:
            entry.update(updates)
            break
    _save_json(OUTREACH_HISTORY, history)


# ── Job lookup history ─────────────────────────────────────────────────────────

def load_lookup_history() -> List[Dict[str, Any]]:
    return _load_json(LOOKUP_HISTORY, [])


def save_lookup_entry(url: str, analysis: Dict[str, Any]):
    history = load_lookup_history()
    # Avoid duplicates
    history = [h for h in history if h.get("job_url") != url]
    history.insert(0, {
        "job_url": url,
        "looked_up_at": now_iso(),
        **analysis,
    })
    history = history[:50]  # Keep last 50
    _save_json(LOOKUP_HISTORY, history)


# ── Recruiter finder cache ─────────────────────────────────────────────────────

def load_recruiter_cache() -> Dict[str, Any]:
    return _load_json(RECRUITER_CACHE, {})


def get_cached_recruiter(domain: str) -> Optional[Dict[str, Any]]:
    cache = load_recruiter_cache()
    entry = cache.get(domain)
    if not entry:
        return None
    # Cache expires after 7 days
    cached_at = entry.get("cached_at", "")
    if cached_at:
        try:
            age = (datetime.now() - datetime.fromisoformat(cached_at)).days
            if age > 7:
                return None
        except Exception:
            pass
    return entry


def save_recruiter_cache(domain: str, data: Dict[str, Any]):
    cache = load_recruiter_cache()
    cache[domain] = {**data, "cached_at": now_iso()}
    _save_json(RECRUITER_CACHE, cache)


# ── Alerts ─────────────────────────────────────────────────────────────────────

def load_alerts() -> List[Dict[str, Any]]:
    return _load_json(ALERTS_JSON, [])


def save_alerts(alerts: List[Dict[str, Any]]):
    _save_json(ALERTS_JSON, alerts)


def add_alert(message: str, alert_type: str = "info", job_url: str = ""):
    alerts = load_alerts()
    alerts.insert(0, {
        "id": f"alert_{len(alerts)+1}",
        "message": message,
        "type": alert_type,
        "job_url": job_url,
        "created_at": now_iso(),
        "read": False,
    })
    alerts = alerts[:100]
    save_alerts(alerts)


def mark_alerts_read():
    alerts = load_alerts()
    for a in alerts:
        a["read"] = True
    save_alerts(alerts)


def get_unread_alert_count() -> int:
    return sum(1 for a in load_alerts() if not a.get("read"))
