#!/usr/bin/env python3
"""ECOSCAPE MOE 2024 vegetation QA300 exact-area intersection runner.

The locked QA300 sample is read from the existing Sentinel aggregate endpoint,
validated by its sample SHA, and converted back to canonical 100 m polygons.
Official MOE FeatureServer responses are cached as immutable receipts. Polygon
intersections are calculated in EPSG:6677 and replayed once to prove identical
raw inputs produce byte-identical facts.
"""
from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

import requests
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

try:
    from shapely.validation import make_valid
except ImportError:
    make_valid = None

SOURCE_ID = "SRC-ECO-MOE-001"
SOURCE_NAME = "環境省 現存植生図2024 関東ブロック"
SERVICE_URL = "https://svr-moej.gisservice.jp/arcgis/rest/services/Hosted/veg2024bk3/FeatureServer/0/query"
LAYER_URL = "https://svr-moej.gisservice.jp/arcgis/rest/services/Hosted/veg2024bk3/FeatureServer/0"
SAMPLE_URL = "https://ecoscape-qa300-aggregate.vercel.app/api/aggregate"
SAMPLE_VERSION = "ECOSCAPE_QA300_v1_20260816"
SAMPLE_SHA256 = "80573f7ceafb929af087ba88e8d822a2cd2aa583d04b4400be7aff2e988da131"
BUILD_ID = "ecos-e2-qa300-20260816-b13-moe-facts300"
METHOD_VERSION = "ECOSCAPE_MOE_AREA_INTERSECTION_v1"
GRID = {
    "originNorth": 35.839647862019405,
    "originWest": 139.43,
    "latitudeStep": 0.0008983111749910168,
    "longitudeStep": 0.0011042452218025757,
}
OUT_FIELDS = ["fid", "凡例コード", "凡例名", "植生自然度", "植生自然度区分", "植生区分", "作成年度", "地域ブロック"]
CELL_RE = re.compile(r"^g(?P<row>\d+)-(?P<col>\d+)$")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
TO_6677 = Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True).transform


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


def load_locked_sample() -> list[dict[str, Any]]:
    response = requests.get(SAMPLE_URL, timeout=(20, 90))
    response.raise_for_status()
    aggregate = response.json()
    contract = aggregate.get("contract") or {}
    if contract.get("rows") != 300 or contract.get("sampleSha256") != SAMPLE_SHA256:
        raise RuntimeError(f"Unexpected sample contract: {contract}")
    encoded = aggregate.get("payloadBase64")
    if not encoded:
        raise RuntimeError("Sentinel aggregate lacks payloadBase64")
    payload = json.loads(gzip.decompress(base64.b64decode(encoded)))
    rows = find_sample_rows(payload)
    if rows is None:
        raise RuntimeError("Could not locate 300 canonical rows in aggregate payload")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        order = int(row.get("sampleOrder") or row.get("sample_order") or index)
        cell_id = str(row.get("cellId") or row.get("canonicalCellId"))
        normalized.append({
            "sampleOrder": order,
            "cellId": cell_id,
            "municipalityCode": str(row.get("municipalityCode") or ""),
            "municipalityName": str(row.get("municipalityName") or ""),
        })
    normalized.sort(key=lambda row: row["sampleOrder"])
    if [r["sampleOrder"] for r in normalized] != list(range(1, 301)):
        raise RuntimeError("sampleOrder is not exactly 1..300")
    if len({r["cellId"] for r in normalized}) != 300:
        raise RuntimeError("QA300 cell IDs are not unique")
    return normalized


def cell_bounds(cell_id: str) -> tuple[float, float, float, float]:
    match = CELL_RE.fullmatch(cell_id)
    if not match:
        raise ValueError(f"Invalid canonical cell ID: {cell_id}")
    row = int(match.group("row"))
    col = int(match.group("col"))
    center_lat = GRID["originNorth"] - row * GRID["latitudeStep"]
    center_lon = GRID["originWest"] + col * GRID["longitudeStep"]
    return (
        center_lon - GRID["longitudeStep"] / 2,
        center_lat - GRID["latitudeStep"] / 2,
        center_lon + GRID["longitudeStep"] / 2,
        center_lat + GRID["latitudeStep"] / 2,
    )


def center_from_cell(cell_id: str) -> tuple[float, float]:
    west, south, east, north = cell_bounds(cell_id)
    return ((south + north) / 2, (west + east) / 2)


