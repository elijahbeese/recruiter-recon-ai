from flask import Blueprint, render_template, request, jsonify
import json
import os
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
lookup_bp = Blueprint("lookup", __name__)


def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


def fetch_page_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer"]):
            tag.decompose()
        import re
        text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
        return text[:12000]
    except Exception as e:
        return f"Could not fetch page: {e}"


def load_profile():
    for path in ["candidate_profile_generated.json", "candidate_profile.json"]:
        if Path(path).exists():
            with open(path) as f:
                return json.load(f)
    return {}


def analyze_job(url: str, job_text: str, profile: dict) -> dict:
    client = get_client()
    clearance = "Active Secret clearance. TS adjudication in progress. Security+ meets DoD 8570 IAT II."

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "job_title":         {"type": "string"},
            "company_name":      {"type": "string"},
            "job_location":      {"type": "string"},
            "entry_level_fit":   {"type": "string", "enum": ["yes", "maybe", "no", "unclear"]},
            "clearance_fit":     {"type": "string", "enum": ["required", "preferred", "eligible", "not_mentioned", "unclear"]},
            "overall_fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "required_skills":   {"type": "array", "items": {"type": "string"}},
            "preferred_skills":  {"type": "array", "items": {"type": "string"}},
            "fit_reasoning":     {"type": "string"},
            "outreach_angle":    {"type": "string"},
            "red_flags":         {"type": "array", "items": {"type": "string"}},
            "salary_estimate":   {"type": "string"},
            "company_domain":    {"type": "string"},
        },
        "required": [
            "job_title", "company_name", "job_location", "entry_level_fit",
            "clearance_fit", "overall_fit_score", "required_skills",
            "preferred_skills", "fit_reasoning", "outreach_angle",
            "red_flags", "salary_estimate", "company_domain"
        ]
    }

    instructions = (
        "You are SITREP, an elite job intelligence analyst. "
        f"CANDIDATE CLEARANCE: {clearance} "
        "Analyze this job posting against the candidate profile with brutal honesty. "
        "Extract all relevant intelligence. Estimate salary range if not listed based on role/location/company. "
        "The outreach_angle should be a specific, compelling 2-sentence opener for a cold email to the recruiter."
    )

    prompt = f"""
CANDIDATE PROFILE:
{json.dumps({
    'name': profile.get('name'),
    'experience_level': profile.get('experience_level'),
    'skills': profile.get('skills', []),
    'tools': profile.get('tools', []),
    'certifications': profile.get('certifications', []),
    'clearance': clearance,
    'target_roles': profile.get('target_roles', []),
    'resume_summary': profile.get('resume_summary', ''),
}, indent=2)}

JOB URL: {url}

JOB PAGE TEXT:
{job_text}

Analyze this job and return structured intelligence.
"""

    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            instructions=instructions,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "job_analysis", "schema": schema}},
        )
        return json.loads(response.output_text)
    except Exception as e:
        return {"error": str(e)}


@lookup_bp.route("/lookup")
def lookup():
    return render_template("lookup.html")


@lookup_bp.route("/api/lookup", methods=["POST"])
def api_lookup():
    data = request.get_json()
    urls = data.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    profile = load_profile()
    results = []

    for url in urls[:5]:
        url = url.strip()
        if not url:
            continue
        job_text = fetch_page_text(url)
        analysis = analyze_job(url, job_text, profile)
        analysis["job_url"] = url

        # Hunter lookup for recruiter
        domain = analysis.get("company_domain", "")
        if domain and not domain.endswith(".gov") and not domain.endswith(".mil"):
            hunter_key = os.getenv("HUNTER_API_KEY", "")
            if hunter_key:
                try:
                    r = requests.get(
                        "https://api.hunter.io/v2/domain-search",
                        params={"domain": domain, "api_key": hunter_key, "department": "hr"},
                        timeout=10,
                    )
                    hunter_data = r.json().get("data", {}).get("emails", [])
                    if hunter_data:
                        best = max(hunter_data, key=lambda x: int(x.get("confidence", 0)))
                        analysis["recruiter_name"] = f"{best.get('first_name','')} {best.get('last_name','')}".strip()
                        analysis["recruiter_email"] = best.get("value", "")
                        analysis["recruiter_confidence"] = best.get("confidence", 0)
                except Exception:
                    pass

        results.append(analysis)

    return jsonify(results)
