#!/usr/bin/env python3
"""Acquire official Tokyo archaeological-map geometry for Kozukappara.

This uses only public Tokyo Metropolitan Government endpoints discovered from
map.html and the public map JavaScript:
- json2.php for search results,
- getdata.php for detailed attributes,
- MapServer WFS for geometry.

The returned archaeological extent is a present-day cultural-property review
area. It MUST NOT be represented as the exact Edo-period execution-ground
boundary and MUST NOT affect scoring by itself.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

OUT = Path("out-kozuka-official-geometry")
BASE = "https://tokyo-iseki.metro.tokyo.lg.jp"
MAPSERVER = BASE + "/cgi-bin/mapserver?map=/var/www/wms/iseki/wms_iseki3.map"
TARGET_NAME = "小塚原刑場跡"
TARGET_MUNICIPALITY = "荒川区"
TARGET_NO = "12"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_bytes(path: Path, data: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": str(path.relative_to(OUT)), "bytes": len(data), "sha256": sha256_bytes(data)}


def json_dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_ids(rows: list[dict]) -> list[str]:
    ids: list[str] = []
    for row in rows:
        for key in ("id", "sid", "gid"):
            v = row.get(key)
            if v not in (None, ""):
                ids.append(str(v))
        for key in ("map_link", "link", "html"):
            text = str(row.get(key) or "")
            ids.extend(re.findall(r"setmap\(['\"]([^'\"]+)", text))
            ids.extend(re.findall(r"open_data\(['\"]([^'\"]+)", text))
    return list(dict.fromkeys(ids))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; iyashiro-map-research/1.0)",
        "Accept-Language": "ja,en;q=0.7",
    })
    report: dict = {
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": {"name": TARGET_NAME, "municipality": TARGET_MUNICIPALITY, "siteNumber": TARGET_NO},
        "searchAttempts": [],
        "selectedIds": [],
        "details": [],
        "wfs": [],
        "qualityRules": [
            "Official archaeological extent is a notification/development-review area, not automatically the exact historical execution-ground boundary.",
            "All resulting features have scoringEffect=none.",
            "Promotion requires independent historical maps, disposition records, dimensions/orientation and third-party review.",
        ],
    }

    # Establish an ordinary public session and preserve source pages/scripts.
    for url, name in [
        (BASE + "/map.html", "map.html"),
        (BASE + "/common/js/map.js", "map.js"),
    ]:
        try:
            r = session.get(url, timeout=90)
            rec = {"url": url, "status": r.status_code, "contentType": r.headers.get("content-type"), **write_bytes(OUT / "source" / name, r.content)}
            report.setdefault("sources", []).append(rec)
        except Exception as exc:
            report.setdefault("sources", []).append({"url": url, "error": f"{type(exc).__name__}: {exc}"})

    variants = [
        {"rd_syurui": "遺跡", "txtname": TARGET_NAME, "lst_kushityouson": TARGET_MUNICIPALITY, "txtisekino": TARGET_NO, "txttyotyome": "", "txtsyubetsu": "", "txtjidai": ""},
        {"rd_syurui": "遺跡", "txtname": TARGET_NAME, "lst_kushityouson": "", "txtisekino": "", "txttyotyome": "", "txtsyubetsu": "", "txtjidai": ""},
        {"rd_syurui": "遺跡", "txtname": "", "lst_kushityouson": TARGET_MUNICIPALITY, "txtisekino": TARGET_NO, "txttyotyome": "", "txtsyubetsu": "", "txtjidai": ""},
        {"rd_syurui": "遺跡", "txtname": "小塚原", "lst_kushityouson": TARGET_MUNICIPALITY, "txtisekino": "", "txttyotyome": "", "txtsyubetsu": "", "txtjidai": ""},
    ]
    all_rows: list[dict] = []
    for i, form in enumerate(variants, 1):
        try:
            r = session.post(BASE + "/json2.php", data=form, headers={"Referer": BASE + "/map.html", "X-Requested-With": "XMLHttpRequest"}, timeout=90)
            raw = r.content
            meta = {"attempt": i, "form": form, "url": r.url, "status": r.status_code, "contentType": r.headers.get("content-type"), **write_bytes(OUT / "search" / f"attempt-{i:02d}.json", raw)}
            try:
                rows = r.json()
            except Exception:
                rows = []
                meta["parseError"] = "response was not JSON"
            if not isinstance(rows, list):
                rows = []
            meta["rowCount"] = len(rows)
            report["searchAttempts"].append(meta)
            all_rows.extend(x for x in rows if isinstance(x, dict))
        except Exception as exc:
            report["searchAttempts"].append({"attempt": i, "form": form, "error": f"{type(exc).__name__}: {exc}"})

    # De-duplicate rows and retain only target-like records when possible.
    row_keys = set()
    rows: list[dict] = []
    for row in all_rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key not in row_keys:
            row_keys.add(key)
            rows.append(row)
    target_rows = [r for r in rows if TARGET_NAME in json.dumps(r, ensure_ascii=False) or (TARGET_NO in str(r.get("iseki_no12", "")) and "小塚原" in json.dumps(r, ensure_ascii=False))]
    if not target_rows:
        target_rows = rows
    json_dump(OUT / "search" / "all-unique-results.json", rows)
    json_dump(OUT / "search" / "target-results.json", target_rows)
    ids = extract_ids(target_rows)
    report["selectedIds"] = ids

    for sid in ids:
        try:
            r = session.get(BASE + "/getdata.php", params={"sid": sid}, headers={"Referer": BASE + "/map.html", "X-Requested-With": "XMLHttpRequest"}, timeout=90)
            rec = {"sid": sid, "url": r.url, "status": r.status_code, "contentType": r.headers.get("content-type"), **write_bytes(OUT / "details" / f"{sid}.json", r.content)}
            try:
                rec["parsed"] = r.json()
            except Exception:
                rec["parseError"] = "not JSON"
            report["details"].append(rec)
        except Exception as exc:
            report["details"].append({"sid": sid, "error": f"{type(exc).__name__}: {exc}"})

    # Preserve capabilities so the exact layer/CRS contract remains reproducible.
    try:
        cap_url = MAPSERVER + "&SERVICE=WFS&REQUEST=GetCapabilities&VERSION=1.1.0"
        r = session.get(cap_url, headers={"Referer": BASE + "/map.html"}, timeout=120)
        report["capabilities"] = {"url": cap_url, "status": r.status_code, "contentType": r.headers.get("content-type"), **write_bytes(OUT / "wfs" / "GetCapabilities.xml", r.content)}
    except Exception as exc:
        report["capabilities"] = {"error": f"{type(exc).__name__}: {exc}"}

    to_wgs84 = Transformer.from_crs("EPSG:2451", "EPSG:4326", always_xy=True).transform
    to_jgd2011_9 = Transformer.from_crs("EPSG:2451", "EPSG:6677", always_xy=True).transform
    normalized_features: list[dict] = []
    for sid in ids:
        for layer in ("iseki2", "isekipt2", "shise2", "shisept2"):
            filter_xml = f"<Filter><PropertyIsEqualTo><PropertyName>id</PropertyName><Literal>{sid}</Literal></PropertyIsEqualTo></Filter>"
            params = {
                "map": "/var/www/wms/iseki/wms_iseki3.map",
                "SERVICE": "WFS",
                "REQUEST": "GetFeature",
                "VERSION": "1.1.0",
                "TYPENAME": layer,
                "OUTPUTFORMAT": "geojson",
                "Filter": filter_xml,
            }
            url = BASE + "/cgi-bin/mapserver?" + urllib.parse.urlencode(params)
            try:
                r = session.get(url, headers={"Referer": BASE + "/map.html"}, timeout=120)
                rec = {"sid": sid, "layer": layer, "url": url, "status": r.status_code, "contentType": r.headers.get("content-type"), **write_bytes(OUT / "wfs" / f"{sid}_{layer}_EPSG2451.geojson", r.content)}
                try:
                    fc = r.json()
                except Exception:
                    fc = {"type": "FeatureCollection", "features": []}
                    rec["parseError"] = "not JSON"
                features = fc.get("features") or [] if isinstance(fc, dict) else []
                rec["featureCount"] = len(features)
                report["wfs"].append(rec)
                for feature in features:
                    try:
                        geom2451 = shape(feature["geometry"])
                        geom4326 = transform(to_wgs84, geom2451)
                        geom6677 = transform(to_jgd2011_9, geom2451)
                        props = dict(feature.get("properties") or {})
                        props.update({
                            "sourceLayer": layer,
                            "sourceCrs": "EPSG:2451",
                            "sourceSid": sid,
                            "boundaryRole": "official_archaeological_extent" if "pt" not in layer else "official_archaeological_point",
                            "status": "official_context_geometry_not_historical_exact_boundary",
                            "scoringEffect": "none",
                            "verifiedHistoricalSitePolygonCountEffect": 0,
                            "areaSqmEPSG6677": geom6677.area if geom6677.geom_type in {"Polygon", "MultiPolygon"} else 0,
                            "sourceUrl": url,
                        })
                        normalized_features.append({"type": "Feature", "geometry": mapping(geom4326), "properties": props})
                    except Exception as exc:
                        report.setdefault("geometryErrors", []).append({"sid": sid, "layer": layer, "error": f"{type(exc).__name__}: {exc}"})
            except Exception as exc:
                report["wfs"].append({"sid": sid, "layer": layer, "url": url, "error": f"{type(exc).__name__}: {exc}"})

    collection = {
        "type": "FeatureCollection",
        "name": "Kozukappara official archaeological context geometry",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": normalized_features,
    }
    json_dump(OUT / "derived" / "kozukappara-official-archaeological-context-EPSG4326.geojson", collection)

    polygons = [shape(f["geometry"]) for f in normalized_features if shape(f["geometry"]).geom_type in {"Polygon", "MultiPolygon"}]
    report["derived"] = {
        "normalizedFeatureCount": len(normalized_features),
        "polygonFeatureCount": len(polygons),
        "polygonAreasSqm": [f["properties"].get("areaSqmEPSG6677") for f in normalized_features if f["properties"].get("areaSqmEPSG6677")],
        "output": "derived/kozukappara-official-archaeological-context-EPSG4326.geojson",
        "status": "official_context_geometry_not_historical_exact_boundary",
        "scoringEffect": "none",
        "verifiedHistoricalSitePolygonCountEffect": 0,
    }
    report["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json_dump(OUT / "SUMMARY.json", report)
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS.txt":
                f.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(OUT)}\n")
    print(json.dumps({"ids": ids, **report["derived"]}, ensure_ascii=False, indent=2))
    return 0 if normalized_features else 2


if __name__ == "__main__":
    raise SystemExit(main())
