#!/usr/bin/env python3
"""Audit Tokyo's official archaeological service for Suzukamori execution ground.

The public search/API is queried after accepting the displayed terms in a normal
browser session. Raw provider geometry is retained only in the temporary
research artifact. A compact derived summary is written for Drive.

The archaeological extent is a development-review range, not automatically the
exact Edo-period execution-ground boundary. No scoring change is allowed.
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
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

OUT = Path("out-tokyo-iseki-suzugamori-api")
START_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/"
MAP_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/map.html"
BASE_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/"
MAPSERVER = "https://tokyo-iseki.metro.tokyo.lg.jp/cgi-bin/mapserver?map=/var/www/wms/iseki/wms_iseki3.map"
TARGET_NAMES = ["鈴ヶ森刑場跡", "鈴ケ森刑場跡", "鈴ヶ森刑場", "鈴ケ森刑場"]
TARGET_MUNICIPALITY = "品川区"


def write_bytes(name: str, data: bytes) -> dict:
    path = OUT / name
    path.write_bytes(data)
    return {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


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


def candidate_text(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False)


def extract_site_id(row: dict) -> str | None:
    for key in ["id", "sid", "site_id", "objectid", "gid"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    text = candidate_text(row)
    for pattern in [r"setmap\(['\"]([^'\"]+)['\"]\)", r"open_data\(['\"]([^'\"]+)['\"]\)", r"sid[=:'\"\s]+([A-Za-z0-9_-]+)"]:
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
        await page.wait_for_timeout(3_000)

        searches=[]
        all_rows=[]
        for name in TARGET_NAMES:
            form = {
                "rd_syurui": "遺跡",
                "txtname": name,
                "lst_kushityouson": TARGET_MUNICIPALITY,
                "txttyotyome": "",
                "txtisekino": "",
                "txtsyubetsu": "",
                "txtjidai": "",
            }
            resp = await context.request.post(
                urllib.parse.urljoin(BASE_URL, "json2.php"),
                form=form,
                headers={"Referer": MAP_URL, "Accept": "application/json,text/javascript,*/*;q=0.01", "X-Requested-With": "XMLHttpRequest"},
                timeout=120_000,
                fail_on_status_code=False,
            )
            body = await resp.body()
            write_bytes(f"search_{len(searches):02d}_{name}.json", body)
            try:
                rows=json.loads(body.decode("utf-8"))
            except Exception:
                rows=[]
            if not isinstance(rows,list):
                rows=[]
            searches.append({"name":name,"status":resp.status,"rowCount":len(rows)})
            all_rows.extend(rows)

        unique={}
        for row in all_rows:
            unique[json.dumps(row,ensure_ascii=False,sort_keys=True)] = row
        rows=list(unique.values())
        candidates=[r for r in rows if any(name in candidate_text(r) for name in TARGET_NAMES)]
        if not candidates:
            candidates=[r for r in rows if "刑場" in candidate_text(r) and ("鈴" in candidate_text(r) or "南大井" in candidate_text(r))]
        target_row=candidates[0] if candidates else (rows[0] if len(rows)==1 else None)
        site_id=extract_site_id(target_row or {})
        (OUT/"search-summary.json").write_text(json.dumps({"searches":searches,"rows":rows,"candidates":candidates,"targetRow":target_row},ensure_ascii=False,indent=2),encoding="utf-8")

        detail=None
        if site_id:
            resp=await context.request.get(
                urllib.parse.urljoin(BASE_URL,"getdata.php")+"?"+urllib.parse.urlencode({"sid":site_id}),
                headers={"Referer":MAP_URL,"Accept":"application/json,*/*;q=0.8","X-Requested-With":"XMLHttpRequest"},
                timeout=120_000,fail_on_status_code=False,
            )
            body=await resp.body()
            write_bytes("getdata_raw.json",body)
            try: detail=json.loads(body.decode("utf-8"))
            except Exception: detail=None

        raw_wfs=[]; geoms=[]; feature_summaries=[]
        if site_id:
            filter_xml=("<Filter><PropertyIsEqualTo><PropertyName>id</PropertyName>"+f"<Literal>{site_id}</Literal></PropertyIsEqualTo></Filter>")
            for typename in ["iseki2","isekipt2"]:
                params={"SERVICE":"WFS","REQUEST":"GetFeature","VERSION":"1.1.0","TYPENAME":typename,"OUTPUTFORMAT":"geojson","Filter":filter_xml}
                url=MAPSERVER+"&"+urllib.parse.urlencode(params)
                resp=await context.request.get(url,headers={"Referer":MAP_URL,"Accept":"application/json,application/geo+json,*/*;q=0.8"},timeout=120_000,fail_on_status_code=False)
                body=await resp.body(); meta=write_bytes(f"wfs_{typename}_raw.geojson",body); meta.update({"typename":typename,"status":resp.status,"url":url}); raw_wfs.append(meta)
                try:data=json.loads(body.decode("utf-8"))
                except Exception:data=None
                if not isinstance(data,dict):continue
                for feature in data.get("features",[]):
                    if not feature.get("geometry"):continue
                    geom=shape(feature["geometry"]); geoms.append(geom)
                    feature_summaries.append({"typename":typename,"geometryType":geom.geom_type,"featureId":feature.get("id"),"properties":feature.get("properties"),"sourceBoundsEPSG2451":list(geom.bounds)})

        geometry_summary=None
        if geoms:
            src=unary_union(geoms)
            to_wgs=Transformer.from_crs("EPSG:2451","EPSG:4326",always_xy=True).transform
            to_metric=Transformer.from_crs("EPSG:2451","EPSG:6677",always_xy=True).transform
            wgs=transform(to_wgs,src); metric=transform(to_metric,src)
            geometry_summary={
                "geometryType":wgs.geom_type,"sourceCRS":"EPSG:2451","derivedCRS":"EPSG:4326 / EPSG:6677",
                "areaSqm":metric.area,"perimeterM":metric.length,"centroidLonLat":[wgs.centroid.x,wgs.centroid.y],"bboxLonLat":list(wgs.bounds),
                "featureCount":len(geoms),"featureSummaries":feature_summaries,
                "interpretation":"official_archaeological_development_review_extent_not_exact_execution_ground_boundary",
                "scoringEffect":"none","verifiedHistoricalSitePolygonCountEffect":0,
            }
            private={"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":"SUZUKAMORI-OFFICIAL-ARCHAEOLOGICAL-EXTENT-REVIEW-V1","status":"official_archaeological_extent_review_only","scoringEffect":"none","verifiedHistoricalSitePolygonCountEffect":0,"terms":"internal research only; do not republish official provider geometry"},"geometry":mapping(wgs)}]}
            (OUT/"private_review_geometry.geojson").write_text(json.dumps(private,ensure_ascii=False),encoding="utf-8")

        summary={
            "acceptedTerms":accepted,"searches":searches,"searchRowCount":len(rows),"candidateCount":len(candidates),
            "targetRow":target_row,"siteId":site_id,"detail":detail,"wfsResponses":raw_wfs,"geometrySummary":geometry_summary,
            "dimensionConflictGate":{
                "sourceA":"Daikyoji official site: five tanbu taken from Oi village in 1651",
                "sourceB":"secondary/local heritage descriptions: about 40 ken frontage and 8-9 ken depth",
                "policy":"Do not create a single dimension-constrained boundary until the Genroku 8 cadastral record or equivalent primary survey is acquired."
            },
            "qualityGate":"Official archaeological extent is not the exact execution-ground boundary. Historical dimension sources conflict. Keep raw geometry internal, no scoring, no public redistribution, and require primary cadastral/historic-map corroboration before promotion."
        }
        (OUT/"SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        with (OUT/"SHA256SUMS.txt").open("w",encoding="utf-8") as f:
            for path in sorted(OUT.iterdir()):
                if path.is_file() and path.name!="SHA256SUMS.txt": f.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
        print(json.dumps({"siteId":site_id,"geometrySummary":geometry_summary,"candidateCount":len(candidates)},ensure_ascii=False,indent=2))
        await context.close(); await browser.close()


if __name__=="__main__": asyncio.run(main())
