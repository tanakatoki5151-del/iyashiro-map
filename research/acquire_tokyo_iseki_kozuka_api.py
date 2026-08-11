#!/usr/bin/env python3
"""Audit the official Tokyo archaeological service for Kozukappara.

The script uses the site's public search and WFS endpoints after accepting the
published terms in a normal browser session. It retains raw responses only in a
short-lived research artifact, and writes a compact derived summary for Drive.
The official archaeological extent remains a development-review range, not the
exact Edo-period execution-ground boundary, and has no scoring effect.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import urllib.parse
from pathlib import Path

from playwright.async_api import async_playwright
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union

OUT = Path("out-tokyo-iseki-kozuka-api")
START_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/"
MAP_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/map.html"
BASE_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/"
MAPSERVER = "https://tokyo-iseki.metro.tokyo.lg.jp/cgi-bin/mapserver?map=/var/www/wms/iseki/wms_iseki3.map"
TARGET_NAME = "小塚原刑場跡"
TARGET_NUMBER = "12"
TARGET_MUNICIPALITY = "荒川区"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_bytes(name: str, data: bytes) -> dict:
    path = OUT / name
    path.write_bytes(data)
    return {"path": name, "bytes": len(data), "sha256": sha256_bytes(data)}


async def accept_terms(page) -> bool:
    await page.goto(START_URL, wait_until="domcontentloaded", timeout=120_000)
    await page.wait_for_timeout(2_000)
    for label in ["同意する", "同意します", "上記の利用条件の全てに同意", "はい"]:
        loc = page.get_by_text(label, exact=False)
        for i in range(await loc.count()):
            try:
                if await loc.nth(i).is_visible():
                    await loc.nth(i).click(timeout=8_000)
                    await page.wait_for_timeout(2_000)
                    return True
            except Exception:
                pass
    for selector in ["input[type=submit]", "button", "input[type=button]"]:
        loc = page.locator(selector)
        for i in range(await loc.count()):
            item = loc.nth(i)
            try:
                text = " ".join(filter(None, [await item.inner_text(), await item.get_attribute("value")]))
                if "同意" in text or text.strip() == "はい":
                    await item.click(timeout=8_000)
                    await page.wait_for_timeout(2_000)
                    return True
            except Exception:
                pass
    return False


def extract_site_id(row: dict) -> str | None:
    for key in ["id", "sid", "site_id", "objectid", "gid"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    text = json.dumps(row, ensure_ascii=False)
    patterns = [
        r"setmap\(['\"]([^'\"]+)['\"]\)",
        r"open_data\(['\"]([^'\"]+)['\"]\)",
        r"sid[=:'\"\s]+([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1100})
        page = await context.new_page()
        accepted = await accept_terms(page)
        await page.goto(MAP_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(5_000)

        form = {
            "rd_syurui": "遺跡",
            "txtname": "",
            "lst_kushityouson": TARGET_MUNICIPALITY,
            "txttyotyome": "",
            "txtisekino": TARGET_NUMBER,
            "txtsyubetsu": "",
            "txtjidai": "",
        }
        search_resp = await context.request.post(
            urllib.parse.urljoin(BASE_URL, "json2.php"),
            form=form,
            headers={"Referer": MAP_URL, "Accept": "application/json,text/javascript,*/*;q=0.01", "X-Requested-With": "XMLHttpRequest"},
            timeout=120_000,
            fail_on_status_code=False,
        )
        search_body = await search_resp.body()
        search_file = write_bytes("01_json2_search_raw.json", search_body)
        try:
            search_rows = json.loads(search_body.decode("utf-8"))
        except Exception:
            search_rows = []
        if not isinstance(search_rows, list):
            search_rows = []
        candidates = [
            row for row in search_rows
            if TARGET_NAME in json.dumps(row, ensure_ascii=False)
            or str(row.get("iseki_no12", "")) == TARGET_NUMBER
            or (TARGET_NUMBER in str(row.get("no", "")) and "小塚原" in str(row.get("name", "")))
        ]
        target_row = candidates[0] if candidates else (search_rows[0] if len(search_rows) == 1 else None)
        site_id = extract_site_id(target_row or {})
        (OUT / "02_search_rows.json").write_text(json.dumps(search_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "03_target_row.json").write_text(json.dumps(target_row, ensure_ascii=False, indent=2), encoding="utf-8")

        detail = None
        detail_meta = None
        if site_id:
            detail_resp = await context.request.get(
                urllib.parse.urljoin(BASE_URL, "getdata.php") + "?" + urllib.parse.urlencode({"sid": site_id}),
                headers={"Referer": MAP_URL, "Accept": "application/json,*/*;q=0.8", "X-Requested-With": "XMLHttpRequest"},
                timeout=120_000,
                fail_on_status_code=False,
            )
            detail_body = await detail_resp.body()
            detail_meta = write_bytes("04_getdata_raw.json", detail_body)
            try:
                detail = json.loads(detail_body.decode("utf-8"))
            except Exception:
                detail = None

        raw_wfs_meta = []
        geometries = []
        feature_summaries = []
        if site_id:
            filter_xml = (
                "<Filter><PropertyIsEqualTo><PropertyName>id</PropertyName>"
                f"<Literal>{site_id}</Literal></PropertyIsEqualTo></Filter>"
            )
            for typename in ["iseki2", "isekipt2"]:
                params = {
                    "SERVICE": "WFS",
                    "REQUEST": "GetFeature",
                    "VERSION": "1.1.0",
                    "TYPENAME": typename,
                    "OUTPUTFORMAT": "geojson",
                    "Filter": filter_xml,
                }
                url = MAPSERVER + "&" + urllib.parse.urlencode(params)
                resp = await context.request.get(
                    url,
                    headers={"Referer": MAP_URL, "Accept": "application/json,application/geo+json,*/*;q=0.8"},
                    timeout=120_000,
                    fail_on_status_code=False,
                )
                body = await resp.body()
                meta = write_bytes(f"05_wfs_{typename}_raw.geojson", body)
                meta.update({"typename": typename, "status": resp.status, "contentType": resp.headers.get("content-type"), "url": url})
                raw_wfs_meta.append(meta)
                try:
                    data = json.loads(body.decode("utf-8"))
                except Exception:
                    data = None
                if not isinstance(data, dict):
                    continue
                for feature in data.get("features", []):
                    if not feature.get("geometry"):
                        continue
                    geom = shape(feature["geometry"])
                    geometries.append(geom)
                    feature_summaries.append({
                        "typename": typename,
                        "geometryType": geom.geom_type,
                        "featureId": feature.get("id"),
                        "properties": feature.get("properties"),
                        "sourceBoundsEPSG2451": list(geom.bounds),
                    })

        geometry_summary = None
        private_review_geojson = None
        if geometries:
            source_union = unary_union(geometries)
            to_wgs84 = Transformer.from_crs("EPSG:2451", "EPSG:4326", always_xy=True).transform
            to_metric = Transformer.from_crs("EPSG:2451", "EPSG:6677", always_xy=True).transform
            wgs_union = transform(to_wgs84, source_union)
            metric_union = transform(to_metric, source_union)
            geometry_summary = {
                "geometryType": wgs_union.geom_type,
                "sourceCRS": "EPSG:2451",
                "derivedCRS": "EPSG:4326 / EPSG:6677",
                "areaSqm": metric_union.area,
                "perimeterM": metric_union.length,
                "centroidLonLat": [wgs_union.centroid.x, wgs_union.centroid.y],
                "bboxLonLat": list(wgs_union.bounds),
                "featureCount": len(geometries),
                "featureSummaries": feature_summaries,
                "interpretation": "official_archaeological_development_review_extent_not_exact_execution_ground_boundary",
                "scoringEffect": "none",
                "verifiedHistoricalSitePolygonCountEffect": 0,
            }
            private_review_geojson = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {
                        "id": "KOZUKAPPARA-OFFICIAL-ARCHAEOLOGICAL-EXTENT-REVIEW-V1",
                        "status": "official_archaeological_extent_review_only",
                        "scoringEffect": "none",
                        "verifiedHistoricalSitePolygonCountEffect": 0,
                        "terms": "internal research only; do not republish official map geometry",
                    },
                    "geometry": mapping(wgs_union),
                }],
            }
            (OUT / "06_private_review_geometry.geojson").write_text(
                json.dumps(private_review_geojson, ensure_ascii=False), encoding="utf-8"
            )

        summary = {
            "acceptedTerms": accepted,
            "searchStatus": search_resp.status,
            "searchRaw": search_file,
            "searchRowCount": len(search_rows),
            "targetCandidateCount": len(candidates),
            "targetRow": target_row,
            "siteId": site_id,
            "detail": detail,
            "detailRaw": detail_meta,
            "wfsResponses": raw_wfs_meta,
            "geometrySummary": geometry_summary,
            "qualityGate": "Official archaeological extent is not the exact execution-ground boundary. Keep private/internal, no scoring, no public redistribution, and require historic map/cadastral corroboration before any boundary promotion.",
        }
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
            for path in sorted(OUT.iterdir()):
                if path.is_file() and path.name != "SHA256SUMS.txt":
                    f.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
        print(json.dumps({
            "acceptedTerms": accepted,
            "searchStatus": search_resp.status,
            "searchRowCount": len(search_rows),
            "siteId": site_id,
            "geometrySummary": geometry_summary,
        }, ensure_ascii=False, indent=2))
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
