#!/usr/bin/env python3
"""Focused exact-cell audit for Ichibancho archaeological site.

Uses the official Tokyo archaeological map search/detail/WFS interfaces under
their normal public terms flow. The registered site geometry is treated as a
site-level development/archaeology boundary, not as the exact geometry of the
two Yayoi square-moated graves. The decision question is whether the fixed V10
~100m cell intersects the official site geometry, including conservative
10/25/50m site-boundary buffers.
"""
from __future__ import annotations
import asyncio,csv,hashlib,json,re,urllib.parse
from datetime import datetime,timezone
from pathlib import Path
from playwright.async_api import async_playwright
from pyproj import CRS,Transformer
from shapely.geometry import Point,box,mapping,shape
from shapely.ops import transform,unary_union

OUT=Path('out-ichibancho-site-exact-cell-v1')
START='https://tokyo-iseki.metro.tokyo.lg.jp/'
MAP='https://tokyo-iseki.metro.tokyo.lg.jp/map.html'
BASE='https://tokyo-iseki.metro.tokyo.lg.jp/'
MAPSERVER='https://tokyo-iseki.metro.tokyo.lg.jp/cgi-bin/mapserver?map=/var/www/wms/iseki/wms_iseki3.map'
TARGET={'cellId':'g169-281','town':'一番町','lat':35.687833,'lon':139.740293}
LAT_HALF=0.000898/2;LON_HALF=0.001104/2
SRC=CRS.from_epsg(2451);WGS=CRS.from_epsg(4326);METRIC=CRS.from_epsg(6677)
SRC_TO_M=Transformer.from_crs(SRC,METRIC,always_xy=True).transform
WGS_TO_M=Transformer.from_crs(WGS,METRIC,always_xy=True).transform
TO_WGS=Transformer.from_crs(SRC,WGS,always_xy=True).transform
BUFFERS=[0,10,25,50]

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def site_id(row):
 for k in ['id','sid','site_id','objectid','gid']:
  if row.get(k) not in (None,''):return str(row[k])
 s=json.dumps(row,ensure_ascii=False)
 for pat in [r"setmap\(['\"]([^'\"]+)",r"open_data\(['\"]([^'\"]+)",r"sid[=:'\"\s]+([A-Za-z0-9_-]+)"]:
  m=re.search(pat,s)
  if m:return m.group(1)
 return None
async def accept(page):
 await page.goto(START,wait_until='domcontentloaded',timeout=120000);await page.wait_for_timeout(1200)
 for label in ['同意する','同意します','上記の利用条件の全てに同意','はい']:
  loc=page.get_by_text(label,exact=False)
  for i in range(await loc.count()):
   try:
    if await loc.nth(i).is_visible():await loc.nth(i).click(timeout=7000);await page.wait_for_timeout(700);return True
   except:pass
 return False
async def wfs(ctx,sid,typename):
 filt=f'<Filter><PropertyIsEqualTo><PropertyName>id</PropertyName><Literal>{sid}</Literal></PropertyIsEqualTo></Filter>'
 params={'SERVICE':'WFS','REQUEST':'GetFeature','VERSION':'1.1.0','TYPENAME':typename,'OUTPUTFORMAT':'geojson','Filter':filt}
 url=MAPSERVER+'&'+urllib.parse.urlencode(params)
 r=await ctx.request.get(url,headers={'Referer':MAP,'Accept':'application/json,application/geo+json,*/*;q=0.8'},timeout=120000,fail_on_status_code=False)
 b=await r.body();p=OUT/f'wfs-{typename}.geojson';p.write_bytes(b)
 try:d=json.loads(b.decode())
 except:return [],url,r.status
 geoms=[]
 for f in d.get('features',[]) if isinstance(d,dict) else []:
  if f.get('geometry'):
   try:geoms.append(shape(f['geometry']))
   except:pass
 return geoms,url,r.status
