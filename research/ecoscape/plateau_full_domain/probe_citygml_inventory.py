#!/usr/bin/env python3
import json,hashlib,requests
from pathlib import Path
URL='https://api.plateauview.mlit.go.jp/datacatalog/citygml/r:139.43,35.30,139.95,35.85'
r=requests.get(URL,timeout=(20,180),headers={'User-Agent':'ECOSCAPE-PLATEAU-E3/1.0'});r.raise_for_status();payload=r.json()
Path('output').mkdir(exist_ok=True);raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode();Path('output/PLATEAU_CITYGML_INVENTORY_RAW.json').write_bytes(raw)
objs=payload if isinstance(payload,list) else (payload.get('cities') or payload.get('results') or [payload])
rows=[]
for city in objs:
 if not isinstance(city,dict):continue
 files=city.get('files') or {};b=files.get('bldg') or files.get('building') or []
 for f in b:
  if not isinstance(f,dict):continue
  rows.append({'cityCode':city.get('cityCode'),'cityName':city.get('cityName'),'year':city.get('year'),'spec':city.get('spec'),'code':f.get('code'),'maxLod':f.get('maxLod'),'url':f.get('url'),'fileSize':int(f.get('fileSize') or 0),'features':int(f.get('features') or 0),'lod0':f.get('lod0'),'lod1':f.get('lod1'),'lod2':f.get('lod2'),'lod3':f.get('lod3'),'lod4':f.get('lod4')})
report={'requestUrl':URL,'httpStatus':r.status_code,'rawBytes':len(raw),'rawSha256':hashlib.sha256(raw).hexdigest(),'cityObjects':len(objs),'buildingFiles':len(rows),'buildingBytes':sum(x['fileSize'] for x in rows),'buildingFeatures':sum(x['features'] for x in rows),'years':sorted({x['year'] for x in rows if x['year'] is not None}),'cityCodes':sorted({str(x['cityCode']) for x in rows if x['cityCode']}),'maxFileBytes':max([x['fileSize'] for x in rows] or [0])}
Path('output/PLATEAU_BUILDING_FILE_INVENTORY.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');Path('output/PLATEAU_CITYGML_INVENTORY_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
