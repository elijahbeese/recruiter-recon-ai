from flask import Blueprint, render_template, request, jsonify
import json, os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from app.auth import login_required
from app.data import load_jobs

load_dotenv()
gap_bp = Blueprint("gap", __name__)


def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


def load_profile():
    for path in ["candidate_profile_generated.json", "candidate_profile.json"]:
        if Path(path).exists():
            with open(path) as f:
                return json.load(f)
    return {}


@gap_bp.route("/gap")
@login_required
def gap():
    jobs = load_jobs()
    return render_template("gap.html", jobs=jobs)


@gap_bp.route("/api/gap/analyze", methods=["POST"])
@login_required
def analyze_gap():
    data    = request.get_json()
    job_url = data.get("job_url", "")
    job     = data.get("job", {})

    if not job and job_url:
        jobs = load_jobs()
        job  = next((j for j in jobs if j.get("job_url") == job_url), {})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    profile = load_profile()
    client  = get_client()

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "overall_gap_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "strong_matches": {"type": "array", "items": {"type": "string"}},
            "gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "skill":      {"type": "string"},
                        "importance": {"type": "string", "enum": ["critical","important","nice-to-have"]},
                        "action":     {"type": "string"},
                        "resource":   {"type": "string"},
                        "time_estimate": {"type": "string"},
                    },
                    "required": ["skill","importance","action","resource","time_estimate"]
                }
            },
            "quick_wins":       {"type": "array", "items": {"type": "string"}},
            "resume_additions": {"type": "array", "items": {"type": "string"}},
            "overall_advice":   {"type": "string"},
        },
        "required": ["overall_gap_score","strong_matches","gaps","quick_wins","resume_additions","overall_advice"]
    }

    instructions = (
        "You are an elite career coach specializing in cybersecurity. "
        "Analyze the gap between the candidate's profile and this job posting. "
        "Be specific and actionable — name real certifications, real free resources, real labs. "
        "For each gap, provide a concrete action the candidate can take this week. "
        "overall_gap_score: how ready they are (100 = perfect fit, 0 = completely unqualified). "
        "quick_wins: things they can add to their resume RIGHT NOW from their existing experience. "
        "resume_additions: specific bullet points they could add to their resume."
    )

    prompt = f"""
CANDIDATE PROFILE:
{json.dumps({
    'name': profile.get('name'),
    'experience_level': profile.get('experience_level'),
    'skills': profile.get('skills', []),
    'tools': profile.get('tools', []),
    'certifications': profile.get('certifications', []),
    'resume_summary': profile.get('resume_summary', ''),
}, indent=2)}

TARGET JOB:
Title: {job.get('job_title', '')}
Company: {job.get('company_name', '')}
Required Skills: {job.get('required_skills', '')}
Preferred Skills: {job.get('preferred_skills', '')}
Fit Reasoning: {job.get('fit_reasoning', '')}
Red Flags: {job.get('red_flags', '')}
"""

    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            instructions=instructions,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "gap_analysis", "schema": schema}},
        )
        return jsonify(json.loads(response.output_text))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
