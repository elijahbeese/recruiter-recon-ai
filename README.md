# 🔍 Recruiter Recon AI

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-success?style=for-the-badge)
![Version](https://img.shields.io/badge/Version-2.3-blue?style=for-the-badge)

> **AI-assisted job targeting pipeline for cybersecurity professionals.**
> Resume in. Ranked opportunities out.

Instead of manually scanning job boards one posting at a time, this pipeline takes your resume, builds a structured candidate profile, discovers relevant jobs across multiple sources, scores each one against your background using AI, and attempts to identify recruiter contacts — all without touching a browser.

This is a **review-first workflow**, not a blind outreach machine. Every output is designed for human review before any action is taken.

---

## 📋 Table of Contents

- [How It Works](#how-it-works)
- [Pipeline Overview](#pipeline-overview)
- [Discovery Sources](#discovery-sources)
- [Setup](#setup)
- [Running the Pipeline](#running-the-pipeline)
- [Output Files](#output-files)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Version History](#version-history)
- [Roadmap](#roadmap)

---

## ⚙️ How It Works

The pipeline runs in four sequential steps:

```
┌─────────────────────────────────────────────────────────────┐
│                        YOUR RESUME                          │
│                    (PDF / DOCX / TXT)                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  STEP 1 — PROFILE BUILD                     │
│   AI parses resume → structured JSON candidate profile      │
│   Target roles, skills, tools, certs, clearance, queries    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                 STEP 2 — JOB DISCOVERY                      │
│   9 sources queried simultaneously:                         │
│   USAJobs · ClearanceJobs · Indeed · Dice                   │
│   LinkedIn · Greenhouse · Lever · Workday · iCIMS           │
│                                                             │
│   Raw results → relevance filter → heuristic score         │
│   → AI reranking → top 100 jobs selected                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                STEP 3 — AI ENRICHMENT                       │
│   Each job page fetched and parsed                          │
│   AI evaluates: entry-level fit, clearance fit,             │
│   required skills, preferred skills, fit score (0-100),     │
│   outreach angle, red flags                                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 4 — RECRUITER ENRICHMENT                  │
│   Hunter.io queried per company domain                      │
│   Recruiter / talent contacts identified                    │
│   Email confidence scored                                   │
│   Final enriched CSV exported for review                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🌐 Discovery Sources

| Source | Type | What It Finds | Status |
|---|---|---|---|
| **USAJobs API** | Official API | Federal, DoD, cleared cyber roles | ✅ Active |
| **ClearanceJobs** | RSS Feed | Private sector cleared positions | ⚠️ Intermittent |
| **Indeed** | RSS Feed | Broad market, small contractors | ❌ Blocked (403) |
| **Dice** | RSS Feed | Tech/cyber contractor roles | ❌ Dead endpoint |
| **LinkedIn** | HTML Scrape | General job market | ⚠️ Blocked (best-effort) |
| **Greenhouse** | Direct JSON API | Cyber/defense company boards | ✅ Active |
| **Lever** | Direct JSON API | Defense tech company boards | ✅ Active |
| **Workday** | Direct API | Defense prime contractors | 🔧 In progress |
| **iCIMS** | HTML Scrape | Traditional defense contractors | ✅ Partial |

### v2.3 Discovery Results (sample run)

```
usajobs        75 jobs    ████████████████████████████████
greenhouse     84 jobs    ████████████████████████████████████
lever         149 jobs    ████████████████████████████████████████████████████████
icims           5 jobs    ██
─────────────────────────────────────────────────────────────
total         300 raw → 98 final (after AI reranking)
```

---

## 🚀 Setup

### 1. Clone the repository

```bash
git clone https://github.com/elijahbeese/recruiter-recon-ai.git
cd recruiter-recon-ai
```

### 2. Create and activate a virtual environment

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in your API keys:

```env
OPENAI_API_KEY=your_openai_key
HUNTER_API_KEY=your_hunter_key
USAJOBS_API_KEY=your_usajobs_key
USAJOBS_USER_AGENT=your_email@example.com
```

> **Getting API keys:**
> - OpenAI: [platform.openai.com](https://platform.openai.com)
> - Hunter.io: [hunter.io](https://hunter.io) — free tier available
> - USAJobs: [developer.usajobs.gov](https://developer.usajobs.gov/APIRequest/) — free, instant

### 5. Add your resume

Drop your resume into the `resumes/` folder. Supported formats:

```
resumes/resume.pdf
resumes/resume.docx
resumes/resume.txt
```

---

## ▶️ Running the Pipeline

From the repo root with your virtual environment active:

```bash
python scripts/run_v2_2.py
```

The pipeline prints progress for each step. Expected runtime:

| Step | Estimated Time |
|---|---|
| Profile build | 30–60 seconds |
| Job discovery (9 sources) | 3–8 minutes |
| AI enrichment | 10–20 minutes |
| **Total** | **~15–30 minutes** |

> **Tip:** Run it in a dedicated terminal window. It prints progress continuously so you can monitor without interrupting it.

---

## 📁 Output Files

| File | Description |
|---|---|
| `candidate_profile_generated.json` | AI-parsed candidate profile from your resume |
| `output/raw_discovered_jobs.csv` | All discovered jobs before AI reranking (up to 300) |
| `output/discovered_jobs.csv` | AI-reranked top jobs (up to 100) |
| `output/enriched_jobs.csv` | Final output with AI scores + recruiter contacts |

### Enriched CSV columns

| Column | Description |
|---|---|
| `company_name` | Employer name |
| `job_title` | Position title |
| `job_url` | Direct link to job posting |
| `job_location` | Location or Remote |
| `overall_fit_score` | AI fit score 0–100 |
| `entry_level_fit` | yes / maybe / no / unclear |
| `clearance_fit` | required / preferred / eligible / not_mentioned |
| `required_skills` | Skills explicitly required by the posting |
| `preferred_skills` | Nice-to-have skills mentioned |
| `fit_reasoning` | AI explanation of the score |
| `outreach_angle` | Suggested angle for recruiter outreach |
| `red_flags` | Potential concerns flagged by AI |
| `recruiter_contact_name` | Identified recruiter or HR contact |
| `recruiter_contact_email` | Contact email if found |
| `recruiter_contact_confidence` | Hunter.io confidence score |

---

## 🗂️ Repository Structure

```
recruiter-recon-ai/
│
├── resumes/
│   └── resume.pdf                      # Your resume goes here
│
├── scripts/
│   ├── build_profile_v2_0.py           # Resume → candidate profile (AI)
│   ├── parse_resume_v2_0.py            # Resume text extraction
│   ├── discover_jobs_v2_3.py           # Discovery engine (current — 9 sources)
│   ├── recruiter_recon_v1_0.py         # AI scoring + Hunter enrichment
│   └── run_v2_2.py                     # Pipeline orchestrator (current)
│
├── output/                             # Generated — gitignored
│   ├── raw_discovered_jobs.csv
│   ├── discovered_jobs.csv
│   └── enriched_jobs.csv
│
├── assets/                             # Screenshots and diagrams
├── .env                                # Your API keys — never committed
├── .env.example                        # Template for .env
├── requirements.txt
└── README.md
```

---

## 🛠️ Tech Stack

| Component | Library / Service | Purpose |
|---|---|---|
| Language | Python 3.10+ | Core |
| AI | OpenAI API | Resume parsing, job scoring, reranking |
| Job data | USAJobs API | Federal/DoD job discovery |
| Job data | Greenhouse API | Direct ATS board queries |
| Job data | Lever API | Direct ATS board queries |
| Recruiter data | Hunter.io API | Contact identification |
| Parsing | BeautifulSoup4 | HTML job page parsing |
| Data | Pandas | CSV processing |
| HTTP | Requests | API and web requests |
| Config | python-dotenv | Environment variables |
| Domains | tldextract | Company domain parsing |

---

## 📜 Version History

### `v1.0` — Job Enrichment Pipeline
Manual workflow. Provide job URLs in `input_jobs.csv`. The system fetches each posting, runs AI analysis against your candidate profile, and outputs fit scores and recruiter contacts. No automated discovery — jobs must be provided manually.

---

### `v2.0` — Resume-Driven Discovery
Introduced automated resume parsing and candidate profile generation via AI. Discovery engine used DuckDuckGo HTML scraping to find job postings across ATS platforms.

---

### `v2.1` — Discovery Engine Improvements
Improved heuristic scoring with profile alignment. Better ATS source classification. AI-assisted reranking of raw candidates. LinkedIn URL support. Profile-aligned query generation from resume.

---

### `v2.2` — Rate Limiting & Query Budget
Fixed silent discovery failures caused by DuckDuckGo rate limiting. Added randomized sleep between requests, exponential backoff retry logic, removal of wildcard `site:` queries, and a hard query budget cap. Pipeline ran reliably but remained dependent on a single brittle scraping target.

---

### `v2.3` — Multi-Source Discovery Engine *(current)*
Complete replacement of DuckDuckGo scraping with 9 dedicated sources. USAJobs, Greenhouse, and Lever are the primary active sources. LinkedIn, Indeed, and Dice are either blocked or deprecated — being replaced in v2.4.

**Sample run results:** 300 raw jobs → 98 after AI reranking.
Top sources: Lever (149), Greenhouse (84), USAJobs (75).

Notable jobs discovered: NSA, CIA, DISA, Air Force, Booz Allen Hamilton,
Huntress, ThreatLocker, Palantir, Recorded Future.

---

## 🗺️ Roadmap

### `v2.4` — Performance & Source Fixes *(next)*
- Batch AI scoring (groups of 15 instead of 1 per call — 10x faster enrichment)
- Skip Hunter lookups for federal agency domains
- Skip job page fetch when description already populated from ATS source
- Per-job progress counter during enrichment
- Fix Workday company slugs (returned 0 in v2.3)
- Fix ClearanceJobs RSS endpoint
- Replace Indeed and Dice with working alternatives

### `v3.0` — Autonomous Agent *(future)*
- Scheduled runs via cron
- Delta detection — new jobs since last run only
- Email or Slack digest of top opportunities
- Outreach draft generation per job
- Application tracking integration

---

## ⚠️ Disclaimer

This tool is for personal job search use only. It does not automate job applications or recruiter outreach. All discovered data is exported for human review before any action is taken. Respect the terms of service of any platform queried.
