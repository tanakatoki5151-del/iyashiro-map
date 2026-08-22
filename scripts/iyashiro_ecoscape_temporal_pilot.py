#!/usr/bin/env python3
from __future__ import annotations
import csv, json, time, traceback
from pathlib import Path
import requests

OUT=Path('output/ecoscape_temporal'); OUT.mkdir(parents=True,exist_ok=True)
ZONES=json.loads(r'''[
{"zoneId":"HRZ01642","lat":35.51024838303989,"lon":139.4926659163373,"displayArea":"横浜市緑区長津田町","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ02166","lat":35.45043957360163,"lon":139.55266119515667,"displayArea":"横浜市保土ケ谷区今井町","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ00822","lat":35.609926313872386,"lon":139.5632808856069,"displayArea":"川崎市多摩区枡形六丁目","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ02662","lat":35.36895847235768,"lon":139.51777803017427,"displayArea":"横浜市戸塚区小雀町","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ02842","lat":35.3437202060127,"lon":139.58404220844147,"displayArea":"横浜市栄区上郷町","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ02887","lat":35.32944166505432,"lon":139.59776033177383,"displayArea":"横浜市金沢区朝比奈町","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ00360","lat":35.69431394692264,"lon":139.85292591995042,"displayArea":"江戸川区小松川一丁目","lanes":["RESIDENTIAL","PURE_ENV","TOKYO23"]},{"zoneId":"HRZ02822","lat":35.35060549695983,"lon":139.60632197968135,"displayArea":"横浜市金沢区釜利谷東五丁目","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ01742","lat":35.50356719367589,"lon":139.53145252975312,"displayArea":"横浜市緑区台村町","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ02790","lat":35.360532382903926,"lon":139.60533623454296,"displayArea":"横浜市磯子区氷取沢町","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ02897","lat":35.32401724757456,"lon":139.59551408935687,"displayArea":"横浜市金沢区東朝比奈二丁目","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ02819","lat":35.354641492176526,"lon":139.58208468282103,"displayArea":"横浜市栄区庄戸一丁目","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ02832","lat":35.35258354293927,"lon":139.59011555716137,"displayArea":"横浜市栄区庄戸三丁目","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ02225","lat":35.442014767076614,"lon":139.50916132143823,"displayArea":"横浜市泉区新橋町","lanes":["RESIDENTIAL","PURE_ENV"]},{"zoneId":"HRZ02846","lat":35.34692418253683,"lon":139.63460902411575,"displayArea":"横浜市金沢区柴町","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ01487","lat":35.52819054463324,"lon":139.52831726206978,"displayArea":"横浜市緑区西八朔町","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ02430","lat":35.41694254800974,"lon":139.65980570004848,"displayArea":"横浜市中区本牧三之谷","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ01549","lat":35.51945981554677,"lon":139.64387389537612,"displayArea":"横浜市鶴見区獅子ケ谷三丁目","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ02750","lat":35.36641753503414,"lon":139.61203482481417,"displayArea":"横浜市磯子区上中里町","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ02898","lat":35.32311893639957,"lon":139.6021323433986,"displayArea":"横浜市金沢区東朝比奈一丁目","lanes":["RESIDENTIAL"]},{"zoneId":"HRZ01585","lat":35.509849951057525,"lon":139.51661090281078,"displayArea":"横浜市緑区三保町","lanes":["PURE_ENV"]},{"zoneId":"HRZ01104","lat":35.57606727412167,"lon":139.480251398228,"displayArea":"川崎市麻生区岡上","lanes":["PURE_ENV"]},{"zoneId":"HRZ02490","lat":35.40166206479188,"lon":139.55176483001733,"displayArea":"横浜市戸塚区舞岡町","lanes":["PURE_ENV"]},{"zoneId":"HRZ01021","lat":35.57414919731126,"lon":139.51814950959246,"displayArea":"横浜市青葉区鉄町","lanes":["PURE_ENV"]},{"zoneId":"HRZ02444","lat":35.39938273534544,"lon":139.4858460879439,"displayArea":"横浜市泉区下飯田町","lanes":["PURE_ENV"]},{"zoneId":"HRZ01446","lat":35.52984140926169,"lon":139.5391839503879,"displayArea":"横浜市緑区北八朔町","lanes":["PURE_ENV"]},{"zoneId":"HRZ02191","lat":35.43860279761427,"lon":139.49039756794076,"displayArea":"横浜市泉区和泉町","lanes":["PURE_ENV"]},{"zoneId":"HRZ01459","lat":35.52795349807864,"lon":139.57447288685776,"displayArea":"横浜市都筑区池辺町","lanes":["PURE_ENV"]},{"zoneId":"HRZ02759","lat":35.36572134387352,"lon":139.5982041534111,"displayArea":"横浜市磯子区峰町","lanes":["PURE_ENV"]},{"zoneId":"HRZ01776","lat":35.49624423007822,"lon":139.56485382416412,"displayArea":"横浜市保土ケ谷区上菅田町","lanes":["PURE_ENV"]},{"zoneId":"HRZ00023","lat":35.79460397310199,"lon":139.7713169397486,"displayArea":"足立区古千谷一丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00012","lat":35.799910802984506,"lon":139.77393990879085,"displayArea":"足立区古千谷二丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00059","lat":35.78556952928494,"lon":139.72991300224157,"displayArea":"北区志茂五丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00068","lat":35.78275482093664,"lon":139.88642135834507,"displayArea":"葛飾区東金町八丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00426","lat":35.680646784046,"lon":139.72888237336792,"displayArea":"港区元赤坂二丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00429","lat":35.67584848776983,"lon":139.69900490915524,"displayArea":"渋谷区代々木神園町","lanes":["TOKYO23"]},{"zoneId":"HRZ00394","lat":35.68548384421902,"lon":139.7075477894031,"displayArea":"新宿区内藤町","lanes":["TOKYO23"]},{"zoneId":"HRZ00866","lat":35.607434423284225,"lon":139.6331811208117,"displayArea":"世田谷区上野毛二丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00070","lat":35.78179662234999,"lon":139.74515158630246,"displayArea":"足立区鹿浜二丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00399","lat":35.68618636962511,"lon":139.6379661834395,"displayArea":"杉並区大宮二丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00666","lat":35.63371002515272,"lon":139.60888772593202,"displayArea":"世田谷区大蔵三丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00232","lat":35.73835647165148,"lon":139.59921721474714,"displayArea":"練馬区石神井町五丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00316","lat":35.71598035692897,"lon":139.58827514845837,"displayArea":"杉並区善福寺三丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00509","lat":35.66178224937118,"lon":139.61220046159744,"displayArea":"世田谷区粕谷一丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ01100","lat":35.579137621272004,"lon":139.70642938719126,"displayArea":"大田区池上一丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00144","lat":35.76508803449515,"lon":139.6257274655645,"displayArea":"練馬区光が丘四丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00018","lat":35.79607977003234,"lon":139.64864055391695,"displayArea":"板橋区新河岸一丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00271","lat":35.7270595280872,"lon":139.567846611855,"displayArea":"練馬区関町北三丁目","lanes":["TOKYO23"]},{"zoneId":"HRZ00550","lat":35.65433909963554,"lon":139.59942276688798,"displayArea":"世田谷区上祖師谷三丁目","lanes":["TOKYO23"]}
]''')
BBOX=[min(z['lon'] for z in ZONES)-.01,min(z['lat'] for z in ZONES)-.01,max(z['lon'] for z in ZONES)+.01,max(z['lat'] for z in ZONES)+.01]
S2_SLOTS={'S2_LEAFOFF_2024':'2024-02-15/2024-04-15','S2_LEAFON_2024':'2024-05-15/2024-09-30','S2_LEAFOFF_2025':'2025-02-15/2025-04-15','S2_LEAFON_2025':'2025-05-15/2025-09-30'}
LST_SLOTS={'LST_SUMMER_2024':'2024-06-15/2024-09-15','LST_SUMMER_2025':'2025-06-15/2025-09-15'}
SESSION=requests.Session();SESSION.headers.update({'User-Agent':'IyashirochiECOSCAPE-F17/2026-08-22','Content-Type':'application/json'})

