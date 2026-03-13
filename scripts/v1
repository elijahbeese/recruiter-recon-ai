import json
import os
import re
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import requests
import tldextract
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


class Config:
    def __init__(self) -> None:
        load_dotenv()

        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.hunter_api_key = os.getenv("HUNTER_API_KEY", "").strip()
        self.output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "20"))
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-5").strip()
        self.min_recruiter_confidence = int(os.getenv("MIN_RECRUITER_CONFIDENCE", "70"))
        self.verify_emails = os.getenv("VERIFY_EMAILS", "false").lower() == "true"

        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is missing in .env")

        self.output_dir.mkdir(parents=True, exist_ok=True)


def load_candidate_profile(path: str = "candidate_profile.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_input_data() -> pd.DataFrame:
    input_path = Path("input_jobs.csv")
    if not input_path.exists():
        raise FileNotFoundError("input_jobs.csv not found.")
    return pd.read_csv(input_path).fillna("")


def fetch_job_page_text(url: str, timeout: int = 20) -> str:
    if not url or not str(url).startswith(("http://", "https://")):
        return ""

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "img", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:20000]


def domain_from_url(url: str) -> str:
    ext = tldextract.extract(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return ""


def normalize_domain(raw_domain: str, job_url: str) -> str:
    raw_domain = (raw_domain or "").strip().lower()
    if raw_domain:
        return raw_domain.replace("https://", "").replace("http://", "").split("/")[0]
    return domain_from_url(job_url)


def openai_extract_and_score(
    client: OpenAI,
    model: str,
    candidate_profile: Dict[str, Any],
    row: Dict[str, Any],
    job_text: str
) -> Dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entry_level_fit": {
                "type": "string",
                "enum": ["yes", "maybe", "no", "unclear"]
            },
            "clearance_fit": {
                "type": "string",
                "enum": ["required", "preferred", "eligible", "not_mentioned", "unclear"]
            },
            "overall_fit_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100
            },
            "required_skills": {
                "type": "array",
                "items": {"type": "string"}
            },
            "preferred_skills": {
                "type": "array",
                "items": {"type": "string"}
            },
            "fit_reasoning": {"type": "string"},
            "outreach_angle": {"type": "string"},
            "us_based_company": {
                "type": "string",
                "enum": ["yes", "no", "unclear"]
            },
            "likely_job_family": {"type": "string"},
            "red_flags": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": [
            "entry_level_fit",
            "clearance_fit",
            "overall_fit_score",
            "required_skills",
            "preferred_skills",
            "fit_reasoning",
            "outreach_angle",
            "us_based_company",
            "likely_job_family",
            "red_flags"
        ]
    }

    instructions = (
        "You are a strict job-target analysis engine. "
        "Do not invent certifications, clearances, referrals, or experience. "
        "If the information is missing or unclear, say so directly."
    )

    input_text = f"""
Analyze this job target against the candidate profile.

CANDIDATE PROFILE:
{json.dumps(candidate_profile, indent=2)}

JOB TARGET:
{json.dumps(row, indent=2)}

JOB PAGE TEXT:
{job_text[:15000]}

Scoring guidance:
- 80 to 100 = strong fit
- 60 to 79 = decent fit
- 40 to 59 = weak fit
- 0 to 39 = poor fit

Consider:
- entry-level suitability
- cybersecurity relevance
- alignment to the candidate's actual skills
- government / defense / critical infrastructure alignment
- clearance language
"""

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=input_text,
        text={
            "format": {
                "type": "json_schema",
                "name": "job_fit_analysis",
                "schema": schema
            }
        }
    )

    return json.loads(response.output_text)


