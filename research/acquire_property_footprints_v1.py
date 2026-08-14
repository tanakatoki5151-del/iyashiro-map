#!/usr/bin/env python3
"""Acquire fail-closed OSM building-footprint candidates for V10 tier-1 properties.

This script does not promote any polygon into scoring. It records source geometry,
selection evidence, ambiguity, and identity gates for independent QA.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

TARGETS = [
    {"propertyId":"BLDG-b8fccb8ba282","buildingName":"コンフィアンサ等々力","address":"東京都世田谷区等々力7丁目3-5","lat":35.613114,"lon":139.655754,"identityStatus":"conflict","publicStatus":"public_warning"},
    {"propertyId":"BLDG-b1dbdbdf3f3d","buildingName":"SPHERE YOYOGIUEHARA HILLTOP","address":"東京都渋谷区上原2丁目11-20","lat":35.666282,"lon":139.683747,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-6583382c8322","buildingName":"建物名未確認（目黒本町5丁目・築13年）","address":"東京都目黒区目黒本町5丁目29-12","lat":35.620316,"lon":139.697525,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-f2a532eb6c9c","buildingName":"スチューデントハイツ代々木上原","address":"東京都渋谷区大山町47-15","lat":35.668621,"lon":139.678284,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-8bafd187bc1e","buildingName":"建物名未確認（駒沢大学徒歩8分）","address":"東京都目黒区東が丘2丁目13-11","lat":35.629673,"lon":139.663986,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-edf6c2448f9e","buildingName":"エスティメゾン代沢","address":"東京都世田谷区代沢2丁目39-13","lat":35.659447,"lon":139.673950,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-7f1edc74e493","buildingName":"いなげやアパート","address":"東京都世田谷区代沢2丁目44-9","lat":35.660534,"lon":139.672165,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-4e6c9a14c783","buildingName":"レオパレス駒場東大前","address":"東京都目黒区駒場4丁目3-21","lat":35.660763,"lon":139.680847,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-cef1a041caab","buildingName":"栄荘","address":"東京都目黒区目黒本町5丁目26-23","lat":35.619453,"lon":139.698257,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-c404c81c08a5","buildingName":"プリュメゾン駒沢","address":"東京都目黒区東が丘1丁目16-26","lat":35.628464,"lon":139.668793,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-72776fe404db","buildingName":"デュエル・ヤト","address":"東京都目黒区東が丘1丁目2-9","lat":35.628357,"lon":139.671021,"identityStatus":"confirmed","publicStatus":"public_confirmed"},
    {"propertyId":"BLDG-52b3385e1cff","buildingName":"AIFLAT代々木上原","address":"東京都渋谷区上原3丁目44-9","lat":35.6679527,"lon":139.6783275,"identityStatus":"unverified","publicStatus":"internal_only"},
    {"propertyId":"BLDG-f96539dece85","buildingName":"FAREウエハラコマチ","address":"東京都渋谷区上原2丁目42-10","lat":35.666479,"lon":139.681407,"identityStatus":"conflict","publicStatus":"public_warning"},
    {"propertyId":"BLDG-a08bd39495b1","buildingName":"CREATIF学芸大学","address":"東京都目黒区柿の木坂2丁目10-2","lat":35.6270553,"lon":139.6758456,"identityStatus":"provisional","publicStatus":"public_warning"},
    {"propertyId":"BLDG-86fc0a35dbb8","buildingName":"エバーグリーン東が丘","address":"東京都目黒区東が丘1丁目1-17","lat":35.62972513,"lon":139.671748,"identityStatus":"unverified","publicStatus":"internal_only"},
    {"propertyId":"BLDG-7331c4ac78c5","buildingName":"グレースコート東が丘","address":"東京都目黒区東が丘1丁目12-8","lat":35.62961116,"lon":139.67048359,"identityStatus":"provisional","publicStatus":"public_warning"},
    {"propertyId":"BLDG-73f4d89a1c58","buildingName":"ファーレ代々木上原","address":"東京都渋谷区富ヶ谷2丁目18-19","lat":35.668651,"lon":139.684841,"identityStatus":"unverified","publicStatus":"internal_only"},
]

ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
OUT = Path("out-property-footprints")
SEARCH_RADIUS_M = 45.0
FILTER_RADIUS_M = 80.0


def norm(value: str | None) -> str:
    return re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龠]+", "", (value or "").lower())


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1, d2 = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(d1 / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d2 / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_in_ring(lat: float, lon: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)):
            x_cross = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-30) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def element_rings(element: dict[str, Any]) -> list[list[list[float]]]:
    if element.get("type") == "way":
        geom = element.get("geometry") or []
        ring = [[float(p["lon"]), float(p["lat"])] for p in geom if "lon" in p and "lat" in p]
        return [ring] if len(ring) >= 3 else []
    rings = []
    for member in element.get("members") or []:
        if member.get("role") not in ("outer", ""):
            continue
        geom = member.get("geometry") or []
        ring = [[float(p["lon"]), float(p["lat"])] for p in geom if "lon" in p and "lat" in p]
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def element_center(element: dict[str, Any], rings: list[list[list[float]]]) -> tuple[float, float] | None:
    center = element.get("center")
    if center and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    pts = [p for ring in rings for p in ring]
    if not pts:
        return None
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def query_text() -> str:
    clauses = []
    for t in TARGETS:
        clauses.append(f'way(around:{SEARCH_RADIUS_M:.0f},{t["lat"]},{t["lon"]})["building"];')
        clauses.append(f'relation(around:{SEARCH_RADIUS_M:.0f},{t["lat"]},{t["lon"]})["building"];')
    return "[out:json][timeout:120];(" + "".join(clauses) + ");out meta tags center geom;"


def acquire(query: str) -> tuple[str, dict[str, Any]]:
    errors = []
    headers = {"User-Agent": "iyashiro-map-v10-research/1.0 (public research acquisition)"}
    for endpoint in ENDPOINTS:
        for attempt in range(3):
            try:
                response = requests.post(endpoint, data={"data": query}, headers=headers, timeout=150)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload.get("elements"), list):
                    raise ValueError("Overpass response has no elements array")
                return endpoint, payload
            except Exception as exc:
                errors.append({"endpoint": endpoint, "attempt": attempt + 1, "error": str(exc)})
                time.sleep(2 ** attempt)
    raise RuntimeError(json.dumps(errors, ensure_ascii=False))


def address_number(address: str) -> str | None:
    match = re.search(r"(\d+)[-丁目](\d+)(?:-(\d+))?$", address)
    if not match:
        return None
    parts = [p for p in match.groups() if p]
    return "-".join(parts[-2:]) if len(parts) >= 2 else parts[0]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    query = query_text()
    endpoint, payload = acquire(query)
    query_sha = hashlib.sha256(query.encode("utf-8")).hexdigest()
    elements = []
    for element in payload["elements"]:
        rings = element_rings(element)
        center = element_center(element, rings)
        if not rings or not center:
            continue
        elements.append({"raw": element, "rings": rings, "center": center})

    results = []
    features = []
    all_candidate_refs = set()

    for target in TARGETS:
        candidates = []
        for item in elements:
            distance = haversine(target["lat"], target["lon"], item["center"][0], item["center"][1])
            if distance > FILTER_RADIUS_M:
                continue
            containing = any(point_in_ring(target["lat"], target["lon"], ring) for ring in item["rings"])
            tags = item["raw"].get("tags") or {}
            candidates.append({
                "item": item,
                "distance": round(distance, 3),
                "contains": containing,
                "tags": tags,
            })
        candidates.sort(key=lambda c: (not c["contains"], c["distance"], c["item"]["raw"]["type"], c["item"]["raw"]["id"]))
        containing = [c for c in candidates if c["contains"]]
        selected = containing[0] if len(containing) == 1 else (candidates[0] if candidates else None)

        classification = "no_candidate_within_80m"
        name_match = False
        number_match = False
        if selected:
            tags = selected["tags"]
            osm_name = tags.get("name") or tags.get("name:ja")
            name_match = bool(osm_name and "未確認" not in target["buildingName"] and norm(osm_name) == norm(target["buildingName"]))
            expected_number = address_number(target["address"])
            osm_number = tags.get("addr:housenumber")
            number_match = bool(expected_number and osm_number and (norm(expected_number) == norm(osm_number) or norm(expected_number).endswith(norm(osm_number))))
            if target["identityStatus"] != "confirmed" or target["publicStatus"] != "public_confirmed":
                classification = "review_identity_or_publication_warning"
            elif len(containing) > 1:
                classification = "review_multiple_buildings_contain_representative_point"
            elif len(containing) == 1 and (name_match or number_match):
                classification = "strong_candidate_contains_point_and_osm_identity_match"
            elif len(containing) == 1:
                classification = "candidate_contains_address_representative_point"
            elif selected["distance"] <= 15:
                classification = "candidate_nearest_center_within_15m"
            else:
                classification = "review_nearest_candidate_over_15m"

        refs = []
        for c in candidates:
            e = c["item"]["raw"]
            ref = f'{e["type"]}/{e["id"]}'
            refs.append({
                "osmRef": ref,
                "containsRepresentativePoint": c["contains"],
                "centerDistanceMeters": c["distance"],
                "tags": c["tags"],
            })
            all_candidate_refs.add(ref)

        selected_ref = None
        if selected:
            e = selected["item"]["raw"]
            selected_ref = f'{e["type"]}/{e["id"]}'
            geom = selected["item"]["rings"]
            geometry = {"type": "Polygon", "coordinates": geom} if len(geom) == 1 else {"type": "MultiPolygon", "coordinates": [[ring] for ring in geom]}
            features.append({
                "type": "Feature",
                "id": target["propertyId"],
                "properties": {
                    "propertyId": target["propertyId"],
                    "buildingName": target["buildingName"],
                    "address": target["address"],
                    "source": "OpenStreetMap via Overpass",
                    "sourceEndpoint": endpoint,
                    "osmRef": selected_ref,
                    "classification": classification,
                    "containsRepresentativePoint": selected["contains"],
                    "centerDistanceMeters": selected["distance"],
                    "osmNameMatch": name_match,
                    "osmHouseNumberMatch": number_match,
                    "promotionStatus": "review_candidate_not_promoted",
                    "scoringEffect": "none",
                },
                "geometry": geometry,
            })

        results.append({
            **target,
            "candidateCountWithin80m": len(candidates),
            "containingCandidateCount": len(containing),
            "selectedOsmRef": selected_ref,
            "classification": classification,
            "osmNameMatch": name_match,
            "osmHouseNumberMatch": number_match,
            "promotionStatus": "review_candidate_not_promoted",
            "candidates": refs,
            "scoringEffect": "none",
        })

    counts: dict[str, int] = {}
    for result in results:
        counts[result["classification"]] = counts.get(result["classification"], 0) + 1

    summary = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lane": "V10",
        "mode": "fail_closed_research_candidate_acquisition",
        "source": {
            "name": "OpenStreetMap Overpass API",
            "endpoint": endpoint,
            "querySha256": query_sha,
            "searchRadiusMeters": SEARCH_RADIUS_M,
            "candidateFilterRadiusMeters": FILTER_RADIUS_M,
        },
        "counts": {
            "targets": len(TARGETS),
            "targetsWithSelectedCandidate": sum(1 for r in results if r["selectedOsmRef"]),
            "uniqueOsmCandidates": len(all_candidate_refs),
            "verifiedBuildingPolygonsPromoted": 0,
            "parcelPolygonsPromoted": 0,
            "byClassification": counts,
        },
        "policy": {
            "representativePointIsNotBuildingProof": True,
            "candidateGeometryRequiresIndependentIdentityQa": True,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
        },
        "items": results,
    }

    (OUT / "overpass-query.txt").write_text(query + "\n", encoding="utf-8")
    (OUT / "raw-overpass-response.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "tier1-building-candidates.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# V10 tier-1 building-footprint candidate acquisition",
        "",
        f"- Targets: {len(TARGETS)}",
        f"- Selected candidates: {summary['counts']['targetsWithSelectedCandidate']}",
        f"- Unique OSM candidates: {summary['counts']['uniqueOsmCandidates']}",
        "- Verified building polygons promoted: 0",
        "- Parcel polygons promoted: 0",
        "- Ranking / score / automatic exclusion changes: 0 / 0 / 0",
        "",
        "All geometries remain review candidates. An address representative point is not proof of building identity.",
    ]
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    hashes = []
    for path in sorted(OUT.iterdir()):
        if path.name == "SHA256SUMS.txt":
            continue
        hashes.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
