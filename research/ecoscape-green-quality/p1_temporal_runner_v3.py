#!/usr/bin/env python3
"""ECOSCAPE P1 temporal acquisition v3.

Queries each target phenological period independently so early-summer scenes
are not displaced by lower-cloud peak-summer scenes. Outputs raw, deduplicated
scene evidence and period-year composites. This is feasibility evidence only:
no ranking or score is changed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import planetary_computer
from pystac import Item
from pystac_client import Client

import p1_micro_pilot as base

OUT = Path(os.environ.get("ECOSCAPE_P1_OUTPUT", Path(__file__).resolve().parent / "output-v3"))
OUT.mkdir(parents=True, exist_ok=True)
AREAS_CSV = Path(os.environ.get("ECOSCAPE_P1_AREAS_CSV", Path(__file__).resolve().parent / "P1_MICRO_PILOT_AREAS.csv"))
YEAR_START = int(os.environ.get("ECOSCAPE_P1_YEAR_START", "2019"))
YEAR_END = int(os.environ.get("ECOSCAPE_P1_YEAR_END", "2026"))
SHARD_INDEX = int(os.environ.get("ECOSCAPE_P1_SHARD_INDEX", "0"))
SHARD_COUNT = int(os.environ.get("ECOSCAPE_P1_SHARD_COUNT", "1"))
YEARS = list(range(YEAR_START, YEAR_END + 1))
FULL_YEARS = [year for year in YEARS if year <= 2025]

PERIODS = {
    "SPRING": ((3, 15), (5, 31)),
    "EARLY_SUMMER": ((6, 1), (7, 15)),
    "PEAK_SUMMER": ((7, 16), (9, 15)),
    "AUTUMN_RECOVERY": ((9, 16), (11, 30)),
    "WINTER_DIAGNOSTIC": ((1, 1), (2, 28)),
}
CORE_PERIODS = ("SPRING", "EARLY_SUMMER", "PEAK_SUMMER", "AUTUMN_RECOVERY")

_original_pick_asset = base.pick_asset


def pick_asset_v3(item: Item, names):
    requested = list(names)
    if requested == ["lwir11", "ST_B10", "st_b10"]:
        requested = ["lwir11", "lwir", "ST_B10", "st_b10", "ST_B6", "st_b6"]
    return _original_pick_asset(item, requested)


base.pick_asset = pick_asset_v3


def read_areas():
    base.AREAS_CSV = AREAS_CSV
    areas = base.read_areas()
    if SHARD_COUNT < 1 or SHARD_INDEX < 0 or SHARD_INDEX >= SHARD_COUNT:
        raise ValueError(f"Invalid shard {SHARD_INDEX}/{SHARD_COUNT}")
    return [area for ordinal, area in enumerate(areas) if ordinal % SHARD_COUNT == SHARD_INDEX]


def date_window(year: int, period: str) -> tuple[str, str]:
    (m1, d1), (m2, d2) = PERIODS[period]
    return f"{year}-{m1:02d}-{d1:02d}", f"{year}-{m2:02d}-{d2:02d}"


def item_datetime_key(item: Item) -> str:
    if item.datetime:
        return item.datetime.isoformat()
    return str(item.properties.get("datetime") or item.id)


def unique_acquisitions(items: list[Item]) -> list[Item]:
    # Items can be duplicated across processing baselines/overlapping records.
    # Lowest cloud wins for an identical acquisition timestamp.
    ordered = sorted(items, key=lambda item: (item.properties.get("eo:cloud_cover", 1000), item.id))
    chosen: dict[str, Item] = {}
    for item in ordered:
        chosen.setdefault(item_datetime_key(item), item)
    return sorted(chosen.values(), key=lambda item: item_datetime_key(item))


def period_summary(scene_df: pd.DataFrame) -> pd.DataFrame:
    if scene_df.empty:
        return pd.DataFrame()
    metrics = ["ndviMedian", "eviMedian", "ndmiMedian", "ndreMedian", "validFraction500m"]
    keys = ["pilotId", "pilotCategory", "canonicalCellId", "officialAreaLabel", "year", "period"]
    grouped = scene_df.groupby(keys, dropna=False)
    out = grouped[metrics].median().reset_index()
    out = out.merge(grouped["date"].nunique().rename("distinctAcquisitionDates").reset_index())
    out = out.merge(
        grouped["date"].agg(lambda x: "|".join(sorted(set(str(v) for v in x)))).rename("sceneDates").reset_index()
    )
    return out


def thermal_summary(scene_df: pd.DataFrame) -> pd.DataFrame:
    if scene_df.empty:
        return pd.DataFrame()
    metrics = ["lstMedianC", "lstP10C", "lstP90C", "validFraction500m"]
    keys = ["pilotId", "pilotCategory", "canonicalCellId", "officialAreaLabel", "year"]
    grouped = scene_df.groupby(keys, dropna=False)
    out = grouped[metrics].median().reset_index()
    out = out.merge(grouped["date"].nunique().rename("distinctAcquisitionDates").reset_index())
    out = out.merge(
        grouped["date"].agg(lambda x: "|".join(sorted(set(str(v) for v in x)))).rename("sceneDates").reset_index()
    )
    return out


def main() -> None:
    areas = read_areas()
    s2_client = Client.open(base.S2_STAC)
    landsat_client = Client.open(base.LANDSAT_STAC)
    s2_rows: list[dict[str, Any]] = []
    ls_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for area in areas:
        for year in YEARS:
            for period in PERIODS:
                start, end = date_window(year, period)
                try:
                    items = unique_acquisitions(base.search_s2(s2_client, area, start, end))
                except Exception as exc:
                    errors.append({"source":"S2_SEARCH","pilotId":area.pilot_id,"year":year,"period":period,"error":repr(exc)})
                    continue
                accepted = 0
                for item in items[:10]:
                    try:
                        row = base.s2_scene_metrics(item, area)
                        if row["validFraction500m"] >= 0.45:
                            dt = pd.to_datetime(row["datetime"], utc=True)
                            row.update({"year": year, "period": period, "date": dt.date().isoformat()})
                            s2_rows.append(row)
                            accepted += 1
                        if accepted >= 3:
                            break
                    except Exception as exc:
                        errors.append({"source":"S2_SCENE","pilotId":area.pilot_id,"year":year,"period":period,"itemId":item.id,"error":repr(exc)})

            try:
                items = unique_acquisitions(base.search_landsat(landsat_client, area, year))
            except Exception as exc:
                errors.append({"source":"LANDSAT_SEARCH","pilotId":area.pilot_id,"year":year,"error":repr(exc)})
                continue
            accepted = 0
            for raw_item in items[:14]:
                try:
                    row = base.landsat_scene_metrics(raw_item, area)
                    if row["validFraction500m"] >= 0.35 and row["lstMedianC"] is not None:
                        dt = pd.to_datetime(row["datetime"], utc=True)
                        row.update({"year": year, "date": dt.date().isoformat()})
                        ls_rows.append(row)
                        accepted += 1
                    if accepted >= 5:
                        break
                except Exception as exc:
                    errors.append({"source":"LANDSAT_SCENE","pilotId":area.pilot_id,"year":year,"itemId":raw_item.id,"error":repr(exc)})

    s2_df = pd.DataFrame(s2_rows)
    ls_df = pd.DataFrame(ls_rows)
    s2_df.to_csv(OUT / "P1_SENTINEL_SCENES_V3.csv", index=False)
    ls_df.to_csv(OUT / "P1_LANDSAT_SUMMER_SCENES_V3.csv", index=False)
    psummary = period_summary(s2_df)
    hsummary = thermal_summary(ls_df)
    psummary.to_csv(OUT / "P1_SENTINEL_PERIOD_COMPOSITES_V3.csv", index=False)
    hsummary.to_csv(OUT / "P1_LANDSAT_MULTI_SUMMER_COMPOSITES_V3.csv", index=False)
    (OUT / "P1_ERRORS_V3.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    coverage_rows = []
    for area in areas:
        pg = psummary[psummary["pilotId"] == area.pilot_id] if not psummary.empty else pd.DataFrame()
        hg = hsummary[hsummary["pilotId"] == area.pilot_id] if not hsummary.empty else pd.DataFrame()
        core = pg[(pg["period"].isin(CORE_PERIODS)) & (pg["year"].isin(FULL_YEARS))] if not pg.empty else pd.DataFrame()
        core_2plus = int((core["distinctAcquisitionDates"] >= 2).sum()) if not core.empty else 0
        period_counts = {}
        for period in PERIODS:
            x = pg[(pg["period"] == period) & (pg["year"].isin(FULL_YEARS))] if not pg.empty else pd.DataFrame()
            period_counts[f"{period}_fullYears2Plus"] = int((x["distinctAcquisitionDates"] >= 2).sum()) if not x.empty else 0
        coverage_rows.append({
            "pilotId": area.pilot_id,
            "pilotCategory": area.category,
            "canonicalCellId": area.cell_id,
            "officialAreaLabel": area.label,
            "sentinelSceneRows": int((s2_df["pilotId"] == area.pilot_id).sum()) if not s2_df.empty else 0,
            "fullCorePeriodYearTargets": len(FULL_YEARS) * len(CORE_PERIODS),
            "fullCorePeriodYears2Plus": core_2plus,
            "fullCoreCoverageRate": core_2plus / (len(FULL_YEARS) * len(CORE_PERIODS)),
            "landsatSceneRows": int((ls_df["pilotId"] == area.pilot_id).sum()) if not ls_df.empty else 0,
            "landsatFullYearsCovered": int(hg[hg["year"].isin(FULL_YEARS)]["year"].nunique()) if not hg.empty else 0,
            **period_counts,
        })
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(OUT / "P1_COVERAGE_SUMMARY_V3.csv", index=False)

    error_by_source = {}
    for row in errors:
        error_by_source[row.get("source", "UNKNOWN")] = error_by_source.get(row.get("source", "UNKNOWN"), 0) + 1
    thermal_missing = sum(row.get("source") == "LANDSAT_SCENE" and "None of assets" in str(row.get("error")) for row in errors)
    audit = {
        "buildId": "ecoscape-green-quality-p1-temporal-period-specific-20260819-v3",
        "pilotAreas": len(areas),
        "yearStart": YEAR_START,
        "yearEnd": YEAR_END,
        "fullComparisonYears": FULL_YEARS,
        "periods": list(PERIODS),
        "sentinelSceneRows": int(len(s2_df)),
        "landsatSceneRows": int(len(ls_df)),
        "errorCount": len(errors),
        "errorsBySource": error_by_source,
        "landsatThermalAssetMissingErrors": thermal_missing,
        "medianFullCoreCoverageRate": float(coverage["fullCoreCoverageRate"].median()) if len(coverage) else 0,
        "minimumFullCoreCoverageRate": float(coverage["fullCoreCoverageRate"].min()) if len(coverage) else 0,
        "rankingEffect": "none",
        "scoringEffect": "none",
        "releaseState": "FEASIBILITY_EVIDENCE_ONLY",
        "note": "Each phenological period was searched independently; identical acquisition timestamps were deduplicated before raster reads.",
    }
    (OUT / "P1_AUDIT_V3.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
