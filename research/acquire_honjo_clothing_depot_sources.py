#!/usr/bin/env python3
"""Acquire public evidence for the former Honjo Army Clothing Depot.

Research roles remain separate:
- former military-facility extent,
- mass-death/conflagration area on 1 September 1923,
- memorial/ossuary locations,
- present Yokamicho Park.

Public GSI aerial photos, official municipal/metropolitan/memorial pages, NDL and
Tokyo archives are preserved. Current park geometry or a memorial point never
becomes the former depot boundary by itself.
"""
from __future__ import annotations
import asyncio, hashlib, json, math, re
from pathlib import Path
from urllib.parse import quote, urljoin
from playwright.async_api import async_playwright

OUT=Path('out-honjo-clothing-depot-sources')
QUERIES=['本所被服廠跡','横網町公園','東京都慰霊堂','陸軍被服廠 本所','本所被服廠 震災']
FALLBACK=(139.7981,35.6994)
GSI_API='https://service.gsi.go.jp/map-photos/app/api/photo'
GSI_IMAGE_BASE='https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/'
TARGETS=[
 ('tokyo_memorial','https://tokyoireikyoukai.or.jp/'),
 ('sumida_search','https://www.city.sumida.lg.jp/search.html?q='+quote('本所被服廠 横網町公園')),
 ('tokyo_park_search','https://www.kensetsu.metro.tokyo.lg.jp/search.html?q='+quote('横網町公園 被服廠')),
 ('ndl_search','https://ndlsearch.ndl.go.jp/search?cs=bib&from=0&size=100&q-title='+quote('本所被服廠 陸軍被服廠 横網町公園')),
 ('ndl_digital','https://dl.ndl.go.jp/search/searchResult?searchWord='+quote('本所被服廠')),
 ('tokyo_archives','https://archives.metro.tokyo.lg.jp/'),
]
KEY=re.compile(r'本所被服廠|陸軍被服廠|被服廠跡|横網町公園|横網公園|東京都慰霊堂|震災記念堂|納骨堂|焼死|圧死|大量死|配置図|平面図|敷地|公図|地番|clothing.?depot|army.?clothing|site.?plan|plot.?plan|layout',re.I)

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def pin(lon,lat,corners):
 x,y=lon,lat;inside=False;pts=corners+[corners[0]]
 for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
  if (y1>y)!=(y2>y):
   cross=(x2-x1)*(y-y1)/(y2-y1)+x1
   if x<cross:inside=not inside
 return inside

def hav(a,b,c,d):
 r=6371008.8;p1,p2=math.radians(b),math.radians(d);dp=math.radians(d-b);dl=math.radians(c-a)
 x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 2*r*math.asin(math.sqrt(x))

