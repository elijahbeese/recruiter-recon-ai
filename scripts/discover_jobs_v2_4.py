"""
discover_jobs_v2_4.py
---------------------
Recruiter Recon AI — Job Discovery Engine v2.4

Changes from v2.3:
  - Massively expanded Greenhouse + Lever company lists into private sector:
    banks, pure-play cyber companies, big tech, healthcare, critical
    infrastructure, insurance/consulting, Tampa-specific employers
  - Score threshold: only jobs scoring 70+ passed to enrichment
  - Deduplication by company + normalized title before enrichment
    (kills 15x Palantir duplicates etc)
  - Tighter senior role filtering in discovery (not just enrichment)
  - Discovery pool target raised to 500 raw before reranking
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

USAJOBS_API_KEY    = os.getenv("USAJOBS_API_KEY", "").strip()
USAJOBS_USER_AGENT = os.getenv("USAJOBS_USER_AGENT", "").strip()

# ── Score threshold ────────────────────────────────────────────────────────────
# Only jobs at or above this score proceed to AI enrichment.
# Keeps enrichment focused on genuinely relevant roles.
ENRICHMENT_SCORE_THRESHOLD = 50

# ── Source priority ────────────────────────────────────────────────────────────
SOURCE_PRIORITY = {
    "usajobs":       95,
    "clearancejobs": 92,
    "greenhouse":    90,
    "lever":         90,
    "workday":       88,
    "icims":         85,
    "dice":          75,
    "indeed":        70,
    "linkedin":      70,
    "other":         40,
}

# ── Relevance keywords ─────────────────────────────────────────────────────────
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
    "senior", "sr.", "lead", "principal", "staff", "manager",
    "director", "architect", "vp ", "chief", "head of",
    "5+ years", "7+ years", "8+ years", "10+ years", "15+ years",
]

JUNK_MARKERS = [
    "jobs near", "get hired", "salary", "career advice", "resume tips",
    "browse jobs", "search jobs", "job alert", "top jobs", "best jobs",
    "sign in", "login", "create account", "job board",
    "financial analyst", "physical security guard", "security officer",
    "administrative assistant", "human resources", "accountant",
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

# ── RSS feed queries ───────────────────────────────────────────────────────────
RSS_QUERIES = [
    "SOC analyst",
    "cybersecurity analyst entry level",
    "incident response analyst",
    "network security analyst",
    "information security analyst",
    "cyber operations analyst",
    "threat intelligence analyst",
    "vulnerability analyst",
    "security operations center analyst",
    "SIEM analyst splunk",
]

# ─────────────────────────────────────────────
# SECTION 2: COMPANY LISTS
# ─────────────────────────────────────────────

# ── Greenhouse companies ───────────────────────────────────────────────────────
# Expanded from 57 to 100+ covering private sector, banks, healthcare,
# critical infrastructure, consulting, Tampa-specific employers.
GREENHOUSE_COMPANIES = [
    # Pure-play cybersecurity
    "crowdstrike", "sentinelone", "lacework", "snyk",
    "dragos", "claroty", "darktrace", "vectra",
    "exabeam", "sumologic", "devo", "anomali", "recordedfuture",
    "flashpoint", "zerofox", "cybereason", "huntress", "expel",
    "redcanary", "blumira", "deepwatch", "threatlocker", "illumio",
    "orca-security", "wiz", "apiiro", "armorcode",
    "arcticsecurity", "expanse", "cybersixgill", "intsights",
    "corelight", "stamus-networks", "gravwell", "datto",
    "securly", "netspi", "horizon3ai", "runzero",
    # MSSP / Consulting
    "coalfire", "optiv", "guidepoint", "trustwave", "secureworks",
    "trellix", "kroll", "bishopfox", "nccgroup",
    "mandiant", "forsythe", "sievert", "redteaminc",
    # Defense / Government contractors
    "saic", "leidos", "boozallen", "caci", "mantech",
    "peraton", "parsons", "amentum", "telos",
    # Banks / Financial services
    "capitalone", "usaa", "jpmorgan", "bankofamerica",
    "citigroup", "wellsfargo", "pnc", "truist",
    "raymond-james", "td-bank", "fidelity", "schwab",
    "visa", "mastercard", "paypal", "stripe",
    # Big tech with cyber divisions
    "microsoft", "google", "amazon", "apple", "meta",
    "ibm", "oracle", "salesforce", "servicenow", "splunk",
    "paloaltonetworks", "fortinet", "rapid7", "tenable", "qualys",
    "beyondtrust", "cyberark", "sailpoint", "okta", "delinea",
    # Healthcare / Hospital systems
    "hca-healthcare", "cigna", "unitedhealth", "humana",
    "advent-health", "baycare", "moffitt",
    # Critical infrastructure / Energy
    "nextera", "duke-energy", "dominion-energy",
    "constellation-energy", "aecom", "jacobs",
    # Consulting / Big 4
    "deloitte", "pwc", "kpmg", "ey",
    "accenture", "booz-allen", "mckinsey", "bcg",
    # Tampa-specific / Florida employers
    "raymond-james", "techdata", "catalina", "verizon",
    "baybridgeit", "voxx-international",
    # Telecom / ISP
    "verizon", "att", "t-mobile", "comcast", "lumen",
    # Insurance
    "travelers", "progressive", "allstate", "aig",
    "brighthouse", "healthfirst",
]

# Remove duplicates while preserving order
_seen = set()
GREENHOUSE_COMPANIES = [
    c for c in GREENHOUSE_COMPANIES
    if not (c in _seen or _seen.add(c))
]

# ── Lever companies ────────────────────────────────────────────────────────────
LEVER_COMPANIES = [
    # Defense tech
    "palantir", "anduril", "shield-ai", "rebellion-defense",
    "scale-ai", "primer", "govini", "hawkeye360",
    "c3-ai", "sievert",
    # Pure cyber
    "crowdstrike", "huntress", "expel", "redcanary", "blumira",
    "lumu", "ox-security", "ncc-group", "bishopfox",
    "intsights", "cybersixgill", "flare-systems",
    "securin", "veriti", "revelstoke", "torq",
    "abnormal-security", "material-security", "proofpoint",
    "cofense", "ironscales", "tessian",
    # Banks / Finance
    "capitalone", "stripe", "brex", "plaid", "chime",
    "robinhood", "coinbase", "kraken",
    # Big tech
    "cloudflare", "hashicorp", "datadog", "elastic",
    "sumo-logic", "devo-technology", "logscale",
    "lacework", "orca", "wiz-io",
    # Healthcare
    "oscar-health", "clover-health", "hims",
    # Consulting
    "boozallen", "telos", "perspecta",
    # Tampa / Florida
    "techdata", "catalinainc", "verizon-business",
]

# Deduplicate
_seen2 = set()
LEVER_COMPANIES = [
    c for c in LEVER_COMPANIES
    if not (c in _seen2 or _seen2.add(c))
]

# ── Workday defense/federal employers ─────────────────────────────────────────
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
    ("parsons", "Parsons Corporation"),
    ("amentum", "Amentum"),
    ("vectrus", "Vectrus"),
    ("deloitte", "Deloitte"),
    ("accenture", "Accenture"),
    ("ibm", "IBM"),
    ("verizon", "Verizon"),
    ("att", "AT&T"),
    ("capitalone", "Capital One"),
    ("usaa", "USAA"),
]

# ── iCIMS employers ────────────────────────────────────────────────────────────
ICIMS_COMPANIES = [
    ("bah", "careers.boozallen.com", "Booz Allen Hamilton"),
    ("mantech", "careers.mantech.com", "ManTech"),
    ("caci", "careers.caci.com", "CACI"),
    ("mitre", "careers.mitre.org", "MITRE"),
    ("l3harris", "careers.l3harris.com", "L3Harris"),
    ("nsa", "apply.intelligencecareers.gov", "NSA"),
    ("raymond-james", "careers.raymondjames.com", "Raymond James"),
    ("hca", "careers.hcahealthcare.com", "HCA Healthcare"),
    ("jpmorgan", "careers.jpmorgan.com", "JPMorgan Chase"),
    ("bankofamerica", "careers.bankofamerica.com", "Bank of America"),
]


# ─────────────────────────────────────────────
# SECTION 3: UTILITIES
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
    return any(re.search(rf"\b{re.escape(s)}\b", t) for s in SENIOR_MARKERS)


def normalize_title(title: str) -> str:
    """Normalize title for deduplication — strips location suffixes and extra whitespace."""
    title = clean_text(title).lower()
    title = re.sub(r"\s*[-–|]\s*(new york|washington|palo alto|remote|dc|ny|ca|fl|tx|md|va).*$", "", title)
    return title.strip()


def dedupe_jobs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate by URL first, then by company + normalized title.
    This kills same-role/different-location duplicates (Palantir problem).
    """
    seen_urls: set = set()
    seen_company_title: set = set()
    deduped = []

    for row in rows:
        url = clean_text(row.get("job_url", "")).lower()
        company = clean_text(row.get("company_name", "")).lower()
        title = normalize_title(row.get("job_title", ""))
        company_title_key = f"{company}||{title}"

        if url and url in seen_urls:
            continue
        if company_title_key in seen_company_title:
            continue

        if url:
            seen_urls.add(url)
        seen_company_title.add(company_title_key)
        deduped.append(row)

    return deduped


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


