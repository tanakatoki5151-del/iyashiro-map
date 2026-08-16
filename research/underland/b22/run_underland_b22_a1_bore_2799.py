#!/usr/bin/env python3
"""UNDERLAND B22: execute KuniJiban acquisition for the B19J 2,799-cell queue.

Conservative contract:
- 2,799 target cells are compressed into deduplicated z13 tile requests.
- Each cell loads the center tile plus its 8 neighbors before testing 100/300/500 m.
- Runtime/source failures remain explicit and are never interpreted as borehole absence.
- Only unique nearest markers within 500 m are detail-queried.
- Marker detail and source-native XML are acquisition evidence, not strict A4 promotion.
- No scoring, ranking, or Sites write is performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = "https://www.kunijiban.pwri.go.jp/viewer/"
MARKERS_URL = urllib.parse.urljoin(BASE, "server/markers.php")
MARKER_URL = urllib.parse.urljoin(BASE, "server/marker.php")
REFER_URL = urllib.parse.urljoin(BASE, "refer/")
USER_AGENT = (
    "UNDERLAND-B22-A1-BORE/1.0 "
    "(+https://github.com/tanakatoki5151-del/iyashiro-map; low-rate public research)"
)
ZOOM = 13
SEARCH_RADIUS_M = 500.0
EARTH_RADIUS_M = 6_371_008.8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({k for row in rows for k in row}) if rows else []
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if fields:
            writer.writeheader()
            for row in rows:
                cooked: dict[str, Any] = {}
                for key in fields:
                    value = row.get(key)
                    if isinstance(value, (list, dict, tuple, set)):
                        cooked[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
                    else:
                        cooked[key] = value
                writer.writerow(cooked)


def latlon_to_tile(lat: float, lon: float, z: int = ZOOM) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class FetchRecord:
    assetKind: str
    requestedUrl: str
    state: str = "runtime_incomplete"
    finalUrl: str | None = None
    httpStatus: int | None = None
    contentType: str | None = None
    bytes: int | None = None
    sha256: str | None = None
    elapsedMs: float | None = None
    savedAs: str | None = None
    error: str | None = None
    attempts: int = 0


class LowRateFetcher:
    def __init__(self, delay: float, timeout: float, retries: int) -> None:
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.retries = retries
        self.last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def get(self, kind: str, url: str, out_path: Path) -> FetchRecord:
        record = FetchRecord(assetKind=kind, requestedUrl=url)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, self.retries + 2):
            record.attempts = attempt
            self._throttle()
            started = time.monotonic()
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json, application/xml, text/xml, text/html, */*",
                    "Accept-Language": "ja,en;q=0.7",
                    "Cache-Control": "no-cache",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=ssl.create_default_context()) as resp:
                    self.last_request_at = time.monotonic()
                    data = resp.read()
                    record.finalUrl = resp.geturl()
                    record.httpStatus = int(getattr(resp, "status", 200))
                    record.contentType = resp.headers.get("Content-Type")
                    record.bytes = len(data)
                    record.sha256 = sha256_bytes(data)
                    record.elapsedMs = round((time.monotonic() - started) * 1000, 1)
                    out_path.write_bytes(data)
                    record.savedAs = str(out_path)
                    record.state = "fetched"
                    return record
            except urllib.error.HTTPError as exc:
                self.last_request_at = time.monotonic()
                record.httpStatus = exc.code
                record.finalUrl = exc.geturl()
                record.contentType = exc.headers.get("Content-Type") if exc.headers else None
                try:
                    body = exc.read()
                except Exception:
                    body = b""
                if body:
                    out_path.write_bytes(body)
                    record.bytes = len(body)
                    record.sha256 = sha256_bytes(body)
                    record.savedAs = str(out_path)
                record.elapsedMs = round((time.monotonic() - started) * 1000, 1)
                record.error = f"HTTPError: {exc.code} {exc.reason}"
                if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt <= self.retries:
                    time.sleep(min(8.0, 1.5 * 2 ** (attempt - 1)))
                    continue
                return record
            except Exception as exc:  # noqa: BLE001
                self.last_request_at = time.monotonic()
                record.elapsedMs = round((time.monotonic() - started) * 1000, 1)
                record.error = f"{type(exc).__name__}: {exc}"
                if attempt <= self.retries:
                    time.sleep(min(8.0, 1.5 * 2 ** (attempt - 1)))
                    continue
                return record
        return record


def parse_markers(data: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    info: dict[str, Any] = {"schemaOk": False, "sourceSuccess": False, "markerCount": 0}
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        info["parseError"] = f"{type(exc).__name__}: {exc}"
        return [], info
    values = payload.get("data", {}).get("values") if isinstance(payload, dict) else None
    success = bool(payload.get("header", {}).get("success")) if isinstance(payload, dict) else False
    schema_ok = isinstance(values, list)
    info.update({"schemaOk": schema_ok, "sourceSuccess": success, "markerCount": len(values) if schema_ok else 0})
    return values if schema_ok else [], info


def flag_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "none", "null"}


def extract_tag_values(text: str, tag: str) -> list[str]:
    pattern = rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>"
    return [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(pattern, text, flags=re.S)]


def parse_boring_xml(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    try:
        text = data.decode("cp932")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    dates = [x for x in extract_tag_values(text, "調査期間_開始年月日") + extract_tag_values(text, "調査期間_終了年月日") if x]
    water_dates = [x for x in extract_tag_values(text, "孔内水位_測定年月日") if x]
    water_levels = [x for x in extract_tag_values(text, "孔内水位_孔内水位") if x]
    spt_depths = [x for x in extract_tag_values(text, "標準貫入試験_開始深度") if x]
    spt_hits = [x for x in extract_tag_values(text, "標準貫入試験_合計打撃回数") if x]
    lithologies = [x for x in extract_tag_values(text, "土質岩種区分_土質岩種区分1") if x]
    return {
        "parsedXml": True,
        "surveyDates": dates,
        "waterLevelDates": water_dates,
        "waterLevels": water_levels,
        "sptRecordCount": max(len(spt_depths), len(spt_hits)),
        "lithologyRecordCount": len(lithologies),
        "lithologies": lithologies,
        "hasObservedWater": bool(water_levels),
        "hasExplicitWaterLevelDate": bool(water_dates),
    }


def build_requests(targets: list[dict[str, str]]) -> tuple[dict[str, list[tuple[int, int]]], dict[tuple[int, int], list[str]]]:
    cell_tiles: dict[str, list[tuple[int, int]]] = {}
    tile_targets: dict[tuple[int, int], list[str]] = defaultdict(list)
    for row in targets:
        x, y = latlon_to_tile(float(row["latitude"]), float(row["longitude"]))
        tiles = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        cell_tiles[row["cellId"]] = tiles
        for tile in tiles:
            tile_targets[tile].append(row["cellId"])
    return cell_tiles, dict(tile_targets)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--detail-delay", type=float, default=0.25)
    ap.add_argument("--timeout", type=float, default=40.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = args.output.resolve()
    if out.exists():
        shutil.rmtree(out)
    for part in ["raw/tiles", "raw/marker", "raw/boring_xml", "raw/soiltest_xml", "normalized", "analysis"]:
        (out / part).mkdir(parents=True, exist_ok=True)

    targets = list(csv.DictReader(args.targets.open(encoding="utf-8-sig")))
    if len(targets) != 2799:
        raise RuntimeError(f"expected 2799 targets, got {len(targets)}")
    cell_tiles, tile_targets = build_requests(targets)
    tile_rows = [
        {
            "requestOrder": i,
            "x": x,
            "y": y,
            "z": ZOOM,
            "targetCellCount": len(set(tile_targets[(x, y)])),
            "targetCellIds": sorted(set(tile_targets[(x, y)])),
            "url": f"{MARKERS_URL}?{urllib.parse.urlencode({'x': x, 'y': y, 'z': ZOOM})}",
            "cacheFile": f"z{ZOOM}_{x}_{y}.json",
        }
        for i, (x, y) in enumerate(sorted(tile_targets), start=1)
    ]
    write_csv(out / "normalized" / "UNDERLAND_B22_TILE_REQUEST_MANIFEST.csv", tile_rows)

    build_summary = {
        "buildId": "underland-b22-a1-bore-2799-execution-v1",
        "startedAtUTC": utc_now(),
        "targetCells": len(targets),
        "deduplicatedTileRequests": len(tile_rows),
        "neighborRadiusTiles": 1,
        "searchRadiusContract": "<=100m_then_<=300m_then_<=500m",
        "strictA4Promotion": 0,
        "scoringEffect": "none",
        "absenceInferenceFromFailure": "prohibited",
    }
    if args.dry_run:
        build_summary["state"] = "dry_run_complete"
        write_json(out / "RUN_SUMMARY.json", build_summary)
        print(json.dumps(build_summary, ensure_ascii=False, indent=2))
        return 0

    fetcher = LowRateFetcher(args.delay, args.timeout, args.retries)
    request_ledger: list[dict[str, Any]] = []
    tile_markers: dict[tuple[int, int], list[dict[str, Any]]] = {}
    marker_catalog: dict[int, dict[str, Any]] = {}

    for row in tile_rows:
        x, y = int(row["x"]), int(row["y"])
        raw_path = out / "raw" / "tiles" / row["cacheFile"]
        rec = fetcher.get("marker_tile", row["url"], raw_path)
        values: list[dict[str, Any]] = []
        schema: dict[str, Any] = {"schemaOk": False, "sourceSuccess": False, "markerCount": 0}
        if rec.state == "fetched":
            values, schema = parse_markers(raw_path.read_bytes())
        tile_markers[(x, y)] = values
        for value in values:
            try:
                marker_catalog[int(value["id"])] = value
            except (KeyError, TypeError, ValueError):
                continue
        request_ledger.append({**row, **asdict(rec), **schema})
        if len(request_ledger) % 10 == 0 or len(request_ledger) == len(tile_rows):
            print(f"marker tiles {len(request_ledger)}/{len(tile_rows)}", flush=True)

    write_csv(out / "normalized" / "KUNIJIBAN_TILE_FETCH_LEDGER.csv", request_ledger)
    marker_rows = [
        {
            "boreholeId": mid,
            "boreholeLatitude": value.get("latitude"),
            "boreholeLongitude": value.get("longitude"),
            "clientClassId": value.get("client_class_id"),
            "approval": value.get("approval"),
        }
        for mid, value in sorted(marker_catalog.items())
    ]
    write_csv(out / "normalized" / "KUNIJIBAN_MARKER_CATALOG.csv", marker_rows)

    target_results: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    nearest_within500: dict[int, dict[str, Any]] = {}
    request_lookup = {(int(r["x"]), int(r["y"])): r for r in request_ledger}

    for target in targets:
        cell_id = target["cellId"]
        lat, lon = float(target["latitude"]), float(target["longitude"])
        loaded_markers: dict[int, dict[str, Any]] = {}
        complete = True
        successful = 0
        for tile in cell_tiles[cell_id]:
            ledger = request_lookup.get(tile)
            if ledger and ledger.get("schemaOk") and ledger.get("sourceSuccess"):
                successful += 1
            else:
                complete = False
            for value in tile_markers.get(tile, []):
                try:
                    loaded_markers[int(value["id"])] = value
                except (KeyError, TypeError, ValueError):
                    continue
        distances: list[tuple[float, int, dict[str, Any]]] = []
        for mid, value in loaded_markers.items():
            try:
                d = haversine_m(lat, lon, float(value["latitude"]), float(value["longitude"]))
            except (KeyError, TypeError, ValueError):
                continue
            distances.append((d, mid, value))
        distances.sort(key=lambda x: (x[0], x[1]))
        within500 = [x for x in distances if x[0] <= SEARCH_RADIUS_M]
        for d, mid, value in within500:
            band = "<=100m" if d <= 100 else "<=300m" if d <= 300 else "<=500m"
            candidate_rows.append({
                "cellId": cell_id,
                "gridIndex": target["gridIndex"],
                "prefecture": target["prefecture"],
                "municipality": target["municipality"],
                "townChome": target["townChome"],
                "cellLatitude": lat,
                "cellLongitude": lon,
                "boreholeId": mid,
                "boreholeLatitude": value.get("latitude"),
                "boreholeLongitude": value.get("longitude"),
                "distanceM": round(d, 3),
                "band": band,
                "clientClassId": value.get("client_class_id"),
                "approval": value.get("approval"),
            })
        nearest = distances[0] if distances else None
        nearest_distance = nearest[0] if nearest else None
        nearest_id = nearest[1] if nearest else None
        status = (
            "candidate_within_100m" if nearest_distance is not None and nearest_distance <= 100 else
            "candidate_within_300m" if nearest_distance is not None and nearest_distance <= 300 else
            "candidate_within_500m" if nearest_distance is not None and nearest_distance <= 500 else
            "no_candidate_within_500m_in_complete_query" if complete else
            "runtime_incomplete"
        )
        result = {
            **target,
            "requestCount": 9,
            "successfulRequestCount": successful,
            "queryComplete": complete,
            "queryState": "complete" if complete else "runtime_incomplete",
            "candidateCount500m": len(within500),
            "hit100m": any(x[0] <= 100 for x in within500),
            "hit300m": any(x[0] <= 300 for x in within500),
            "hit500m": bool(within500),
            "nearestMarkerIdInLoadedCache": nearest_id,
            "nearestDistanceMInLoadedCache": round(nearest_distance, 3) if nearest_distance is not None else None,
            "candidateStatus": status,
        }
        target_results.append(result)
        if nearest is not None and nearest_distance is not None and nearest_distance <= 500:
            entry = nearest_within500.setdefault(nearest_id, {
                "markerId": nearest_id,
                "markerLatitude": nearest[2].get("latitude"),
                "markerLongitude": nearest[2].get("longitude"),
                "clientClassId": nearest[2].get("client_class_id"),
                "approval": nearest[2].get("approval"),
                "targetCountNearestWithin500m": 0,
                "minNearestDistanceM": nearest_distance,
                "nearestCellIds": [],
            })
            entry["targetCountNearestWithin500m"] += 1
            entry["minNearestDistanceM"] = min(entry["minNearestDistanceM"], nearest_distance)
            entry["nearestCellIds"].append(cell_id)

    write_csv(out / "normalized" / "KUNIJIBAN_TARGET_RESULTS.csv", target_results)
    write_csv(out / "normalized" / "KUNIJIBAN_TARGET_CANDIDATES.csv", candidate_rows)

    detail_fetcher = LowRateFetcher(args.detail_delay, args.timeout, args.retries)
    detail_fetch_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    selection = [nearest_within500[k] for k in sorted(nearest_within500)]
    write_csv(out / "normalized" / "KUNIJIBAN_NEAREST_WITHIN500_SELECTION.csv", selection)

    for index, selected in enumerate(selection, start=1):
        marker_id = int(selected["markerId"])
        marker_path = out / "raw" / "marker" / f"{marker_id}.json"
        marker_url = f"{MARKER_URL}?{urllib.parse.urlencode({'id': marker_id})}"
        mrec = detail_fetcher.get("marker_json", marker_url, marker_path)
        detail_fetch_rows.append({"markerId": marker_id, **asdict(mrec)})
        detail: dict[str, Any] = {**selected, "officialMarkerSuccess": False, "markerFetchState": mrec.state}
        marker_data: dict[str, Any] | None = None
        if mrec.state == "fetched":
            try:
                payload = json.loads(marker_path.read_text(encoding="utf-8-sig"))
                values = payload.get("data", {}).get("values")
                if bool(payload.get("header", {}).get("success")) and isinstance(values, dict):
                    marker_data = values
                    detail["officialMarkerSuccess"] = True
                    for key, value in values.items():
                        detail[f"marker_{key}"] = value
            except Exception as exc:  # noqa: BLE001
                detail["markerParseError"] = f"{type(exc).__name__}: {exc}"
        if marker_data is not None:
            boring_advertised = flag_present(marker_data.get("boring_xml_url"))
            soil_advertised = flag_present(marker_data.get("soiltest_xml_url"))
            detail["boringXmlAdvertised"] = boring_advertised
            detail["soiltestXmlAdvertised"] = soil_advertised
            if boring_advertised:
                params = {"data": "boring", "type": "xml", "id": marker_id}
                path = out / "raw" / "boring_xml" / f"{marker_id}.xml"
                rec = detail_fetcher.get("boring_xml", f"{REFER_URL}?{urllib.parse.urlencode(params)}", path)
                detail_fetch_rows.append({"markerId": marker_id, **asdict(rec)})
                detail["boringXmlState"] = rec.state
                detail["boringXmlHttpStatus"] = rec.httpStatus
                if rec.state == "fetched":
                    try:
                        detail.update(parse_boring_xml(path))
                    except Exception as exc:  # noqa: BLE001
                        detail["parsedXml"] = False
                        detail["xmlParseError"] = f"{type(exc).__name__}: {exc}"
            if soil_advertised:
                params = {"data": "soiltest", "type": "xml", "id": marker_id}
                path = out / "raw" / "soiltest_xml" / f"{marker_id}.xml"
                rec = detail_fetcher.get("soiltest_xml", f"{REFER_URL}?{urllib.parse.urlencode(params)}", path)
                detail_fetch_rows.append({"markerId": marker_id, **asdict(rec)})
                detail["soiltestXmlState"] = rec.state
                detail["soiltestXmlHttpStatus"] = rec.httpStatus
        detail_rows.append(detail)
        if index % 50 == 0 or index == len(selection):
            print(f"marker details {index}/{len(selection)}", flush=True)

    write_csv(out / "normalized" / "KUNIJIBAN_NEAREST_DETAIL_LEDGER.csv", detail_rows)
    write_csv(out / "normalized" / "KUNIJIBAN_DETAIL_FETCH_LEDGER.csv", detail_fetch_rows)

    complete_targets = [r for r in target_results if r["queryComplete"]]
    summary = {
        **build_summary,
        "finishedAtUTC": utc_now(),
        "state": "completed" if len(complete_targets) == len(targets) else "partial_runtime_incomplete",
        "successfulTileRequests": sum(bool(r.get("schemaOk") and r.get("sourceSuccess")) for r in request_ledger),
        "runtimeIncompleteTileRequests": sum(not bool(r.get("schemaOk") and r.get("sourceSuccess")) for r in request_ledger),
        "uniqueMarkersFetched": len(marker_catalog),
        "completeTargetCells": len(complete_targets),
        "hit100m": sum(bool(r["hit100m"]) for r in target_results),
        "hit300m": sum(bool(r["hit300m"]) for r in target_results),
        "hit500m": sum(bool(r["hit500m"]) for r in target_results),
        "candidateRelationsWithin500m": len(candidate_rows),
        "uniqueNearestMarkersWithin500m": len(selection),
        "markerDetailsSuccessful": sum(bool(r.get("officialMarkerSuccess")) for r in detail_rows),
        "genuineBoringXmlFetched": sum(r.get("boringXmlState") == "fetched" for r in detail_rows),
        "xmlWithObservedWater": sum(bool(r.get("hasObservedWater")) for r in detail_rows),
        "xmlWithExplicitWaterLevelDate": sum(bool(r.get("hasExplicitWaterLevelDate")) for r in detail_rows),
        "xmlWithSPT": sum(int(r.get("sptRecordCount") or 0) > 0 for r in detail_rows),
        "xmlWithLithology": sum(int(r.get("lithologyRecordCount") or 0) > 0 for r in detail_rows),
        "interpretationGuard": (
            "Acquisition and basic source-native field extraction only. Water-level semantics, reference datum, "
            "aquifer identity, survey epoch, source dependence, model agreement and strict A4 remain separate gates."
        ),
    }
    write_json(out / "RUN_SUMMARY.json", summary)

    muni_rows: list[dict[str, Any]] = []
    by_muni: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in target_results:
        by_muni[row["municipality"]].append(row)
    for municipality, rows in sorted(by_muni.items()):
        muni_rows.append({
            "municipality": municipality,
            "cells": len(rows),
            "complete": sum(bool(r["queryComplete"]) for r in rows),
            "hit100m": sum(bool(r["hit100m"]) for r in rows),
            "hit300m": sum(bool(r["hit300m"]) for r in rows),
            "hit500m": sum(bool(r["hit500m"]) for r in rows),
        })
    write_csv(out / "analysis" / "MUNICIPALITY_SUMMARY.csv", muni_rows)

    sha_lines: list[str] = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            sha_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(out).as_posix()}")
    (out / "SHA256SUMS.txt").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    archive = shutil.make_archive(str(out), "zip", root_dir=out)
    print(json.dumps({"summary": summary, "archive": archive}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
