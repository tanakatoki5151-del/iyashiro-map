#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, time
from pathlib import Path
from urllib.parse import quote
import requests

OUT=Path('output/crosslane_repair'); OUT.mkdir(parents=True,exist_ok=True)
DL=OUT/'official_downloads'; DL.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'IyashirochiCrosslaneRepair/2026-08-22','Accept':'*/*'})
ADDRESSES={
 'B10-01':'東京都目黒区東が丘2丁目4-21',
 'B10-02':'東京都目黒区東が丘1丁目18-20',
 'B10-04':'東京都大田区中馬込1丁目5-3',
 'B10-05':'東京都大田区中馬込1丁目5-21',
 'B10-07':'東京都目黒区柿の木坂3丁目5-8',
}
SOURCES={
 'B10-07_bldg':'https://assets.cms.plateau.reearth.io/assets/c1/5af712-42ee-403a-bad5-f5d82f8b2492/13110_meguro-ku_pref_2025_citygml_1_op/udx/bldg/53393553_bldg_6697_op.gml',
 'B10-07_tran':'https://assets.cms.plateau.reearth.io/assets/c1/5af712-42ee-403a-bad5-f5d82f8b2492/13110_meguro-ku_pref_2025_citygml_1_op/udx/tran/53393553_tran_6697_op.gml',
}

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def geocode(case_id,address):
 url='https://msearch.gsi.go.jp/address-search/AddressSearch?q='+quote(address)
 try:
  r=S.get(url,timeout=(20,120)); r.raise_for_status(); data=r.json()
  feats=data if isinstance(data,list) else data.get('features',[])
  if not feats: return {'caseId':case_id,'address':address,'status':'NO_HIT','sourceUrl':url}
  f=feats[0]; coords=(f.get('geometry') or {}).get('coordinates') or []
  return {'caseId':case_id,'address':address,'status':'SUCCESS','lon':coords[0] if len(coords)>1 else None,'lat':coords[1] if len(coords)>1 else None,'title':(f.get('properties') or {}).get('title'),'sourceUrl':url,'rawFeature':f}
 except Exception as e:
  return {'caseId':case_id,'address':address,'status':'FAILED','error':f'{type(e).__name__}: {e}','sourceUrl':url}

def download(key,url):
 p=DL/(key+'.gml')
 try:
  with S.get(url,stream=True,timeout=(30,300)) as r:
   r.raise_for_status()
   with p.open('wb') as f:
    for b in r.iter_content(1<<20):
     if b:f.write(b)
  head=p.read_bytes()[:100].lstrip()
  if not head.startswith(b'<?xml') and b'CityModel' not in head: raise RuntimeError('not CityGML/XML')
  return {'key':key,'status':'SUCCESS','url':url,'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
 except Exception as e:
  if p.exists():p.unlink()
  return {'key':key,'status':'FAILED','url':url,'error':f'{type(e).__name__}: {e}'}

def main():
 geos=[geocode(k,v) for k,v in ADDRESSES.items()]
 (OUT/'FINALIST5_GSI_GEOCODES.json').write_text(json.dumps(geos,ensure_ascii=False,indent=2),encoding='utf-8')
 with (OUT/'FINALIST5_GSI_GEOCODES.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=['caseId','address','status','lon','lat','title','sourceUrl','error'],extrasaction='ignore');w.writeheader();w.writerows(geos)
 downloads=[download(k,v) for k,v in SOURCES.items()]
 status={'schema':'IYASHIRO_GEOCODE_PLATEAU_FETCH_v1','generatedUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'geocodes':geos,'downloads':downloads,'sourceWrites':0,'rankingEffect':0}
 (OUT/'GEOCODE_PLATEAU_FETCH_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'geocodeSuccess':sum(x['status']=='SUCCESS' for x in geos),'downloadSuccess':sum(x['status']=='SUCCESS' for x in downloads)},ensure_ascii=False))
if __name__=='__main__': main()
