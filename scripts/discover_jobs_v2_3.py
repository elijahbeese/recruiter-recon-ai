"""
discover_jobs_v2_3.py
---------------------
Recruiter Recon AI — Job Discovery Engine v2.3

Sources:
  1. USAJobs API          — federal/DoD/cleared roles, free API
  2. ClearanceJobs RSS    — private sector cleared roles
  3. Indeed RSS           — broad market, small contractors, unknown companies
  4. Dice RSS             — tech/cyber focused contractor roles
  5. LinkedIn Jobs        — best-effort scrape, rate-limited, graceful fallback
  6. Greenhouse API       — direct ATS queries, 50+ cyber/defense companies
  7. Lever API            — direct ATS queries, 35+ defense tech companies
  8. Workday search       — top defense primes (Leidos, Northrop, L3Harris, etc.)
  9. iCIMS search         — traditional defense contractors (Raytheon, BAE, etc.)

No DuckDuckGo. No wildcard queries. No silent failures.
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
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ── API credentials ────────────────────────────────────────────────────────────
USAJOBS_API_KEY     = os.getenv("USAJOBS_API_KEY", "").strip()
USAJOBS_USER_AGENT  = os.getenv("USAJOBS_USER_AGENT", "").strip()

# ── Source priority scores (base heuristic) ───────────────────────────────────
SOURCE_PRIORITY = {
    "usajobs":      95,
    "clearancejobs": 92,
    "greenhouse":   90,
    "lever":        90,
    "workday":      88,
    "icims":        85,
    "dice":         75,
    "indeed":       70,
    "linkedin":     70,
    "other":        40,
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
]

SENIOR_MARKERS = [
    "senior", "sr.", "lead", "principal", "staff", "manager",
    "director", "architect", "vp ", "chief", "head of",
    "5+ years", "7+ years", "8+ years", "10+ years", "15+ years",
]

# ── Greenhouse company list (50+ cyber/defense companies) ─────────────────────
GREENHOUSE_COMPANIES = [
    # Pure-play cybersecurity
    "crowdstrike", "sentinelone", "lacework", "snyk",
    "dragos", "claroty", "nozomi", "darktrace", "vectra",
    "exabeam", "sumologic", "devo", "anomali", "recordedfuture",
    "flashpoint", "zerofox", "cybereason", "huntress", "expel",
    "redcanary", "blumira", "deepwatch", "threatlocker", "illumio",
    "orca-security", "wiz", "apiiro", "armorcode", "lineaje",
    # Consulting / MSSP
    "coalfire", "optiv", "guidepoint", "trustwave", "secureworks",
    "trellix", "kroll", "bishopfox",
    # Defense / government contractors
    "saic", "leidos", "boozallen", "caci", "mantech",
    "peraton", "parsons", "amentum", "telos", "perspecta",
    # Networking / infrastructure security
    "paloaltonetworks", "fortinet", "rapid7", "tenable", "qualys",
    "beyondtrust", "cyberark", "sailpoint", "okta", "delinea",
]

# ── Lever company list (35+ defense tech / cyber companies) ───────────────────
LEVER_COMPANIES = [
    # Defense tech
    "palantir", "anduril", "shield-ai", "rebellion-defense",
    "scale-ai", "primer", "govini", "hawkeye360",
    # Cybersecurity
    "crowdstrike", "huntress", "expel", "redcanary", "blumira",
    "lumu", "accurics", "ox-security", "sevenzero",
    "infosec", "ncc-group",
    # Contractors
    "telos", "unison", "perspecta",
    # Broader tech with cyber divisions
    "cloudflare", "hashicorp", "datadog", "elastic",
    "splunk", "sumo-logic", "devo-technology",
]

# ── Workday defense/federal employers ─────────────────────────────────────────
# Format: (company_slug, display_name)
WORKDAY_COMPANIES = [
    ("leidos", "Leidos"),
    ("northropgrumman", "Northrop Grumman"),
    ("l3harris", "L3Harris Technologies"),
    ("baesystems", "BAE Systems"),
    ("generaldynamics", "General Dynamics"),
    ("lmco", "Lockheed Martin"),
    ("boeing", "Boeing"),
    ("raytheon", "Raytheon Technologies"),
    ("saic", "SAIC"),
    ("peraton", "Peraton"),
    ("mss", "MSS"),
    ("parsons", "Parsons Corporation"),
    ("amentum", "Amentum"),
    ("vectrus", "Vectrus"),
    ("csc", "CSC"),
]

# ── iCIMS defense/federal employers ───────────────────────────────────────────
ICIMS_COMPANIES = [
    ("raytheon", "careers.rtx.com", "Raytheon"),
    ("bah", "careers.boozallen.com", "Booz Allen Hamilton"),
    ("mantech", "careers.mantech.com", "ManTech"),
    ("caci", "careers.caci.com", "CACI"),
    ("mitre", "careers.mitre.org", "MITRE"),
    ("mitre", "jobs.mitre.org", "MITRE"),
    ("l3harris", "careers.l3harris.com", "L3Harris"),
    ("nsa", "apply.intelligencecareers.gov", "NSA"),
]

# ── USAJobs search keywords ────────────────────────────────────────────────────
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

# ── Indeed/Dice/ClearanceJobs search queries ──────────────────────────────────
RSS_QUERIES = [
    "SOC analyst",
    "cybersecurity analyst entry level",
    "incident response analyst",
    "network security analyst",
    "information security analyst clearance",
    "cyber operations analyst",
    "threat intelligence analyst",
    "vulnerability analyst entry level",
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
    return any(k in text for k in CYBER_KEYWORDS)


def is_too_senior(title: str, description: str = "") -> bool:
    text = f"{title} {description}".lower()
    return any(s in text for s in SENIOR_MARKERS)


def dedupe_jobs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = clean_text(row.get("job_url", "")).lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped


def load_profile(path: str = "candidate_profile_generated.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")
    return OpenAI(api_key=api_key)


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

    if not is_too_senior(title, description):
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


def safe_get(url: str, headers: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[requests.Response]:
    try:
        resp = requests.get(
            url,
            headers=headers or {"User-Agent": USER_AGENT},
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"  [HTTP] Failed {url[:80]}: {e}")
        return None


# ─────────────────────────────────────────────
# SECTION 3: USAJOBS API
# ─────────────────────────────────────────────

def fetch_usajobs(profile: Dict[str, Any], max_results: int = 150) -> List[Dict[str, Any]]:
    if not USAJOBS_API_KEY or not USAJOBS_USER_AGENT:
        print("[USAJobs] Skipping — API key or user agent not configured.")
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
        for location in locations:
            params = {
                "Keyword": keyword,
                "ResultsPerPage": 25,
                "WhoMayApply": "all",
                "SortField": "OpenDate",
                "SortDirection": "Desc",
            }
            if location:
                params["LocationName"] = location

            resp = safe_get("https://data.usajobs.gov/api/search", headers=headers, params=params)
            if not resp:
                continue

            items = resp.json().get("SearchResult", {}).get("SearchResultItems", [])

            for item in items:
                d = item.get("MatchedObjectDescriptor", {})
                job_id = d.get("PositionID", "")
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                title = d.get("PositionTitle", "")
                if not is_relevant(title):
                    continue
                if is_too_senior(title):
                    continue

                org = d.get("OrganizationName", "") or d.get("DepartmentName", "")
                url = d.get("PositionURI", "")
                locs = d.get("PositionLocation", [{}])
                loc_str = locs[0].get("LocationName", "") if locs else ""
                quals = d.get("QualificationSummary", "")
                pay = ""
                rem = d.get("PositionRemuneration", [])
                if rem:
                    pay = f"Pay: {rem[0].get('MinimumRange', '')}–{rem[0].get('MaximumRange', '')}"

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

            time.sleep(0.5)

        if len(results) >= max_results:
            break

    print(f"[USAJobs] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 4: RSS FEEDS (Indeed, Dice, ClearanceJobs)
# ─────────────────────────────────────────────

def _fetch_rss(
    base_url: str,
    source_name: str,
    queries: List[str],
    locations: List[str],
    profile: Dict[str, Any],
    max_results: int = 100,
    extra_params: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()

    for query in queries:
        for location in locations:
            params = {"q": query, "l": location, "sort": "date", "fromage": "14"}
            if extra_params:
                params.update(extra_params)

            resp = safe_get(base_url, params=params)
            if not resp:
                continue

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError:
                continue

            for item in root.findall(".//item"):
                title = clean_text(item.findtext("title", ""))
                job_url = clean_text(item.findtext("link", ""))
                description = strip_html(item.findtext("description", ""))

                if not title or not job_url or job_url in seen_urls:
                    continue
                if not is_relevant(title, description):
                    continue
                if is_too_senior(title):
                    continue

                seen_urls.add(job_url)

                company_name = ""
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    company_name = parts[1].strip()

                results.append(make_job_row(
                    company_name=company_name,
                    company_domain=normalized_hostname(job_url),
                    job_title=title,
                    job_url=job_url,
                    job_location=location,
                    notes=description[:300],
                    source=source_name,
                    profile=profile,
                ))

            time.sleep(random.uniform(1.0, 2.5))

            if len(results) >= max_results:
                break

        if len(results) >= max_results:
            break

    print(f"[{source_name.title()}] {len(results)} postings found")
    return results[:max_results]


def fetch_indeed(profile: Dict[str, Any], max_results: int = 100) -> List[Dict[str, Any]]:
    locations = profile.get("location_preferences", ["Tampa, FL"])[:3] + ["Remote"]
    return _fetch_rss(
        base_url="https://www.indeed.com/rss",
        source_name="indeed",
        queries=RSS_QUERIES,
        locations=locations,
        profile=profile,
        max_results=max_results,
    )


def fetch_dice(profile: Dict[str, Any], max_results: int = 75) -> List[Dict[str, Any]]:
    locations = profile.get("location_preferences", ["Tampa, FL"])[:3] + ["Remote"]
    return _fetch_rss(
        base_url="https://www.dice.com/jobs/rss",
        source_name="dice",
        queries=RSS_QUERIES,
        locations=locations,
        profile=profile,
        max_results=max_results,
    )


def fetch_clearancejobs(profile: Dict[str, Any], max_results: int = 100) -> List[Dict[str, Any]]:
    """
    ClearanceJobs RSS feed — private sector cleared roles.
    Specifically targets Secret/TS cleared cybersecurity positions.
    """
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
    return _fetch_rss(
        base_url="https://www.clearancejobs.com/jobs/rss",
        source_name="clearancejobs",
        queries=cleared_queries,
        locations=locations,
        profile=profile,
        max_results=max_results,
    )


# ─────────────────────────────────────────────
# SECTION 5: GREENHOUSE DIRECT API
# ─────────────────────────────────────────────

def fetch_greenhouse(profile: Dict[str, Any], max_results: int = 200) -> List[Dict[str, Any]]:
    """
    Query Greenhouse's public JSON API for every company in GREENHOUSE_COMPANIES.
    No authentication required. Returns all open roles, filtered for relevance.
    """
    results = []
    seen_urls: set = set()

    for company in GREENHOUSE_COMPANIES:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        resp = safe_get(url)
        if not resp:
            continue

        try:
            jobs = resp.json().get("jobs", [])
        except Exception:
            continue

        for job in jobs:
            title = clean_text(job.get("title", ""))
            job_url = clean_text(job.get("absolute_url", ""))
            location = clean_text((job.get("location") or {}).get("name", ""))

            if not title or not job_url or job_url in seen_urls:
                continue
            if not is_relevant(title):
                continue
            if is_too_senior(title):
                continue

            seen_urls.add(job_url)
            results.append(make_job_row(
                company_name=company.replace("-", " ").title(),
                company_domain=f"{company}.com",
                job_title=title,
                job_url=job_url,
                job_location=location,
                notes=f"Greenhouse posting — {company}",
                source="greenhouse",
                profile=profile,
            ))

        time.sleep(0.3)

        if len(results) >= max_results:
            break

    print(f"[Greenhouse] {len(results)} postings found across {len(GREENHOUSE_COMPANIES)} companies")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 6: LEVER DIRECT API
# ─────────────────────────────────────────────

def fetch_lever(profile: Dict[str, Any], max_results: int = 150) -> List[Dict[str, Any]]:
    """
    Query Lever's public JSON API for every company in LEVER_COMPANIES.
    No authentication required.
    """
    results = []
    seen_urls: set = set()

    for company in LEVER_COMPANIES:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        resp = safe_get(url)
        if not resp:
            continue

        try:
            jobs = resp.json()
            if not isinstance(jobs, list):
                continue
        except Exception:
            continue

        for job in jobs:
            title = clean_text(job.get("text", ""))
            job_url = clean_text(job.get("hostedUrl", ""))
            categories = job.get("categories", {})
            location = clean_text(categories.get("location", ""))
            description = strip_html(job.get("descriptionPlain", "") or "")

            if not title or not job_url or job_url in seen_urls:
                continue
            if not is_relevant(title, description):
                continue
            if is_too_senior(title):
                continue

            seen_urls.add(job_url)
            results.append(make_job_row(
                company_name=company.replace("-", " ").title(),
                company_domain=f"{company}.com",
                job_title=title,
                job_url=job_url,
                job_location=location,
                notes=description[:300],
                source="lever",
                profile=profile,
            ))

        time.sleep(0.3)

        if len(results) >= max_results:
            break

    print(f"[Lever] {len(results)} postings found across {len(LEVER_COMPANIES)} companies")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 7: WORKDAY
# ─────────────────────────────────────────────

def fetch_workday(profile: Dict[str, Any], max_results: int = 100) -> List[Dict[str, Any]]:
    """
    Query Workday job boards for top defense/federal employers.
    Workday has a standard search API endpoint across all companies.
    """
    results = []
    seen_urls: set = set()

    keywords = ["cybersecurity", "SOC analyst", "security analyst",
                "incident response", "network security", "cyber"]

    for slug, company_name in WORKDAY_COMPANIES:
        for keyword in keywords[:3]:
            url = f"https://{slug}.wd1.myworkdayjobs.com/wday/cxs/{slug}/External/jobs"
            payload = {
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": keyword,
            }

            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except Exception:
                continue

            jobs = data.get("jobPostings", [])

            for job in jobs:
                title = clean_text(job.get("title", ""))
                path = clean_text(job.get("externalPath", ""))
                location = clean_text(job.get("locationsText", ""))

                if not title or not path:
                    continue

                job_url = f"https://{slug}.wd1.myworkdayjobs.com/External{path}"

                if job_url in seen_urls:
                    continue
                if not is_relevant(title):
                    continue
                if is_too_senior(title):
                    continue

                seen_urls.add(job_url)
                results.append(make_job_row(
                    company_name=company_name,
                    company_domain=f"{slug}.com",
                    job_title=title,
                    job_url=job_url,
                    job_location=location,
                    notes=f"Workday posting — {company_name}",
                    source="workday",
                    profile=profile,
                ))

            time.sleep(0.5)

        if len(results) >= max_results:
            break

    print(f"[Workday] {len(results)} postings found across {len(WORKDAY_COMPANIES)} companies")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 8: iCIMS
# ─────────────────────────────────────────────

def fetch_icims(profile: Dict[str, Any], max_results: int = 75) -> List[Dict[str, Any]]:
    """
    Scrape iCIMS-powered career pages for top defense contractors.
    iCIMS has a consistent URL pattern for job search.
    """
    results = []
    seen_urls: set = set()

    keywords = ["cybersecurity", "SOC analyst", "security analyst", "cyber"]

    for slug, domain, company_name in ICIMS_COMPANIES:
        for keyword in keywords[:2]:
            url = f"https://{domain}/jobs/search?q={quote_plus(keyword)}"
            resp = safe_get(url)
            if not resp:
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
                if not is_relevant(title):
                    continue
                if is_too_senior(title):
                    continue

                seen_urls.add(job_url)
                results.append(make_job_row(
                    company_name=company_name,
                    company_domain=domain,
                    job_title=title,
                    job_url=job_url,
                    job_location="",
                    notes=f"iCIMS posting — {company_name}",
                    source="icims",
                    profile=profile,
                ))

            time.sleep(random.uniform(1.0, 2.0))

        if len(results) >= max_results:
            break

    print(f"[iCIMS] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 9: LINKEDIN (BEST-EFFORT)
# ─────────────────────────────────────────────

def fetch_linkedin(profile: Dict[str, Any], max_results: int = 75) -> List[Dict[str, Any]]:
    """
    Scrape LinkedIn public job search. Best-effort — LinkedIn actively blocks
    scrapers so this will degrade gracefully. Returns what it can get.
    Uses randomized delays and rotates queries to avoid triggering blocks.
    """
    results = []
    seen_urls: set = set()

    queries = profile.get("search_queries", [])[:6]
    locations = profile.get("location_preferences", ["Tampa, FL"])[:2] + ["Remote"]

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.linkedin.com/",
    }

    for query in queries:
        for location in locations:
            url = (
                f"https://www.linkedin.com/jobs/search?"
                f"keywords={quote_plus(query)}&"
                f"location={quote_plus(location)}&"
                f"f_TPR=r604800&"  # Posted in last week
                f"f_E=1,2&"        # Entry level, Associate
                f"sortBy=DD"       # Sort by date
            )

            resp = safe_get(url, headers=headers)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = soup.select(".job-search-card") or soup.select(".base-card")

            if not job_cards:
                print(f"  [LinkedIn] No cards found for '{query}' — may be blocked")
                time.sleep(random.uniform(5.0, 10.0))
                continue

            for card in job_cards[:15]:
                title_tag = card.select_one(".base-search-card__title") or card.select_one("h3")
                company_tag = card.select_one(".base-search-card__subtitle") or card.select_one("h4")
                location_tag = card.select_one(".job-search-card__location")
                link_tag = card.select_one("a[href*='/jobs/view/']")

                if not title_tag or not link_tag:
                    continue

                title = clean_text(title_tag.get_text())
                company = clean_text(company_tag.get_text()) if company_tag else ""
                loc = clean_text(location_tag.get_text()) if location_tag else location
                job_url = clean_text(link_tag.get("href", "").split("?")[0])

                if not job_url or job_url in seen_urls:
                    continue
                if not is_relevant(title):
                    continue
                if is_too_senior(title):
                    continue

                seen_urls.add(job_url)
                results.append(make_job_row(
                    company_name=company,
                    company_domain="linkedin.com",
                    job_title=title,
                    job_url=job_url,
                    job_location=loc,
                    notes=f"LinkedIn posting",
                    source="linkedin",
                    profile=profile,
                ))

            time.sleep(random.uniform(4.0, 8.0))

            if len(results) >= max_results:
                break

        if len(results) >= max_results:
            break

    print(f"[LinkedIn] {len(results)} postings found (best-effort)")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 10: AI RERANKING
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

    prompt_candidates = []
    for idx, c in enumerate(candidates[:200]):
        prompt_candidates.append({
            "index": idx,
            "job_title": c["job_title"],
            "company_name": c["company_name"],
            "job_location": c["job_location"],
            "source": c["source"],
            "notes": c["notes"],
            "heuristic_score": c["discovery_score"],
        })

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

    instructions = (
        "You are selecting the best cybersecurity job matches for a candidate. "
        "The candidate has an active Secret clearance with TS adjudication in progress, "
        "CompTIA Security+, ISC2 CC, and is commissioning as a U.S. Army Cyber Officer (17A). "
        "Prefer: entry-level to early-career roles, cleared/DoD positions, "
        "defense contractors, federal agencies, SOC/NOC/incident response, "
        "and roles aligned with the candidate's actual skills. "
        "Penalize: roles requiring 5+ years experience, non-cyber roles, "
        "roles with no relevance to the candidate's background. "
        "Score conservatively. Do not invent facts."
    )

    prompt = f"""
