#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,gzip,hashlib,io,json,math,re,time,zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from urllib.parse import urlencode
import requests
from pyproj import Transformer
from shapely.geometry import box,shape
from shapely.ops import transform,unary_union
try:
 from shapely.validation import make_valid
except ImportError:
 make_valid=None

GRID_SHA='c8c822568e3313e800906665652e8d2f6d9dbb862d711e13b26e70ec99f03232'
LANDSAT_URL='https://ecoscape-landsat-cell-runner.vercel.app/api/cell'
MOE_URL='https://svr-moej.gisservice.jp/arcgis/rest/services/Hosted/veg2024bk3/FeatureServer/0/query'
MOE_LAYER='https://svr-moej.gisservice.jp/arcgis/rest/services/Hosted/veg2024bk3/FeatureServer/0'
TO_6677=Transformer.from_crs('EPSG:4326','EPSG:6677',always_xy=True).transform
NUM=re.compile(r'-?\d+(?:\.\d+)?')

def cj(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def valid(g):
 if g.is_valid:return g
 return make_valid(g) if make_valid is not None else g.buffer(0)
def grid(path):
 d=json.loads(path.read_text());assert d['sourceFileSha256']==GRID_SHA and d['encoding']=='zlib-row-major-msb0-base64'
 comp=base64.b64decode(d['maskZlibBase64']);assert sha(comp)==d['compressedSha256'];mask=zlib.decompress(comp);assert sha(mask)==d['maskSha256']
 ls=float(d['latitudeStep']);os=float(d['longitudeStep']);out=[]
 for r in range(int(d['rows'])):
  for c in range(int(d['columns'])):
   i=r*int(d['columns'])+c
   if mask[i//8]&(1<<(7-i%8)):
    lat=float(d['originNorth'])-r*ls;lon=float(d['originWest'])+c*os
    out.append({'ordinal':len(out)+1,'cellId':f'g{r}-{c}','row':r,'col':c,'lat':lat,'lon':lon,'west':lon-os/2,'south':lat-ls/2,'east':lon+os/2,'north':lat+ls/2})
 assert len(out)==120662 and out[0]['cellId']==d['firstCellId'] and out[-1]['cellId']==d['lastCellId'] and len({x['cellId'] for x in out})==len(out);return out
def shard(rows,n):
 x=rows[(n-1)*5000:min(n*5000,len(rows))];assert len(x)==(662 if n==25 else 5000);return x
def bbox(x):
 lat,lon=x['lat'],x['lon'];dx=50/(111320*math.cos(math.radians(lat)));dy=50/111320;return lon-dx,lat-dy,lon+dx,lat+dy
def nested(d,p):
 for k in p.split('.'):
  if not isinstance(d,dict):return None
  d=d.get(k)
 return d
def landsat(x,retries=6):
 b=bbox(x);q={'run':f"e3-b81-{x['ordinal']}",'sampleOrder':x['ordinal'],'cellId':x['cellId'],'bbox':','.join(f'{v:.15f}' for v in b)};url=LANDSAT_URL+'?'+urlencode(q);err=''
 for a in range(1,retries+1):
  try:
   r=requests.get(url,timeout=(20,150),headers={'User-Agent':'ECOSCAPE-E3-Landsat/1.0'});r.raise_for_status();p=r.json();s=str(p.get('status'))
   if p.get('cellId')!=x['cellId']:raise RuntimeError('identity mismatch')
   if s not in {'PASS','NO_VALID_CLEAR_PIXEL'}:raise RuntimeError('runner status='+s)
   return {**x,'status':s,'itemId':nested(p,'scene.itemId'),'acquisitionDate':nested(p,'scene.acquisitionDate'),'qualityValidFraction':p.get('qualityValidFraction'),'landValidFraction':p.get('landValidFraction'),'lstMeanC':nested(p,'lstQualityC.mean'),'lstMedianC':nested(p,'lstQualityC.median'),'lstP10C':nested(p,'lstQualityC.p10'),'lstP90C':nested(p,'lstQualityC.p90'),'stUncertaintyMeanK':nested(p,'stUncertaintyK.mean'),'cloudFraction':nested(p,'qaFractions.cloud'),'shadowFraction':nested(p,'qaFractions.shadow'),'waterFraction':nested(p,'qaFractions.water'),'provenanceUrl':p.get('provenanceUrl'),'sourceId':'SRC-ECO-LANDSAT-001','sourceYear':'2024','missingReason':'NO_VALID_CLEAR_PIXEL' if s=='NO_VALID_CLEAR_PIXEL' else '','attempt':a,'scoringEffect':'none'}
  except Exception as e:err=f'{type(e).__name__}: {e}';time.sleep(min(20,0.7*(2**(a-1))))
 return {**x,'status':'ERROR','missingReason':err,'sourceId':'SRC-ECO-LANDSAT-001','sourceYear':'2024','attempt':retries,'scoringEffect':'none'}
def natural(v):
 m=NUM.search(str(v)) if v not in (None,'') else None;return float(m.group(0)) if m else None
def ent(fracs):
 vals=[v for v in fracs if v>0]
 if not vals:return 0.0,0.0
 t=sum(vals);ps=[v/t for v in vals];raw=-sum(p*math.log(p) for p in ps);return raw,raw/math.log(len(ps)) if len(ps)>1 else 0.0
def moe(x,retries=6):
 geom={'xmin':x['west'],'ymin':x['south'],'xmax':x['east'],'ymax':x['north'],'spatialReference':{'wkid':4326}}
 params={'where':'1=1','geometry':json.dumps(geom,separators=(',',':')),'geometryType':'esriGeometryEnvelope','inSR':'4326','spatialRel':'esriSpatialRelIntersects','outFields':'fid,凡例コード,凡例名,植生自然度,植生自然度区分,植生区分,作成年度,地域ブロック','returnGeometry':'true','outSR':'4326','geometryPrecision':'9','returnExceededLimitFeatures':'true','f':'geojson'};err=''
 for a in range(1,retries+1):
  try:
   r=requests.get(MOE_URL,params=params,timeout=(20,120),headers={'User-Agent':'ECOSCAPE-E3-MOE-ExactArea/1.0'});r.raise_for_status();p=r.json()
   if p.get('error'):raise RuntimeError(str(p['error']))
   fs=sorted(p.get('features',[]),key=lambda f:str((f.get('properties') or {}).get('fid','')));cell=transform(TO_6677,box(x['west'],x['south'],x['east'],x['north']));ca=float(cell.area);ints=[];cats={};props={};years=set();warnings=[]
   for f in fs:
    pr=f.get('properties') or {};g=f.get('geometry')
    if not g:continue
    try:
     clip=valid(transform(TO_6677,valid(shape(g))).intersection(cell))
     if clip.is_empty or clip.area<=0.01:continue
    except Exception as ex:warnings.append(f"fid={pr.get('fid')}:{type(ex).__name__}");continue
    key=tuple(str(pr.get(n) or '') for n in ['凡例コード','凡例名','植生自然度','植生自然度区分','植生区分']);ints.append(clip);cats.setdefault(key,[]).append(clip);props[key]=pr
    if pr.get('作成年度') not in (None,''):years.add(str(pr['作成年度']))
   if not ints:
    st='EXPLICIT_NO_INTERSECTION' if not warnings else 'GEOMETRY_REJECTED'
    return {**x,'status':st,'featureCount':len(fs),'coveredFraction':0.0,'uncoveredFraction':1.0,'categoryCount':0,'categoryEntropy':0.0,'categoryEntropyNormalized':0.0,'dominantLegendCode':None,'dominantLegendName':None,'dominantVegetationNaturalness':None,'dominantNaturalnessClass':None,'dominantVegetationClass':None,'dominantFractionOfCovered':None,'naturalnessAreaWeightedMean':None,'sourceYears':sorted(years),'categoryFractions':[],'overlapExcessFraction':0.0,'sourceId':'SRC-ECO-MOE-001','sourceYear':'2024','provenanceUrl':MOE_LAYER,'missingReason':'NO_INTERSECTING_VEGETATION_POLYGON' if st=='EXPLICIT_NO_INTERSECTION' else ';'.join(warnings),'attempt':a,'methodVersion':'ECOSCAPE_MOE_AREA_INTERSECTION_v1','scoringEffect':'none'}
   cov=min(1.0,max(0.0,float(valid(unary_union(ints)).area/ca)));arr=[];cs=0.0;nn=nd=0.0
   for key in sorted(cats):
    area=float(valid(unary_union(cats[key])).area);frac=max(0.0,area/ca);cs+=frac;pr=props[key];nv=natural(pr.get('植生自然度'))
    if nv is not None:nn+=nv*area;nd+=area
    arr.append({'legendCode':key[0] or None,'legendName':key[1] or None,'vegetationNaturalness':key[2] or None,'naturalnessClass':key[3] or None,'vegetationClass':key[4] or None,'cellFraction':frac})
   for c in arr:c['fractionOfCovered']=c['cellFraction']/cs if cs else 0.0
   dom=max(arr,key=lambda c:(c['cellFraction'],str(c['legendCode'])));er,en=ent(c['fractionOfCovered'] for c in arr);st='PASS' if not warnings else 'PASS_WITH_GEOMETRY_WARNINGS'
   return {**x,'status':st,'featureCount':len(fs),'coveredFraction':cov,'uncoveredFraction':max(0.0,1.0-cov),'categoryCount':len(arr),'categoryEntropy':er,'categoryEntropyNormalized':en,'dominantLegendCode':dom['legendCode'],'dominantLegendName':dom['legendName'],'dominantVegetationNaturalness':dom['vegetationNaturalness'],'dominantNaturalnessClass':dom['naturalnessClass'],'dominantVegetationClass':dom['vegetationClass'],'dominantFractionOfCovered':dom['fractionOfCovered'],'naturalnessAreaWeightedMean':nn/nd if nd else None,'sourceYears':sorted(years),'categoryFractions':arr,'overlapExcessFraction':max(0.0,cs-cov),'sourceId':'SRC-ECO-MOE-001','sourceYear':'2024','provenanceUrl':MOE_LAYER,'missingReason':';'.join(warnings),'attempt':a,'methodVersion':'ECOSCAPE_MOE_AREA_INTERSECTION_v1','scoringEffect':'none'}
  except Exception as ex:err=f'{type(ex).__name__}: {ex}';time.sleep(min(20,0.8*(2**(a-1))))
 return {**x,'status':'ERROR','featureCount':0,'sourceId':'SRC-ECO-MOE-001','sourceYear':'2024','provenanceUrl':MOE_LAYER,'missingReason':err,'attempt':retries,'methodVersion':'ECOSCAPE_MOE_AREA_INTERSECTION_v1','scoringEffect':'none'}
def gz_jsonl(rows):
 bio=io.BytesIO()
 with gzip.GzipFile(fileobj=bio,mode='wb',mtime=0) as g:
  for r in rows:g.write(cj(r)+b'\n')
 return bio.getvalue()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',choices=['landsat','moe'],required=True);ap.add_argument('--grid',type=Path,required=True);ap.add_argument('--shard',type=int,required=True);ap.add_argument('--workers',type=int,default=6);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 rows=shard(grid(a.grid),a.shard);fn=landsat if a.source=='landsat' else moe;facts=[]
 with ThreadPoolExecutor(max_workers=a.workers) as ex:
  fut={ex.submit(fn,x):x for x in rows}
  for i,f in enumerate(as_completed(fut),1):facts.append(f.result());print(a.source,a.shard,i,len(rows),facts[-1]['status'],flush=True)
 facts.sort(key=lambda x:x['ordinal']);ids=[x['cellId'] for x in facts];expected=[x['cellId'] for x in rows];counts=Counter(x['status'] for x in facts);errors=counts.get('ERROR',0)+counts.get('GEOMETRY_REJECTED',0)
 ok=len(facts)==len(rows) and ids==expected and len(ids)==len(set(ids)) and errors==0;data=gz_jsonl(facts);fp=a.out/f'{a.source.upper()}_E3_S{a.shard:02d}_FACTS.jsonl.gz';fp.write_bytes(data)
 man={'buildId':f'ecos-e3-b81-{a.source}-full-domain','source':a.source,'shard':a.shard,'expected':len(rows),'actual':len(facts),'firstCellId':ids[0],'lastCellId':ids[-1],'uniqueCells':len(set(ids)),'duplicateCount':len(ids)-len(set(ids)),'silentMissing':len(rows)-len(facts),'statusCounts':dict(counts),'factsSha256':sha(data),'qaPass':ok,'scoringEffect':'none','crossProjectWrites':0};(a.out/f'{a.source.upper()}_E3_S{a.shard:02d}_MANIFEST.json').write_bytes(cj(man));print(json.dumps(man,ensure_ascii=False,indent=2));raise SystemExit(0 if ok else 2)
if __name__=='__main__':main()
