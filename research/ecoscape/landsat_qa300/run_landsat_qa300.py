#!/usr/bin/env python3
"""ECOSCAPE Landsat QA300 static-fact runner.

Reads the locked QA300 sample from the Sentinel aggregate contract, calls the
existing Landsat cell runner directly, caches one immutable JSON receipt per
cell, and emits deterministic static facts. NO_VALID_CLEAR_PIXEL is retained as
an explicit quality rejection, never converted to zero or a bad score.
"""
from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

SOURCE_ID = "SRC-ECO-LANDSAT-001"
SAMPLE_URL = "https://ecoscape-qa300-aggregate.vercel.app/api/aggregate"
CELL_RUNNER = "https://ecoscape-landsat-cell-runner.vercel.app/api/cell"
SAMPLE_VERSION = "ECOSCAPE_QA300_v1_20260816"
SAMPLE_SHA256 = "80573f7ceafb929af087ba88e8d822a2cd2aa583d04b4400be7aff2e988da131"
BUILD_ID = "ecos-e2-qa300-20260816-b14-landsat-facts300-static"
METHOD_VERSION = "ECOSCAPE_LANDSAT_CELL_RUNNER_STATIC_v1"
GRID = {
    "originNorth": 35.839647862019405,
    "originWest": 139.43,
    "latitudeStep": 0.0008983111749910168,
    "longitudeStep": 0.0011042452218025757,
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_sample_rows(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list) and len(value) == 300 and all(isinstance(v, dict) for v in value):
        if all(("cellId" in v or "canonicalCellId" in v) for v in value):
            return value
    if isinstance(value, dict):
        for child in value.values():
            found = find_sample_rows(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = find_sample_rows(child)
            if found is not None:
                return found
    return None


def load_sample() -> list[dict[str, Any]]:
    response = requests.get(SAMPLE_URL, timeout=(20, 90))
    response.raise_for_status()
    aggregate = response.json()
    contract = aggregate.get("contract") or {}
    if contract.get("rows") != 300 or contract.get("sampleSha256") != SAMPLE_SHA256:
        raise RuntimeError(f"Unexpected sample contract: {contract}")
    payload = json.loads(gzip.decompress(base64.b64decode(aggregate["payloadBase64"])))
    rows = find_sample_rows(payload)
    if rows is None:
        raise RuntimeError("Could not locate locked QA300 rows")
    output = []
    for index, row in enumerate(rows, start=1):
        output.append({
            "sampleOrder": int(row.get("sampleOrder") or row.get("sample_order") or index),
            "cellId": str(row.get("cellId") or row.get("canonicalCellId")),
            "municipalityCode": str(row.get("municipalityCode") or ""),
            "municipalityName": str(row.get("municipalityName") or ""),
        })
    output.sort(key=lambda row: row["sampleOrder"])
    if [row["sampleOrder"] for row in output] != list(range(1, 301)):
        raise RuntimeError("sampleOrder is not exactly 1..300")
    if len({row["cellId"] for row in output}) != 300:
        raise RuntimeError("QA300 cell IDs are not unique")
    return output


def center(cell_id: str) -> tuple[float, float]:
    row_text, col_text = cell_id[1:].split("-")
    row = int(row_text)
    col = int(col_text)
    lat = GRID["originNorth"] - row * GRID["latitudeStep"]
    lon = GRID["originWest"] + col * GRID["longitudeStep"]
    return lat, lon


def bbox(cell_id: str) -> tuple[float, float, float, float]:
    lat, lon = center(cell_id)
    west = lon - 50 / (111320 * math.cos(math.radians(lat)))
    south = lat - 50 / 111320
    east = lon + 50 / (111320 * math.cos(math.radians(lat)))
    north = lat + 50 / 111320
    return west, south, east, north


def receipt_path(raw_dir: Path, row: dict[str, Any]) -> Path:
    return raw_dir / f"{row['sampleOrder']:03d}_{row['cellId']}.json"


def fetch_cell(row: dict[str, Any], raw_dir: Path, retries: int = 6) -> dict[str, Any]:
    bounds = bbox(row["cellId"])
    params = {
        "run": f"b14-{row['sampleOrder']}",
        "sampleOrder": row["sampleOrder"],
        "cellId": row["cellId"],
        "bbox": ",".join(f"{value:.15f}" for value in bounds),
    }
    url = CELL_RUNNER + "?" + urlencode(params)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=(20, 120), headers={"User-Agent": "ECOSCAPE-Landsat-QA300/1.0"})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "status" not in payload:
                raise RuntimeError("cell runner response lacks status")
            if payload.get("cellId") != row["cellId"] or int(payload.get("sampleOrder")) != row["sampleOrder"]:
                raise RuntimeError("cell runner identity mismatch")
            receipt = {
                "sourceId": SOURCE_ID,
                "sampleOrder": row["sampleOrder"],
                "cellId": row["cellId"],
                "requestUrl": url,
                "httpStatus": response.status_code,
                "payload": payload,
            }
            raw = canonical_bytes(receipt)
            target = receipt_path(raw_dir, row)
            target.write_bytes(raw)
            return {"sampleOrder": row["sampleOrder"], "cellId": row["cellId"], "status": "FETCH_PASS", "attempt": attempt, "receiptPath": target.name, "receiptSha256": sha256(raw)}
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(15.0, 0.7 * (2 ** (attempt - 1))))
    receipt = {
        "sourceId": SOURCE_ID,
        "sampleOrder": row["sampleOrder"],
        "cellId": row["cellId"],
        "requestUrl": url,
        "fetchError": f"{type(last_error).__name__}: {last_error}",
    }
    raw = canonical_bytes(receipt)
    target = receipt_path(raw_dir, row)
    target.write_bytes(raw)
    return {"sampleOrder": row["sampleOrder"], "cellId": row["cellId"], "status": "FETCH_ERROR", "attempt": retries, "receiptPath": target.name, "receiptSha256": sha256(raw), "error": receipt["fetchError"]}