async def capture(context,label,url):
 page=await context.new_page();network=[];payloads=[];saved=set();errors=[]
 async def on_resp(resp):
  rurl=resp.url;ct=(resp.headers.get('content-type') or '').lower();network.append({'url':rurl,'status':resp.status,'contentType':ct})
  if resp.status!=200 or not (KEY.search(rurl) or any(x in ct for x in ['json','xml','javascript','text/html','text/plain','application/pdf'])):return
  try:body=await resp.body()
  except:return
  if not body or len(body)>80_000_000:return
  digest=hashlib.sha256(body).hexdigest()
  if digest in saved:return
  saved.add(digest);suffix='.bin'
  if 'json' in ct:suffix='.json'
  elif 'xml' in ct:suffix='.xml'
  elif 'javascript' in ct:suffix='.js'
  elif 'html' in ct:suffix='.html'
  elif 'text/plain' in ct:suffix='.txt'
  elif 'pdf' in ct:suffix='.pdf'
  p=OUT/'payloads'/f'{label}_{len(payloads):04d}_{digest[:12]}{suffix}';p.write_bytes(body);payloads.append({'url':rurl,'status':resp.status,'contentType':ct,'savedAs':str(p.relative_to(OUT)),'bytes':len(body),'sha256':digest})
 page.on('response',lambda r:asyncio.create_task(on_resp(r)))
 try:response=await page.goto(url,wait_until='domcontentloaded',timeout=120000);await page.wait_for_timeout(12000)
 except Exception as e:response=None;errors.append(f'goto:{type(e).__name__}:{e}')
 for text in ['同意する','同意します','上記に同意','はい']:
  try:
   loc=page.get_by_text(text,exact=False)
   if await loc.count() and await loc.first.is_visible():await loc.first.click(timeout=5000);await page.wait_for_timeout(2000);break
  except:pass
 # use visible search fields on official top pages
 for q in QUERIES[:3]:
  try:
   els=page.locator('input[type=text],input:not([type]),textarea')
   for i in range(min(await els.count(),20)):
    el=els.nth(i)
    if await el.is_visible():
     ph=((await el.get_attribute('placeholder')) or '')+((await el.get_attribute('aria-label')) or '')
     if any(k in ph for k in ['検索','キーワード','サイト内']):await el.fill(q);await el.press('Enter');await page.wait_for_timeout(5000);break
  except:pass
 try:await page.screenshot(path=str(OUT/f'{label}.png'),full_page=True)
 except Exception as e:errors.append(f'screenshot:{e}')
 try:html=await page.content();body=await page.locator('body').inner_text()
 except:html='';body=''
 (OUT/f'{label}.html').write_text(html,encoding='utf-8',errors='replace');(OUT/f'{label}.txt').write_text(body,encoding='utf-8',errors='replace')
 try:links=await page.locator('a').evaluate_all("els=>els.slice(0,4000).map(a=>({text:(a.innerText||'').trim(),href:a.href||'',title:a.title||''}))")
 except:links=[]
 hits=[]
 for src,text in [('body',body),('html',html),('links',json.dumps(links,ensure_ascii=False))]:
  for m in KEY.finditer(text):
   hits.append({'source':src,'needle':m.group(0),'context':text[max(0,m.start()-600):m.start()+2000]})
   if len(hits)>=400:break
 result={'label':label,'requestedUrl':url,'finalUrl':page.url,'status':response.status if response else None,'title':await page.title(),'links':links,'network':network,'payloads':payloads,'hits':hits,'errors':errors}
 (OUT/f'{label}-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');await page.close();return result

