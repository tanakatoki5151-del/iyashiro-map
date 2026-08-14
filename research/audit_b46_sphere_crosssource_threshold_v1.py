#!/usr/bin/env python3
"""V10 B46 SPHERE cross-source identity + 500 m threshold audit v1.

Runs the two existing public-source probes first, then cross-checks the likely
current SPHERE building between PLATEAU 2025 and GSI Vector 2026-04-01 and
recomputes shrine/temple/cemetery distances against a tiny subset selected
from the exact frozen V10 sensitive-geometry baseline.

Fail-closed research audit only. No formal Building Polygon promotion and no
score/rank/automatic-exclusion change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform as shp_transform, unary_union

PLATEAU_SUMMARY = Path("out-b46-sphere-plateau-v1/SUMMARY.json")
GSI_SUMMARY = Path("out-b46-sphere-gsi-vector-v1/SUMMARY.json")
FIXTURE = Path("research/fixtures/b46_sphere_sensitive_subset_v1.json")
OUT = Path("out-b46-sphere-crosssource-threshold-v1")

CURRENT_PLATEAU_ID = "13113-bldg-2503209"
LEGACY_PLATEAU_ID = "13113-bldg-15513"
OFFICIAL_BUILDING_AREA_M2 = 204.50
THRESHOLD_M = 500.0
ATTR_API = "https://api.plateauview.mlit.go.jp/citygml/attributes"
CATS = ("temple", "shrine", "cemetery")


def prop_ftcode(c):
    p = c.get("properties") or {}
    v = p.get("ftCode") if "ftCode" in p else p.get("ftcode")
    try:
        return int(v)
    except Exception:
        return None


def building_id(c):
    vals = (c.get("attributes") or {}).get("buildingID") or []
    return vals[0] if vals else None


def geometry_from_frozen(rec):
    typ = rec.get("geometryType")
    g = rec.get("geometry") or {}
    if typ == "Point":
        return Point(g["coordinates"])
    if typ in {"Polygon", "MultiPolygon"}:
        rings = g.get("rings") or []
        outers = [Polygon(r["coordinates"]) for r in rings if r.get("role") == "outer" and len(r.get("coordinates") or []) >= 4]
        inners = [Polygon(r["coordinates"]) for r in rings if r.get("role") == "inner" and len(r.get("coordinates") or []) >= 4]
        if not outers:
            return None
        geom = unary_union(outers)
        for hole in inners:
            geom = geom.difference(hole)
        return geom
    return None


def find_plateau(summary, bid):
    hits = [c for c in summary["candidates"] if building_id(c) == bid]
    if len(hits) != 1:
        raise AssertionError((bid, len(hits)))
    return hits[0]


def overlap_record(pgeom, gsi_candidates, to6677):
    pm = shp_transform(to6677.transform, pgeom)
    rows = []
    for c in gsi_candidates:
        gm = shp_transform(to6677.transform, shape(c["geometry"]))
        inter = pm.intersection(gm).area
        if inter <= 0:
            continue
        rows.append(
            {
                "gsiFeatureId": c.get("featureId"),
                "ftCode": prop_ftcode(c),
                "gsiAreaM2": round(gm.area, 6),
                "plateauAreaM2": round(pm.area, 6),
                "intersectionM2": round(inter, 6),
                "coverageOfGsi": round(inter / gm.area, 6) if gm.area else 0,
                "coverageOfPlateau": round(inter / pm.area, 6) if pm.area else 0,
                "gsiDistanceFromCurrentPointM": c.get("distanceFromCurrentPointM"),
            }
        )
    rows.sort(key=lambda r: (-r["intersectionM2"], -r["coverageOfGsi"]))
    return rows[0] if rows else None


def nearest_by_category(target_geom_6677, fixture):
    out = {}
    for cat in CATS:
        ids = fixture["selection"]["selectedFeatureIds"][cat]
        rows = []
        for rec in fixture["features"]:
            if rec["featureId"] not in ids:
                continue
            fg = geometry_from_frozen(rec)
            if fg is None:
                continue
            rows.append(
                {
                    "featureId": rec["featureId"],
                    "name": rec.get("name"),
                    "distanceM": round(target_geom_6677.distance(fg), 6),
                    "sourceUrl": rec.get("sourceUrl"),
                    "geometryType": rec.get("geometryType"),
                }
            )
        rows.sort(key=lambda r: r["distanceM"])
        if len(rows) < 2:
            raise AssertionError((cat, rows))
        out[cat] = {"nearest": rows[0], "runnerUp": rows[1]}
    return out


def class_band(d):
    return "review" if d < THRESHOLD_M else "within_preference"


def fetch_attributes(source_url, gml_ids, offline=False):
    if offline:
        return {"status": "skipped_offline", "records": []}
    s = requests.Session()
    s.headers["User-Agent"] = "iyashiro-v10-research/1.0"
    try:
        r = s.get(ATTR_API, params={"url": source_url, "id": ",".join(gml_ids)}, timeout=120)
        r.raise_for_status()
        data = r.json()
        return {"status": "success", "requestUrl": r.url, "records": data}
    except Exception as e:
        return {"status": "failed_non_blocking", "error": f"{type(e).__name__}: {e}", "records": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    plateau = json.loads(PLATEAU_SUMMARY.read_text(encoding="utf-8"))
    gsi = json.loads(GSI_SUMMARY.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["sourceFullGeometry"]["sha256"] == "8108dad15b108ec1a1654368e7c7dbb4535963f270ec4cf838cb749c3b2bddef"
    current = find_plateau(plateau, CURRENT_PLATEAU_ID)
    legacy = find_plateau(plateau, LEGACY_PLATEAU_ID)
    gsi_candidates = gsi["likelyBuildingPolygons"]
    sturdy = sorted([c for c in gsi_candidates if prop_ftcode(c) == 3102], key=lambda c: (c["distanceFromCurrentPointM"], c["centroidDistanceM"]))[0]

    to6677 = Transformer.from_crs(4326, 6677, always_xy=True)
    current_geom = shape(current["geometry"])
    legacy_geom = shape(legacy["geometry"])
    sturdy_geom = shape(sturdy["geometry"])
    current_6677 = shp_transform(to6677.transform, current_geom)
    sturdy_6677 = shp_transform(to6677.transform, sturdy_geom)

    current_overlap = overlap_record(current_geom, gsi_candidates, to6677)
    legacy_overlap = overlap_record(legacy_geom, gsi_candidates, to6677)
    current_dist = nearest_by_category(current_6677, fixture)
    sturdy_dist = nearest_by_category(sturdy_6677, fixture)

    source_url = next(x["url"] for x in plateau["sourceFiles"] if x.get("cityCode") == "13113")
    raw_attrs = fetch_attributes(
        source_url,
        [current["attributes"]["gmlId"], legacy["attributes"]["gmlId"]],
        offline=args.offline,
    )

    area_ratio = current["areaM2"] / OFFICIAL_BUILDING_AREA_M2
    current_temple = current_dist["temple"]["nearest"]
    sturdy_temple = sturdy_dist["temple"]["nearest"]

    gates = {
        "currentCandidateAddressAnchorWithin2m": current["distanceFromGsiM"] <= 2.0,
        "currentCandidateOfficialAreaWithin5pct": 0.95 <= area_ratio <= 1.05,
        "currentCandidateGsiOverlapIsSturdyBuilding": bool(current_overlap and current_overlap["ftCode"] == 3102 and current_overlap["coverageOfGsi"] >= 0.90),
        "legacyCandidateMapsToDifferentCurrentOrdinaryBuilding": bool(legacy_overlap and legacy_overlap["ftCode"] == 3101 and legacy_overlap["coverageOfGsi"] >= 0.95),
        "plateauCandidateTempleOutside500m": current_temple["distanceM"] >= THRESHOLD_M,
        "gsiSturdyTempleOutside500m": sturdy_temple["distanceM"] >= THRESHOLD_M,
        "sameNearestTempleAcrossRepresentations": current_temple["featureId"] == sturdy_temple["featureId"],
    }
    assert all(gates.values()), gates

    result = {
        "schemaVersion": "v10-b46-sphere-crosssource-threshold-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": plateau["target"],
        "officialPhysicalControl": {
            "sourcePage": "https://omiex.co.jp/sphere/index.html",
            "sourceImage": "https://omiex.co.jp/sphere/images/series04.jpg",
            "buildingAreaM2": OFFICIAL_BUILDING_AREA_M2,
            "siteAreaM2": 292.71,
            "totalFloorAreaM2": 799.65,
            "structure": "WRC",
            "storeys": "B1/3F",
        },
        "currentPlateauCandidate": {
            "buildingID": CURRENT_PLATEAU_ID,
            "gmlId": current["attributes"]["gmlId"],
            "distanceFromGsiAddressAnchorM": current["distanceFromGsiM"],
            "areaM2": current["areaM2"],
            "officialAreaRatio": round(area_ratio, 6),
            "measuredHeight": current["attributes"].get("measuredHeight"),
            "storeysAboveGroundRaw": current["attributes"].get("storeysAboveGround"),
            "storeysRawStatus": "unresolved_implausible_value" if (current["attributes"].get("storeysAboveGround") or 0) > 100 else "plausible",
            "geometryMeta": current.get("geometryMeta"),
            "bestCurrentGsiOverlap": current_overlap,
        },
        "legacyPlateauCandidate": {
            "buildingID": LEGACY_PLATEAU_ID,
            "gmlId": legacy["attributes"]["gmlId"],
            "distanceFromGsiAddressAnchorM": legacy["distanceFromGsiM"],
            "areaM2": legacy["areaM2"],
            "bestCurrentGsiOverlap": legacy_overlap,
        },
        "currentGsiSturdyBuilding": {
            "dataAsOf": gsi["source"]["documentedDataAsOf"],
            "ftCode": prop_ftcode(sturdy),
            "distanceFromCurrentPointM": sturdy["distanceFromCurrentPointM"],
            "areaM2": sturdy["areaM2"],
            "properties": sturdy.get("properties"),
        },
        "plateauSensitiveDistances": current_dist,
        "gsiSensitiveDistances": sturdy_dist,
        "thresholdM": THRESHOLD_M,
        "thresholdDecision": {
            "nearestFeatureId": current_temple["featureId"],
            "nearestFeatureName": current_temple["name"],
            "plateauPolygonDistanceM": current_temple["distanceM"],
            "plateauMarginM": round(current_temple["distanceM"] - THRESHOLD_M, 6),
            "gsiPolygonDistanceM": sturdy_temple["distanceM"],
            "gsiMarginM": round(sturdy_temple["distanceM"] - THRESHOLD_M, 6),
            "plateauClass": class_band(current_temple["distanceM"]),
            "gsiClass": class_band(sturdy_temple["distanceM"]),
            "classChangedFrom500mPreference": False,
            "decisionLevel": "no_threshold_flip_corroborated_by_plateau_and_current_gsi",
        },
        "plateauAttributeApi": raw_attrs,
        "gates": gates,
        "formalBuildingPolygonsPromoted": 0,
        "verifiedGeometryAdded": 0,
        "policy": {
            "formalPromotion": False,
            "candidateStatus": "high_confidence_current_candidate_formal_pending",
            "reasonFormalPending": "PLATEAU storeysAboveGround raw value 9999 is unresolved and the PLATEAU 500m margin is only about one metre",
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextGate": "inspect PLATEAU raw attributes/data-quality provenance for 13113-bldg-2503209; if identity/accuracy remains coherent, formalize candidate and rerun B45",
        },
    }

    (OUT / "SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# V10 B46 SPHERE cross-source threshold audit v1",
        "",
        f"- PLATEAU current candidate: `{CURRENT_PLATEAU_ID}` / d(address)={current['distanceFromGsiM']:.3f}m / area={current['areaM2']:.2f}m²",
        f"- Official building area control: {OFFICIAL_BUILDING_AREA_M2:.2f}m² / ratio={area_ratio:.4f}",
        f"- Best current GSI overlap: ftCode={current_overlap['ftCode']} / coverage-of-GSI={current_overlap['coverageOfGsi']:.4f}",
        f"- Legacy `{LEGACY_PLATEAU_ID}` best GSI overlap: ftCode={legacy_overlap['ftCode']} / coverage-of-GSI={legacy_overlap['coverageOfGsi']:.4f}",
        f"- Nearest temple: {current_temple['name']} ({current_temple['featureId']})",
        f"- PLATEAU polygon → temple: {current_temple['distanceM']:.3f}m (margin {current_temple['distanceM']-THRESHOLD_M:+.3f}m)",
        f"- Current GSI sturdy-building polygon → temple: {sturdy_temple['distanceM']:.3f}m (margin {sturdy_temple['distanceM']-THRESHOLD_M:+.3f}m)",
        "- 500m class flip: **NO in both independent geometries**",
        "- Formal promotion: **0** (raw PLATEAU storey value 9999 remains unresolved)",
        "- Score/rank/automatic exclusion changes: **0**",
        "",
        "## Gate result",
        *[f"- {k}: `{v}`" for k, v in gates.items()],
    ]
    (OUT / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    sums = []
    for p in sorted(OUT.iterdir()):
        if p.name == "SHA256SUMS.txt" or not p.is_file():
            continue
        sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps({"gates": gates, "thresholdDecision": result["thresholdDecision"], "attributeApi": raw_attrs["status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
