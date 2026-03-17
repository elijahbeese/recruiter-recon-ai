import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List
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

# We allow LinkedIn job posting URLs, but do not try to scrape logged-in pages or private content.
GOOD_HOST_MARKERS = [
    "myworkdayjobs.com",
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.smartrecruiters.com",
    "linkedin.com",
    "careers.",
    "jobs.",
]

BAD_HOST_MARKERS = [
    "duckduckgo.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "glassdoor.com",
    "monster.com",
    "careerjet.com",
    "jooble.org",
    "talent.com",
]

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
]

SOURCE_PRIORITY = {
    "linkedin": 70,
    "workday": 95,
    "greenhouse": 95,
    "lever": 95,
    "smartrecruiters": 95,
    "company_careers": 85,
    "company_jobs": 85,
    "other": 40,
}


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
    if host.startswith("careers.") or ".careers." in host:
        return "company_careers"
    if host.startswith("jobs.") or ".jobs." in host:
        return "company_jobs"
    return "other"


def looks_like_job_posting(title: str, snippet: str, url: str) -> bool:
    text = f"{title} {snippet} {url}".lower()

    obvious_bad_markers = [
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
    ]
    if any(marker in text for marker in obvious_bad_markers):
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

    if "myworkdayjobs.com" in host:
        for part in path_parts:
            if part.lower() not in {"en-us", "external", "careers", "job"}:
                cleaned = re.sub(r"[_\-]+", " ", part).strip()
                if len(cleaned) > 2:
                    return cleaned.title()

    # LinkedIn titles often look like "Cybersecurity Analyst - Company Name"
    title_parts = re.split(r"\s[-|–]\s", title)
    if len(title_parts) >= 2:
        possible_company = clean_text(title_parts[-1])
        if 1 <= len(possible_company.split()) <= 6:
            return possible_company

    # Snippet sometimes contains "... at Company ..."
    m = re.search(r"\bat\s+([A-Z][A-Za-z0-9&,\-.\s]{2,60})", snippet)
    if m:
        return clean_text(m.group(1))

    if host:
        root = host.split(".")[0]
        if root not in {"jobs", "careers", "boards"}:
            return root.replace("-", " ").title()

    return ""


def infer_company_domain(url: str, source: str) -> str:
    host = normalized_hostname(url)

    # LinkedIn is useful as an application link but not as company domain for enrichment.
    if source == "linkedin":
        return ""

    return host


def score_result_heuristic(title: str, snippet: str, url: str, profile: Dict[str, Any]) -> int:
    text = f"{title} {snippet}".lower()
    source = classify_source(url)
    score = SOURCE_PRIORITY.get(source, 30)

    # Role relevance
    for term in JOBISH_TERMS:
        if term in text:
            score += 5

    # Experience level bias
    junior_terms = ["entry", "junior", "associate", "analyst i", "level i", "early career", "new grad"]
    if any(term in text for term in junior_terms):
        score += 10

    # Candidate profile role alignment
    for role in profile.get("target_roles", []):
        role_lower = role.lower()
        if role_lower in text:
            score += 10

    # Candidate skills alignment
    matched_skills = 0
    for skill in profile.get("skills", [])[:20]:
        if skill.lower() in text:
            matched_skills += 1
    score += min(matched_skills * 3, 24)

    # Clearance-oriented bias if relevant
    clearance_rel = profile.get("clearance_relevance", "").lower()
    if "high" in clearance_rel and any(term in text for term in ["clearance", "secret", "top secret", "dod", "government"]):
        score += 10

    return score


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


def search_duckduckgo(query: str, max_results: int = 20) -> List[Dict[str, str]]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return []

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

        results.append({
            "title": title,
            "url": href,
            "snippet": snippet,
        })

        if len(results) >= max_results:
            break

    return results


def build_search_queries(profile: Dict[str, Any]) -> List[str]:
    queries = []

    # Use AI-derived search queries if available
    ai_queries = [clean_text(q) for q in profile.get("search_queries", []) if clean_text(q)]
    queries.extend(ai_queries)

    # Backfill from target roles if needed
    target_roles = [clean_text(r) for r in profile.get("target_roles", []) if clean_text(r)]
    for role in target_roles[:8]:
        queries.append(role)
        queries.append(f"{role} clearance")
        queries.append(f"{role} entry level")

    # Fallback from skills if profile is sparse
    skills = [clean_text(s) for s in profile.get("skills", []) if clean_text(s)]
    skill_seed = []
    for preferred in ["SIEM", "SOC", "Incident Response", "Splunk", "Network Security", "Critical Infrastructure"]:
        if preferred.lower() in {s.lower() for s in skills}:
            skill_seed.append(preferred)

    for seed in skill_seed[:4]:
        queries.append(f"{seed} analyst")
        queries.append(f"{seed} cybersecurity")

    deduped = []
    seen = set()
    for q in queries:
        q_norm = q.lower()
        if q_norm not in seen:
            seen.add(q_norm)
            deduped.append(q)

    return deduped[:20]


