#!/usr/bin/env python3
"""Rebuild F8 NEXUS holdout cross-layer profiles.

Inputs are the F7 temporal final folder and F7 static preflight CSV.
The script never changes ECOSCAPE rank/score/candidate state.
"""
from pathlib import Path
import pandas as pd


def contains(value, token):
    return token in str(value)


def moisture_state(row):
    high_m = contains(row.moistureBand, "HIGH")
    high_v = contains(row.vitalityBand, "HIGH")
    water = bool(row.underlandHistoricalWaterSignal)
    underland = bool(row.underlandHighOrElevatedAttention)
    enclosed = row.ventilationPotential_static == "ENCLOSED_ATTENTION"
    open_support = row.ventilationPotential_static == "OPEN_SUPPORT"
    stable = bool(row.moistureThresholdStable)
    wet_heavy = (
        high_m
        and stable
        and (water or underland)
        and enclosed
        and row.urbanCautionShare_500m >= 0.5
    )
    if wet_heavy:
        return "WET_HEAVY_ATTENTION"
    if high_m and high_v and open_support:
        return "MOIST_HEALTHY_OPEN"
    if high_m and high_v and not (water or underland):
        return "MOIST_HEALTHY_NO_GROUNDWATER_SIGNAL"
    if high_m:
        return "HIGH_MOISTURE_UNRESOLVED"
    return "NO_HIGH_MOISTURE_SIGNAL"


def main(temporal_csv, static_csv, threshold_csv, output_csv):
    temporal = pd.read_csv(temporal_csv)
    static = pd.read_csv(static_csv)
    thresholds = pd.read_csv(threshold_csv)
    keys = ["pilotId", "canonicalCellId"]
    out = temporal.merge(
        static,
        on=keys,
        how="left",
        suffixes=("_temporal", "_static"),
        validate="one_to_one",
    )
    out = out.merge(thresholds, on=keys, how="left", validate="one_to_one")
    if len(out) != 10 or out["ventilationPotential_static"].isna().any():
        raise RuntimeError("F8 exact static/temporal join failed")
    out["moistureInterpretation"] = out.apply(moisture_state, axis=1)
    out["rankingEffectFinal"] = "none"
    out["scoringEffectFinal"] = "none"
    out["candidateOverrideFinal"] = False
    out.to_csv(output_csv, index=False)


if __name__ == "__main__":
    raise SystemExit("Import and call main() with explicit source paths.")
