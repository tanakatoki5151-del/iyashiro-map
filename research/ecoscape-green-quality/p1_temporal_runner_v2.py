#!/usr/bin/env python3
"""Compatibility runner for ECOSCAPE P1 temporal acquisition v2.

Uses the shared acquisition engine with explicit year bounds and deterministic
sharding. It does not change any ECOSCAPE score or ranking.
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
base.SHARD_INDEX = SHARD_INDEX
base.SHARD_COUNT = SHARD_COUNT
base.BUILD_ID = "ecoscape-green-quality-p1-temporal-20260819-v2"


if __name__ == "__main__":
    base.main()
    audit_path = base.OUT / "P1_AUDIT.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    errors_path = base.OUT / "P1_ERRORS.json"
    errors = (
        json.loads(errors_path.read_text(encoding="utf-8"))
        if errors_path.exists()
        else []
    )
    audit.update(
        {
            "buildId": "ecoscape-green-quality-p1-temporal-20260819-v2",
            "areasCsv": str(AREAS_CSV),
            "shardIndex": SHARD_INDEX,
            "shardCount": SHARD_COUNT,
            "errorsBySource": {
                source: sum(
                    1 for row in errors if row.get("source") == source
                )
                for source in sorted(
                    {row.get("source", "UNKNOWN") for row in errors}
                )
            },
            "landsatThermalAssetMissingErrors": sum(
                row.get("source") == "LANDSAT_SCENE"
                and "None of assets" in str(row.get("error"))
                for row in errors
            ),
            "rankingEffect": "none",
            "scoringEffect": "none",
            "note": (
                "Feasibility only. Sentinel acquisitions are deduplicated and "
                "the Landsat search is restricted to Landsat 8/9."
            ),
        }
    )
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
