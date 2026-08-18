#!/usr/bin/env python3
"""Build the P2A geometry-only ventilation-potential feasibility table.

Inputs:
  1. ECOSCAPE B114 full-domain ZIP
  2. P2 pilot-area CSV containing canonicalCellId

This is not a wind-speed model. It only labels urban geometry as supporting
openness, mixed, enclosed/stuffiness attention, or unknown. It never changes
ECOSCAPE scores or rankings.
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

B114_MEMBER = "ECOSCAPE_LEVELB_V4_CORE6_FULL_120662_B114.csv.gz"
SOURCE_COLUMNS = [
    "canonicalCellId",
    "plateauStatus",
    "plateauBuildingCoverageFractionApprox",
    "plateauOpenSpaceFractionApprox",
    "plateauHeightP90M",
    "urbanState_P25",
    "urbanFavorableShare_300m",
    "urbanCautionShare_300m",
    "urbanFavorableShare_500m",
    "urbanCautionShare_500m",
    "thermalFavorableShare_300m",
    "thermalCautionShare_300m",
    "thermalFavorableShare_500m",
    "thermalCautionShare_500m",
]


def load_b114(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        raw = zf.read(B114_MEMBER)
    return pd.read_csv(
        io.BytesIO(raw),
        compression="gzip",
        usecols=SOURCE_COLUMNS,
        low_memory=False,
    )


def thresholds(frame: pd.DataFrame) -> dict[str, float]:
    finite = frame.dropna(
        subset=[
            "plateauBuildingCoverageFractionApprox",
            "plateauOpenSpaceFractionApprox",
        ]
    )
    return {
        "coverage_q25": float(
            finite["plateauBuildingCoverageFractionApprox"].quantile(0.25)
        ),
        "coverage_q75": float(
            finite["plateauBuildingCoverageFractionApprox"].quantile(0.75)
        ),
        "open_q25": float(
            finite["plateauOpenSpaceFractionApprox"].quantile(0.25)
        ),
        "open_q75": float(
            finite["plateauOpenSpaceFractionApprox"].quantile(0.75)
        ),
    }


def classify(row: pd.Series, q: dict[str, float]) -> str:
    cov = row["plateauBuildingCoverageFractionApprox"]
    open_space = row["plateauOpenSpaceFractionApprox"]
    if pd.isna(cov) or pd.isna(open_space):
        return "UNKNOWN"
    caution_300 = row["urbanCautionShare_300m"]
    caution_500 = row["urbanCautionShare_500m"]
    open_support = (
        open_space >= q["open_q75"]
        and cov <= q["coverage_q25"]
        and (pd.isna(caution_300) or caution_300 <= 0.25)
        and (pd.isna(caution_500) or caution_500 <= 0.25)
    )
    enclosed = (
        open_space <= q["open_q25"]
        and cov >= q["coverage_q75"]
        and (
            (not pd.isna(caution_300) and caution_300 >= 0.5)
            or (not pd.isna(caution_500) and caution_500 >= 0.5)
        )
    )
    if open_support:
        return "OPEN_AND_VENTILATION_SUPPORTING"
    if enclosed:
        return "ENCLOSED_STUFFINESS_ATTENTION"
    return "MIXED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--b114", type=Path, required=True)
    parser.add_argument("--pilots", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    b114 = load_b114(args.b114)
    pilots = pd.read_csv(args.pilots)
    merged = pilots.merge(b114, on="canonicalCellId", how="left", validate="one_to_one")
    q = thresholds(b114)
    merged["ventilationPotentialProxy"] = merged.apply(classify, axis=1, q=q)
    merged["heatCorroboration"] = np.select(
        [
            (merged["thermalCautionShare_300m"] >= 0.5)
            | (merged["thermalCautionShare_500m"] >= 0.5),
            (merged["thermalFavorableShare_300m"] >= 0.5)
            & (merged["thermalFavorableShare_500m"] >= 0.5),
        ],
        ["HEAT_RETENTION_ATTENTION", "THERMAL_SUPPORTING"],
        default="MIXED_OR_UNKNOWN",
    )
    merged["actualWindClaimAllowed"] = False
    merged["rankingEffect"] = "none"
    merged.to_csv(args.output / "P2A_VENTILATION_POTENTIAL.csv", index=False)
    audit = {
        "pilotAreaCount": int(len(merged)),
        "joinedAreaCount": int(merged["plateauStatus"].notna().sum()),
        "thresholds": q,
        "stateCounts": {
            str(k): int(v)
            for k, v in merged["ventilationPotentialProxy"].value_counts().items()
        },
        "actualWindClaim": False,
        "rankingEffect": "none",
        "scoringEffect": "none",
        "remainingGaps": [
            "directional road/rail/river/open-land corridor continuity",
            "prevailing-wind climate context",
            "validation against observed heat or wind",
        ],
    }
    (args.output / "P2A_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
