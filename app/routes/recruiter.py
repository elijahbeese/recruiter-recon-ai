from flask import Blueprint, render_template, request, jsonify
import os
import requests
from dotenv import load_dotenv

load_dotenv()
recruiter_bp = Blueprint("recruiter", __name__)


@recruiter_bp.route("/recruiter")
def recruiter():
    return render_template("recruiter.html")


@recruiter_bp.route("/api/recruiter", methods=["POST"])
def api_recruiter():
    data = request.get_json()
    domain = (data.get("domain") or "").strip().lower()
    company = (data.get("company") or "").strip()

    if not domain and not company:
        return jsonify({"error": "Provide a company name or domain"}), 400

    hunter_key = os.getenv("HUNTER_API_KEY", "")
    if not hunter_key:
        return jsonify({"error": "HUNTER_API_KEY not configured"}), 500

    # If only company name given, try to infer domain
    if not domain and company:
        domain = company.lower().replace(" ", "").replace(",", "") + ".com"

    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": hunter_key,
                "limit": 20,
            },
            timeout=15,
        )
        r.raise_for_status()
        data_resp = r.json().get("data", {})
        emails = data_resp.get("emails", [])
        org_name = data_resp.get("organization", company)
        pattern = data_resp.get("pattern", "")

        preferred = ["recruit", "talent", "acquisition", "hr", "hiring", "careers", "staffing"]
        contacts = []

        for e in emails:
            email = e.get("value", "")
            position = e.get("position", "")
            first = e.get("first_name", "")
            last = e.get("last_name", "")
            confidence = int(e.get("confidence", 0))
            dept = e.get("department", "")

            is_recruiting = any(k in email.lower() or k in position.lower() for k in preferred)

            contacts.append({
                "name": f"{first} {last}".strip(),
                "email": email,
                "position": position,
                "department": dept,
                "confidence": confidence,
                "is_recruiting": is_recruiting,
                "linkedin": e.get("linkedin", ""),
            })

        contacts.sort(key=lambda x: (x["is_recruiting"], x["confidence"]), reverse=True)

        return jsonify({
            "company": org_name,
            "domain": domain,
            "pattern": pattern,
            "total_found": len(contacts),
            "contacts": contacts,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
