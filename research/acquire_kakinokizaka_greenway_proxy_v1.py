#!/usr/bin/env python3
"""Acquire a review-only current greenway geometry proxy for the former
Nomikawa Kakinokizaka tributary and intersect it with V10 target cells.

The official Meguro sources establish the historical route and that the present
urban greenway follows the culverted tributary. OSM/Nominatim geometry is used
only as a current-surface trace proxy. It is never promoted as the historical
open-channel centerline without independent historical-map georeferencing.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Polygon, box, mapping, shape
from shapely.ops import transform, unary_union

OUT = Path("out-kakinokizaka-greenway-proxy-v1")
OFFICIAL_ROUTE = "https://www.city.meguro.tokyo.jp/shougaigakushuu/bunkasports/areanavi/nomigawa_kakinokizaka.html"
OFFICIAL_PARK = "https://www.city.meguro.tokyo.jp/dobokukanri/shigoto/kouen/toshikouen.html"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
HEADERS = {"User-Agent": "iyashiro-map-v10-watercourse-proxy/1.0 public research"}

# Canonical V10 fixed-cell centers. Approximate cell dimensions are the same
# fixed ~100m lattice used by the V10 matrix: lat step 0.000898, lon step 0.001104.
CELLS = [
    {"cellId": "g233-217", "town": "東が丘一丁目", "lat": 35.630340, "lon": 139.669621},
    {"cellId": "g239-220", "town": "柿の木坂二丁目", "lat": 35.624952, "lon": 139.672934},
]
LAT_HALF = 0.000898 / 2
LON_HALF = 0.001104 / 2
METRIC = CRS.from_epsg(6677)
WGS84 = CRS.from_epsg(4326)
TO_METRIC = Transformer.from_crs(WGS84, METRIC, always_xy=True).transform


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_json(name: str, obj: Any) -> None:
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def nominatim_probe() -> list[dict[str, Any]]:
    rows = []
    for q in [
        "呑川柿の木坂支流緑道, 目黒区, 東京都",
        "呑川柿の木坂支流緑道, 東が丘, 目黒区",
        "呑川柿の木坂支流緑道, 柿の木坂, 目黒区",
    ]:
        r = requests.get(NOMINATIM, params={"q": q, "format": "jsonv2", "polygon_geojson": 1, "limit": 10}, headers=HEADERS, timeout=60)
        r.raise_for_status()
        data = r.json()
        rows.append({"query": q, "results": data})
        time.sleep(1.1)
    return rows


def overpass_probe() -> dict[str, Any]:
    # Bounding box covers official endpoint corridor: Nakane 1-3 to Higashigaoka 1-35.
    bbox = "35.6200,139.6630,35.6385,139.6810"
    query = f'''[out:json][timeout:120];(
      nwr["name"="呑川柿の木坂支流緑道"]({bbox});
      nwr["name"~"柿の木坂.*支流|呑川.*柿の木坂|柿の木坂.*緑道"]({bbox});
      nwr["name:ja"~"柿の木坂.*支流|呑川.*柿の木坂"]({bbox});
    );out meta tags center geom;'''
    errors = []
    for endpoint in OVERPASS:
        try:
            r = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=150)
            r.raise_for_status()
            payload = r.json()
            return {"endpoint": endpoint, "query": query, "payload": payload}
        except Exception as exc:
            errors.append({"endpoint": endpoint, "error": str(exc)})
    raise RuntimeError(json.dumps(errors, ensure_ascii=False))


def rings_from_element(e: dict[str, Any]) -> list[list[list[float]]]:
    if e.get("type") == "way":
        geom = e.get("geometry") or []
        coords = [[float(p["lon"]), float(p["lat"])] for p in geom if "lon" in p and "lat" in p]
        return [coords] if len(coords) >= 2 else []
    rings = []
    for m in e.get("members") or []:
        geom = m.get("geometry") or []
        coords = [[float(p["lon"]), float(p["lat"])] for p in geom if "lon" in p and "lat" in p]
        if len(coords) >= 2:
            rings.append(coords)
    return rings


def geometry_from_osm(e: dict[str, Any]):
    pieces = []
    for coords in rings_from_element(e):
        if len(coords) >= 4 and coords[0] == coords[-1]:
            try:
                pieces.append(Polygon(coords))
                continue
            except Exception:
                pass
        pieces.append(LineString(coords))
    return unary_union(pieces) if pieces else None


def geometry_candidates(nominatim_rows: list[dict[str, Any]], overpass: dict[str, Any]):
    candidates = []
    seen = set()
    for block in nominatim_rows:
        for row in block["results"]:
            gj = row.get("geojson")
            if not gj:
                continue
            ref = f"{row.get('osm_type')}/{row.get('osm_id')}"
            if ref in seen:
                continue
            try:
                geom = shape(gj)
            except Exception:
                continue
            if geom.is_empty:
                continue
            seen.add(ref)
            candidates.append({"ref": ref, "source": "Nominatim", "displayName": row.get("display_name"), "tags": {"type": row.get("type"), "class": row.get("class")}, "geom": geom})
    for e in overpass["payload"].get("elements") or []:
        ref = f"{e.get('type')}/{e.get('id')}"
        geom = geometry_from_osm(e)
        if not geom or geom.is_empty:
            continue
        tags = e.get("tags") or {}
        # Prefer the richer Overpass record when the same OSM object is present.
        candidates = [x for x in candidates if x["ref"] != ref]
        candidates.append({"ref": ref, "source": "Overpass", "displayName": tags.get("name") or tags.get("name:ja"), "tags": tags, "geom": geom})
    return candidates


def target_cells():
    out = []
    for c in CELLS:
        poly = box(c["lon"] - LON_HALF, c["lat"] - LAT_HALF, c["lon"] + LON_HALF, c["lat"] + LAT_HALF)
        out.append({**c, "geometry": poly})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    nom = nominatim_probe()
    ov = overpass_probe()
    save_json("nominatim-probe.json", nom)
    save_json("overpass-probe.json", ov)
    candidates = geometry_candidates(nom, ov)
    cells = target_cells()
    qa = []
    features = []

    for cand in candidates:
        geom = cand["geom"]
        gm = transform(TO_METRIC, geom)
        cell_rows = []
        for c in cells:
            cm = transform(TO_METRIC, c["geometry"])
            center_m = transform(TO_METRIC, shape({"type": "Point", "coordinates": [c["lon"], c["lat"]]}))
            distance_to_cell = gm.distance(cm)
            distance_to_center = gm.distance(center_m)
            inter = gm.intersection(cm)
            cell_rows.append({
                "cellId": c["cellId"],
                "town": c["town"],
                "intersectsCell": not inter.is_empty,
                "intersectionLengthM": round(getattr(inter, "length", 0.0), 3),
                "intersectionAreaSqm": round(getattr(inter, "area", 0.0), 3),
                "distanceToCellM": round(distance_to_cell, 3),
                "distanceToCellCenterM": round(distance_to_center, 3),
            })
        score = sum(1 for x in cell_rows if x["intersectsCell"])
        qa.append({
            "osmRef": cand["ref"],
            "source": cand["source"],
            "displayName": cand["displayName"],
            "tags": cand["tags"],
            "geometryType": geom.geom_type,
            "bounds": [round(x, 7) for x in geom.bounds],
            "targetCellIntersectionCount": score,
            "cells": cell_rows,
            "promotionStatus": "current_greenway_proxy_review_only",
            "historicalGeometryVerified": False,
            "scoringEffect": "none",
        })
        features.append({
            "type": "Feature",
            "properties": {
                "osmRef": cand["ref"],
                "source": cand["source"],
                "displayName": cand["displayName"],
                "targetCellIntersectionCount": score,
                "role": "current_greenway_surface_proxy_not_historical_centerline",
                "scoringEffect": "none",
            },
            "geometry": mapping(geom),
        })

    qa.sort(key=lambda x: (-x["targetCellIntersectionCount"], min((c["distanceToCellM"] for c in x["cells"]), default=999999)))
    selected = qa[0] if qa else None
    summary = {
        "version": "v10-kakinokizaka-greenway-proxy-v1-20260815",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "officialEvidence": {
            "routeSource": OFFICIAL_ROUTE,
            "routeFact": "former tributary entered Meguro at Higashigaoka 1-35, passed Kakinokizaka 3/2/1 and joined Nomikawa at Nakane 1-3; culverted from 1972 and greenway completed by 1980",
            "parkSource": OFFICIAL_PARK,
            "parkFact": "urban greenway officially listed from Nakane 1-3 to Higashigaoka 1-35",
        },
        "candidateCount": len(qa),
        "selectedReviewProxy": selected,
        "allCandidates": qa,
        "targetCells": [{k: v for k, v in c.items() if k != "geometry"} for c in cells],
        "policy": {
            "currentGreenwayProxyAllowed": True,
            "historicalCenterlineVerified": False,
            "formalHistoricalGeometryPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextGate": "independent pre-culvert historical map centerline georeference and proxy-vs-history residual QA",
        },
    }
    save_json("SUMMARY.json", summary)
    save_json("greenway-proxy-candidates.geojson", {"type": "FeatureCollection", "features": features})
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{sha(p)}  {p.name}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