def get_nested(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def normalize(row: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    target = receipt_path(raw_dir, row)
    raw = target.read_bytes()
    receipt = json.loads(raw)
    lat, lon = center(row["cellId"])
    base = {
        **row,
        "centerLat": lat,
        "centerLon": lon,
        "sourceId": SOURCE_ID,
        "methodVersion": METHOD_VERSION,
        "buildId": BUILD_ID,
        "sampleVersion": SAMPLE_VERSION,
        "sampleSha256": SAMPLE_SHA256,
        "rawReceiptFile": target.name,
        "rawReceiptSha256": sha256(raw),
        "scoringEffect": "none",
    }
    if receipt.get("fetchError"):
        return {**base, "status": "ERROR", "itemId": None, "acquisitionDate": None, "pixelCount": 0, "stRawValidCount": 0, "qualityValidCount": 0, "qualityValidFraction": 0.0, "landValidCount": 0, "landValidFraction": 0.0, "lstMeanC": None, "lstMedianC": None, "lstP10C": None, "lstP90C": None, "lstMinC": None, "lstMaxC": None, "stUncertaintyMeanK": None, "cloudFraction": None, "shadowFraction": None, "waterFraction": None, "provenanceUrl": None, "stAssetSha256": None, "qaPixelAssetSha256": None, "stQaAssetSha256": None, "missingReason": receipt["fetchError"]}
    payload = receipt["payload"]
    status = str(payload.get("status"))
    accepted = {"PASS", "NO_VALID_CLEAR_PIXEL"}
    if status not in accepted:
        status = "RUNNER_NONPASS"
    return {
        **base,
        "status": status,
        "itemId": get_nested(payload, "scene.itemId"),
        "acquisitionDate": get_nested(payload, "scene.acquisitionDate"),
        "pixelCount": payload.get("pixelCount", 0),
        "stRawValidCount": payload.get("stRawValidCount", 0),
        "qualityValidCount": payload.get("qualityValidCount", 0),
        "qualityValidFraction": payload.get("qualityValidFraction", 0.0),
        "landValidCount": payload.get("landValidCount", 0),
        "landValidFraction": payload.get("landValidFraction", 0.0),
        "lstMeanC": get_nested(payload, "lstQualityC.mean"),
        "lstMedianC": get_nested(payload, "lstQualityC.median"),
        "lstP10C": get_nested(payload, "lstQualityC.p10"),
        "lstP90C": get_nested(payload, "lstQualityC.p90"),
        "lstMinC": get_nested(payload, "lstQualityC.min"),
        "lstMaxC": get_nested(payload, "lstQualityC.max"),
        "stUncertaintyMeanK": get_nested(payload, "stUncertaintyK.mean"),
        "cloudFraction": get_nested(payload, "qaFractions.cloud"),
        "shadowFraction": get_nested(payload, "qaFractions.shadow"),
        "waterFraction": get_nested(payload, "qaFractions.water"),
        "provenanceUrl": payload.get("provenanceUrl"),
        "stAssetSha256": get_nested(payload, "assets.st.sha256"),
        "qaPixelAssetSha256": get_nested(payload, "assets.qaPixel.sha256"),
        "stQaAssetSha256": get_nested(payload, "assets.stQa.sha256"),
        "missingReason": "NO_VALID_CLEAR_PIXEL" if status == "NO_VALID_CLEAR_PIXEL" else ("LANDSAT_RUN_NONPASS" if status == "RUNNER_NONPASS" else ""),
    }


def write_outputs(sample: list[dict[str, Any]], raw_dir: Path, output_dir: Path, manifest: list[dict[str, Any]]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    facts = sorted((normalize(row, raw_dir) for row in sample), key=lambda row: row["sampleOrder"])
    facts_bytes = canonical_bytes(facts)
    facts_sha = sha256(facts_bytes)
    (output_dir / "LANDSAT_FACTS_300.json").write_bytes(facts_bytes)
    fields = ["sampleOrder", "cellId", "municipalityCode", "municipalityName", "centerLat", "centerLon", "status", "itemId", "acquisitionDate", "pixelCount", "stRawValidCount", "qualityValidCount", "qualityValidFraction", "landValidCount", "landValidFraction", "lstMeanC", "lstMedianC", "lstP10C", "lstP90C", "lstMinC", "lstMaxC", "stUncertaintyMeanK", "cloudFraction", "shadowFraction", "waterFraction", "sourceId", "provenanceUrl", "sampleSha256", "buildId", "missingReason", "methodVersion", "rawReceiptFile", "rawReceiptSha256", "stAssetSha256", "qaPixelAssetSha256", "stQaAssetSha256", "scoringEffect"]
    with (output_dir / "LANDSAT_FACTS_300.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for fact in facts:
            writer.writerow({key: fact.get(key) for key in fields})
    counts: dict[str, int] = {}
    for fact in facts:
        counts[fact["status"]] = counts.get(fact["status"], 0) + 1
    error_count = counts.get("ERROR", 0) + counts.get("RUNNER_NONPASS", 0)
    provenance_count = sum(1 for fact in facts if fact.get("provenanceUrl") and fact.get("rawReceiptSha256"))
    report = {
        "buildId": BUILD_ID,
        "sourceId": SOURCE_ID,
        "sampleVersion": SAMPLE_VERSION,
        "sampleSha256": SAMPLE_SHA256,
        "rows": len(facts),
        "uniqueOrders": len({fact["sampleOrder"] for fact in facts}),
        "uniqueCells": len({fact["cellId"] for fact in facts}),
        "statusCounts": counts,
        "explicitQualityRejected": counts.get("NO_VALID_CLEAR_PIXEL", 0),
        "silentMissing": 0 if len(facts) == 300 else 300 - len(facts),
        "errorCount": error_count,
        "provenanceCount": provenance_count,
        "provenanceFraction": provenance_count / len(facts),
        "factsSha256": facts_sha,
        "scoringEffect": "none",
        "qaPass": len(facts) == 300 and len({fact["cellId"] for fact in facts}) == 300 and error_count == 0 and provenance_count == 300,
    }
    (output_dir / "LANDSAT_QA_REPORT.json").write_bytes(canonical_bytes(report))
    (output_dir / "FETCH_MANIFEST.json").write_bytes(canonical_bytes(sorted(manifest, key=lambda row: row["sampleOrder"])))
    return facts_sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("fetch", "replay"), required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    sample = load_sample()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    if args.mode == "fetch":
        manifest: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as executor:
            futures = {executor.submit(fetch_cell, row, args.raw_dir): row for row in sample}
            for future in as_completed(futures):
                result = future.result()
                manifest.append(result)
                print(f"[{len(manifest):03d}/300] {result['cellId']} {result['status']} attempt={result['attempt']}", flush=True)
    else:
        manifest = []
        for row in sample:
            target = receipt_path(args.raw_dir, row)
            receipt = json.loads(target.read_bytes())
            manifest.append({"sampleOrder": row["sampleOrder"], "cellId": row["cellId"], "status": "FETCH_ERROR" if receipt.get("fetchError") else "FETCH_PASS", "attempt": 0, "receiptPath": target.name, "receiptSha256": sha256(target.read_bytes())})
    result_sha = write_outputs(sample, args.raw_dir, args.output_dir, manifest)
    print(f"FACTS_SHA256={result_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
