"""
Phase 3 evaluation — builds the held-out set of (AQI, health profile) combinations
your plan doc's Objective O5 calls for, generates advisories for each, and writes
a CSV with empty rater_1_score / rater_2_score columns ready for you and a
groupmate/guide to fill in independently (accuracy / actionability / no unsafe
claims, e.g. 1-5 each). Inter-rater agreement on this file is a very defensible
paper table.

Usage:
    python advisory/generate_eval_set.py
Writes:
    data/processed/advisory_eval_set.csv
"""
import csv
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from advisory_generator import generate_advisory  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AQI_SAMPLES = [40, 90, 150, 250, 350, 450]
PROFILES = [
    {"age_band": "adult", "respiratory": False, "cardiac": False, "pregnant": False, "activity_level": "moderate"},
    {"age_band": "child", "respiratory": False, "cardiac": False, "pregnant": False, "activity_level": "moderate"},
    {"age_band": "elderly", "respiratory": True, "cardiac": False, "pregnant": False, "activity_level": "sedentary"},
    {"age_band": "adult", "respiratory": False, "cardiac": False, "pregnant": True, "activity_level": "moderate"},
    {"age_band": "adult", "respiratory": False, "cardiac": False, "pregnant": False, "activity_level": "outdoor_worker"},
]


def main():
    rows = []
    for aqi in AQI_SAMPLES:
        for profile in PROFILES:
            result = generate_advisory(aqi, **profile)
            rows.append({
                "aqi_value": aqi,
                "age_band": profile["age_band"],
                "respiratory": profile["respiratory"],
                "cardiac": profile["cardiac"],
                "pregnant": profile["pregnant"],
                "activity_level": profile["activity_level"],
                "aqi_category": result["aqi_category"],
                "advisory_text": result["advisory_text"],
                "generated_by": result["generated_by"],
                "rater_1_score_1to5": "",
                "rater_2_score_1to5": "",
                "unsafe_claim_flag": "",
            })

    out_path = OUT_DIR / "advisory_eval_set.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} advisory samples to {out_path}")
    print("Have two independent raters fill in the score columns, then compute "
          "% fully correct + inter-rater agreement (e.g. Cohen's kappa) for the paper.")


if __name__ == "__main__":
    main()
