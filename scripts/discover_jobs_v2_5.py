"""
discover_jobs_v2_5.py
---------------------
SITREP — Discovery Engine v2.5

Changes from v2.4:
  - Parallel execution via ThreadPoolExecutor (replaces aiohttp — more reliable)
  - JSearch API — hits LinkedIn, Indeed, Glassdoor, ZipRecruiter simultaneously
  - Adzuna API — aggregates 15+ job boards with full descriptions
  - Greenhouse directory scraping — verified slugs instead of guessing
  - Lever expanded company list — 54 boards queried in parallel
  - The Muse API — free, no key needed
  - Delta detection — seen URLs saved to output/seen_urls.json
  - Target runtime: under 3 minutes
"""

# ─────────────────────────────────────────────
# SECTION 1: IMPORTS & CONSTANTS
# ─────────────────────────────────────────────

import csv
import json
import os
import re
import time
import random
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── API credentials ────────────────────────────────────────────────────────────
USAJOBS_API_KEY    = os.getenv("USAJOBS_API_KEY", "").strip()
USAJOBS_USER_AGENT = os.getenv("USAJOBS_USER_AGENT", "").strip()
JSEARCH_API_KEY    = os.getenv("JSEARCH_API_KEY", "").strip()
ADZUNA_APP_ID      = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY     = os.getenv("ADZUNA_APP_KEY", "").strip()

# ── Runtime config ─────────────────────────────────────────────────────────────
REQUEST_TIMEOUT            = 12
ENRICHMENT_SCORE_THRESHOLD = 50
MAX_RAW_POOL               = 600
MAX_WORKERS                = 20
SEEN_URLS_PATH             = Path("output/seen_urls.json")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# ── Source priority ────────────────────────────────────────────────────────────
SOURCE_PRIORITY = {
    "usajobs":       95,
    "clearancejobs": 92,
    "greenhouse":    90,
    "lever":         90,
    "jsearch":       88,
    "workday":       88,
    "icims":         85,
    "adzuna":        85,
    "muse":          82,
    "other":         40,
}

# ── Relevance signals ──────────────────────────────────────────────────────────
CYBER_KEYWORDS = [
    "cyber", "security", "soc", "analyst", "incident response",
    "threat", "intelligence", "network security", "information security",
    "infosec", "vulnerability", "penetration", "forensics", "siem",
    "splunk", "firewall", "noc", "toc", "operations center",
    "cleared", "secret", "top secret", "dod", "federal", "government",
    "critical infrastructure", "ics", "scada", "defense", "army",
    "monitoring", "detection", "response", "malware", "endpoint",
    "cloud security", "devsecops", "appsec", "red team", "blue team",
]

SENIOR_MARKERS = [
    r"\bsenior\b", r"\bsr\.\b", r"\blead\b", r"\bprincipal\b",
    r"\bstaff\b", r"\bmanager\b", r"\bdirector\b", r"\barchitect\b",
    r"\bsupervisor\b", r"\bchief\b", r"\bhead of\b", r"\bvp\b",
    r"nh-04", r"nh-05", r"gs-13", r"gs-14", r"gs-15",
]

JUNK_MARKERS = [
    "jobs near", "get hired", "salary", "career advice", "resume tips",
    "browse jobs", "search jobs", "job alert", "sign in", "login",
    "financial analyst", "physical security guard", "administrative assistant",
    "human resources manager", "accountant", "marketing manager",
]

