![Python](https://img.shields.io/badge/python-3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

# recruiter-recon-ai

Private AI-assisted job targeting pipeline for cybersecurity roles.

This project helps automate the front end of a job search workflow by turning job postings into structured, reviewable data. Instead of manually scanning roles one at a time, the script pulls job information, analyzes required skills and qualifications, compares them against a candidate profile, assigns a fit score, and attempts to identify recruiter or recruiting contacts for manual verification.

This is designed as a review-first workflow, not a blind outreach machine.

## What it does

- Reads seed job targets from CSV or Google Sheets
- Pulls public job description text from job URLs
- Uses the OpenAI API to extract requirements and classify fit
- Scores alignment based on entry-level suitability, clearance language, and skills match
- Uses Hunter to find likely recruiter or recruiting contacts by company domain
- Exports enriched results to CSV for human review

## How It Works

1. Job URLs are added to a seed spreadsheet or CSV.
2. The script fetches the job page text.
3. An LLM extracts skills, experience requirements, and role characteristics.
4. The system compares the job against a structured candidate profile.
5. A fit score is generated based on skill alignment and role criteria.
6. The company domain is analyzed to identify likely recruiter or talent contacts.
7. The results are exported to a structured spreadsheet for manual review.

## Why this exists

Hiring pipelines increasingly rely on automated systems to parse resumes and filter candidates before a recruiter ever reads them. This project takes the opposite-side view of that problem and applies automation to the job search itself.

Instead of manually reviewing hundreds of roles, this workflow identifies which jobs are most worth pursuing and prepares structured outreach intelligence for review.

## Core features

- Job page text extraction
- Skill and qualification parsing
- Entry-level fit classification
- Clearance requirement classification
- Overall fit scoring
- Recruiter/contact enrichment
- Structured spreadsheet export
- Optional Google Sheets support

## Tech Stack

Python

OpenAI API – job description analysis and skill extraction  
Hunter API – recruiter and talent contact discovery  
BeautifulSoup – job page parsing  
Pandas – structured data processing  
dotenv – API configuration  
tldextract – company domain parsing

## Workflow

1. Seed jobs are added to `input_jobs.csv` or a Google Sheet
2. The script fetches job page text from each URL
3. OpenAI analyzes the posting against a candidate profile
4. The script assigns a fit score and extracts job-relevant fields
5. Hunter performs contact discovery by company domain
6. Results are written to `output/enriched_jobs.csv`
7. Contacts and opportunities are manually verified before any outreach

## v1 Features

- Reads seed job targets from CSV
- Pulls public job description text from job URLs
- Uses the OpenAI API to extract requirements and classify fit
- Scores alignment based on entry-level suitability, clearance language, and skills match
- Uses Hunter to find likely recruiter or recruiting contacts by company domain
- Exports enriched results to CSV for human review

## v1 Workflow

1. Add jobs to `input_jobs.csv`
2. Run the script
3. The script fetches job text from each URL
4. OpenAI analyzes the posting against your candidate profile
5. Hunter searches for likely recruiting contacts by domain
6. Results are written to `output/enriched_jobs.csv`
7. You manually review before any outreach

## v1 Setup
* **Clone the repository**
  * `git clone https://github.com/elijahbeese/recruiter-recon-ai.git`
  * `cd recruiter-recon-ai`
  
 * **Create and activate a virtual environment**
   *  **macOS / Linux**
     * `python3 -m venv .venv`
     * `source .venv/bin/activate`
   * **Windows PowerShell**
     * `python -m venv .venv`
     * `.venv\Scripts\Activate.ps1`
  
* **Install dependencies**
  * `pip install -r requirements.txt`
  
* **Configure environment variables**
  * Copy .env.example to .env.
  
* **macOS / Linux**
  * `cp .env.example .env`
* **Windows PowerShell**
  * `copy .env.example .env`
    
  * Then fill in your API keys.
  
* **Edit your candidate profile**
  * Update candidate_profile.json with your actual experience, skills, certifications, interests, and conservative clearance wording.
  
* **Add job targets**
  * Populate input_jobs.csv with company names, domains, job titles, URLs, and locations.
  
* **Run the script**
  * `python app.py`
  
* **Review output**
  * **Open:**
    * output/enriched_jobs.csv
  
## Repository structure

```text
recruiter-recon-ai/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── app.py
├── candidate_profile.json
├── input_jobs.csv
├── output/
│   └── enriched_jobs.csv
└── credentials/
    └── credentials.json
