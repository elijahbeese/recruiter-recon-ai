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

## Workflow

1. Seed jobs are added to `input_jobs.csv` or a Google Sheet
2. The script fetches job page text from each URL
3. OpenAI analyzes the posting against a candidate profile
4. The script assigns a fit score and extracts job-relevant fields
5. Hunter performs contact discovery by company domain
6. Results are written to `output/enriched_jobs.csv`
7. Contacts and opportunities are manually verified before any outreach

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
