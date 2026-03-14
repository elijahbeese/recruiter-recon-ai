import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI

from parse_resume_v2 import parse_resume


def build_candidate_profile(resume_text: str, output_path: str = "candidate_profile_generated.json") -> Dict[str, Any]:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-5").strip()

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing in .env")

    client = OpenAI(api_key=api_key)

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "target_roles": {
                "type": "array",
                "items": {"type": "string"}
            },
            "experience_level": {"type": "string"},
            "industries": {
                "type": "array",
                "items": {"type": "string"}
            },
            "skills": {
                "type": "array",
                "items": {"type": "string"}
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"}
            },
            "certifications": {
                "type": "array",
                "items": {"type": "string"}
            },
            "clearance_relevance": {"type": "string"},
            "location_preferences": {
                "type": "array",
                "items": {"type": "string"}
            },
            "resume_summary": {"type": "string"},
            "search_queries": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": [
            "name",
            "target_roles",
            "experience_level",
            "industries",
            "skills",
            "tools",
            "certifications",
            "clearance_relevance",
            "location_preferences",
            "resume_summary",
            "search_queries"
        ]
    }

    instructions = (
        "You extract a structured candidate profile from resume text. "
        "Do not invent experience, credentials, or clearance status. "
        "Infer likely target roles and useful job-search queries conservatively."
    )

    prompt = f"""
Extract a structured candidate profile from this resume.

RESUME TEXT:
{resume_text[:25000]}

Return:
- likely target roles
- realistic experience level
- skills
- tools
- certifications
- industries
- clearance relevance
- a concise summary
- 8-12 useful search queries that could be used to find fitting jobs
"""

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "candidate_profile",
                "schema": schema
            }
        }
    )

    profile = json.loads(response.output_text)

    Path(output_path).write_text(
        json.dumps(profile, indent=2),
        encoding="utf-8"
    )

    return profile


if __name__ == "__main__":
    resume_path = "resumes/resume.docx"
    resume_text = parse_resume(resume_path)
    profile = build_candidate_profile(resume_text)
    print(json.dumps(profile, indent=2))
