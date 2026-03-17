"""
discover_jobs_v2_2.py
---------------------
Recruiter Recon AI — Job Discovery Engine v2.2

Changes from v2.1:
  - Rate limiting with randomized sleep between every DDG request (fixes silent empty returns)
  - Wildcard site: queries removed and replaced with real, working ATS-targeted queries
  - Query budget capped at a sane ceiling before the loop runs (not after 700 requests)
  - Discovery structured in two passes: ATS-direct queries first, then broader location queries
  - DDG retry logic with exponential backoff on failure
  - Cleaner query deduplication before any searching begins
  - run_v2.py updated separately to call this file
"""

# ─────────────────────────────────────────────
# SECTION 1: IMPORTS & CONSTANTS
# ─────────────────────────────────────────────

import csv
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 20

# ── Rate limiting ──────────────────────────────────────────────────────────────
# DuckDuckGo HTML scraping will rate-limit you silently (returns 0 results, no
# error) if you hammer it. A randomized sleep between every request keeps you
# under the radar. Tune these if you're still getting throttled.
DDG_SLEEP_MIN = 2.5   # seconds
DDG_SLEEP_MAX = 5.5   # seconds
DDG_MAX_RETRIES = 3
DDG_RETRY_BACKOFF_BASE = 8  # seconds — doubles each retry

# ── Query budget ──────────────────────────────────────────────────────────────
# Hard ceiling on how many DDG searches fire per run. Keeps runtime predictable
# and prevents accidental 700-request runs that all come back empty.
MAX_DDG_QUERIES = 60

# ── ATS platforms — explicit site: targets (no wildcards) ─────────────────────
# v2.1 used site:careers.* and site:jobs.* — DDG doesn't support wildcards.
# These are real, working site: targets.
ATS_SITE_TARGETS = [
    "site:myworkdayjobs.com",
    "site:boards.greenhouse.io",
    "site:jobs.lever.co",
    "site:jobs.smartrecruiters.com",
    "site:linkedin.com/jobs/view",
    "site:careers.google.com",
    "site:jobs.ashbyhq.com",
]

# ── Source classification ──────────────────────────────────────────────────────
BAD_HOST_MARKERS = [
    "duckduckgo.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "glassdoor.com",
    "monster.com",
    "careerjet.com",
    "jooble.org",
    "talent.com",
    "indeed.com",
    "snagajob.com",
    "salary.com",
]

GOOD_HOST_MARKERS = [
    "myworkdayjobs.com",
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.smartrecruiters.com",
    "linkedin.com",
    "jobs.ashbyhq.com",
    "careers.",
    "jobs.",
]

SOURCE_PRIORITY = {
    "linkedin": 70,
    "workday": 95,
    "greenhouse": 95,
    "lever": 95,
    "smartrecruiters": 95,
    "ashby": 90,
    "company_careers": 85,
    "company_jobs": 80,
    "other": 40,
}

# ── Relevance signals ──────────────────────────────────────────────────────────
JOBISH_TERMS = [
    "cyber",
    "security",
    "analyst",
    "engineer",
    "technician",
    "incident response",
    "soc",
    "operations",
    "network security",
    "threat",
    "intelligence",
    "forensics",
    "vulnerability",
    "penetration",
]

JUNK_MARKERS = [
    "jobs near",
    "get hired in",
    "salary",
    "career advice",
    "resume tips",
    "browse jobs",
    "search jobs",
    "job alert",
    "top jobs",
    "best jobs",
    "sign in",
    "login",
    "create account",
    "job board",
]


# ─────────────────────────────────────────────
# SECTION 2: UTILITIES
# ─────────────────────────────────────────────

