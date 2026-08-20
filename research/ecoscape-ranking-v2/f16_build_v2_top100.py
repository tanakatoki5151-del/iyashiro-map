#!/usr/bin/env python3
"""Build ECOSCAPE V2 green-quality-upgraded rank for V1 top-100 residential zones.

The V1 release band is immutable. Green-quality evidence only reorders zones
inside the same V1 release band. No source-owned ECOSCAPE score or candidate
state is changed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

GREEN_BAND_ORDER = {
    "BRIGHT_HEALTHY": 0,
    "COOL_SHADE_HEALTHY": 1,
    "MOIST_HEALTHY": 2,
    "MIXED": 3,
    "STRESS_DECLINE_ATTENTION": 4,
    "URBAN_LOW_GREEN_HEAT_ATTENTION": 5,
    "WET_HEAVY_ATTENTION": 6,
    "UNKNOWN": 7,
}

ZONE_BAND_ORDER = {
    "A_HIGH_EVIDENCE_CLUSTER": 0,
    "B_SOLID_CLUSTER": 1,
    "C_REVIEW_CLUSTER": 2,
    "D_REVIEW_SPOT": 3,
}

def normalize_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1", "yes"])

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--stability", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    queue = pd.read_csv(args.queue)
    profiles = pd.read_csv(args.profiles)
    stability = pd.read_csv(args.stability)

    required_queue = {
        "pilotId","canonicalCellId","officialAreaLabel","zoneId",
        "v1ResidentialAreaRank","v1ZoneRank","zoneReleaseBand",
    }
    missing = sorted(required_queue - set(queue.columns))
    if missing:
        raise RuntimeError(f"queue missing columns: {missing}")

    data = queue.merge(
        profiles,
        on=["pilotId","canonicalCellId","officialAreaLabel"],
        how="left",
        validate="one_to_one",
    ).merge(
        stability,
        on=["pilotId","canonicalCellId"],
        how="left",
        validate="one_to_one",
        suffixes=("","_stability"),
    )
    if len(data) != len(queue):
        raise RuntimeError(f"row mismatch queue={len(queue)} output={len(data)}")

    for col in (
        "vitalityThresholdStable",
        "moistureThresholdStable",
        "heatThresholdStable",
    ):
        data[col] = normalize_bool(data[col])
    data["stableAxisCount"] = data[
        ["vitalityThresholdStable","moistureThresholdStable","heatThresholdStable"]
    ].sum(axis=1)

    data["zoneBandIndex"] = data["zoneReleaseBand"].map(ZONE_BAND_ORDER).fillna(9)
    data["greenBandIndex"] = (
        data["greenQualityDescriptiveBand"].map(GREEN_BAND_ORDER).fillna(8)
    )
    data["coverageBandIndex"] = np.select(
        [
            (data["fullCoreCoverageRate"] >= 0.75) & (data["stableAxisCount"] == 3),
            (data["fullCoreCoverageRate"] >= 0.75) & (data["stableAxisCount"] >= 2),
        ],
        [0, 1],
        default=2,
    )
    data["stabilityIndex"] = np.where(
        data["interannualStabilityBand"].eq("STABLE"), 0, 1
    )
    vitality_order = {"HIGH":0, "MID":1, "LOW":2}
    heat_order = {"COOLER":0, "MID":1, "HOTTER":2}
    data["vitalityIndex"] = data["vitalityBand"].map(vitality_order).fillna(3)
    data["heatIndex"] = data["heatBand"].map(heat_order).fillna(3)

    data = data.sort_values(
        [
            "zoneBandIndex",
            "greenBandIndex",
            "coverageBandIndex",
            "stabilityIndex",
            "stableAxisCount",
            "vitalityIndex",
            "heatIndex",
            "v1ResidentialAreaRank",
            "canonicalCellId",
        ],
        ascending=[True,True,True,True,False,True,True,True,True],
        kind="stable",
    ).reset_index(drop=True)
    data["v2GreenQualityRank"] = np.arange(1, len(data)+1)
    data["v2RankDeltaVsV1"] = (
        data["v1ResidentialAreaRank"] - data["v2GreenQualityRank"]
    )
    data["v2Confidence"] = data["coverageBandIndex"].map(
        {0:"HIGH", 1:"MEDIUM", 2:"LOW"}
    )
    data["v2InterpretationJa"] = data.apply(
        lambda r: (
            f"V1 {int(r.v1ResidentialAreaRank)}位から"
            f"{int(r.v2GreenQualityRank)}位。"
            f"緑質={r.greenQualityDescriptiveBand}、"
            f"活力={r.vitalityBand}、水分={r.moistureBand}、"
            f"複数夏の熱={r.heatBand}、"
            f"安定軸={int(r.stableAxisCount)}/3、"
            f"充足率={float(r.fullCoreCoverageRate):.0%}。"
        ),
        axis=1,
    )
    data["rankingEffectOnCanonical"] = "none"
    data["scoringEffect"] = "none"
    data["candidateOverride"] = 0
    data["wetHeavyNegativeLabel"] = "HOLD"
    data["maintenanceCleanliness"] = "UNKNOWN"

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    data.to_csv(out / "ECOSCAPE_V2_TOP100_GREEN_QUALITY_RANKING.csv", index=False)
    data.head(50).to_csv(out / "ECOSCAPE_V2_TOP50_REPORT_TABLE.csv", index=False)

    audit = {
        "buildId":"ecoscape-v2-green-quality-top100-20260820-v1",
        "rows":int(len(data)),
        "uniqueCells":int(data["canonicalCellId"].nunique()),
        "uniqueZones":int(data["zoneId"].nunique()),
        "v1ReleaseBandCrossingAllowed":False,
        "fullCoverage":int(data["fullCoreCoverageRate"].ge(0.75).sum()),
        "highConfidence":int(data["v2Confidence"].eq("HIGH").sum()),
        "mediumConfidence":int(data["v2Confidence"].eq("MEDIUM").sum()),
        "lowConfidence":int(data["v2Confidence"].eq("LOW").sum()),
        "greenBandCounts":data["greenQualityDescriptiveBand"].value_counts(dropna=False).to_dict(),
        "rankingEffectOnCanonical":"none",
        "scoringEffect":"none",
        "candidateOverride":0,
        "status":"V2_RESEARCH_RANK_READY",
    }
    (out / "ECOSCAPE_V2_TOP100_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
