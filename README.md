# SITREP — Job Intelligence Platform

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-API-412991?style=for-the-badge&logo=openai&logoColor=white)
![Railway](https://img.shields.io/badge/Deployed-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Version](https://img.shields.io/badge/Version-3.1-6366f1?style=for-the-badge)

> **Situation Report. Job Intelligence. Built for cybersecurity professionals.**
> Resume in. Mission-ready opportunities out.

SITREP is a local and cloud-hosted AI-powered job intelligence platform that automates the front end of a cybersecurity job search. It discovers relevant roles across 9 sources simultaneously, scores each one against your resume using AI, identifies recruiter contacts, and presents everything in a full-featured web dashboard — accessible locally or from anywhere via Railway.

This is a **review-first workflow**, not a blind outreach machine. Every output is designed for human review before any action is taken.

**Live demo:** `web-production-f0cfe.up.railway.app`

---

## 📋 Table of Contents

- [How It Works](#how-it-works)
- [SITREP Dashboard](#sitrep-dashboard)
- [Discovery Sources](#discovery-sources)
- [Company Coverage](#company-coverage)
- [Setup](#setup)
- [Running the Pipeline](#running-the-pipeline)
- [Running the Dashboard](#running-the-dashboard)
- [Deploying to Railway](#deploying-to-railway)
- [Output Files](#output-files)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Version History](#version-history)
- [Roadmap](#roadmap)

---

## ⚙️ How It Works

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
│   Target roles · Skills · Tools · Certs · Clearance         │
│   Location preferences · Search query generation            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 2 — JOB DISCOVERY (v2.5)                  │
│                                                             │
│   9 sources queried in parallel via ThreadPoolExecutor:     │
│   JSearch · Adzuna · Greenhouse (100+ cos) · Lever (54 cos) │
│   The Muse · USAJobs API · ClearanceJobs · iCIMS            │
│                                                             │
│   → Senior role filter                                      │
│   → Relevance filter (non-cyber removed)                    │
│   → Heuristic scoring (source quality + skill overlap)      │
│   → Company + title deduplication                           │
│   → AI reranking — only 50+ scores passed forward           │
│   → Delta detection — seen URLs tracked between runs        │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 3 — AI ENRICHMENT (v2.0)                  │
│                                                             │
│   Batched AI scoring (15 jobs per API call)                 │
│   · Entry-level fit · Clearance fit · Score (0-100)         │
│   · Required skills · Preferred skills · Red flags          │
│   · Fit reasoning · Outreach angle · Salary estimate        │
│                                                             │
│   Recruiter enrichment (Hunter.io):                         │
│   · Named recruiter + email + confidence score              │
│   · Skips .gov/.mil · Filters junk emails                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 4 — SITREP DASHBOARD (v3.1)               │
│                                                             │
│   Flask web app — local or Railway (public URL)             │
│   Session-based auth · All features protected by login      │
│                                                             │
│   · Mission Dashboard · Job Lookup · Recruiter Finder       │
│   · Pipeline Runner · App Tracker · Outreach AI             │
│   · Gap Analyzer · Interview Prep · History · Alerts        │
│   · Profile Editor                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🖥️ SITREP Dashboard

### Mission Dashboard

Browse all enriched jobs with live charts showing score distribution, source breakdown, and clearance fit. Filter by score, entry-level status, clearance requirement, and source. Search across all fields. Click any job card to open a full detail modal with fit reasoning, required skills, red flags, recruiter contact, and one-click outreach generation.

![Mission Dashboard](assets/screenshots/dashboard.png)

---

### Job Detail Modal

Full intelligence on any role — fit score, entry-level and clearance classification, required and preferred skills, outreach angle, red flags, and recruiter contact. One click to open the posting or generate a cold email.

![Job Detail Modal](assets/screenshots/job-detail.png)

---

### Recruiter Finder

Enter a company name or domain. Returns all identified recruiting and HR contacts sorted by relevance, with names, emails, job titles, and Hunter.io confidence scores. Results cached for 7 days to preserve API quota.

![Recruiter Finder](assets/screenshots/recruiter-finder.png)

---

### Application Tracker

Kanban board with six columns: Discovered, Targeted, Applied, Interviewing, Offer, Rejected. Drag cards between columns to update status. Click any card to add notes and application date. All changes persist between sessions.

![Application Tracker](assets/screenshots/tracker.png)

---

### Outreach AI

Select from discovered jobs via dropdown or fill in manually. Generates a tailored cold outreach email using your actual profile and the specific role — references real tech stack, clearance, and experience. Three tone options. Includes subject line, email body, follow-up line, and key hooks. All generated emails saved to history automatically.

![Outreach AI](assets/screenshots/outreach.png)

---

### Gap Analyzer

Select any job and get a detailed gap analysis — readiness score, strong matches, specific skill gaps with importance ratings, concrete actions to close each gap, free resources and labs, and exact resume bullet points you can add right now.

---

### Interview Prep

Select any job and generate complete interview preparation grounded in your actual experience — technical questions with suggested answers, behavioral questions in STAR format, smart questions to ask the interviewer, key talking points, red flags to address proactively, and salary negotiation advice.

---

### History

Full persistent history of all generated outreach emails and job lookups. Mark emails as sent, track responses, copy or open in mail client directly from history.

---

### My Profile

Tag-based UI for editing all profile fields — target roles, skills, tools, certifications, location preferences, industries, and search queries. Clearance status prominently displayed. All changes save back to JSON.

![My Profile](assets/screenshots/profile.png)

---

### Pipeline Runner

Launch the full discovery and enrichment pipeline from the browser. Live terminal log streams in real time via Server-Sent Events. Fires an alert on completion.

![Pipeline Runner](assets/screenshots/pipeline.png)

---

## 🌐 Discovery Sources

| Source | Type | What It Finds | Status |
|---|---|---|---|
| **JSearch (RapidAPI)** | Aggregator API | LinkedIn, Indeed, Glassdoor, ZipRecruiter | ✅ Active |
| **Adzuna API** | Aggregator API | 15+ job boards with full descriptions | ✅ Active |
| **Greenhouse** | Direct ATS API | 100+ cyber/defense/private sector boards | ✅ Active |
| **Lever** | Direct ATS API | 54 defense tech/cyber company boards | ✅ Active |
| **USAJobs API** | Official API | Federal, DoD, cleared cyber roles | ✅ Active |
| **ClearanceJobs** | RSS Feed | Private sector cleared positions | ⚠️ Intermittent |
| **The Muse** | Public API | Tech/cyber company jobs | ⚠️ Intermittent |
| **iCIMS** | HTML Scrape | Traditional defense contractors | ✅ Partial |
| **Workday** | Direct API | Defense prime + enterprise employers | 🔧 Partial |

---

## 🏢 Company Coverage

**Defense & Government Contractors**
Leidos · Northrop Grumman · L3Harris · BAE Systems · General Dynamics · Lockheed Martin · Boeing · Raytheon · SAIC · Peraton · Parsons · Amentum · Booz Allen Hamilton · ManTech · CACI · MITRE · Telos

**Pure-Play Cybersecurity**
CrowdStrike · SentinelOne · Huntress · ThreatLocker · Expel · Red Canary · Blumira · Dragos · Claroty · Recorded Future · Flashpoint · Vectra · Exabeam · Anomali · Cybereason · Arctic Wolf · DeepWatch · NetSPI · Bishop Fox · NCC Group · Mandiant · Kroll · Secureworks · Trellix · Rapid7 · Tenable · Qualys · Palo Alto Networks · Fortinet · BeyondTrust · CyberArk · Okta · Wiz · Lacework · Axonius · Deepwatch · Coalfire · Optiv

**Banks & Financial Services**
Capital One · USAA · JPMorgan Chase · Bank of America · Citigroup · Wells Fargo · Raymond James · Fidelity · Charles Schwab · Visa · Mastercard · PayPal · Stripe · Robinhood · Coinbase · Brex · Plaid

**Big Tech**
Microsoft · Google · Amazon · Apple · Meta · IBM · Oracle · Salesforce · ServiceNow · Splunk · Cloudflare · Datadog · Elastic · Palantir · Anduril

**Consulting / Big 4**
Deloitte · PwC · KPMG · EY · Accenture

**Healthcare**
HCA Healthcare · AdventHealth · BayCare · Cigna · UnitedHealth · Humana

**Critical Infrastructure / Energy**
NextEra Energy · Duke Energy · Dominion Energy · Constellation Energy · AECOM · Jacobs

**Telecom**
Verizon · AT&T · T-Mobile · Comcast · Lumen

**Tampa / Florida Specific**
Raymond James · Tech Data · USAA Tampa · Catalina · Verizon Business

---

## 🚀 Setup

### 1. Clone the repository

```bash
git clone https://github.com/elijahbeese/sitrep.git
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

```env
# Required
OPENAI_API_KEY=your_openai_key
HUNTER_API_KEY=your_hunter_key
USAJOBS_API_KEY=your_usajobs_key
USAJOBS_USER_AGENT=your_email@example.com

# Job aggregators
JSEARCH_API_KEY=your_rapidapi_key
ADZUNA_APP_ID=your_adzuna_id
ADZUNA_APP_KEY=your_adzuna_key

# SITREP login
SITREP_USERNAME=your_username
SITREP_PASSWORD=your_password
SECRET_KEY=your_random_secret_key
```

> **Getting API keys:**
> - **OpenAI:** [platform.openai.com](https://platform.openai.com)
> - **Hunter.io:** [hunter.io](https://hunter.io) — free tier available
> - **USAJobs:** [developer.usajobs.gov](https://developer.usajobs.gov/APIRequest/) — free, instant
> - **JSearch:** [rapidapi.com/letscrape](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) — free tier 200 req/month
> - **Adzuna:** [developer.adzuna.com](https://developer.adzuna.com/signup) — free tier available

### 5. Add your resume

```
resumes/resume.pdf     ← preferred
resumes/resume.docx
resumes/resume.txt
```

---

## ▶️ Running the Pipeline

```bash
python scripts/run_v2_5.py
```

Or launch from the SITREP dashboard using the **Run Pipeline** page.

| Step | What Happens | Estimated Time |
|---|---|---|
| Profile Build | AI parses resume → JSON profile | 30–60 sec |
| Job Discovery | 9 sources parallel, 500 raw → 50+ threshold | 1–2 min |
| AI Enrichment | Batched scoring + Hunter contacts | 3–5 min |
| **Total** | | **~5 min** |

---

## 🌐 Running the Dashboard

```bash
python run_app.py
```

Browser opens automatically at `http://127.0.0.1:5000`. Log in with your credentials from `.env`.

> **Note:** Use `127.0.0.1:5000` in Chrome. Disable AirPlay Receiver in System Settings if port 5000 is blocked on Mac.

---

## 🚂 Deploying to Railway

1. Push your repo to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
3. Select `recruiter-recon-ai`
4. Add all environment variables from `.env` in the **Variables** tab
5. Add `SECRET_KEY` as a Railway variable
6. Click **Settings** → **Networking** → your public domain is auto-generated
7. Every `git push` triggers an automatic redeploy

> **Note:** Railway is stateless — `output/enriched_jobs.csv` must be committed to GitHub for the dashboard to show jobs. Run the pipeline locally and push the output folder after each run.

---

## 📁 Output Files

| File | Description | Persists |
|---|---|---|
| `candidate_profile_generated.json` | AI-parsed candidate profile | ✅ Yes |
| `output/raw_discovered_jobs.csv` | All discovered jobs pre-reranking | Until next run |
| `output/discovered_jobs.csv` | 50+ scored jobs passed to enrichment | Until next run |
| `output/enriched_jobs.csv` | Full enriched dataset — dashboard source | Until next run |
| `output/enriched_jobs.html` | Standalone browser report | Until next run |
| `output/tracker.json` | Application tracker state | ✅ Persists |
| `output/outreach_history.json` | All generated outreach emails | ✅ Persists |
| `output/lookup_history.json` | Job URL lookup history (last 50) | ✅ Persists |
| `output/recruiter_cache.json` | Hunter.io results cached 7 days | ✅ Persists |
| `output/seen_urls.json` | Delta detection — all seen job URLs | ✅ Persists |
| `output/alerts.json` | Pipeline completion alerts | ✅ Persists |

---

## 🗂️ Repository Structure

```
recruiter-recon-ai/
│
├── resumes/
│   └── resume.pdf
│
├── scripts/
│   ├── build_profile_v2_0.py       # Resume → candidate profile (AI)
│   ├── parse_resume_v2_0.py        # Resume text extraction
│   ├── discover_jobs_v2_5.py       # Discovery engine — 9 sources parallel
│   ├── recruiter_recon_v2_0.py     # Enrichment — batched AI + Hunter
│   └── run_v2_5.py                 # Pipeline orchestrator
│
├── app/                            # SITREP Flask dashboard
│   ├── __init__.py                 # App factory — registers all blueprints
│   ├── auth.py                     # Login helper + login_required decorator
│   ├── data.py                     # Centralized persistence layer
│   └── routes/
│       ├── auth.py                 # /login /logout
│       ├── dashboard.py            # / — main dashboard
│       ├── lookup.py               # /lookup — manual job URL analysis
│       ├── recruiter.py            # /recruiter — contact finder
│       ├── pipeline.py             # /pipeline — run pipeline from browser
│       ├── tracker.py              # /tracker — kanban board
│       ├── outreach.py             # /outreach — email generator
│       ├── gap.py                  # /gap — resume gap analyzer
│       ├── interview.py            # /interview — interview prep
│       ├── history.py              # /history — outreach + lookup history
│       ├── alerts.py               # /alerts — pipeline alerts
│       └── profile.py             # /profile — candidate profile editor
│
├── app/templates/                  # Jinja2 HTML templates (12 pages)
├── app/static/css/main.css         # Full SITREP stylesheet
├── app/static/js/main.js           # Shared JS utilities
│
├── run_app.py                      # Entry point — local + Railway
├── Procfile                        # Railway/Gunicorn config
├── railway.json                    # Railway deployment config
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
│
├── output/                         # Generated per run (commit for Railway)
└── assets/screenshots/             # README screenshots
```

---

## 🛠️ Tech Stack

| Component | Library / Service | Purpose |
|---|---|---|
| Language | Python 3.10+ | Core |
| Web Framework | Flask 3.0+ | SITREP dashboard |
| Production Server | Gunicorn | Railway deployment |
| AI | OpenAI API (GPT-4o) | Resume parsing, scoring, outreach, gap analysis, interview prep |
| Job Aggregator | JSearch (RapidAPI) | LinkedIn, Indeed, Glassdoor, ZipRecruiter |
| Job Aggregator | Adzuna API | 15+ job boards |
| Job Data | Greenhouse API | 100+ company ATS boards |
| Job Data | Lever API | 54 company ATS boards |
| Job Data | USAJobs API | Federal/DoD roles |
| Recruiter Data | Hunter.io API | Contact identification + caching |
| Parsing | BeautifulSoup4 | HTML job page parsing |
| Parallelism | ThreadPoolExecutor | Concurrent source fetching |
| Data | Pandas | CSV processing |
| HTTP | Requests | API and web requests |
| Deployment | Railway | Cloud hosting + auto-deploy |
| Config | python-dotenv | Environment variables |

---

## 📜 Version History

### `v1.0` — Job Enrichment Pipeline
Manual workflow. Provide job URLs in `input_jobs.csv`. AI scores each posting and outputs recruiter contacts. No automated discovery.

### `v2.0` — Resume-Driven Discovery
Automated resume parsing and AI candidate profile. DuckDuckGo HTML scraping for job discovery.

### `v2.1` — Discovery Improvements
Improved heuristic scoring, AI-assisted reranking, LinkedIn URL support, profile-aligned query generation.

### `v2.2` — Rate Limiting & Query Budget
Fixed DuckDuckGo rate limiting with backoff, randomized sleep, hard query budget cap.

### `v2.3` — Multi-Source Discovery Engine
Replaced DuckDuckGo with 9 dedicated sources. USAJobs, Greenhouse, and Lever as primary active sources.

### `v2.4` — Private Sector Expansion + Quality Filter
Greenhouse expanded to 100+ companies. Lever expanded to 50+. Score threshold at 50+. Deduplication. Batched AI enrichment — runtime cut from 90 min to 15 min.

### `v2.5` — Async Parallel Architecture
- ThreadPoolExecutor parallel requests — all sources fire simultaneously
- JSearch API — hits LinkedIn, Indeed, Glassdoor, ZipRecruiter in one call
- Adzuna API — 15+ job board aggregation
- Greenhouse directory scraping — verified slugs instead of guessing
- Delta detection — seen URLs tracked in `output/seen_urls.json`
- Runtime: ~5 minutes end to end

### `v3.0` — SITREP Web Dashboard
Full local Flask web application. Mission Dashboard with 3 live charts, Job Lookup, Recruiter Finder with Hunter.io, Pipeline Runner with live SSE streaming, Application Tracker Kanban, Outreach AI with job dropdown, Profile Editor.

### `v3.1` — Auth, Intelligence Features & Public Deployment *(current)*
- Session-based authentication — login page, `login_required` on all routes
- Centralized data persistence layer (`app/data.py`)
- Outreach history — all generated emails saved, mark sent/response tracked
- Job Lookup history — last 50 lookups persisted
- Recruiter Finder cache — 7-day domain cache to preserve Hunter API quota
- **Resume Gap Analyzer** — readiness score, skill gaps, actions, resources, resume bullet points
- **Interview Prep Generator** — technical + behavioral questions grounded in actual experience, salary negotiation advice
- Alert system — pipeline completion fires browser notification badge
- Railway deployment — public URL, auto-deploy on push, environment variable management

---

## 🗺️ Roadmap

### `v3.2` — Pipeline Fixes
- Fix JSearch returning 0 results on parallel requests
- Fix The Muse API returning 0 results
- ClearanceJobs RSS reliability improvement
- Workday company slug verification

### `v4.0` — Autonomous Agent
- Scheduled pipeline runs — monitor target companies for new postings
- Delta detection — surface only new jobs since last run
- Email/Slack digest of top new opportunities
- Persistent cloud database (PostgreSQL) — remove dependency on CSV commits
- Full outreach campaign management with follow-up scheduling

---

## ⚠️ Disclaimer

This tool is for personal job search use only. It does not automate job applications or recruiter outreach. All output is intended for human review before any action is taken. Respect the terms of service of any platform queried.
