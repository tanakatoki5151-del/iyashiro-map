#!/usr/bin/env python3
"""ECOSCAPE Green Quality F7 evidence gate.

Builds descriptive area evidence from period-specific Sentinel-2 and
multi-summer Landsat composites. Optional B114/B118/B101 context is joined by
canonicalCellId. The script never writes an ECOSCAPE score, ranking, or
candidate override.

Core rules:
- compare the same phenological period across full years
- winter is a phenology diagnostic, never a vitality penalty
- summer stress uses early-summer -> peak-summer decline and weak recovery,
  not spring -> summer growth
- high vegetation moisture alone never means wet-heavy
- urban geometry never becomes an actual wind-speed claim
- 20/25/30-percent sensitivity is reported without cherry-picking
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

CORE_PERIODS = ("SPRING", "EARLY_SUMMER", "PEAK_SUMMER", "AUTUMN_RECOVERY")
ALL_PERIODS = CORE_PERIODS + ("WINTER_DIAGNOSTIC",)
SENTINEL_METRICS = ("ndviMedian", "eviMedian", "ndmiMedian", "ndreMedian")
B114_MEMBER = "ECOSCAPE_LEVELB_V4_CORE6_FULL_120662_B114.csv.gz"
B118_MEMBER = "ECOSCAPE_MW4_UNDERLAND_SHADOW_CELL_120662_B118.csv"
B101_MEMBER = "ECOSCAPE_MAGNETIC_CROSSSCALE_CELL_120662_B101.csv.gz"


def slope(frame: pd.DataFrame, value_col: str) -> float:
    values = frame[["year", value_col]].dropna()
    if len(values) < 4 or values["year"].nunique() < 4:
        return float("nan")
    return float(
        np.polyfit(
            values["year"].astype(float),
            values[value_col].astype(float),
            1,
        )[0]
    )


def robust_iqr(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return float("nan")
    return float(values.quantile(0.75) - values.quantile(0.25))


def safe_median(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.median()) if len(values) else float("nan")


def pct_rank(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rank(
        pct=True,
        method="average",
    )


def three_threshold_labels(
    percentile: float,
    *,
    low_name: str,
    mid_name: str,
    high_name: str,
) -> dict[str, str]:
    if pd.isna(percentile):
        return {f"T{threshold}": "UNKNOWN" for threshold in (20, 25, 30)}
    result: dict[str, str] = {}
    for threshold in (20, 25, 30):
        fraction = threshold / 100.0
        if percentile <= fraction:
            label = low_name
        elif percentile >= 1.0 - fraction:
            label = high_name
        else:
            label = mid_name
        result[f"T{threshold}"] = label
    return result


def stable_label(labels: dict[str, str]) -> tuple[bool, str]:
    values = list(labels.values())
    if all(value == values[0] for value in values):
        return True, values[0]
    return False, "BORDERLINE_" + "_".join(values)


def load_optional_zip(
    path: Path | None,
    member: str,
    usecols: Iterable[str],
) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(member)
    compression = "gzip" if member.endswith(".gz") else None
    return pd.read_csv(
        io.BytesIO(raw),
        compression=compression,
        usecols=list(usecols),
        low_memory=False,
    )


def ventilation_class(row: pd.Series, thresholds: dict[str, float]) -> str:
    coverage = row.get("plateauBuildingCoverageFractionApprox")
    open_space = row.get("plateauOpenSpaceFractionApprox")
    if pd.isna(coverage) or pd.isna(open_space):
        return "UNKNOWN"
    caution_300 = row.get("urbanCautionShare_300m")
    caution_500 = row.get("urbanCautionShare_500m")
    open_support = (
        open_space >= thresholds["open_q75"]
        and coverage <= thresholds["coverage_q25"]
        and (pd.isna(caution_300) or caution_300 <= 0.25)
        and (pd.isna(caution_500) or caution_500 <= 0.25)
    )
    enclosed = (
        open_space <= thresholds["open_q25"]
        and coverage >= thresholds["coverage_q75"]
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


def build_zone_metrics(
    sentinel: pd.DataFrame,
    landsat: pd.DataFrame,
    coverage: pd.DataFrame,
    pilots: pd.DataFrame,
    full_year_end: int,
) -> pd.DataFrame:
    sentinel = sentinel[
        pd.to_numeric(sentinel["year"], errors="coerce") <= full_year_end
    ].copy()
    records: list[dict[str, object]] = []
    for pilot_id, group in sentinel.groupby("pilotId"):
        row: dict[str, object] = {"pilotId": pilot_id}
        for period in ALL_PERIODS:
            period_group = group[group["period"] == period].sort_values("year")
            row[f"{period}_yearCount"] = int(period_group["year"].nunique())
            for metric in SENTINEL_METRICS:
                row[f"{period}_{metric}_median"] = safe_median(
                    period_group[metric]
                )
                row[f"{period}_{metric}_iqr"] = robust_iqr(
                    period_group[metric]
                )
                row[f"{period}_{metric}_slope"] = slope(
                    period_group,
                    metric,
                )
        row["earlyToPeakNdvi"] = (
            row["PEAK_SUMMER_ndviMedian_median"]
            - row["EARLY_SUMMER_ndviMedian_median"]
        )
        row["peakToAutumnNdvi"] = (
            row["AUTUMN_RECOVERY_ndviMedian_median"]
            - row["PEAK_SUMMER_ndviMedian_median"]
        )
        row["springToPeakNdvi"] = (
            row["PEAK_SUMMER_ndviMedian_median"]
            - row["SPRING_ndviMedian_median"]
        )
        row["winterToPeakNdvi"] = (
            row["PEAK_SUMMER_ndviMedian_median"]
            - row["WINTER_DIAGNOSTIC_ndviMedian_median"]
        )
        normalized_iqrs = []
        for period in CORE_PERIODS:
            median_value = row[f"{period}_ndviMedian_median"]
            iqr_value = row[f"{period}_ndviMedian_iqr"]
            if pd.notna(median_value) and pd.notna(iqr_value):
                normalized_iqrs.append(
                    float(iqr_value) / max(abs(float(median_value)), 0.05)
                )
        row["ndviNormalizedIqrMedian"] = (
            float(np.median(normalized_iqrs))
            if normalized_iqrs
            else np.nan
        )
        records.append(row)
    output = pd.DataFrame(records)

    landsat = landsat[
        pd.to_numeric(landsat["year"], errors="coerce") <= full_year_end
    ].copy()
    heat_rows = []
    for pilot_id, group in landsat.groupby("pilotId"):
        heat_rows.append(
            {
                "pilotId": pilot_id,
                "heatYearCount": int(group["year"].nunique()),
                "lstMedianMultiSummer": safe_median(group["lstMedianC"]),
                "lstP90MultiSummer": safe_median(group["lstP90C"]),
                "lstMedianIqr": robust_iqr(group["lstMedianC"]),
            }
        )
    heat = pd.DataFrame(heat_rows)
    output = pilots.merge(
        output,
        on="pilotId",
        how="left",
        validate="one_to_one",
    )
    output = output.merge(
        heat,
        on="pilotId",
        how="left",
        validate="one_to_one",
    )
    coverage_columns = [
        column
        for column in (
            "pilotId",
            "fullCoreCoverageRate",
            "fullCorePeriodYears2Plus",
            "fullCorePeriodYearTargets",
            "landsatFullYearsCovered",
        )
        if column in coverage.columns
    ]
    return output.merge(
        coverage[coverage_columns],
        on="pilotId",
        how="left",
        validate="one_to_one",
    )


def add_static_context(
    output: pd.DataFrame,
    b114: pd.DataFrame,
    b118: pd.DataFrame,
    b101: pd.DataFrame,
) -> pd.DataFrame:
    if not b114.empty:
        output = output.merge(
            b114,
            on="canonicalCellId",
            how="left",
            validate="one_to_one",
        )
        thresholds = {
            "coverage_q25": float(
                b114["plateauBuildingCoverageFractionApprox"].quantile(0.25)
            ),
            "coverage_q75": float(
                b114["plateauBuildingCoverageFractionApprox"].quantile(0.75)
            ),
            "open_q25": float(
                b114["plateauOpenSpaceFractionApprox"].quantile(0.25)
            ),
            "open_q75": float(
                b114["plateauOpenSpaceFractionApprox"].quantile(0.75)
            ),
        }
        output["ventilationPotential"] = output.apply(
            ventilation_class,
            axis=1,
            thresholds=thresholds,
        )
    else:
        output["ventilationPotential"] = "UNKNOWN_NO_B114"
    output["ventilationActualWindClaimAllowed"] = False
    if not b118.empty:
        output = output.merge(
            b118,
            on="canonicalCellId",
            how="left",
            validate="one_to_one",
        )
    if not b101.empty:
        output = output.merge(
            b101,
            on="canonicalCellId",
            how="left",
            validate="one_to_one",
        )
    return output


def assign_axes(
    output: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = output.copy()
    vitality_components = pd.concat(
        [
            pct_rank(output["PEAK_SUMMER_ndviMedian_median"]),
            pct_rank(output["PEAK_SUMMER_eviMedian_median"]),
            pct_rank(output["PEAK_SUMMER_ndreMedian_median"]),
        ],
        axis=1,
    )
    output["vitalityPercentile"] = vitality_components.median(axis=1)
    output["moisturePercentile"] = pct_rank(
        output["PEAK_SUMMER_ndmiMedian_median"]
    )
    output["heatPercentile"] = pct_rank(output["lstMedianMultiSummer"])

    threshold_rows: list[dict[str, object]] = []
    vitality_bands = []
    moisture_bands = []
    heat_bands = []
    for _, row in output.iterrows():
        vitality_labels = three_threshold_labels(
            row["vitalityPercentile"],
            low_name="LOW",
            mid_name="MID",
            high_name="HIGH",
        )
        moisture_labels = three_threshold_labels(
            row["moisturePercentile"],
            low_name="LOW",
            mid_name="MID",
            high_name="HIGH",
        )
        heat_labels = three_threshold_labels(
            row["heatPercentile"],
            low_name="COOLER",
            mid_name="MID",
            high_name="HOTTER",
        )
        vitality_stable, vitality_band = stable_label(vitality_labels)
        moisture_stable, moisture_band = stable_label(moisture_labels)
        heat_stable, heat_band = stable_label(heat_labels)
        vitality_bands.append(vitality_band)
        moisture_bands.append(moisture_band)
        heat_bands.append(heat_band)
        threshold_rows.append(
            {
                "pilotId": row["pilotId"],
                "canonicalCellId": row["canonicalCellId"],
                "vitality_T20": vitality_labels["T20"],
                "vitality_T25": vitality_labels["T25"],
                "vitality_T30": vitality_labels["T30"],
                "vitalityThresholdStable": vitality_stable,
                "moisture_T20": moisture_labels["T20"],
                "moisture_T25": moisture_labels["T25"],
                "moisture_T30": moisture_labels["T30"],
                "moistureThresholdStable": moisture_stable,
                "heat_T20": heat_labels["T20"],
                "heat_T25": heat_labels["T25"],
                "heat_T30": heat_labels["T30"],
                "heatThresholdStable": heat_stable,
            }
        )
    output["vitalityBand"] = vitality_bands
    output["moistureBand"] = moisture_bands
    output["heatBand"] = heat_bands
    return output, pd.DataFrame(threshold_rows)


def explain_and_classify(
    output: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = output.copy()
    audit_rows = []
    labels = []
    stress_states = []
    phenology_states = []
    wet_states = []
    evidence_states = []
    explanations = []
    for _, row in output.iterrows():
        coverage_ok = (
            pd.notna(row.get("fullCoreCoverageRate"))
            and row.get("fullCoreCoverageRate") >= 0.75
            and pd.notna(row.get("heatYearCount"))
            and row.get("heatYearCount") >= 3
        )
        normalized_iqr = row.get("ndviNormalizedIqrMedian")
        if pd.isna(normalized_iqr):
            stability = "UNKNOWN"
        elif normalized_iqr <= 0.15:
            stability = "STABLE"
        elif normalized_iqr <= 0.30:
            stability = "VARIABLE"
        else:
            stability = "HIGH_VARIABILITY"

        deciduous_growth = (
            pd.notna(row.get("winterToPeakNdvi"))
            and row.get("winterToPeakNdvi") >= 0.08
            and pd.notna(row.get("springToPeakNdvi"))
            and row.get("springToPeakNdvi") >= 0.04
        )
        early_peak_drop = (
            pd.notna(row.get("earlyToPeakNdvi"))
            and row.get("earlyToPeakNdvi") <= -0.05
        )
        weak_recovery = (
            pd.notna(row.get("peakToAutumnNdvi"))
            and row.get("peakToAutumnNdvi") <= 0.015
        )
        negative_peak_trend = (
            pd.notna(row.get("PEAK_SUMMER_ndviMedian_slope"))
            and row.get("PEAK_SUMMER_ndviMedian_slope") <= -0.005
        )
        stress_supported = coverage_ok and (
            (early_peak_drop and weak_recovery)
            or negative_peak_trend
        )
        if stress_supported:
            stress_state = "SUPPORTED_ATTENTION"
        elif deciduous_growth:
            stress_state = "NOT_SUPPORTED_NORMAL_SEASONAL_GROWTH"
        else:
            stress_state = (
                "NOT_SUPPORTED_OR_MIXED"
                if coverage_ok
                else "UNKNOWN_COVERAGE"
            )

        moisture_high = (
            str(row.get("moistureBand", "")).endswith("HIGH")
            or row.get("moistureBand") == "HIGH"
        )
        underland_high = (
            bool(row.get("underlandHighOrElevatedAttention", False))
            if pd.notna(row.get("underlandHighOrElevatedAttention"))
            else False
        )
        water_signal = (
            bool(row.get("underlandHistoricalWaterSignal", False))
            if pd.notna(row.get("underlandHistoricalWaterSignal"))
            else False
        )
        enclosed = (
            row.get("ventilationPotential")
            == "ENCLOSED_STUFFINESS_ATTENTION"
        )
        heat_hot = (
            str(row.get("heatBand", "")).endswith("HOTTER")
            or row.get("heatBand") == "HOTTER"
        )
        wet_heavy = (
            coverage_ok
            and moisture_high
            and (underland_high or water_signal)
            and (enclosed or heat_hot)
        )
        vitality_high = (
            str(row.get("vitalityBand", "")).endswith("HIGH")
            or row.get("vitalityBand") == "HIGH"
        )
        open_support = (
            row.get("ventilationPotential")
            == "OPEN_AND_VENTILATION_SUPPORTING"
        )
        cool = (
            str(row.get("heatBand", "")).endswith("COOLER")
            or row.get("heatBand") == "COOLER"
        )
        moist_healthy = (
            coverage_ok
            and moisture_high
            and vitality_high
            and not wet_heavy
            and (
                open_support
                or cool
                or not (underland_high or water_signal)
            )
        )

        if not coverage_ok:
            label = "UNKNOWN_INSUFFICIENT_TEMPORAL_EVIDENCE"
            evidence_state = "UNKNOWN"
        elif stress_supported:
            label = "STRESS_DECLINE_ATTENTION"
            evidence_state = "DESCRIPTIVE_ONLY"
        elif wet_heavy:
            label = "WET_HEAVY_ATTENTION"
            evidence_state = "DESCRIPTIVE_ONLY"
        elif moist_healthy:
            label = "MOIST_HEALTHY"
            evidence_state = "DESCRIPTIVE_ONLY"
        elif vitality_high and cool and not open_support:
            label = "COOL_SHADE_HEALTHY"
            evidence_state = "DESCRIPTIVE_ONLY"
        elif vitality_high and open_support:
            label = "VITALITY_STABLE_OPEN"
            evidence_state = "DESCRIPTIVE_ONLY"
        elif row.get("vitalityBand") == "LOW" and heat_hot:
            label = "URBAN_LOW_GREEN_HEAT_ATTENTION"
            evidence_state = "DESCRIPTIVE_ONLY"
        else:
            label = "MIXED"
            evidence_state = "DESCRIPTIVE_ONLY"

        proxy = str(row.get("pilotCategory", ""))
        if not coverage_ok:
            proxy_support = "INSUFFICIENT"
        elif proxy == "STRESS_MISMATCH_PROXY":
            proxy_support = "SUPPORTED" if stress_supported else "NOT_SUPPORTED"
        elif proxy == "WET_HEAVY_ATTENTION_PROXY":
            if wet_heavy:
                proxy_support = "SUPPORTED"
            elif moist_healthy:
                proxy_support = "CONTRADICTED_MOIST_HEALTHY"
            else:
                proxy_support = "NOT_SUPPORTED"
        elif proxy == "BRIGHT_HEALTHY_PROXY":
            proxy_support = (
                "SUPPORTED"
                if label in {"VITALITY_STABLE_OPEN", "MOIST_HEALTHY"}
                else "PARTIAL_OR_NOT_SUPPORTED"
            )
        elif proxy == "COOL_SHADED_PROXY":
            proxy_support = (
                "SUPPORTED"
                if label == "COOL_SHADE_HEALTHY"
                else "PARTIAL_OR_NOT_SUPPORTED"
            )
        elif proxy == "URBAN_LOW_GREEN_HOT":
            proxy_support = (
                "SUPPORTED"
                if label == "URBAN_LOW_GREEN_HEAT_ATTENTION"
                else "PARTIAL_OR_NOT_SUPPORTED"
            )
        else:
            proxy_support = "EXPLORATORY"

        reason = "; ".join(
            [
                f"coverage={row.get('fullCoreCoverageRate')}",
                f"vitality={row.get('vitalityBand')}",
                f"moisture={row.get('moistureBand')}",
                f"heat={row.get('heatBand')}",
                f"ventilation={row.get('ventilationPotential')}",
                f"stress={stress_state}",
                f"underlandHigh={underland_high}",
                f"waterSignal={water_signal}",
            ]
        )
        labels.append(label)
        stress_states.append(stress_state)
        phenology_states.append(
            "DECIDUOUS_OR_SEASONAL_GROWTH"
            if deciduous_growth
            else "NO_STRONG_DECIDUOUS_SIGNAL"
        )
        wet_states.append(
            "WET_HEAVY_SUPPORTED"
            if wet_heavy
            else (
                "MOIST_HEALTHY_SUPPORTED"
                if moist_healthy
                else "NOT_SUPPORTED_OR_MIXED"
            )
        )
        evidence_states.append(evidence_state)
        explanations.append(reason)
        audit_rows.append(
            {
                "pilotId": row["pilotId"],
                "pilotCategory": proxy,
                "canonicalCellId": row["canonicalCellId"],
                "officialAreaLabel": row.get("officialAreaLabel"),
                "coveragePass": coverage_ok,
                "phenologyState": phenology_states[-1],
                "stressState": stress_state,
                "wetHeavyState": wet_states[-1],
                "proxySupport": proxy_support,
                "descriptiveLabel": label,
                "reason": reason,
            }
        )
    output["interannualStabilityBand"] = [
        "UNKNOWN"
        if pd.isna(value)
        else (
            "STABLE"
            if value <= 0.15
            else ("VARIABLE" if value <= 0.30 else "HIGH_VARIABILITY")
        )
        for value in output["ndviNormalizedIqrMedian"]
    ]
    output["phenologyState"] = phenology_states
    output["stressEvidence"] = stress_states
    output["wetHeavyEvidence"] = wet_states
    output["greenQualityDescriptiveBand"] = labels
    output["evidenceReleaseState"] = evidence_states
    output["maintenanceCleanliness"] = "UNKNOWN_IMAGE_GATE"
    output["rankingEffect"] = "none"
    output["scoringEffect"] = "none"
    output["candidateOverride"] = False
    output["evidenceExplanation"] = explanations
    return output, pd.DataFrame(audit_rows)


def make_gate(
    output: pd.DataFrame,
    thresholds: pd.DataFrame,
    audit_rows: pd.DataFrame,
) -> dict[str, object]:
    count = len(output)
    coverage_pass = (
        int((audit_rows["coveragePass"] == True).sum())
        if count
        else 0
    )
    threshold_rates = {
        axis: (
            float(thresholds[f"{axis}ThresholdStable"].mean())
            if count
            else 0.0
        )
        for axis in ("vitality", "moisture", "heat")
    }
    return {
        "buildId": "ecoscape-green-quality-f7-evidence-gate-20260819-v1",
        "pilotAreas": count,
        "coveragePassCount": coverage_pass,
        "coveragePassRate": coverage_pass / count if count else 0.0,
        "thresholdStableRates": threshold_rates,
        "proxySupportCounts": {
            str(key): int(value)
            for key, value in audit_rows["proxySupport"].value_counts().items()
        },
        "descriptiveBandCounts": {
            str(key): int(value)
            for key, value in output[
                "greenQualityDescriptiveBand"
            ].value_counts().items()
        },
        "maintenanceCoverageGate": "OPEN_OR_HELD_SEPARATELY",
        "holdoutGate": "NOT_RUN_IN_THIS_BUILD",
        "rankingPromotionAllowed": False,
        "rankingEffect": "none",
        "scoringEffect": "none",
        "candidateOverride": 0,
        "gateResults": {
            "temporalCoverage": (
                "PASS"
                if count and coverage_pass / count >= 0.70
                else "FAIL"
            ),
            "thresholdStability": (
                "PASS"
                if threshold_rates
                and min(threshold_rates.values()) >= 0.75
                else "FAIL"
            ),
            "phenologyFalsePositiveAudit": "PASS_INFORMATION_ONLY",
            "wetHeavyMultiFactorRule": "PASS_RULE_ENFORCED",
            "rankPromotion": "HELD_UNTIL_HOLDOUT_AND_P2A_VALIDATION",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sentinel", type=Path, required=True)
    parser.add_argument("--landsat", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--pilots", type=Path, required=True)
    parser.add_argument("--b114", type=Path)
    parser.add_argument("--b118", type=Path)
    parser.add_argument("--b101", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-year-end", type=int, default=2025)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    metrics = build_zone_metrics(
        pd.read_csv(args.sentinel),
        pd.read_csv(args.landsat),
        pd.read_csv(args.coverage),
        pd.read_csv(args.pilots),
        args.full_year_end,
    )
    b114 = load_optional_zip(
        args.b114,
        B114_MEMBER,
        [
            "canonicalCellId",
            "plateauBuildingCoverageFractionApprox",
            "plateauOpenSpaceFractionApprox",
            "plateauHeightP90M",
            "urbanCautionShare_300m",
            "urbanCautionShare_500m",
            "urbanFavorableShare_300m",
            "urbanFavorableShare_500m",
            "thermalCautionShare_300m",
            "thermalCautionShare_500m",
        ],
    )
    b118 = load_optional_zip(
        args.b118,
        B118_MEMBER,
        [
            "canonicalCellId",
            "groundwaterRegionalBand",
            "waterHistoryClass",
            "moistureAttentionClass",
            "underlandModelMaterialized",
            "underlandHighOrElevatedAttention",
            "underlandHistoricalWaterSignal",
            "evidenceConfidenceClass",
        ],
    )
    b101 = load_optional_zip(
        args.b101,
        B101_MEMBER,
        [
            "canonicalCellId",
            "crossScaleClass",
            "anomalyBandAgreement",
            "gradientBandAgreement",
            "regionalContext5km",
            "onsiteELFMeasurementPriority",
            "scoringEffect",
        ],
    )
    metrics = add_static_context(metrics, b114, b118, b101)
    metrics, threshold_table = assign_axes(metrics)
    profiles, false_positive = explain_and_classify(metrics)
    gate = make_gate(profiles, threshold_table, false_positive)

    profiles.to_csv(
        args.output / "F7_ZONE_EVIDENCE_PROFILES.csv",
        index=False,
    )
    threshold_table.to_csv(
        args.output / "F7_THRESHOLD_STABILITY.csv",
        index=False,
    )
    false_positive.to_csv(
        args.output / "F7_PHENOLOGY_FALSE_POSITIVE_AUDIT.csv",
        index=False,
    )
    (args.output / "F7_ADOPTION_GATE.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = [
        "# ECOSCAPE Green Quality F7 Evidence Gate",
        "",
        f"- pilot areas: {gate['pilotAreas']}",
        (
            "- temporal coverage: "
            f"{gate['gateResults']['temporalCoverage']} "
            f"({gate['coveragePassCount']}/{gate['pilotAreas']})"
        ),
        (
            "- threshold stability: "
            f"{gate['gateResults']['thresholdStability']} "
            f"{gate['thresholdStableRates']}"
        ),
        f"- descriptive bands: {gate['descriptiveBandCounts']}",
        f"- proxy support: {gate['proxySupportCounts']}",
        "- total score/ranking changes: none",
        "- actual wind-speed claim: prohibited",
        "- maintenance/cleanliness: UNKNOWN until image gate passes",
        "- rank promotion: held until NEXUS holdout and P2A validation",
    ]
    (args.output / "F7_REPORT.md").write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(gate, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
