#!/usr/bin/env python3
"""Resolve current OSM geometry of UTokyo Mathematical Sciences Building and
measure it against V10 Komaba-4 target cell g199-227.

The historical SK03 cremation grave was excavated in the Phase-II construction
area of this building. This probe only establishes a modern outer spatial bound;
it does not yet georeference the E5 grid or SK03 itself.
"""
from __future__ import annotations
import hashlib, json, math, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests
from pyproj import CRS, Transformer
from shapely.geometry import Point, box, mapping, shape, LineString, Polygon
from shapely.ops import transform, unary_union

OUT=Path('out-utokyo-math-building-geometry-v1')
ENDPOINTS=['https://overpass.kumi.systems/api/interpreter','https://overpass-api.de/api/interpreter']
BBOX='35.6550,139.6780,35.6645,139.6885'
TARGET={'cellId':'g199-227','town':'駒場四丁目','lat':35.660885,'lon':139.680663}
LAT_HALF=0.000898/2; LON_HALF=0.001104/2
METRIC=CRS.from_epsg(6677); WGS=CRS.from_epsg(4326)
TO_M=Transformer.from_crs(WGS,METRIC,always_xy=True).transform
HEADERS={'User-Agent':'iyashiro-map-v10-komaba-math-building/1.0 public research'}


def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def query():
 return f'''[out:json][timeout:90];(
 way["building"]["name"~"数理科学|Mathematical Sciences"]({BBOX});
 relation["building"]["name"~"数理科学|Mathematical Sciences"]({BBOX});
 way["building"]["operator"~"東京大学|University of Tokyo"]({BBOX});
 way["building"]["addr:housenumber"="8-1"]({BBOX});
);out meta tags center geom;'''

def acquire(q):
 errs=[]
 for ep in ENDPOINTS:
  for attempt in range(3):
   try:
    r=requests.post(ep,data={'data':q},headers=HEADERS,timeout=120);r.raise_for_status();d=r.json()
    return ep,d
   except Exception as e:
    errs.append({'endpoint':ep,'attempt':attempt+1,'error':str(e)});time.sleep(2**attempt)
 raise RuntimeError(json.dumps(errs,ensure_ascii=False))

def geom(e:dict[str,Any]):
 if e.get('type')=='way':
  coords=[[float(p['lon']),float(p['lat'])] for p in e.get('geometry') or [] if 'lon' in p and 'lat' in p]
  if len(coords)>=4 and coords[0]==coords[-1]: return Polygon(coords)
  if len(coords)>=2:return LineString(coords)
 return None

def score_name(tags):
 s=' '.join(str(tags.get(k,'')) for k in ['name','name:ja','name:en','official_name'])
 score=0
 if '数理科学研究科棟' in s: score+=100
 if '数理科学' in s: score+=50
 if 'Mathematical Sciences' in s: score+=50
 if '東京大学' in s or 'University of Tokyo' in s: score+=10
 return score

def main():
 OUT.mkdir(parents=True,exist_ok=True);q=query();ep,payload=acquire(q)
 (OUT/'overpass.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 target_point=Point(TARGET['lon'],TARGET['lat']); target_cell=box(TARGET['lon']-LON_HALF,TARGET['lat']-LAT_HALF,TARGET['lon']+LON_HALF,TARGET['lat']+LAT_HALF)
 tp_m=transform(TO_M,target_point);tc_m=transform(TO_M,target_cell)
 candidates=[];features=[]
 for e in payload.get('elements') or []:
  g=geom(e)
  if not g or g.is_empty:continue
  gm=transform(TO_M,g);tags=e.get('tags') or {};center=gm.centroid
  row={
   'osmRef':f"{e.get('type')}/{e.get('id')}", 'osmVersion':e.get('version'),'osmTimestamp':e.get('timestamp'),'tags':tags,'nameScore':score_name(tags),
   'geometryType':g.geom_type,'areaSqm':round(gm.area,2),'distanceToTargetCellM':round(gm.distance(tc_m),3),'distanceToTargetCenterM':round(gm.distance(tp_m),3),'centroidDistanceToTargetCenterM':round(center.distance(tp_m),3),'intersectsTargetCell':g.intersects(target_cell),
  }
  candidates.append(row);features.append({'type':'Feature','properties':{**row,'tags':json.dumps(tags,ensure_ascii=False)},'geometry':mapping(g)})
 candidates.sort(key=lambda x:(-x['nameScore'],x['distanceToTargetCellM']))
 selected=candidates[0] if candidates else None
 summary={
  'version':'v10-utokyo-math-building-geometry-v1-20260815','generatedAt':datetime.now(timezone.utc).isoformat(),'endpoint':ep,'querySha256':hashlib.sha256(q.encode()).hexdigest(),'target':TARGET,'candidateCount':len(candidates),'selected':selected,'candidates':candidates,
  'historicalContext':{'report':'UTokyo Graduate School of Mathematical Sciences Phase-II excavation report','constructionAreaSqm':1160,'grid':'8m x 8m; NE corner naming origin','SK03':'Heian-period cremation grave at E5 grid, S6m W2m relative notation in Fig.32'},
  'policy':{'modernBuildingGeometryVerified':bool(selected and selected['nameScore']>=50),'SK03GeometryVerified':False,'formalHistoricalGeometryPromotion':False,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none','nextGate':'georeference report site outline/grid to the selected building footprint; then derive SK03 point/error ellipse and target-cell distance'}
 }
 (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'candidates.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,indent=2),encoding='utf-8')
 with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
  for p in sorted(OUT.iterdir()):
   if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{sha(p)}  {p.name}\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
