import csv
import json
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def load_search_config(path: str = "search_config.json") -> Dict:
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


def derive_company_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname
    except Exception:
        return ""


def infer_location(text: str, configured_locations: List[str]) -> str:
    lower_text = text.lower()
    for location in configured_locations:
        if location.lower() in lower_text:
            return location
    return ""


def looks_like_job_posting(title: str, snippet: str) -> bool:
    text = f"{title} {snippet}".lower()
    keywords = [
        "job", "career", "apply", "analyst", "security", "cyber",
        "technician", "engineer", "operations", "incident response"
    ]
    return any(k in text for k in keywords)


def discover_jobs() -> Path:
    config = load_search_config()
    keywords = config["keywords"]
    locations = config["locations"]
    max_results = config.get("max_results_per_query", 20)

    discovered = []
    seen_urls = set()

    for keyword in keywords:
        for location in locations:
            query = f'{keyword} "{location}" site:jobs.lever.co OR site:boards.greenhouse.io OR site:myworkdayjobs.com OR site:jobs.smartrecruiters.com'
            print(f"Searching: {query}")

            results = search_duckduckgo(query, max_results=max_results)

            for item in results:
                url = item["url"]
                if not url or url in seen_urls:
                    continue

                if not looks_like_job_posting(item["title"], item["snippet"]):
                    continue

                seen_urls.add(url)

                discovered.append({
                    "company_name": "",
                    "company_domain": derive_company_domain(url),
                    "job_title": item["title"],
                    "job_url": url,
                    "job_location": infer_location(
                        f"{item['title']} {item['snippet']}",
                        locations
                    ),
                    "recruiter_name": "",
                    "notes": item["snippet"]
                })

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "discovered_jobs.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as f:
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

    print(f"Discovered jobs written to: {output_path}")
    return output_path


if __name__ == "__main__":
    discover_jobs()