async def main():
 OUT.mkdir(parents=True,exist_ok=True)
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(headless=True)
  ctx=await browser.new_context(locale='ja-JP',viewport={'width':1500,'height':1000})
  page=await ctx.new_page();accepted=await accept(page);await page.goto(MAP,wait_until='domcontentloaded',timeout=120000);await page.wait_for_timeout(1000)
  form={'rd_syurui':'遺跡','txtname':'一番町','lst_kushityouson':'千代田区','txttyotyome':'一番町','txtisekino':'','txtsyubetsu':'','txtjidai':''}
  r=await ctx.request.post(urllib.parse.urljoin(BASE,'json2.php'),form=form,headers={'Referer':MAP,'Accept':'application/json,text/javascript,*/*;q=0.01','X-Requested-With':'XMLHttpRequest'},timeout=120000,fail_on_status_code=False)
  body=await r.body();(OUT/'search.json').write_bytes(body)
  try:rows=json.loads(body.decode())
  except:rows=[]
  if not isinstance(rows,list):rows=[]
  chosen=None
  for row in rows:
   s=json.dumps(row,ensure_ascii=False)
   if '一番町遺跡' in s:
    chosen=row;break
  if chosen is None and rows:chosen=rows[0]
  sid=site_id(chosen or {}) if chosen else None
  detail=None;detail_status=None
  if sid:
   dr=await ctx.request.get(urllib.parse.urljoin(BASE,'getdata.php')+'?'+urllib.parse.urlencode({'sid':sid}),headers={'Referer':MAP,'Accept':'application/json,*/*;q=0.8','X-Requested-With':'XMLHttpRequest'},timeout=120000,fail_on_status_code=False)
   db=await dr.body();(OUT/'detail.json').write_bytes(db);detail_status=dr.status
   try:detail=json.loads(db.decode())
   except:detail=None
  geoms=[];wfs_status=[]
  if sid:
   for typename in ['iseki2','isekipt2']:
    gs,u,st=await wfs(ctx,sid,typename);geoms+=gs;wfs_status.append({'typename':typename,'status':st,'url':u,'geometryCount':len(gs)})
  await ctx.close();await browser.close()
 cell_wgs=box(TARGET['lon']-LON_HALF,TARGET['lat']-LAT_HALF,TARGET['lon']+LON_HALF,TARGET['lat']+LAT_HALF)
 cell_m=transform(WGS_TO_M,cell_wgs);center_m=transform(WGS_TO_M,Point(TARGET['lon'],TARGET['lat']))
 union_src=unary_union(geoms) if geoms else None
 if union_src and not union_src.is_empty:
  site_m=transform(SRC_TO_M,union_src);site_wgs=transform(TO_WGS,union_src)
  center_dist=site_m.distance(center_m);cell_dist=site_m.distance(cell_m)
  rows_out=[];features=[]
  for b in BUFFERS:
   gb=site_m.buffer(b) if b else site_m
   rows_out.append({'bufferMeters':b,'intersectsExactCell':gb.intersects(cell_m),'clearanceToExactCellM':round(gb.distance(cell_m),3),'siteCenterDistanceM':round(center_dist,3)})
   features.append({'type':'Feature','properties':{'role':'official_archaeological_site_outer_bound','bufferMeters':b,'exactGraveGeometry':False,'scoringEffect':'none'},'geometry':mapping(transform(Transformer.from_crs(METRIC,WGS,always_xy=True).transform,gb))})
  decision='strong_negative_site_outer_bound' if not any(x['intersectsExactCell'] for x in rows_out) else ('official_site_nonintersect_but_buffer_sensitive' if not rows_out[0]['intersectsExactCell'] else 'official_site_intersects_cell')
  site_bounds=list(site_wgs.bounds)
 else:
  center_dist=cell_dist=None;rows_out=[];features=[];decision='no_official_geometry';site_bounds=None
 summary={
  'version':'v10-ichibancho-site-exact-cell-v1-20260815','generatedAt':datetime.now(timezone.utc).isoformat(),'acceptedTerms':accepted,'target':TARGET,'searchRowCount':len(rows),'selectedSiteId':sid,'selectedSearchRow':chosen,'detailStatus':detail_status,'detail':detail,'wfsStatus':wfs_status,
  'siteBoundsWgs84':site_bounds,'siteToCellCenterDistanceM':round(center_dist,3) if center_dist is not None else None,'siteToExactCellDistanceM':round(cell_dist,3) if cell_dist is not None else None,'bufferTests':rows_out,
  'decision':decision,
  'context':{'report':'一番町遺跡発掘調査報告書, 千代田区文化財調査報告書5, 1994','reportedFeature':'弥生時代 方形周溝墓2基','facilityInference':'report title says construction of tentative Ichibancho comprehensive public facility; current Ikiiki Plaza Ichibancho is at Ichibancho 12 and opened 1995; treated as corroborating context, not geometry source'},
  'policy':{'officialSiteGeometryIsNotExactGraveGeometry':True,'formalGraveGeometryPromotion':False,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none','nextGate':'if site outer-bound clears exact cell with margin, downgrade paid report geometry to provenance completion; otherwise paid/original plan remains decision-relevant'}
 }
 (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'site-outer-bound-review.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,indent=2),encoding='utf-8')
 with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
  for p in sorted(OUT.iterdir()):
   if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{sha(p)}  {p.name}\n')
 print(json.dumps({k:summary[k] for k in ['acceptedTerms','searchRowCount','selectedSiteId','siteToCellCenterDistanceM','siteToExactCellDistanceM','bufferTests','decision','policy']},ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(main())
