#!/usr/bin/env python3
"""V10 B46 SPHERE GSI Vector current-building diagnostic v1.

Reads only public GSI experimental_bvmap vector tiles around the current
SPHERE address point. The tile set is documented by GSI as 2026-04-01 data.
This is a diagnostic candidate probe only: no formal geometry promotion and
no score/rank/automatic-exclusion change.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import mapbox_vector_tile
import requests
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform as shp_transform

OUT = Path("out-b46-sphere-gsi-vector-v1")
URL = "https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/{z}/{x}/{y}.pbf"
Z = 16
RADIUS_M = 100.0
TARGET = {
    "propertyId": "BLDG-b1dbdbdf3f3d",
    "buildingName": "SPHERE YOYOGIUEHARA HILLTOP",
    "address": "東京都渋谷区上原2丁目11-20",
    "lon": 139.683747,
    "lat": 35.666282,
    "completion": "2023-04",
    "units": 23,
    "storeysAboveGround": 3,
    "storeysBelowGround": 1,
    "maxFloorPrivateAreaM2": 172.58,
    "representativeTempleDistanceM": 502.228858,
}


def tile_xy(lon: float, lat: float, z: int):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    latr = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(latr)) / math.pi) / 2.0 * n)
    return x, y


def tilecoord_to_lonlat(tx, ty, z, px, py, extent, y_down):
    # Decoder coordinate convention is diagnosed explicitly rather than assumed.
    gx = tx + px / extent
    gy = ty + (py / extent if y_down else (extent - py) / extent)
    n = 2 ** z
    lon = gx / n * 360.0 - 180.0
    a = math.pi * (1.0 - 2.0 * gy / n)
    lat = math.degrees(math.atan(math.sinh(a)))
    return lon, lat


def convert_coords(obj, fn):
    if not obj:
        return obj
    if isinstance(obj[0], (int, float)):
        return fn(obj[0], obj[1])
    return [convert_coords(v, fn) for v in obj]


def candidate_from_feature(layer, feat, tx, ty, extent, y_down, to_local, target_local):
    geom = feat.get("geometry")
    if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    coords = convert_coords(
        geom.get("coordinates"),
        lambda px, py: tilecoord_to_lonlat(tx, ty, Z, px, py, extent, y_down),
    )
    gj = {"type": geom["type"], "coordinates": coords}
    try:
        poly = shape(gj)
        if poly.is_empty or not poly.is_valid:
            return None
        pm = shp_transform(to_local, poly)
    except Exception:
        return None
    d = pm.distance(target_local)
    cd = pm.centroid.distance(target_local)
    if min(d, cd) > RADIUS_M:
        return None
    return {
        "layer": layer,
        "featureId": feat.get("id"),
        "properties": feat.get("properties") or {},
        "distanceFromCurrentPointM": round(d, 3),
        "centroidDistanceM": round(cd, 3),
        "areaM2": round(pm.area, 2),
        "containsCurrentPoint": bool(pm.covers(target_local)),
        "geometry": gj,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "iyashiro-v10-research/1.0"
    cx, cy = tile_xy(TARGET["lon"], TARGET["lat"], Z)
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={TARGET['lat']} +lon_0={TARGET['lon']} +datum=WGS84 +units=m +no_defs"
    )
    to_local = Transformer.from_crs(4326, local, always_xy=True).transform
    target_local = Point(*to_local(TARGET["lon"], TARGET["lat"]))

    tile_meta = []
    decoded_tiles = []
    layer_stats = {}
    for tx in range(cx - 1, cx + 2):
        for ty in range(cy - 1, cy + 2):
            u = URL.format(z=Z, x=tx, y=ty)
            r = session.get(u, timeout=30)
            r.raise_for_status()
            blob = r.content
            sha = hashlib.sha256(blob).hexdigest()
            decoded = mapbox_vector_tile.decode(blob)
            decoded_tiles.append((tx, ty, decoded))
            tile_meta.append({"z": Z, "x": tx, "y": ty, "url": u, "bytes": len(blob), "sha256": sha})
            for lname, layer in decoded.items():
                feats = layer.get("features") or []
                rec = layer_stats.setdefault(lname, {"featureCount": 0, "geometryTypes": {}, "sampleProperties": []})
                rec["featureCount"] += len(feats)
                for f in feats:
                    gt = (f.get("geometry") or {}).get("type")
                    rec["geometryTypes"][gt] = rec["geometryTypes"].get(gt, 0) + 1
                    p = f.get("properties") or {}
                    if p and len(rec["sampleProperties"]) < 10:
                        rec["sampleProperties"].append(p)

    orientation_results = {}
    for y_down in (False, True):
        cands = []
        for tx, ty, decoded in decoded_tiles:
            for lname, layer in decoded.items():
                extent = int(layer.get("extent") or 4096)
                for f in layer.get("features") or []:
                    c = candidate_from_feature(lname, f, tx, ty, extent, y_down, to_local, target_local)
                    if c:
                        cands.append(c)
        # de-dupe tile-edge repeats using geometry + layer/properties hash
        uniq = {}
        for c in cands:
            key = hashlib.sha256(json.dumps([c["layer"], c["properties"], c["geometry"]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            uniq[key] = c
        vals = sorted(uniq.values(), key=lambda x: (x["distanceFromCurrentPointM"], x["centroidDistanceM"]))
        orientation_results[str(y_down).lower()] = vals

    # Correct orientation should yield more realistic near features and a very small minimum distance.
    def score(vals):
        if not vals:
            return (999999.0, 0)
        return (vals[0]["distanceFromCurrentPointM"], -len(vals))
    selected_key = min(orientation_results, key=lambda k: score(orientation_results[k]))
    selected = orientation_results[selected_key]

    likely_building = []
    for c in selected:
        lname = c["layer"].lower()
        p = c["properties"]
        code = p.get("ftCode") or p.get("ftcode")
        # Keep explicit building-ish layers OR common GSI building code family 31xx.
        code_num = None
        try:
            code_num = int(code) if code is not None else None
        except Exception:
            pass
        if "building" in lname or (code_num is not None and 3100 <= code_num < 3200):
            likely_building.append(c)

    summary = {
        "schemaVersion": "v10-b46-sphere-gsi-vector-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "provider": "Geospatial Information Authority of Japan",
            "dataset": "GSI Maps Vector experimental_bvmap",
            "documentedDataAsOf": "2026-04-01",
            "tileTemplate": URL,
            "zoom": Z,
        },
        "target": TARGET,
        "centerTile": {"z": Z, "x": cx, "y": cy},
        "tiles": tile_meta,
        "layerStats": layer_stats,
        "orientationCandidateCounts": {k: len(v) for k, v in orientation_results.items()},
        "selectedYDown": selected_key == "true",
        "nearPolygonCount": len(selected),
        "likelyBuildingPolygonCount": len(likely_building),
        "nearPolygons": selected[:100],
        "likelyBuildingPolygons": likely_building[:100],
        "formalBuildingPolygonsPromoted": 0,
        "verifiedGeometryAdded": 0,
        "policy": {
            "formalPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextGate": "inspect current GSI building candidate against 172.58m2 physical lower bound, current address point, and temporal controls",
        },
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "near-polygons.geojson").write_text(json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{k:v for k,v in c.items() if k!="geometry"},"geometry":c["geometry"]} for c in selected]}, ensure_ascii=False), encoding="utf-8")
    (OUT / "likely-building-polygons.geojson").write_text(json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{k:v for k,v in c.items() if k!="geometry"},"geometry":c["geometry"]} for c in likely_building]}, ensure_ascii=False), encoding="utf-8")
    (OUT / "README.md").write_text("\n".join([
        "# V10 B46 SPHERE GSI Vector diagnostic v1",
        "",
        f"- data as of: 2026-04-01 (GSI documented)",
        f"- center tile: {Z}/{cx}/{cy}",
        f"- layers: {len(layer_stats)}",
        f"- selected y-down: {summary['selectedYDown']}",
        f"- near polygons <= {RADIUS_M:.0f}m: {len(selected)}",
        f"- likely building polygons: {len(likely_building)}",
        "- formal promotion: 0",
        "- score/rank/exclusion change: 0",
        "",
        *[f"- #{i}: layer={c['layer']} d={c['distanceFromCurrentPointM']}m area={c['areaM2']}m2 contains={c['containsCurrentPoint']} props={json.dumps(c['properties'], ensure_ascii=False, sort_keys=True)}" for i,c in enumerate(likely_building[:20],1)]
    ])+"\n", encoding="utf-8")
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums)+"\n", encoding="utf-8")
    print(json.dumps({
        "centerTile": summary["centerTile"],
        "layers": list(layer_stats.keys()),
        "orientationCandidateCounts": summary["orientationCandidateCounts"],
        "selectedYDown": summary["selectedYDown"],
        "nearPolygonCount": len(selected),
        "likelyBuildingPolygonCount": len(likely_building),
        "firstLikelyBuilding": likely_building[0] if likely_building else None,
        "formalPromotion": 0,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