# ─────────────────────────────────────────────
# SECTION 4: USAJOBS API
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

            time.sleep(0.5)
        if len(results) >= max_results:
            break

    print(f"[USAJobs] {len(results)} postings found")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 5: RSS FEEDS
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
                if not is_relevant(title, description) or is_too_senior(title):
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
    return _fetch_rss(
        base_url="https://www.clearancejobs.com/jobs/rss",
        source_name="clearancejobs",
        queries=cleared_queries,
        locations=locations,
        profile=profile,
        max_results=max_results,
    )


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


# ─────────────────────────────────────────────
# SECTION 6: GREENHOUSE DIRECT API
# ─────────────────────────────────────────────

def fetch_greenhouse(profile: Dict[str, Any], max_results: int = 300) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()
    hit = 0
    miss = 0

    for company in GREENHOUSE_COMPANIES:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        resp = safe_get(url)
        if not resp:
            miss += 1
            continue

        try:
            jobs = resp.json().get("jobs", [])
        except Exception:
            miss += 1
            continue

        hit += 1
        for job in jobs:
            title = clean_text(job.get("title", ""))
            job_url = clean_text(job.get("absolute_url", ""))
            location = clean_text((job.get("location") or {}).get("name", ""))

            if not title or not job_url or job_url in seen_urls:
                continue
            if not is_relevant(title) or is_too_senior(title):
                continue

            seen_urls.add(job_url)
            results.append(make_job_row(
                company_name=company.replace("-", " ").title(),
                company_domain=f"{company}.com",
                job_title=title,
                job_url=job_url,
                job_location=location,
                notes=f"Greenhouse — {company}",
                source="greenhouse",
                profile=profile,
            ))

        time.sleep(0.2)
        if len(results) >= max_results:
            break

    print(f"[Greenhouse] {len(results)} postings from {hit} active boards ({miss} 404s)")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 7: LEVER DIRECT API
