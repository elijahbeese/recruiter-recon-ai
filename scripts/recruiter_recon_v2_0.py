"""
recruiter_recon_v2_0.py
------------------------
Recruiter Recon AI — Enrichment Engine v2.0

Changes from v1.0:
  - Batched AI scoring: 15 jobs per API call instead of 1 (10x faster)
  - Pre-enrichment relevance filter: kills financial, physical security,
    admin, and other irrelevant roles before wasting API calls on them
  - Clearance context passed explicitly to AI so it stops flagging
    'clearance not stated' for a candidate with an active Secret
  - Hunter skipped entirely for .gov domains
  - Junk contact filter: jobs@usajobs.gov and generic emails removed
  - Progress counter: [12/98] instead of just scrolling names
  - Generates both CSV and HTML report output
"""

# ─────────────────────────────────────────────
# SECTION 1: IMPORTS & CONSTANTS
# ─────────────────────────────────────────────

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

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

AI_BATCH_SIZE = 15

IRRELEVANT_TITLE_PATTERNS = [
    r"financial analyst", r"budget analyst", r"contract specialist",
    r"procurement", r"physical security", r"security guard",
    r"security officer", r"administrative", r"human resources",
    r"logistics", r"supply chain", r"attorney", r"paralegal",
    r"accountant", r"auditor", r"economist", r"statistician",
    r"public affairs", r"communications specialist", r"graphic design",
    r"web content", r"librarian", r"nurse", r"medical", r"dental",
    r"facilities", r"food service", r"sales representative", r"marketing",
    r"program analyst",  # catches non-cyber program management roles
]

SENIOR_TITLE_PATTERNS = [
    r"\bsenior\b", r"\bsr\.\b", r"\blead\b", r"\bprincipal\b",
    r"\bstaff\b", r"\bmanager\b", r"\bdirector\b", r"\barchitect\b",
    r"\bsupervisor\b", r"\bchief\b", r"\bhead of\b", r"\bvp\b",
    r"nh-04", r"nh-05", r"gs-13", r"gs-14", r"gs-15",
]

SKIP_HUNTER_DOMAINS = [".gov", ".mil", "usajobs.gov"]

JUNK_CONTACT_EMAILS = [
    "jobs@usajobs.gov", "noreply@", "no-reply@",
    "donotreply@", "apply@", "info@usajobs",
]


# ─────────────────────────────────────────────
# SECTION 2: CONFIG
# ─────────────────────────────────────────────

class Config:
    def __init__(self) -> None:
        load_dotenv()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.hunter_api_key = os.getenv("HUNTER_API_KEY", "").strip()
        self.output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "20"))
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
        self.min_recruiter_confidence = int(os.getenv("MIN_RECRUITER_CONFIDENCE", "70"))
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is missing in .env")
        self.output_dir.mkdir(parents=True, exist_ok=True)


def load_candidate_profile() -> Dict[str, Any]:
    for path in ["candidate_profile_generated.json", "candidate_profile.json"]:
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("No candidate profile found.")


def read_input_data() -> pd.DataFrame:
    if not Path("input_jobs.csv").exists():
        raise FileNotFoundError("input_jobs.csv not found.")
    return pd.read_csv("input_jobs.csv").fillna("")


# ─────────────────────────────────────────────
# SECTION 3: PRE-ENRICHMENT FILTERING
# ─────────────────────────────────────────────

def is_irrelevant(title: str) -> bool:
    t = title.lower()
    return any(re.search(p, t) for p in IRRELEVANT_TITLE_PATTERNS)


def is_too_senior(title: str) -> bool:
    t = title.lower()
    return any(re.search(p, t) for p in SENIOR_TITLE_PATTERNS)


def pre_filter(df: pd.DataFrame) -> pd.DataFrame:
    original = len(df)
    irr = df["job_title"].apply(is_irrelevant)
    sen = df["job_title"].apply(is_too_senior)
    df = df[~irr & ~sen].copy()
    print(f"[Filter] {original} in → removed {irr.sum()} irrelevant + {sen.sum()} senior → {len(df)} remaining")
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────
# SECTION 4: JOB PAGE FETCHING
# ─────────────────────────────────────────────

def fetch_job_text(url: str, timeout: int, existing_notes: str = "") -> str:
    if existing_notes and len(existing_notes.strip()) > 150:
        return existing_notes
    if not url or not url.startswith(("http://", "https://")):
        return existing_notes
    if "usajobs.gov" in url:
        return existing_notes
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except requests.RequestException:
        return existing_notes
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "img", "footer", "nav"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
    return text[:15000]


