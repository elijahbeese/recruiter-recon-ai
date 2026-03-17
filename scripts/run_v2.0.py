import shutil
import subprocess
from pathlib import Path


def main() -> None:
    resume_candidates = [
        Path("resumes/resume.docx"),
        Path("resumes/resume.pdf"),
        Path("resumes/resume.txt")
    ]

    resume_path = next((p for p in resume_candidates if p.exists()), None)
    if not resume_path:
        raise FileNotFoundError(
            "No resume found. Add one of these:\n"
            "- resumes/resume.docx\n"
            "- resumes/resume.pdf\n"
            "- resumes/resume.txt"
        )

    print(f"Using resume: {resume_path}")

    print("Step 1: Building candidate profile from resume...")
    subprocess.run(["python", "scripts/build_profile_v2.py"], check=True)

    print("Step 2: Discovering jobs from AI-generated profile...")
    subprocess.run(["python", "scripts/discover_jobs_v2.py"], check=True)

    discovered_path = Path("output/discovered_jobs.csv")
    if not discovered_path.exists():
        raise FileNotFoundError("output/discovered_jobs.csv was not created.")

    print("Step 3: Feeding discovered jobs into V1 enrichment pipeline...")
    shutil.copy(discovered_path, "input_jobs.csv")

    print("Step 4: Running enrichment...")
    subprocess.run(["python", "scripts/recruiter_recon_v1.py"], check=True)

    print("Done.")
    print("Generated files:")
    print("- candidate_profile_generated.json")
    print("- output/discovered_jobs.csv")
    print("- output/enriched_jobs.csv")


if __name__ == "__main__":
    main()

