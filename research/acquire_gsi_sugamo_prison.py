#!/usr/bin/env python3
"""Acquire public 1945-1950 GSI aerial photos around Sugamo Prison, fail-closed.

The V10 proxy point g122-262 is used only for photo discovery. A photo is
accepted for download only when its official four-corner footprint contains the
proxy point, or as a small nearest fallback for diagnosis. Imagery alone never
creates a confirmed historical parcel and never changes scoring.
"""
from __future__ import annotations
import asyncio, hashlib, json, math, re
from pathlib import Path
from urllib.parse import urljoin
from playwright.async_api import async_playwright

OUT=Path('out-gsi-sugamo-prison')
LON,LAT=139.719312,35.730054
PAGE=('https://service.gsi.go.jp/map-photos/app/map?search=photo'
      '&search_date_from=1945&search_date_to=1950'
      f'#15/{LAT}/{LON}')
API='https://service.gsi.go.jp/map-photos/app/api/photo'
IMG='https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/'

def inside(lon,lat,c):
    yes=False; pts=c+[c[0]]
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        if (y1>lat)!=(y2>lat):
            xc=(x2-x1)*(lat-y1)/(y2-y1)+x1
            if lon<xc: yes=not yes
    return yes

def dist(lon1,lat1,lon2,lat2):
    r=6371008.8;p1,p2=map(math.radians,(lat1,lat2));dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))

def year_ok(x):
    try:return 1945<=int(str(x)[:4])<=1950
    except:return False

async def main():
    OUT.mkdir(parents=True,exist_ok=True); im=OUT/'images';im.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        b=await pw.chromium.launch(headless=True);ctx=await b.new_context(locale='ja-JP',viewport={'width':1600,'height':1100});p=await ctx.new_page();payloads=[]
        async def capture(r):
            if '/app/api/' in r.url and r.status==200 and 'json' in (r.headers.get('content-type') or ''):
                try:payloads.append(await r.json())
                except:pass
        p.on('response',lambda r:asyncio.create_task(capture(r)))
        await p.goto(PAGE,wait_until='domcontentloaded',timeout=120000);await p.wait_for_timeout(12000)
        agree=p.locator('#terms_dialog #agree_btn:visible')
        if await agree.count():await agree.first.click(timeout=10000);await p.wait_for_timeout(1500)
        await p.locator('#photo select[aria-label="yearfrom"]').select_option('1945')
        await p.locator('#photo select[aria-label="yearto"]').select_option('1950')
        await p.locator('#plannerSelector').select_option(label='米軍')
        await p.locator('#aerial_maplink').click(timeout=20000);await p.wait_for_timeout(20000)
        await p.screenshot(path=str(OUT/'search-results.png'),full_page=True)
        rows=await p.locator('#search_result_pane .ag-center-cols-container .ag-row').evaluate_all("els=>els.map(e=>({rowId:e.getAttribute('row-id'),className:e.className,text:(e.innerText||'').trim()}))")
        ids=[]
        for r in rows:
            rid=r.get('rowId') or ''
            if rid.isdigit():ids.append(int(rid))
            m=re.search(r'specid-(\d+)',r.get('className') or '')
            if m:ids.append(int(m.group(1)))
        for x in payloads:
            t=json.dumps(x,ensure_ascii=False);ids += [int(v) for v in re.findall(r'"(?:specification_id|id)"\s*:\s*(\d+)',t)]
        ids=sorted(set(ids));accepted=[];rejected=[]
        for pid in ids:
            try:
                r=await ctx.request.get(f'{API}/{pid}',headers={'Referer':PAGE,'Accept':'application/json'},timeout=30000,fail_on_status_code=False)
                if r.status!=200:continue
                x=(await r.json()).get('results') or {}
                if not x:continue
                x['apiPhotoId']=pid;c=[x.get('geom_image_left_top_pos'),x.get('geom_image_right_top_pos'),x.get('geom_image_right_bottom_pos'),x.get('geom_image_left_bottom_pos')];c=[v for v in c if isinstance(v,list) and len(v)==2]
                x['containsProxyPoint']=len(c)==4 and inside(LON,LAT,c);cen=x.get('geom_center_pos') or [None,None]
                if len(cen)==2 and all(isinstance(v,(int,float)) for v in cen):x['centerDistanceM']=dist(LON,LAT,cen[0],cen[1])
                if year_ok(x.get('search_date')) and (x['containsProxyPoint'] or x.get('centerDistanceM',1e99)<5000):accepted.append(x)
                else:rejected.append({'photoId':pid,'date':x.get('search_date'),'containsProxyPoint':x['containsProxyPoint'],'centerDistanceM':x.get('centerDistanceM')})
            except Exception:pass
        accepted.sort(key=lambda x:(not x.get('containsProxyPoint'),x.get('centerDistanceM',1e99)))
        (OUT/'photo-metadata.json').write_text(json.dumps(accepted,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'rejected-metadata.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2),encoding='utf-8')
        chosen=[x for x in accepted if x.get('containsProxyPoint')][:12]
        if not chosen:chosen=accepted[:6]
        downloads=[]
        for x in chosen:
            rel=x.get('url_image_standard')
            if not rel:continue
            u=urljoin(IMG,rel);r=await ctx.request.get(u,headers={'Referer':PAGE,'Accept':'image/*,*/*;q=0.8'},timeout=120000,fail_on_status_code=False);body=await r.body();d={'photoId':x.get('apiPhotoId'),'date':x.get('search_date'),'centerDistanceM':x.get('centerDistanceM'),'containsProxyPoint':x.get('containsProxyPoint'),'status':r.status,'bytes':len(body)}
            if r.status==200 and body[:3]==b'\xff\xd8\xff':
                name=re.sub(r'[^A-Za-z0-9._-]+','_',f"{x.get('reference_number')}-{x.get('course_number')}-{x.get('photo_number')}_id{x.get('apiPhotoId')}_400dpi.jpg");f=im/name;f.write_bytes(body);d['savedAs']=str(f.relative_to(OUT));d['sha256']=hashlib.sha256(body).hexdigest()
            downloads.append(d)
        (OUT/'downloads.json').write_text(json.dumps(downloads,ensure_ascii=False,indent=2),encoding='utf-8')
        summary={'proxyPoint':[LON,LAT],'proxyCellId':'g122-262','searchYears':[1945,1950],'planner':'米軍','renderedRows':len(rows),'discoveredIds':len(ids),'acceptedMetadataCount':len(accepted),'coveringPhotoCount':sum(x.get('containsProxyPoint',False) for x in accepted),'downloadedCount':sum(bool(x.get('savedAs')) for x in downloads),'qualityRule':'Proxy point selects imagery only. Facility parcel requires visible perimeter plus independent archival evidence. All imagery scoringEffect=none.'}
        (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2));await p.close();await ctx.close();await b.close()
if __name__=='__main__':asyncio.run(main())
