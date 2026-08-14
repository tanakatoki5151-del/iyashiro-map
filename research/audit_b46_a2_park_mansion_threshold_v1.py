#!/usr/bin/env python3
"""V10 B46 A2 Park Mansion 500 m threshold audit v1.

Consumes the public-source A2 cross-source probe plus a tiny exact-copy subset
selected by a full scan of the frozen V10 shrine/temple/cemetery baseline.
The purpose is decision closure only. Existing formal Building source contracts
are not relaxed and no score/rank/automatic-exclusion write is performed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform as shp_transform, unary_union

PROBE = Path("out-b46-a2-park-mansion-crosssource-v1/SUMMARY.json")
FIXTURE = Path("research/fixtures/b46_a2_park_mansion_sensitive_subset_v1.json")
OUT = Path("out-b46-a2-park-mansion-threshold-v1")
LEAD_BUILDING_ID = "13110-bldg-50079"
THRESHOLD_M = 500.0
EXPECTED_BASELINE_SHA = "8108dad15b108ec1a1654368e7c7dbb4535963f270ec4cf838cb749c3b2bddef"
CATS = ("temple", "shrine", "cemetery")


def frozen_shape(rec):
    typ = rec["geometryType"]
    g = rec["geometry"]
    if typ == "Point":
        return Point(g["coordinates"])
    rings = g.get("rings") or []
    outers, inners = [], []
    for r in rings:
        coords = r.get("coordinates") or []
        if len(coords) < 4:
            continue
        p = Polygon(coords)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty:
            continue
        (inners if r.get("role") == "inner" else outers).append(p)
    if not outers:
        return None
    geom = unary_union(outers)
    for h in inners:
        geom = geom.difference(h)
    return geom


def building_id(c):
    vals = c.get("buildingID") or []
    return vals[0] if vals else None


def ftcode(c):
    raw = c.get("ftCode")
    if raw is None:
        p = c.get("properties") or {}
        raw = p.get("ftCode") if "ftCode" in p else p.get("ftcode")
    try:
        return int(raw)
    except Exception:
        return None


def overlap(a, b):
    inter = a.intersection(b).area
    union = a.union(b).area
    return {
        "intersectionM2": round(inter, 6),
        "iou": round(inter / union, 6) if union else 0,
        "coverageA": round(inter / a.area, 6) if a.area else 0,
        "coverageB": round(inter / b.area, 6) if b.area else 0,
        "centroidDistanceM": round(a.centroid.distance(b.centroid), 6),
    }


def attrs_for(probe, gml_id):
    rows = [r for r in probe["plateauAttributeApi"].get("records", []) if r.get("gml:id") == gml_id]
    if len(rows) != 1:
        raise AssertionError((gml_id, len(rows)))
    return rows[0]


def distances(target, fixture):
    out = {}
    for cat in CATS:
        selected = fixture["selection"]["selectedFeatureIds"][cat]
        rec = next(r for r in fixture["features"] if r["featureId"] == selected)
        fg = frozen_shape(rec)
        if fg is None:
            raise AssertionError((cat, selected, "no geometry"))
        out[cat] = {
            "featureId": selected,
            "name": rec.get("name"),
            "sourceUrl": rec.get("sourceUrl"),
            "distanceM": round(target.distance(fg), 6),
            "class500": "review" if target.distance(fg) < THRESHOLD_M else "within_preference",
        }
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["sourceFullGeometry"]["sha256"] == EXPECTED_BASELINE_SHA
    assert fixture["sourceFullGeometry"]["featureCount"] == 31918

    leads = [c for c in probe["plateauCandidates"] if building_id(c) == LEAD_BUILDING_ID]
    if len(leads) != 1:
        raise AssertionError((LEAD_BUILDING_ID, len(leads)))
    lead = leads[0]
    lead_attrs = attrs_for(probe, lead["gmlId"])

    to6677 = Transformer.from_crs(4326, 6677, always_xy=True).transform
    lead_m = shp_transform(to6677, shape(lead["geometry"]))
    osm_m = shp_transform(to6677, shape(probe["osmCandidate"]["geometry"]))

    gsi_rows = []
    for g in probe["gsi"]["buildings"]:
        gm = shp_transform(to6677, shape(g["geometry"]))
        ov = overlap(lead_m, gm)
        gsi_rows.append({"candidate": g, "geometry": gm, "overlap": ov})
    gsi_rows.sort(key=lambda x: (-x["overlap"]["iou"], x["candidate"]["distanceFromCurrentPointM"]))
    best_gsi = gsi_rows[0]
    gsi = best_gsi["candidate"]
    gsi_m = best_gsi["geometry"]

    pd = distances(lead_m, fixture)
    gd = distances(gsi_m, fixture)
    od = distances(osm_m, fixture)

    same_storey_near = [
        c for c in probe["plateauCandidates"]
        if c.get("storeysAboveGround") == 3 and c.get("distanceFromGsiM", 999999) <= 10
    ]
    detail = (lead_attrs.get("uro:buildingDetailAttribute") or [{}])[0]
    usage = lead_attrs.get("bldg:usage") or []
    detailed_usage = detail.get("uro:detailedUsage")

    gates = {
        "one3fPlateauCandidateWithin10m": len(same_storey_near) == 1 and building_id(same_storey_near[0]) == LEAD_BUILDING_ID,
        "leadWithin5mOfExactGsiAddress": lead["distanceFromGsiM"] <= 5.0,
        "leadStoreys3": lead_attrs.get("bldg:storeysAboveGround") == 3,
        "leadClassSturdy": lead_attrs.get("bldg:class") == "堅ろう建物",
        "leadApartmentUsage": "共同住宅" in usage and detailed_usage == "集合住宅",
        "leadMeasuredHeightPlausible": 8.0 <= float(lead_attrs.get("bldg:measuredHeight", 0)) <= 15.0,
        "leadCurrentSourceHas2021Survey": detail.get("uro:surveyYear") == "2021",
        "gsiBestOverlapIsSturdy": ftcode(gsi) == 3102,
        "gsiPlateauIouAtLeast098": best_gsi["overlap"]["iou"] >= 0.98,
        "plateauCemeteryOutside500m": pd["cemetery"]["distanceM"] >= THRESHOLD_M,
        "gsiCemeteryOutside500m": gd["cemetery"]["distanceM"] >= THRESHOLD_M,
        "legacyOsmCemeteryOutside500m": od["cemetery"]["distanceM"] >= THRESHOLD_M,
        "sameNearestCemeteryAcrossRepresentations": pd["cemetery"]["featureId"] == gd["cemetery"]["featureId"] == od["cemetery"]["featureId"],
    }
    assert all(gates.values()), gates

    formal_gate_existing = {
        "plateauCanonicalPartialOsmOverlapRequirement": 0.95,
        "observedOsmCoverageByPlateau": round(lead_m.intersection(osm_m).area / osm_m.area, 6),
        "passesExistingPartialOsmContract": (lead_m.intersection(osm_m).area / osm_m.area) >= 0.95,
    }

    result = {
        "schemaVersion": "v10-b46-a2-park-mansion-threshold-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": probe["target"],
        "leadPlateau": {
            "buildingID": LEAD_BUILDING_ID,
            "gmlId": lead["gmlId"],
            "distanceFromGsiAddressM": lead["distanceFromGsiM"],
            "areaM2": lead["areaM2"],
            "measuredHeightM": float(lead_attrs["bldg:measuredHeight"]),
            "storeysAboveGround": lead_attrs["bldg:storeysAboveGround"],
            "class": lead_attrs["bldg:class"],
            "usage": usage,
            "detailedUsage": detailed_usage,
            "creationDate": lead_attrs.get("core:creationDate"),
            "surveyYear": detail.get("uro:surveyYear"),
        },
        "bestCurrentGsi": {
            "ftCode": ftcode(gsi),
            "areaM2": gsi["areaM2"],
            "distanceFromGsiAddressM": gsi["distanceFromCurrentPointM"],
            "plateauOverlap": best_gsi["overlap"],
        },
        "legacyOsm": {
            "wayId": probe["osmCandidate"]["wayId"],
            "timestamp": probe["osmCandidate"]["timestamp"],
            "areaM2": probe["osmCandidate"]["areaM2"],
            "distanceFromGsiAddressM": probe["osmCandidate"]["distanceFromGsiM"],
        },
        "sensitiveDistances": {"plateau": pd, "gsi": gd, "osm": od},
        "thresholdDecision": {
            "nearestCategory": "cemetery",
            "nearestFeatureId": pd["cemetery"]["featureId"],
            "plateauDistanceM": pd["cemetery"]["distanceM"],
            "plateauMarginM": round(pd["cemetery"]["distanceM"] - THRESHOLD_M, 6),
            "gsiDistanceM": gd["cemetery"]["distanceM"],
            "gsiMarginM": round(gd["cemetery"]["distanceM"] - THRESHOLD_M, 6),
            "osmDistanceM": od["cemetery"]["distanceM"],
            "osmMarginM": round(od["cemetery"]["distanceM"] - THRESHOLD_M, 6),
            "classChanged": False,
            "decisionLevel": "no_500m_flip_three_geometry_corroborated",
        },
        "gates": gates,
        "formalExistingGateCheck": formal_gate_existing,
        "formalBuildingPolygonsPromoted": 0,
        "verifiedGeometryAdded": 0,
        "policy": {
            "decisionStatus": "D-DONE",
            "formalStatus": "hold_existing_source_contract_not_relaxed",
            "formalHoldReason": "Existing PLATEAU-canonical contract requires >=95% coverage of the OSM partial by PLATEAU; A2 observed coverage is lower. GSI provides strong decision corroboration but is not silently substituted into an existing formal source contract.",
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextAutonomousBuilding": "A3 デュエル・ヤト",
        },
    }

    (OUT / "SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# V10 B46 A2 Park Mansion threshold audit v1",
        "",
        f"- Lead: `{LEAD_BUILDING_ID}` / 3F / {lead_attrs.get('bldg:class')} / {lead_attrs.get('bldg:measuredHeight')}m / {usage}",
        f"- PLATEAU ↔ current GSI IoU: {best_gsi['overlap']['iou']:.6f} (GSI ftCode={ftcode(gsi)})",
        f"- Nearest sensitive feature: {pd['cemetery']['featureId']} (cemetery)",
        f"- PLATEAU → cemetery: {pd['cemetery']['distanceM']:.3f}m ({pd['cemetery']['distanceM']-THRESHOLD_M:+.3f}m)",
        f"- GSI → cemetery: {gd['cemetery']['distanceM']:.3f}m ({gd['cemetery']['distanceM']-THRESHOLD_M:+.3f}m)",
        f"- legacy OSM → cemetery: {od['cemetery']['distanceM']:.3f}m ({od['cemetery']['distanceM']-THRESHOLD_M:+.3f}m)",
        "- 500m class flip: **NO across all three representations**",
        "- Decision status: **D-DONE**",
        "- Formal promotion: **0**; existing formal source contract remains unchanged",
        "- Score/rank/automatic exclusion changes: **0**",
        "",
        "## Gates",
        *[f"- {k}: `{v}`" for k, v in gates.items()],
    ]
    (OUT / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    sums = []
    for p in sorted(OUT.iterdir()):
        if p.name == "SHA256SUMS.txt" or not p.is_file():
            continue
        sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps({"gates": gates, "thresholdDecision": result["thresholdDecision"], "formal": result["policy"]["formalStatus"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