def build_query_variants(base_query: str, locations: List[str]) -> List[str]:
    variants = []
    target_sources = [
        "site:linkedin.com/jobs/view",
        "site:myworkdayjobs.com",
        "site:boards.greenhouse.io",
        "site:jobs.lever.co",
        "site:jobs.smartrecruiters.com",
        "site:careers.*",
        "site:jobs.*",
    ]

    for location in locations[:5]:
        for source in target_sources:
            variants.append(f'{base_query} "{location}" {source}')
            variants.append(f'{base_query} "{location}" apply {source}')

    return variants


def ai_rerank_candidates(
    client: OpenAI,
    profile: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    model: str,
    keep_count: int = 100,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    # Limit the prompt size while still giving the model enough to work with.
    prompt_candidates = []
    for idx, c in enumerate(candidates[:180]):
        prompt_candidates.append({
            "index": idx,
            "job_title": c["job_title"],
            "company_name": c["company_name"],
            "company_domain": c["company_domain"],
            "job_url": c["job_url"],
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
                        "reason": {"type": "string"}
                    },
                    "required": ["index", "fit_score", "reason"]
                }
            }
        },
        "required": ["selected"]
    }

    instructions = (
        "You are selecting promising cybersecurity job postings for a candidate. "
        "Use the candidate profile and the candidate list. "
        "Prefer real job postings, entry-level to early-career fit, government/defense/critical-infrastructure relevance, "
        "and likely alignment with the candidate's skills. "
        "Do not invent facts. Score conservatively."
    )

    prompt = f"""
CANDIDATE PROFILE:
{json.dumps(profile, indent=2)}

JOB CANDIDATES:
{json.dumps(prompt_candidates, indent=2)}

Return up to {keep_count} selected candidates, ranked by relevance.
"""

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
    selected = parsed.get("selected", [])

    reranked = []
    seen_indices = set()

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
        key=lambda x: (
            int(x.get("ai_fit_score", 0)),
            int(x.get("discovery_score", 0)),
        ),
        reverse=True,
    )

    return reranked[:keep_count]


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

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out


def discover_jobs_from_profile(
    profile: Dict[str, Any],
    raw_output_path: str = "output/raw_discovered_jobs.csv",
    final_output_path: str = "output/discovered_jobs.csv",
    target_final_jobs: int = 75,
) -> Dict[str, Path]:
    load_dotenv()
    model = os.getenv("OPENAI_MODEL", "gpt-5").strip()
    client = load_client()

    locations = profile.get("location_preferences", [])
    if not locations:
        locations = ["United States", "Remote", "Florida", "Virginia", "Texas"]

    base_queries = build_search_queries(profile)

    raw_candidates: List[Dict[str, Any]] = []
    seen_urls = set()

    for base_query in base_queries:
        query_variants = build_query_variants(base_query, locations)

        for query in query_variants[:14]:
            print(f"Searching: {query}")
            results = search_duckduckgo(query, max_results=20)

            for item in results:
                raw_url = clean_text(item["url"])
                url = unwrap_duckduckgo_url(raw_url)
                title = clean_text(item["title"])
                snippet = clean_text(item["snippet"])
                host = normalized_hostname(url)
                source = classify_source(url)

                if not url or url in seen_urls:
                    continue

                if is_bad_result_url(url):
                    continue

                if not looks_like_job_posting(title, snippet, url):
                    continue

                if source == "other" and not any(marker in host for marker in GOOD_HOST_MARKERS):
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

    raw_candidates = dedupe_jobs(raw_candidates)
    raw_candidates.sort(key=lambda x: int(x.get("discovery_score", 0)), reverse=True)

    # Keep a bigger raw pool for AI reranking
    raw_candidates = raw_candidates[:220]

    raw_path = write_csv(raw_output_path, raw_candidates)

    reranked = ai_rerank_candidates(
        client=client,
        profile=profile,
        candidates=raw_candidates,
        model=model,
        keep_count=target_final_jobs,
    )

    final_rows = reranked if reranked else raw_candidates[:target_final_jobs]
    final_path = write_csv(final_output_path, final_rows)

    return {
        "raw": raw_path,
        "final": final_path,
    }


if __name__ == "__main__":
    profile = load_profile()
    paths = discover_jobs_from_profile(profile)
    print(f"Raw discovered jobs written to: {paths['raw']}")
    print(f"Final discovered jobs written to: {paths['final']}")
