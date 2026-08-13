#!/usr/bin/env python3
"""Scan the official Tokyo archaeological service for V10 top-10 residential cells.

The output is a source-discovery/proximity audit only. Official archaeological
register geometry is a development-review layer, not a historical major-event
boundary and never changes scoring automatically.
"""
from __future__ import annotations

import asyncio, csv, hashlib, json, math, re, urllib.parse
from pathlib import Path

from playwright.async_api import async_playwright
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

OUT=Path('out-top10-tokyo-iseki-v1')
START='https://tokyo-iseki.metro.tokyo.lg.jp/'
MAP='https://tokyo-iseki.metro.tokyo.lg.jp/map.html'
BASE='https://tokyo-iseki.metro.tokyo.lg.jp/'
MAPSERVER='https://tokyo-iseki.metro.tokyo.lg.jp/cgi-bin/mapserver?map=/var/www/wms/iseki/wms_iseki3.map'

# Current V10 representative cell IDs come from the canonical top10 matrix v2.
# Centers for changed representatives are derived from the same fixed ~100m lattice
# used by the canonical exact-position sheet: +1 g-row = -0.000898 latitude,
# +1 g-column = +0.001104 longitude. Unchanged cells cross-check the lattice.
CELLS=[
 {'rank':1,'address':'東京都渋谷区上原二丁目','ward':'渋谷区','town':'上原二丁目','cellId':'g194-226','gridIndex':89854,'lat':35.665375,'lon':139.679559},
 {'rank':2,'address':'東京都渋谷区上原三丁目','ward':'渋谷区','town':'上原三丁目','cellId':'g195-224','gridIndex':90314,'lat':35.664477,'lon':139.677351},
 {'rank':3,'address':'東京都目黒区駒場四丁目','ward':'目黒区','town':'駒場四丁目','cellId':'g199-227','gridIndex':92165,'lat':35.660885,'lon':139.680663},
 {'rank':4,'address':'東京都渋谷区大山町','ward':'渋谷区','town':'大山町','cellId':'g187-221','gridIndex':86615,'lat':35.671663,'lon':139.674038},
 {'rank':5,'address':'東京都目黒区東が丘一丁目','ward':'目黒区','town':'東が丘一丁目','cellId':'g233-217','gridIndex':107863,'lat':35.630340,'lon':139.669621},
 {'rank':6,'address':'東京都世田谷区北沢五丁目','ward':'世田谷区','town':'北沢五丁目','cellId':'g188-216','gridIndex':87072,'lat':35.670765,'lon':139.668517},
 {'rank':7,'address':'東京都世田谷区北沢一丁目','ward':'世田谷区','town':'北沢一丁目','cellId':'g199-219','gridIndex':92157,'lat':35.660885,'lon':139.671830},
 {'rank':8,'address':'東京都目黒区柿の木坂二丁目','ward':'目黒区','town':'柿の木坂二丁目','cellId':'g239-220','gridIndex':110638,'lat':35.624952,'lon':139.672934},
 {'rank':9,'address':'東京都目黒区目黒本町五丁目','ward':'目黒区','town':'目黒本町五丁目','cellId':'g244-243','gridIndex':112971,'lat':35.620460,'lon':139.698332},
 {'rank':10,'address':'東京都千代田区一番町','ward':'千代田区','town':'一番町','cellId':'g169-281','gridIndex':78359,'lat':35.687833,'lon':139.740293},
]
KEYWORDS=['人骨','遺骨','埋葬','墓地','墓','墳墓','周溝墓','土壙墓','火葬','刑場','処刑','供養','焼場']

TO_WGS=Transformer.from_crs('EPSG:2451','EPSG:4326',always_xy=True).transform
TO_METRIC=Transformer.from_crs('EPSG:2451','EPSG:6677',always_xy=True).transform
WGS_TO_METRIC=Transformer.from_crs('EPSG:4326','EPSG:6677',always_xy=True).transform

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def save(name,b):
 p=OUT/name;p.write_bytes(b);return {'file':name,'bytes':len(b),'sha256':sha(b)}
def site_id(row):
 for k in ['id','sid','site_id','objectid','gid']:
  if row.get(k) not in (None,''):return str(row[k])
 s=json.dumps(row,ensure_ascii=False)
 for pat in [r"setmap\(['\"]([^'\"]+)",r"open_data\(['\"]([^'\"]+)",r"sid[=:'\"\s]+([A-Za-z0-9_-]+)"]:
  m=re.search(pat,s)
  if m:return m.group(1)
 return None

def txtblob(*objs):return ' '.join(json.dumps(x,ensure_ascii=False,sort_keys=True) for x in objs if x is not None)

def title_from(row,detail):
 s=txtblob(row,detail)
 for k in ['iseki_name','name','遺跡名','isekimei','iseki_name12']:
  if isinstance(detail,dict) and detail.get(k):return str(detail[k])
  if isinstance(row,dict) and row.get(k):return str(row[k])
 for pat in [r'"(?:name|iseki_name|isekimei)"\s*:\s*"([^"]+)"']:
  m=re.search(pat,s)
  if m:return m.group(1)
 return ''

async def accept(page):
 await page.goto(START,wait_until='domcontentloaded',timeout=120000);await page.wait_for_timeout(1500)
 for label in ['同意する','同意します','上記の利用条件の全てに同意','はい']:
  loc=page.get_by_text(label,exact=False)
  for i in range(await loc.count()):
   try:
    if await loc.nth(i).is_visible():await loc.nth(i).click(timeout=7000);await page.wait_for_timeout(1000);return True
   except:pass
 return False