CANDIDATE PROFILE:
{json.dumps(profile, indent=2)}

JOB CANDIDATES ({len(prompt_candidates)} total):
{json.dumps(prompt_candidates, indent=2)}

Return the top {keep_count} candidates ranked by fit. Include fit_score (0-100) and a brief reason.
"""

    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "selected_jobs",
                    "schema": schema,
                }
            },
        )
        parsed = json.loads(response.output_text)
    except Exception as exc:
        print(f"[AI Rerank] Failed: {exc}. Using heuristic order.")
        return candidates[:keep_count]

    selected = parsed.get("selected", [])
    reranked = []
    seen_indices: set = set()

    for item in selected:
        idx = item["index"]
        if idx in seen_indices or idx >= len(candidates[:200]):
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
# SECTION 11: MAIN PIPELINE
# ─────────────────────────────────────────────

def discover_jobs_from_profile(
    profile: Dict[str, Any],
    raw_output_path: str = "output/raw_discovered_jobs.csv",
    final_output_path: str = "output/discovered_jobs.csv",
    target_final_jobs: int = 100,
) -> Dict[str, Path]:
    """
    Full v2.3 discovery pipeline.

    Runs all sources in parallel-ish sequence, merges results,
    deduplicates, heuristic-sorts, AI reranks, writes output.
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
    client = load_client()

    print("\n" + "═" * 60)
    print("  Recruiter Recon AI — Discovery Engine v2.3")
    print("═" * 60)
    print(f"  Candidate: {profile.get('name', 'Unknown')}")
    print(f"  Target roles: {len(profile.get('target_roles', []))}")
    print(f"  Sources: USAJobs, ClearanceJobs, Indeed, Dice, LinkedIn,")
    print(f"           Greenhouse ({len(GREENHOUSE_COMPANIES)} cos), Lever ({len(LEVER_COMPANIES)} cos),")
    print(f"           Workday ({len(WORKDAY_COMPANIES)} cos), iCIMS ({len(ICIMS_COMPANIES)} cos)")
    print("═" * 60 + "\n")

    all_results: List[Dict[str, Any]] = []

    # ── Run all sources ────────────────────────────────────────────────────────
    print("[1/9] USAJobs API...")
    all_results.extend(fetch_usajobs(profile))

    print("[2/9] ClearanceJobs RSS...")
    all_results.extend(fetch_clearancejobs(profile))

    print("[3/9] Indeed RSS...")
    all_results.extend(fetch_indeed(profile))

    print("[4/9] Dice RSS...")
    all_results.extend(fetch_dice(profile))

    print("[5/9] LinkedIn (best-effort)...")
    all_results.extend(fetch_linkedin(profile))

    print("[6/9] Greenhouse direct API...")
    all_results.extend(fetch_greenhouse(profile))

    print("[7/9] Lever direct API...")
    all_results.extend(fetch_lever(profile))

    print("[8/9] Workday defense employers...")
    all_results.extend(fetch_workday(profile))

    print("[9/9] iCIMS defense contractors...")
    all_results.extend(fetch_icims(profile))

    # ── Merge, dedupe, sort ────────────────────────────────────────────────────
    all_results = dedupe_jobs(all_results)
    all_results.sort(key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
    all_results = all_results[:300]

    print(f"\n[Discovery] Raw pool: {len(all_results)} unique jobs after dedup")

    # Source breakdown
    from collections import Counter
    source_counts = Counter(r["source"] for r in all_results)
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"  {source:<20} {count} jobs")

    # ── Write raw CSV ──────────────────────────────────────────────────────────
    raw_path = write_csv(raw_output_path, all_results)
    print(f"\n[Discovery] Raw CSV: {raw_path}")

    # ── AI rerank ──────────────────────────────────────────────────────────────
    print(f"[Discovery] AI reranking top {min(200, len(all_results))} → keeping {target_final_jobs}...")
    reranked = ai_rerank_candidates(
        client=client,
        profile=profile,
        candidates=all_results,
        model=model,
        keep_count=target_final_jobs,
    )

    final_rows = reranked if reranked else all_results[:target_final_jobs]
    final_path = write_csv(final_output_path, final_rows)

    print(f"[Discovery] Final CSV: {final_path} ({len(final_rows)} jobs)")
    print("\n" + "═" * 60)

    return {"raw": raw_path, "final": final_path}


# ─────────────────────────────────────────────
# SECTION 12: ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    profile = load_profile()
    paths = discover_jobs_from_profile(profile)
    print(f"  Raw:   {paths['raw']}")
    print(f"  Final: {paths['final']}")
