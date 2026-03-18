from flask import Blueprint, render_template, request, jsonify
import json, os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from app.auth import login_required
from app.data import load_jobs

load_dotenv()
interview_bp = Blueprint("interview", __name__)


def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


def load_profile():
    for path in ["candidate_profile_generated.json", "candidate_profile.json"]:
        if Path(path).exists():
            with open(path) as f:
                return json.load(f)
    return {}


@interview_bp.route("/interview")
@login_required
def interview():
    jobs = load_jobs()
    return render_template("interview.html", jobs=jobs)


@interview_bp.route("/api/interview/prep", methods=["POST"])
@login_required
def prep():
    data    = request.get_json()
    job     = data.get("job", {})
    profile = load_profile()
    client  = get_client()

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "technical_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question":        {"type": "string"},
                        "why_asked":       {"type": "string"},
                        "suggested_answer":{"type": "string"},
                        "your_experience": {"type": "string"},
                    },
                    "required": ["question","why_asked","suggested_answer","your_experience"]
                }
            },
            "behavioral_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question":        {"type": "string"},
                        "framework":       {"type": "string"},
                        "suggested_answer":{"type": "string"},
                    },
                    "required": ["question","framework","suggested_answer"]
                }
            },
            "questions_to_ask":  {"type": "array", "items": {"type": "string"}},
            "key_talking_points":{"type": "array", "items": {"type": "string"}},
            "red_flags_to_address": {"type": "array", "items": {"type": "string"}},
            "salary_negotiation":{"type": "string"},
        },
        "required": [
            "technical_questions","behavioral_questions","questions_to_ask",
            "key_talking_points","red_flags_to_address","salary_negotiation"
        ]
    }

    instructions = (
        "You are an elite interview coach for cybersecurity roles. "
        "Generate interview prep grounded in the candidate's ACTUAL experience — "
        "suggested answers must reference their real background, not generic examples. "
        "Technical questions should match the specific role and required skills. "
        "Behavioral questions should use STAR format. "
        "questions_to_ask: smart questions the candidate should ask the interviewer. "
        "salary_negotiation: specific advice for negotiating comp for this role."
    )

    prompt = f"""
CANDIDATE:
{json.dumps({
    'name': profile.get('name'),
    'experience_level': profile.get('experience_level'),
    'skills': profile.get('skills', []),
    'tools': profile.get('tools', []),
    'certifications': profile.get('certifications', []),
    'resume_summary': profile.get('resume_summary', ''),
    'clearance': 'Active Secret, TS adjudication in progress, Security+',
}, indent=2)}

TARGET JOB:
Title: {job.get('job_title', '')}
Company: {job.get('company_name', '')}
Required Skills: {job.get('required_skills', '')}
Fit Reasoning: {job.get('fit_reasoning', '')}
Red Flags: {job.get('red_flags', '')}

Generate 5 technical questions, 4 behavioral questions, 5 questions to ask, 4 talking points.
"""

    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            instructions=instructions,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "interview_prep", "schema": schema}},
        )
        return jsonify(json.loads(response.output_text))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