def load_profile(path: str = "candidate_profile_generated.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_client() -> OpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")
    return OpenAI(api_key=api_key)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalized_hostname(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def unwrap_duckduckgo_url(url: str) -> str:
    if "duckduckgo.com/l/" not in url:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    target = qs.get("uddg", [""])[0]
    return unquote(target) if target else url


def is_bad_result_url(url: str) -> bool:
    host = normalized_hostname(url)
    return any(marker in host for marker in BAD_HOST_MARKERS)


def classify_source(url: str) -> str:
    host = normalized_hostname(url)
    if "linkedin.com" in host and "/jobs/view/" in url:
        return "linkedin"
    if "myworkdayjobs.com" in host:
        return "workday"
    if "boards.greenhouse.io" in host:
        return "greenhouse"
    if "jobs.lever.co" in host:
        return "lever"
    if "jobs.smartrecruiters.com" in host:
        return "smartrecruiters"
    if "jobs.ashbyhq.com" in host:
        return "ashby"
    if host.startswith("careers.") or ".careers." in host:
        return "company_careers"
    if host.startswith("jobs.") or ".jobs." in host:
        return "company_jobs"
    return "other"


def looks_like_job_posting(title: str, snippet: str, url: str) -> bool:
    text = f"{title} {snippet} {url}".lower()
    if any(marker in text for marker in JUNK_MARKERS):
        return False
    return any(term in text for term in JOBISH_TERMS)


def infer_location(text: str, configured_locations: List[str]) -> str:
    lower_text = text.lower()
    for location in configured_locations:
        if location.lower() in lower_text:
            return location
    return ""


def infer_company_name(title: str, snippet: str, url: str) -> str:
    title = clean_text(title)
    snippet = clean_text(snippet)
    host = normalized_hostname(url)
    path_parts = [p for p in urlparse(url).path.strip("/").split("/") if p]

    if "boards.greenhouse.io" in host and path_parts:
        return path_parts[0].replace("-", " ").title()
    if "jobs.lever.co" in host and path_parts:
        return path_parts[0].replace("-", " ").title()
    if "jobs.smartrecruiters.com" in host and len(path_parts) >= 2:
        return path_parts[1].replace("-", " ").title()
    if "jobs.ashbyhq.com" in host and path_parts:
        return path_parts[0].replace("-", " ").title()
    if "myworkdayjobs.com" in host:
        for part in path_parts:
            if part.lower() not in {"en-us", "external", "careers", "job", "jobs"}:
                cleaned = re.sub(r"[_\-]+", " ", part).strip()
                if len(cleaned) > 2:
                    return cleaned.title()

    # "Job Title - Company Name" pattern
    title_parts = re.split(r"\s[-|–]\s", title)
    if len(title_parts) >= 2:
        possible_company = clean_text(title_parts[-1])
        if 1 <= len(possible_company.split()) <= 6:
            return possible_company

    # "at Company" in snippet
    m = re.search(r"\bat\s+([A-Z][A-Za-z0-9&,\-.\s]{2,60})", snippet)
    if m:
        return clean_text(m.group(1))

    if host:
        root = host.split(".")[0]
        if root not in {"jobs", "careers", "boards", "apply"}:
            return root.replace("-", " ").title()

    return ""


def infer_company_domain(url: str, source: str) -> str:
    # LinkedIn is useful as an application link but useless for Hunter enrichment
    if source == "linkedin":
        return ""
    return normalized_hostname(url)


def dedupe_jobs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (
            clean_text(row.get("job_url", "")).lower(),
            clean_text(row.get("job_title", "")).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


# ─────────────────────────────────────────────
# SECTION 3: DDG SEARCH WITH RATE LIMITING
# ─────────────────────────────────────────────

def _sleep_between_requests() -> None:
    """Randomized sleep to avoid DDG rate limiting. Call before every request."""
    delay = random.uniform(DDG_SLEEP_MIN, DDG_SLEEP_MAX)
    time.sleep(delay)


def search_duckduckgo(query: str, max_results: int = 20) -> List[Dict[str, str]]:
    """
    Query DuckDuckGo HTML and return result list.

    Includes:
    - Randomized sleep before every attempt
    - Retry with exponential backoff on request failure
    - Returns empty list on total failure (never raises)
    """
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(DDG_MAX_RETRIES):
        _sleep_between_requests()

        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            wait = DDG_RETRY_BACKOFF_BASE * (2 ** attempt)
            print(f"  [DDG] Request failed (attempt {attempt + 1}/{DDG_MAX_RETRIES}): {e}")
            if attempt < DDG_MAX_RETRIES - 1:
                print(f"  [DDG] Retrying in {wait}s...")
                time.sleep(wait)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for result in soup.select(".result"):
            title_tag = result.select_one(".result__title a")
            snippet_tag = result.select_one(".result__snippet")

            if not title_tag:
                continue

            title = clean_text(title_tag.get_text(" ", strip=True))
            href = clean_text(title_tag.get("href", ""))
            snippet = clean_text(snippet_tag.get_text(" ", strip=True) if snippet_tag else "")

            if not title or not href:
                continue

            results.append({"title": title, "url": href, "snippet": snippet})

            if len(results) >= max_results:
                break

        return results

    print(f"  [DDG] All retries exhausted for query: {query[:80]}")
    return []


# ─────────────────────────────────────────────
# SECTION 4: QUERY CONSTRUCTION
# ─────────────────────────────────────────────

def build_search_queries(profile: Dict[str, Any]) -> List[str]:
    """
    Build a deduplicated list of base search queries from the candidate profile.

    Priority:
    1. AI-generated search_queries from the profile
    2. Target roles (with entry-level and clearance variants)
    3. High-value skill seeds
    """
    queries = []

    # 1. AI-derived queries from profile
    ai_queries = [clean_text(q) for q in profile.get("search_queries", []) if clean_text(q)]
    queries.extend(ai_queries)

    # 2. Role-based variants
    target_roles = [clean_text(r) for r in profile.get("target_roles", []) if clean_text(r)]
    for role in target_roles[:6]:
        queries.append(role)
        queries.append(f"{role} entry level")
        queries.append(f"{role} clearance")
        queries.append(f"{role} DoD")

    # 3. Skill-seeded queries for cybersecurity domain
    skills = {s.lower() for s in profile.get("skills", [])}
    preferred_seeds = [
        "SIEM", "SOC", "Incident Response", "Splunk",
        "Network Security", "Critical Infrastructure", "Threat Intelligence"
    ]
    for seed in preferred_seeds:
        if seed.lower() in skills:
            queries.append(f"{seed} analyst")
            queries.append(f"{seed} cybersecurity job")

    # Deduplicate while preserving order
    seen: set = set()
    deduped = []
    for q in queries:
        q_norm = q.lower().strip()
        if q_norm and q_norm not in seen:
            seen.add(q_norm)
            deduped.append(q)

    return deduped[:25]  # 25 base queries max — enough signal, not enough rope to hang yourself


def build_query_plan(
    base_queries: List[str],
    locations: List[str],
    max_total: int = MAX_DDG_QUERIES,
) -> List[str]:
    """
    Build the final flat list of DDG queries to run, capped at max_total.

    Strategy (two-pass):
    Pass 1 — ATS-direct: each base query paired with each ATS site: target, no location.
             These are the highest-quality hits. Run first.
    Pass 2 — Location-scoped: top base queries × top locations, no site: restriction.
             Catches company career pages and anything ATS-direct missed.

    The entire list is capped at max_total before any searching begins.
    """
    plan: List[str] = []
    seen: set = set()

    def add(q: str) -> None:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            plan.append(q)

    # Pass 1: ATS-direct (no location filter — maximizes hits per ATS)
    for base in base_queries[:15]:
        for site in ATS_SITE_TARGETS:
            add(f'"{base}" {site}')

    # Pass 2: Location-scoped broad queries (top queries × top locations)
    for base in base_queries[:10]:
        for loc in locations[:4]:
            add(f'"{base}" "{loc}"')
            add(f'"{base}" "{loc}" apply now')

    # Trim to budget
    return plan[:max_total]


# ─────────────────────────────────────────────
# SECTION 5: HEURISTIC SCORING
# ─────────────────────────────────────────────

def score_result_heuristic(
    title: str,
    snippet: str,
    url: str,
    profile: Dict[str, Any],
) -> int:
    """
    Score a raw search result before AI reranking.
    Higher = more likely to be a good fit and a real job posting.
    """
    text = f"{title} {snippet}".lower()
    source = classify_source(url)
    score = SOURCE_PRIORITY.get(source, 30)

    # Domain relevance
    for term in JOBISH_TERMS:
        if term in text:
            score += 4

    # Entry-level signals
    entry_terms = ["entry", "junior", "associate", "analyst i", "level i", "early career", "new grad"]
    if any(t in text for t in entry_terms):
        score += 12

    # Role alignment against candidate profile
    for role in profile.get("target_roles", []):
        if role.lower() in text:
            score += 10

    # Skill overlap
    matched = sum(1 for s in profile.get("skills", [])[:20] if s.lower() in text)
    score += min(matched * 3, 24)

    # Clearance relevance bonus
    if "high" in profile.get("clearance_relevance", "").lower():
        if any(t in text for t in ["clearance", "secret", "top secret", "dod", "government", "federal"]):
            score += 12

    # Defense / critical infrastructure alignment
    if any(t in text for t in ["defense", "army", "dod", "federal", "critical infrastructure", "ics", "scada"]):
        score += 8

    return score


# ─────────────────────────────────────────────
# SECTION 6: AI RERANKING
# ─────────────────────────────────────────────

def ai_rerank_candidates(
    client: OpenAI,
    profile: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    model: str,
    keep_count: int = 100,
) -> List[Dict[str, Any]]:
    """
    Send the top raw candidates to the LLM for relevance scoring and reranking.
    Falls back to heuristic order if the API call fails.
    """
    if not candidates:
        return []

    prompt_candidates = []
    for idx, c in enumerate(candidates[:180]):
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
                        "index": {"type": "integer"},
                        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "reason": {"type": "string"},
                    },
                    "required": ["index", "fit_score", "reason"],
                },
            }
        },
        "required": ["selected"],
    }

    instructions = (
        "You are selecting promising cybersecurity job postings for a candidate. "
        "Prefer real job postings at named companies, entry-level to early-career fit, "
        "government / defense / critical-infrastructure relevance, "
        "and alignment with the candidate's actual skills and clearance status. "
        "Do not invent facts. Score conservatively. Exclude obvious junk or aggregator results."
    )

    prompt = f"""
CANDIDATE PROFILE:
{json.dumps(profile, indent=2)}

JOB CANDIDATES:
{json.dumps(prompt_candidates, indent=2)}

Return up to {keep_count} selected candidates, ranked by fit.
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
        print(f"[AI Rerank] Failed: {exc}. Falling back to heuristic order.")
        return candidates[:keep_count]

    selected = parsed.get("selected", [])
    reranked = []
    seen_indices: set = set()

    for item in selected:
        idx = item["index"]
        if idx in seen_indices or idx >= len(candidates[:180]):
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
# SECTION 7: CSV OUTPUT
# ─────────────────────────────────────────────

def write_csv(path: str, rows: List[Dict[str, Any]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "company_name",
        "company_domain",
        "job_title",
        "job_url",
        "job_location",
        "recruiter_name",
        "notes",
        "source",
        "discovery_score",
        "ai_fit_score",
        "ai_reason",
    ]

    # Ensure every row has all fields (graceful handling of partial rows)
    normalized = []
    for row in rows:
        normalized.append({field: row.get(field, "") for field in fieldnames})

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)

    return out


# ─────────────────────────────────────────────
# SECTION 8: MAIN PIPELINE
# ─────────────────────────────────────────────

def discover_jobs_from_profile(
    profile: Dict[str, Any],
    raw_output_path: str = "output/raw_discovered_jobs.csv",
    final_output_path: str = "output/discovered_jobs.csv",
    target_final_jobs: int = 75,
) -> Dict[str, Path]:
    """
    Full discovery pipeline:
    1. Build query plan from profile (capped, no wildcards, rate-limit-aware)
    2. Execute DDG searches with sleep + retry
    3. Filter, score, and deduplicate raw results
    4. Write raw CSV
    5. AI rerank top candidates
    6. Write final CSV
    """
    load_dotenv()
    model = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
    client = load_client()

    locations = profile.get("location_preferences", [])
    if not locations:
        locations = ["United States", "Remote", "Florida", "Virginia", "Texas"]

    base_queries = build_search_queries(profile)
    query_plan = build_query_plan(base_queries, locations, max_total=MAX_DDG_QUERIES)

    print(f"[Discovery] {len(base_queries)} base queries → {len(query_plan)} planned DDG searches")
    print(f"[Discovery] Estimated runtime: {len(query_plan) * ((DDG_SLEEP_MIN + DDG_SLEEP_MAX) / 2):.0f}s (~{len(query_plan) * ((DDG_SLEEP_MIN + DDG_SLEEP_MAX) / 2) / 60:.1f} min)")

    raw_candidates: List[Dict[str, Any]] = []
    seen_urls: set = set()

    for i, query in enumerate(query_plan, start=1):
        print(f"  [{i}/{len(query_plan)}] {query[:100]}")
        results = search_duckduckgo(query, max_results=20)

        if not results:
            print(f"    → 0 results (rate limited or no hits)")
            continue

        accepted = 0
        for item in results:
            raw_url = clean_text(item["url"])
            url = unwrap_duckduckgo_url(raw_url)
            title = clean_text(item["title"])
            snippet = clean_text(item["snippet"])
            source = classify_source(url)

            if not url or url in seen_urls:
                continue
            if is_bad_result_url(url):
                continue
            if not looks_like_job_posting(title, snippet, url):
                continue
            if source == "other" and not any(m in normalized_hostname(url) for m in GOOD_HOST_MARKERS):
                continue

            seen_urls.add(url)
            heuristic_score = score_result_heuristic(title, snippet, url, profile)

            raw_candidates.append({
                "company_name": infer_company_name(title, snippet, url),
                "company_domain": infer_company_domain(url, source),
                "job_title": title,
                "job_url": url,
                "job_location": infer_location(f"{title} {snippet}", locations),
                "recruiter_name": "",
                "notes": snippet,
                "source": source,
                "discovery_score": heuristic_score,
                "ai_fit_score": 0,
                "ai_reason": "",
            })
            accepted += 1

        print(f"    → {len(results)} results, {accepted} accepted")

    raw_candidates = dedupe_jobs(raw_candidates)
    raw_candidates.sort(key=lambda x: int(x.get("discovery_score", 0)), reverse=True)
    raw_candidates = raw_candidates[:220]

    print(f"\n[Discovery] Raw pool: {len(raw_candidates)} candidates after dedup + sort")

    raw_path = write_csv(raw_output_path, raw_candidates)
    print(f"[Discovery] Raw CSV written: {raw_path}")

    print(f"[Discovery] Running AI rerank (top {min(180, len(raw_candidates))} → keep {target_final_jobs})...")
    reranked = ai_rerank_candidates(
        client=client,
        profile=profile,
        candidates=raw_candidates,
        model=model,
        keep_count=target_final_jobs,
    )

    final_rows = reranked if reranked else raw_candidates[:target_final_jobs]
    final_path = write_csv(final_output_path, final_rows)
    print(f"[Discovery] Final CSV written: {final_path} ({len(final_rows)} jobs)")

    return {"raw": raw_path, "final": final_path}


# ─────────────────────────────────────────────
# SECTION 9: ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    profile = load_profile()
    paths = discover_jobs_from_profile(profile)
    print(f"\nDone.")
    print(f"  Raw:   {paths['raw']}")
    print(f"  Final: {paths['final']}")
