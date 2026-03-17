"""
run_v2_1.py
-----------
Recruiter Recon AI — Pipeline Orchestrator

Steps:
  1. Parse resume → extract text
  2. Build structured candidate profile (AI)
  3. Discover jobs (v2.3 — 9 sources, no DDG)
  4. Copy discovered jobs → input_jobs.csv
  5. Run V1 enrichment (AI scoring + Hunter recruiter lookup)
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

    print(f"[run_v2] Resume found: {resume_path}")

    run_step("Step 1 of 4 — Building candidate profile from resume", "scripts/build_profile_v2_0.py")
    run_step("Step 2 of 4 — Discovering jobs (v2.3 — 9 sources)", "scripts/discover_jobs_v2_3.py")

    discovered_path = Path("output/discovered_jobs.csv")
    if not discovered_path.exists():
        print("[ERROR] output/discovered_jobs.csv not created. Check discovery logs.")
        sys.exit(1)

    print(f"\n[run_v2] Copying {discovered_path} → input_jobs.csv")
    shutil.copy(discovered_path, "input_jobs.csv")

    run_step("Step 3 of 4 — Running V1 enrichment (AI + Hunter)", "scripts/recruiter_recon_v1_0.py")

    print(f"\n{'═' * 60}")
    print("  Pipeline complete.")
    print(f"{'═' * 60}")
    print("  Output files:")
    print("    candidate_profile_generated.json")
    print("    output/raw_discovered_jobs.csv")
    print("    output/discovered_jobs.csv")
    print("    output/enriched_jobs.csv")


if __name__ == "__main__":
    main()
