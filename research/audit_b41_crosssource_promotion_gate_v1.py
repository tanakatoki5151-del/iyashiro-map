#!/usr/bin/env python3
"""V10 B41 cross-source building polygon promotion gate v1.

Re-runs the geometry-identity evidence using three independent public sources:
1) GSI exact residence-display address search point,
2) MLIT PLATEAU 2025 CityGML building footprint/attributes,
3) OpenStreetMap exact way geometry/version.

The script applies the previously fixed V10 building-polygon contract. It emits
`promotionReady=True` only when every machine-verifiable geometry gate passes.
The master-sheet promotion itself is a separate controlled write.
"""
from __future__ import annotations
import hashlib, json, math, re
from datetime import datetime, timezone
from pathlib import Path
import requests
from lxml import etree
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, Point, mapping
from shapely.ops import transform as shp_transform

OUT=Path('out-b41-crosssource-promotion-gate-v1')
GSI='https://msearch.gsi.go.jp/address-search/AddressSearch'
OSM='https://api.openstreetmap.org/api/0.6'
TARGETS=[
 {
  'propertyId':'BLDG-edf6c2448f9e','name':'エスティメゾン代沢','address':'東京都世田谷区代沢2丁目39-13',
  'expectedLat':35.659447,'expectedLon':139.673950,'expectedStoreys':3,'units':71,'minPrivateM2':25.25,
  'propertyIdentitySources':['https://www.homes.co.jp/archive/b-13691515/u-6075169/','https://suumo.jp/library/tf_13/sc_13112/to_1001629380/'],
  'plateauGmlId':'bldg_31b5fd98-da35-4c9e-9b0e-20a47c2f51c8','plateauBuildingID':'13112-bldg-118096',
  'plateauUrl':'https://assets.cms.plateau.reearth.io/assets/b4/38c131-2e1e-4226-95f7-44f2b12debd7/13112_setagaya-ku_pref_2025_citygml_1_op/udx/bldg/53393593_bldg_6697_op.gml',
  'plateauSha256':'0031349149f89a35d117fe36cdcd770948654d4acba95c823e04457579b16dfe',
  'osmWayId':133633394,
 },
 {
  'propertyId':'BLDG-4e6c9a14c783','name':'レオパレス駒場東大前','address':'東京都目黒区駒場4丁目3-21',
  'expectedLat':35.660763,'expectedLon':139.680847,'expectedStoreys':2,'units':14,'minPrivateM2':19.87,
  'propertyIdentitySources':['https://www.leopalace21.com/word/m/%E7%9B%AE%E9%BB%92%E5%8C%BA%E3%80%80%E8%B3%83%E8%B2%B8%E3%80%80%E3%83%AC%E3%82%AA%E3%83%91%E3%83%AC%E3%82%B9/','https://www.leopalace21.com/app/searchCondition/detail/r/0000096636101.html'],
  'plateauGmlId':'bldg_eea5678b-c018-44ba-bc6c-56b241eee276','plateauBuildingID':'13110-bldg-45829',
  'plateauUrl':'https://assets.cms.plateau.reearth.io/assets/c1/5af712-42ee-403a-bad5-f5d82f8b2492/13110_meguro-ku_pref_2025_citygml_1_op/udx/bldg/53393594_bldg_6697_op.gml',
  'plateauSha256':'17c1ad44f0cc932cf537d2547e8c12caf8a25352ce0327c987130a2bbf8d6c56',
  'osmWayId':133340630,
 },
]
GML_ID='{http://www.opengis.net/gml}id'

def lname(tag): return tag.split('}')[-1] if '}' in tag else tag

def epsg_from_srs(s):
 if not s: return None
 m=re.search(r'EPSG(?::|/0/|::)(\d+)',s) or re.search(r'(\d{4,5})$',s)
 return int(m.group(1)) if m else None

def split_coords(text,dim):
 vals=[float(v) for v in text.split()]
 if dim not in (2,3): dim=3 if len(vals)%3==0 else 2
 return [tuple(vals[i:i+dim]) for i in range(0,len(vals)-dim+1,dim)]

def coord_lonlat(x,y,epsg):
 if 30<=x<=40 and 130<=y<=145: return y,x
 if 130<=x<=145 and 30<=y<=40: return x,y
 if epsg:
  try:
   lon,lat=Transformer.from_crs(CRS.from_epsg(epsg),4326,always_xy=True).transform(x,y)
   return lon,lat
  except Exception: pass
 return None