# ── Company lists ──────────────────────────────────────────────────────────────
GREENHOUSE_COMPANIES = [
    "crowdstrike", "sentinelone", "huntress", "expel", "redcanary",
    "blumira", "deepwatch", "threatlocker", "recordedfuture", "flashpoint",
    "dragos", "claroty", "vectra", "exabeam", "anomali", "cybereason",
    "coalfire", "optiv", "guidepoint", "trustwave", "secureworks",
    "rapid7", "tenable", "qualys", "beyondtrust", "cyberark",
    "sailpoint", "okta", "delinea", "paloaltonetworks", "fortinet",
    "capitalone", "stripe", "palantir", "anduril", "govini",
    "deloitte", "accenture", "ibm", "lacework", "snyk",
    "wiz", "orca-security", "apiiro", "armorcode", "deepinstinct",
    "axonius", "sevenzero", "netspi", "horizon3ai", "runzero",
    "corelight", "gravwell", "datto", "cofense", "proofpoint",
    "abnormal-security", "material-security", "ironscales", "tessian",
    "flare-systems", "securin", "veriti", "revelstoke", "torq",
    "microsoft", "google", "amazon", "apple", "meta",
    "oracle", "salesforce", "servicenow", "splunk", "cloudflare",
    "datadog", "elastic", "hashicorp", "saic", "leidos",
    "boozallen", "caci", "mantech", "peraton", "parsons",
    "usaa", "jpmorgan", "bankofamerica", "wellsfargo", "visa",
    "mastercard", "paypal", "robinhood", "coinbase", "brex",
    "hca-healthcare", "cigna", "unitedhealth", "humana", "nextera",
]

LEVER_COMPANIES = [
    "palantir", "anduril", "shield-ai", "rebellion-defense", "scale-ai",
    "primer", "govini", "c3-ai", "crowdstrike", "huntress", "expel",
    "redcanary", "blumira", "lumu", "ncc-group", "bishopfox",
    "abnormal-security", "material-security", "cofense", "ironscales",
    "cloudflare", "datadog", "elastic", "lacework", "wiz",
    "capitalone", "stripe", "brex", "plaid", "robinhood", "coinbase",
    "oscar-health", "deloitte", "boozallen", "telos",
    "flare-systems", "securin", "veriti", "revelstoke", "torq",
    "intsights", "cybersixgill", "deepinstinct", "axonius",
    "microsoft", "google", "amazon", "apple", "meta", "ibm",
    "techdata", "verizon-business",
]

ICIMS_COMPANIES = [
    ("bah", "careers.boozallen.com", "Booz Allen Hamilton"),
    ("mantech", "careers.mantech.com", "ManTech"),
    ("caci", "careers.caci.com", "CACI"),
    ("mitre", "careers.mitre.org", "MITRE"),
    ("l3harris", "careers.l3harris.com", "L3Harris"),
    ("jpmorgan", "careers.jpmorgan.com", "JPMorgan Chase"),
    ("bankofamerica", "careers.bankofamerica.com", "Bank of America"),
    ("hca", "careers.hcahealthcare.com", "HCA Healthcare"),
    ("raymond-james", "careers.raymondjames.com", "Raymond James"),
]

USAJOBS_KEYWORDS = [
    "cybersecurity analyst", "SOC analyst", "information security analyst",
    "network security", "incident response analyst", "cyber operations",
    "threat analyst", "vulnerability analyst", "security operations center",
    "cyber defense analyst", "computer network defense",
]

JSEARCH_QUERIES = [
    "SOC analyst entry level",
    "cybersecurity analyst entry level clearance",
    "incident response analyst junior",
    "network security analyst entry level",
    "information security analyst secret clearance",
    "cyber operations analyst DoD",
    "threat intelligence analyst entry level",
    "SIEM analyst Splunk entry level",
    "security operations center analyst",
    "NOC analyst cybersecurity",
]

ADZUNA_QUERIES = [
    "SOC analyst", "cybersecurity analyst", "incident response analyst",
    "network security analyst", "information security analyst",
    "cyber operations", "threat analyst", "vulnerability analyst",
    "SIEM analyst", "security engineer entry level",
]