# ─────────────────────────────────────────────
# SECTION 5: BATCHED AI ENRICHMENT
# ─────────────────────────────────────────────

def build_clearance_context(profile: Dict[str, Any]) -> str:
    raw = profile.get("clearance_relevance", "").lower()
    if "secret" in raw and ("top secret" in raw or "ts" in raw) and ("adjudication" in raw or "progress" in raw):
        return "Active Secret clearance. TS adjudication in progress. Security+ meets DoD 8570 IAT II."
    if "secret" in raw:
        return "Active Secret clearance. Security+ meets DoD 8570 IAT II."
    return profile.get("clearance_relevance", "")[:300]


def empty_analysis(reason: str) -> Dict[str, Any]:
    return {
        "entry_level_fit": "unclear", "clearance_fit": "unclear",
        "overall_fit_score": 0, "required_skills": [], "preferred_skills": [],
        "fit_reasoning": reason, "outreach_angle": "", "us_based_company": "unclear",
        "likely_job_family": "", "red_flags": ["analysis_failed"],
    }


def ai_batch_enrich(
    client: OpenAI,
    model: str,
    profile: Dict[str, Any],
    batch: List[Dict[str, Any]],
    job_texts: List[str],
) -> List[Dict[str, Any]]:
    clearance = build_clearance_context(profile)

    batch_input = [
        {
            "index": i,
            "company": row.get("company_name", ""),
            "title": row.get("job_title", ""),
            "location": row.get("job_location", ""),
            "job_text": text[:3000],
        }
        for i, (row, text) in enumerate(zip(batch, job_texts))
    ]

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "index":             {"type": "integer"},
                        "entry_level_fit":   {"type": "string", "enum": ["yes", "maybe", "no", "unclear"]},
                        "clearance_fit":     {"type": "string", "enum": ["required", "preferred", "eligible", "not_mentioned", "unclear"]},
                        "overall_fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "required_skills":   {"type": "array", "items": {"type": "string"}},
                        "preferred_skills":  {"type": "array", "items": {"type": "string"}},
                        "fit_reasoning":     {"type": "string"},
                        "outreach_angle":    {"type": "string"},
                        "us_based_company":  {"type": "string", "enum": ["yes", "no", "unclear"]},
                        "likely_job_family": {"type": "string"},
                        "red_flags":         {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "index", "entry_level_fit", "clearance_fit", "overall_fit_score",
                        "required_skills", "preferred_skills", "fit_reasoning",
                        "outreach_angle", "us_based_company", "likely_job_family", "red_flags",
                    ],
                },
            }
        },
        "required": ["results"],
    }

    instructions = (
        "You are a precise cybersecurity job-fit analysis engine. "
        f"CANDIDATE CLEARANCE: {clearance} "
        "Do NOT flag Secret clearance as missing for roles requiring Secret or below — candidate holds it. "
        "Only flag clearance concern if role requires TS/SCI or polygraph. "
        "Score entry_level_fit 'yes' only for genuine 0-3 year roles. "
        "Score conservatively. Do not invent experience not in the profile."
    )

    prompt = f"""
CANDIDATE:
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

JOBS:
{json.dumps(batch_input, indent=2)}

Return one result per index. Score: 80-100=strong, 60-79=good, 40-59=moderate, 0-39=poor.
"""

    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "batch_job_analysis", "schema": schema}},
        )
        parsed = json.loads(response.output_text)
        indexed = {r["index"]: r for r in parsed.get("results", [])}
        return [indexed.get(i, empty_analysis(f"Missing index {i}")) for i in range(len(batch))]
    except Exception as exc:
        print(f"  [AI] Batch failed: {exc}")
        return [empty_analysis(str(exc)) for _ in batch]


# ─────────────────────────────────────────────
# SECTION 6: HUNTER ENRICHMENT
# ─────────────────────────────────────────────

def skip_hunter(domain: str) -> bool:
    if not domain:
        return True
    return any(domain.lower().endswith(s) for s in SKIP_HUNTER_DOMAINS)


def is_junk_email(email: str) -> bool:
    if not email:
        return True
    return any(j in email.lower() for j in JUNK_CONTACT_EMAILS)


