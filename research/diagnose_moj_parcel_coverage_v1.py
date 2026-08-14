#!/usr/bin/env python3
"""Diagnose spatial coverage of the 2026 MoJ-derived parcel GeoJSON around V10 buildings."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

import acquire_moj_parcel_pilot_v1 as base

OUT = Path("out-moj-parcel-coverage-diagnostic-v1")
INPUT = base.INPUT


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = json.loads(INPUT.read_text(encoding="utf-8"))
    buildings = {f["properties"]["propertyId"]: f for f in frozen["features"]}
    results = []
    nearest_features = []

    for property_id, cfg in base.TARGETS.items():
        building = buildings[property_id]
        package = base.get_package(cfg["packageId"])
        selected, available = base.choose_resource(package)
        year = selected["year"]
        resource = selected["resource"]
        raw_path = OUT / f"_download_{cfg['packageId']}_{year}.geojson"
        base.download(resource, raw_path)
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        source_crs, crs_reason = base.detect_crs(payload)
        src_to_metric = Transformer.from_crs(source_crs, CRS.from_epsg(6677), always_xy=True).transform
        src_to_wgs = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True).transform
        wgs_to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(6677), always_xy=True).transform
        building_wgs = shape(building["geometry"])
        building_metric = transform(wgs_to_metric, building_wgs)

        feature_count = 0
        valid_count = 0
        minx = miny = float("inf")
        maxx = maxy = float("-inf")
        nearest = []
        buckets = {100: 0, 250: 0, 500: 0, 1000: 0, 2000: 0, 5000: 0}

        for idx, feat in enumerate(payload.get("features") or []):
            gj = feat.get("geometry")
            if not gj:
                continue
            feature_count += 1
            try:
                geom_src = shape(gj)
            except Exception:
                continue
            if geom_src.is_empty:
                continue
            valid_count += int(geom_src.is_valid)
            bx = geom_src.bounds
            minx, miny = min(minx, bx[0]), min(miny, bx[1])
            maxx, maxy = max(maxx, bx[2]), max(maxy, bx[3])
            geom_metric = transform(src_to_metric, geom_src)
            distance = geom_metric.distance(building_metric)
            for threshold in buckets:
                if distance <= threshold:
                    buckets[threshold] += 1
            props = base.selected_properties(feat.get("properties") or {})
            item = {
                "sourceFeatureIndex": idx,
                "distanceToBuildingM": round(distance, 3),
                "parcelAreaSqm": round(geom_metric.area, 3),
                "semanticFields": base.semantic_fields(props),
                "properties": props,
                "geometry": mapping(transform(src_to_wgs, geom_src)) if source_crs.to_epsg() not in {4326, 6668} else mapping(geom_src),
            }
            nearest.append(item)

        nearest.sort(key=lambda x: x["distanceToBuildingM"])
        nearest = nearest[:10]
        if minx != float("inf"):
            dataset_box_src = box(minx, miny, maxx, maxy)
            dataset_box_wgs = transform(src_to_wgs, dataset_box_src) if source_crs.to_epsg() not in {4326, 6668} else dataset_box_src
            envelope = list(dataset_box_wgs.bounds)
            building_in_envelope = dataset_box_wgs.envelope.intersects(building_wgs)
        else:
            envelope = None
            building_in_envelope = False

        nearest_distance = nearest[0]["distanceToBuildingM"] if nearest else None
        if nearest_distance is None:
            diagnosis = "no_geometries_in_resource"
        elif nearest_distance <= 100:
            diagnosis = "local_coverage_present_but_join_logic_or_alignment_requires_review"
        elif nearest_distance <= 500:
            diagnosis = "local_coverage_sparse_target_near_edge_or_gap"
        else:
            diagnosis = "converted_public_coordinate_coverage_gap_near_target"

        result = {
            "propertyId": property_id,
            "buildingName": building["properties"]["buildingName"],
            "address": building["properties"]["address"],
            "ward": cfg["ward"],
            "packageId": cfg["packageId"],
            "availableGeojsonYears": [x["year"] for x in available],
            "selectedYear": year,
            "resourceId": resource.get("id"),
            "resourceName": resource.get("name"),
            "resourceUrl": resource.get("url"),
            "downloadSha256": sha(raw_path),
            "downloadBytes": raw_path.stat().st_size,
            "sourceCrs": source_crs.to_string(),
            "crsDetection": crs_reason,
            "featureCount": feature_count,
            "validGeometryCount": valid_count,
            "datasetEnvelopeWgs84": envelope,
            "buildingIntersectsDatasetEnvelope": building_in_envelope,
            "nearestParcelDistanceM": nearest_distance,
            "parcelCountWithinDistance": {str(k): v for k, v in buckets.items()},
            "diagnosis": diagnosis,
            "formalParcelPromotion": False,
            "scoringEffect": "none",
            "nearestFeatures": [{k: v for k, v in x.items() if k != "geometry"} for x in nearest],
        }
        results.append(result)
        for rank, x in enumerate(nearest[:5], 1):
            nearest_features.append({
                "type": "Feature",
                "properties": {
                    "propertyId": property_id,
                    "buildingName": building["properties"]["buildingName"],
                    "rank": rank,
                    "distanceToBuildingM": x["distanceToBuildingM"],
                    "semanticFields": x["semanticFields"],
                    "sourceProperties": x["properties"],
                    "scoringEffect": "none",
                },
                "geometry": x["geometry"],
            })
        raw_path.unlink(missing_ok=True)

    summary = {
        "version": "v10-moj-parcel-coverage-diagnostic-v1-20260815",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "policy": {"formalParcelPromotion": False, "scoringEffect": "none", "rankingEffect": "none", "automaticExclusionEffect": "none"},
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "nearest-parcels.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": nearest_features}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{sha(p)}  {p.name}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