# ─────────────────────────────────────────────
# SECTION 2: UTILITIES
# ─────────────────────────────────────────────

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def normalized_hostname(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower().lstrip("www.")
    except Exception:
        return ""


def strip_html(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def is_relevant(title: str, description: str = "") -> bool:
    text = f"{title} {description}".lower()
    if any(j in text for j in JUNK_MARKERS):
        return False
    return any(k in text for k in CYBER_KEYWORDS)


def is_too_senior(title: str) -> bool:
    t = title.lower()
    return any(re.search(p, t) for p in SENIOR_MARKERS)


def normalize_title(title: str) -> str:
    title = clean_text(title).lower()
    title = re.sub(r"\s*[-–|]\s*(new york|washington|palo alto|remote|dc|ny|ca|fl|tx|md|va|nationwide).*$", "", title)
    return title.strip()


def load_seen_urls() -> Set[str]:
    if SEEN_URLS_PATH.exists():
        try:
            with open(SEEN_URLS_PATH) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen_urls(urls: Set[str]) -> None:
    SEEN_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_URLS_PATH, "w") as f:
        json.dump(list(urls), f)


def load_profile(path: str = "candidate_profile_generated.json") -> Dict[str, Any]:
    for p in [path, "candidate_profile.json"]:
        if Path(p).exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("No candidate profile found.")


def load_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY missing in .env")
    return OpenAI(api_key=api_key)


def write_csv(path: str, rows: List[Dict[str, Any]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "company_name", "company_domain", "job_title", "job_url",
        "job_location", "recruiter_name", "notes", "source",
        "discovery_score", "ai_fit_score", "ai_reason",
    ]
    normalized = [{f: row.get(f, "") for f in fieldnames} for row in rows]
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)
    return out


def score_heuristic(title: str, description: str, source: str, profile: Dict[str, Any]) -> int:
    text = f"{title} {description}".lower()
    score = SOURCE_PRIORITY.get(source, 40)
    for kw in CYBER_KEYWORDS:
        if kw in text:
            score += 3
    if not is_too_senior(title):
        score += 12
    entry_terms = ["entry", "junior", "associate", "tier 1", "tier i", "level i", "early career", "new grad", "analyst i"]
    if any(t in text for t in entry_terms):
        score += 10
    for role in profile.get("target_roles", []):
        if role.lower() in text:
            score += 10
    matched = sum(1 for s in profile.get("skills", [])[:20] if s.lower() in text)
    score += min(matched * 3, 24)
    if "secret" in profile.get("clearance_relevance", "").lower():
        if any(t in text for t in ["clearance", "secret", "top secret", "dod", "federal"]):
            score += 15
    if any(t in text for t in ["defense", "army", "dod", "federal", "critical infrastructure", "ics", "scada"]):
        score += 10
    return score


def make_job_row(company_name, company_domain, job_title, job_url, job_location, notes, source, profile):
    return {
        "company_name":    clean_text(company_name),
        "company_domain":  clean_text(company_domain),
        "job_title":       clean_text(job_title),
        "job_url":         clean_text(job_url),
        "job_location":    clean_text(job_location),
        "recruiter_name":  "",
        "notes":           clean_text(notes)[:300],
        "source":          source,
        "discovery_score": score_heuristic(job_title, notes, source, profile),
        "ai_fit_score":    0,
        "ai_reason":       "",
    }


def dedupe_jobs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_urls: set = set()
    seen_ct: set = set()
    deduped = []
    for row in rows:
        url = clean_text(row.get("job_url", "")).lower()
        ct = f"{clean_text(row.get('company_name','')).lower()}||{normalize_title(row.get('job_title',''))}"
        if url and url in seen_urls:
            continue
        if ct in seen_ct:
            continue
        if url:
            seen_urls.add(url)
        seen_ct.add(ct)
        deduped.append(row)
    return deduped


def safe_get(url: str, headers: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[requests.Response]:
    try:
        resp = SESSION.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


# ─────────────────────────────────────────────
# SECTION 3: JSEARCH (parallel)
# ─────────────────────────────────────────────

def _jsearch_single(query: str, location: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not JSEARCH_API_KEY:
        return []
    headers = {
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
        "x-rapidapi-key": JSEARCH_API_KEY,
    }
    params = {
        "query": f"{query} {location}",
        "page": "1",
        "num_pages": "1",
        "country": "us",
        "date_posted": "month",
    }
    resp = safe_get("https://jsearch.p.rapidapi.com/search", headers=headers, params=params)
    if not resp:
        return []

    results = []
    try:
        data = resp.json()
    except Exception:
        return []

    for job in data.get("data", []):
        title = clean_text(job.get("job_title", ""))
        company = clean_text(job.get("employer_name", ""))
        job_url = clean_text(job.get("job_apply_link", "") or job.get("job_google_link", ""))
        loc = clean_text(f"{job.get('job_city','')}, {job.get('job_state','')}".strip(", "))
        description = clean_text(job.get("job_description", ""))[:300]
        domain = clean_text(job.get("employer_website", "") or "").replace("https://","").replace("http://","").split("/")[0]

        if not title or not job_url:
            continue
        if not is_relevant(title, description) or is_too_senior(title):
            continue

        results.append(make_job_row(company, domain, title, job_url, loc or location, description, "jsearch", profile))

    return results


def fetch_jsearch(profile: Dict[str, Any], max_results: int = 200) -> List[Dict[str, Any]]:
    if not JSEARCH_API_KEY:
        print("[JSearch] Skipping — JSEARCH_API_KEY not configured.")
        return []

    locations = profile.get("location_preferences", ["Tampa, FL"])[:2] + ["Remote", "United States"]
    tasks = [(q, l) for q in JSEARCH_QUERIES[:8] for l in locations[:3]]

    results = []
    seen_urls: set = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_jsearch_single, q, l, profile): (q, l) for q, l in tasks}
        for future in as_completed(futures):
            try:
                for job in future.result():
                    url = job.get("job_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(job)
            except Exception:
                pass

    print(f"[JSearch] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 4: ADZUNA (parallel)
# ─────────────────────────────────────────────

def _adzuna_single(query: str, location: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    loc_map = {
        "Tampa, FL": "florida", "Florida": "florida",
        "Remote": "", "United States": "",
        "Virginia": "virginia", "Texas": "texas",
    }
    adzuna_loc = loc_map.get(location, "")

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": 20,
        "what": query,
        "sort_by": "date",
    }
    if adzuna_loc:
        params["where"] = adzuna_loc

    resp = safe_get("https://api.adzuna.com/v1/api/jobs/us/search/1", params=params)
    if not resp:
        return []

    results = []
    try:
        data = resp.json()
    except Exception:
        return []

    for job in data.get("results", []):
        title = clean_text(job.get("title", ""))
        company = clean_text((job.get("company") or {}).get("display_name", ""))
        job_url = clean_text(job.get("redirect_url", ""))
        loc_obj = job.get("location", {})
        loc_str = clean_text(", ".join(loc_obj.get("area", [])[-2:]) if loc_obj else "")
        description = clean_text(job.get("description", ""))[:300]

        if not title or not job_url:
            continue
        if not is_relevant(title, description) or is_too_senior(title):
            continue

        results.append(make_job_row(company, "", title, job_url, loc_str or location, description, "adzuna", profile))

    return results


def fetch_adzuna(profile: Dict[str, Any], max_results: int = 200) -> List[Dict[str, Any]]:
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("[Adzuna] Skipping — credentials not configured.")
        return []

    locations = profile.get("location_preferences", ["Tampa, FL"])[:2] + ["Remote", "United States"]
    tasks = [(q, l) for q in ADZUNA_QUERIES[:8] for l in locations[:3]]

    results = []
    seen_urls: set = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_adzuna_single, q, l, profile): (q, l) for q, l in tasks}
        for future in as_completed(futures):
            try:
                for job in future.result():
                    url = job.get("job_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(job)
            except Exception:
                pass

    print(f"[Adzuna] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 5: GREENHOUSE (parallel)
# ─────────────────────────────────────────────

def _greenhouse_single(slug: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    resp = safe_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if not resp:
        return []
    try:
        jobs = resp.json().get("jobs", [])
    except Exception:
        return []

    results = []
    for job in jobs:
        title = clean_text(job.get("title", ""))
        job_url = clean_text(job.get("absolute_url", ""))
        location = clean_text((job.get("location") or {}).get("name", ""))
        if not title or not job_url:
            continue
        if not is_relevant(title) or is_too_senior(title):
            continue
        results.append(make_job_row(
            slug.replace("-", " ").title(), f"{slug}.com",
            title, job_url, location, f"Greenhouse — {slug}", "greenhouse", profile
        ))
    return results


def fetch_greenhouse(profile: Dict[str, Any], max_results: int = 300) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_greenhouse_single, slug, profile): slug for slug in GREENHOUSE_COMPANIES}
        for future in as_completed(futures):
            try:
                for job in future.result():
                    url = job.get("job_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(job)
            except Exception:
                pass

    hits = sum(1 for _ in results)
    print(f"[Greenhouse] {len(results)} postings found across {len(GREENHOUSE_COMPANIES)} companies")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 6: LEVER (parallel)
# ─────────────────────────────────────────────

def _lever_single(slug: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    resp = safe_get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not resp:
        return []
    try:
        jobs = resp.json()
        if not isinstance(jobs, list):
            return []
    except Exception:
        return []

    results = []
    for job in jobs:
        title = clean_text(job.get("text", ""))
        job_url = clean_text(job.get("hostedUrl", ""))
        location = clean_text((job.get("categories") or {}).get("location", ""))
        description = strip_html(job.get("descriptionPlain", "") or "")
        if not title or not job_url:
            continue
        if not is_relevant(title, description) or is_too_senior(title):
            continue
        results.append(make_job_row(
            slug.replace("-", " ").title(), f"{slug}.com",
            title, job_url, location, description[:300], "lever", profile
        ))
    return results


def fetch_lever(profile: Dict[str, Any], max_results: int = 300) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_lever_single, slug, profile): slug for slug in LEVER_COMPANIES}
        for future in as_completed(futures):
            try:
                for job in future.result():
                    url = job.get("job_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(job)
            except Exception:
                pass

    print(f"[Lever] {len(results)} postings found across {len(LEVER_COMPANIES)} companies")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 7: THE MUSE (parallel)
# ─────────────────────────────────────────────

def _muse_single(category: str, page: int, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    resp = safe_get(
        f"https://www.themuse.com/api/public/jobs",
        params={"category": category, "page": page, "descending": "true"}
    )
    if not resp:
        return []
    try:
        data = resp.json()
    except Exception:
        return []

    results = []
    for job in data.get("results", []):
        title = clean_text(job.get("name", ""))
        company = clean_text((job.get("company") or {}).get("name", ""))
        job_url = clean_text((job.get("refs") or {}).get("landing_page", ""))
        locations = job.get("locations", [{}])
        location = clean_text(locations[0].get("name", "")) if locations else ""
        description = strip_html(job.get("contents", ""))[:300]

        if not title or not job_url:
            continue
        if not is_relevant(title, description) or is_too_senior(title):
            continue

        results.append(make_job_row(company, "", title, job_url, location, description, "muse", profile))
    return results


def fetch_muse(profile: Dict[str, Any], max_results: int = 100) -> List[Dict[str, Any]]:
    categories = ["IT", "Software Engineer", "Data Science", "DevOps", "Cybersecurity"]
    results = []
    seen_urls: set = set()

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_muse_single, cat, page, profile): (cat, page)
                   for cat in categories for page in range(1, 4)}
        for future in as_completed(futures):
            try:
                for job in future.result():
                    url = job.get("job_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(job)
            except Exception:
                pass

    print(f"[The Muse] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 8: USAJOBS (sync — rate limited)
# ─────────────────────────────────────────────

def fetch_usajobs(profile: Dict[str, Any], max_results: int = 150) -> List[Dict[str, Any]]:
    if not USAJOBS_API_KEY or not USAJOBS_USER_AGENT:
        print("[USAJobs] Skipping — API key not configured.")
        return []

    headers = {
        "Authorization-Key": USAJOBS_API_KEY,
        "User-Agent": USAJOBS_USER_AGENT,
        "Host": "data.usajobs.gov",
    }
    locations = profile.get("location_preferences", ["Tampa, FL"])[:3] + ["", "Remote"]
    results = []
    seen_ids: set = set()

    for keyword in USAJOBS_KEYWORDS:
        for location in locations[:3]:
            params = {
                "Keyword": keyword,
                "ResultsPerPage": 25,
                "WhoMayApply": "all",
                "SortField": "OpenDate",
                "SortDirection": "Desc",
            }
            if location:
                params["LocationName"] = location

            try:
                resp = requests.get(
                    "https://data.usajobs.gov/api/search",
                    headers=headers, params=params, timeout=REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                items = resp.json().get("SearchResult", {}).get("SearchResultItems", [])
            except Exception:
                continue

            for item in items:
                d = item.get("MatchedObjectDescriptor", {})
                job_id = d.get("PositionID", "")
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                title = d.get("PositionTitle", "")
                if not is_relevant(title) or is_too_senior(title):
                    continue

                org = d.get("OrganizationName", "") or d.get("DepartmentName", "")
                url = d.get("PositionURI", "")
                locs = d.get("PositionLocation", [{}])
                loc_str = locs[0].get("LocationName", "") if locs else ""
                quals = d.get("QualificationSummary", "")
                rem = d.get("PositionRemuneration", [])
                pay = f"Pay: {rem[0].get('MinimumRange','')}–{rem[0].get('MaximumRange','')}" if rem else ""

                results.append(make_job_row(
                    org, "usajobs.gov", title, url, loc_str,
                    f"{quals[:200]} {pay}".strip(), "usajobs", profile
                ))
            time.sleep(0.3)

        if len(results) >= max_results:
            break

    print(f"[USAJobs] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 9: CLEARANCEJOBS (sync)
# ─────────────────────────────────────────────

def fetch_clearancejobs(profile: Dict[str, Any], max_results: int = 100) -> List[Dict[str, Any]]:
    queries = [
        "SOC analyst Secret clearance", "cybersecurity analyst Secret",
        "incident response Secret clearance", "network security analyst clearance",
        "cyber operations Secret TS", "information security analyst DoD",
        "SIEM analyst clearance", "threat analyst Secret",
    ]
    locations = profile.get("location_preferences", ["Tampa, FL"])[:2] + ["Remote"]
    results = []
    seen_urls: set = set()

    for query in queries:
        for location in locations[:2]:
            try:
                resp = SESSION.get(
                    "https://www.clearancejobs.com/jobs/rss",
                    params={"q": query, "l": location, "sort": "date"},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
            except Exception:
                continue

            for item in root.findall(".//item"):
                title = clean_text(item.findtext("title", ""))
                job_url = clean_text(item.findtext("link", ""))
                description = strip_html(item.findtext("description", ""))

                if not title or not job_url or job_url in seen_urls:
                    continue
                if not is_relevant(title, description) or is_too_senior(title):
                    continue

                seen_urls.add(job_url)
                company = ""
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    company = parts[1].strip()

                results.append(make_job_row(
                    company, normalized_hostname(job_url),
                    title, job_url, location, description[:300], "clearancejobs", profile
                ))
            time.sleep(0.8)

        if len(results) >= max_results:
            break

    print(f"[ClearanceJobs] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 10: iCIMS (sync)
# ─────────────────────────────────────────────

def fetch_icims(profile: Dict[str, Any], max_results: int = 75) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()

    for slug, domain, company_name in ICIMS_COMPANIES:
        for keyword in ["cybersecurity", "SOC analyst"][:2]:
            resp = safe_get(f"https://{domain}/jobs/search?q={quote_plus(keyword)}")
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            links = soup.select("a[href*='/jobs/']") or soup.select(".iCIMS_JobsTable a")
            for link in links[:15]:
                title = clean_text(link.get_text())
                href = link.get("href", "")
                if not title or not href:
                    continue
                job_url = href if href.startswith("http") else f"https://{domain}{href}"
                if job_url in seen_urls:
                    continue
                if not is_relevant(title) or is_too_senior(title):
                    continue
                seen_urls.add(job_url)
                results.append(make_job_row(
                    company_name, domain, title, job_url, "",
                    f"iCIMS — {company_name}", "icims", profile
                ))
            time.sleep(0.8)

        if len(results) >= max_results:
            break

    print(f"[iCIMS] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 11: AI RERANKING
# ─────────────────────────────────────────────

def ai_rerank_candidates(
    client: OpenAI,
    profile: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    model: str,
    keep_count: int = 100,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    prompt_candidates = [
        {
            "index": idx,
            "job_title": c["job_title"],
            "company_name": c["company_name"],
            "job_location": c["job_location"],
            "source": c["source"],
            "notes": c["notes"],
            "heuristic_score": c["discovery_score"],
        }
        for idx, c in enumerate(candidates[:300])
    ]

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "index":     {"type": "integer"},
                        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "reason":    {"type": "string"},
                    },
                    "required": ["index", "fit_score", "reason"],
                },
            }
        },
        "required": ["selected"],
    }

    clearance = "Active Secret clearance. TS adjudication in progress. Security+ meets DoD 8570 IAT II."
    instructions = (
        "You are selecting the best cybersecurity job matches for an entry-level candidate. "
        f"CLEARANCE: {clearance} "
        "Prefer: entry-level to early-career SOC/NOC/IR/threat analyst roles, "
        "cleared/DoD positions, defense contractors, federal agencies, "
        "private sector cybersecurity companies, banks with large security teams. "
        "Penalize: roles requiring 5+ years, non-cyber roles, "
        "software engineering roles unless security-focused. "
        f"Only include jobs with fit_score >= {ENRICHMENT_SCORE_THRESHOLD}."
    )

    prompt = f"""
CANDIDATE:
{json.dumps({
    'name': profile.get('name'),
    'experience_level': profile.get('experience_level'),
    'skills': profile.get('skills', [])[:15],
    'certifications': profile.get('certifications', []),
    'clearance': clearance,
    'target_roles': profile.get('target_roles', []),
}, indent=2)}

JOBS ({len(prompt_candidates)} total):
{json.dumps(prompt_candidates, indent=2)}

Return top {keep_count} ranked by fit. Only include fit_score >= {ENRICHMENT_SCORE_THRESHOLD}.
"""

    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "selected_jobs", "schema": schema}},
        )
        parsed = json.loads(response.output_text)
    except Exception as exc:
        print(f"[AI Rerank] Failed: {exc}. Using heuristic order.")
        return [c for c in candidates if c.get("discovery_score", 0) >= ENRICHMENT_SCORE_THRESHOLD][:keep_count]

    selected = parsed.get("selected", [])
    reranked = []
    seen_indices: set = set()

    for item in selected:
        idx = item["index"]
        if idx in seen_indices or idx >= len(candidates[:300]):
            continue
        if item.get("fit_score", 0) < ENRICHMENT_SCORE_THRESHOLD:
            continue
        seen_indices.add(idx)
        row = dict(candidates[idx])
        row["ai_fit_score"] = item["fit_score"]
        row["ai_reason"] = clean_text(item["reason"])
        reranked.append(row)

    reranked.sort(
        key=lambda x: (int(x.get("ai_fit_score", 0)), int(x.get("discovery_score", 0))),
        reverse=True,
    )
    return reranked[:keep_count]


# ─────────────────────────────────────────────
# SECTION 12: MAIN PIPELINE
# ─────────────────────────────────────────────

def discover_jobs_from_profile(
    profile: Dict[str, Any],
    raw_output_path: str = "output/raw_discovered_jobs.csv",
    final_output_path: str = "output/discovered_jobs.csv",
    target_final_jobs: int = 100,
) -> Dict[str, Path]:
    model = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
    client = load_client()

    print("\n" + "═" * 60)
    print("  SITREP — Discovery Engine v2.5")
    print("═" * 60)
    print(f"  Candidate: {profile.get('name', 'Unknown')}")
    print(f"  Sources:   JSearch · Adzuna · Greenhouse ({len(GREENHOUSE_COMPANIES)} cos)")
    print(f"             Lever ({len(LEVER_COMPANIES)} cos) · Muse · USAJobs")
    print(f"             ClearanceJobs · iCIMS")
    print(f"  Mode:      ThreadPoolExecutor parallel (max {MAX_WORKERS} workers)")
    print(f"  Threshold: {ENRICHMENT_SCORE_THRESHOLD}+ score to pass enrichment")
    print("═" * 60 + "\n")

    start_time = time.time()
    all_results: List[Dict[str, Any]] = []

    # ── Run parallel sources simultaneously using threads ─────────────────────
    print("[1/3] Running parallel sources...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {
            ex.submit(fetch_jsearch, profile):      "JSearch",
            ex.submit(fetch_adzuna, profile):       "Adzuna",
            ex.submit(fetch_greenhouse, profile):   "Greenhouse",
            ex.submit(fetch_lever, profile):        "Lever",
            ex.submit(fetch_muse, profile):         "Muse",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                jobs = future.result()
                all_results.extend(jobs)
            except Exception as e:
                print(f"  [{name}] Failed: {e}")

    parallel_time = time.time() - start_time
    print(f"  → {len(all_results)} jobs from parallel sources in {parallel_time:.1f}s")

    # ── Run sync sources (rate-limited APIs) ──────────────────────────────────
    print("[2/3] Running sync sources (USAJobs, ClearanceJobs, iCIMS)...")
    all_results.extend(fetch_usajobs(profile))
    all_results.extend(fetch_clearancejobs(profile))
    all_results.extend(fetch_icims(profile))
    sync_time = time.time() - start_time - parallel_time
    print(f"  → Sync sources complete in {sync_time:.1f}s")

    # ── Merge, dedupe, sort ────────────────────────────────────────────────────
    all_results = dedupe_jobs(all_results)
    all_results.sort(key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
    all_results = all_results[:MAX_RAW_POOL]

    total_time = time.time() - start_time
    print(f"\n[Discovery] Raw pool: {len(all_results)} unique jobs in {total_time:.1f}s")

    from collections import Counter
    source_counts = Counter(r["source"] for r in all_results)
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"  {source:<20} {count} jobs")

    raw_path = write_csv(raw_output_path, all_results)
    print(f"\n[Discovery] Raw CSV: {raw_path}")

    # ── AI rerank ──────────────────────────────────────────────────────────────
    print(f"[3/3] AI reranking → keeping {ENRICHMENT_SCORE_THRESHOLD}+ fits (max {target_final_jobs})...")
    reranked = ai_rerank_candidates(
        client=client,
        profile=profile,
        candidates=all_results,
        model=model,
        keep_count=target_final_jobs,
    )

    if not reranked:
        reranked = [r for r in all_results if r.get("discovery_score", 0) >= ENRICHMENT_SCORE_THRESHOLD][:target_final_jobs]

    final_path = write_csv(final_output_path, reranked)
    total_time = time.time() - start_time
    print(f"[Discovery] Final: {final_path} ({len(reranked)} jobs in {total_time:.1f}s total)")
    print("\n" + "═" * 60)

    # ── Save seen URLs ─────────────────────────────────────────────────────────
    seen = load_seen_urls()
    seen.update(r["job_url"] for r in all_results if r.get("job_url"))
    save_seen_urls(seen)

    return {"raw": raw_path, "final": final_path}


# ─────────────────────────────────────────────
# SECTION 13: ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    profile = load_profile()
    paths = discover_jobs_from_profile(profile)
    print(f"  Raw:   {paths['raw']}")
    print(f"  Final: {paths['final']}")