async def wfs(context,sid,typename,slug):
 filt=f'<Filter><PropertyIsEqualTo><PropertyName>id</PropertyName><Literal>{sid}</Literal></PropertyIsEqualTo></Filter>'
 params={'SERVICE':'WFS','REQUEST':'GetFeature','VERSION':'1.1.0','TYPENAME':typename,'OUTPUTFORMAT':'geojson','Filter':filt}
 url=MAPSERVER+'&'+urllib.parse.urlencode(params)
 r=await context.request.get(url,headers={'Referer':MAP,'Accept':'application/json,application/geo+json,*/*;q=0.8'},timeout=120000,fail_on_status_code=False)
 b=await r.body();save(f'{slug}_wfs_{typename}.geojson',b)
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
 rows=[]; raw_index=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(headless=True)
  ctx=await browser.new_context(locale='ja-JP',viewport={'width':1500,'height':1000})
  page=await ctx.new_page();accepted=await accept(page)
  await page.goto(MAP,wait_until='domcontentloaded',timeout=120000);await page.wait_for_timeout(2000)
  for cell in CELLS:
   form={'rd_syurui':'遺跡','txtname':'','lst_kushityouson':cell['ward'],'txttyotyome':cell['town'],'txtisekino':'','txtsyubetsu':'','txtjidai':''}
   r=await ctx.request.post(urllib.parse.urljoin(BASE,'json2.php'),form=form,headers={'Referer':MAP,'Accept':'application/json,text/javascript,*/*;q=0.01','X-Requested-With':'XMLHttpRequest'},timeout=120000,fail_on_status_code=False)
   b=await r.body();meta=save(f"rank{cell['rank']:02d}_{cell['cellId']}_search.json",b)
   try:found=json.loads(b.decode())
   except:found=[]
   if not isinstance(found,list):found=[]
   raw_index.append({**cell,'searchStatus':r.status,'searchRowCount':len(found),**meta})
   if not found:
    rows.append({**cell,'siteId':'','siteName':'','searchRowCount':0,'distanceM':'','withinApproxCell':'','matchedKeywords':'','officialTownSearch':'no_rows_not_absence','detailStatus':'','geometryStatus':'','interpretation':'official_town_search_no_rows_not_absence','scoringEffect':'none'})
   for j,row in enumerate(found,1):
    sid=site_id(row);detail=None;detail_status='not_requested';detail_meta=None
    if sid:
     dr=await ctx.request.get(urllib.parse.urljoin(BASE,'getdata.php')+'?'+urllib.parse.urlencode({'sid':sid}),headers={'Referer':MAP,'Accept':'application/json,*/*;q=0.8','X-Requested-With':'XMLHttpRequest'},timeout=120000,fail_on_status_code=False)
     db=await dr.body();detail_meta=save(f"rank{cell['rank']:02d}_{cell['cellId']}_site{j:02d}_{sid}_detail.json",db);detail_status=str(dr.status)
     try:detail=json.loads(db.decode())
     except:detail=None
    geoms=[];statuses=[]
    if sid:
     for typename in ['iseki2','isekipt2']:
      gs,u,st=await wfs(ctx,sid,typename,f"rank{cell['rank']:02d}_{cell['cellId']}_site{j:02d}_{sid}");geoms+=gs;statuses.append(f'{typename}:{st}')
    dist=None
    if geoms:
     try:
      metric=transform(TO_METRIC,unary_union(geoms));cx,cy=WGS_TO_METRIC(cell['lon'],cell['lat']);dist=metric.distance(Point(cx,cy))
     except:dist=None
    blob=txtblob(row,detail);hits=[k for k in KEYWORDS if k in blob]
    name=title_from(row,detail)
    rows.append({**cell,'siteId':sid or '','siteName':name,'searchRowCount':len(found),'distanceM':round(dist,1) if dist is not None else '','withinApproxCell':bool(dist is not None and dist<=70.8),'matchedKeywords':' | '.join(hits),'officialTownSearch':'row_returned','detailStatus':detail_status,'geometryStatus':' | '.join(statuses),'interpretation':'official_archaeological_register_proximity_only_not_major_history_boundary','scoringEffect':'none'})
  await ctx.close();await browser.close()
 
 # Write CSV + compact summary. Raw WFS stays inside artifact only.
 fields=list(rows[0].keys()) if rows else []
 with (OUT/'top10-official-archaeology-proximity.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 summary=[]
 for c in CELLS:
  rr=[x for x in rows if x['cellId']==c['cellId']]
  with_kw=[x for x in rr if x.get('matchedKeywords')]
  within=[x for x in rr if x.get('withinApproxCell')]
  summary.append({**c,'returnedSiteRows':sum(1 for x in rr if x.get('siteId')),'keywordRows':len(with_kw),'withinApproxCellRows':len(within),'nearestDistanceM':min([x['distanceM'] for x in rr if isinstance(x.get('distanceM'),(int,float))],default=None),'keywordSites':[{'siteId':x['siteId'],'siteName':x['siteName'],'distanceM':x['distanceM'],'keywords':x['matchedKeywords']} for x in with_kw]})
 S={'version':'top10-tokyo-iseki-v1-20260813','acceptedTerms':accepted,'cellCount':10,'rawSearchIndex':raw_index,'cellSummary':summary,'rules':['official archaeological registry geometry is a development-review/proximity layer, not a major-history boundary','distance <=70.8m is only a center-to-registered-geometry screening test, not proof the feature covers the cell','keyword hits require original excavation report review','no rows/no keyword never means absence','raw official geometry remains inside the research artifact and is not republished','scoringEffect none']}
 (OUT/'SUMMARY.json').write_text(json.dumps(S,ensure_ascii=False,indent=2),encoding='utf-8')
 with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
  for p in sorted(OUT.iterdir()):
   if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
 print(json.dumps({'acceptedTerms':accepted,'rows':len(rows),'summary':summary},ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
