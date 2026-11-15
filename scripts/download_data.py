"""Download the Kaggle datasets into data/raw/<slug>/ (git-ignored).

Requires the Kaggle CLI and a token (~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY).
Never commit the token or the raw data. Alternatively download the zips by hand from the
Kaggle pages and unzip each into data/raw/<folder>/ using the folder names below.
"""
from __future__ import annotations

import subprocess
import sys

from common import RAW

DATASETS = {
    "upwork-jobs-2024-50k": "asaniczka/upwork-job-postings-dataset-2024-50k-records",
    "upwork-all-jobs-200k": "asaniczka/all-jobs-on-upwork-200k-plus",
    "upwork-freelance-jobs-60k": "ahmedmyalo/upwork-freelance-jobs-60k",
    "freelance-contracts-1-3m": "asaniczka/freelance-contracts-dataset-1-3-million-entries",
    "freelancer-success-churn": "sarveshchhetri/freelancer-success-earnings-and-churn-prediction",
    "trial-1": "adityammantri/trial-1",
}


def main(only: list[str]) -> int:
    for folder, ref in DATASETS.items():
        if only and folder not in only:
            continue
        dest = RAW / folder
        dest.mkdir(parents=True, exist_ok=True)
        print(f"==> {ref} -> {dest}")
        r = subprocess.run(["kaggle", "datasets", "download", "-d", ref, "-p", str(dest), "--unzip"])
        if r.returncode != 0:
            print(f"   FAILED (is the kaggle CLI installed and authenticated?): {ref}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
