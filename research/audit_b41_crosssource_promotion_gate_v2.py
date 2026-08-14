#!/usr/bin/env python3
"""V10 B41 cross-source promotion gate v2.

Corrected execution wrapper around v1 source/provenance functions. v1 failed closed
because the PLATEAU candidate row dict was passed to Shapely instead of its polygon.
No evidence rule or threshold is relaxed here.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from shapely.geometry import Point, mapping
from shapely.ops import transform as shp_transform
import requests

from research.audit_b41_crosssource_promotion_gate_v1 import (
    TARGETS, gsi, plateau, osm_way, local_proj
)

OUT=Path('out-b41-crosssource-promotion-gate-v2')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sess=requests.Session(); sess.headers['User-Agent']='iyashiro-v10-research/1.0'
    items=[]; features=[]
    for t in TARGETS:
        lower=t['units']*t['minPrivateM2']/t['expectedStoreys']
        g=gsi(sess,t['address'])
        prow,allp,pmeta=plateau(sess,t)
        ppoly=prow['polygon']
        opoly,ometa=osm_way(sess,t['osmWayId'])
        proj=local_proj(g['lon'],g['lat'])
        gp=Point(*proj(g['lon'],g['lat']))
        ppm=shp_transform(proj,ppoly); opm=shp_transform(proj,opoly)
        inter=ppm.intersection(opm).area; union=ppm.union(opm).area
        iou=inter/union if union else 0.0
        overlap_min=inter/min(ppm.area,opm.area) if min(ppm.area,opm.area)>0 else 0.0
        pstoreys=int(prow['storeys']) if prow['storeys'] and prow['storeys'].isdigit() else None
        plausible=[]
        for b in allp:
            bm=shp_transform(proj,b['polygon'])
            bs=int(b['storeys']) if b['storeys'] and b['storeys'].isdigit() else None
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
            'plateauPolygonIntegrity':ppoly.is_valid and ppoly.geom_type=='Polygon',
            'osmPolygonIntegrity':opoly.is_valid and opoly.geom_type=='Polygon',
            'parcelSeparationDeclared':True,
        }
        ready=all(checks.values())
        item={
            **t,'minimumCompleteFootprintM2':round(lower,3),'gsi':g,
            'plateau':{'gmlId':prow['gmlId'],'buildingID':t['plateauBuildingID'],'storeys':pstoreys,'height':prow['height'],'locality':prow['locality'],'areaM2':round(ppm.area,2),'distanceFromGsiM':round(ppm.distance(gp),3),'physicallyPlausibleRankWithin60m':target_rank,'physicallyPlausibleCandidatesWithin60m':plausible,'source':pmeta},
            'osm':{**ometa,'areaM2':round(opm.area,2),'distanceFromGsiM':round(opm.distance(gp),3)},
            'crossSource':{'intersectionM2':round(inter,2),'iou':round(iou,4),'overlapOfSmaller':round(overlap_min,4),'hausdorffM':round(ppm.hausdorff_distance(opm),3)},
            'checks':checks,'promotionReady':ready,'formalPromotionPerformed':False,
            'policy':{'geometryRole':'building_footprint_not_parcel','scoringEffect':'none_until_master_promotion_and_dryrun','rankingEffect':'none','automaticExclusionEffect':'none'}
        }
        items.append(item)
        features += [
            {'type':'Feature','properties':{'propertyId':t['propertyId'],'name':t['name'],'source':'PLATEAU','gmlId':t['plateauGmlId'],'promotionReady':ready},'geometry':mapping(ppoly)},
            {'type':'Feature','properties':{'propertyId':t['propertyId'],'name':t['name'],'source':'OSM','osmWayId':t['osmWayId'],'promotionReady':ready},'geometry':mapping(opoly)}
        ]
    summary={'schemaVersion':'v10-b41-crosssource-promotion-gate-v2','generatedAt':datetime.now(timezone.utc).isoformat(),'supersedesExecution':'v1 implementation failure only','contract':'V10_BUILDING_POLYGON_PILOT_CONTRACT_v1_20260814','promotionReadyCount':sum(x['promotionReady'] for x in items),'formalPromotionsPerformed':0,'items':items,'policy':{'masterWriteSeparate':True,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none'}}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'crosssource-geometries.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    md=['# V10 B41 cross-source promotion gate v2','']
    for x in items:
        md += [f"## {x['name']} — promotionReady={x['promotionReady']}",f"- GSI: {x['gsi']['title']} @ {x['gsi']['lat']},{x['gsi']['lon']}",f"- PLATEAU: {x['plateau']['areaM2']}m² / {x['plateau']['storeys']}F / d={x['plateau']['distanceFromGsiM']}m / physically-plausible-rank={x['plateau']['physicallyPlausibleRankWithin60m']}",f"- OSM way/{x['osm']['id']}: {x['osm']['areaM2']}m² / d={x['osm']['distanceFromGsiM']}m / v{x['osm']['version']} / {x['osm']['timestamp']}",f"- IoU={x['crossSource']['iou']} overlap(smaller)={x['crossSource']['overlapOfSmaller']} Hausdorff={x['crossSource']['hausdorffM']}m",f"- checks={x['checks']}",'']
    md += ['## Policy','- readiness is not the master promotion itself','- score/rank/automatic exclusion unchanged in this artifact','- building footprint remains separate from parcel boundary']
    (OUT/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.name=='SHA256SUMS.txt' or not p.is_file(): continue
        sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print(json.dumps({x['propertyId']:{'ready':x['promotionReady'],'iou':x['crossSource']['iou'],'overlap':x['crossSource']['overlapOfSmaller'],'plateauRank':x['plateau']['physicallyPlausibleRankWithin60m'],'checks':x['checks']} for x in items},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