# ─────────────────────────────────────────────

def fetch_lever(profile: Dict[str, Any], max_results: int = 200) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()
    hit = 0
    miss = 0

    for company in LEVER_COMPANIES:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        resp = safe_get(url)
        if not resp:
            miss += 1
            continue

        try:
            jobs = resp.json()
            if not isinstance(jobs, list):
                miss += 1
                continue
        except Exception:
            miss += 1
            continue

        hit += 1
        for job in jobs:
            title = clean_text(job.get("text", ""))
            job_url = clean_text(job.get("hostedUrl", ""))
            categories = job.get("categories", {})
            location = clean_text(categories.get("location", ""))
            description = strip_html(job.get("descriptionPlain", "") or "")

            if not title or not job_url or job_url in seen_urls:
                continue
            if not is_relevant(title, description) or is_too_senior(title):
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

        time.sleep(0.2)
        if len(results) >= max_results:
            break

    print(f"[Lever] {len(results)} postings from {hit} active boards ({miss} 404s)")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 8: WORKDAY
# ─────────────────────────────────────────────

def fetch_workday(profile: Dict[str, Any], max_results: int = 100) -> List[Dict[str, Any]]:
    results = []
    seen_urls: set = set()
    keywords = ["cybersecurity", "SOC analyst", "security analyst", "cyber"]

    for slug, company_name in WORKDAY_COMPANIES:
        for keyword in keywords[:3]:
            url = f"https://{slug}.wd1.myworkdayjobs.com/wday/cxs/{slug}/External/jobs"
            payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": keyword}

            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except Exception:
                continue

            for job in data.get("jobPostings", []):
                title = clean_text(job.get("title", ""))
                path = clean_text(job.get("externalPath", ""))
                location = clean_text(job.get("locationsText", ""))

                if not title or not path:
                    continue

                job_url = f"https://{slug}.wd1.myworkdayjobs.com/External{path}"
                if job_url in seen_urls:
                    continue
                if not is_relevant(title) or is_too_senior(title):
                    continue

                seen_urls.add(job_url)
                results.append(make_job_row(
                    company_name=company_name,
                    company_domain=f"{slug}.com",
                    job_title=title,
                    job_url=job_url,
                    job_location=location,
                    notes=f"Workday — {company_name}",
                    source="workday",
                    profile=profile,
                ))

            time.sleep(0.5)
        if len(results) >= max_results:
            break

    print(f"[Workday] {len(results)} postings")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 9: iCIMS
