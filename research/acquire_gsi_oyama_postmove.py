#!/usr/bin/env python3
"""Acquire post-move GSI aerial photos for the Oyama/Nishihara institution study.

Historical gate: Shibuya chronology records Tokyo Juvenile Training School moving
to old Yoyogi-Oyama in January 1949. A 1978 National Diet record places the
later Tokyo Medical Juvenile Training School in Shibuya Nishihara. The old town
spanned parts of current Oyama and Nishihara, so imagery is used only to locate
facility-change candidates, never to assume the current Oyama representative
cell contains the institution.

This script searches 1949-1956 imagery by Survey Department / GSI planners,
downloads public standard JPEGs, and records official photo footprints. No login
or access-control bypass is used. scoringEffect=none.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

OUT = Path("out-gsi-sugamo-prison")  # compatibility with existing protected workflow artifact path
CENTER_LON = 139.675142
CENTER_LAT = 35.669867
YEAR_FROM, YEAR_TO = 1949, 1956
PLANNERS = ["地理調査所", "国土地理院"]
BASE_PAGE = "https://service.gsi.go.jp/map-photos/app/map?search=photo"
API_BASE = "https://service.gsi.go.jp/map-photos/app/api/photo"
IMAGE_BASE = "https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/"


def point_in_polygon(lon: float, lat: float, corners: list[list[float]]) -> bool:
    x, y = lon, lat
    inside = False
    pts = corners + [corners[0]]
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        if (y1 > y) != (y2 > y):
            xc = (x2-x1)*(y-y1)/(y2-y1)+x1
            if x < xc: inside = not inside
    return inside


def haversine_m(lon1,lat1,lon2,lat2):
    r=6371008.8
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    images=OUT/"images"; images.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        context=await browser.new_context(locale="ja-JP",viewport={"width":1600,"height":1100})
        all_metadata=[]; all_downloads=[]; search_runs=[]; errors=[]

        for planner in PLANNERS:
            page=await context.new_page()
            page_url=(f"{BASE_PAGE}&search_date_from={YEAR_FROM}&search_date_to={YEAR_TO}#15/{CENTER_LAT}/{CENTER_LON}")
            api_payloads=[]
            async def on_response(response):
                if "/app/api/" in response.url and response.status==200 and "json" in (response.headers.get("content-type") or ""):
                    try: api_payloads.append({"url":response.url,"payload":await response.json()})
                    except Exception: pass
            page.on("response", lambda r: asyncio.create_task(on_response(r)))
            await page.goto(page_url,wait_until="domcontentloaded",timeout=120_000)
            await page.wait_for_timeout(10_000)
            agree=page.locator("#terms_dialog #agree_btn:visible")
            if await agree.count():
                await agree.first.click(timeout=10_000); await page.wait_for_timeout(1500)
            await page.locator('#photo select[aria-label="yearfrom"]').select_option(str(YEAR_FROM))
            await page.locator('#photo select[aria-label="yearto"]').select_option(str(YEAR_TO))
            await page.locator("#plannerSelector").select_option(label=planner)
            await page.locator("#aerial_maplink").click(timeout=20_000)
            await page.wait_for_timeout(18_000)
            await page.screenshot(path=str(OUT/f"search-{planner}.png"),full_page=True)
            rows=await page.locator("#search_result_pane .ag-center-cols-container .ag-row").evaluate_all(
                "els=>els.map(e=>({rowId:e.getAttribute('row-id'),className:e.className,text:(e.innerText||'').trim()}))"
            )
            ids=[]
            for row in rows:
                rid=row.get("rowId") or ""
                if rid.isdigit(): ids.append(int(rid))
                else:
                    m=re.search(r"specid-(\d+)",row.get("className") or "")
                    if m: ids.append(int(m.group(1)))
            for item in api_payloads:
                txt=json.dumps(item["payload"],ensure_ascii=False)
                ids.extend(int(x) for x in re.findall(r'"(?:specification_id|id)"\s*:\s*(\d+)',txt))
            html=await page.content(); ids.extend(int(x) for x in re.findall(r"specid-(\d+)",html)); ids=sorted(set(ids))
            search_runs.append({"planner":planner,"renderedRows":len(rows),"discoveredIds":len(ids)})

            planner_meta=[]
            for photo_id in ids:
                try:
                    response=await context.request.get(f"{API_BASE}/{photo_id}",headers={"Referer":page_url,"Accept":"application/json"},timeout=30_000,fail_on_status_code=False)
                    if response.status!=200: continue
                    result=(await response.json()).get("results") or {}
                    if not result: continue
                    result["apiPhotoId"]=photo_id; result["requestedPlanner"]=planner
                    corners=[result.get("geom_image_left_top_pos"),result.get("geom_image_right_top_pos"),result.get("geom_image_right_bottom_pos"),result.get("geom_image_left_bottom_pos")]
                    corners=[c for c in corners if isinstance(c,list) and len(c)==2]
                    result["containsProxyPoint"]=len(corners)==4 and point_in_polygon(CENTER_LON,CENTER_LAT,corners)
                    center=result.get("geom_center_pos") or [None,None]
                    if len(center)==2 and all(isinstance(v,(int,float)) for v in center): result["centerDistanceM"]=haversine_m(CENTER_LON,CENTER_LAT,center[0],center[1])
                    planner_meta.append(result)
                except Exception as exc: errors.append({"planner":planner,"photoId":photo_id,"error":f"{type(exc).__name__}: {exc}"})
            all_metadata.extend(planner_meta)
            await page.close()

        # de-duplicate photo IDs across planner searches
        uniq={}
        for r in all_metadata:
            old=uniq.get(r["apiPhotoId"])
            if old is None or (r.get("containsProxyPoint") and not old.get("containsProxyPoint")): uniq[r["apiPhotoId"]]=r
        metadata=list(uniq.values())
        metadata.sort(key=lambda r:(not r.get("containsProxyPoint",False),r.get("centerDistanceM",1e99),str(r.get("search_date",""))))
        (OUT/"photo-metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
        (OUT/"search-runs.json").write_text(json.dumps(search_runs,ensure_ascii=False,indent=2),encoding="utf-8")
        (OUT/"errors.json").write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding="utf-8")

        selected=[r for r in metadata if r.get("containsProxyPoint")]
        # Ensure multiple dates/courses are represented, then nearest extras.
        if not selected: selected=metadata[:16]
        selected=selected[:24]
        for item in selected:
            rel=item.get("url_image_standard")
            if not rel: continue
            url=urljoin(IMAGE_BASE,rel)
            response=await context.request.get(url,headers={"Referer":BASE_PAGE,"Accept":"image/*,*/*;q=0.8"},timeout=120_000,fail_on_status_code=False)
            body=await response.body()
            row={"photoId":item.get("apiPhotoId"),"referenceNumber":item.get("reference_number"),"courseNumber":item.get("course_number"),"photoNumber":item.get("photo_number"),"date":item.get("search_date"),"planner":item.get("requestedPlanner"),"scale":item.get("scale"),"containsProxyPoint":item.get("containsProxyPoint"),"centerDistanceM":item.get("centerDistanceM"),"status":response.status,"bytes":len(body),"url":url}
            if response.status==200 and body[:3]==b"\xff\xd8\xff":
                name=f"{item.get('search_date')}_{item.get('reference_number')}-{item.get('course_number')}-{item.get('photo_number')}_id{item.get('apiPhotoId')}.jpg"; name=re.sub(r"[^A-Za-z0-9._-]+","_",name)
                path=images/name; path.write_bytes(body); row["savedAs"]=str(path.relative_to(OUT)); row["sha256"]=hashlib.sha256(body).hexdigest()
            all_downloads.append(row)
        (OUT/"downloads.json").write_text(json.dumps(all_downloads,ensure_ascii=False,indent=2),encoding="utf-8")
        with (OUT/"SHA256SUMS.txt").open("w",encoding="utf-8") as f:
            for p in sorted(images.glob("*.jpg")): f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
        dates=sorted(set(str(r.get("search_date")) for r in metadata if r.get("search_date")))
        summary={"studyLabel":"Oyama-Nishihara post-1949 institution-change aerial acquisition","proxyPoint":[CENTER_LON,CENTER_LAT],"proxyCellId":"g187-221","searchYears":[YEAR_FROM,YEAR_TO],"requestedPlanners":PLANNERS,"searchRuns":search_runs,"metadataCount":len(metadata),"coveringPhotoCount":sum(1 for r in metadata if r.get("containsProxyPoint")),"availableDates":dates,"downloadedCount":sum(1 for d in all_downloads if d.get("savedAs")),"historicalGate":"Tokyo Juvenile Training School moved to old Yoyogi-Oyama in Jan 1949; later institution recorded in Shibuya Nishihara.","qualityRule":"Use imagery only to detect facility-change candidates. Exact institution identity/parcel requires archival old-address/layout corroboration. Current Oyama cell is not assumed positive. scoringEffect=none."}
        (OUT/"SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(summary,ensure_ascii=False,indent=2))
        await context.close(); await browser.close()

if __name__=="__main__": asyncio.run(main())
