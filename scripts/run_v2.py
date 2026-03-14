import shutil
import subprocess
from pathlib import Path


def main() -> None:
    print("Step 1: Discovering jobs...")
    subprocess.run(["python", "scripts/discover_jobs_v2.py"], check=True)

    discovered_path = Path("output/discovered_jobs.csv")
    if not discovered_path.exists():
        raise FileNotFoundError("output/discovered_jobs.csv was not created.")

    print("Step 2: Copying discovered jobs to input_jobs.csv for enrichment...")
    shutil.copy(discovered_path, "input_jobs.csv")

    print("Step 3: Running enrichment pipeline...")
    subprocess.run(["python", "scripts/recruiter_recon_v1.py"], check=True)

    print("V2 pipeline complete.")
    print("Check output/discovered_jobs.csv and output/enriched_jobs.csv")


if __name__ == "__main__":
    main()