# ─────────────────────────────────────────────

def fetch_icims(profile: Dict[str, Any], max_results: int = 75) -> List[Dict[str, Any]]:
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

            time.sleep(random.uniform(1.0, 2.0))
        if len(results) >= max_results:
            break

    print(f"[iCIMS] {len(results)} postings")
    return results[:max_results]


# ─────────────────────────────────────────────
# SECTION 10: LINKEDIN (BEST-EFFORT)
# ─────────────────────────────────────────────

def fetch_linkedin(profile: Dict[str, Any], max_results: int = 75) -> List[Dict[str, Any]]:
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
                f"f_TPR=r604800&f_E=1,2&sortBy=DD"
            )
            resp = safe_get(url, headers=headers)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = soup.select(".job-search-card") or soup.select(".base-card")

            if not job_cards:
                print(f"  [LinkedIn] No cards for '{query}' — blocked")
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
                if not is_relevant(title) or is_too_senior(title):
                    continue

                seen_urls.add(job_url)
                results.append(make_job_row(
                    company_name=company,
                    company_domain="linkedin.com",
                    job_title=title,
                    job_url=job_url,
                    job_location=loc,
                    notes="LinkedIn posting",
                    source="linkedin",
                    profile=profile,
                ))

            time.sleep(random.uniform(4.0, 8.0))
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    print(f"[LinkedIn] {len(results)} postings (best-effort)")
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
        "You are selecting the best cybersecurity job matches for a candidate. "
        f"CLEARANCE: {clearance} "
        "Prefer: entry-level to early-career roles, SOC/NOC/IR/threat analyst positions, "
        "cleared/DoD positions, defense contractors, federal agencies, "
        "private sector cybersecurity companies, banks with large security teams, "
        "and roles aligned with the candidate's actual skills. "
        "Penalize: roles requiring 5+ years, non-cyber roles, "
        "roles clearly unrelated to cybersecurity. "
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

Return top {keep_count} ranked by fit. Only include jobs with fit_score >= 50.
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
    print("  Recruiter Recon AI — Discovery Engine v2.4")
    print("═" * 60)
    print(f"  Candidate:       {profile.get('name', 'Unknown')}")
    print(f"  Target roles:    {len(profile.get('target_roles', []))}")
    print(f"  Greenhouse cos:  {len(GREENHOUSE_COMPANIES)}")
    print(f"  Lever cos:       {len(LEVER_COMPANIES)}")
    print(f"  Score threshold: {ENRICHMENT_SCORE_THRESHOLD}+ only passed to enrichment")
    print("═" * 60 + "\n")

    all_results: List[Dict[str, Any]] = []

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

    # ── Dedupe by URL then by company + normalized title ───────────────────────
    all_results = dedupe_jobs(all_results)
    all_results.sort(key=lambda x: int(x.get("discovery_score", 0)), reverse=True)

    print(f"\n[Discovery] Raw pool: {len(all_results)} unique jobs after dedup")

    from collections import Counter
    source_counts = Counter(r["source"] for r in all_results)
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"  {source:<20} {count} jobs")

    # Cap raw pool
    all_results = all_results[:500]

    raw_path = write_csv(raw_output_path, all_results)
    print(f"\n[Discovery] Raw CSV: {raw_path}")

    # ── AI rerank — only keep 50+ ──────────────────────────────────────────────
    print(f"[Discovery] AI reranking → keeping only 50+ fit scores (max {target_final_jobs})...")
    reranked = ai_rerank_candidates(
        client=client,
        profile=profile,
        candidates=all_results,
        model=model,
        keep_count=target_final_jobs,
    )

    # Fallback if AI returns nothing
    if not reranked:
        reranked = [r for r in all_results if r.get("discovery_score", 0) >= ENRICHMENT_SCORE_THRESHOLD][:target_final_jobs]

    final_path = write_csv(final_output_path, reranked)
    print(f"[Discovery] Final CSV: {final_path} ({len(reranked)} jobs at 50+ threshold)")
    print("\n" + "═" * 60)

    return {"raw": raw_path, "final": final_path}


# ─────────────────────────────────────────────
# SECTION 13: ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    profile = load_profile()
    paths = discover_jobs_from_profile(profile)
    print(f"  Raw:   {paths['raw']}")
    print(f"  Final: {paths['final']}")