async def main():
 OUT.mkdir(exist_ok=True);(OUT/'payloads').mkdir(exist_ok=True);(OUT/'gsi-images').mkdir(exist_ok=True)
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(headless=True);context=await browser.new_context(locale='ja-JP',viewport={'width':1600,'height':1100})
  geocodes=[];center=None
  for q in QUERIES:
   try:
    rr=await context.request.get('https://msearch.gsi.go.jp/address-search/AddressSearch',params={'q':q},timeout=30000,fail_on_status_code=False);data=await rr.json() if rr.status==200 else [];geocodes.append({'query':q,'status':rr.status,'results':data})
    if data and center is None:
     c=(data[0].get('geometry') or {}).get('coordinates')
     if c and len(c)==2:center=(float(c[0]),float(c[1]))
   except Exception as e:geocodes.append({'query':q,'error':f'{type(e).__name__}:{e}'})
  if center is None:center=FALLBACK
  lon,lat=center;(OUT/'gsi-geocode.json').write_text(json.dumps(geocodes,ensure_ascii=False,indent=2),encoding='utf-8')
  page_url=f'https://service.gsi.go.jp/map-photos/app/map?search=photo&search_date_from=1936&search_date_to=1950#15/{lat}/{lon}'
  page=await context.new_page();api_payloads=[]
  async def on_gsi(resp):
   if '/app/api/' in resp.url and resp.status==200 and 'json' in (resp.headers.get('content-type') or ''):
    try:api_payloads.append({'url':resp.url,'payload':await resp.json()})
    except:pass
  page.on('response',lambda r:asyncio.create_task(on_gsi(r)));await page.goto(page_url,wait_until='domcontentloaded',timeout=120000);await page.wait_for_timeout(12000)
  agree=page.locator('#terms_dialog #agree_btn:visible')
  if await agree.count():await agree.first.click(timeout=10000);await page.wait_for_timeout(2000)
  yf=page.locator('#photo select[aria-label="yearfrom"]');yt=page.locator('#photo select[aria-label="yearto"]');opts=await yf.locator('option').evaluate_all('els=>els.map(e=>e.value).filter(Boolean)');opts2=await yt.locator('option').evaluate_all('els=>els.map(e=>e.value).filter(Boolean)')
  if opts:await yf.select_option(opts[0])
  if '1950' in opts2:await yt.select_option('1950')
  elif opts2:await yt.select_option(opts2[-1])
  try:await page.locator('#plannerSelector').select_option(value='')
  except:pass
  await page.locator('#aerial_maplink').click(timeout=20000);await page.wait_for_timeout(22000);await page.screenshot(path=str(OUT/'gsi-search-results.png'),full_page=True)
  rows=await page.locator('#search_result_pane .ag-center-cols-container .ag-row').evaluate_all("els=>els.map(e=>({rowId:e.getAttribute('row-id'),className:e.className,text:(e.innerText||'').trim()}))");ids=[]
  for row in rows:
   rid=row.get('rowId') or ''
   if rid.isdigit():ids.append(int(rid))
   else:
    m=re.search(r'specid-(\d+)',row.get('className') or '')
    if m:ids.append(int(m.group(1)))
  for item in api_payloads:ids += [int(x) for x in re.findall(r'"(?:specification_id|id)"\s*:\s*(\d+)',json.dumps(item['payload'],ensure_ascii=False))]
  ids=sorted(set(ids));meta=[];errors=[]
  for pid in ids:
   try:
    rr=await context.request.get(f'{GSI_API}/{pid}',headers={'Referer':page_url,'Accept':'application/json'},timeout=30000,fail_on_status_code=False)
    if rr.status!=200:continue
    p=(await rr.json()).get('results') or {};p['apiPhotoId']=pid;corners=[p.get('geom_image_left_top_pos'),p.get('geom_image_right_top_pos'),p.get('geom_image_right_bottom_pos'),p.get('geom_image_left_bottom_pos')];corners=[c for c in corners if isinstance(c,list) and len(c)==2];p['containsProxyPoint']=len(corners)==4 and pin(lon,lat,corners);c=p.get('geom_center_pos') or []
    if len(c)==2:p['centerDistanceM']=hav(lon,lat,c[0],c[1])
    meta.append(p)
   except Exception as e:errors.append({'photoId':pid,'error':f'{type(e).__name__}:{e}'})
  meta.sort(key=lambda p:(not p.get('containsProxyPoint',False),p.get('centerDistanceM',1e99),p.get('search_date','')));selected=[p for p in meta if p.get('containsProxyPoint')][:14] or meta[:10];downloads=[]
  for p in selected:
   rel=p.get('url_image_standard')
   if not rel:continue
   url=urljoin(GSI_IMAGE_BASE,rel);rr=await context.request.get(url,headers={'Referer':page_url,'Accept':'image/*,*/*;q=.8'},timeout=120000,fail_on_status_code=False);body=await rr.body();row={'photoId':p.get('apiPhotoId'),'referenceNumber':p.get('reference_number'),'courseNumber':p.get('course_number'),'photoNumber':p.get('photo_number'),'date':p.get('search_date'),'scale':p.get('scale'),'url':url,'status':rr.status,'bytes':len(body)}
   if rr.status==200 and body[:3]==b'\xff\xd8\xff':
    name=re.sub(r'[^A-Za-z0-9._-]+','_',f"{p.get('reference_number')}-{p.get('course_number')}-{p.get('photo_number')}_id{p.get('apiPhotoId')}_400dpi.jpg");fp=OUT/'gsi-images'/name;fp.write_bytes(body);row['savedAs']=str(fp.relative_to(OUT));row['sha256']=hashlib.sha256(body).hexdigest()
   downloads.append(row)
  for name,data in [('gsi-result-rows.json',rows),('gsi-photo-metadata.json',meta),('gsi-downloads.json',downloads),('gsi-errors.json',errors)]: (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
  await page.close()
  archive=[]
  for label,url in TARGETS:archive.append(await capture(context,label,url))
  (OUT/'archive-results.json').write_text(json.dumps(archive,ensure_ascii=False,indent=2),encoding='utf-8')
  summary={'proxyPoint':[lon,lat],'gsiMetadataCount':len(meta),'gsiCoveringPhotoCount':sum(bool(x.get('containsProxyPoint')) for x in meta),'gsiDownloadedCount':sum('savedAs' in x for x in downloads),'archivePageCount':len(archive),'archiveHitCount':sum(len(x.get('hits',[])) for x in archive),'qualityRule':'Former depot extent, mass-death area, memorial/ossuary locations and present park remain separate. No current park geometry or memorial point creates the former-site boundary or score change.'}
  (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
  with (OUT/'SHA256SUMS.txt').open('w') as f:
   for p in sorted(OUT.rglob('*')):
    if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{sha(p)}  {p.relative_to(OUT)}\n')
  print(json.dumps(summary,ensure_ascii=False,indent=2));await context.close();await browser.close()
if __name__=='__main__':asyncio.run(main())