def search_stac(url,collection,dt,cloud=35):
 body={'collections':[collection],'bbox':BBOX,'datetime':dt,'limit':100,'query':{'eo:cloud_cover':{'lt':cloud}}}
 r=SESSION.post(url.rstrip('/')+'/search',json=body,timeout=(30,180));r.raise_for_status();return r.json().get('features',[])

def coverage(item):
 from shapely.geometry import shape,Point
 g=shape(item['geometry']);return sum(g.covers(Point(z['lon'],z['lat'])) for z in ZONES)

def pick(items):
 if not items:return None
 return sorted(items,key=lambda i:(-coverage(i),float(i.get('properties',{}).get('eo:cloud_cover',100)),i.get('properties',{}).get('datetime','')))[0]

def asset(item,*keys):
 assets=item.get('assets',{})
 for k in keys:
  if k in assets:return k,assets[k]
 low={k.lower():k for k in assets}
 for k in keys:
  if k.lower() in low:
   kk=low[k.lower()];return kk,assets[kk]
 return None,None

def sample_assets(urls):
 import rasterio
 from pyproj import Transformer
 out=[]
 with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif,.TIF',GDAL_HTTP_MULTIPLEX='YES'):
  srcs=[rasterio.open(u) for u in urls]
  try:
   tr=Transformer.from_crs('EPSG:4326',srcs[0].crs,always_xy=True);coords=[tr.transform(z['lon'],z['lat']) for z in ZONES];vals=[list(s.sample(coords)) for s in srcs]
   for i,z in enumerate(ZONES):out.append((z,[v[i][0] if len(v[i]) else None for v in vals]))
  finally:
   for s in srcs:s.close()
 return out