def extract_ring(building):
 preferred=('lod0FootPrint','lod0RoofEdge','GroundSurface')
 containers=[]
 for p in preferred: containers += [x for x in building.iter() if lname(x.tag)==p]
 containers.append(building)
 for c in containers:
  for pos in c.iter():
   if lname(pos.tag)!='posList' or not pos.text: continue
   srs=pos.get('srsName'); q=pos.getparent()
   while not srs and q is not None: srs=q.get('srsName'); q=q.getparent()
   dimtxt=pos.get('srsDimension'); dim=int(dimtxt) if dimtxt and dimtxt.isdigit() else None
   ll=[]
   for xyz in split_coords(pos.text,dim):
    p=coord_lonlat(xyz[0],xyz[1],epsg_from_srs(srs))
    if p: ll.append(p)
   if len(ll)>=4:
    if ll[0]!=ll[-1]: ll.append(ll[0])
    poly=Polygon(ll)
    if poly.is_valid and not poly.is_empty and poly.area>0: return poly
 return None

def first_text(building,name):
 for x in building.iter():
  if lname(x.tag)==name and x.text and x.text.strip(): return x.text.strip()
 return None

def locality(building):
 vals=[]
 for x in building.iter():
  if lname(x.tag)=='LocalityName' and x.text and x.text.strip(): vals.append(' '.join(x.text.split()))
 return vals

def local_proj(lon,lat):
 crs=CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs')
 return Transformer.from_crs(4326,crs,always_xy=True).transform

def gsi(session,address):
 r=session.get(GSI,params={'q':address},timeout=30); r.raise_for_status(); data=r.json()
 if not data: raise RuntimeError(f'GSI no result: {address}')
 f=data[0]; lon,lat=f['geometry']['coordinates'][:2]
 return {'queryUrl':r.url,'title':f.get('properties',{}).get('title'),'lon':float(lon),'lat':float(lat)}

def osm_way(session,wayid):
 url=f'{OSM}/way/{wayid}/full.json'; r=session.get(url,timeout=30); r.raise_for_status(); data=r.json()
 nodes={e['id']:(float(e['lon']),float(e['lat'])) for e in data['elements'] if e['type']=='node'}
 way=next(e for e in data['elements'] if e['type']=='way' and e['id']==wayid)
 coords=[nodes[n] for n in way['nodes']]
 if coords[0]!=coords[-1]: coords.append(coords[0])
 poly=Polygon(coords)
 if not poly.is_valid or poly.is_empty: raise RuntimeError(f'OSM invalid polygon {wayid}')
 return poly,{'url':url,'id':wayid,'version':way.get('version'),'timestamp':way.get('timestamp'),'changeset':way.get('changeset'),'tags':way.get('tags',{})}

