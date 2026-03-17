import csv
import json
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

GOOD_HOST_MARKERS = [
    "myworkdayjobs.com",
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.smartrecruiters.com",
    "careers.",
    "jobs.",
]

BAD_HOST_MARKERS = [
    "duckduckgo.com",
    "indeed.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "glassdoor.com",
    "linkedin.com",
    "monster.com",
    "careerjet.com",
    "jooble.org",
]


def load_profile(path: str = "candidate_profile_generated.json") -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def search_duckduckgo(query: str, max_results: int = 10) -> List[Dict]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=20)
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

        title = title_tag.get_text(" ", strip=True)
        href = title_tag.get("href", "").strip()
        snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""

        results.append({
            "title": title,
            "url": href,
            "snippet": snippet,
        })

        if len(results) >= max_results:
            break

    return results


def unwrap_duckduckgo_url(url: str) -> str:
    if "duckduckgo.com/l/" not in url:
        return url

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    target = qs.get("uddg", [""])[0]
    return unquote(target) if target else url


def normalized_hostname(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def is_bad_result_url(url: str) -> bool:
    host = normalized_hostname(url)
    return any(marker in host for marker in BAD_HOST_MARKERS)


def is_good_result_url(url: str) -> bool:
    host = normalized_hostname(url)
    return any(marker in host for marker in GOOD_HOST_MARKERS)


def looks_like_job_posting(title: str, snippet: str, url: str) -> bool:
    text = f"{title} {snippet} {url}".lower()

    required_markers = [
        "job",
        "career",
        "apply",
        "analyst",
        "security",
        "cyber",
        "engineer",
        "technician",
        "operations",
        "incident response",
    ]
    obvious_bad_markers = [
        "jobs near",
        "get hired in",
        "salary",
        "career advice",
        "resume tips",
        "browse jobs",
        "search jobs",
    ]

    if any(marker in text for marker in obvious_bad_markers):
        return False

    return any(marker in text for marker in required_markers)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def infer_location(text: str, configured_locations: List[str]) -> str:
    lower_text = text.lower()
    for location in configured_locations:
        if location.lower() in lower_text:
            return location
    return ""


def company_domain_from_url(url: str) -> str:
    return normalized_hostname(url)


def infer_company_name(title: str, url: str) -> str:
    title = clean_text(title)
    host = normalized_hostname(url)

    if "boards.greenhouse.io" in host:
        parts = urlparse(url).path.strip("/").split("/")
        if parts:
            return parts[0].replace("-", " ").title()

    if "jobs.lever.co" in host:
        parts = urlparse(url).path.strip("/").split("/")
        if parts:
            return parts[0].replace("-", " ").title()

    if "jobs.smartrecruiters.com" in host:
        parts = urlparse(url).path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[1].replace("-", " ").title()

    if "myworkdayjobs.com" in host:
        parts = urlparse(url).path.strip("/").split("/")
        for part in parts:
            if part and part.lower() not in {"en-us", "external", "careers", "job"}:
                cleaned = re.sub(r"[_\-]+", " ", part).strip()
                if len(cleaned) > 2:
                    return cleaned.title()

    title_parts = re.split(r"\s[-|–]\s", title)
    if len(title_parts) >= 2:
        possible_company = title_parts[-1].strip()
        if len(possible_company.split()) <= 5:
            return possible_company

    if host:
        root = host.split(".")[0]
        return root.replace("-", " ").title()

    return ""


def score_result(title: str, snippet: str, url: str) -> int:
    text = f"{title} {snippet}".lower()
    score = 0

    if is_good_result_url(url):
        score += 50

    if "security" in text or "cyber" in text:
        score += 20

    if "analyst" in text or "engineer" in text or "technician" in text:
        score += 10

    if "apply" in text or "job" in text or "career" in text:
        score += 10

    if "entry" in text or "junior" in text or "associate" in text:
        score += 10

    return score


def dedupe_jobs(rows: List[Dict]) -> List[Dict]:
    seen = set()
    deduped = []

    for row in rows:
        key = (
            row.get("job_url", "").strip().lower(),
            row.get("job_title", "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    return deduped


def discover_jobs_from_profile(
    profile: Dict,
    output_path: str = "output/discovered_jobs.csv"
) -> Path:
    queries = profile.get("search_queries", [])
    locations = profile.get("location_preferences", [])
    if not locations:
        locations = ["United States", "Remote", "Florida", "Virginia"]

    discovered: List[Dict] = []
    seen_urls = set()

    for base_query in queries:
        for location in locations[:4]:
            query = (
                f'{base_query} "{location}" '
                f'(site:jobs.lever.co OR site:boards.greenhouse.io OR '
                f'site:myworkdayjobs.com OR site:jobs.smartrecruiters.com OR '
                f'site:careers.* OR site:jobs.*)'
            )
            print(f"Searching: {query}")

            results = search_duckduckgo(query, max_results=15)

            for item in results:
                raw_url = item["url"]
                url = unwrap_duckduckgo_url(raw_url)
                title = clean_text(item["title"])
                snippet = clean_text(item["snippet"])

                if not url or url in seen_urls:
                    continue

                if is_bad_result_url(url):
                    continue

                if not looks_like_job_posting(title, snippet, url):
                    continue

                score = score_result(title, snippet, url)
                if score < 50:
                    continue

                seen_urls.add(url)

                discovered.append({
                    "company_name": infer_company_name(title, url),
                    "company_domain": company_domain_from_url(url),
                    "job_title": title,
                    "job_url": url,
                    "job_location": infer_location(
                        f"{title} {snippet}",
                        locations
                    ) or location,
                    "recruiter_name": "",
                    "notes": snippet,
                })

    discovered = dedupe_jobs(discovered)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "company_name",
                "company_domain",
                "job_title",
                "job_url",
                "job_location",
                "recruiter_name",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(discovered)

    return out


if __name__ == "__main__":
    profile = load_profile()
    path = discover_jobs_from_profile(profile)
    print(f"Discovered jobs written to: {path}")