def receipt_path(raw_dir: Path, row: dict[str, Any]) -> Path:
    return raw_dir / f"{row['sampleOrder']:03d}_{row['cellId']}.json"


def fetch_cell(row: dict[str, Any], raw_dir: Path, retries: int = 5) -> dict[str, Any]:
    west, south, east, north = cell_bounds(row["cellId"])
    geometry = {"xmin": west, "ymin": south, "xmax": east, "ymax": north, "spatialReference": {"wkid": 4326}}
    params = {
        "where": "1=1",
        "geometry": json.dumps(geometry, separators=(",", ":")),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(OUT_FIELDS),
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "9",
        "returnExceededLimitFeatures": "true",
        "f": "geojson",
    }
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                SERVICE_URL,
                params=params,
                headers={"User-Agent": "ECOSCAPE-QA300/1.0 non-commercial-research"},
                timeout=(20, 90),
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(json.dumps(payload["error"], ensure_ascii=False))
            if "features" not in payload:
                raise RuntimeError("FeatureServer response lacks features")
            receipt = {
                "sourceId": SOURCE_ID,
                "sampleOrder": row["sampleOrder"],
                "cellId": row["cellId"],
                "request": {"endpoint": SERVICE_URL, "geometry": geometry, "outFields": OUT_FIELDS, "outSR": 4326},
                "http": {
                    "status": response.status_code,
                    "contentType": response.headers.get("content-type"),
                    "etag": response.headers.get("etag"),
                    "lastModified": response.headers.get("last-modified"),
                },
                "payload": payload,
            }
            raw = canonical_bytes(receipt)
            target = receipt_path(raw_dir, row)
            target.write_bytes(raw)
            return {"sampleOrder": row["sampleOrder"], "cellId": row["cellId"], "receiptPath": target.name, "receiptSha256": sha256(raw), "status": "FETCH_PASS", "attempt": attempt}
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(12.0, 0.8 * (2 ** (attempt - 1))))
    receipt = {
        "sourceId": SOURCE_ID,
        "sampleOrder": row["sampleOrder"],
        "cellId": row["cellId"],
        "request": {"endpoint": SERVICE_URL, "geometry": geometry, "outFields": OUT_FIELDS, "outSR": 4326},
        "fetchError": f"{type(last_error).__name__}: {last_error}",
    }
    raw = canonical_bytes(receipt)
    target = receipt_path(raw_dir, row)
    target.write_bytes(raw)
    return {"sampleOrder": row["sampleOrder"], "cellId": row["cellId"], "receiptPath": target.name, "receiptSha256": sha256(raw), "status": "FETCH_ERROR", "attempt": retries, "error": receipt["fetchError"]}


def valid_geometry(geometry: Any) -> Any:
    if geometry.is_valid:
        return geometry
    if make_valid is not None:
        return make_valid(geometry)
    return geometry.buffer(0)


def numeric_naturalness(value: Any) -> float | None:
    match = NUMBER_RE.search(str(value)) if value not in (None, "") else None
    return float(match.group(0)) if match else None


def entropy(fractions: Iterable[float]) -> tuple[float, float]:
    values = [v for v in fractions if v > 0]
    if not values:
        return 0.0, 0.0
    total = sum(values)
    probabilities = [v / total for v in values]
    raw = -sum(p * math.log(p) for p in probabilities)
    return raw, raw / math.log(len(probabilities)) if len(probabilities) > 1 else 0.0


