#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import requests

API_ROOT = "https://api.plateauview.mlit.go.jp"
BUILD_ID = "ecos-practical-v2-20260817-b95-plateau-spatialid-probe"
ZOOM = 18
VERTICAL_INDEX = 1

POINTS = [
    {"name": "tokyo_chiyoda", "lat": 35.69681638519583, "lon": 139.78225422575503},
    {"name": "tokyo_uehara", "lat": 35.6689, "lon": 139.6807},
    {"name": "yokohama_aoba", "lat": 35.5580, "lon": 139.5350},
    {"name": "kawasaki_nakahara", "lat": 35.5795, "lon": 139.6555},
]

TYPE_VARIANTS = ["bldg:Building", "Building", "bldg"]
SID_FORMATS = [
    lambda z, f, x, y: f"{z}/{f}/{x}/{y}",
    lambda z, f, x, y: f"/{z}/{f}/{x}/{y}",
    lambda z, f, x, y: f"{z}/{x}/{y}",
    lambda z, f, x, y: f"/{z}/{x}/{y}",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def lonlat_to_xyz(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(max(-85.05112878, min(85.05112878, lat)))
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def request_json(session: requests.Session, path: str, params: dict[str, str]) -> dict[str, Any]:
    url = API_ROOT + path
    try:
        response = session.get(url, params=params, timeout=(20, 120))
        body = response.content
        parsed: Any = None
        parse_error = None
        try:
            parsed = response.json()
        except Exception as exc:  # noqa: BLE001
            parse_error = f"{type(exc).__name__}: {exc}"
        count = None
        if isinstance(parsed, list):
            count = len(parsed)
        elif isinstance(parsed, dict):
            if isinstance(parsed.get("featureIds"), list):
                count = len(parsed["featureIds"])
            elif isinstance(parsed.get("features"), list):
                count = len(parsed["features"])
        return {
            "requestUrl": response.url,
            "httpStatus": response.status_code,
            "contentType": response.headers.get("Content-Type"),
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "jsonType": type(parsed).__name__ if parsed is not None else None,
            "recordCount": count,
            "parseError": parse_error,
            "bodyPreview": body[:1200].decode("utf-8", "replace"),
            "parsedSample": parsed[:2] if isinstance(parsed, list) else parsed,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "requestUrl": url,
            "httpStatus": None,
            "error": f"{type(exc).__name__}: {exc}",
            "recordCount": None,
        }


def main() -> int:
    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "ECOSCAPE-PLATEAU-SPATIALID-PROBE/1.0"})

    attempts: list[dict[str, Any]] = []
    for point in POINTS:
        x, y = lonlat_to_xyz(point["lon"], point["lat"], ZOOM)
        for sid_index, sid_builder in enumerate(SID_FORMATS, start=1):
            sid = sid_builder(ZOOM, VERTICAL_INDEX, x, y)
            feature_response = request_json(session, "/citygml/features", {"sid": sid})
            attempts.append(
                {
                    **point,
                    "z": ZOOM,
                    "f": VERTICAL_INDEX,
                    "x": x,
                    "y": y,
                    "sidVariant": sid_index,
                    "sid": sid,
                    "endpoint": "/citygml/features",
                    "typeVariant": None,
                    "response": feature_response,
                }
            )
            for type_name in TYPE_VARIANTS:
                attr_response = request_json(
                    session,
                    "/citygml/spatialid_attributes",
                    {"sid": sid, "type": type_name, "skip_code_list_fetch": "true"},
                )
                attempts.append(
                    {
                        **point,
                        "z": ZOOM,
                        "f": VERTICAL_INDEX,
                        "x": x,
                        "y": y,
                        "sidVariant": sid_index,
                        "sid": sid,
                        "endpoint": "/citygml/spatialid_attributes",
                        "typeVariant": type_name,
                        "response": attr_response,
                    }
                )

    successful = [
        row
        for row in attempts
        if row["response"].get("httpStatus") == 200
        and isinstance(row["response"].get("recordCount"), int)
        and row["response"]["recordCount"] > 0
    ]
    attribute_success = [
        row for row in successful if row["endpoint"] == "/citygml/spatialid_attributes"
    ]
    feature_success = [row for row in successful if row["endpoint"] == "/citygml/features"]

    best = None
    if attribute_success:
        best = max(attribute_success, key=lambda row: row["response"]["recordCount"])
    elif feature_success:
        best = max(feature_success, key=lambda row: row["response"]["recordCount"])

    audit = {
        "buildId": BUILD_ID,
        "zoom": ZOOM,
        "verticalIndex": VERTICAL_INDEX,
        "points": len(POINTS),
        "attempts": len(attempts),
        "http200": sum(1 for row in attempts if row["response"].get("httpStatus") == 200),
        "positiveResponses": len(successful),
        "positiveAttributeResponses": len(attribute_success),
        "positiveFeatureResponses": len(feature_success),
        "bestCombination": {
            "point": best["name"],
            "sid": best["sid"],
            "endpoint": best["endpoint"],
            "typeVariant": best["typeVariant"],
            "recordCount": best["response"]["recordCount"],
        }
        if best
        else None,
        "qaPass": bool(best),
        "purpose": "Test whether the official PLATEAU Spatial ID API can replace an 18.6 GB full 3D tile download for practical Level B urban-form facts.",
        "scoringEffect": "none",
    }

    (output / "PLATEAU_SPATIALID_PROBE_ATTEMPTS.json").write_text(
        json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "PLATEAU_SPATIALID_PROBE_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "README.md").write_text(
        "# PLATEAU Spatial ID API probe\n\n"
        "Tests official `/citygml/features` and `/citygml/spatialid_attributes` endpoints "
        "against multiple documented Spatial ID spellings and building type names. "
        "This is an access and schema probe only; it does not change ECOSCAPE scoring.\n",
        encoding="utf-8",
    )
    names = [
        "PLATEAU_SPATIALID_PROBE_ATTEMPTS.json",
        "PLATEAU_SPATIALID_PROBE_AUDIT.json",
        "README.md",
    ]
    sums = []
    for name in names:
        body = (output / name).read_bytes()
        sums.append(f"{hashlib.sha256(body).hexdigest()}  {name}")
    (output / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")

    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not audit["qaPass"]:
        raise SystemExit("PLATEAU Spatial ID API probe found no usable positive response")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
