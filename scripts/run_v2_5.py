"""
run_v2_5.py
-----------
SITREP — Pipeline Orchestrator v2.5

Steps:
  1. Build candidate profile from resume (AI)
  2. Discover jobs (v2.5 — async parallel, JSearch, Adzuna, Greenhouse directory)
  3. Enrich jobs (v2.0 — batched AI, HTML report)
"""

import shutil
import subprocess
import sys
from pathlib import Path

RESUME_CANDIDATES = [
    Path("resumes/resume.docx"),
    Path("resumes/resume.pdf"),
    Path("resumes/resume.txt"),
]


def run_step(label: str, script: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    result = subprocess.run(["python", script], check=False)
    if result.returncode != 0:
        print(f"\n[ERROR] {script} exited with code {result.returncode}. Aborting.")
        sys.exit(result.returncode)


def main() -> None:
    resume_path = next((p for p in RESUME_CANDIDATES if p.exists()), None)
    if not resume_path:
        print(
            "[ERROR] No resume found. Add one of:\n"
            "  resumes/resume.pdf\n"
            "  resumes/resume.docx\n"
            "  resumes/resume.txt"
        )
        sys.exit(1)

    print(f"[SITREP] Resume found: {resume_path}")

    run_step("Step 1 of 3 — Building candidate profile", "scripts/build_profile_v2_0.py")
    run_step("Step 2 of 3 — Discovering jobs (v2.5 — async parallel)", "scripts/discover_jobs_v2_5.py")

    discovered = Path("output/discovered_jobs.csv")
    if not discovered.exists():
        print("[ERROR] output/discovered_jobs.csv not found.")
        sys.exit(1)

    print(f"\n[SITREP] Copying {discovered} → input_jobs.csv")
    shutil.copy(discovered, "input_jobs.csv")

    run_step("Step 3 of 3 — Enriching jobs (v2.0 — batched AI + HTML report)", "scripts/recruiter_recon_v2_0.py")

    print(f"\n{'═' * 60}")
    print("  SITREP pipeline complete.")
    print(f"{'═' * 60}")
    print("  Output files:")
    print("    candidate_profile_generated.json")
    print("    output/raw_discovered_jobs.csv")
    print("    output/discovered_jobs.csv")
    print("    output/enriched_jobs.csv")
    print("    output/enriched_jobs.html  ← open in browser")
    print("    output/seen_urls.json      ← delta detection tracking")
    print(f"{'═' * 60}")
    print("\n  Launch dashboard: python run_app.py")


if __name__ == "__main__":
    main()