def hunter_domain_search(company_domain: str, hunter_api_key: str) -> Dict[str, Any]:
    if not company_domain or not hunter_api_key:
        return {}

    endpoint = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": company_domain,
        "api_key": hunter_api_key,
        "department": "hr"
    }

    try:
        response = requests.get(endpoint, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {}


def hunter_email_finder(company_domain: str, recruiter_name: str, hunter_api_key: str) -> Dict[str, Any]:
    if not company_domain or not recruiter_name or not hunter_api_key:
        return {}

    parts = recruiter_name.strip().split()
    if len(parts) < 2:
        return {}

    first_name = parts[0]
    last_name = parts[-1]

    endpoint = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain": company_domain,
        "first_name": first_name,
        "last_name": last_name,
        "api_key": hunter_api_key
    }

    try:
        response = requests.get(endpoint, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {}


def hunter_email_verify(email: str, hunter_api_key: str) -> Dict[str, Any]:
    if not email or not hunter_api_key:
        return {}

    endpoint = "https://api.hunter.io/v2/email-verifier"
    params = {
        "email": email,
        "api_key": hunter_api_key
    }

    try:
        response = requests.get(endpoint, params=params, timeout=20)
        if response.status_code in (200, 202):
            return response.json()
        return {}
    except requests.RequestException:
        return {}


def choose_best_contact(
    row: Dict[str, Any],
    domain_search_result: Dict[str, Any],
    email_finder_result: Dict[str, Any],
    min_confidence: int
) -> Dict[str, Any]:
    recruiter_name_input = (row.get("recruiter_name") or "").strip()

    if email_finder_result.get("data"):
        data = email_finder_result["data"]
        score = int(data.get("score") or 0)
        email = data.get("email") or ""

        if email and score >= min_confidence:
            return {
                "recruiter_contact_name": f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
                "recruiter_contact_email": email,
                "recruiter_contact_type": "named_recruiter",
                "recruiter_contact_confidence": score,
                "recruiter_contact_source": "hunter_email_finder"
            }

    emails = domain_search_result.get("data", {}).get("emails", [])
    preferred_keywords = ["recruit", "talent", "acquisition", "careers", "hr", "staffing"]

    best = None
    best_score = -1

    for item in emails:
        email = (item.get("value") or "").lower()
        position = (item.get("position") or "").lower()
        confidence = int(item.get("confidence") or 0)
        first_name = item.get("first_name") or ""
        last_name = item.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip()

        keyword_boost = 0
        if any(k in email for k in preferred_keywords):
            keyword_boost += 20
        if any(k in position for k in preferred_keywords):
            keyword_boost += 20

        total_score = confidence + keyword_boost

        if total_score > best_score:
            best_score = total_score
            best = {
                "recruiter_contact_name": full_name or recruiter_name_input,
                "recruiter_contact_email": email,
                "recruiter_contact_type": "recruiting_or_hr_contact",
                "recruiter_contact_confidence": total_score,
                "recruiter_contact_source": "hunter_domain_search"
            }

    return best or {
        "recruiter_contact_name": recruiter_name_input,
        "recruiter_contact_email": "",
        "recruiter_contact_type": "none_found",
        "recruiter_contact_confidence": 0,
        "recruiter_contact_source": "none"
    }


def verify_contact_email(email: str, hunter_api_key: str, enabled: bool) -> Dict[str, Any]:
    if not enabled or not email:
        return {
            "recruiter_email_verification_result": "",
            "recruiter_email_verification_score": ""
        }

    result = hunter_email_verify(email, hunter_api_key)
    data = result.get("data", {}) if result else {}

    return {
        "recruiter_email_verification_result": data.get("result", ""),
        "recruiter_email_verification_score": data.get("score", "")
    }


def main() -> None:
    config = Config()
    client = OpenAI(api_key=config.openai_api_key)
    candidate_profile = load_candidate_profile()
    df = read_input_data()

    results = []

    for _, row_series in df.iterrows():
        row = row_series.to_dict()
        company_name = (row.get("company_name") or "").strip()
        job_title = (row.get("job_title") or "").strip()
        job_url = (row.get("job_url") or "").strip()
        recruiter_name_input = (row.get("recruiter_name") or "").strip()
        company_domain = normalize_domain((row.get("company_domain") or ""), job_url)

        print(f"Processing: {company_name} | {job_title}")

        job_text = fetch_job_page_text(job_url, timeout=config.request_timeout)

        if not job_text:
            analysis = {
                "entry_level_fit": "unclear",
                "clearance_fit": "unclear",
                "overall_fit_score": 0,
                "required_skills": [],
                "preferred_skills": [],
                "fit_reasoning": "Job page could not be fetched or parsed.",
                "outreach_angle": "",
                "us_based_company": "unclear",
                "likely_job_family": "",
                "red_flags": ["job_page_unavailable"]
            }
        else:
            try:
                analysis = openai_extract_and_score(
                    client=client,
                    model=config.openai_model,
                    candidate_profile=candidate_profile,
                    row=row,
                    job_text=job_text
                )
            except Exception as exc:
                analysis = {
                    "entry_level_fit": "unclear",
                    "clearance_fit": "unclear",
                    "overall_fit_score": 0,
                    "required_skills": [],
                    "preferred_skills": [],
                    "fit_reasoning": f"Model analysis failed: {exc}",
                    "outreach_angle": "",
                    "us_based_company": "unclear",
                    "likely_job_family": "",
                    "red_flags": ["model_analysis_failed"]
                }

        domain_search_result = hunter_domain_search(company_domain, config.hunter_api_key)
        email_finder_result = hunter_email_finder(company_domain, recruiter_name_input, config.hunter_api_key)

        contact = choose_best_contact(
            row=row,
            domain_search_result=domain_search_result,
            email_finder_result=email_finder_result,
            min_confidence=config.min_recruiter_confidence
        )

        verification = verify_contact_email(
            email=contact.get("recruiter_contact_email", ""),
            hunter_api_key=config.hunter_api_key,
            enabled=config.verify_emails
        )

        result_row = {
            "company_name": company_name,
            "company_domain": company_domain,
            "job_title": job_title,
            "job_url": job_url,
            "job_location": row.get("job_location", ""),
            "recruiter_name_input": recruiter_name_input,
            "recruiter_contact_name": contact.get("recruiter_contact_name", ""),
            "recruiter_contact_email": contact.get("recruiter_contact_email", ""),
            "recruiter_contact_type": contact.get("recruiter_contact_type", ""),
            "recruiter_contact_confidence": contact.get("recruiter_contact_confidence", ""),
            "recruiter_contact_source": contact.get("recruiter_contact_source", ""),
            "recruiter_email_verification_result": verification.get("recruiter_email_verification_result", ""),
            "recruiter_email_verification_score": verification.get("recruiter_email_verification_score", ""),
            "entry_level_fit": analysis.get("entry_level_fit", ""),
            "clearance_fit": analysis.get("clearance_fit", ""),
            "overall_fit_score": analysis.get("overall_fit_score", 0),
            "required_skills": ", ".join(analysis.get("required_skills", [])),
            "preferred_skills": ", ".join(analysis.get("preferred_skills", [])),
            "fit_reasoning": analysis.get("fit_reasoning", ""),
            "outreach_angle": analysis.get("outreach_angle", ""),
            "us_based_company": analysis.get("us_based_company", ""),
            "likely_job_family": analysis.get("likely_job_family", ""),
            "red_flags": ", ".join(analysis.get("red_flags", [])),
            "verification_status": "pending_manual_review"
        }

        results.append(result_row)

    output_df = pd.DataFrame(results)
    output_path = config.output_dir / "enriched_jobs.csv"
    output_df.to_csv(output_path, index=False)
    print(f"Done. Output written to: {output_path}")


if __name__ == "__main__":
    main()
