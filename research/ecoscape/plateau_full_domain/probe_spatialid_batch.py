#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import requests

API_URL = "https://api.plateauview.mlit.go.jp/citygml/spatialid_attributes"
BUILD_ID = "ecos-practical-v2-20260817-b96-plateau-spatialid-batch"
ZOOM = 18
CENTER_LAT = 35.6689
CENTER_LON = 139.6807
BATCH_SIZES = [1, 4, 16, 32, 64]


def lonlat_to_xyz(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(max(-85.05112878, min(85.05112878, lat)))
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def spiral_tiles(cx: int, cy: int, count: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    radius = 0
    while len(out) < count:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                out.append((cx + dx, cy + dy))
                if len(out) >= count:
                    return out
        radius += 1
    return out


def run_batch(session: requests.Session, size: int, cx: int, cy: int) -> dict[str, Any]:
    sids = [f"{ZOOM}/{x}/{y}" for x, y in spiral_tiles(cx, cy, size)]
    started = time.perf_counter()
    try:
        response = session.get(
            API_URL,
            params={"sid": ",".join(sids), "type": "bldg", "skip_code_list_fetch": "true"},
            timeout=(20, 240),
        )
        elapsed = time.perf_counter() - started
        body = response.content
        try:
            payload = response.json()
        except Exception:
            payload = None
        ids = []
        if isinstance(payload, list):
            ids = [str(row.get("gml:id")) for row in payload if isinstance(row, dict) and row.get("gml:id")]
        return {
            "requestedSidCount": size,
            "httpStatus": response.status_code,
            "elapsedSeconds": elapsed,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "jsonType": type(payload).__name__ if payload is not None else None,
            "recordCount": len(payload) if isinstance(payload, list) else None,
            "uniqueBuildingIds": len(set(ids)),
            "duplicateBuildingRows": len(ids) - len(set(ids)),
            "requestUrlLength": len(response.url),
            "bodyPreview": body[:500].decode("utf-8", "replace"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "requestedSidCount": size,
            "elapsedSeconds": time.perf_counter() - started,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    cx, cy = lonlat_to_xyz(CENTER_LON, CENTER_LAT, ZOOM)
    session = requests.Session()
    session.headers.update({"User-Agent": "ECOSCAPE-PLATEAU-SPATIALID-BATCH-PROBE/1.0"})

    rows = [run_batch(session, size, cx, cy) for size in BATCH_SIZES]
    passing = [row for row in rows if row.get("httpStatus") == 200 and isinstance(row.get("recordCount"), int)]
    max_passing = max((row["requestedSidCount"] for row in passing), default=0)
    audit = {
        "buildId": BUILD_ID,
        "zoom": ZOOM,
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON, "x": cx, "y": cy},
        "batchSizes": BATCH_SIZES,
        "maxPassingBatchSize": max_passing,
        "results": rows,
        "recommendedInitialBatchSize": min(32, max_passing) if max_passing else 1,
        "qaPass": max_passing >= 4,
        "scoringEffect": "none",
    }
    (output / "PLATEAU_SPATIALID_BATCH_PROBE_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    body = (output / "PLATEAU_SPATIALID_BATCH_PROBE_AUDIT.json").read_bytes()
    (output / "SHA256SUMS.txt").write_text(
        f"{hashlib.sha256(body).hexdigest()}  PLATEAU_SPATIALID_BATCH_PROBE_AUDIT.json\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not audit["qaPass"]:
        raise SystemExit("Spatial ID batch probe did not support at least four SIDs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
