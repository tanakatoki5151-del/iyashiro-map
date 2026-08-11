#!/usr/bin/env python3
"""Acquire public GSI aerial photos covering the Suzugamori execution-ground marker.

The geocoded point is only an imagery-discovery proxy. It is never treated as
the historical execution-ground boundary. The script accepts the displayed GSI
terms, records official metadata and downloads public standard images.
"""
from __future__ import annotations
import asyncio, hashlib, json, math, re
from pathlib import Path
from urllib.parse import urljoin
from playwright.async_api import async_playwright

OUT=Path('out-gsi-suzugamori')
FALLBACK=(139.7370,35.5900)
API_BASE='https://service.gsi.go.jp/map-photos/app/api/photo'
IMAGE_BASE='https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/'

def sha256(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
 return h.hexdigest()

def pin(lon,lat,corners):
 x,y=lon,lat; inside=False; pts=corners+[corners[0]]
 for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
  if (y1>y)!=(y2>y):
   cross=(x2-x1)*(y-y1)/(y2-y1)+x1
   if x<cross: inside=not inside
 return inside

def hav(lon1,lat1,lon2,lat2):
 r=6371008.8; p1,p2=math.radians(lat1),math.radians(lat2); dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
 a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 2*r*math.asin(math.sqrt(a))

async def main():
 OUT.mkdir(exist_ok=True); (OUT/'images').mkdir(exist_ok=True)
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(headless=True)
  context=await browser.new_context(locale='ja-JP',viewport={'width':1600,'height':1100})
  # Resolve public GSI address-search point.
  center=None; geocode=[]
  for q in ['鈴ヶ森刑場跡','東京都品川区南大井2丁目 鈴ヶ森刑場跡','大経寺 品川区']:
   try:
    rr=await context.request.get('https://msearch.gsi.go.jp/address-search/AddressSearch',params={'q':q},timeout=30000,fail_on_status_code=False)
    if rr.status==200:
     data=await rr.json(); geocode.append({'query':q,'results':data})
     if data and not center:
      c=(data[0].get('geometry') or {}).get('coordinates')
      if c and len(c)==2: center=(float(c[0]),float(c[1]))
   except Exception as e: geocode.append({'query':q,'error':f'{type(e).__name__}: {e}'})
  if not center: center=FALLBACK
  lon,lat=center
  page_url=f'https://service.gsi.go.jp/map-photos/app/map?search=photo&search_date_from=1945&search_date_to=1950#15/{lat}/{lon}'
  page=await context.new_page(); api_payloads=[]
  async def on_response(resp):
   if '/app/api/' in resp.url and resp.status==200 and 'json' in (resp.headers.get('content-type') or ''):
    try: api_payloads.append({'url':resp.url,'payload':await resp.json()})
    except: pass
  page.on('response',lambda r:asyncio.create_task(on_response(r)))
  await page.goto(page_url,wait_until='domcontentloaded',timeout=120000); await page.wait_for_timeout(12000)
  agree=page.locator('#terms_dialog #agree_btn:visible')
  if await agree.count(): await agree.first.click(timeout=10000); await page.wait_for_timeout(2000)
  # choose earliest available year, latest 1950 and US military.
  yf=page.locator('#photo select[aria-label="yearfrom"]'); yt=page.locator('#photo select[aria-label="yearto"]')
  opts=await yf.locator('option').evaluate_all('els=>els.map(e=>e.value).filter(Boolean)')
  if opts: await yf.select_option(opts[0])
  opts2=await yt.locator('option').evaluate_all('els=>els.map(e=>e.value).filter(Boolean)')
  if '1950' in opts2: await yt.select_option('1950')
  else: await yt.select_option(opts2[-1])
  try: await page.locator('#plannerSelector').select_option(label='米軍')
  except: pass
  await page.locator('#aerial_maplink').click(timeout=20000); await page.wait_for_timeout(20000)
  await page.screenshot(path=str(OUT/'search-results.png'),full_page=True)
  rows=await page.locator('#search_result_pane .ag-center-cols-container .ag-row').evaluate_all("els=>els.map(e=>({rowId:e.getAttribute('row-id'),className:e.className,text:(e.innerText||'').trim()}))")
  ids=[]
  for row in rows:
   rid=row.get('rowId') or ''
   if rid.isdigit(): ids.append(int(rid))
   else:
    m=re.search(r'specid-(\d+)',row.get('className') or '')
    if m: ids.append(int(m.group(1)))
  for item in api_payloads:
   ids += [int(x) for x in re.findall(r'"(?:specification_id|id)"\s*:\s*(\d+)',json.dumps(item['payload'],ensure_ascii=False))]
  ids=sorted(set(ids)); meta=[]; errors=[]
  for pid in ids:
   try:
    rr=await context.request.get(f'{API_BASE}/{pid}',headers={'Referer':page_url,'Accept':'application/json'},timeout=30000,fail_on_status_code=False)
    if rr.status!=200: continue
    p=(await rr.json()).get('results') or {}; p['apiPhotoId']=pid
    corners=[p.get('geom_image_left_top_pos'),p.get('geom_image_right_top_pos'),p.get('geom_image_right_bottom_pos'),p.get('geom_image_left_bottom_pos')]
    corners=[c for c in corners if isinstance(c,list) and len(c)==2]
    p['containsProxyPoint']=len(corners)==4 and pin(lon,lat,corners)
    c=p.get('geom_center_pos') or []
    if len(c)==2: p['centerDistanceM']=hav(lon,lat,c[0],c[1])
    meta.append(p)
   except Exception as e: errors.append({'photoId':pid,'error':f'{type(e).__name__}: {e}'})
  meta.sort(key=lambda p:(not p.get('containsProxyPoint',False),p.get('centerDistanceM',1e99),p.get('search_date','')))
  selected=[p for p in meta if p.get('containsProxyPoint')][:12] or meta[:8]
  downloads=[]
  for p in selected:
   rel=p.get('url_image_standard')
   if not rel: continue
   url=urljoin(IMAGE_BASE,rel)
   rr=await context.request.get(url,headers={'Referer':page_url,'Accept':'image/*,*/*;q=.8'},timeout=120000,fail_on_status_code=False)
   body=await rr.body(); row={'photoId':p.get('apiPhotoId'),'referenceNumber':p.get('reference_number'),'courseNumber':p.get('course_number'),'photoNumber':p.get('photo_number'),'date':p.get('search_date'),'scale':p.get('scale'),'containsProxyPoint':p.get('containsProxyPoint'),'url':url,'status':rr.status,'bytes':len(body)}
   if rr.status==200 and body[:3]==b'\xff\xd8\xff':
    name=re.sub(r'[^A-Za-z0-9._-]+','_',f"{p.get('reference_number')}-{p.get('course_number')}-{p.get('photo_number')}_id{p.get('apiPhotoId')}_400dpi.jpg")
    fp=OUT/'images'/name; fp.write_bytes(body); row['savedAs']=str(fp.relative_to(OUT)); row['sha256']=hashlib.sha256(body).hexdigest()
   downloads.append(row)
  for name,data in [('geocode.json',geocode),('result-rows.json',rows),('photo-metadata.json',meta),('downloads.json',downloads),('errors.json',errors)]: (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
  with (OUT/'SHA256SUMS.txt').open('w') as f:
   for p in sorted((OUT/'images').glob('*.jpg')): f.write(f'{sha256(p)}  {p.name}\n')
  summary={'proxyPoint':[lon,lat],'proxySource':'GSI address search' if center!=FALLBACK else 'fallback approximate','metadataCount':len(meta),'coveringPhotoCount':sum(bool(p.get('containsProxyPoint')) for p in meta),'selectedPhotoIds':[p.get('apiPhotoId') for p in selected],'downloadedCount':sum('savedAs' in d for d in downloads),'qualityRule':'Proxy point selects imagery only. Boundary requires visible historical features and independent map/cadastral corroboration; no scoring change.'}
  (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False,indent=2))
  await context.close(); await browser.close()

if __name__=='__main__': asyncio.run(main())