def run_s2(slot,dt):
 rec={'slot':slot,'datetime':dt,'status':'FAILED'}
 try:
  it=pick(search_stac('https://earth-search.aws.element84.com/v1','sentinel-2-l2a',dt,40))
  if not it:return rec|{'status':'NO_ITEM'}
  rk,ra=asset(it,'red','B04');nk,na=asset(it,'nir','nir08','B08');sk,sa=asset(it,'scl','SCL')
  if not all((ra,na,sa)):return rec|{'status':'ASSET_KEYS_MISSING','assetKeys':list(it.get('assets',{}))}
  rows=[];invalid={0,1,3,8,9,10,11}
  for z,(red,nir,scl) in sample_assets([ra['href'],na['href'],sa['href']]):
   ok=red not in (None,0) and nir not in (None,0) and scl not in invalid;ndvi=(float(nir)-float(red))/(float(nir)+float(red)) if ok and (float(nir)+float(red)) else None
   rows.append({'zoneId':z['zoneId'],'displayArea':z['displayArea'],'lanes':'|'.join(z['lanes']),'lat':z['lat'],'lon':z['lon'],'slot':slot,'metric':'NDVI','value':ndvi,'status':'PASS' if ndvi is not None else 'INVALID_PIXEL','itemId':it['id'],'acquisitionDate':it.get('properties',{}).get('datetime','')[:10],'cloudCover':it.get('properties',{}).get('eo:cloud_cover'),'coverageCount':coverage(it),'assetKeys':f'{rk}|{nk}|{sk}'})
  return rec|{'status':'SUCCESS','itemId':it['id'],'coverageCount':coverage(it),'cloudCover':it.get('properties',{}).get('eo:cloud_cover'),'rows':rows}
 except Exception as e:return rec|{'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()}

def run_lst(slot,dt):
 rec={'slot':slot,'datetime':dt,'status':'FAILED'}
 try:
  import planetary_computer as pc
  it=pick(search_stac('https://planetarycomputer.microsoft.com/api/stac/v1','landsat-c2-l2',dt,40))
  if not it:return rec|{'status':'NO_ITEM'}
  tk,ta=asset(it,'lwir11','ST_B10','st_b10','thermal');qk,qa=asset(it,'qa_pixel','QA_PIXEL')
  if not ta:return rec|{'status':'ASSET_KEYS_MISSING','assetKeys':list(it.get('assets',{}))}
  urls=[pc.sign_url(ta['href'])]+([pc.sign_url(qa['href'])] if qa else [])
  rb=(ta.get('raster:bands') or ta.get('extra_fields',{}).get('raster:bands') or [{}])[0];scale=float(rb.get('scale',0.00341802));offset=float(rb.get('offset',149.0));rows=[]
  for z,vals in sample_assets(urls):
   raw=vals[0];q=vals[1] if len(vals)>1 else None;bad=False
   if q is not None:q=int(q);bad=bool(q & (1<<3) or q & (1<<4) or q & (1<<5))
   lst=(float(raw)*scale+offset-273.15) if raw not in (None,0) and not bad else None
   rows.append({'zoneId':z['zoneId'],'displayArea':z['displayArea'],'lanes':'|'.join(z['lanes']),'lat':z['lat'],'lon':z['lon'],'slot':slot,'metric':'LST_C','value':lst,'status':'PASS' if lst is not None else 'INVALID_PIXEL','itemId':it['id'],'acquisitionDate':it.get('properties',{}).get('datetime','')[:10],'cloudCover':it.get('properties',{}).get('eo:cloud_cover'),'coverageCount':coverage(it),'assetKeys':f'{tk}|{qk or ""}'})
  return rec|{'status':'SUCCESS','itemId':it['id'],'coverageCount':coverage(it),'cloudCover':it.get('properties',{}).get('eo:cloud_cover'),'rows':rows,'scale':scale,'offset':offset}
 except Exception as e:return rec|{'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()}

def main():
 results=[run_s2(s,d) for s,d in S2_SLOTS.items()]+[run_lst(s,d) for s,d in LST_SLOTS.items()];rows=[]
 for r in results:rows.extend(r.get('rows',[]))
 fields=['zoneId','displayArea','lanes','lat','lon','slot','metric','value','status','itemId','acquisitionDate','cloudCover','coverageCount','assetKeys']
 with (OUT/'ECOSCAPE_F17_TEMPORAL_PILOT_LONG_49ZONES_V1.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 by={z['zoneId']:{'zoneId':z['zoneId'],'displayArea':z['displayArea'],'lanes':'|'.join(z['lanes'])} for z in ZONES}
 for r in rows:
  if r['status']=='PASS':by[r['zoneId']][r['slot']]=r['value']
 wide=[]
 for z in ZONES:
  d=by[z['zoneId']]
  for k in list(S2_SLOTS)+list(LST_SLOTS):d.setdefault(k,None)
  def delta(a,b):return (float(a)-float(b)) if a is not None and b is not None else None
  d['NDVI_LEAFON_MINUS_LEAFOFF_2024']=delta(d['S2_LEAFON_2024'],d['S2_LEAFOFF_2024']);d['NDVI_LEAFON_MINUS_LEAFOFF_2025']=delta(d['S2_LEAFON_2025'],d['S2_LEAFOFF_2025']);d['NDVI_LEAFON_CHANGE_2025_VS_2024']=delta(d['S2_LEAFON_2025'],d['S2_LEAFON_2024']);d['LST_CHANGE_2025_VS_2024']=delta(d['LST_SUMMER_2025'],d['LST_SUMMER_2024']);obs=sum(d[k] is not None for k in list(S2_SLOTS)+list(LST_SLOTS));d['validSlotCount']=obs;d['temporalState']='MULTIYEAR_MULTI_SEASON' if obs>=5 else ('PARTIAL_TEMPORAL' if obs>=2 else 'TEMPORAL_UNKNOWN');wide.append(d)
 with (OUT/'ECOSCAPE_F17_TEMPORAL_PILOT_WIDE_49ZONES_V1.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(wide[0]));w.writeheader();w.writerows(wide)
 compact=[{k:v for k,v in r.items() if k not in ('rows','traceback')} for r in results]
 report={'schema':'ECOSCAPE_F17_TEMPORAL_PILOT_v1','generatedUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'zoneCount':len(ZONES),'slotCount':len(results),'resultStatusCounts':{s:sum(r['status']==s for r in results) for s in sorted(set(r['status'] for r in results))},'passRows':sum(x['status']=='PASS' for x in rows),'wideTemporalStates':{s:sum(x['temporalState']==s for x in wide) for s in sorted(set(x['temporalState'] for x in wide))},'runs':compact,'method':'one representative point per F16 zone; shadow pilot only','canonicalWrite':0,'rankingEffect':0}
 (OUT/'ECOSCAPE_F17_TEMPORAL_PILOT_REPORT_V1.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'ECOSCAPE_F17_TEMPORAL_PILOT_DEBUG_V1.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
