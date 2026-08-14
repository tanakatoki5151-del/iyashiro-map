#!/usr/bin/env python3
"""V10 B46 A2 Park Mansion cross-source geometry probe v1.

Target: Park Mansion, Tokyo Meguro-ku Higashigaoka 2-13-11.
Known public identity controls: completed 1968-12, RC, 3 floors above ground.

This probe does NOT promote formal geometry or alter score/rank/exclusion.
It only aligns exact-address GSI anchor, latest PLATEAU CityGML, current GSI
Vector building polygons, and the pre-existing OSM candidate way/688654246.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import mapbox_vector_tile
import requests
from lxml import etree
from pyproj import CRS, Transformer
from shapely.geometry import Point, Polygon, shape, mapping
from shapely.ops import transform as shp_transform

import probe_b46_sphere_plateau_v1 as plateau_utils
import probe_b46_sphere_gsi_vector_v1 as gsi_utils

OUT = Path("out-b46-a2-park-mansion-crosssource-v1")
GSI_ADDR = "https://msearch.gsi.go.jp/address-search/AddressSearch"
GSI_TILE = "https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/{z}/{x}/{y}.pbf"
PLATEAU_ATTR = "https://api.plateauview.mlit.go.jp/citygml/attributes"
OSM_FULL = "https://api.openstreetmap.org/api/0.6/way/688654246/full"
Z = 16
RADIUS_M = 80.0
TARGET = {
    "propertyId": "BLDG-8bafd187bc1e",
    "buildingName": "パークマンション",
    "address": "東京都目黒区東が丘2丁目13-11",
    "expectedStoreys": 3,
    "expectedStructure": "RC",
    "built": "1968-12",
    "osmCandidateWayId": 688654246,
    "representativeSensitiveDistanceM": 508.9,
    "thresholdM": 500.0,
}


def gsi_anchor(session):
    r = session.get(GSI_ADDR, params={"q": TARGET["address"]}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise RuntimeError("GSI address search returned no result")
    f = data[0]
    lon, lat = f["geometry"]["coordinates"][:2]
    return {"queryUrl": r.url, "title": f.get("properties", {}).get("title"), "lon": float(lon), "lat": float(lat)}


def local_transformer(lon, lat):
    crs = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs")
    return Transformer.from_crs(4326, crs, always_xy=True)


def parse_plateau(blob, anchor):
    root = etree.fromstring(blob)
    tr = local_transformer(anchor["lon"], anchor["lat"])
    am = Point(*tr.transform(anchor["lon"], anchor["lat"]))
    rows = []
    for b in root.iter():
        if plateau_utils.lname(b.tag) != "Building":
            continue
        geom, geom_meta = plateau_utils.extract_complete_lod0(b)
        if geom is None:
            continue
        gm = shp_transform(tr.transform, geom)
        d = gm.distance(am)
        cd = gm.centroid.distance(am)
        if min(d, cd) > RADIUS_M:
            continue
        gid = next((v for k, v in b.attrib.items() if plateau_utils.lname(k) == "id"), None)
        storeys = plateau_utils.first_text(b, {"storeysAboveGround"})
        try:
            storeys_i = int(storeys) if storeys is not None else None
        except ValueError:
            storeys_i = None
        rows.append({
            "gmlId": gid,
            "buildingID": plateau_utils.all_text(b, {"buildingID", "buildingIDAttribute"})[:5],
            "name": plateau_utils.all_text(b, {"name"})[:5],
            "storeysAboveGround": storeys_i,
            "yearOfConstruction": plateau_utils.first_text(b, {"yearOfConstruction"}),
            "measuredHeight": plateau_utils.first_text(b, {"measuredHeight"}),
            "distanceFromGsiM": round(d, 3),
            "centroidDistanceFromGsiM": round(cd, 3),
            "areaM2": round(gm.area, 2),
            "containsGsi": bool(gm.covers(am)),
            "storeysMatch": storeys_i == TARGET["expectedStoreys"],
            "geometryMeta": geom_meta,
            "geometry": mapping(geom),
        })
    rows.sort(key=lambda r: (r["distanceFromGsiM"], not r["storeysMatch"], r["centroidDistanceFromGsiM"]))
    return rows


def parse_osm_way(blob, anchor):
    root = etree.fromstring(blob)
    nodes = {int(n.get("id")): (float(n.get("lon")), float(n.get("lat"))) for n in root.findall("node")}
    ways = [w for w in root.findall("way") if int(w.get("id")) == TARGET["osmCandidateWayId"]]
    if len(ways) != 1:
        raise RuntimeError(f"OSM candidate way count={len(ways)}")
    w = ways[0]
    refs = [int(nd.get("ref")) for nd in w.findall("nd")]
    coords = [nodes[r] for r in refs if r in nodes]
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
    tr = local_transformer(anchor["lon"], anchor["lat"])
    pm = shp_transform(tr.transform, poly)
    am = Point(*tr.transform(anchor["lon"], anchor["lat"]))
    return {
        "wayId": TARGET["osmCandidateWayId"],
        "version": int(w.get("version")),
        "timestamp": w.get("timestamp"),
        "changeset": w.get("changeset"),
        "user": w.get("user"),
        "tags": tags,
        "areaM2": round(pm.area, 2),
        "distanceFromGsiM": round(pm.distance(am), 3),
        "centroidDistanceFromGsiM": round(pm.centroid.distance(am), 3),
        "containsGsi": bool(pm.covers(am)),
        "geometry": mapping(poly),
    }


def decode_gsi(session, anchor):
    cx, cy = gsi_utils.tile_xy(anchor["lon"], anchor["lat"], Z)
    tr = local_transformer(anchor["lon"], anchor["lat"])
    am = Point(*tr.transform(anchor["lon"], anchor["lat"]))
    tiles = []
    decoded_tiles = []
    for tx in range(cx - 1, cx + 2):
        for ty in range(cy - 1, cy + 2):
            url = GSI_TILE.format(z=Z, x=tx, y=ty)
            r = session.get(url, timeout=30)
            r.raise_for_status()
            blob = r.content
            tiles.append({"z": Z, "x": tx, "y": ty, "url": url, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()})
            decoded_tiles.append((tx, ty, mapbox_vector_tile.decode(blob)))
    orientation = {}
    for y_down in (False, True):
        vals = []
        for tx, ty, decoded in decoded_tiles:
            for lname, layer in decoded.items():
                extent = int(layer.get("extent") or 4096)
                for f in layer.get("features") or []:
                    c = gsi_utils.candidate_from_feature(lname, f, tx, ty, extent, y_down, tr.transform, am)
                    if c:
                        vals.append(c)
        uniq = {}
        for c in vals:
            key = hashlib.sha256(json.dumps([c["layer"], c["properties"], c["geometry"]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            uniq[key] = c
        orientation[y_down] = sorted(uniq.values(), key=lambda c: (c["distanceFromCurrentPointM"], c["centroidDistanceM"]))
    selected_y = min(orientation, key=lambda k: (orientation[k][0]["distanceFromCurrentPointM"] if orientation[k] else 999999, -len(orientation[k])))
    buildings = []
    for c in orientation[selected_y]:
        p = c["properties"]
        raw = p.get("ftCode") if "ftCode" in p else p.get("ftcode")
        try:
            code = int(raw) if raw is not None else None
        except Exception:
            code = None
        if "building" in c["layer"].lower() or (code is not None and 3100 <= code < 3200):
            c = dict(c)
            c["ftCode"] = code
            buildings.append(c)
    return {"centerTile": {"z": Z, "x": cx, "y": cy}, "tiles": tiles, "selectedYDown": selected_y, "buildings": buildings[:100]}


def overlap_metrics(a, b, tr):
    am = shp_transform(tr.transform, shape(a))
    bm = shp_transform(tr.transform, shape(b))
    inter = am.intersection(bm).area
    union = am.union(bm).area
    return {
        "intersectionM2": round(inter, 4),
        "iou": round(inter / union, 6) if union else 0,
        "coverageA": round(inter / am.area, 6) if am.area else 0,
        "coverageB": round(inter / bm.area, 6) if bm.area else 0,
        "centroidDistanceM": round(am.centroid.distance(bm.centroid), 4),
    }


def fetch_plateau_attrs(session, source_url, ids):
    if not ids:
        return {"status": "none", "records": []}
    try:
        r = session.get(PLATEAU_ATTR, params={"url": source_url, "id": ",".join(ids)}, timeout=120)
        r.raise_for_status()
        return {"status": "success", "requestUrl": r.url, "records": r.json()}
    except Exception as e:
        return {"status": "failed_non_blocking", "error": f"{type(e).__name__}: {e}", "records": []}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "iyashiro-v10-research/1.0"
    anchor = gsi_anchor(s)
    query_url, files, catalog = plateau_utils.citygml_files_for_point(s, anchor["lon"], anchor["lat"])
    plateau = []
    source_files = []
    for row in files:
        r = s.get(row["url"], timeout=90)
        r.raise_for_status()
        blob = r.content
        source_files.append({**row, "downloadedBytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()})
        plateau.extend(parse_plateau(blob, anchor))
    # de-dupe CityGML building ids/geometries
    pu = {}
    for c in plateau:
        k = (c.get("gmlId"), json.dumps(c["geometry"], sort_keys=True))
        pu[k] = c
    plateau = sorted(pu.values(), key=lambda r: (r["distanceFromGsiM"], not r["storeysMatch"], r["centroidDistanceFromGsiM"]))
    osm_r = s.get(OSM_FULL, timeout=30)
    osm_r.raise_for_status()
    osm = parse_osm_way(osm_r.content, anchor)
    gsi = decode_gsi(s, anchor)
    tr = local_transformer(anchor["lon"], anchor["lat"])

    for c in plateau:
        c["vsOsm"] = overlap_metrics(c["geometry"], osm["geometry"], tr)
        overlaps = []
        for g in gsi["buildings"]:
            m = overlap_metrics(c["geometry"], g["geometry"], tr)
            if m["intersectionM2"] > 0:
                overlaps.append({"featureId": g.get("featureId"), "ftCode": g.get("ftCode"), "areaM2": g.get("areaM2"), "distanceFromGsiM": g.get("distanceFromCurrentPointM"), **m})
        overlaps.sort(key=lambda x: (-x["intersectionM2"], -x["coverageA"]))
        c["bestGsiOverlap"] = overlaps[0] if overlaps else None
    for g in gsi["buildings"]:
        g["vsOsm"] = overlap_metrics(g["geometry"], osm["geometry"], tr)

    attr_ids = [c["gmlId"] for c in plateau[:20] if c.get("gmlId")]
    source_url = source_files[0]["url"] if source_files else None
    attrs = fetch_plateau_attrs(s, source_url, attr_ids) if source_url else {"status": "no_source", "records": []}

    rank = sorted(
        plateau,
        key=lambda c: (
            not c["storeysMatch"],
            -c["vsOsm"]["iou"],
            -(c["bestGsiOverlap"] or {}).get("iou", 0),
            c["distanceFromGsiM"],
        ),
    )
    summary = {
        "schemaVersion": "v10-b46-a2-park-mansion-crosssource-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "gsiAnchor": anchor,
        "catalogQueryUrl": query_url,
        "sourceFiles": source_files,
        "osmCandidate": osm,
        "gsi": gsi,
        "plateauCandidateCount": len(plateau),
        "plateauCandidates": plateau,
        "rankedPlateauCandidates": [{k:v for k,v in c.items() if k != "geometry"} for c in rank[:20]],
        "plateauAttributeApi": attrs,
        "formalBuildingPolygonsPromoted": 0,
        "verifiedGeometryAdded": 0,
        "policy": {
            "formalPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nearestFallback": False,
            "nextGate": "identify one building only if exact-address + RC/3F controls and independent shape overlaps are coherent; then calculate fixed-sensitive-geometry threshold",
        },
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    feats = []
    for i,c in enumerate(plateau):
        feats.append({"type":"Feature","properties":{"rank":i+1,"gmlId":c.get("gmlId"),"buildingID":c.get("buildingID"),"storeys":c.get("storeysAboveGround"),"distanceFromGsiM":c.get("distanceFromGsiM"),"areaM2":c.get("areaM2"),"osmIou":c["vsOsm"]["iou"],"gsiBestIou":(c.get("bestGsiOverlap") or {}).get("iou")},"geometry":c["geometry"]})
    (OUT / "plateau-candidates.geojson").write_text(json.dumps({"type":"FeatureCollection","features":feats},ensure_ascii=False),encoding="utf-8")
    (OUT / "README.md").write_text("\n".join([
        "# V10 B46 A2 Park Mansion cross-source probe v1", "",
        f"- GSI anchor: {anchor['lat']}, {anchor['lon']} ({anchor['title']})",
        f"- OSM way/{TARGET['osmCandidateWayId']}: d={osm['distanceFromGsiM']}m area={osm['areaM2']}m² version={osm['version']} timestamp={osm['timestamp']} tags={json.dumps(osm['tags'],ensure_ascii=False,sort_keys=True)}",
        f"- PLATEAU candidates within {RADIUS_M:.0f}m: {len(plateau)}",
        f"- GSI current building candidates: {len(gsi['buildings'])}",
        "- formal promotion: 0", "- score/rank/automatic exclusion changes: 0", "",
        *[f"- #{i}: d={c['distanceFromGsiM']}m area={c['areaM2']}m² floors={c['storeysAboveGround']} id={c['buildingID']} osmIoU={c['vsOsm']['iou']} bestGsi={json.dumps(c.get('bestGsiOverlap'),ensure_ascii=False,sort_keys=True)}" for i,c in enumerate(rank[:20],1)]
    ])+"\n",encoding="utf-8")
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums)+"\n",encoding="utf-8")
    print(json.dumps({"anchor":anchor,"osm":{k:v for k,v in osm.items() if k!="geometry"},"plateauCount":len(plateau),"gsiBuildingCount":len(gsi['buildings']),"topRanked":summary['rankedPlateauCandidates'][:5],"attrApi":attrs['status'],"formalPromotion":0},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
