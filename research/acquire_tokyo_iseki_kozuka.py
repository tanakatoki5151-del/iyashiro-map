#!/usr/bin/env python3
"""Acquire official Tokyo archaeological-map data for Kozukappara.

This script uses only the public endpoints used by the Tokyo Metropolitan
Government map application:
- json2.php for the public search form,
- getdata.php for public detail attributes,
- MapServer WFS GetFeature for public geometry.

The returned archaeological extent is preserved as an official development-
review / buried-cultural-property extent. It is NOT promoted to the exact
Edo-period execution-ground boundary and never changes scoring by itself.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform

OUT = Path("out-tokyo-iseki-kozuka")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://tokyo-iseki.metro.tokyo.lg.jp"
MAP_PAGE = f"{BASE}/map.html"
SEARCH_URL = f"{BASE}/json2.php"
DETAIL_URL = f"{BASE}/getdata.php"
MAPSERVER_URL = f"{BASE}/cgi-bin/mapserver"
MAPFILE = "/var/www/wms/iseki/wms_iseki3.map"
TARGET_NAME = "小塚原刑場跡"
TARGET_NUMBER = "12"
TARGET_MUNICIPALITY = "荒川区"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (compatible; iyashiro-map-research/1.0; +https://github.com/tanakatoki5151-del/iyashiro-map)",
        "Accept-Language": "ja,en;q=0.8",
        "Referer": MAP_PAGE,
    }
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_response(name: str, response: requests.Response) -> dict[str, Any]:
    path = OUT / name
    path.write_bytes(response.content)
    return {
        "url": response.url,
        "status": response.status_code,
        "contentType": response.headers.get("content-type"),
        "bytes": len(response.content),
        "sha256": sha256(path),
        "savedAs": name,
    }


def parse_json_response(response: requests.Response) -> Any:
    response.raise_for_status()
    return response.json()


def select_target(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    exact = [r for r in rows if TARGET_NAME == str(r.get("name", "")).strip()]
    if exact:
        return exact[0]
    named = [r for r in rows if "小塚原" in str(r.get("name", "")) and "刑場" in str(r.get("name", ""))]
    if named:
        return named[0]
    numbered = [r for r in rows if str(r.get("iseki_no12", "")).split("-")[0] == TARGET_NUMBER and "南千住" in str(r.get("syozai", ""))]
    return numbered[0] if numbered else None


def feature_id(row: dict[str, Any]) -> str | None:
    for key in ("id", "sid", "ID"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    link = str(row.get("map_link", ""))
    match = re.search(r"setmap\(['\"]([^'\"]+)", link)
    return match.group(1) if match else None


def get_wfs(type_name: str, sid: str, srs_name: str | None = None) -> tuple[requests.Response, dict[str, Any] | None]:
    xml_filter = (
        "<Filter><PropertyIsEqualTo><PropertyName>id</PropertyName>"
        f"<Literal>{sid}</Literal></PropertyIsEqualTo></Filter>"
    )
    params: dict[str, str] = {
        "map": MAPFILE,
        "SERVICE": "WFS",
        "REQUEST": "GetFeature",
        "VERSION": "1.1.0",
        "TYPENAME": type_name,
        "OUTPUTFORMAT": "geojson",
        "Filter": xml_filter,
    }
    if srs_name:
        params["SRSNAME"] = srs_name
    response = SESSION.get(MAPSERVER_URL, params=params, timeout=120)
    data = None
    try:
        data = response.json()
    except Exception:
        pass
    return response, data


def coordinate_magnitude(geometry: dict[str, Any]) -> float:
    nums: list[float] = []
    def walk(value: Any) -> None:
        if isinstance(value, (int, float)):
            nums.append(abs(float(value)))
        elif isinstance(value, list):
            for x in value:
                walk(x)
    walk(geometry.get("coordinates"))
    return max(nums) if nums else 0.0


def transform_collection(data: dict[str, Any], source_epsg: int, target_epsg: int = 4326) -> dict[str, Any]:
    transformer = Transformer.from_crs(CRS.from_epsg(source_epsg), CRS.from_epsg(target_epsg), always_xy=True)
    out = json.loads(json.dumps(data, ensure_ascii=False))
    for feature in out.get("features", []):
        geom = shape(feature["geometry"])
        geom = transform(transformer.transform, geom)
        feature["geometry"] = mapping(geom)
        props = feature.setdefault("properties", {})
        props["sourceCrs"] = f"EPSG:{source_epsg}"
        props["derivedCrs"] = f"EPSG:{target_epsg}"
        props["scoringEffect"] = "none"
        props["boundaryRole"] = "official_archaeological_review_extent_not_exact_historical_site"
    out["crsDerivation"] = {
        "source": f"EPSG:{source_epsg}",
        "target": f"EPSG:{target_epsg}",
        "method": "pyproj always_xy",
    }
    return out


def collection_metrics(data4326: dict[str, Any]) -> dict[str, Any]:
    to_metric = Transformer.from_crs(4326, 6677, always_xy=True)
    metrics = []
    total_area = 0.0
    total_length = 0.0
    for feature in data4326.get("features", []):
        geom_wgs84 = shape(feature["geometry"])
        geom_m = transform(to_metric.transform, geom_wgs84)
        centroid = geom_wgs84.centroid
        row = {
            "featureId": feature.get("id") or feature.get("properties", {}).get("id"),
            "geometryType": geom_wgs84.geom_type,
            "areaSqm": round(geom_m.area, 3),
            "perimeterM": round(geom_m.length, 3),
            "centroidLng": round(centroid.x, 9),
            "centroidLat": round(centroid.y, 9),
            "boundsWgs84": [round(x, 9) for x in geom_wgs84.bounds],
        }
        metrics.append(row)
        total_area += geom_m.area
        total_length += geom_m.length
    return {
        "featureCount": len(metrics),
        "totalAreaSqm": round(total_area, 3),
        "totalPerimeterM": round(total_length, 3),
        "features": metrics,
    }


def main() -> int:
    provenance: dict[str, Any] = {
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "officialService": BASE,
        "qualityRule": (
            "The official archaeological extent is a development-review / buried-cultural-property extent. "
            "It is not automatically the exact Edo-period execution-ground boundary and has scoringEffect=none."
        ),
        "requests": [],
    }

    landing = SESSION.get(MAP_PAGE, timeout=120)
    provenance["requests"].append(save_response("00_map-page.html", landing))
    landing.raise_for_status()

    searches = [
        {
            "rd_syurui": "遺跡",
            "txtname": TARGET_NAME,
            "lst_kushityouson": TARGET_MUNICIPALITY,
            "txttyotyome": "",
            "txtisekino": "",
            "txtsyubetsu": "",
            "txtjidai": "",
        },
        {
            "rd_syurui": "遺跡",
            "txtname": "",
            "lst_kushityouson": TARGET_MUNICIPALITY,
            "txttyotyome": "南千住",
            "txtisekino": TARGET_NUMBER,
            "txtsyubetsu": "",
            "txtjidai": "",
        },
        {
            "rd_syurui": "遺跡",
            "txtname": "小塚原",
            "lst_kushityouson": TARGET_MUNICIPALITY,
            "txttyotyome": "",
            "txtisekino": "",
            "txtsyubetsu": "",
            "txtjidai": "",
        },
    ]
    all_rows: list[dict[str, Any]] = []
    search_reports = []
    for index, payload in enumerate(searches, 1):
        response = SESSION.post(SEARCH_URL, data=payload, timeout=120)
        provenance["requests"].append(save_response(f"01_search-{index}.json", response))
        rows = parse_json_response(response)
        if not isinstance(rows, list):
            rows = []
        search_reports.append({"query": payload, "resultCount": len(rows)})
        all_rows.extend(rows)
    # Stable de-duplication by JSON representation.
    unique_rows: list[dict[str, Any]] = []
    seen = set()
    for row in all_rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)
    (OUT / "02_search-results-merged.json").write_text(json.dumps(unique_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    target = select_target(unique_rows)
    if not target:
        (OUT / "SUMMARY.json").write_text(
            json.dumps({"status": "target_not_found", "searchReports": search_reports, **provenance}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 2
    sid = feature_id(target)
    if not sid:
        (OUT / "SUMMARY.json").write_text(
            json.dumps({"status": "feature_id_missing", "targetRow": target, **provenance}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 3

    (OUT / "03_target-row.json").write_text(json.dumps(target, ensure_ascii=False, indent=2), encoding="utf-8")
    detail = SESSION.get(DETAIL_URL, params={"sid": sid}, timeout=120)
    provenance["requests"].append(save_response("04_target-detail.json", detail))
    detail_data = parse_json_response(detail)

    caps_params = {"map": MAPFILE, "SERVICE": "WFS", "REQUEST": "GetCapabilities", "VERSION": "1.1.0"}
    caps = SESSION.get(MAPSERVER_URL, params=caps_params, timeout=120)
    provenance["requests"].append(save_response("05_wfs-capabilities.xml", caps))

    wfs_reports = []
    selected_collection = None
    selected_type = None
    selected_source_crs = None
    for typename in ("iseki2", "isekipt2", "iseki", "isekipt"):
        raw_response, raw_data = get_wfs(typename, sid, None)
        provenance["requests"].append(save_response(f"06_{typename}_raw.geojson", raw_response))
        wgs_response, wgs_data = get_wfs(typename, sid, "EPSG:4326")
        provenance["requests"].append(save_response(f"07_{typename}_srs4326.geojson", wgs_response))
        report = {
            "typeName": typename,
            "rawStatus": raw_response.status_code,
            "rawFeatureCount": len((raw_data or {}).get("features", [])) if isinstance(raw_data, dict) else None,
            "srs4326Status": wgs_response.status_code,
            "srs4326FeatureCount": len((wgs_data or {}).get("features", [])) if isinstance(wgs_data, dict) else None,
        }
        # Prefer a server-returned 4326 collection whose coordinates are degrees.
        if isinstance(wgs_data, dict) and wgs_data.get("features"):
            magnitude = coordinate_magnitude(wgs_data["features"][0].get("geometry", {}))
            report["srs4326CoordinateMagnitude"] = magnitude
            if magnitude <= 360 and selected_collection is None:
                selected_collection = wgs_data
                selected_type = typename
                selected_source_crs = 4326
        if isinstance(raw_data, dict) and raw_data.get("features"):
            magnitude = coordinate_magnitude(raw_data["features"][0].get("geometry", {}))
            report["rawCoordinateMagnitude"] = magnitude
            if selected_collection is None:
                if magnitude <= 360:
                    selected_collection = raw_data
                    selected_type = typename
                    selected_source_crs = 4326
                else:
                    # The official map JavaScript declares EPSG:2451 for raw WFS geometry.
                    selected_collection = transform_collection(raw_data, 2451, 4326)
                    selected_type = typename
                    selected_source_crs = 2451
        wfs_reports.append(report)

    if not selected_collection:
        summary = {
            "status": "wfs_geometry_not_found",
            "targetRow": target,
            "featureId": sid,
            "detail": detail_data,
            "searchReports": search_reports,
            "wfsReports": wfs_reports,
            **provenance,
        }
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 4

    for feature in selected_collection.get("features", []):
        props = feature.setdefault("properties", {})
        props.update(
            {
                "sourceService": BASE,
                "sourceEndpoint": "MapServer WFS",
                "sourceFeatureType": selected_type,
                "officialFeatureId": sid,
                "status": "official_archaeological_review_extent",
                "boundaryRole": "development_review_extent_not_exact_execution_ground",
                "scoringEffect": "none",
                "verifiedHistoricalSitePolygonCountEffect": 0,
            }
        )
    (OUT / "08_official-archaeological-extent-wgs84.geojson").write_text(
        json.dumps(selected_collection, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    metrics = collection_metrics(selected_collection)
    (OUT / "09_geometry-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "status": "official_geometry_acquired",
        "targetRow": target,
        "featureId": sid,
        "detail": detail_data,
        "searchReports": search_reports,
        "wfsReports": wfs_reports,
        "selectedFeatureType": selected_type,
        "selectedSourceCrs": f"EPSG:{selected_source_crs}",
        "metrics": metrics,
        "officialDimensionComparison": {
            "historicalApproximateDimensionsM": [108, 54],
            "historicalApproximateRectangleAreaSqm": 5832,
            "interpretation": "A size mismatch is expected because the archaeological extent is not necessarily the exact historical execution-ground parcel.",
        },
        **provenance,
        "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS.txt":
                f.write(f"{sha256(path)}  {path.relative_to(OUT)}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
