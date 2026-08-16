#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

CATALOG_URL = "https://api.plateauview.mlit.go.jp/datacatalog/plateau-datasets"
TOKYO_CODES = [f"131{i:02d}" for i in range(1, 24)]
YOKOHAMA_CODES = [f"141{i:02d}" for i in range(1, 19)]
KAWASAKI_CODES = [f"141{i:02d}" for i in range(31, 38)]
TARGET_CODES = TOKYO_CODES + YOKOHAMA_CODES + KAWASAKI_CODES
BUILD_ID = "ecos-practical-v2-20260817-m1-plateau-dataset-discovery-48"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def effective_code(row: dict[str, Any]) -> str:
    ward_code = str(row.get("ward_code") or "")
    city_code = str(row.get("city_code") or "")
    if ward_code in TARGET_CODES:
        return ward_code
    if city_code in TARGET_CODES:
        return city_code
    return ""


def candidate_rank(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
    """Prefer newest, geometry-only, direct URL, then 3D Tiles 1.0 as tie-break."""
    year = int(row.get("year") or 0)
    no_texture = 1 if not bool(row.get("texture")) else 0
    direct_url = 1 if row.get("url") else 0
    format_10 = 1 if str(row.get("format_version") or "") == "1.0" else 0
    return (year, no_texture, direct_url, format_10, str(row.get("id") or ""))


def slim(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "id", "name", "pref", "pref_code", "city", "city_code", "ward",
        "ward_code", "type", "type_en", "url", "composite_url", "year",
        "registration_year", "spec", "format", "format_version", "lod",
        "texture", "interior", "file_size",
    ]
    return {key: row.get(key) for key in keys}


def probe_tileset(session: requests.Session, row: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("url") or row.get("composite_url") or "")
    if not url:
        return {"status": "NO_URL", "url": ""}
    try:
        response = session.get(url, timeout=(20, 120))
        response.raise_for_status()
        payload = response.json()
        root = payload.get("root") or {}
        content = root.get("content") or {}
        return {
            "status": "PASS",
            "url": url,
            "finalUrl": response.url,
            "httpStatus": response.status_code,
            "bytes": len(response.content),
            "sha256": hashlib.sha256(response.content).hexdigest(),
            "assetVersion": (payload.get("asset") or {}).get("version"),
            "extensionsUsed": payload.get("extensionsUsed") or [],
            "extensionsRequired": payload.get("extensionsRequired") or [],
            "rootRefine": root.get("refine"),
            "rootGeometricError": root.get("geometricError"),
            "rootBoundingVolumeKeys": sorted((root.get("boundingVolume") or {}).keys()),
            "rootContentUri": content.get("uri") or content.get("url"),
            "rootHasImplicitTiling": bool(root.get("implicitTiling")),
            "rootChildren": len(root.get("children") or []),
        }
    except Exception as exc:
        return {"status": "ERROR", "url": url, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "ECOSCAPE-PLATEAU-DISCOVERY/2.0"})

    response = session.get(CATALOG_URL, timeout=(30, 240))
    response.raise_for_status()
    payload = response.json()
    raw = canonical_bytes(payload)
    (output / "PLATEAU_DATASET_CATALOG_RAW.json").write_bytes(raw)

    datasets = payload.get("datasets") or []
    candidates_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_row in datasets:
        if not isinstance(raw_row, dict):
            continue
        if raw_row.get("format") != "3D Tiles":
            continue
        if raw_row.get("type_en") != "bldg":
            continue
        if str(raw_row.get("lod") or "") != "1":
            continue
        if raw_row.get("interior") is True:
            continue
        code = effective_code(raw_row)
        if code:
            candidates_by_code[code].append(slim(raw_row))

    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for code in TARGET_CODES:
        rows = sorted(candidates_by_code.get(code, []), key=candidate_rank, reverse=True)
        if not rows:
            missing.append(code)
            continue
        choice = dict(rows[0])
        choice["targetCode"] = code
        choice["candidateCount"] = len(rows)
        choice["allCandidateIds"] = [row.get("id") for row in rows]
        choice["tilesetProbe"] = probe_tileset(session, choice)
        selected.append(choice)

    candidate_rows = []
    for code in TARGET_CODES:
        for row in sorted(candidates_by_code.get(code, []), key=candidate_rank, reverse=True):
            candidate_rows.append({"targetCode": code, **row})

    probe_status = Counter((row.get("tilesetProbe") or {}).get("status") for row in selected)
    selected_years = Counter(str(row.get("year")) for row in selected)
    selected_versions = Counter(str(row.get("format_version")) for row in selected)
    selected_texture = Counter("texture" if row.get("texture") else "notexture" for row in selected)
    selected_asset_versions = Counter(str((row.get("tilesetProbe") or {}).get("assetVersion")) for row in selected)
    implicit_count = sum(1 for row in selected if (row.get("tilesetProbe") or {}).get("rootHasImplicitTiling"))

    audit = {
        "buildId": BUILD_ID,
        "catalogUrl": CATALOG_URL,
        "catalogBytes": len(raw),
        "catalogSha256": hashlib.sha256(raw).hexdigest(),
        "catalogDatasetRows": len(datasets),
        "targetCodes": len(TARGET_CODES),
        "selectedCodes": len(selected),
        "missingCodes": missing,
        "candidateRows": len(candidate_rows),
        "probeStatusCounts": dict(sorted(probe_status.items())),
        "selectedYearCounts": dict(sorted(selected_years.items())),
        "selectedFormatVersionCounts": dict(sorted(selected_versions.items())),
        "selectedTextureCounts": dict(sorted(selected_texture.items())),
        "selectedAssetVersionCounts": dict(sorted(selected_asset_versions.items())),
        "selectedImplicitTilingCount": implicit_count,
        "selectionPolicy": "newest_year_then_notexture_then_direct_url_then_3dtiles_1_0_tiebreak",
        "qaPass": len(selected) == len(TARGET_CODES) and not missing and probe_status.get("ERROR", 0) == 0 and probe_status.get("NO_URL", 0) == 0,
        "scoringEffect": "none",
    }

    (output / "PLATEAU_DATASET_CANDIDATES_48.json").write_text(
        json.dumps(candidate_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "PLATEAU_DATASET_SELECTED_48.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "PLATEAU_DATASET_DISCOVERY_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "README.md").write_text(
        "# ECOSCAPE PLATEAU dataset discovery\n\n"
        "Official PLATEAU Data Catalog rows for the 23 Tokyo wards, 18 Yokohama wards, "
        "and 7 Kawasaki wards. This bundle chooses one default LOD1 building 3D Tiles "
        "dataset per target code but preserves all candidates for decoder fallback. "
        "It is discovery evidence, not the final 120,662-cell geometry product.\n",
        encoding="utf-8",
    )
    names = [
        "PLATEAU_DATASET_CATALOG_RAW.json",
        "PLATEAU_DATASET_CANDIDATES_48.json",
        "PLATEAU_DATASET_SELECTED_48.json",
        "PLATEAU_DATASET_DISCOVERY_AUDIT.json",
        "README.md",
    ]
    lines = []
    for name in names:
        body = (output / name).read_bytes()
        lines.append(f"{hashlib.sha256(body).hexdigest()}  {name}")
    (output / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not audit["qaPass"]:
        raise SystemExit("PLATEAU dataset discovery QA failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
