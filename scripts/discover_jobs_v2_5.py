"""
discover_jobs_v2_5.py
---------------------
Recruiter Recon AI — Job Discovery Engine v2.5

Changes from v2.4:
  - Full async/parallel architecture using aiohttp
    All sources fire concurrently — runtime cut from 15 min to under 3 min
  - JSearch API (RapidAPI) — hits LinkedIn, Indeed, Glassdoor, ZipRecruiter
    simultaneously via Google for Jobs aggregation
  - Adzuna API — aggregates 15+ job boards with full descriptions
  - Greenhouse company directory scraping — pulls verified company list
    instead of guessing slugs (fixes the 404 problem)
  - Lever company directory scraping — same approach
  - The Muse API — free, no key, tech/cyber company jobs with descriptions
  - USAJobs, ClearanceJobs, iCIMS remain as sync sources (rate limited APIs)
  - Delta detection groundwork — seen_urls persisted to output/seen_urls.json
"""

# ─────────────────────────────────────────────
# SECTION 1: IMPORTS & CONSTANTS
# ─────────────────────────────────────────────

import asyncio
import csv
import json
import os
import re
import time
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus, urlparse

import aiohttp
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── API credentials ────────────────────────────────────────────────────────────
USAJOBS_API_KEY     = os.getenv("USAJOBS_API_KEY", "").strip()
USAJOBS_USER_AGENT  = os.getenv("USAJOBS_USER_AGENT", "").strip()
JSEARCH_API_KEY     = os.getenv("JSEARCH_API_KEY", "").strip()
ADZUNA_APP_ID       = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY      = os.getenv("ADZUNA_APP_KEY", "").strip()

