#!/usr/bin/env python3
"""V10 B46 SPHERE YOYOGIUEHARA HILLTOP PLATEAU candidate probe v2.

Fail-closed research probe for one threshold-sensitive property.
No formal Building Polygon promotion and no score/rank/exclusion change.

v2 fixes a geometry bug in v1: CityGML lod0FootPrint/lod0RoofEdge are
MultiSurface geometries. v1 returned the first valid posList only, which can
truncate a multipart footprint. v2 parses every gml:Polygon in the preferred
LOD0 container, preserves interior rings, and unions the polygon members.

Sources:
- MLIT PLATEAU delivery API: coordinate query, latest returned CityGML, bldg only
- GSI residence-display address search: authoritative address anchor
- Frozen V10 property facts: current building is SPHERE YOYOGIUEHARA HILLTOP,
  Tokyo Shibuya-ku Uehara 2-11-20, completed 2023-04, RC, 23 units, 3F/B1.
- Developer project page/image: independent physical-size control only.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from lxml import etree
from pyproj import CRS, Transformer
from shapely.geometry import GeometryCollection, Point, Polygon, mapping
from shapely.ops import transform as shp_transform, unary_union

API = "https://api.plateauview.mlit.go.jp"
GSI = "https://msearch.gsi.go.jp/address-search/AddressSearch"
OUT = Path("out-b46-sphere-plateau-v1")
RADIUS_M = 90.0

TARGET = {
    "propertyId": "BLDG-b1dbdbdf3f3d",
    "buildingName": "SPHERE YOYOGIUEHARA HILLTOP",
    "address": "東京都渋谷区上原2丁目11-20",
    "lat": 35.66623235,
    "lon": 139.6837241,
    "expectedStoreys": 3,
    "expectedYear": 2023,
    "expectedUnits": 23,
    "thresholdM": 500.0,
    "representativeDistanceM": 502.2,
    "identitySources": [
        "https://www.kencorp.co.jp/housing/properties/212583/",
        "https://rent.tokyu-housing-lease.co.jp/rent/8033991",
    ],
    "developerPhysicalControl": {
        "pageUrl": "https://omiex.co.jp/sphere/index.html",
        "imageUrl": "https://omiex.co.jp/sphere/images/series04.jpg",
        "siteAreaM2": 292.71,
        "buildingAreaM2": 204.50,
        "totalFloorAreaM2": 799.65,
        "structure": "WRC",
        "storeys": "B1/3F",
        "role": "independent_physical_size_control_not_geometry_source",
    },
    "staleOsmWayId": 134410229,
    "staleOsmReason": "way v1=2011, source Bing 2007-04; current building completed 2023-04",
}


def lname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def first_text(elem, names):
    for x in elem.iter():
        if lname(x.tag) in names and x.text and x.text.strip():
            return " ".join(x.text.split())
    return None


def all_text(elem, names):
    out = []
    for x in elem.iter():
        if lname(x.tag) in names and x.text and x.text.strip():
            v = " ".join(x.text.split())
            if v not in out:
                out.append(v)
    return out


def epsg_from_srs(srs):
    if not srs:
        return None
    m = re.search(r"EPSG(?::|/0/|::)(\d+)", srs) or re.search(r"(\d{4,5})$", srs)
    return int(m.group(1)) if m else None


def split_coords(text, dim):
    vals = [float(v) for v in text.split()]
    if dim not in (2, 3):
        dim = 3 if len(vals) % 3 == 0 else 2
    return [tuple(vals[i : i + dim]) for i in range(0, len(vals) - dim + 1, dim)]


def inherited_attr(elem, name):
    cur = elem
    while cur is not None:
        value = cur.get(name)
        if value:
            return value
        cur = cur.getparent()
    return None


def coord_to_lonlat(x, y, epsg):
    if 30 <= x <= 40 and 130 <= y <= 145:
        return y, x
    if 130 <= x <= 145 and 30 <= y <= 40:
        return x, y
    if epsg:
        try:
            lon, lat = Transformer.from_crs(
                CRS.from_epsg(epsg), 4326, always_xy=True
            ).transform(x, y)
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                return lon, lat
        except Exception:
            pass
    return None


def ring_coords(ring):
    poslists = [x for x in ring.iter() if lname(x.tag) == "posList" and x.text]
    if poslists:
        pos = poslists[0]
        srs = inherited_attr(pos, "srsName")
        dimtxt = inherited_attr(pos, "srsDimension")
        dim = int(dimtxt) if dimtxt and dimtxt.isdigit() else None
        coords = []
        for raw in split_coords(pos.text, dim):
            p = coord_to_lonlat(raw[0], raw[1], epsg_from_srs(srs))
            if p:
                coords.append(p)
    else:
        coords = []
        poses = [x for x in ring.iter() if lname(x.tag) == "pos" and x.text]
        for pos in poses:
            srs = inherited_attr(pos, "srsName")
            vals = [float(v) for v in pos.text.split()]
            if len(vals) < 2:
                continue
            p = coord_to_lonlat(vals[0], vals[1], epsg_from_srs(srs))
            if p:
                coords.append(p)
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def polygon_from_gml(poly_elem):
    exterior = None
    holes = []
    for child in poly_elem.iter():
        typ = lname(child.tag)
        if typ not in {"exterior", "interior"}:
            continue
        rings = [x for x in child.iter() if lname(x.tag) == "LinearRing"]
        if not rings:
            continue
        coords = ring_coords(rings[0])
        if not coords:
            continue
        if typ == "exterior" and exterior is None:
            exterior = coords
        elif typ == "interior":
            holes.append(coords)
    if exterior is None:
        return None
    p = Polygon(exterior, holes)
    if not p.is_valid:
        p = p.buffer(0)
    if p.is_empty or p.area <= 0:
        return None
    return p


def polygonal_only(geom):
    if geom.geom_type in {"Polygon", "MultiPolygon"}:
        return geom
    if isinstance(geom, GeometryCollection):
        parts = [g for g in geom.geoms if g.geom_type in {"Polygon", "MultiPolygon"}]
        return unary_union(parts) if parts else None
    return None


def extract_complete_lod0(building):
    """Return a complete polygonal LOD0 geometry, never just the first posList."""
    for source_name in ("lod0FootPrint", "lod0RoofEdge", "GroundSurface"):
        containers = [x for x in building.iter() if lname(x.tag) == source_name]
        polys = []
        for container in containers:
            for pe in container.iter():
                if lname(pe.tag) != "Polygon":
                    continue
                p = polygon_from_gml(pe)
                if p is not None:
                    polys.append(p)
        if polys:
            merged = polygonal_only(unary_union(polys))
            if merged is not None and not merged.is_empty and merged.area > 0:
                return merged, {
                    "sourceElement": source_name,
                    "polygonMembersParsed": len(polys),
                    "resultGeometryType": merged.geom_type,
                    "fix": "all_gml_polygon_members_unioned",
                }
    return None, {
        "sourceElement": None,
        "polygonMembersParsed": 0,
        "resultGeometryType": None,
        "fix": "no_safe_lod0_or_groundsurface_geometry",
    }


def local_projector(lon, lat):
    crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs"
    )
    return Transformer.from_crs(4326, crs, always_xy=True).transform


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def gsi_anchor(session):
    r = session.get(GSI, params={"q": TARGET["address"]}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise RuntimeError("GSI address search returned no result")
    f = data[0]
    lon, lat = f["geometry"]["coordinates"][:2]
    return {
        "queryUrl": r.url,
        "title": f.get("properties", {}).get("title"),
        "lon": float(lon),
        "lat": float(lat),
        "distanceFromFrozenRepresentativeM": round(
            haversine_m(TARGET["lon"], TARGET["lat"], float(lon), float(lat)), 3
        ),
    }


def citygml_files_for_point(session, lon, lat):
    url = f"{API}/datacatalog/citygml/r:{lon},{lat}?types=bldg"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    cities = data.get("cities") or data.get("citygml") or data.get("datasets") or []
    if isinstance(data, list):
        cities = data
    rows = []
    for city in cities:
        for f in (city.get("files") or {}).get("bldg") or []:
            if f.get("url"):
                rows.append(
                    {
                        "cityCode": city.get("cityCode") or city.get("city_code"),
                        "cityName": city.get("cityName") or city.get("city"),
                        "year": city.get("year"),
                        "registrationYear": city.get("registrationYear") or city.get("registration_year"),
                        "spec": city.get("spec"),
                        "meshCode": f.get("code"),
                        "maxLod": f.get("maxLod"),
                        "fileSize": f.get("fileSize"),
                        "features": f.get("features"),
                        "url": f.get("url"),
                    }
                )
    if not rows:
        raise RuntimeError(f"no bldg CityGML file returned from {url}")
    maxyear = max((x.get("year") or 0) for x in rows)
    return url, [x for x in rows if (x.get("year") or 0) == maxyear], data


def parse_gml(blob, anchor):
    root = etree.fromstring(blob)
    fwd = local_projector(anchor["lon"], anchor["lat"])
    anchor_m = Point(*fwd(anchor["lon"], anchor["lat"]))
    found = []
    for b in root.iter():
        if lname(b.tag) != "Building":
            continue
        geom, geom_meta = extract_complete_lod0(b)
        if geom is None:
            continue
        gm = shp_transform(fwd, geom)
        d = gm.distance(anchor_m)
        cd = gm.centroid.distance(anchor_m)
        if d > RADIUS_M and cd > RADIUS_M:
            continue
        gid = next((v for k, v in b.attrib.items() if lname(k) == "id"), None)
        storeys = first_text(b, {"storeysAboveGround"})
        try:
            storeys_int = int(storeys) if storeys is not None else None
        except ValueError:
            storeys_int = None
        attrs = {
            "gmlId": gid,
            "name": all_text(b, {"name"})[:5],
            "buildingID": all_text(b, {"buildingID", "buildingIDAttribute"})[:5],
            "measuredHeight": first_text(b, {"measuredHeight"}),
            "storeysAboveGround": storeys_int,
            "yearOfConstruction": first_text(b, {"yearOfConstruction"}),
            "localityNames": all_text(b, {"LocalityName"})[:5],
        }
        area = gm.area
        control_area = TARGET["developerPhysicalControl"]["buildingAreaM2"]
        found.append(
            {
                "distanceFromGsiM": round(d, 3),
                "centroidDistanceFromGsiM": round(cd, 3),
                "areaM2": round(area, 2),
                "developerBuildingAreaM2": control_area,
                "areaVsDeveloperBuildingAreaRatio": round(area / control_area, 4),
                "containsGsi": bool(gm.covers(anchor_m)),
                "storeysMatch": storeys_int == TARGET["expectedStoreys"],
                "geometryMeta": geom_meta,
                "attributes": attrs,
                "geometry": mapping(geom),
            }
        )
    found.sort(
        key=lambda x: (
            not x["containsGsi"],
            not x["storeysMatch"],
            x["distanceFromGsiM"],
            abs(1.0 - x["areaVsDeveloperBuildingAreaRatio"]),
            x["centroidDistanceFromGsiM"],
        )
    )
    return found


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "iyashiro-v10-research/1.0"
    anchor = gsi_anchor(session)
    query_url, files, catalog = citygml_files_for_point(session, anchor["lon"], anchor["lat"])
    candidates = []
    source_files = []
    for row in files:
        r = session.get(row["url"], timeout=90)
        r.raise_for_status()
        blob = r.content
        sha = hashlib.sha256(blob).hexdigest()
        source_files.append({**row, "downloadedBytes": len(blob), "sha256": sha})
        for c in parse_gml(blob, anchor):
            c["sourceMeshCode"] = row.get("meshCode")
            c["sourceSha256"] = sha
            candidates.append(c)
    uniq = []
    seen = set()
    for c in candidates:
        k = (c["attributes"].get("gmlId"), json.dumps(c["geometry"], sort_keys=True))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    shortlist = [c for c in uniq if c["storeysMatch"] and c["distanceFromGsiM"] <= 20.0]
    exactish = [c for c in shortlist if c["containsGsi"] or c["distanceFromGsiM"] <= 10.0]
    features = []
    for i, c in enumerate(uniq):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "propertyId": TARGET["propertyId"],
                    "targetName": TARGET["buildingName"],
                    "candidateRank": i + 1,
                    "distanceFromGsiM": c["distanceFromGsiM"],
                    "areaM2": c["areaM2"],
                    "areaVsDeveloperBuildingAreaRatio": c["areaVsDeveloperBuildingAreaRatio"],
                    "containsGsi": c["containsGsi"],
                    "storeysMatch": c["storeysMatch"],
                    "geometrySourceElement": c["geometryMeta"]["sourceElement"],
                    "polygonMembersParsed": c["geometryMeta"]["polygonMembersParsed"],
                    **c["attributes"],
                },
                "geometry": c["geometry"],
            }
        )
    summary = {
        "schemaVersion": "v10-b46-sphere-plateau-v2-complete-multisurface",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "gsiAnchor": anchor,
        "catalogQueryUrl": query_url,
        "sourceFiles": source_files,
        "candidateCountWithin90m": len(uniq),
        "sameStoreyCandidatesWithin20m": len(shortlist),
        "exactishCandidatesWithin10mOrContainingGsi": len(exactish),
        "candidates": uniq,
        "formalBuildingPolygonsPromoted": 0,
        "verifiedGeometryAdded": 0,
        "geometryFix": {
            "v1Problem": "first_valid_posList_only",
            "v2Rule": "parse_all_gml_Polygon_members_in_preferred_LOD0_container_and_union",
            "arbitraryBuildingPosListFallback": False,
        },
        "policy": {
            "identityGate": "reverified_before_probe",
            "staleOsmWayUsage": "historical_shape_control_only",
            "developerPhysicalControlUsage": "independent_plausibility_only",
            "formalPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextGate": "candidate-level identity/source integrity + complete-multisurface shape QA, then frozen-sensitive-distance dry-run",
        },
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "plateau-candidates.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "catalog-response.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# V10 B46 SPHERE PLATEAU candidate probe v2",
        "",
        "v2 unions every gml:Polygon member in the selected LOD0 MultiSurface; it never treats the first posList as the full building.",
        "",
        f"- Property: {TARGET['buildingName']} ({TARGET['propertyId']})",
        f"- Address: {TARGET['address']}",
        f"- GSI anchor: {anchor['lat']}, {anchor['lon']} ({anchor['title']})",
        f"- Developer physical control: building {TARGET['developerPhysicalControl']['buildingAreaM2']} m² / site {TARGET['developerPhysicalControl']['siteAreaM2']} m² / total floor {TARGET['developerPhysicalControl']['totalFloorAreaM2']} m²",
        f"- Candidates within {RADIUS_M:.0f}m: {len(uniq)}",
        f"- 3F candidates within 20m: {len(shortlist)}",
        f"- Exact-ish candidates (contains GSI or <=10m): {len(exactish)}",
        "- Formal promotion: 0",
        "- Score/rank/automatic exclusion changes: 0",
        "",
    ]
    for i, c in enumerate(uniq[:20], 1):
        a = c["attributes"]
        gm = c["geometryMeta"]
        md.append(
            f"- #{i}: d={c['distanceFromGsiM']}m centroid={c['centroidDistanceFromGsiM']}m "
            f"area={c['areaM2']}m² area/dev={c['areaVsDeveloperBuildingAreaRatio']} "
            f"source={gm['sourceElement']} members={gm['polygonMembersParsed']} containsGSI={c['containsGsi']} "
            f"floors={a.get('storeysAboveGround')} id={a.get('gmlId')} buildingID={a.get('buildingID')} year={a.get('yearOfConstruction')}"
        )
    (OUT / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    sums = []
    for p in sorted(OUT.iterdir()):
        if p.name == "SHA256SUMS.txt" or not p.is_file():
            continue
        sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "target": TARGET["propertyId"],
                "gsi": anchor,
                "sourceFiles": len(source_files),
                "candidates": len(uniq),
                "sameStoreyWithin20m": len(shortlist),
                "exactish": len(exactish),
                "formalPromotion": 0,
                "topCandidate": {
                    "buildingID": (uniq[0]["attributes"].get("buildingID") if uniq else None),
                    "areaM2": (uniq[0]["areaM2"] if uniq else None),
                    "source": (uniq[0]["geometryMeta"]["sourceElement"] if uniq else None),
                    "members": (uniq[0]["geometryMeta"]["polygonMembersParsed"] if uniq else None),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
