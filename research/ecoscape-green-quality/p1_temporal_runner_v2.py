#!/usr/bin/env python3
"""Compatibility runner for ECOSCAPE P1 temporal acquisition v2.

Adds Landsat-7 thermal asset support and optional deterministic sharding
without changing the original micro-pilot scoring/ranking guardrails.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import p1_micro_pilot as base

YEAR_START = int(os.environ.get("ECOSCAPE_P1_YEAR_START", "2019"))
YEAR_END = int(os.environ.get("ECOSCAPE_P1_YEAR_END", "2026"))
SHARD_INDEX = int(os.environ.get("ECOSCAPE_P1_SHARD_INDEX", "0"))
SHARD_COUNT = int(os.environ.get("ECOSCAPE_P1_SHARD_COUNT", "1"))
AREAS_CSV = Path(
    os.environ.get(
        "ECOSCAPE_P1_AREAS_CSV",
        str(Path(__file__).resolve().parent / "P1_MICRO_PILOT_AREAS.csv"),
    )
)

base.YEARS = list(range(YEAR_START, YEAR_END + 1))
base.AREAS_CSV = AREAS_CSV

_original_pick_asset = base.pick_asset
_original_read_areas = base.read_areas


def pick_asset_v2(item, names):
    requested = list(names)
    if requested == ["lwir11", "ST_B10", "st_b10"]:
        requested = ["lwir11", "lwir", "ST_B10", "st_b10", "ST_B6", "st_b6"]
    return _original_pick_asset(item, requested)


def read_areas_v2():
    areas = _original_read_areas()
    if SHARD_COUNT < 1 or SHARD_INDEX < 0 or SHARD_INDEX >= SHARD_COUNT:
        raise ValueError(f"Invalid shard {SHARD_INDEX}/{SHARD_COUNT}")
    return [area for ordinal, area in enumerate(areas) if ordinal % SHARD_COUNT == SHARD_INDEX]


base.pick_asset = pick_asset_v2
base.read_areas = read_areas_v2


if __name__ == "__main__":
    base.main()
    audit_path = base.OUT / "P1_AUDIT.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    errors_path = base.OUT / "P1_ERRORS.json"
    errors = json.loads(errors_path.read_text(encoding="utf-8")) if errors_path.exists() else []
    audit.update(
        {
            "buildId": "ecoscape-green-quality-p1-temporal-20260819-v2",
            "areasCsv": str(AREAS_CSV),
            "shardIndex": SHARD_INDEX,
            "shardCount": SHARD_COUNT,
            "errorsBySource": {
                source: sum(1 for row in errors if row.get("source") == source)
                for source in sorted({row.get("source", "UNKNOWN") for row in errors})
            },
            "landsatThermalAssetMissingErrors": sum(
                row.get("source") == "LANDSAT_SCENE" and "None of assets" in str(row.get("error"))
                for row in errors
            ),
            "rankingEffect": "none",
            "scoringEffect": "none",
            "note": "Feasibility only. Landsat-7 lwir is supported; no ranking promotion.",
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