def normalize_domain(raw: str, url: str) -> str:
    raw = (raw or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    if raw:
        return raw
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}" if ext.domain and ext.suffix else ""


def hunter_search(domain: str, key: str) -> Dict:
    if not domain or not key:
        return {}
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": key, "department": "hr"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def hunter_find(domain: str, name: str, key: str) -> Dict:
    if not domain or not name or not key:
        return {}
    parts = name.strip().split()
    if len(parts) < 2:
        return {}
    try:
        r = requests.get(
            "https://api.hunter.io/v2/email-finder",
            params={"domain": domain, "first_name": parts[0], "last_name": parts[-1], "api_key": key},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def best_contact(row: Dict, domain_result: Dict, finder_result: Dict, min_conf: int) -> Dict:
    name_input = (row.get("recruiter_name") or "").strip()
    preferred = ["recruit", "talent", "acquisition", "careers", "hr", "staffing"]

    if finder_result.get("data"):
        d = finder_result["data"]
        email = d.get("email", "")
        score = int(d.get("score") or 0)
        if email and not is_junk_email(email) and score >= min_conf:
            return {
                "recruiter_contact_name": f"{d.get('first_name','')} {d.get('last_name','')}".strip(),
                "recruiter_contact_email": email,
                "recruiter_contact_type": "named_recruiter",
                "recruiter_contact_confidence": score,
                "recruiter_contact_source": "hunter_email_finder",
            }

    best = None
    best_score = -1
    for item in domain_result.get("data", {}).get("emails", []):
        email = (item.get("value") or "").lower()
        pos = (item.get("position") or "").lower()
        conf = int(item.get("confidence") or 0)
        if is_junk_email(email):
            continue
        boost = sum(20 for k in preferred if k in email or k in pos)
        total = conf + boost
        if total > best_score:
            best_score = total
            fn = item.get("first_name") or ""
            ln = item.get("last_name") or ""
            best = {
                "recruiter_contact_name": f"{fn} {ln}".strip() or name_input,
                "recruiter_contact_email": email,
                "recruiter_contact_type": "recruiting_or_hr_contact",
                "recruiter_contact_confidence": total,
                "recruiter_contact_source": "hunter_domain_search",
            }

    return best or {
        "recruiter_contact_name": name_input,
        "recruiter_contact_email": "",
        "recruiter_contact_type": "none_found",
        "recruiter_contact_confidence": 0,
        "recruiter_contact_source": "none",
    }


# ─────────────────────────────────────────────
# SECTION 7: HTML REPORT
# ─────────────────────────────────────────────

def score_color(score: int) -> str:
    if score >= 70: return "#2d6a4f"
    if score >= 40: return "#b5620a"
    return "#9b2226"


def generate_html(results: List[Dict], path: Path) -> None:
    sorted_r = sorted(results, key=lambda x: int(x.get("overall_fit_score", 0)), reverse=True)

    rows = ""
    for r in sorted_r:
        score = int(r.get("overall_fit_score", 0))
        color = score_color(score)
        email = r.get("recruiter_contact_email", "")
        contact_name = r.get("recruiter_contact_name", "")
        contact_html = f'{contact_name}<br><small><a href="mailto:{email}">{email}</a></small>' if email else (contact_name or "—")
        ef = r.get("entry_level_fit", "")
        ef_color = {"yes": "#2d6a4f", "maybe": "#b5620a", "no": "#9b2226"}.get(ef, "#8b949e")
        cf = r.get("clearance_fit", "")
        cf_color = {"required": "#58a6ff", "preferred": "#388bfd", "eligible": "#2d6a4f", "not_mentioned": "#8b949e"}.get(cf, "#8b949e")
        reasoning = (r.get("fit_reasoning") or "")[:250]
        red_flags = r.get("red_flags", "")

        rows += f"""<tr>
            <td><strong style="color:{color};font-size:1.2em">{score}</strong></td>
            <td><a href="{r.get('job_url','#')}" target="_blank">{r.get('job_title','')}</a></td>
            <td>{r.get('company_name','')}</td>
            <td>{r.get('job_location','')}</td>
            <td><span style="color:{ef_color};font-weight:bold">{ef}</span></td>
            <td><span style="color:{cf_color}">{cf}</span></td>
            <td style="font-size:0.85em">{contact_html}</td>
            <td style="font-size:0.82em;color:#8b949e">{reasoning}{"..." if len(r.get("fit_reasoning","")) > 250 else ""}</td>
        </tr>"""

    strong = sum(1 for r in results if int(r.get("overall_fit_score", 0)) >= 70)
    entry = sum(1 for r in results if r.get("entry_level_fit") == "yes")
    contacts = sum(1 for r in results if r.get("recruiter_contact_email", ""))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Recruiter Recon AI — Results</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;padding:24px}}