def process_receipt(row: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    target = receipt_path(raw_dir, row)
    raw = target.read_bytes()
    receipt = json.loads(raw)
    center_lat, center_lon = center_from_cell(row["cellId"])
    base = {
        **row,
        "centerLat": center_lat,
        "centerLon": center_lon,
        "sourceId": SOURCE_ID,
        "sourceName": SOURCE_NAME,
        "sourceProductYear": "2024",
        "methodVersion": METHOD_VERSION,
        "buildId": BUILD_ID,
        "sampleVersion": SAMPLE_VERSION,
        "sampleSha256": SAMPLE_SHA256,
        "provenanceUrl": LAYER_URL,
        "rawReceiptFile": target.name,
        "rawReceiptSha256": sha256(raw),
        "scoringEffect": "none",
        "coverageAbsenceNotPenalty": True,
    }
    if receipt.get("fetchError"):
        return {**base, "status": "ERROR", "featureCount": 0, "coveredFraction": None, "uncoveredFraction": None, "categoryCount": 0, "categoryEntropy": None, "categoryEntropyNormalized": None, "dominantLegendCode": None, "dominantLegendName": None, "dominantVegetationNaturalness": None, "dominantNaturalnessClass": None, "dominantVegetationClass": None, "dominantFractionOfCovered": None, "naturalnessAreaWeightedMean": None, "sourceYears": [], "categoryFractions": [], "overlapExcessFraction": None, "missingReason": receipt["fetchError"]}

    features = sorted(receipt["payload"].get("features", []), key=lambda f: str((f.get("properties") or {}).get("fid", "")))
    cell_projected = transform(TO_6677, box(*cell_bounds(row["cellId"])))
    cell_area = float(cell_projected.area)
    intersections: list[Any] = []
    category_geometries: dict[tuple[str, ...], list[Any]] = {}
    category_properties: dict[tuple[str, ...], dict[str, Any]] = {}
    source_years: set[str] = set()
    warnings: list[str] = []

    for feature in features:
        properties = feature.get("properties") or {}
        if not feature.get("geometry"):
            continue
        try:
            projected = valid_geometry(transform(TO_6677, valid_geometry(shape(feature["geometry"]))))
            clipped = valid_geometry(projected.intersection(cell_projected))
            if clipped.is_empty or clipped.area <= 0.01:
                continue
        except Exception as exc:
            warnings.append(f"fid={properties.get('fid')}: {type(exc).__name__}: {exc}")
            continue
        key = tuple(str(properties.get(name) or "") for name in ["凡例コード", "凡例名", "植生自然度", "植生自然度区分", "植生区分"])
        intersections.append(clipped)
        category_geometries.setdefault(key, []).append(clipped)
        category_properties[key] = properties
        if properties.get("作成年度") not in (None, ""):
            source_years.add(str(properties["作成年度"]))

    if not intersections:
        status = "EXPLICIT_NO_INTERSECTION" if not warnings else "GEOMETRY_REJECTED"
        return {**base, "status": status, "featureCount": len(features), "coveredFraction": 0.0, "uncoveredFraction": 1.0, "categoryCount": 0, "categoryEntropy": 0.0, "categoryEntropyNormalized": 0.0, "dominantLegendCode": None, "dominantLegendName": None, "dominantVegetationNaturalness": None, "dominantNaturalnessClass": None, "dominantVegetationClass": None, "dominantFractionOfCovered": None, "naturalnessAreaWeightedMean": None, "sourceYears": sorted(source_years), "categoryFractions": [], "overlapExcessFraction": 0.0, "missingReason": "NO_INTERSECTING_VEGETATION_POLYGON" if status == "EXPLICIT_NO_INTERSECTION" else "; ".join(warnings)}

    covered_fraction = min(1.0, max(0.0, float(valid_geometry(unary_union(intersections)).area / cell_area)))
    categories: list[dict[str, Any]] = []
    category_sum = 0.0
    naturalness_num = 0.0
    naturalness_den = 0.0
    for key in sorted(category_geometries):
        area = float(valid_geometry(unary_union(category_geometries[key])).area)
        fraction = max(0.0, area / cell_area)
        category_sum += fraction
        properties = category_properties[key]
        naturalness = numeric_naturalness(properties.get("植生自然度"))
        if naturalness is not None:
            naturalness_num += naturalness * area
            naturalness_den += area
        categories.append({"legendCode": key[0] or None, "legendName": key[1] or None, "vegetationNaturalness": key[2] or None, "naturalnessClass": key[3] or None, "vegetationClass": key[4] or None, "cellFraction": fraction})
    for category in categories:
        category["fractionOfCovered"] = category["cellFraction"] / category_sum if category_sum else 0.0
    dominant = max(categories, key=lambda c: (c["cellFraction"], str(c["legendCode"])))
    raw_entropy, normalized_entropy = entropy(c["fractionOfCovered"] for c in categories)
    return {
        **base,
        "status": "PASS" if not warnings else "PASS_WITH_GEOMETRY_WARNINGS",
        "featureCount": len(features),
        "coveredFraction": covered_fraction,
        "uncoveredFraction": max(0.0, 1.0 - covered_fraction),
        "categoryCount": len(categories),
        "categoryEntropy": raw_entropy,
        "categoryEntropyNormalized": normalized_entropy,
        "dominantLegendCode": dominant["legendCode"],
        "dominantLegendName": dominant["legendName"],
        "dominantVegetationNaturalness": dominant["vegetationNaturalness"],
        "dominantNaturalnessClass": dominant["naturalnessClass"],
        "dominantVegetationClass": dominant["vegetationClass"],
        "dominantFractionOfCovered": dominant["fractionOfCovered"],
        "naturalnessAreaWeightedMean": naturalness_num / naturalness_den if naturalness_den else None,
        "sourceYears": sorted(source_years),
        "categoryFractions": categories,
        "overlapExcessFraction": max(0.0, category_sum - covered_fraction),
        "missingReason": "; ".join(warnings),
    }


def write_outputs(sample: list[dict[str, Any]], raw_dir: Path, output_dir: Path, manifest: list[dict[str, Any]]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    facts = sorted((process_receipt(row, raw_dir) for row in sample), key=lambda r: r["sampleOrder"])
    facts_bytes = canonical_bytes(facts)
    facts_sha = sha256(facts_bytes)
    (output_dir / "MOE_FACTS_300.json").write_bytes(facts_bytes)
    fields = ["sampleOrder", "cellId", "municipalityCode", "municipalityName", "centerLat", "centerLon", "status", "featureCount", "coveredFraction", "uncoveredFraction", "categoryCount", "categoryEntropy", "categoryEntropyNormalized", "dominantLegendCode", "dominantLegendName", "dominantVegetationNaturalness", "dominantNaturalnessClass", "dominantVegetationClass", "dominantFractionOfCovered", "naturalnessAreaWeightedMean", "sourceYears", "categoryFractions", "overlapExcessFraction", "sourceId", "sourceProductYear", "methodVersion", "provenanceUrl", "rawReceiptFile", "rawReceiptSha256", "sampleSha256", "buildId", "coverageAbsenceNotPenalty", "missingReason", "scoringEffect"]
    with (output_dir / "MOE_FACTS_300.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for fact in facts:
            record = {name: fact.get(name) for name in fields}
            record["sourceYears"] = json.dumps(record["sourceYears"], ensure_ascii=False, separators=(",", ":"))
            record["categoryFractions"] = json.dumps(record["categoryFractions"], ensure_ascii=False, separators=(",", ":"))
            writer.writerow(record)
    counts: dict[str, int] = {}
    for fact in facts:
        counts[fact["status"]] = counts.get(fact["status"], 0) + 1
    errors = sum(v for k, v in counts.items() if k in {"ERROR", "GEOMETRY_REJECTED"})
    provenance = sum(1 for fact in facts if fact.get("sourceId") and fact.get("provenanceUrl") and fact.get("rawReceiptSha256"))
    coverage = [fact["coveredFraction"] for fact in facts if fact["coveredFraction"] is not None]
    report = {
        "buildId": BUILD_ID,
        "sourceId": SOURCE_ID,
        "sampleVersion": SAMPLE_VERSION,
        "sampleSha256": SAMPLE_SHA256,
        "rows": len(facts),
        "uniqueOrders": len({f["sampleOrder"] for f in facts}),
        "uniqueCells": len({f["cellId"] for f in facts}),
        "statusCounts": counts,
        "silentMissing": 0 if len(facts) == 300 else 300 - len(facts),
        "errorCount": errors,
        "provenanceCount": provenance,
        "provenanceFraction": provenance / len(facts),
        "meanCoveredFraction": sum(coverage) / len(coverage) if coverage else None,
        "minCoveredFraction": min(coverage) if coverage else None,
        "maxCoveredFraction": max(coverage) if coverage else None,
        "factsSha256": facts_sha,
        "scoringEffect": "none",
        "qaPass": len(facts) == 300 and len({f["cellId"] for f in facts}) == 300 and errors == 0 and provenance == 300,
    }
    (output_dir / "MOE_QA_REPORT.json").write_bytes(canonical_bytes(report))
    (output_dir / "FETCH_MANIFEST.json").write_bytes(canonical_bytes(sorted(manifest, key=lambda r: r["sampleOrder"])))
    return facts_sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("fetch", "replay"), required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    sample = load_locked_sample()
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
            manifest.append({"sampleOrder": row["sampleOrder"], "cellId": row["cellId"], "receiptPath": target.name, "receiptSha256": sha256(target.read_bytes()), "status": "FETCH_ERROR" if receipt.get("fetchError") else "FETCH_PASS", "attempt": 0})
    result_sha = write_outputs(sample, args.raw_dir, args.output_dir, manifest)
    print(f"FACTS_SHA256={result_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
