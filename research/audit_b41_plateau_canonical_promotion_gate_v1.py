#!/usr/bin/env python3
"""V10 B41 PLATEAU-canonical Building Polygon promotion gate v1.

This is a separate geometry-source contract, not a relaxation of the OSM-canonical gate.
It is intended for targets where OSM appears to map only a building part while official
MLIT PLATEAU CityGML provides a plausible complete LOD0 footprint.

Roles:
- canonical candidate geometry: MLIT PLATEAU 2025 CityGML LOD0 footprint
- authoritative address anchor: GSI residence-display address search point
- independent shape control: OSM partial footprint, required to be almost entirely
  contained by the PLATEAU footprint
- property identity: two independent public sources already frozen in B41 master audit

The script only emits promotionReady; master promotion is a separate write.
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

OUT=Path('out-b41-plateau-canonical-promotion-gate-v1')
GSI='https://msearch.gsi.go.jp/address-search/AddressSearch'
OSM='https://api.openstreetmap.org/api/0.6'
GML_ID='{http://www.opengis.net/gml}id'

TARGETS=[
 {
  'propertyId':'BLDG-6583382c8322','name':'レ・サン・サーンス','address':'東京都目黒区目黒本町5丁目29-12',
  'expectedLat':35.620316,'expectedLon':139.697525,'expectedWardCode':'13110','expectedWard':'目黒区','expectedLocality':'目黒本町五丁目',
  'expectedStoreys':3,'units':29,'minPrivateM2':25.28,
  'propertyIdentitySources':['https://www.mitsui-chintai.co.jp/rf/tatemono/69527','https://www.homes.co.jp/chintai/b-1331530513697/'],
  'plateauGmlId':'bldg_7b54ce02-37b0-4c5d-99e3-24f184f5d7fe','plateauBuildingID':'13110-bldg-1504',
  'plateauUrl':'https://assets.cms.plateau.reearth.io/assets/4b/90d7b7-679a-46d4-a842-7706fec36d40/13109_shinagawa-ku_pref_2025_citygml_1_op/udx/bldg/53393545_bldg_6697_op.gml',
  'plateauSha256':'baa900ffcbfafb213cd74b5f1d2416e5bb1bb50bb8adb4d841b88eb57e5d33a9',
  'osmPartialWayId':694173696,
 },
 {
  'propertyId':'BLDG-c404c81c08a5','name':'プリュメゾン駒沢','address':'東京都目黒区東が丘1丁目16-26',
  'expectedLat':35.628464,'expectedLon':139.668793,'expectedWardCode':'13110','expectedWard':'目黒区','expectedLocality':'東が丘一丁目',
  'expectedStoreys':4,'units':26,'minPrivateM2':18.46,
  'propertyIdentitySources':['https://www.royal-community.co.jp/build-6812226/','https://lifullhomes-index.jp/buildings/b-34401606/'],
  'plateauGmlId':'bldg_958e8009-cbab-4089-b09f-06e45eba935d','plateauBuildingID':'13110-bldg-50639',
  'plateauUrl':'https://assets.cms.plateau.reearth.io/assets/c1/5af712-42ee-403a-bad5-f5d82f8b2492/13110_meguro-ku_pref_2025_citygml_1_op/udx/bldg/53393553_bldg_6697_op.gml',
  'plateauSha256':'1c76b1e9e695a6c0dfd3afe678373d0543f1e328f753bef87fbf9a44ec5e3199',
  'osmPartialWayId':689285630,
 },
]


def lname(tag): return tag.split('}')[-1] if '}' in tag else tag

def epsg_from_srs(s):
    if not s:return None
    m=re.search(r'EPSG(?::|/0/|::)(\d+)',s) or re.search(r'(\d{4,5})$',s)
    return int(m.group(1)) if m else None

def split_coords(text,dim):
    vals=[float(v) for v in text.split()]
    if dim not in (2,3):dim=3 if len(vals)%3==0 else 2
    return [tuple(vals[i:i+dim]) for i in range(0,len(vals)-dim+1,dim)]

def coord_lonlat(x,y,epsg):
    if 30<=x<=40 and 130<=y<=145:return y,x
    if 130<=x<=145 and 30<=y<=40:return x,y
    if epsg:
        try:return Transformer.from_crs(CRS.from_epsg(epsg),4326,always_xy=True).transform(x,y)
        except Exception:pass
    return None

def extract_ring(building):
    containers=[]
    for p in ('lod0FootPrint','lod0RoofEdge','GroundSurface'):
        containers += [x for x in building.iter() if lname(x.tag)==p]
    containers.append(building)
    for c in containers:
        for pos in c.iter():
            if lname(pos.tag)!='posList' or not pos.text:continue
            srs=pos.get('srsName');q=pos.getparent()
            while not srs and q is not None:srs=q.get('srsName');q=q.getparent()
            dimtxt=pos.get('srsDimension');dim=int(dimtxt) if dimtxt and dimtxt.isdigit() else None
            ll=[]
            for xyz in split_coords(pos.text,dim):
                p=coord_lonlat(xyz[0],xyz[1],epsg_from_srs(srs))
                if p:ll.append(p)
            if len(ll)>=4:
                if ll[0]!=ll[-1]:ll.append(ll[0])
                poly=Polygon(ll)
                if poly.is_valid and not poly.is_empty and poly.area>0:return poly
    return None

def first_text(b,name):
    for x in b.iter():
        if lname(x.tag)==name and x.text and x.text.strip():return ' '.join(x.text.split())
    return None

def texts(b,name):
    out=[]
    for x in b.iter():
        if lname(x.tag)==name and x.text and x.text.strip():
            v=' '.join(x.text.split())
            if v not in out:out.append(v)
    return out

def plateau(session,t):
    r=session.get(t['plateauUrl'],timeout=90);r.raise_for_status();blob=r.content
    sha=hashlib.sha256(blob).hexdigest();root=etree.fromstring(blob)
    rows=[];target=None
    for b in root.iter():
        if lname(b.tag)!='Building':continue
        p=extract_ring(b)
        if p is None:continue
        row={'gmlId':b.get(GML_ID),'polygon':p,'storeys':first_text(b,'storeysAboveGround'),'height':first_text(b,'measuredHeight'),'buildingIDs':texts(b,'buildingID'),'localityNames':texts(b,'LocalityName')}
        rows.append(row)
        if row['gmlId']==t['plateauGmlId']:target=row
    if target is None:raise RuntimeError('PLATEAU target not found '+t['plateauGmlId'])
    return target,rows,{'url':t['plateauUrl'],'bytes':len(blob),'sha256':sha,'expectedSha256':t['plateauSha256'],'integrityMatch':sha==t['plateauSha256']}

def gsi(session,address):
    r=session.get(GSI,params={'q':address},timeout=30);r.raise_for_status();data=r.json()
    if not data:raise RuntimeError('GSI no result '+address)
    f=data[0];lon,lat=f['geometry']['coordinates'][:2]
    return {'queryUrl':r.url,'title':f.get('properties',{}).get('title'),'lon':float(lon),'lat':float(lat)}

def osm_way(session,wayid):
    url=f'{OSM}/way/{wayid}/full.json';r=session.get(url,timeout=30);r.raise_for_status();data=r.json()
    nodes={e['id']:(float(e['lon']),float(e['lat'])) for e in data['elements'] if e['type']=='node'}
    w=next(e for e in data['elements'] if e['type']=='way' and e['id']==wayid)
    coords=[nodes[n] for n in w['nodes']]
    if coords[0]!=coords[-1]:coords.append(coords[0])
    p=Polygon(coords)
    if not p.is_valid or p.is_empty:raise RuntimeError('invalid OSM partial')
    return p,{'url':url,'id':wayid,'version':w.get('version'),'timestamp':w.get('timestamp'),'changeset':w.get('changeset'),'tags':w.get('tags',{})}

def proj(lon,lat):
    crs=CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs')
    return Transformer.from_crs(4326,crs,always_xy=True).transform


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    session=requests.Session();session.headers['User-Agent']='iyashiro-v10-research/1.0'
    items=[];features=[]
    for t in TARGETS:
        lower=t['units']*t['minPrivateM2']/t['expectedStoreys']
        g=gsi(session,t['address']);pr,allp,pmeta=plateau(session,t);op,ometa=osm_way(session,t['osmPartialWayId'])
        tf=proj(g['lon'],g['lat']);gp=Point(*tf(g['lon'],g['lat']));pm=shp_transform(tf,pr['polygon']);om=shp_transform(tf,op)
        pstoreys=int(pr['storeys']) if pr['storeys'] and pr['storeys'].isdigit() else None
        plausible=[]
        for b in allp:
            bs=int(b['storeys']) if b['storeys'] and b['storeys'].isdigit() else None
            bm=shp_transform(tf,b['polygon']);d=bm.distance(gp)
            if d<=60 and bs==t['expectedStoreys'] and bm.area>=lower*0.98:
                plausible.append({'gmlId':b['gmlId'],'buildingIDs':b['buildingIDs'],'distanceFromGsiM':round(d,3),'areaM2':round(bm.area,2),'storeys':bs,'height':b['height'],'localityNames':b['localityNames']})
        plausible.sort(key=lambda x:(x['distanceFromGsiM'],abs(x['areaM2']-pm.area),x['gmlId']))
        rank=next((i+1 for i,x in enumerate(plausible) if x['gmlId']==t['plateauGmlId']),None)
        inter=pm.intersection(om).area
        overlap_osm=inter/om.area if om.area else 0
        overlap_plateau=inter/pm.area if pm.area else 0
        area_ratio=om.area/pm.area if pm.area else 0
        iou=inter/pm.union(om).area if pm.union(om).area else 0
        loc=' | '.join(pr['localityNames'])
        checks={
          'propertyIdentityTwoSources':len(t['propertyIdentitySources'])>=2,
          'gsiExactCoordinateMatchesFrozen':abs(g['lon']-t['expectedLon'])<1e-9 and abs(g['lat']-t['expectedLat'])<1e-9,
          'plateauSourceIntegrity':pmeta['integrityMatch'],
          'plateauBuildingIdMatchesExpected':t['plateauBuildingID'] in pr['buildingIDs'],
          'plateauBuildingIdWardPrefix':t['plateauBuildingID'].startswith(t['expectedWardCode']+'-'),
          'plateauLocalityMatches':t['expectedLocality'] in loc,
          'plateauStoreysMatch':pstoreys==t['expectedStoreys'],
          'plateauAreaPhysical':pm.area>=lower*0.98,
          'plateauNearestPhysicallyPlausibleSameStoreys':rank==1,
          'gsiNearPlateauFootprint':pm.distance(gp)<=10.0,
          'plateauPolygonIntegrity':pr['polygon'].is_valid and pr['polygon'].geom_type=='Polygon' and len(pr['polygon'].interiors)==0,
          'osmPartialPolygonIntegrity':op.is_valid and op.geom_type=='Polygon',
          'osmPartialMostlyContainedByPlateau':overlap_osm>=0.95,
          'osmPartialIsMaterialSubset':0.20<=area_ratio<=0.80,
          'osmPartialNotCompetingFullGeometry':iou<0.85,
          'parcelSeparationDeclared':True,
        }
        ready=all(checks.values())
        item={**t,'minimumCompleteFootprintM2':round(lower,3),'gsi':g,
          'plateau':{'gmlId':pr['gmlId'],'buildingIDs':pr['buildingIDs'],'storeys':pstoreys,'height':pr['height'],'localityNames':pr['localityNames'],'areaM2':round(pm.area,2),'distanceFromGsiM':round(pm.distance(gp),3),'physicallyPlausibleRankWithin60m':rank,'physicallyPlausibleCandidatesWithin60m':plausible,'source':pmeta},
          'osmPartial':{**ometa,'areaM2':round(om.area,2),'distanceFromGsiM':round(om.distance(gp),3)},
          'crossSourcePartialControl':{'intersectionM2':round(inter,2),'overlapOfOsmPartial':round(overlap_osm,4),'overlapOfPlateau':round(overlap_plateau,4),'osmToPlateauAreaRatio':round(area_ratio,4),'iou':round(iou,4),'hausdorffM':round(pm.hausdorff_distance(om),3)},
          'checks':checks,'promotionReady':ready,'formalPromotionPerformed':False,
          'policy':{'canonicalGeometrySource':'MLIT PLATEAU 2025 CityGML','independentShapeControl':'OSM partial footprint','geometryRole':'building_footprint_not_parcel','scoringEffect':'none_until_master_promotion_and_b45_dryrun','rankingEffect':'none','automaticExclusionEffect':'none'}}
        items.append(item)
        features += [
          {'type':'Feature','properties':{'propertyId':t['propertyId'],'name':t['name'],'source':'PLATEAU_CANONICAL_CANDIDATE','gmlId':t['plateauGmlId'],'promotionReady':ready},'geometry':mapping(pr['polygon'])},
          {'type':'Feature','properties':{'propertyId':t['propertyId'],'name':t['name'],'source':'OSM_PARTIAL_CONTROL','osmWayId':t['osmPartialWayId'],'promotionReady':ready},'geometry':mapping(op)},
        ]
    summary={'schemaVersion':'v10-b41-plateau-canonical-promotion-gate-v1','generatedAt':datetime.now(timezone.utc).isoformat(),'contract':{'name':'PLATEAU-canonical complete Building footprint','separateFrom':'OSM-canonical cross-source gate v2','thresholds':{'gsiToPlateauMaxM':10,'osmPartialOverlapMin':0.95,'osmPartialAreaRatioMin':0.20,'osmPartialAreaRatioMax':0.80,'osmPartialIouMustBeBelow':0.85}},'promotionReadyCount':sum(x['promotionReady'] for x in items),'formalPromotionsPerformed':0,'items':items,'policy':{'scoreChanges':0,'rankChanges':0,'automaticExclusionChanges':0,'masterWriteSeparate':True}}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'candidate-and-control.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    md=['# V10 B41 PLATEAU-canonical promotion gate v1','', 'This is a separate source model. The existing OSM-canonical gate is not relaxed.','']
    for x in items:
        c=x['crossSourcePartialControl'];p=x['plateau']
        md += [f"## {x['name']} — promotionReady={x['promotionReady']}",f"- PLATEAU canonical candidate: {p['gmlId']} / {p['buildingIDs']} / {p['areaM2']}m² / {p['storeys']}F / GSI distance {p['distanceFromGsiM']}m / plausible rank {p['physicallyPlausibleRankWithin60m']}",f"- OSM partial way/{x['osmPartial']['id']}: {x['osmPartial']['areaM2']}m²",f"- OSM partial contained by PLATEAU: {c['overlapOfOsmPartial']}; area ratio {c['osmToPlateauAreaRatio']}; IoU {c['iou']}; Hausdorff {c['hausdorffM']}m",f"- checks={x['checks']}",'']
    md += ['## Guardrails','- No master promotion in this artifact.','- Building footprint only; parcel/lot geometry remains separate.','- Score/rank/automatic exclusion remain unchanged until a subsequent verified-only B45 dry-run.']
    (OUT/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.name=='SHA256SUMS.txt' or not p.is_file():continue
        sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print(json.dumps({x['propertyId']:{'ready':x['promotionReady'],'plateauRank':x['plateau']['physicallyPlausibleRankWithin60m'],'plateauArea':x['plateau']['areaM2'],'osmArea':x['osmPartial']['areaM2'],'overlapOsm':x['crossSourcePartialControl']['overlapOfOsmPartial'],'areaRatio':x['crossSourcePartialControl']['osmToPlateauAreaRatio'],'checks':x['checks']} for x in items},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
