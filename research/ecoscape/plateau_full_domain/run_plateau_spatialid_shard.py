#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,gzip,hashlib,io,json,math,statistics,time,zlib
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
GRID_SHA='c8c822568e3313e800906665652e8d2f6d9dbb862d711e13b26e70ec99f03232'
API='https://api.plateauview.mlit.go.jp/citygml/spatialid_attributes'; Z=18
METHOD='PLATEAU_SPATIALID_LOD1_BBOX_APPROX_v1'
def cj(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def gz(rows):
 b=io.BytesIO()
 with gzip.GzipFile(fileobj=b,mode='wb',mtime=0) as f:
  for x in rows:f.write(cj(x)+b'\n')
 return b.getvalue()
def grid(path):
 d=json.loads(path.read_text());assert d['sourceFileSha256']==GRID_SHA and d['encoding']=='zlib-row-major-msb0-base64'
 comp=base64.b64decode(d['maskZlibBase64']);assert sha(comp)==d['compressedSha256'];mask=zlib.decompress(comp);assert sha(mask)==d['maskSha256']
 out=[];ls=float(d['latitudeStep']);os=float(d['longitudeStep']);cols=int(d['columns'])
 for r in range(int(d['rows'])):
  for c in range(cols):
   i=r*cols+c
   if mask[i//8]&(1<<(7-i%8)):
    lat=float(d['originNorth'])-r*ls;lon=float(d['originWest'])+c*os
    out.append({'ordinal':len(out)+1,'cellId':f'g{r}-{c}','row':r,'col':c,'lat':lat,'lon':lon,'west':lon-os/2,'south':lat-ls/2,'east':lon+os/2,'north':lat+ls/2})
 assert len(out)==120662 and out[0]['cellId']==d['firstCellId'] and out[-1]['cellId']==d['lastCellId'];return d,out
def shard(rows,n,limit=None):
 x=rows[(n-1)*5000:min(n*5000,len(rows))];assert len(x)==(662 if n==25 else 5000);return x[:limit] if limit else x
def tile(lon,lat):
 n=2**Z;x=int((lon+180)/360*n);q=math.radians(max(-85.05112878,min(85.05112878,lat)));y=int((1-math.asinh(math.tan(q))/math.pi)/2*n);return x,y
def tiles(cell):
 e=1e-12;x0,y1=tile(cell['west']+e,cell['south']+e);x1,y0=tile(cell['east']-e,cell['north']-e);return [(x,y) for x in range(min(x0,x1),max(x0,x1)+1) for y in range(min(y0,y1),max(y0,y1)+1)]
def num(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except:return None
def nested(rows,key):
 if isinstance(rows,list):
  for r in rows:
   if isinstance(r,dict) and r.get(key) not in (None,''):return r[key]
 return None
def year(v):
 if v in (None,''):return None
 for t in str(v).replace('/','-').split('-'):
  if len(t)==4 and t.isdigit() and 1900<=int(t)<=2100:return t
 return None
def area(w,s,e,n):
 return max(0.0,(e-w)*111320*math.cos(math.radians((s+n)/2))*(n-s)*111320) if e>w and n>s else 0.0
def overlap(a,b):
 w=max(a[0],b[0]);s=max(a[1],b[1]);e=min(a[2],b[2]);n=min(a[3],b[3]);return (w,s,e,n) if e>w and n>s else None
def bbox(rec):
 try:
  a=rec['_bbox']['min'];b=rec['_bbox']['max'];q=(num(a['lng']),num(a['lat']),num(b['lng']),num(b['lat']))
  return q if None not in q and q[2]>q[0] and q[3]>q[1] else None
 except:return None
def quant(v,q):
 if not v:return None
 a=sorted(v);p=(len(a)-1)*q;i=math.floor(p);j=math.ceil(p);return a[i] if i==j else a[i]*(j-p)+a[j]*(p-i)
def mode(c):return sorted(c.items(),key=lambda x:(-x[1],x[0]))[0][0] if c else None
def req_once(tile_batch,name,retries):
 sid=[f'{Z}/{x}/{y}' for x,y in tile_batch];sess=requests.Session();sess.headers['User-Agent']='ECOSCAPE-PLATEAU-SPATIALID-FULL/1.0';last={}
 for a in range(1,retries+1):
  t=time.perf_counter()
  try:
   r=sess.get(API,params={'sid':','.join(sid),'type':'bldg','skip_code_list_fetch':'true'},timeout=(20,240));body=r.content
   try:p=r.json()
   except Exception as e:p=None
   last={'batchIndex':name,'attempt':a,'requestedTileCount':len(tile_batch),'firstSid':sid[0],'lastSid':sid[-1],'httpStatus':r.status_code,'elapsedSeconds':time.perf_counter()-t,'bytes':len(body),'sha256':sha(body),'recordCount':len(p) if isinstance(p,list) else None}
   if r.status_code==200 and isinstance(p,list):return sorted([x for x in p if isinstance(x,dict)],key=lambda x:str(x.get('gml:id') or '')), [last], True
  except Exception as e:last={'batchIndex':name,'attempt':a,'requestedTileCount':len(tile_batch),'firstSid':sid[0],'lastSid':sid[-1],'httpStatus':None,'elapsedSeconds':time.perf_counter()-t,'bytes':0,'recordCount':None,'error':f'{type(e).__name__}: {e}'}
  if a<retries:time.sleep(min(12,.8*2**(a-1)))
 return None,[last],False
def fetch(tile_batch,name,retries):
 p,receipts,ok=req_once(tile_batch,name,retries)
 if p is not None:return p,receipts,True
 if len(tile_batch)==1:return [],receipts,False
 m=len(tile_batch)//2;a,ra,oa=fetch(tile_batch[:m],name+'a',retries);b,rb,ob=fetch(tile_batch[m:],name+'b',retries);return sorted(a+b,key=lambda x:str(x.get('gml:id') or '')),receipts+ra+rb,oa and ob
def idxrange(q,d):
 w,s,e,n=q;ls=float(d['latitudeStep']);os=float(d['longitudeStep']);on=float(d['originNorth']);ow=float(d['originWest'])
 r0=max(0,math.ceil((on-ls/2-n)/ls));r1=min(int(d['rows'])-1,math.floor((on+ls/2-s)/ls));c0=max(0,math.ceil((w-ow-os/2)/os));c1=min(int(d['columns'])-1,math.floor((e-ow+os/2)/os));return range(r0,r1+1),range(c0,c1+1)
def newacc():return {'ids':set(),'centers':set(),'known':0.0,'unknown':0.0,'bbox':0.0,'heights':[],'storeys':[],'hids':set(),'rids':set(),'addr':Counter(),'survey':Counter(),'creation':Counter(),'city':Counter()}
def add(rec,d,bycoord,acc,fill):
 bid=str(rec.get('gml:id') or '');q=bbox(rec)
 if not bid or not q:return False
 ba=area(*q)
 if ba<=0:return False
 roof=num(nested(rec.get('uro:buildingDetailAttribute'),'uro:buildingRoofEdgeArea'));h=num(rec.get('bldg:measuredHeight'));st=num(rec.get('bldg:storeysAboveGround'))
 if h is not None and not (0<h<500):h=None
 if st is not None and not (0<st<200):st=None
 sy=year(nested(rec.get('uro:buildingDetailAttribute'),'uro:surveyYear'));cy=year(rec.get('core:creationDate'));cc=nested(rec.get('uro:buildingIDAttribute'),'uro:city_code');ads=rec.get('bldg:address') if isinstance(rec.get('bldg:address'),list) else []
 if roof and roof>0:fill.append(min(1,max(.05,roof/ba)))
 cen=(rec.get('_bbox') or {}).get('center') or {};clat=num(cen.get('lat'));clon=num(cen.get('lng'));touched=False
 rr,cr=idxrange(q,d)
 for r in rr:
  for c in cr:
   cell=bycoord.get((r,c));ov=overlap(q,(cell['west'],cell['south'],cell['east'],cell['north'])) if cell else None
   if not ov:continue
   oa=area(*ov)
   if oa<=.01:continue
   x=acc[cell['cellId']]
   if bid in x['ids']:continue
   touched=True;x['ids'].add(bid);x['bbox']+=oa;ratio=min(1,oa/ba)
   if roof and roof>0:x['known']+=min(oa,roof*ratio);x['rids'].add(bid)
   else:x['unknown']+=oa
   if clat is not None and clon is not None and cell['west']<=clon<cell['east'] and cell['south']<=clat<cell['north']:x['centers'].add(bid)
   if h is not None:x['heights'].append(h);x['hids'].add(bid)
   if st is not None:x['storeys'].append(st)
   for ad in ads:
    if ad:x['addr'][str(ad)]+=1
   if sy:x['survey'][sy]+=1
   if cy:x['creation'][cy]+=1
   if cc:x['city'][str(cc)]+=1
 return touched
def fact(cell,x,tc,fr,shard,contract_sha):
 ca=area(cell['west'],cell['south'],cell['east'],cell['north']);count=len(x['ids']);fp=min(ca,max(0,x['known']+fr*x['unknown']));cov=fp/ca if ca else None;h=x['heights'];st=x['storeys']
 return {'ordinal':cell['ordinal'],'cellId':cell['cellId'],'row':cell['row'],'col':cell['col'],'lat':cell['lat'],'lon':cell['lon'],'status':'PASS' if count else 'EXPLICIT_NO_BUILDINGS','buildingCountIntersecting':count,'buildingCenterCount':len(x['centers']),'buildingCoverageFractionApprox':cov,'openSpaceFractionApprox':1-cov if cov is not None else None,'bboxCoverageFractionUpperBound':min(1,x['bbox']/ca) if ca else None,'roofAreaKnownBuildingFraction':len(x['rids'])/count if count else None,'heightKnownBuildingFraction':len(x['hids'])/count if count else None,'heightMeanM':statistics.fmean(h) if h else None,'heightMedianM':statistics.median(h) if h else None,'heightP90M':quant(h,.9),'heightMaxM':max(h) if h else None,'buildingCountHeight20mPlus':sum(v>=20 for v in h),'buildingCountHeight31mPlus':sum(v>=31 for v in h),'storeysMean':statistics.fmean(st) if st else None,'storeysP90':quant(st,.9),'dominantAddress':mode(x['addr']),'dominantCityCode':mode(x['city']),'dominantSurveyYear':mode(x['survey']),'dominantCreationYear':mode(x['creation']),'spatialTileCount':tc,'bboxFillRatioMedianShard':fr,'coverageMethod':'ROOF_EDGE_AREA_ALLOCATED_PLUS_SHARD_MEDIAN_BBOX_FILL','geometryMethod':'LOD1_ATTRIBUTE_BBOX_INTERSECTION_APPROX','approximationClass':'LEVEL_B_NOT_EXACT_FOOTPRINT','sourceId':'SRC-ECO-PLATEAU-SPATIALID-001','sourceYear':mode(x['creation']),'provenanceUrl':API,'requestTileManifestSha256':contract_sha,'methodVersion':METHOD,'shard':shard,'missingReason':'NO_INTERSECTING_BUILDING_ATTRIBUTE' if not count else '','scoringEffect':'none'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--grid',type=Path,required=True);ap.add_argument('--shard',type=int,required=True);ap.add_argument('--limit',type=int);ap.add_argument('--workers',type=int,default=2);ap.add_argument('--batch-size',type=int,default=16);ap.add_argument('--retries',type=int,default=4);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();assert 1<=a.batch_size<=16 and 1<=a.workers<=8;a.out.mkdir(parents=True,exist_ok=True);started=time.perf_counter();d,allrows=grid(a.grid);cells=shard(allrows,a.shard,a.limit);bycoord={(x['row'],x['col']):x for x in cells};acc={x['cellId']:newacc() for x in cells};ct={};alltiles=set()
 for c in cells:ct[c['cellId']]=tiles(c);alltiles.update(ct[c['cellId']])
 ordered=sorted(alltiles,key=lambda q:(q[1],q[0]));batches=[ordered[i:i+a.batch_size] for i in range(0,len(ordered),a.batch_size)];contract_sha=sha(cj({'zoom':Z,'tiles':ordered}));seen=set();fills=[];receipts=[];fail=0;apirows=0;touch=0;skipbbox=0
 with ThreadPoolExecutor(max_workers=a.workers) as ex:
  for ws in range(0,len(batches),a.workers*2):
   fs=[(i+1,ex.submit(fetch,batches[i],f'B{i+1:05d}',a.retries)) for i in range(ws,min(ws+a.workers*2,len(batches)))]
   for i,f in fs:
    records,rr,ok=f.result();receipts+=rr;fail+=0 if ok else 1;apirows+=len(records)
    for rec in records:
     bid=str(rec.get('gml:id') or '')
     if not bid or bid in seen:continue
     seen.add(bid)
     if not bbox(rec):skipbbox+=1;continue
     if add(rec,d,bycoord,acc,fills):touch+=1
    print(f'PLATEAU shard={a.shard} batch={i}/{len(batches)} records={len(records)} unique={len(seen)} ok={ok}',flush=True)
 receipts.sort(key=lambda x:(str(x.get('batchIndex')),int(x.get('attempt') or 0)));rd=gz(receipts);rp=a.out/f'PLATEAU_SPATIALID_S{a.shard:02d}_REQUEST_RECEIPTS.jsonl.gz';rp.write_bytes(rd);rsha=sha(rd);fr=statistics.median(fills) if fills else .6;facts=[fact(c,acc[c['cellId']],len(ct[c['cellId']]),fr,a.shard,contract_sha) for c in cells];facts.sort(key=lambda x:x['ordinal']);fd=gz(facts);fp=a.out/f'PLATEAU_E3_S{a.shard:02d}_FACTS.jsonl.gz';fp.write_bytes(fd);ids=[x['cellId'] for x in facts];exp=[x['cellId'] for x in cells];cnt=Counter(x['status'] for x in facts);ok=fail==0 and ids==exp and len(ids)==len(set(ids))
 audit={'buildId':'ecos-practical-v2-20260817-b97-plateau-spatialid-full','source':'plateau_spatialid','methodVersion':METHOD,'shard':a.shard,'limit':a.limit,'expectedCells':len(cells),'actualCells':len(facts),'uniqueCells':len(set(ids)),'duplicateCells':len(ids)-len(set(ids)),'canonicalSetAndOrderEqual':ids==exp,'uniqueSpatialTiles':len(ordered),'initialBatchCount':len(batches),'requestReceiptRows':len(receipts),'requestFailures':fail,'apiRecordRows':apirows,'uniqueBuildingIdsReturned':len(seen),'uniqueBuildingsTouchingShard':touch,'skippedBadBbox':skipbbox,'observedRoofFillRatios':len(fills),'bboxFillRatioMedianShard':fr,'bboxFillRatioSource':'SHARD_MEDIAN_OBSERVED' if fills else 'FALLBACK_0_60','statusCounts':dict(cnt),'factsBytes':len(fd),'factsSha256':sha(fd),'requestReceiptsBytes':len(rd),'requestReceiptsSha256':rsha,'requestTileManifestSha256':contract_sha,'apiResponseBytes':sum(int(x.get('bytes') or 0) for x in receipts),'elapsedSeconds':time.perf_counter()-started,'qaPass':ok,'approximationClass':'LEVEL_B_NOT_EXACT_FOOTPRINT','scoringEffect':'none','globalNexusWrites':0,'crossProjectWrites':0};apath=a.out/f'PLATEAU_E3_S{a.shard:02d}_AUDIT.json';apath.write_text(json.dumps(audit,ensure_ascii=False,indent=2));(a.out/'SHA256SUMS.txt').write_text(f'{sha(fd)}  {fp.name}\n{rsha}  {rp.name}\n{sha(apath.read_bytes())}  {apath.name}\n');print(json.dumps(audit,ensure_ascii=False,indent=2));raise SystemExit(0 if ok else 2)
if __name__=='__main__':main()
