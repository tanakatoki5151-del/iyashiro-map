#!/usr/bin/env python3
"""V10 B41 address representative-point authority audit.

Cross-checks frozen representative points against GSI address search and the official
PLATEAU coordinate catalog. This is a diagnostic only. No point or geometry is promoted
or replaced automatically.
"""
from __future__ import annotations
import hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
import requests
from pyproj import CRS, Transformer

OUT=Path('out-b41-address-point-authority-v1')
GSI='https://msearch.gsi.go.jp/address-search/AddressSearch'
PLATEAU='https://api.plateauview.mlit.go.jp'
TARGETS=[
 {'propertyId':'BLDG-6583382c8322','name':'レ・サン・サーンス','address':'東京都目黒区目黒本町5丁目29-12','frozenLat':35.620316,'frozenLon':139.697525,'expectedWard':'目黒区','expectedCityCode':'13110'},
 {'propertyId':'BLDG-edf6c2448f9e','name':'エスティメゾン代沢','address':'東京都世田谷区代沢2丁目39-13','frozenLat':35.659447,'frozenLon':139.673950,'expectedWard':'世田谷区','expectedCityCode':'13112'},
 {'propertyId':'BLDG-4e6c9a14c783','name':'レオパレス駒場東大前','address':'東京都目黒区駒場4丁目3-21','frozenLat':35.660763,'frozenLon':139.680847,'expectedWard':'目黒区','expectedCityCode':'13110'},
 {'propertyId':'BLDG-c404c81c08a5','name':'プリュメゾン駒沢','address':'東京都目黒区東が丘1丁目16-26','frozenLat':35.628464,'frozenLon':139.668793,'expectedWard':'目黒区','expectedCityCode':'13110'},
]

def dist_m(lon1,lat1,lon2,lat2):
 crs=CRS.from_proj4(f'+proj=aeqd +lat_0={lat1} +lon_0={lon1} +datum=WGS84 +units=m +no_defs')
 tr=Transformer.from_crs(4326,crs,always_xy=True)
 x1,y1=tr.transform(lon1,lat1); x2,y2=tr.transform(lon2,lat2)
 return math.hypot(x2-x1,y2-y1)

def plateau_cities(session,lon,lat):
 url=f'{PLATEAU}/datacatalog/citygml/r:{lon},{lat}?types=bldg'
 r=session.get(url,timeout=30); r.raise_for_status(); data=r.json()
 cities=data.get('cities') if isinstance(data,dict) else None
 if cities is None and isinstance(data,list): cities=data
 rows=[]
 for c in cities or []:
  rows.append({'cityCode':str(c.get('cityCode') or c.get('city_code') or ''),'cityName':c.get('cityName') or c.get('city'),'year':c.get('year'),'spec':c.get('spec')})
 return url,rows

def gsi_query(session,address):
 r=session.get(GSI,params={'q':address},timeout=30); r.raise_for_status(); data=r.json()
 rows=[]
 for f in data if isinstance(data,list) else []:
  geom=f.get('geometry') or {}; coords=geom.get('coordinates') or []
  props=f.get('properties') or {}
  if len(coords)>=2:
   rows.append({'title':props.get('title'),'addressCode':props.get('addressCode'),'lon':float(coords[0]),'lat':float(coords[1])})
 return r.url,rows

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 s=requests.Session(); s.headers['User-Agent']='iyashiro-v10-research/1.0'
 items=[]
 for t in TARGETS:
  gsi_url,gsi=gsi_query(s,t['address'])
  frozen_url,frozen_cities=plateau_cities(s,t['frozenLon'],t['frozenLat'])
  gsi_checks=[]
  for g in gsi[:5]:
   purl,pcities=plateau_cities(s,g['lon'],g['lat'])
   gsi_checks.append({**g,'distanceFromFrozenM':round(dist_m(t['frozenLon'],t['frozenLat'],g['lon'],g['lat']),3),'plateauQueryUrl':purl,'plateauCities':pcities,'expectedCityCodePresent':t['expectedCityCode'] in {x['cityCode'] for x in pcities}})
  frozen_codes={x['cityCode'] for x in frozen_cities}
  decision='frozen_point_admin_consistent' if t['expectedCityCode'] in frozen_codes else 'frozen_point_admin_mismatch_review_required'
  items.append({**t,'gsiQueryUrl':gsi_url,'gsiResults':gsi_checks,'frozenPlateauQueryUrl':frozen_url,'frozenPlateauCities':frozen_cities,'frozenExpectedCityCodePresent':t['expectedCityCode'] in frozen_codes,'decision':decision,'formalPointReplacement':False,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none'})
 summary={'schemaVersion':'v10-b41-address-point-authority-v1','generatedAt':datetime.now(timezone.utc).isoformat(),'sources':{'gsi':GSI,'plateau':PLATEAU},'items':items,'policy':{'formalPointReplacement':0,'formalGeometryPromotion':0,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none'}}
 (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# V10 B41 address point authority audit v1','', 'Diagnostic only. No automatic point replacement.','']
 for x in items:
  lines.append(f"## {x['name']} — {x['decision']}")
  lines.append(f"Frozen: {x['frozenLat']},{x['frozenLon']} → PLATEAU cities: {x['frozenPlateauCities']}")
  for g in x['gsiResults']:
   lines.append(f"- GSI {g['title']}: {g['lat']},{g['lon']} Δ={g['distanceFromFrozenM']}m cities={g['plateauCities']} expected={g['expectedCityCodePresent']}")
  lines.append('')
 (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 sums=[]
 for p in sorted(OUT.iterdir()):
  if p.name=='SHA256SUMS.txt' or not p.is_file(): continue
  sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
 (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
 print(json.dumps({'items':[{'propertyId':x['propertyId'],'decision':x['decision'],'gsi':x['gsiResults'][:2],'frozenCities':x['frozenPlateauCities']} for x in items]},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
