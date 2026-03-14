import csv
import json
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


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
            "snippet": snippet
        })

        if len(results) >= max_results:
            break

    return results


def looks_like_job_posting(title: str, snippet: str) -> bool:
    text = f"{title} {snippet}".lower()
    markers = [
        "job", "career", "apply", "analyst", "security", "cyber",
        "engineer", "technician", "operations", "incident response"
    ]
    return any(m in text for m in markers)


def company_domain_from_url(url: str) -> str:
    try:
        hostname = urlparse(url).hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname
    except Exception:
        return ""


def discover_jobs_from_profile(profile: Dict, output_path: str = "output/discovered_jobs.csv") -> Path:
    queries = profile.get("search_queries", [])
    locations = profile.get("location_preferences", [])
    if not locations:
        locations = ["United States", "Remote", "Florida", "Virginia"]

    discovered = []
    seen_urls = set()

    for base_query in queries:
        for location in locations[:4]:
            query = (
                f'{base_query} "{location}" '
                f'(site:jobs.lever.co OR site:boards.greenhouse.io OR '
                f'site:myworkdayjobs.com OR site:jobs.smartrecruiters.com)'
            )
            print(f"Searching: {query}")

            results = search_duckduckgo(query, max_results=10)

            for item in results:
                url = item["url"]
                if not url or url in seen_urls:
                    continue

                if not looks_like_job_posting(item["title"], item["snippet"]):
                    continue

                seen_urls.add(url)

                discovered.append({
                    "company_name": "",
                    "company_domain": company_domain_from_url(url),
                    "job_title": item["title"],
                    "job_url": url,
                    "job_location": location,
                    "recruiter_name": "",
                    "notes": item["snippet"]
                })

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
                "notes"
            ]
        )
        writer.writeheader()
        writer.writerows(discovered)

    return out


if __name__ == "__main__":
    profile = load_profile()
    path = discover_jobs_from_profile(profile)
    print(f"Discovered jobs written to: {path}")

