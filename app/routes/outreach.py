from flask import Blueprint, render_template, request, jsonify
import json
import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
outreach_bp = Blueprint("outreach", __name__)


def get_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


def load_profile():
    for path in ["candidate_profile_generated.json", "candidate_profile.json"]:
        if Path(path).exists():
            with open(path) as f:
                return json.load(f)
    return {}


@outreach_bp.route("/outreach")
def outreach():
    return render_template("outreach.html")


@outreach_bp.route("/api/outreach/generate", methods=["POST"])
def generate_outreach():
    data = request.get_json()
    job = data.get("job", {})
    recruiter_name = data.get("recruiter_name", "")
    recruiter_email = data.get("recruiter_email", "")
    tone = data.get("tone", "professional")

    profile = load_profile()
    client = get_client()

    clearance = "Active Secret clearance (TS adjudication in progress). CompTIA Security+ (DoD 8570 IAT II)."

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "subject_line":    {"type": "string"},
            "email_body":      {"type": "string"},
            "follow_up_line":  {"type": "string"},
            "key_hooks":       {"type": "array", "items": {"type": "string"}},
        },
        "required": ["subject_line", "email_body", "follow_up_line", "key_hooks"]
    }

    tone_instructions = {
        "professional": "Formal, confident, direct. No fluff. Gets to the point in the first sentence.",
        "personable": "Warm but professional. Shows personality. Feels human, not templated.",
        "aggressive": "Bold and confident. Makes a strong case immediately. Commands attention.",
    }

    instructions = (
        f"You are the world's best technical recruiter writing a cold outreach email ON BEHALF OF the candidate to a recruiter. "
        f"Tone: {tone_instructions.get(tone, tone_instructions['professional'])} "
        f"The email must reference SPECIFIC details from the job posting — not generic platitudes. "
        f"Mention the candidate's clearance naturally, not desperately. "
        f"Keep the email under 180 words. Make every word earn its place. "
        f"The subject line must be specific and compelling — not 'Interested in opportunity'. "
        f"The follow_up_line is a single suggested sentence to use in a follow-up 5 days later."
    )

    recruiter_ref = f"Hi {recruiter_name}," if recruiter_name else "Hi,"

    prompt = f"""
CANDIDATE:
Name: {profile.get('name', 'Elijah Beese')}
Summary: {profile.get('resume_summary', '')}
Clearance: {clearance}
Key Skills: {', '.join(profile.get('skills', [])[:8])}
Certifications: {', '.join(profile.get('certifications', []))}
Graduating: May 2026

TARGET JOB:
Title: {job.get('job_title', '')}
Company: {job.get('company_name', '')}
Location: {job.get('job_location', '')}
Fit Score: {job.get('overall_fit_score', '')}
Required Skills: {job.get('required_skills', '')}
Fit Reasoning: {job.get('fit_reasoning', '')}
Outreach Angle: {job.get('outreach_angle', '')}

RECRUITER: {recruiter_name or 'Unknown'} ({recruiter_email or 'email unknown'})

Start the email with: "{recruiter_ref}"
Generate a compelling, specific cold outreach email.
"""

    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            instructions=instructions,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "outreach_email", "schema": schema}},
        )
        result = json.loads(response.output_text)
        result["recruiter_email"] = recruiter_email
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
