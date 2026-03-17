![Python](https://img.shields.io/badge/python-3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

# recruiter-recon-ai

AI-assisted job targeting pipeline for cybersecurity roles.

This project automates the front end of a job search by turning a resume into a ranked list of relevant opportunities with recruiter contact intelligence — without manually scanning job boards one posting at a time.

This is designed as a **review-first workflow**, not a blind outreach machine.

---

## How It Works

```
Resume (PDF/DOCX)
       ↓
AI Resume Parser
       ↓
Structured Candidate Profile (JSON)
       ↓
Job Discovery Engine
       ↓
Raw Job Dataset
       ↓
AI Fit Scoring & Reranking
       ↓
Recruiter Contact Enrichment (Hunter.io)
       ↓
Enriched CSV — ready for human review
```

---

## Features

- Parses a resume and builds a structured candidate profile using AI
- Generates targeted search queries from the profile automatically
- Discovers job postings across ATS platforms and job boards
- Scores each job against the candidate profile using AI reasoning
- Attempts to identify recruiter contact information via Hunter.io
- Exports a ranked, enriched dataset for manual review

---

## Setup

**Clone the repository**
```bash
git clone https://github.com/elijahbeese/recruiter-recon-ai.git
cd recruiter-recon-ai
```

**Create and activate a virtual environment**
```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Install dependencies**
```bash
pip install -r requirements.txt
```

**Configure environment variables**
```bash
cp .env.example .env
nano .env
```
```
OPENAI_API_KEY=your_openai_key
HUNTER_API_KEY=your_hunter_key
USAJOBS_API_KEY=your_usajobs_key   # v2.3+
BING_API_KEY=your_bing_key         # v2.3+
```

**Add your resume**
```
resumes/resume.pdf   (or .docx / .txt)
```

**Run the pipeline**
```bash
python scripts/run_v2_1.py
```

**Review output**
```
output/discovered_jobs.csv     # All discovered and ranked jobs
output/enriched_jobs.csv       # Jobs with AI scoring + recruiter contacts
```

---

## Repository Structure

```
recruiter-recon-ai/
│
├── resumes/
│   └── resume.pdf
│
├── scripts/
│   ├── build_profile_v2_0.py       # Resume → candidate profile (AI)
│   ├── parse_resume_v2_0.py        # Resume text extraction
│   ├── discover_jobs_v2_2.py       # Job discovery engine (current)
│   ├── recruiter_recon_v1_0.py     # AI scoring + Hunter enrichment
│   └── run_v2_1.py                 # Pipeline orchestrator
│
├── output/
│   ├── raw_discovered_jobs.csv
│   ├── discovered_jobs.csv
│   └── enriched_jobs.csv
│
├── assets/
├── .env.example
├── requirements.txt
└── README.md
```

---

## Tech Stack

| Component | Purpose |
|---|---|
| Python | Core language |
| OpenAI API | Resume parsing, job scoring, AI reranking |
| Hunter.io API | Recruiter contact discovery |
| BeautifulSoup | Job page parsing |
| Pandas | Data processing |
| Requests | HTTP requests |
| python-dotenv | Environment config |
| tldextract | Domain parsing |

---

## Version History

### v1 — Job Enrichment Pipeline
Manual workflow. Provide job URLs in `input_jobs.csv`, the system fetches each posting, runs AI analysis against your candidate profile, and outputs fit scores and recruiter contacts.

Jobs must be provided manually. No automated discovery.

---

### v2.0 — Resume-Driven Discovery (Initial)
Introduced automated resume parsing and candidate profile generation. Discovery engine used DuckDuckGo HTML scraping to find job postings across ATS platforms.

---

### v2.1 — Discovery Engine Improvements
Improved heuristic scoring, better ATS source classification, AI-assisted reranking of raw candidates, LinkedIn URL support, profile-aligned query generation.

---

### v2.2 — Rate Limiting & Query Budget (Current)
Fixed silent discovery failures caused by DuckDuckGo rate limiting. Added randomized sleep between requests, exponential backoff retry logic, wildcard `site:` query removal, and a hard query budget cap before the search loop runs.

**Known limitation:** DuckDuckGo HTML scraping remains brittle and subject to network-level timeouts. v2.3 replaces it entirely.

---

### v2.3 — Direct Source Discovery (In Development)
Replaces DuckDuckGo scraping with direct integrations:

- **USAJobs API** — federal and DoD cybersecurity roles, free API, ideal for cleared candidates
- **Bing Search API** — reliable programmatic search, 1000 free queries/month
- **Greenhouse JSON API** — direct company job board access, no auth required
- **Lever JSON API** — same approach as Greenhouse
- **LinkedIn Jobs** — public job search endpoint

This eliminates dependency on a single brittle scraping target and dramatically improves discovery reliability and volume.

---

## Why This Exists

Hiring pipelines increasingly rely on automated systems to filter candidates before a recruiter reads a single resume. This project applies the same automation logic to the job search itself.

Instead of manually reviewing hundreds of roles, the pipeline identifies which jobs are worth pursuing and prepares structured outreach intelligence — ready for human review before any action is taken.
