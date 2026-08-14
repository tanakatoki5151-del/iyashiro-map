#!/usr/bin/env python3
"""Acquire and QA MoJ-derived parcel polygons around two V10 verified buildings.

Fail-closed contract:
- Frozen V10 verified building polygons are the only building inputs.
- CKAN package metadata is queried live; the newest public converted GeoJSON resource is selected.
- A stale converted dataset may be used for pipeline/topology QA, but can never be formally promoted.
- Even a current-year dataset remains review-only in this acquisition run; formal promotion requires
  an independent identity/precision QA step after inspecting the clipped evidence.
- No score, ranking, or automatic-exclusion changes are made by this script.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

OUT = Path("out-moj-parcel-pilot-v1")
INPUT = Path("research/inputs/v10-verified-building-polygons-v1.geojson")
CKAN = "https://www.geospatial.jp/ckan/api/3/action/package_show"
MOJ_CURRENT_YEAR = 2026
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "iyashiro-map-v10-parcel-pilot/1.0 public research"})

TARGETS = {
    "BLDG-7331c4ac78c5": {"ward": "目黒区", "packageId": "aigid-moj-13110"},
    "BLDG-f2a532eb6c9c": {"ward": "渋谷区", "packageId": "aigid-moj-13113"},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def get_package(package_id: str) -> dict[str, Any]:
    r = SESSION.get(CKAN, params={"id": package_id}, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success") or not isinstance(payload.get("result"), dict):
        raise RuntimeError(f"CKAN package_show failed for {package_id}: {payload}")
    return payload["result"]


def geojson_year(resource: dict[str, Any]) -> int | None:
    blob = " ".join(str(resource.get(k, "")) for k in ["name", "url", "description", "format"])
    if "筆R" not in blob or "geojson" not in blob.lower():
        return None
    m = re.search(r"筆R[_-]?(20\d{2})\.geojson", blob, flags=re.I)
    if not m:
        m = re.search(r"(20\d{2}).*geojson", blob, flags=re.I)
    return int(m.group(1)) if m else None


def choose_resource(package: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = []
    for resource in package.get("resources") or []:
        year = geojson_year(resource)
        if year:
            candidates.append({"year": year, "resource": resource})
    if not candidates:
        raise RuntimeError(f"No 筆R GeoJSON resource found in {package.get('name')}")
    candidates.sort(key=lambda x: (x["year"], x["resource"].get("last_modified") or ""), reverse=True)
    return candidates[0], candidates


def download(resource: dict[str, Any], destination: Path) -> dict[str, Any]:
    url = resource.get("url")
    if not isinstance(url, str) or not url.startswith("http"):
        raise RuntimeError(f"Resource has no downloadable URL: {resource}")
    with SESSION.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with destination.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
        return {
            "url": url,
            "status": r.status_code,
            "contentType": r.headers.get("Content-Type"),
            "contentLengthHeader": r.headers.get("Content-Length"),
            "etag": r.headers.get("ETag"),
            "lastModified": r.headers.get("Last-Modified"),
        }


def first_xy(geometry: Any) -> tuple[float, float] | None:
    if not geometry:
        return None
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    while isinstance(coords, list) and coords:
        if isinstance(coords[0], (int, float)) and len(coords) >= 2:
            return float(coords[0]), float(coords[1])
        coords = coords[0]
    return None


def detect_crs(payload: dict[str, Any]) -> tuple[CRS, str]:
    crs_obj = payload.get("crs")
    crs_name = ""
    if isinstance(crs_obj, dict):
        props = crs_obj.get("properties")
        if isinstance(props, dict):
            crs_name = str(props.get("name") or "")
    for epsg in [6677, 6668, 4326]:
        if str(epsg) in crs_name:
            return CRS.from_epsg(epsg), f"geojson_crs:{crs_name}"
    for feature in payload.get("features") or []:
        xy = first_xy(feature.get("geometry"))
        if xy:
            x, y = xy
            if abs(x) <= 180 and abs(y) <= 90:
                return CRS.from_epsg(6668), f"coordinate_magnitude_geographic:{x:.6f},{y:.6f}"
            return CRS.from_epsg(6677), f"coordinate_magnitude_projected:{x:.3f},{y:.3f}"
    raise RuntimeError("Unable to detect source CRS")


def bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def selected_properties(props: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in props.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            s = str(v) if v is not None else ""
            if len(s) <= 1000:
                out[k] = v
    return out


def semantic_fields(props: dict[str, Any]) -> dict[str, Any]:
    keys = list(props)
    wanted = {
        "parcelIdLike": ["筆id", "筆ID", "筆番号", "筆識別", "id", "ID"],
        "lotNumberLike": ["地番", "本番", "枝番", "地番区域"],
        "mapTypeLike": ["地図", "図種", "図郭", "法14条", "14条"],
        "precisionLike": ["精度", "座標", "測量", "縮尺"],
    }
    result: dict[str, Any] = {}
    for bucket, tokens in wanted.items():
        matched = {}
        for k in keys:
            kl = str(k)
            if any(token.lower() in kl.lower() for token in tokens):
                matched[kl] = props.get(k)
        result[bucket] = matched
    return result


def polygon_to_geojson_wgs84(geom, source_crs: CRS) -> dict[str, Any]:
    if source_crs.to_epsg() in {4326, 6668}:
        return mapping(geom)
    tx = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True).transform
    return mapping(transform(tx, geom))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = json.loads(INPUT.read_text(encoding="utf-8"))
    input_sha = sha256_file(INPUT)
    buildings = {f["properties"]["propertyId"]: f for f in frozen["features"]}
    package_cache: dict[str, dict[str, Any]] = {}
    resource_cache: dict[str, dict[str, Any]] = {}
    results = []
    clipped_features = []
    manifests = []

    for property_id, cfg in TARGETS.items():
        building = buildings[property_id]
        package_id = cfg["packageId"]
        if package_id not in package_cache:
            package_cache[package_id] = get_package(package_id)
        package = package_cache[package_id]
        selected, all_candidates = choose_resource(package)
        year = selected["year"]
        resource = selected["resource"]
        resource_id = str(resource.get("id") or safe_name(resource.get("name") or f"{package_id}-{year}"))
        if resource_id not in resource_cache:
            raw_path = OUT / f"_download_{safe_name(package_id)}_{year}.geojson"
            headers = download(resource, raw_path)
            resource_cache[resource_id] = {
                "path": str(raw_path),
                "sha256": sha256_file(raw_path),
                "bytes": raw_path.stat().st_size,
                "headers": headers,
            }
        raw = resource_cache[resource_id]
        raw_path = Path(raw["path"])
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        source_crs, crs_reason = detect_crs(payload)
        to_source = Transformer.from_crs(CRS.from_epsg(4326), source_crs, always_xy=True).transform
        source_to_metric = Transformer.from_crs(source_crs, CRS.from_epsg(6677), always_xy=True).transform
        metric_to_source = Transformer.from_crs(CRS.from_epsg(6677), source_crs, always_xy=True).transform
        building_wgs = shape(building["geometry"])
        building_source = transform(to_source, building_wgs)
        building_metric = transform(source_to_metric, building_source)
        search_source = transform(metric_to_source, building_metric.buffer(60))
        search_bbox = search_source.bounds

        parcel_rows = []
        intersects = []
        for idx, feat in enumerate(payload.get("features") or []):
            geom_json = feat.get("geometry")
            if not geom_json:
                continue
            try:
                geom = shape(geom_json)
            except Exception:
                continue
            if geom.is_empty or not bbox_intersects(geom.bounds, search_bbox):
                continue
            geom_metric = transform(source_to_metric, geom)
            centroid_distance = geom_metric.centroid.distance(building_metric.centroid)
            if centroid_distance > 120 and not geom_metric.intersects(building_metric.buffer(5)):
                continue
            inter_area = geom_metric.intersection(building_metric).area if geom_metric.intersects(building_metric) else 0.0
            ratio = inter_area / building_metric.area if building_metric.area else 0.0
            props = selected_properties(feat.get("properties") or {})
            row = {
                "sourceFeatureIndex": idx,
                "intersectionAreaSqm": round(inter_area, 4),
                "buildingCoverageRatio": round(ratio, 6),
                "parcelAreaSqm": round(geom_metric.area, 3),
                "centroidDistanceM": round(centroid_distance, 3),
                "containsBuilding": bool(geom_metric.covers(building_metric)),
                "intersectsBuilding": bool(inter_area > 0),
                "valid": bool(geom.is_valid),
                "semanticFields": semantic_fields(props),
                "properties": props,
            }
            parcel_rows.append(row)
            if inter_area > 0:
                intersects.append((row, geom, geom_metric))
                clipped_features.append({
                    "type": "Feature",
                    "properties": {
                        "propertyId": property_id,
                        "buildingName": building["properties"]["buildingName"],
                        "ward": cfg["ward"],
                        "datasetYear": year,
                        "sourceFeatureIndex": idx,
                        "buildingCoverageRatio": row["buildingCoverageRatio"],
                        "containsBuilding": row["containsBuilding"],
                        "semanticFields": row["semanticFields"],
                        "sourceProperties": props,
                        "promotionStatus": "review_candidate_not_promoted",
                        "scoringEffect": "none",
                    },
                    "geometry": polygon_to_geojson_wgs84(geom, source_crs),
                })

        union_coverage = 0.0
        if intersects:
            union_geom = unary_union([x[2] for x in intersects])
            union_coverage = union_geom.intersection(building_metric).area / building_metric.area
        single_covers = [x for x in intersects if x[0]["containsBuilding"] or x[0]["buildingCoverageRatio"] >= 0.98]
        has_identity_fields = any(
            any(v for v in x[0]["semanticFields"][bucket].values())
            for x in intersects
            for bucket in ["parcelIdLike", "lotNumberLike"]
        )
        has_precision_fields = any(
            any(v for v in x[0]["semanticFields"][bucket].values())
            for x in intersects
            for bucket in ["mapTypeLike", "precisionLike"]
        )

        freshness = "current_moj_year" if year >= MOJ_CURRENT_YEAR else "stale_relative_to_moj_2026_current"
        if year < MOJ_CURRENT_YEAR:
            decision = "review_stale_converted_dataset_no_formal_promotion"
        elif union_coverage < 0.95:
            decision = "hold_alignment_or_missing_parcel_coverage"
        elif not has_identity_fields:
            decision = "hold_parcel_identifier_fields_missing"
        elif not has_precision_fields:
            decision = "review_precision_or_maptype_metadata_missing"
        elif len(single_covers) == 1:
            decision = "review_single_parcel_candidate_ready_for_independent_qa"
        else:
            decision = "review_multi_parcel_or_ambiguous_candidate"

        result = {
            "propertyId": property_id,
            "buildingName": building["properties"]["buildingName"],
            "address": building["properties"]["address"],
            "ward": cfg["ward"],
            "buildingInputSha256": input_sha,
            "packageId": package_id,
            "packageModified": package.get("metadata_modified"),
            "availableGeojsonYears": [x["year"] for x in all_candidates],
            "selectedResourceYear": year,
            "resourceId": resource.get("id"),
            "resourceName": resource.get("name"),
            "resourceUrl": resource.get("url"),
            "resourceModified": resource.get("last_modified"),
            "downloadSha256": raw["sha256"],
            "downloadBytes": raw["bytes"],
            "sourceCrs": source_crs.to_string(),
            "crsDetection": crs_reason,
            "nearbyParcelCount": len(parcel_rows),
            "intersectingParcelCount": len(intersects),
            "singleCoverCandidateCount": len(single_covers),
            "unionBuildingCoverageRatio": round(union_coverage, 6),
            "hasParcelIdentityFields": has_identity_fields,
            "hasMapTypeOrPrecisionFields": has_precision_fields,
            "freshness": freshness,
            "decision": decision,
            "formalParcelPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "parcelCandidates": sorted(parcel_rows, key=lambda x: (-x["buildingCoverageRatio"], x["centroidDistanceM"]))[:20],
        }
        results.append(result)
        manifests.append({
            "packageId": package_id,
            "datasetTitle": package.get("title"),
            "selectedYear": year,
            "selectedResource": {k: resource.get(k) for k in ["id", "name", "url", "format", "created", "last_modified", "size"]},
            "download": {k: v for k, v in raw.items() if k != "path"},
            "availableResources": [
                {"year": x["year"], **{k: x["resource"].get(k) for k in ["id", "name", "url", "last_modified"]}}
                for x in all_candidates
            ],
        })

    for cached in resource_cache.values():
        Path(cached["path"]).unlink(missing_ok=True)

    summary = {
        "version": "v10-moj-parcel-pilot-v1-20260815",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mojCurrentDataYear": MOJ_CURRENT_YEAR,
        "input": {"path": str(INPUT), "sha256": input_sha, "featureCount": len(buildings)},
        "counts": {
            "targets": len(results),
            "formalParcelPromotions": sum(1 for x in results if x["formalParcelPromotion"]),
            "currentYearResources": sum(1 for x in results if x["freshness"] == "current_moj_year"),
            "staleConvertedResources": sum(1 for x in results if x["freshness"] != "current_moj_year"),
        },
        "results": results,
        "policy": {
            "parcelLegalBoundaryClaim": "none",
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "promotionRule": "acquisition output is review-only; independent identity/maptype/precision QA required",
        },
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "RESOURCE_MANIFEST.json").write_text(json.dumps(manifests, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "clipped-parcel-candidates.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": clipped_features}, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = [
        "# V10 MoJ Parcel Pilot v1", "", f"Frozen building input SHA-256: `{input_sha}`", "",
        "This artifact is fail-closed. No parcel polygon is formally promoted by the acquisition run.",
        "The newest converted GeoJSON resource exposed by each CKAN package is selected automatically.",
        "If that converted resource is older than the Ministry of Justice current 2026 dataset, the result is explicitly stale/review-only.", "",
    ]
    for r in results:
        readme += [
            f"## {r['buildingName']}",
            f"- selected converted year: {r['selectedResourceYear']} ({r['freshness']})",
            f"- intersecting parcels: {r['intersectingParcelCount']}",
            f"- union building coverage: {r['unionBuildingCoverageRatio']:.3%}",
            f"- decision: `{r['decision']}`", "",
        ]
    (OUT / "README.md").write_text("\n".join(readme), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{sha256_file(p)}  {p.name}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