def plateau(session,t):
 r=session.get(t['plateauUrl'],timeout=90); r.raise_for_status(); blob=r.content
 sha=hashlib.sha256(blob).hexdigest(); root=etree.fromstring(blob)
 target=None; all_buildings=[]
 for b in root.iter():
  if lname(b.tag)!='Building': continue
  p=extract_ring(b)
  if p is None: continue
  row={'gmlId':b.get(GML_ID),'polygon':p,'storeys':first_text(b,'storeysAboveGround'),'height':first_text(b,'measuredHeight'),'locality':locality(b)}
  all_buildings.append(row)
  if row['gmlId']==t['plateauGmlId']: target=row
 if target is None: raise RuntimeError(f"PLATEAU target not found {t['plateauGmlId']}")
 return target,all_buildings,{'url':t['plateauUrl'],'sha256':sha,'expectedSha256':t['plateauSha256'],'integrityMatch':sha==t['plateauSha256'],'bytes':len(blob)}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sess=requests.Session(); sess.headers['User-Agent']='iyashiro-v10-research/1.0'
 items=[]; features=[]
 for t in TARGETS:
  lower=t['units']*t['minPrivateM2']/t['expectedStoreys']
  g=gsi(sess,t['address']); pp,allp,pmeta=plateau(sess,t); op,ometa=osm_way(sess,t['osmWayId'])
  proj=local_proj(g['lon'],g['lat']); gp=Point(*proj(g['lon'],g['lat'])); ppm=shp_transform(proj,pp); opm=shp_transform(proj,op)
  i=ppm.intersection(opm).area; u=ppm.union(opm).area
  iou=i/u if u else 0; overlap_min=i/min(ppm.area,opm.area) if min(ppm.area,opm.area)>0 else 0
  pstoreys=int(pp['storeys']) if pp['storeys'] and pp['storeys'].isdigit() else None
  plausible=[]
  for b in allp:
   bm=shp_transform(proj,b['polygon']); bs=int(b['storeys']) if b['storeys'] and b['storeys'].isdigit() else None
   d=bm.distance(gp)
   if d<=60 and bs==t['expectedStoreys'] and bm.area>=lower*0.98:
    plausible.append({'gmlId':b['gmlId'],'distanceFromGsiM':round(d,3),'areaM2':round(bm.area,2),'storeys':bs,'height':b['height'],'locality':b['locality']})
  plausible.sort(key=lambda x:(x['distanceFromGsiM'],abs(x['areaM2']-ppm.area)))
  target_rank=next((idx+1 for idx,x in enumerate(plausible) if x['gmlId']==t['plateauGmlId']),None)
  checks={
   'propertyIdentityTwoSources':len(t['propertyIdentitySources'])>=2,
   'gsiExactCoordinateMatchesFrozen':abs(g['lon']-t['expectedLon'])<1e-9 and abs(g['lat']-t['expectedLat'])<1e-9,
   'plateauSourceIntegrity':pmeta['integrityMatch'],
   'plateauStoreysMatch':pstoreys==t['expectedStoreys'],
   'plateauAreaPhysical':ppm.area>=lower*0.98,
   'osmAreaPhysical':opm.area>=lower*0.98,
   'plateauNearestPhysicallyPlausible':target_rank==1,
   'gsiNearPlateauFootprint':ppm.distance(gp)<=10.0,
   'gsiNearOsmFootprint':opm.distance(gp)<=10.0,
   'crossSourceIouStrong':iou>=0.85,
   'crossSourceOverlapStrong':overlap_min>=0.95,
   'plateauPolygonIntegrity':pp.is_valid and pp.geom_type=='Polygon',
   'osmPolygonIntegrity':op.is_valid and op.geom_type=='Polygon',
   'parcelSeparationDeclared':True,
  }
  allpass=all(checks.values())
  item={**t,'minimumCompleteFootprintM2':round(lower,3),'gsi':g,'plateau':{'gmlId':pp['gmlId'],'buildingID':t['plateauBuildingID'],'storeys':pstoreys,'height':pp['height'],'locality':pp['locality'],'areaM2':round(ppm.area,2),'distanceFromGsiM':round(ppm.distance(gp),3),'physicallyPlausibleRankWithin60m':target_rank,'physicallyPlausibleCandidatesWithin60m':plausible,'source':pmeta},'osm':{**ometa,'areaM2':round(opm.area,2),'distanceFromGsiM':round(opm.distance(gp),3)},'crossSource':{'intersectionM2':round(i,2),'iou':round(iou,4),'overlapOfSmaller':round(overlap_min,4),'hausdorffM':round(ppm.hausdorff_distance(opm),3)},'checks':checks,'promotionReady':allpass,'formalPromotionPerformed':False,'policy':{'geometryRole':'building_footprint_not_parcel','scoringEffect':'none_until_master_promotion_and_dryrun','rankingEffect':'none','automaticExclusionEffect':'none'}}
  items.append(item)
  features += [{'type':'Feature','properties':{'propertyId':t['propertyId'],'name':t['name'],'source':'PLATEAU','gmlId':t['plateauGmlId'],'promotionReady':allpass},'geometry':mapping(pp)},{'type':'Feature','properties':{'propertyId':t['propertyId'],'name':t['name'],'source':'OSM','osmWayId':t['osmWayId'],'promotionReady':allpass},'geometry':mapping(op)}]
 summary={'schemaVersion':'v10-b41-crosssource-promotion-gate-v1','generatedAt':datetime.now(timezone.utc).isoformat(),'contract':'V10_BUILDING_POLYGON_PILOT_CONTRACT_v1_20260814','promotionReadyCount':sum(x['promotionReady'] for x in items),'formalPromotionsPerformed':0,'items':items,'policy':{'masterWriteSeparate':True,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none'}}
 (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'crosssource-geometries.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
 md=['# V10 B41 cross-source promotion gate v1','']
 for x in items:
  md += [f"## {x['name']} — promotionReady={x['promotionReady']}",f"- GSI exact: {x['gsi']['title']} @ {x['gsi']['lat']},{x['gsi']['lon']}",f"- PLATEAU: area {x['plateau']['areaM2']}m² / {x['plateau']['storeys']}F / d(GSI) {x['plateau']['distanceFromGsiM']}m / plausible-rank {x['plateau']['physicallyPlausibleRankWithin60m']}",f"- OSM way/{x['osm']['id']}: area {x['osm']['areaM2']}m² / d(GSI) {x['osm']['distanceFromGsiM']}m / version {x['osm']['version']} @ {x['osm']['timestamp']}",f"- PLATEAU↔OSM IoU {x['crossSource']['iou']} / overlap(smaller) {x['crossSource']['overlapOfSmaller']} / Hausdorff {x['crossSource']['hausdorffM']}m",f"- checks: {x['checks']}",'']
 md += ['## Policy','- This action only marks promotion readiness.','- Actual master-sheet promotion and verified-GeoJSON write are a separate step.','- building footprint is never reused as parcel boundary.']
 (OUT/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
 sums=[]
 for p in sorted(OUT.iterdir()):
  if p.name=='SHA256SUMS.txt' or not p.is_file(): continue
  sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
 (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
 print(json.dumps({x['propertyId']:{'ready':x['promotionReady'],'iou':x['crossSource']['iou'],'overlap':x['crossSource']['overlapOfSmaller'],'plateauRank':x['plateau']['physicallyPlausibleRankWithin60m'],'checks':x['checks']} for x in items},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
