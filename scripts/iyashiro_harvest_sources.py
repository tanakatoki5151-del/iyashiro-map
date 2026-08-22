#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, time, zipfile
from pathlib import Path
from typing import Any
import requests

OUT=Path('output'); DL=OUT/'downloads'; EXT=OUT/'extracted'; GJ=OUT/'geojson'; RENDER=OUT/'pdf_renders'
for p in (OUT,DL,EXT,GJ,RENDER): p.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'IyashirochiOfficialClosure/2026-08-22','Accept':'*/*'})
SOURCES={
 'tokyo_current_water':('https://data.storage.data.metro.tokyo.lg.jp/toshiseibi/08_suikei.zip','zip',5_000_000),
 'tokyo_liquefaction_pl':('https://doboku.metro.tokyo.lg.jp/start/03-jyouhou/ekijyouka/shp/PL%E5%88%86%E5%B8%83%E5%9B%B3.zip','zip',10_000),
 'kawasaki_liquefaction_allcity':('https://www.city.kawasaki.jp/601/cmsfiles/contents/0000046/46739/ekijyouka_zensi.pdf','pdf',100_000),
}

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def download(key:str,url:str,kind:str,min_bytes:int)->dict[str,Any]:
 dest=DL/f'{key}.{kind}'; err=None; code=None; ctype=None
 for attempt in range(1,5):
  try:
   with S.get(url,stream=True,timeout=(30,300),allow_redirects=True) as r:
    code=r.status_code; ctype=r.headers.get('content-type'); r.raise_for_status()
    tmp=dest.with_suffix(dest.suffix+'.part')
    with tmp.open('wb') as f:
     for b in r.iter_content(1<<20):
      if b: f.write(b)
    tmp.replace(dest)
   size=dest.stat().st_size
   if size<min_bytes: raise RuntimeError(f'too small: {size}')
   magic=dest.read_bytes()[:8]
   if kind=='zip' and not magic.startswith(b'PK'): raise RuntimeError(f'not zip {magic!r}')
   if kind=='pdf' and not magic.startswith(b'%PDF'): raise RuntimeError(f'not pdf {magic!r}')
   return {'key':key,'url':url,'status':'SUCCESS','http':code,'content_type':ctype,'path':str(dest),'bytes':size,'sha256':sha(dest),'attempts':attempt}
  except Exception as e:
   err=f'{type(e).__name__}: {e}'
   if dest.exists(): dest.unlink()
   time.sleep(min(3*attempt,10))
 return {'key':key,'url':url,'status':'FAILED','http':code,'content_type':ctype,'bytes':0,'error':err,'attempts':4}

def safe_extract(src:Path,dst:Path)->list[str]:
 dst.mkdir(parents=True,exist_ok=True); names=[]
 with zipfile.ZipFile(src) as z:
  for i in z.infolist():
   target=(dst/i.filename).resolve()
   if not str(target).startswith(str(dst.resolve())): raise RuntimeError(i.filename)
   z.extract(i,dst); names.append(i.filename)
 return names

def convert_shapes(key:str,root:Path)->list[dict[str,Any]]:
 import geopandas as gpd
 out=[]
 for shp in sorted(root.rglob('*.shp')):
  rec={'source':key,'shp':str(shp.relative_to(root)),'status':'FAILED'}; gdf=None; last=None; enc_used=None
  for enc in (None,'cp932','shift_jis','utf-8'):
   try:
    gdf=gpd.read_file(shp,**({} if enc is None else {'encoding':enc})); enc_used=enc or 'default'; break
   except Exception as e: last=e
  if gdf is None:
   rec['error']=f'{type(last).__name__}: {last}'; out.append(rec); continue
  try:
   rec.update({'features':len(gdf),'source_crs':str(gdf.crs) if gdf.crs else None,'encoding':enc_used,'geometry_types':sorted(set(map(str,gdf.geom_type.dropna().unique())))})
   if gdf.crs: gdf=gdf.to_crs(4326); rec['output_crs']='EPSG:4326'
   else: rec['output_crs']=None; rec['warning']='CRS missing'
   name=''.join(c if c.isalnum() or c in '._-' else '_' for c in shp.stem) or 'layer'
   dest=GJ/f'{key}__{name}.geojson'; gdf.to_file(dest,driver='GeoJSON',encoding='utf-8')
   rec.update({'status':'SUCCESS','geojson':str(dest),'geojson_sha256':sha(dest)})
  except Exception as e: rec['error']=f'{type(e).__name__}: {e}'
  out.append(rec)
 return out or [{'source':key,'status':'NO_SHAPEFILE'}]

def render_pdf(key:str,p:Path)->dict[str,Any]:
 import fitz
 try:
  d=fitz.open(p); rd=RENDER/key; rd.mkdir(parents=True,exist_ok=True)
  for n in range(min(3,d.page_count)):
   pix=d.load_page(n).get_pixmap(matrix=fitz.Matrix(2,2),alpha=False); pix.save(rd/f'page_{n+1}.png')
  return {'source':key,'status':'SUCCESS','pages':d.page_count,'render_dir':str(rd),'text_chars':sum(len(d.load_page(n).get_text('text')) for n in range(d.page_count))}
 except Exception as e: return {'source':key,'status':'FAILED','error':f'{type(e).__name__}: {e}'}

def main()->None:
 downloads=[]; layers=[]; pdfs=[]
 for key,(url,kind,minb) in SOURCES.items():
  r=download(key,url,kind,minb); downloads.append(r)
  if r['status']!='SUCCESS': continue
  p=Path(r['path'])
  if kind=='zip':
   dst=EXT/key
   try:
    names=safe_extract(p,dst); (dst/'ZIP_MEMBERS.json').write_text(json.dumps(names,ensure_ascii=False,indent=2),encoding='utf-8'); layers+=convert_shapes(key,dst)
   except Exception as e: layers.append({'source':key,'status':'EXTRACT_FAILED','error':f'{type(e).__name__}: {e}'})
  else: pdfs.append(render_pdf(key,p))
 status={'schema':'IYASHIRO_OFFICIAL_SOURCE_HARVEST_v1','generated_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_project_writes':0,'ranking_effect':0,'downloads':downloads,'layers':layers,'pdfs':pdfs}
 status['download_success_count']=sum(x['status']=='SUCCESS' for x in downloads); status['geojson_success_count']=sum(x['status']=='SUCCESS' for x in layers)
 (OUT/'SOURCE_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