h1{{color:#58a6ff;font-size:1.6em;margin-bottom:6px}}
.subtitle{{color:#8b949e;margin-bottom:20px;font-size:0.9em}}
.stats{{display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap}}
.stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 22px;text-align:center;min-width:120px}}
.stat-n{{font-size:2em;font-weight:700;color:#58a6ff}}
.stat-l{{color:#8b949e;font-size:0.8em;margin-top:2px}}
.controls{{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}}
.search{{flex:1;min-width:200px;padding:9px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#e6edf3;font-size:0.95em}}
.filter{{padding:9px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#e6edf3;font-size:0.9em}}
table{{width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden;font-size:0.88em}}
th{{background:#21262d;padding:11px 10px;text-align:left;color:#8b949e;font-size:0.8em;text-transform:uppercase;letter-spacing:.05em;cursor:pointer;white-space:nowrap}}
th:hover{{background:#30363d;color:#e6edf3}}
td{{padding:10px;border-bottom:1px solid #21262d;vertical-align:top}}
tr:hover td{{background:#1c2128}}
a{{color:#58a6ff;text-decoration:none}}
a:hover{{text-decoration:underline}}
small{{color:#8b949e}}
.hidden{{display:none}}
</style>
</head>
<body>
<h1>🔍 Recruiter Recon AI</h1>
<div class="subtitle">v2.4 — Generated results ready for review</div>
<div class="stats">
  <div class="stat"><div class="stat-n">{len(results)}</div><div class="stat-l">Total Jobs</div></div>
  <div class="stat"><div class="stat-n" style="color:#2d6a4f">{strong}</div><div class="stat-l">Strong Fits (70+)</div></div>
  <div class="stat"><div class="stat-n">{entry}</div><div class="stat-l">Entry Level ✓</div></div>
  <div class="stat"><div class="stat-n">{contacts}</div><div class="stat-l">Recruiter Contacts</div></div>
</div>
<div class="controls">
  <input class="search" type="text" id="searchInput" placeholder="Search jobs, companies, locations..." oninput="applyFilters()">
  <select class="filter" id="entryFilter" onchange="applyFilters()">
    <option value="">All Entry Level</option>
    <option value="yes">Yes</option>
    <option value="maybe">Maybe</option>
    <option value="no">No</option>
  </select>
  <select class="filter" id="clearanceFilter" onchange="applyFilters()">
    <option value="">All Clearance</option>
    <option value="required">Required</option>
    <option value="preferred">Preferred</option>
    <option value="eligible">Eligible</option>
    <option value="not_mentioned">Not Mentioned</option>
  </select>
  <select class="filter" id="scoreFilter" onchange="applyFilters()">
    <option value="0">All Scores</option>
    <option value="70">70+ (Strong)</option>
    <option value="40">40+ (Moderate)</option>
  </select>
</div>
<table id="resultsTable">
<thead><tr>
  <th onclick="sortTable(0)">Score ↕</th>
  <th onclick="sortTable(1)">Job Title ↕</th>
  <th onclick="sortTable(2)">Company ↕</th>
  <th onclick="sortTable(3)">Location ↕</th>
  <th onclick="sortTable(4)">Entry ↕</th>
  <th onclick="sortTable(5)">Clearance ↕</th>
  <th>Recruiter Contact</th>
  <th>Fit Summary</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
<script>
function applyFilters(){{
  const search=document.getElementById('searchInput').value.toLowerCase();
  const entry=document.getElementById('entryFilter').value;
  const clearance=document.getElementById('clearanceFilter').value;
  const minScore=parseInt(document.getElementById('scoreFilter').value)||0;
  document.querySelectorAll('#resultsTable tbody tr').forEach(row=>{{
    const text=row.textContent.toLowerCase();
    const score=parseInt(row.cells[0].textContent)||0;
    const entryVal=row.cells[4].textContent.trim();
    const clearVal=row.cells[5].textContent.trim();
    const show=(
      text.includes(search)&&
      (entry===''||entryVal===entry)&&
      (clearance===''||clearVal===clearance)&&
      score>=minScore
    );
    row.classList.toggle('hidden',!show);
  }});
}}
function sortTable(col){{
  const table=document.getElementById('resultsTable');
  const tbody=table.querySelector('tbody');
  const rows=Array.from(tbody.querySelectorAll('tr'));
  const asc=table.dataset.col==col&&table.dataset.dir=='asc';
  rows.sort((a,b)=>{{
    const av=a.cells[col].textContent.trim();
    const bv=b.cells[col].textContent.trim();
    const an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn))return asc?an-bn:bn-an;
    return asc?av.localeCompare(bv):bv.localeCompare(av);
  }});
  rows.forEach(r=>tbody.appendChild(r));
  table.dataset.col=col;
  table.dataset.dir=asc?'desc':'asc';
}}
</script>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")
    print(f"[Output] HTML report: {path}")


# ─────────────────────────────────────────────
# SECTION 8: MAIN PIPELINE
# ─────────────────────────────────────────────

def main() -> None:
    config = Config()
    client = OpenAI(api_key=config.openai_api_key)
    profile = load_candidate_profile()
    df = read_input_data()

    print(f"\n[Enrichment v2.0] {len(df)} jobs loaded")
    df = pre_filter(df)
    total = len(df)
    results = []

    for batch_start in range(0, total, AI_BATCH_SIZE):
        batch_end = min(batch_start + AI_BATCH_SIZE, total)
        batch_rows = [df.iloc[i].to_dict() for i in range(batch_start, batch_end)]

        print(f"\n[Batch {batch_start + 1}–{batch_end}/{total}] Fetching pages + AI scoring...")

        job_texts = [
            fetch_job_text(
                url=r.get("job_url", ""),
                timeout=config.request_timeout,
                existing_notes=r.get("notes", ""),
            )
            for r in batch_rows
        ]

        analyses = ai_batch_enrich(client, config.openai_model, profile, batch_rows, job_texts)

        for i, (row, analysis) in enumerate(zip(batch_rows, analyses)):
            company = (row.get("company_name") or "").strip()
            title = (row.get("job_title") or "").strip()
            url = (row.get("job_url") or "").strip()
            domain = normalize_domain(row.get("company_domain", ""), url)
            recruiter_name = (row.get("recruiter_name") or "").strip()

            print(f"  [{batch_start + i + 1}/{total}] {company} | {title}")

            if skip_hunter(domain):
                contact = {
                    "recruiter_contact_name": "",
                    "recruiter_contact_email": "",
                    "recruiter_contact_type": "skipped_gov_domain",
                    "recruiter_contact_confidence": 0,
                    "recruiter_contact_source": "none",
                }
            else:
                dr = hunter_search(domain, config.hunter_api_key)
                fr = hunter_find(domain, recruiter_name, config.hunter_api_key)
                contact = best_contact(row, dr, fr, config.min_recruiter_confidence)

            results.append({
                "company_name": company,
                "company_domain": domain,
                "job_title": title,
                "job_url": url,
                "job_location": row.get("job_location", ""),
                "recruiter_contact_name": contact.get("recruiter_contact_name", ""),
                "recruiter_contact_email": contact.get("recruiter_contact_email", ""),
                "recruiter_contact_type": contact.get("recruiter_contact_type", ""),
                "recruiter_contact_confidence": contact.get("recruiter_contact_confidence", ""),
                "recruiter_contact_source": contact.get("recruiter_contact_source", ""),
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
                "verification_status": "pending_manual_review",
            })

    # ── CSV ────────────────────────────────────────────────────────────────────
    csv_path = config.output_dir / "enriched_jobs.csv"
    pd.DataFrame(results).to_csv(csv_path, index=False)
    print(f"\n[Output] CSV: {csv_path}")

    # ── HTML ───────────────────────────────────────────────────────────────────
    html_path = config.output_dir / "enriched_jobs.html"
    generate_html(results, html_path)

    strong = sum(1 for r in results if int(r.get("overall_fit_score", 0)) >= 70)
    contacts = sum(1 for r in results if r.get("recruiter_contact_email", ""))

    print(f"\n{'═' * 60}")
    print(f"  Done. {len(results)} jobs enriched.")
    print(f"  Strong fits (70+): {strong}")
    print(f"  Recruiter contacts: {contacts}")
    print(f"  Open: {html_path}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
