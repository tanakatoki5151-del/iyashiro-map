#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

URL = "https://catalog.opendata.pref.kanagawa.jp/dataset/e8b3a9c0-38ac-4632-ace6-61334abe0cbe/resource/1f94e194-1764-46db-baf9-e8b017ae458d/download/02_.zip"
OUT = Path("output")
DL = OUT / "downloads"
EXT = OUT / "extracted" / "kanagawa_2025_liquefaction"
GJ = OUT / "geojson"
for p in (DL, EXT, GJ):
    p.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    zip_path = DL / "kanagawa_2025_liquefaction_distribution.zip"
    with requests.get(URL, stream=True, timeout=(30, 300), allow_redirects=True, headers={"User-Agent": "IyashirochiOfficialClosure/2026-08-22"}) as r:
        r.raise_for_status()
        with zip_path.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    if not zip_path.read_bytes()[:4].startswith(b"PK"):
        raise RuntimeError("Downloaded payload is not ZIP")
    if EXT.exists():
        shutil.rmtree(EXT)
    EXT.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(EXT)
        members = z.namelist()
    results = []
    for shp in sorted(EXT.rglob("*.shp")):
        last = None
        gdf = None
        enc_used = None
        for enc in ("cp932", "shift_jis", "utf-8", None):
            try:
                kwargs = {} if enc is None else {"encoding": enc}
                gdf = gpd.read_file(shp, **kwargs)
                enc_used = enc or "default"
                break
            except Exception as exc:
                last = exc
        if gdf is None:
            results.append({"shp": str(shp.relative_to(EXT)), "status": "FAILED", "error": repr(last)})
            continue
        src_crs = str(gdf.crs) if gdf.crs else None
        if gdf.crs:
            gdf = gdf.to_crs(4326)
        out_name = "kanagawa_2025_liquefaction__" + "_".join(shp.relative_to(EXT).with_suffix("").parts) + ".geojson"
        out_path = GJ / out_name
        gdf.to_file(out_path, driver="GeoJSON", encoding="utf-8")
        results.append({
            "shp": str(shp.relative_to(EXT)),
            "status": "SUCCESS",
            "features": int(len(gdf)),
            "source_crs": src_crs,
            "output_crs": "EPSG:4326" if src_crs else None,
            "encoding": enc_used,
            "columns": [c for c in gdf.columns if c != "geometry"],
            "geometry_types": sorted(set(gdf.geom_type.astype(str))),
            "geojson": str(out_path),
            "geojson_sha256": sha256(out_path),
        })
    report = {
        "schema": "KANAGAWA_2025_LIQUEFACTION_HARVEST_v1",
        "official_source_url": URL,
        "license": "CC-BY",
        "source_release": "2025-03-28",
        "zip_path": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "zip_sha256": sha256(zip_path),
        "zip_members": members,
        "layers": results,
        "source_project_writes": 0,
        "ranking_effect": 0,
    }
    (OUT / "KANAGAWA_2025_LIQUEFACTION_STATUS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
