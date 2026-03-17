# 🔍 Recruiter Recon AI

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-success?style=for-the-badge)
![Version](https://img.shields.io/badge/Version-2.4-blue?style=for-the-badge)

> **AI-assisted job targeting pipeline for cybersecurity professionals.**
> Resume in. Ranked opportunities out.

Instead of manually scanning job boards one posting at a time, this pipeline takes your resume, builds a structured candidate profile, discovers relevant jobs across multiple live sources, scores each one against your background using AI, identifies recruiter contacts, and outputs a clean interactive report — ready for human review before any action is taken.

This is a **review-first workflow**, not a blind outreach machine.

---

## 📋 Table of Contents

- [How It Works](#how-it-works)
- [Discovery Sources](#discovery-sources)
- [Company Coverage](#company-coverage)
- [Setup](#setup)
- [Running the Pipeline](#running-the-pipeline)
- [Output Files](#output-files)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Version History](#version-history)
- [Roadmap — v3.0](#roadmap--v30)

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
│                 STEP 2 — JOB DISCOVERY (v2.4)               │
│                                                             │
│   9 sources queried across:                                 │
│   · Federal/cleared: USAJobs API, ClearanceJobs             │
│   · Broad market: Indeed, Dice, LinkedIn                    │
│   · Direct ATS: Greenhouse (100+ cos), Lever (50+ cos)      │
│   · Defense primes: Workday (20 cos), iCIMS (10 cos)        │
│                                                             │
│   → Senior role filter (removed at discovery)               │
│   → Relevance filter (non-cyber removed)                    │
│   → Heuristic scoring (source quality + skill overlap)      │
│   → Company + title deduplication                           │
│   → AI reranking — only 70+ scores passed forward           │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 3 — AI ENRICHMENT (v2.0)                  │
│                                                             │
│   Pre-filter: removes irrelevant/senior roles               │
│   that slipped through discovery                            │
│                                                             │
│   Batched AI scoring (15 jobs per API call):                │
│   · Entry-level fit · Clearance fit · Score (0-100)         │
│   · Required skills · Preferred skills                      │
│   · Fit reasoning · Outreach angle · Red flags              │
│                                                             │
│   Recruiter enrichment (Hunter.io):                         │
│   · Skips .gov/.mil (no useful contacts there)              │
│   · Filters generic junk emails                             │
│   · Named recruiter + email + confidence score              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                        OUTPUT                               │
│   enriched_jobs.csv  — full structured data export          │
│   enriched_jobs.html — interactive dark-theme browser UI    │
│                        search · filter · sort · click-thru  │
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
| **Greenhouse** | Direct JSON API | 100+ cyber/defense/private sector boards | ✅ Active |
| **Lever** | Direct JSON API | 50+ defense tech/cyber company boards | ✅ Active |
| **Workday** | Direct API | 20 defense prime + enterprise employers | 🔧 Partial |
| **iCIMS** | HTML Scrape | 10 traditional defense contractors | ✅ Partial |

---

## 🏢 Company Coverage

The pipeline queries company job boards directly across every major sector relevant to cybersecurity:

**Defense & Government Contractors**
Leidos · Northrop Grumman · L3Harris · BAE Systems · General Dynamics · Lockheed Martin · Boeing · Raytheon · SAIC · Peraton · Parsons · Amentum · Booz Allen Hamilton · ManTech · CACI · MITRE · Telos

**Pure-Play Cybersecurity**
CrowdStrike · SentinelOne · Huntress · ThreatLocker · Expel · Red Canary · Blumira · Dragos · Claroty · Recorded Future · Flashpoint · Vectra · Exabeam · Anomali · Cybereason · Arctic Wolf · DeepWatch · NetSPI · Bishop Fox · NCC Group · Mandiant · Kroll · Secureworks · Trellix · Rapid7 · Tenable · Qualys · Palo Alto Networks · Fortinet · BeyondTrust · CyberArk · Okta

**Banks & Financial Services**
Capital One · USAA · JPMorgan Chase · Bank of America · Citigroup · Wells Fargo · Raymond James · Fidelity · Charles Schwab · Visa · Mastercard · PayPal · Stripe · Robinhood · Coinbase

**Big Tech**
Microsoft · Google · Amazon · Apple · Meta · IBM · Oracle · Salesforce · ServiceNow · Splunk · Cloudflare · Datadog · Elastic

**Consulting / Big 4**
Deloitte · PwC · KPMG · EY · Accenture · McKinsey

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

```env
OPENAI_API_KEY=your_openai_key
HUNTER_API_KEY=your_hunter_key
USAJOBS_API_KEY=your_usajobs_key
USAJOBS_USER_AGENT=your_email@example.com
```

> **Getting API keys:**
> - **OpenAI:** [platform.openai.com](https://platform.openai.com)
> - **Hunter.io:** [hunter.io](https://hunter.io) — free tier available
> - **USAJobs:** [developer.usajobs.gov](https://developer.usajobs.gov/APIRequest/) — free, instant

### 5. Add your resume

```
resumes/resume.pdf     ← preferred
resumes/resume.docx
resumes/resume.txt
```

---

## ▶️ Running the Pipeline

```bash
python scripts/run_v2_4.py
```

| Step | What Happens | Estimated Time |
|---|---|---|
| Profile Build | AI parses resume → JSON profile | 30–60 sec |
| Job Discovery | 9 sources, 500 raw → 70+ threshold | 5–10 min |
| AI Enrichment | Batched scoring + Hunter contacts | 5–10 min |
| **Total** | | **~15–20 min** |

Progress prints continuously. Do not interrupt mid-run.

When complete, open your results:

```bash
open output/enriched_jobs.html
```

---

## 📁 Output Files

| File | Description |
|---|---|
| `candidate_profile_generated.json` | AI-parsed candidate profile from resume |
| `output/raw_discovered_jobs.csv` | All discovered jobs before filtering (up to 500) |
| `output/discovered_jobs.csv` | 70+ scored jobs passed to enrichment |
| `output/enriched_jobs.csv` | Full enriched dataset with AI scores + contacts |
| `output/enriched_jobs.html` | **Open this in your browser** |

### HTML Report

Dark-theme interactive report with:
- Sortable columns (click any header)
- Search bar across all fields
- Filters: entry-level fit / clearance fit / minimum score
- Color-coded scores: 🟢 70+ · 🟡 40–69 · 🔴 below 40
- Recruiter email shown inline with mailto link
- One-click through to job posting

### Enriched CSV columns

| Column | Description |
|---|---|
| `overall_fit_score` | AI fit score 0–100 |
| `entry_level_fit` | yes / maybe / no / unclear |
| `clearance_fit` | required / preferred / eligible / not_mentioned |
| `required_skills` | Skills the posting explicitly requires |
| `preferred_skills` | Nice-to-have skills mentioned |
| `fit_reasoning` | AI explanation of the score |
| `outreach_angle` | Suggested angle for recruiter outreach |
| `red_flags` | Concerns flagged by AI |
| `recruiter_contact_name` | Named recruiter or HR contact |
| `recruiter_contact_email` | Contact email if found |
| `recruiter_contact_confidence` | Hunter.io confidence score |

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
│   ├── discover_jobs_v2_4.py       # Discovery engine (current)
│   ├── recruiter_recon_v2_0.py     # Enrichment — batched AI + Hunter
│   └── run_v2_4.py                 # Pipeline orchestrator (current)
│
├── output/                         # Gitignored — generated per run
│   ├── raw_discovered_jobs.csv
│   ├── discovered_jobs.csv
│   ├── enriched_jobs.csv
│   └── enriched_jobs.html
│
├── assets/
├── .env
├── .env.example
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
| Job data | Greenhouse API | Direct ATS board queries (100+ companies) |
| Job data | Lever API | Direct ATS board queries (50+ companies) |
| Recruiter data | Hunter.io API | Contact identification |
| Parsing | BeautifulSoup4 | HTML job page parsing |
| Data | Pandas | CSV processing |
| HTTP | Requests | API and web requests |
| Config | python-dotenv | Environment variables |
| Domains | tldextract | Company domain parsing |

---

## 📜 Version History

### `v1.0` — Job Enrichment Pipeline
Manual workflow. Provide job URLs in `input_jobs.csv`. AI scores each posting against your candidate profile and outputs fit scores + recruiter contacts. No automated discovery.

---

### `v2.0` — Resume-Driven Discovery
Automated resume parsing and candidate profile generation via AI. Discovery engine used DuckDuckGo HTML scraping to find job postings across ATS platforms.

---

### `v2.1` — Discovery Improvements
Improved heuristic scoring with profile alignment. Better ATS source classification. AI-assisted reranking. LinkedIn URL support. Profile-aligned query generation.

---

### `v2.2` — Rate Limiting & Query Budget
Fixed silent discovery failures from DuckDuckGo rate limiting. Randomized sleep, exponential backoff, wildcard query removal, hard query budget cap. Still dependent on a single brittle scraping target.

---

### `v2.3` — Multi-Source Discovery Engine
Complete replacement of DuckDuckGo with 9 dedicated sources. USAJobs API, Greenhouse, and Lever became primary active sources. LinkedIn/Indeed/Dice either blocked or deprecated.

Sample run: 300 raw → 98 enriched. Top results included NSA, CIA, DISA, Air Force, Booz Allen, Huntress, ThreatLocker, Palantir.

---

### `v2.4` — Private Sector Expansion + Quality Filter *(current)*

**Discovery:**
- Greenhouse company list expanded from 57 to 100+ companies
- Lever company list expanded from 29 to 50+ companies
- Added banks (Capital One, USAA, JPMorgan, Bank of America), big tech (Microsoft, Google, Amazon, IBM), consulting (Deloitte, PwC, Accenture), healthcare, energy, telecom, and Tampa-specific employers
- Score threshold enforced: only 70+ scores pass to enrichment — eliminates low-quality results entirely
- Deduplication by company + normalized title — eliminates same-role/different-location duplicates

**Enrichment:**
- Batched AI scoring (15 jobs/call) — 90 min runtime reduced to under 10 min
- Clearance context passed explicitly — no more false "clearance not stated" flags
- Hunter skips .gov/.mil domains entirely
- Junk contact emails filtered (jobs@usajobs.gov, noreply@, etc.)
- HTML report generated alongside CSV — dark theme, sortable, filterable, searchable

---

## 🗺️ Roadmap — v3.0

Version 3.0 introduces a local Flask web dashboard replacing manual CSV/HTML review with a full interactive application.

### Planned Features

**Job Search Dashboard**
Browse all enriched results in a filterable, sortable table. Filter by fit score, entry-level status, clearance requirement, source, and location. One-click through to any job posting.

**Manual Job Lookup**
Paste one or more job URLs. The system fetches each posting, scores it against your profile using AI, and returns fit score, required skills, and recruiter contact — on demand without running the full pipeline.

**Recruiter Contact Finder**
Enter a company name or domain. Returns all identified recruiting and HR contacts with names, emails, and Hunter.io confidence scores.

**Pipeline Runner**
Trigger a full pipeline run from the browser. Watch live progress output without touching the terminal.

**Profile Viewer & Editor**
View and edit your candidate profile directly in the UI — update target roles, skills, location preferences, and clearance info without editing JSON files.

**Application Tracker**
Mark jobs as `Applied`, `Interviewing`, `Offer`, or `Rejected`. Track your pipeline across multiple runs. State persists between sessions.

**Outreach Draft Generator**
Select any job from results. AI generates a tailored cold outreach email to the identified recruiter contact, grounded in your profile and the specific job description.

**Export**
Export any filtered view to CSV or PDF for sharing or offline review.

---

## ⚠️ Disclaimer

This tool is for personal job search use only. It does not automate job applications or recruiter outreach. All output is intended for human review before any action is taken. Respect the terms of service of any platform queried.
