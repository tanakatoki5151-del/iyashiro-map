#!/usr/bin/env python3
"""Acquire official and georeferenced sources for the Suzukamori execution ground.

Sources:
1. Tokyo Metropolitan Government archaeological-map public search/detail/WFS.
2. Rumsey GeoGarage georeferenced Tokyo maps (1858 and 1892).
3. GSI public historical aerial photographs around the current monument.

The archaeological extent and all derived map hypotheses remain research-only.
They never change V10 scoring and are not exact historical-site boundaries until
independent cadastral/parcel evidence and third-party review are obtained.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from playwright.async_api import async_playwright
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform

OUT = Path("out-suzugamori-sources")
OUT.mkdir(parents=True, exist_ok=True)
TARGET = {"lat": 35.592612288897, "lng": 139.736986172061}
TARGET_NAMES = ["鈴ヶ森刑場跡", "鈴ヶ森刑場遺跡", "鈴ケ森刑場跡", "鈴ヶ森"]
MUNICIPALITY = "品川区"
BASE = "https://tokyo-iseki.metro.tokyo.lg.jp"
MAP_PAGE = f"{BASE}/map.html"
SEARCH_URL = f"{BASE}/json2.php"
DETAIL_URL = f"{BASE}/getdata.php"
MAPSERVER_URL = f"{BASE}/cgi-bin/mapserver"
MAPFILE = "/var/www/wms/iseki/wms_iseki3.map"
RUMSEY_PAGES = {
    "tokyo1858": "https://rumsey.geogarage.com/maps/g_ea173.html",
    "tokyo1892": "https://rumsey.geogarage.com/maps/geb133.html",
}
GSI_PAGE = (
    "https://service.gsi.go.jp/map-photos/app/map?search=photo"
    "&search_date_from=1935&search_date_to=1950"
    f"#15/{TARGET['lat']}/{TARGET['lng']}"
)
GSI_API = "https://service.gsi.go.jp/map-photos/app/api/photo"
GSI_IMAGE_BASE = "https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; iyashiro-map-research/1.0; +https://github.com/tanakatoki5151-del/iyashiro-map)",
    "Accept-Language": "ja,en;q=0.8",
    "Referer": MAP_PAGE,
})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_response(folder: Path, name: str, response: requests.Response) -> dict[str, Any]:
    path = folder / name
    path.write_bytes(response.content)
    return {
        "url": response.url,
        "status": response.status_code,
        "contentType": response.headers.get("content-type"),
        "bytes": len(response.content),
        "sha256": sha256(path),
        "savedAs": str(path.relative_to(OUT)),
    }


def select_target(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for preferred in TARGET_NAMES[:3]:
        exact = [r for r in rows if preferred == str(r.get("name", "")).strip()]
        if exact:
            return exact[0]
    candidates = [r for r in rows if ("鈴" in str(r.get("name", "")) and "森" in str(r.get("name", "")) and "刑場" in str(r.get("name", "")))]
    if candidates:
        return candidates[0]
    return None


def feature_id(row: dict[str, Any]) -> str | None:
    for key in ("id", "sid", "ID"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    match = re.search(r"setmap\(['\"]([^'\"]+)", str(row.get("map_link", "")))
    return match.group(1) if match else None


def get_wfs(type_name: str, sid: str, srs_name: str | None = None) -> tuple[requests.Response, dict[str, Any] | None]:
    xml_filter = (
        "<Filter><PropertyIsEqualTo><PropertyName>id</PropertyName>"
        f"<Literal>{sid}</Literal></PropertyIsEqualTo></Filter>"
    )
    params = {
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


def magnitude(geometry: dict[str, Any]) -> float:
    values: list[float] = []
    def walk(v: Any) -> None:
        if isinstance(v, (int, float)):
            values.append(abs(float(v)))
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(geometry.get("coordinates"))
    return max(values) if values else 0.0


def transform_collection(data: dict[str, Any], source_epsg: int) -> dict[str, Any]:
    transformer = Transformer.from_crs(source_epsg, 4326, always_xy=True)
    out = json.loads(json.dumps(data, ensure_ascii=False))
    for feature in out.get("features", []):
        feature["geometry"] = mapping(transform(transformer.transform, shape(feature["geometry"])))
    out["crsDerivation"] = {"source": f"EPSG:{source_epsg}", "target": "EPSG:4326", "method": "pyproj always_xy"}
    return out


def metrics(data4326: dict[str, Any]) -> dict[str, Any]:
    to_m = Transformer.from_crs(4326, 6677, always_xy=True)
    rows = []
    total_area = total_length = 0.0
    for feature in data4326.get("features", []):
        g = shape(feature["geometry"])
        gm = transform(to_m.transform, g)
        rows.append({
            "featureId": feature.get("id") or feature.get("properties", {}).get("id"),
            "geometryType": g.geom_type,
            "areaSqm": round(gm.area, 3),
            "perimeterM": round(gm.length, 3),
            "centroidLng": round(g.centroid.x, 9),
            "centroidLat": round(g.centroid.y, 9),
            "boundsWgs84": [round(x, 9) for x in g.bounds],
        })
        total_area += gm.area
        total_length += gm.length
    return {"featureCount": len(rows), "totalAreaSqm": round(total_area, 3), "totalPerimeterM": round(total_length, 3), "features": rows}


def acquire_official_archaeology() -> dict[str, Any]:
    folder = OUT / "official-archaeology"
    folder.mkdir(exist_ok=True)
    provenance = []
    landing = SESSION.get(MAP_PAGE, timeout=120)
    provenance.append(save_response(folder, "00_map-page.html", landing))
    searches = []
    all_rows: list[dict[str, Any]] = []
    for i, name in enumerate(TARGET_NAMES, 1):
        payload = {
            "rd_syurui": "遺跡",
            "txtname": name,
            "lst_kushityouson": MUNICIPALITY,
            "txttyotyome": "",
            "txtisekino": "",
            "txtsyubetsu": "",
            "txtjidai": "",
        }
        response = SESSION.post(SEARCH_URL, data=payload, timeout=120)
        provenance.append(save_response(folder, f"01_search-{i}.json", response))
        try:
            rows = response.json()
        except Exception:
            rows = []
        rows = rows if isinstance(rows, list) else []
        searches.append({"query": payload, "resultCount": len(rows)})
        all_rows.extend(rows)
    unique = []
    seen = set()
    for row in all_rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key); unique.append(row)
    (folder / "02_search-results.json").write_text(json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")
    target = select_target(unique)
    if not target:
        result = {"status": "target_not_found", "searches": searches, "provenance": provenance}
        (folder / "SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    sid = feature_id(target)
    (folder / "03_target-row.json").write_text(json.dumps(target, ensure_ascii=False, indent=2), encoding="utf-8")
    detail = SESSION.get(DETAIL_URL, params={"sid": sid}, timeout=120)
    provenance.append(save_response(folder, "04_detail.json", detail))
    try:
        detail_data = detail.json()
    except Exception:
        detail_data = None
    caps = SESSION.get(MAPSERVER_URL, params={"map":MAPFILE,"SERVICE":"WFS","REQUEST":"GetCapabilities","VERSION":"1.1.0"}, timeout=120)
    provenance.append(save_response(folder, "05_capabilities.xml", caps))
    selected = selected_type = selected_source = None
    wfs_reports = []
    for typename in ("iseki2", "isekipt2", "iseki", "isekipt"):
        raw_resp, raw = get_wfs(typename, sid, None)
        provenance.append(save_response(folder, f"06_{typename}_raw.geojson", raw_resp))
        wgs_resp, wgs = get_wfs(typename, sid, "EPSG:4326")
        provenance.append(save_response(folder, f"07_{typename}_4326.geojson", wgs_resp))
        row = {
            "typeName": typename,
            "rawStatus": raw_resp.status_code,
            "rawFeatureCount": len((raw or {}).get("features", [])) if isinstance(raw, dict) else None,
            "srs4326Status": wgs_resp.status_code,
            "srs4326FeatureCount": len((wgs or {}).get("features", [])) if isinstance(wgs, dict) else None,
        }
        if isinstance(wgs, dict) and wgs.get("features") and magnitude(wgs["features"][0]["geometry"]) <= 360 and selected is None:
            selected, selected_type, selected_source = wgs, typename, 4326
        if isinstance(raw, dict) and raw.get("features") and selected is None:
            mag = magnitude(raw["features"][0]["geometry"])
            if mag <= 360:
                selected, selected_type, selected_source = raw, typename, 4326
            else:
                selected, selected_type, selected_source = transform_collection(raw, 2451), typename, 2451
        wfs_reports.append(row)
    if selected:
        for f in selected.get("features", []):
            f.setdefault("properties", {}).update({
                "sourceService": BASE,
                "sourceFeatureType": selected_type,
                "officialFeatureId": sid,
                "status": "official_archaeological_review_extent",
                "boundaryRole": "development_review_extent_not_exact_execution_ground",
                "scoringEffect": "none",
                "verifiedHistoricalSitePolygonCountEffect": 0,
            })
        (folder / "08_official-extent-wgs84.geojson").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "status": "official_geometry_acquired" if selected else "wfs_geometry_not_found",
        "targetRow": target,
        "featureId": sid,
        "detail": detail_data,
        "selectedFeatureType": selected_type,
        "selectedSourceCrs": f"EPSG:{selected_source}" if selected_source else None,
        "metrics": metrics(selected) if selected else None,
        "historicalDimensions": {"frontageM": 74.0, "depthM": 16.2, "approxAreaSqm": 1198.8, "sourceNote": "1695 cadastral dimensions reported by Shinagawa Tourism Association"},
        "searches": searches,
        "wfsReports": wfs_reports,
        "provenance": provenance,
        "qualityRule": "Official archaeological extent is not automatically the exact historical execution-ground boundary; scoringEffect=none.",
    }
    (folder / "SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


async def capture_rumsey_and_gsi() -> dict[str, Any]:
    report: dict[str, Any] = {"rumsey": [], "gsi": {}}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for key, url in RUMSEY_PAGES.items():
            folder = OUT / "rumsey" / key
            folder.mkdir(parents=True, exist_ok=True)
            context = await browser.new_context(locale="ja-JP", viewport={"width":1600,"height":1200})
            page = await context.new_page()
            network = []; saved = []
            async def on_response(response):
                row={"url":response.url,"status":response.status,"contentType":response.headers.get("content-type")}
                network.append(row)
                ct=(row["contentType"] or "").lower(); low=response.url.lower()
                if response.status!=200 or not ("tile" in low or "geogarage" in low or "image" in ct or low.endswith((".png",".jpg",".jpeg"))): return
                try: body=await response.body()
                except Exception: return
                if not body or len(body)>8_000_000 or (body[:4]!=b"\x89PNG" and body[:3]!=b"\xff\xd8\xff"): return
                digest=hashlib.sha256(body).hexdigest(); ext=".png" if body[:4]==b"\x89PNG" else ".jpg"
                path=folder/f"tile_{len(saved):04d}_{digest[:12]}{ext}"; path.write_bytes(body)
                saved.append({**row,"savedAs":path.name,"bytes":len(body),"sha256":digest})
            page.on("response", lambda r: asyncio.create_task(on_response(r)))
            await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            await page.wait_for_timeout(12_000)
            await page.screenshot(path=str(folder/"01_initial.png"), full_page=True)
            move = await page.evaluate("""target=>{const o={attempts:[]};function t(n,m){if(!m)return false;try{if(typeof m.setCenter==='function'){if(window.google&&google.maps&&google.maps.LatLng)m.setCenter(new google.maps.LatLng(target.lat,target.lng));else m.setCenter([target.lat,target.lng]);if(typeof m.setZoom==='function')m.setZoom(18);o.attempts.push({name:n,method:'setCenter',ok:true});return true;}if(typeof m.setView==='function'){m.setView([target.lat,target.lng],18);o.attempts.push({name:n,method:'setView',ok:true});return true;}if(typeof m.getView==='function'){const v=m.getView();if(v&&typeof v.setCenter==='function'){const c=(window.ol&&ol.proj&&ol.proj.fromLonLat)?ol.proj.fromLonLat([target.lng,target.lat]):[target.lng,target.lat];v.setCenter(c);if(typeof v.setZoom==='function')v.setZoom(18);o.attempts.push({name:n,method:'ol',ok:true});return true;}}}catch(e){o.attempts.push({name:n,ok:false,error:String(e)});}return false;}for(const k of ['map','gmap','googleMap','mymap','olMap','leafletMap'])if(t(k,window[k])){o.movedBy=k;break;}if(!o.movedBy)for(const k of Object.keys(window)){if(/map/i.test(k)&&t(k,window[k])){o.movedBy=k;break;}}return o;}""", TARGET)
            await page.wait_for_timeout(12_000)
            await page.screenshot(path=str(folder/"02_suzugamori_target.png"), full_page=True)
            (folder/"02_after.html").write_text(await page.content(),encoding="utf-8")
            (folder/"network.json").write_text(json.dumps(network,ensure_ascii=False,indent=2),encoding="utf-8")
            (folder/"saved-tiles.json").write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding="utf-8")
            (folder/"move-result.json").write_text(json.dumps(move,ensure_ascii=False,indent=2),encoding="utf-8")
            report["rumsey"].append({"key":key,"url":url,"move":move,"networkCount":len(network),"savedTileCount":len(saved)})
            await context.close()

        folder = OUT / "gsi"
        folder.mkdir(exist_ok=True)
        images = folder / "images"; images.mkdir(exist_ok=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width":1600,"height":1100})
        page = await context.new_page(); api_payloads=[]
        async def on_gsi(response):
            if "/app/api/" in response.url and response.status==200 and "json" in (response.headers.get("content-type") or ""):
                try: api_payloads.append({"url":response.url,"payload":await response.json()})
                except Exception: pass
        page.on("response", lambda r: asyncio.create_task(on_gsi(r)))
        # Keep a public-page capture for provenance, but do not depend on the
        # current UI's year selector (the historical 1935 option can disappear).
        await page.goto(GSI_PAGE,wait_until="domcontentloaded",timeout=120_000); await page.wait_for_timeout(8_000)
        agree=page.locator("#terms_dialog #agree_btn:visible")
        if await agree.count(): await agree.first.click(timeout=10_000); await page.wait_for_timeout(2_000)
        await page.screenshot(path=str(folder/"search-page.png"),full_page=True)

        # Query the ordinary public photo API directly with an explicit date and
        # spatial window, then validate every returned footprint below.
        pad=0.04
        offset=0
        rows=[]
        ids=[]
        while True:
            params={
                "limit":200,
                "offset":offset,
                "rnem":0,
                "cnem":0,
                "search_date_from":1935,
                "search_date_to":1950,
                "color_type_ids":[1,2],
                "scale_from":0,
                "scale_to":99999999,
                "lon_min":TARGET["lng"]-pad,
                "lon_max":TARGET["lng"]+pad,
                "lat_min":TARGET["lat"]-pad,
                "lat_max":TARGET["lat"]+pad,
            }
            direct_url=f"{GSI_API}?{urllib.parse.urlencode(params,doseq=True)}"
            response=await context.request.get(
                direct_url,
                headers={"Referer":GSI_PAGE,"Accept":"application/json"},
                timeout=120_000,
                fail_on_status_code=False,
            )
            if response.status!=200:
                api_payloads.append({"url":direct_url,"status":response.status,"payload":None})
                break
            payload=await response.json()
            api_payloads.append({"url":direct_url,"status":response.status,"payload":payload})
            results=payload.get("results") or []
            rows.extend(results)
            ids.extend(int(x["specification_id"]) for x in results if x.get("specification_id") not in (None,""))
            resultset=payload.get("resultset") or {}
            count=int(resultset.get("count") or len(results))
            total=int(resultset.get("total_count") or len(results))
            offset += count
            if count==0 or offset>=total:
                break
        ids=sorted(set(ids)); metadata=[]
        def point_in_poly(lon,lat,corners):
            inside=False; pts=corners+[corners[0]]
            for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
                if (y1>lat)!=(y2>lat):
                    xc=(x2-x1)*(lat-y1)/(y2-y1)+x1
                    if lon<xc: inside=not inside
            return inside
        def hav(lon1,lat1,lon2,lat2):
            r=6371008.8;p1=math.radians(lat1);p2=math.radians(lat2);dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1);a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*r*math.asin(math.sqrt(a))
        for pid in ids:
            resp=await context.request.get(f"{GSI_API}/{pid}",headers={"Referer":GSI_PAGE,"Accept":"application/json"},timeout=30_000,fail_on_status_code=False)
            if resp.status!=200: continue
            try: result=(await resp.json()).get("results") or {}
            except Exception: continue
            if not result: continue
            result["apiPhotoId"]=pid
            corners=[result.get("geom_image_left_top_pos"),result.get("geom_image_right_top_pos"),result.get("geom_image_right_bottom_pos"),result.get("geom_image_left_bottom_pos")]
            corners=[c for c in corners if isinstance(c,list) and len(c)==2]
            result["containsProxyPoint"]=len(corners)==4 and point_in_poly(TARGET["lng"],TARGET["lat"],corners)
            center=result.get("geom_center_pos") or [None,None]
            if len(center)==2 and all(isinstance(v,(int,float)) for v in center): result["centerDistanceM"]=hav(TARGET["lng"],TARGET["lat"],center[0],center[1])
            metadata.append(result)
        metadata.sort(key=lambda r:(not r.get("containsProxyPoint",False),r.get("centerDistanceM",1e99),r.get("search_date","")))
        selected=[r for r in metadata if r.get("containsProxyPoint")][:16] or metadata[:16]
        downloads=[]
        for item in selected:
            rel=item.get("url_image_standard")
            if not rel: continue
            url=urljoin(GSI_IMAGE_BASE,rel)
            resp=await context.request.get(url,headers={"Referer":GSI_PAGE,"Accept":"image/*,*/*;q=0.8"},timeout=120_000,fail_on_status_code=False)
            body=await resp.body(); row={"photoId":item.get("apiPhotoId"),"referenceNumber":item.get("reference_number"),"courseNumber":item.get("course_number"),"photoNumber":item.get("photo_number"),"date":item.get("search_date"),"scale":item.get("scale"),"containsProxyPoint":item.get("containsProxyPoint"),"url":url,"status":resp.status,"bytes":len(body)}
            if resp.status==200 and body[:3]==b"\xff\xd8\xff":
                name=re.sub(r"[^A-Za-z0-9._-]+","_",f"{item.get('reference_number')}-{item.get('course_number')}-{item.get('photo_number')}_id{item.get('apiPhotoId')}_400dpi.jpg")
                path=images/name;path.write_bytes(body);row["savedAs"]=str(path.relative_to(folder));row["sha256"]=hashlib.sha256(body).hexdigest()
            downloads.append(row)
        (folder/"photo-metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
        (folder/"downloads.json").write_text(json.dumps(downloads,ensure_ascii=False,indent=2),encoding="utf-8")
        report["gsi"]={"searchMethod":"public_photo_api_bbox_1935_1950","resultRowCount":len(rows),"metadataCount":len(metadata),"coveringPhotoCount":sum(1 for r in metadata if r.get("containsProxyPoint")),"selectedPhotoIds":[r.get("apiPhotoId") for r in selected],"downloadedCount":sum(1 for d in downloads if d.get("savedAs"))}
        await context.close(); await browser.close()
    return report


async def main() -> None:
    official = acquire_official_archaeology()
    visual = await capture_rumsey_and_gsi()
    summary = {
        "target": TARGET,
        "officialArchaeology": official,
        "visualSources": visual,
        "qualityRule": "All extents and map-derived hypotheses remain research review only, scoringEffect=none, verifiedHistoricalSitePolygonCountEffect=0.",
        "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT/"SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"SHA256SUMS.txt").open("w",encoding="utf-8") as f:
        for p in sorted(OUT.rglob("*")):
            if p.is_file() and p.name!="SHA256SUMS.txt": f.write(f"{sha256(p)}  {p.relative_to(OUT)}\n")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    asyncio.run(main())