# ── Runtime config ─────────────────────────────────────────────────────────────
REQUEST_TIMEOUT     = 15
ASYNC_TIMEOUT       = aiohttp.ClientTimeout(total=15)
ENRICHMENT_SCORE_THRESHOLD = 50
MAX_RAW_POOL        = 600
SEEN_URLS_PATH      = Path("output/seen_urls.json")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ── Source priority ────────────────────────────────────────────────────────────
SOURCE_PRIORITY = {
    "usajobs":       95,
    "clearancejobs": 92,
    "jsearch":       88,
    "adzuna":        85,
    "greenhouse":    90,
    "lever":         90,
    "muse":          82,
    "workday":       88,
    "icims":         85,
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

# ── JSearch queries ────────────────────────────────────────────────────────────
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

# ── Adzuna queries ─────────────────────────────────────────────────────────────
ADZUNA_QUERIES = [
    "SOC analyst",
    "cybersecurity analyst",
    "incident response analyst",
    "network security analyst",
    "information security analyst",
    "cyber operations",
    "threat analyst",
    "vulnerability analyst",
    "SIEM analyst",
    "security engineer entry level",
]

# ── The Muse categories ────────────────────────────────────────────────────────
MUSE_CATEGORIES = [
    "IT", "Software Engineer", "Data Science", "DevOps", "Cybersecurity"
]

# ── USAJobs keywords ───────────────────────────────────────────────────────────
USAJOBS_KEYWORDS = [
    "cybersecurity analyst",
    "SOC analyst",
    "information security analyst",
    "network security",
    "incident response analyst",
    "cyber operations",
    "threat analyst",
    "vulnerability analyst",
    "security operations center",
    "cyber defense analyst",
    "computer network defense",
    "information systems security",
]

# ── iCIMS employers ────────────────────────────────────────────────────────────
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
        raise ValueError("OPENAI_API_KEY is missing in .env")
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


def score_heuristic(
    title: str,
    description: str,
    source: str,
    profile: Dict[str, Any],
) -> int:
    text = f"{title} {description}".lower()
    score = SOURCE_PRIORITY.get(source, 40)

    for kw in CYBER_KEYWORDS:
        if kw in text:
            score += 3

    if not is_too_senior(title):
        score += 12

    entry_terms = ["entry", "junior", "associate", "tier 1", "tier i",
                   "level i", "early career", "new grad", "analyst i"]
    if any(t in text for t in entry_terms):
        score += 10

    for role in profile.get("target_roles", []):
        if role.lower() in text:
            score += 10

    matched = sum(1 for s in profile.get("skills", [])[:20] if s.lower() in text)
    score += min(matched * 3, 24)

    clearance_rel = profile.get("clearance_relevance", "").lower()
    if "secret" in clearance_rel:
        if any(t in text for t in ["clearance", "secret", "top secret", "dod", "federal"]):
            score += 15

    if any(t in text for t in ["defense", "army", "dod", "federal", "critical infrastructure", "ics", "scada"]):
        score += 10

    return score


def make_job_row(
    company_name: str,
    company_domain: str,
    job_title: str,
    job_url: str,
    job_location: str,
    notes: str,
    source: str,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
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
    seen_company_title: set = set()
    deduped = []
    for row in rows:
        url = clean_text(row.get("job_url", "")).lower()
        company = clean_text(row.get("company_name", "")).lower()
        title = normalize_title(row.get("job_title", ""))
        ct_key = f"{company}||{title}"
        if url and url in seen_urls:
            continue
        if ct_key in seen_company_title:
            continue
        if url:
            seen_urls.add(url)
        seen_company_title.add(ct_key)
        deduped.append(row)
    return deduped


# ─────────────────────────────────────────────
# SECTION 3: ASYNC HTTP HELPERS
# ─────────────────────────────────────────────

async def async_get_json(
    session: aiohttp.ClientSession,
    url: str,
    headers: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Optional[Dict]:
    try:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return None
    except Exception:
        return None


async def async_get_text(
    session: aiohttp.ClientSession,
    url: str,
    headers: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Optional[str]:
    try:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 200:
                return await resp.text()
            return None
    except Exception:
        return None


# ─────────────────────────────────────────────
# SECTION 4: JSEARCH API (async)
# ─────────────────────────────────────────────

async def fetch_jsearch_query(
    session: aiohttp.ClientSession,
    query: str,
    location: str,
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
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

    data = await async_get_json(session, "https://jsearch.p.rapidapi.com/search", headers=headers, params=params)
    if not data:
        return []

    results = []
    for job in data.get("data", []):
        title = clean_text(job.get("job_title", ""))
        company = clean_text(job.get("employer_name", ""))
        job_url = clean_text(job.get("job_apply_link", "") or job.get("job_google_link", ""))
        loc = clean_text(f"{job.get('job_city','')}, {job.get('job_state','')}".strip(", "))
        description = clean_text(job.get("job_description", ""))[:300]
        domain = clean_text(job.get("employer_website", "")).replace("https://","").replace("http://","").split("/")[0]

        if not title or not job_url:
            continue
        if not is_relevant(title, description) or is_too_senior(title):
            continue

        results.append(make_job_row(
            company_name=company,
            company_domain=domain,
            job_title=title,
            job_url=job_url,
            job_location=loc or location,
            notes=description,
            source="jsearch",
            profile=profile,
        ))

    return results


async def fetch_jsearch_all(
    profile: Dict[str, Any],
    max_results: int = 200,
) -> List[Dict[str, Any]]:
    if not JSEARCH_API_KEY:
        print("[JSearch] Skipping — JSEARCH_API_KEY not configured.")
        return []

    locations = profile.get("location_preferences", ["Tampa, FL"])[:2] + ["Remote", "United States"]
    results = []
    seen_urls: set = set()

    async with aiohttp.ClientSession(timeout=ASYNC_TIMEOUT) as session:
        tasks = []
        for query in JSEARCH_QUERIES[:8]:
            for location in locations[:3]:
                tasks.append(fetch_jsearch_query(session, query, location, profile))

        batches = await asyncio.gather(*tasks, return_exceptions=True)

        for batch in batches:
            if isinstance(batch, Exception) or not batch:
                continue
            for job in batch:
                url = job.get("job_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append(job)

    print(f"[JSearch] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 5: ADZUNA API (async)
# ─────────────────────────────────────────────

async def fetch_adzuna_query(
    session: aiohttp.ClientSession,
    query: str,
    location: str,
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []

    # Adzuna location mapping
    loc_map = {
        "Tampa, FL": "florida",
        "Florida": "florida",
        "Remote": "",
        "United States": "",
        "Virginia": "virginia",
        "Texas": "texas",
    }
    adzuna_loc = loc_map.get(location, "")

    base_url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": 20,
        "what": query,
        "content-type": "application/json",
        "sort_by": "date",
    }
    if adzuna_loc:
        params["where"] = adzuna_loc

    data = await async_get_json(session, base_url, params=params)
    if not data:
        return []

    results = []
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

        results.append(make_job_row(
            company_name=company,
            company_domain="",
            job_title=title,
            job_url=job_url,
            job_location=loc_str or location,
            notes=description,
            source="adzuna",
            profile=profile,
        ))

    return results


async def fetch_adzuna_all(
    profile: Dict[str, Any],
    max_results: int = 200,
) -> List[Dict[str, Any]]:
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("[Adzuna] Skipping — ADZUNA_APP_ID or ADZUNA_APP_KEY not configured.")
        return []

    locations = profile.get("location_preferences", ["Tampa, FL"])[:2] + ["Remote", "United States"]
    results = []
    seen_urls: set = set()

    async with aiohttp.ClientSession(timeout=ASYNC_TIMEOUT) as session:
        tasks = []
        for query in ADZUNA_QUERIES[:8]:
            for location in locations[:3]:
                tasks.append(fetch_adzuna_query(session, query, location, profile))

        batches = await asyncio.gather(*tasks, return_exceptions=True)

        for batch in batches:
            if isinstance(batch, Exception) or not batch:
                continue
            for job in batch:
                url = job.get("job_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append(job)

    print(f"[Adzuna] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 6: GREENHOUSE DIRECTORY (async)
# ─────────────────────────────────────────────

async def fetch_greenhouse_company_list(
    session: aiohttp.ClientSession,
) -> List[str]:
    """
    Scrape Greenhouse's public company directory to get verified slugs.
    Much better than guessing — returns hundreds of real company boards.
    """
    slugs = []

    # Greenhouse publishes a sitemap we can use
    sitemap_url = "https://boards.greenhouse.io/sitemap.xml"
    text = await async_get_text(session, sitemap_url)

    if text:
        # Extract company slugs from sitemap URLs
        matches = re.findall(r'boards\.greenhouse\.io/([a-zA-Z0-9_-]+)', text)
        # Filter for likely cybersecurity/tech companies
        cyber_hints = [
            "security", "cyber", "defense", "intelligence", "tech", "data",
            "cloud", "network", "system", "digital", "software", "engineer",
            "capital", "bank", "financial", "health", "energy", "federal",
        ]
        # Return all unique slugs — we'll filter by job title relevance later
        slugs = list(set(matches))[:300]

    if not slugs:
        # Fallback to our known good list
        slugs = [
            "crowdstrike", "sentinelone", "huntress", "expel", "redcanary",
            "blumira", "deepwatch", "threatlocker", "recordedfuture", "flashpoint",
            "dragos", "claroty", "vectra", "exabeam", "anomali", "cybereason",
            "coalfire", "optiv", "guidepoint", "trustwave", "secureworks",
            "rapid7", "tenable", "qualys", "beyondtrust", "cyberark",
            "sailpoint", "okta", "delinea", "paloaltonetworks", "fortinet",
            "capitalone", "stripe", "palantir", "anduril", "govini",
            "deloitte", "accenture", "ibm", "microsoft", "google",
        ]

    return slugs


async def fetch_greenhouse_jobs_for_company(
    session: aiohttp.ClientSession,
    slug: str,
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    data = await async_get_json(session, url)
    if not data:
        return []

    results = []
    for job in data.get("jobs", []):
        title = clean_text(job.get("title", ""))
        job_url = clean_text(job.get("absolute_url", ""))
        location = clean_text((job.get("location") or {}).get("name", ""))

        if not title or not job_url:
            continue
        if not is_relevant(title) or is_too_senior(title):
            continue

        results.append(make_job_row(
            company_name=slug.replace("-", " ").title(),
            company_domain=f"{slug}.com",
            job_title=title,
            job_url=job_url,
            job_location=location,
            notes=f"Greenhouse — {slug}",
            source="greenhouse",
            profile=profile,
        ))

    return results


async def fetch_greenhouse_all(
    profile: Dict[str, Any],
    max_results: int = 300,
) -> List[Dict[str, Any]]:
    async with aiohttp.ClientSession(timeout=ASYNC_TIMEOUT) as session:
        slugs = await fetch_greenhouse_company_list(session)
        print(f"[Greenhouse] Querying {len(slugs)} company boards in parallel...")

        tasks = [fetch_greenhouse_jobs_for_company(session, slug, profile) for slug in slugs]
        batches = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        seen_urls: set = set()
        for batch in batches:
            if isinstance(batch, Exception) or not batch:
                continue
            for job in batch:
                url = job.get("job_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append(job)

    print(f"[Greenhouse] {len(results)} postings found across {len(slugs)} companies")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 7: LEVER DIRECTORY (async)
# ─────────────────────────────────────────────

async def fetch_lever_jobs_for_company(
    session: aiohttp.ClientSession,
    slug: str,
    profile: Dict[str, Any],
) -> List[Dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = await async_get_json(session, url)
    if not data or not isinstance(data, list):
        return []

    results = []
    for job in data:
        title = clean_text(job.get("text", ""))
        job_url = clean_text(job.get("hostedUrl", ""))
        categories = job.get("categories", {})
        location = clean_text(categories.get("location", ""))
        description = strip_html(job.get("descriptionPlain", "") or "")

        if not title or not job_url:
            continue
        if not is_relevant(title, description) or is_too_senior(title):
            continue

        results.append(make_job_row(
            company_name=slug.replace("-", " ").title(),
            company_domain=f"{slug}.com",
            job_title=title,
            job_url=job_url,
            job_location=location,
            notes=description[:300],
            source="lever",
            profile=profile,
        ))

    return results


async def fetch_lever_all(
    profile: Dict[str, Any],
    max_results: int = 300,
) -> List[Dict[str, Any]]:
    # Expanded Lever company list
    lever_companies = [
        "palantir", "anduril", "shield-ai", "rebellion-defense", "scale-ai",
        "primer", "govini", "c3-ai", "crowdstrike", "huntress", "expel",
        "redcanary", "blumira", "lumu", "ncc-group", "bishopfox",
        "abnormal-security", "material-security", "cofense", "ironscales",
        "cloudflare", "datadog", "elastic", "lacework", "wiz",
        "capitalone", "stripe", "brex", "plaid", "robinhood", "coinbase",
        "oscar-health", "deloitte", "boozallen", "telos",
        "flare-systems", "securin", "veriti", "revelstoke", "torq",
        "intsights", "cybersixgill", "deepinstinct", "axonius",
        "sevenzero", "infosec", "techdata", "verizon-business",
        "microsoft", "google", "amazon", "apple", "meta", "ibm",
    ]

    async with aiohttp.ClientSession(timeout=ASYNC_TIMEOUT) as session:
        print(f"[Lever] Querying {len(lever_companies)} company boards in parallel...")
        tasks = [fetch_lever_jobs_for_company(session, slug, profile) for slug in lever_companies]
        batches = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        seen_urls: set = set()
        for batch in batches:
            if isinstance(batch, Exception) or not batch:
                continue
            for job in batch:
                url = job.get("job_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append(job)

    print(f"[Lever] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 8: THE MUSE API (async, free, no key)
# ─────────────────────────────────────────────

async def fetch_muse_all(
    profile: Dict[str, Any],
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """
    The Muse public API — free, no auth, tech/cyber company jobs with descriptions.
    """
    results = []
    seen_urls: set = set()

    async with aiohttp.ClientSession(timeout=ASYNC_TIMEOUT) as session:
        tasks = []
        for category in MUSE_CATEGORIES:
            for page in range(1, 4):
                url = f"https://www.themuse.com/api/public/jobs?category={quote_plus(category)}&page={page}&descending=true"
                tasks.append(async_get_json(session, url))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for data in responses:
            if isinstance(data, Exception) or not data:
                continue
            for job in data.get("results", []):
                title = clean_text(job.get("name", ""))
                company = clean_text((job.get("company") or {}).get("name", ""))
                job_url = clean_text(job.get("refs", {}).get("landing_page", ""))
                locations = job.get("locations", [{}])
                location = clean_text(locations[0].get("name", "")) if locations else ""
                contents = job.get("contents", "")
                description = strip_html(contents)[:300]

                if not title or not job_url or job_url in seen_urls:
                    continue
                if not is_relevant(title, description) or is_too_senior(title):
                    continue

                seen_urls.add(job_url)
                results.append(make_job_row(
                    company_name=company,
                    company_domain="",
                    job_title=title,
                    job_url=job_url,
                    job_location=location,
                    notes=description,
                    source="muse",
                    profile=profile,
                ))

    print(f"[The Muse] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 9: USAJOBS API (sync — rate limited)
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
                    headers=headers,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
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
                    company_name=org,
                    company_domain="usajobs.gov",
                    job_title=title,
                    job_url=url,
                    job_location=loc_str,
                    notes=f"{quals[:200]} {pay}".strip(),
                    source="usajobs",
                    profile=profile,
                ))

            time.sleep(0.3)

        if len(results) >= max_results:
            break

    print(f"[USAJobs] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 10: CLEARANCEJOBS RSS (sync)
# ─────────────────────────────────────────────

def fetch_clearancejobs(profile: Dict[str, Any], max_results: int = 100) -> List[Dict[str, Any]]:
    cleared_queries = [
        "SOC analyst Secret clearance",
        "cybersecurity analyst Secret",
        "incident response Secret clearance",
        "network security analyst clearance",
        "cyber operations Secret TS",
        "information security analyst DoD",
        "SIEM analyst clearance",
        "threat analyst Secret",
    ]
    locations = profile.get("location_preferences", ["Tampa, FL"])[:3] + ["Remote"]
    results = []
    seen_urls: set = set()

    for query in cleared_queries:
        for location in locations[:2]:
            try:
                resp = requests.get(
                    "https://www.clearancejobs.com/jobs/rss",
                    params={"q": query, "l": location, "sort": "date"},
                    headers={"User-Agent": USER_AGENT},
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
                    company_name=company,
                    company_domain=normalized_hostname(job_url),
                    job_title=title,
                    job_url=job_url,
                    job_location=location,
                    notes=description[:300],
                    source="clearancejobs",
                    profile=profile,
                ))

            time.sleep(1.0)

        if len(results) >= max_results:
            break

    print(f"[ClearanceJobs] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 11: iCIMS (sync)
# ─────────────────────────────────────────────

def fetch_icims(profile: Dict[str, Any], max_results: int = 75) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()
    keywords = ["cybersecurity", "SOC analyst", "security analyst"]

    for slug, domain, company_name in ICIMS_COMPANIES:
        for keyword in keywords[:2]:
            try:
                resp = requests.get(
                    f"https://{domain}/jobs/search?q={quote_plus(keyword)}",
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
            except Exception:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            job_links = soup.select("a[href*='/jobs/']") or soup.select(".iCIMS_JobsTable a")

            for link in job_links[:15]:
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
                    company_name=company_name,
                    company_domain=domain,
                    job_title=title,
                    job_url=job_url,
                    job_location="",
                    notes=f"iCIMS — {company_name}",
                    source="icims",
                    profile=profile,
                ))

            time.sleep(random.uniform(0.5, 1.5))

        if len(results) >= max_results:
            break

    print(f"[iCIMS] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 12: AI RERANKING
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
        "You are selecting the best cybersecurity job matches for a candidate. "
        f"CLEARANCE: {clearance} "
        "Prefer: entry-level to early-career SOC/NOC/IR/threat analyst roles, "
        "cleared/DoD positions, defense contractors, federal agencies, "
        "private sector cybersecurity companies, banks with large security teams. "
        "Penalize: roles requiring 5+ years, non-cyber roles, software engineering "
        "roles unless security-focused, roles clearly outside candidate background. "
        "Score conservatively. Only score 50+ for genuine matches."
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

Return top {keep_count} ranked by fit. Only include jobs with fit_score >= {ENRICHMENT_SCORE_THRESHOLD}.
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
# SECTION 13: MAIN PIPELINE
# ─────────────────────────────────────────────

async def run_async_sources(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run all async sources concurrently."""
    print("[Discovery] Launching async sources in parallel...")

    results = await asyncio.gather(
        fetch_jsearch_all(profile),
        fetch_adzuna_all(profile),
        fetch_greenhouse_all(profile),
        fetch_lever_all(profile),
        fetch_muse_all(profile),
        return_exceptions=True,
    )

    all_jobs = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  [Async] Source failed: {r}")
            continue
        all_jobs.extend(r)

    return all_jobs


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
    print(f"  Sources:   JSearch · Adzuna · Greenhouse · Lever · Muse")
    print(f"             USAJobs · ClearanceJobs · iCIMS")
    print(f"  Mode:      Async parallel (all sources fire simultaneously)")
    print(f"  Threshold: {ENRICHMENT_SCORE_THRESHOLD}+ score to pass enrichment")
    print("═" * 60 + "\n")

    start_time = time.time()

    # ── Run async sources in parallel ─────────────────────────────────────────
    print("[1/3] Running async sources (JSearch, Adzuna, Greenhouse, Lever, Muse)...")
    async_jobs = asyncio.run(run_async_sources(profile))
    async_time = time.time() - start_time
    print(f"  → {len(async_jobs)} jobs from async sources in {async_time:.1f}s")

    # ── Run sync sources (rate-limited APIs) ──────────────────────────────────
    print("[2/3] Running sync sources (USAJobs, ClearanceJobs, iCIMS)...")
    sync_jobs = []
    sync_jobs.extend(fetch_usajobs(profile))
    sync_jobs.extend(fetch_clearancejobs(profile))
    sync_jobs.extend(fetch_icims(profile))
    sync_time = time.time() - start_time - async_time
    print(f"  → {len(sync_jobs)} jobs from sync sources in {sync_time:.1f}s")

    # ── Merge, dedupe, sort ────────────────────────────────────────────────────
    all_results = async_jobs + sync_jobs
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
    print(f"[Discovery] Final CSV: {final_path} ({len(reranked)} jobs)")
    print(f"[Discovery] Total runtime: {total_time:.1f}s ({total_time/60:.1f} min)")
    print("\n" + "═" * 60)

    # ── Save seen URLs for delta detection ─────────────────────────────────────
    seen = load_seen_urls()
    new_urls = {r["job_url"] for r in all_results if r.get("job_url")}
    seen.update(new_urls)
    save_seen_urls(seen)

    return {"raw": raw_path, "final": final_path}


# ─────────────────────────────────────────────
# SECTION 14: ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    profile = load_profile()
    paths = discover_jobs_from_profile(profile)
    print(f"  Raw:   {paths['raw']}")
    print(f"  Final: {paths['final']}")
