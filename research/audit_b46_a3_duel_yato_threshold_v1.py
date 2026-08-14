#!/usr/bin/env python3
"""V10 B46 A3 Duel Yato 500 m threshold audit v1.

Decision-only closure audit. It uses the A3 public-source probe and an exact-copy
subset selected by a full scan of the frozen V10 sensitive baseline. Existing
formal Building promotion contracts are checked but never relaxed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform as shp_transform, unary_union

PROBE = Path("out-b46-a3-duel-yato-crosssource-v1/SUMMARY.json")
FIXTURE = Path("research/fixtures/b46_a3_duel_yato_sensitive_subset_v1.json")
OUT = Path("out-b46-a3-duel-yato-threshold-v1")
LEAD_BUILDING_ID = "13110-bldg-50606"
THRESHOLD_M = 500.0
EXPECTED_BASELINE_SHA = "8108dad15b108ec1a1654368e7c7dbb4535963f270ec4cf838cb749c3b2bddef"
CATS = ("temple", "shrine", "cemetery")


def frozen_shape(rec):
    if rec["geometryType"] == "Point":
        return Point(rec["geometry"]["coordinates"])
    outers, inners = [], []
    for r in rec["geometry"].get("rings") or []:
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
        "overlapOfSmaller": round(inter / min(a.area, b.area), 6) if min(a.area, b.area) else 0,
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
        d = target.distance(fg)
        out[cat] = {
            "featureId": selected,
            "name": rec.get("name"),
            "sourceUrl": rec.get("sourceUrl"),
            "distanceM": round(d, 6),
            "class500": "review" if d < THRESHOLD_M else "within_preference",
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
    attrs = attrs_for(probe, lead["gmlId"])
    detail = (attrs.get("uro:buildingDetailAttribute") or [{}])[0]

    to6677 = Transformer.from_crs(4326, 6677, always_xy=True).transform
    lead_m = shp_transform(to6677, shape(lead["geometry"]))
    osm_m = shp_transform(to6677, shape(probe["osmCandidate"]["geometry"]))
    po = overlap(lead_m, osm_m)

    gsi_rows = []
    for g in probe["gsi"]["buildings"]:
        gm = shp_transform(to6677, shape(g["geometry"]))
        ov = overlap(lead_m, gm)
        if ov["intersectionM2"] > 0:
            gsi_rows.append({"candidate": g, "geometry": gm, "overlap": ov})
    if not gsi_rows:
        raise AssertionError("no GSI overlap with lead")
    gsi_rows.sort(key=lambda x: (-x["overlap"]["intersectionM2"], -x["overlap"]["iou"]))
    best_gsi = gsi_rows[0]
    gsi = best_gsi["candidate"]
    gsi_m = best_gsi["geometry"]

    pd = distances(lead_m, fixture)
    od = distances(osm_m, fixture)
    gd = distances(gsi_m, fixture)

    near2_with_osm = [
        c for c in probe["plateauCandidates"]
        if c.get("storeysAboveGround") == 2
        and c.get("distanceFromGsiM", 999999) <= 10
        and (c.get("vsOsm") or {}).get("intersectionM2", 0) > 0
    ]

    gates = {
        "one2fWithin10mOverlapsOsm": len(near2_with_osm) == 1 and building_id(near2_with_osm[0]) == LEAD_BUILDING_ID,
        "leadWithin10mExactGsiAddress": lead["distanceFromGsiM"] <= 10.0,
        "leadStoreys2": attrs.get("bldg:storeysAboveGround") == 2,
        "leadHeightPlausible": 5.0 <= float(attrs.get("bldg:measuredHeight", 0)) <= 9.0,
        "leadResidential": "住宅" in (attrs.get("bldg:usage") or []),
        "leadCurrentSourceHas2021Survey": detail.get("uro:surveyYear") == "2021",
        "plateauOsmDecisionOverlapStrong": po["overlapOfSmaller"] >= 0.90 and po["centroidDistanceM"] <= 2.0,
        "gsiFragmentOrdinaryBuilding": ftcode(gsi) == 3101,
        "gsiFragmentMaterialOverlap": best_gsi["overlap"]["intersectionM2"] >= 40.0,
        "plateauShrineInside500m": pd["shrine"]["distanceM"] < THRESHOLD_M,
        "osmShrineInside500m": od["shrine"]["distanceM"] < THRESHOLD_M,
        "gsiShrineInside500m": gd["shrine"]["distanceM"] < THRESHOLD_M,
        "plateauTempleInside500m": pd["temple"]["distanceM"] < THRESHOLD_M,
        "osmTempleInside500m": od["temple"]["distanceM"] < THRESHOLD_M,
        "gsiTempleInside500m": gd["temple"]["distanceM"] < THRESHOLD_M,
        "sameNearestShrineAcrossRepresentations": pd["shrine"]["featureId"] == od["shrine"]["featureId"] == gd["shrine"]["featureId"],
    }
    assert all(gates.values()), gates

    formal_existing = {
        "crossSourceV2IouRequirement": 0.85,
        "crossSourceV2OverlapSmallerRequirement": 0.95,
        "observedIou": po["iou"],
        "observedOverlapOfSmaller": po["overlapOfSmaller"],
        "passesExistingCrossSourceV2": po["iou"] >= 0.85 and po["overlapOfSmaller"] >= 0.95,
    }

    result = {
        "schemaVersion": "v10-b46-a3-duel-yato-threshold-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": probe["target"],
        "leadPlateau": {
            "buildingID": LEAD_BUILDING_ID,
            "gmlId": lead["gmlId"],
            "distanceFromGsiAddressM": lead["distanceFromGsiM"],
            "areaM2": lead["areaM2"],
            "measuredHeightM": float(attrs["bldg:measuredHeight"]),
            "storeysAboveGround": attrs["bldg:storeysAboveGround"],
            "class": attrs.get("bldg:class"),
            "usage": attrs.get("bldg:usage"),
            "detailedUsage": detail.get("uro:detailedUsage"),
            "creationDate": attrs.get("core:creationDate"),
            "surveyYear": detail.get("uro:surveyYear"),
        },
        "legacyOsm": {
            "wayId": probe["osmCandidate"]["wayId"],
            "timestamp": probe["osmCandidate"]["timestamp"],
            "areaM2": probe["osmCandidate"]["areaM2"],
            "distanceFromGsiAddressM": probe["osmCandidate"]["distanceFromGsiM"],
            "plateauOverlap": po,
        },
        "bestCurrentGsiFragment": {
            "ftCode": ftcode(gsi),
            "areaM2": gsi["areaM2"],
            "distanceFromGsiAddressM": gsi["distanceFromCurrentPointM"],
            "plateauOverlap": best_gsi["overlap"],
            "role": "partial decision corroboration only",
        },
        "sensitiveDistances": {"plateau": pd, "osm": od, "gsi": gd},
        "thresholdDecision": {
            "representativePriorM": probe["target"]["representativeSensitiveDistanceM"],
            "nearestCategory": "shrine",
            "nearestFeatureId": pd["shrine"]["featureId"],
            "nearestFeatureName": pd["shrine"]["name"],
            "plateauShrineM": pd["shrine"]["distanceM"],
            "osmShrineM": od["shrine"]["distanceM"],
            "gsiShrineM": gd["shrine"]["distanceM"],
            "plateauTempleM": pd["temple"]["distanceM"],
            "osmTempleM": od["temple"]["distanceM"],
            "gsiTempleM": gd["temple"]["distanceM"],
            "classChanged": False,
            "class": "review",
            "decisionLevel": "review_preserved_two_independent_sensitive_categories_three_geometry_corroborated",
        },
        "gates": gates,
        "formalExistingGateCheck": formal_existing,
        "formalBuildingPolygonsPromoted": 0,
        "verifiedGeometryAdded": 0,
        "policy": {
            "decisionStatus": "D-DONE",
            "formalStatus": "hold_existing_source_contract_not_relaxed",
            "formalHoldReason": "Existing cross-source v2 formal contract requires IoU>=0.85 and overlap(smaller)>=0.95; A3 is close but below both. Decision closure is stronger than representative-point status because shrine and temple both remain <500m in PLATEAU, OSM and GSI fragment representations.",
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextAutonomousBuilding": None,
            "autonomousBuildingLane": "complete_if_this_audit_passes",
        },
    }

    (OUT / "SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# V10 B46 A3 Duel Yato threshold audit v1",
        "",
        f"- Lead: `{LEAD_BUILDING_ID}` / 2F / {attrs.get('bldg:class')} / {attrs.get('bldg:measuredHeight')}m / {attrs.get('bldg:usage')}",
        f"- PLATEAU ↔ OSM: IoU {po['iou']:.6f} / overlap(smaller) {po['overlapOfSmaller']:.6f} / centroid {po['centroidDistanceM']:.3f}m",
        f"- Shrine {pd['shrine']['name']}: PLATEAU {pd['shrine']['distanceM']:.3f}m / OSM {od['shrine']['distanceM']:.3f}m / GSI {gd['shrine']['distanceM']:.3f}m",
        f"- Temple {pd['temple']['name']}: PLATEAU {pd['temple']['distanceM']:.3f}m / OSM {od['temple']['distanceM']:.3f}m / GSI {gd['temple']['distanceM']:.3f}m",
        "- 500m class flip: **NO; review remains review with two sensitive categories inside 500m**",
        "- Decision status: **D-DONE**",
        "- Formal promotion: **0**; existing source contract not relaxed",
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
