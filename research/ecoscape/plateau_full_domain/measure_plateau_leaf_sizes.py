#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

from discover_plateau_datasets import CATALOG_URL
from inventory_plateau_leaf_tiles import select_roots, walk_area

BUILD_ID = "ecos-practical-v2-20260817-m1-plateau-leaf-size-11280"
WORKERS = 32


def measure_one(url: str) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "ECOSCAPE-PLATEAU-SIZE/1.0"})
    errors = []
    for attempt in range(1, 5):
        try:
            response = session.head(url, allow_redirects=True, timeout=(20, 120))
            if response.status_code >= 400:
                raise requests.HTTPError(f"HEAD {response.status_code}")
            length = response.headers.get("Content-Length")
            if length and length.isdigit():
                return {
                    "url": url,
                    "status": "PASS_HEAD",
                    "bytes": int(length),
                    "contentType": response.headers.get("Content-Type"),
                    "etag": response.headers.get("ETag"),
                }
            probe = session.get(url, headers={"Range": "bytes=0-0"}, timeout=(20, 120))
            probe.raise_for_status()
            content_range = probe.headers.get("Content-Range") or ""
            total = content_range.rsplit("/", 1)[-1] if "/" in content_range else ""
            if total.isdigit():
                return {
                    "url": url,
                    "status": "PASS_RANGE",
                    "bytes": int(total),
                    "contentType": probe.headers.get("Content-Type"),
                    "etag": probe.headers.get("ETag"),
                }
            return {
                "url": url,
                "status": "PASS_BODY_FALLBACK",
                "bytes": len(probe.content),
                "contentType": probe.headers.get("Content-Type"),
                "etag": probe.headers.get("ETag"),
            }
        except Exception as exc:
            errors.append(f"attempt{attempt}:{type(exc).__name__}:{exc}")
            time.sleep(min(8, attempt * 2))
    return {"url": url, "status": "ERROR", "bytes": None, "errors": errors}


def main() -> int:
    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    catalog_response = requests.get(
        CATALOG_URL,
        timeout=(30, 240),
        headers={"User-Agent": "ECOSCAPE-PLATEAU-SIZE/1.0"},
    )
    catalog_response.raise_for_status()
    roots = select_roots(catalog_response.json())

    final_rows = []
    for index, root in enumerate(roots, start=1):
        report, rows = walk_area(requests.Session(), root)
        if report["traversalErrors"]:
            raise RuntimeError(f"Traversal failed for {root['targetCode']}: {report['traversalErrors']}")
        final_rows.extend(row for row in rows if row["isFinalContent"])
        print(f"Traversal {index}/{len(roots)} finalTotal={len(final_rows)}", flush=True)

    url_to_row = {row["contentUrl"]: row for row in final_rows}
    if len(url_to_row) != len(final_rows):
        raise RuntimeError("Duplicate final URLs before size measurement")

    measurements: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(measure_one, url): url for url in url_to_row}
        for index, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            measurements[row["url"]] = row
            if index % 500 == 0:
                errors = sum(1 for item in measurements.values() if item["status"] == "ERROR")
                print(f"Size {index}/{len(url_to_row)} errors={errors}", flush=True)

    output_rows = []
    by_code: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "tileCount": 0,
        "knownBytes": 0,
        "unknownTiles": 0,
        "suffixCounts": Counter(),
        "statusCounts": Counter(),
        "minBytes": None,
        "maxBytes": None,
    })
    for url, source in url_to_row.items():
        measured = measurements[url]
        combined = {
            "targetCode": source["targetCode"],
            "datasetId": source["datasetId"],
            "datasetYear": source["datasetYear"],
            "suffix": source["suffix"],
            **measured,
        }
        output_rows.append(combined)
        agg = by_code[source["targetCode"]]
        agg["tileCount"] += 1
        agg["suffixCounts"][source["suffix"]] += 1
        agg["statusCounts"][measured["status"]] += 1
        value = measured.get("bytes")
        if isinstance(value, int):
            agg["knownBytes"] += value
            agg["minBytes"] = value if agg["minBytes"] is None else min(agg["minBytes"], value)
            agg["maxBytes"] = value if agg["maxBytes"] is None else max(agg["maxBytes"], value)
        else:
            agg["unknownTiles"] += 1

    area_rows = []
    for code in sorted(by_code):
        row = by_code[code]
        area_rows.append({
            "targetCode": code,
            "tileCount": row["tileCount"],
            "knownBytes": row["knownBytes"],
            "unknownTiles": row["unknownTiles"],
            "meanBytes": row["knownBytes"] / max(1, row["tileCount"] - row["unknownTiles"]),
            "minBytes": row["minBytes"],
            "maxBytes": row["maxBytes"],
            "suffixCounts": dict(sorted(row["suffixCounts"].items())),
            "statusCounts": dict(sorted(row["statusCounts"].items())),
        })

    status_counts = Counter(row["status"] for row in output_rows)
    known = [row["bytes"] for row in output_rows if isinstance(row.get("bytes"), int)]
    audit = {
        "buildId": BUILD_ID,
        "areas": len(area_rows),
        "finalTiles": len(output_rows),
        "statusCounts": dict(sorted(status_counts.items())),
        "knownLengthTiles": len(known),
        "unknownLengthTiles": len(output_rows) - len(known),
        "totalKnownBytes": sum(known),
        "meanBytes": sum(known) / max(1, len(known)),
        "minBytes": min(known) if known else None,
        "maxBytes": max(known) if known else None,
        "sha256OfSortedUrlSizePairs": hashlib.sha256(
            "\n".join(f"{row['url']}\t{row.get('bytes')}" for row in sorted(output_rows, key=lambda x: x["url"])).encode("utf-8")
        ).hexdigest(),
        "qaPass": len(area_rows) == 48 and len(output_rows) == 11280 and status_counts.get("ERROR", 0) == 0 and len(known) == len(output_rows),
        "scoringEffect": "none",
    }

    (output / "PLATEAU_LEAF_SIZE_ROWS_11280.json").write_text(
        json.dumps(output_rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (output / "PLATEAU_LEAF_SIZE_BY_AREA_48.json").write_text(
        json.dumps(area_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "PLATEAU_LEAF_SIZE_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    names = [
        "PLATEAU_LEAF_SIZE_ROWS_11280.json",
        "PLATEAU_LEAF_SIZE_BY_AREA_48.json",
        "PLATEAU_LEAF_SIZE_AUDIT.json",
    ]
    (output / "SHA256SUMS.txt").write_text(
        "\n".join(f"{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}" for name in names) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not audit["qaPass"]:
        raise SystemExit("PLATEAU leaf size QA failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
