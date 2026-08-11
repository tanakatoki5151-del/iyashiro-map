#!/usr/bin/env python3
"""Audit V10 100m evidence coverage without inventing negative evidence.

Core invariant:
- legacy 85,767 / 71.1% is an aggregate-only historical baseline;
- it must never be reduced from land-use coverage, catalog no-hits, or log counts;
- a comparable zero-cell rate can only be computed from an explicit cell-id universe
  and explicit per-cell execution/evidence records.

This tool is intentionally conservative. It produces an audit report and fails
closed when legacy cell membership is unavailable.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

LEGACY_ZERO_COUNT = 85_767
LEGACY_ZERO_SHARE = 71.1
V10_CELL_COUNT = 120_662


def load_logs(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            rows = obj.get("logs", [])
        else:
            rows = obj
        if not isinstance(rows, list):
            raise ValueError("JSON logs must be a list or an object with logs[]")
        return [r for r in rows if isinstance(r, dict)]
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_cell_ids(path: Path) -> set[str]:
    if path.suffix.lower() == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            obj = obj.get("cellIds", [])
        return {str(x).strip() for x in obj if str(x).strip()}
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for key in ("cellId", "セルID", "cell_id"):
        if rows and key in rows[0]:
            return {str(r.get(key, "")).strip() for r in rows if str(r.get(key, "")).strip()}
    raise ValueError("No cellId column found")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", type=Path, required=True)
    ap.add_argument("--all-cells", type=Path)
    ap.add_argument("--legacy-zero-cells", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    logs = load_logs(args.logs)
    ids = [str(r.get("logId") or r.get("ログID") or "").strip() for r in logs]
    ids = [x for x in ids if x]
    dup = sorted(k for k, n in Counter(ids).items() if n > 1)

    cell_logs = []
    for r in logs:
        cell = str(r.get("cellId") or r.get("セルID") or "").strip()
        result = str(r.get("result") or r.get("結果") or "").strip().lower()
        if cell and result not in {"pending", "not_started", ""}:
            cell_logs.append(cell)
    executed_cells = set(cell_logs)

    report = {
        "schemaVersion": "coverage-v5-audit-1.0",
        "v10CellCount": V10_CELL_COUNT,
        "legacyBaseline": {
            "zeroEvidenceCellCount": LEGACY_ZERO_COUNT,
            "zeroEvidenceCellSharePercent": LEGACY_ZERO_SHARE,
            "status": "frozen_aggregate_only",
            "comparableUpdateAllowed": False,
        },
        "logAudit": {
            "rowCount": len(logs),
            "idCount": len(ids),
            "uniqueIdCount": len(set(ids)),
            "duplicateIds": dup,
            "cellSpecificExecutedCellCount": len(executed_cells),
        },
        "policy": {
            "landUseCoverageIsNegativeMajorHistoryEvidence": False,
            "catalogNoHitIsProofOfAbsence": False,
            "logCountMayReduceLegacyZeroCount": False,
            "explicitCellMembershipRequiredForComparableRate": True,
        },
    }

    if args.all_cells:
        all_cells = load_cell_ids(args.all_cells)
        report["newExecutionCoverage"] = {
            "universeCellCount": len(all_cells),
            "executedCellCount": len(all_cells & executed_cells),
            "unexecutedCellCount": len(all_cells - executed_cells),
            "executedSharePercent": round(100 * len(all_cells & executed_cells) / len(all_cells), 4) if all_cells else 0,
            "series": "new_cellid_execution_coverage",
        }

    if args.legacy_zero_cells:
        legacy = load_cell_ids(args.legacy_zero_cells)
        report["legacyBaseline"]["explicitMembershipProvided"] = True
        report["legacyBaseline"]["providedCellCount"] = len(legacy)
        report["legacyBaseline"]["membershipCountMatchesAggregate"] = len(legacy) == LEGACY_ZERO_COUNT
        if len(legacy) == LEGACY_ZERO_COUNT:
            remaining = legacy - executed_cells
            report["legacyBaseline"]["comparableUpdateAllowed"] = True
            report["legacyComparableUpdate"] = {
                "remainingZeroSetCountBeforeEvidenceSemanticsReview": len(remaining),
                "caution": "Execution alone is not automatically evidence coverage. Review result semantics before publishing a replacement rate.",
            }
    else:
        report["legacyBaseline"]["explicitMembershipProvided"] = False
        report["legacyBaseline"]["reason"] = (
            "The reconstructed V10 source stores 85,767 / 71.1 as hard-coded aggregate values; "
            "no legacy zero-cell membership list is present."
        )

    report["pass"] = not dup
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
