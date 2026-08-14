#!/usr/bin/env python3
"""Package promotion-ready B41 building footprints into a frozen V10 verified delta.

Input must be the successful cross-source gate v2 output generated in the same run.
Only OSM geometries whose promotionReady flag is true are emitted as canonical
building footprints. PLATEAU remains an independent geometry QA/control source.
No parcel geometry, score, ranking, or automatic-exclusion change is performed here.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

GATE=Path('out-b41-crosssource-promotion-gate-v2')
OUT=Path('out-b41-formal-building-promotions-v1')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    summary=json.loads((GATE/'SUMMARY.json').read_text(encoding='utf-8'))
    geos=json.loads((GATE/'crosssource-geometries.geojson').read_text(encoding='utf-8'))
    items={x['propertyId']:x for x in summary['items']}
    assert summary['promotionReadyCount']==2, summary['promotionReadyCount']
    ready={pid for pid,x in items.items() if x['promotionReady']}
    assert ready=={'BLDG-edf6c2448f9e','BLDG-4e6c9a14c783'}, ready

    osm_by_pid={
        f['properties']['propertyId']:f for f in geos['features']
        if f['properties'].get('source')=='OSM'
    }
    features=[]
    provenance=[]
    for pid in sorted(ready):
        item=items[pid]
        f=json.loads(json.dumps(osm_by_pid[pid]))
        props=f['properties']
        props.update({
            'propertyId':pid,
            'buildingName':item['name'],
            'address':item['address'],
            'geometryRole':'building_footprint_not_parcel',
            'status':'verified_for_v10_spatial_screening',
            'canonicalGeometrySource':'OpenStreetMap',
            'osmWayId':item['osm']['id'],
            'osmVersion':item['osm']['version'],
            'osmTimestamp':item['osm']['timestamp'],
            'osmChangeset':item['osm']['changeset'],
            'independentGeometryControl':'MLIT PLATEAU 2025 CityGML',
            'plateauGmlId':item['plateau']['gmlId'],
            'plateauBuildingID':item['plateau']['buildingID'],
            'gsiAddressTitle':item['gsi']['title'],
            'gsiAddressLon':item['gsi']['lon'],
            'gsiAddressLat':item['gsi']['lat'],
            'osmAreaM2':item['osm']['areaM2'],
            'plateauAreaM2':item['plateau']['areaM2'],
            'plateauStoreys':item['plateau']['storeys'],
            'crossSourceIoU':item['crossSource']['iou'],
            'crossSourceOverlapOfSmaller':item['crossSource']['overlapOfSmaller'],
            'crossSourceHausdorffM':item['crossSource']['hausdorffM'],
            'promotionGate':'v10-b41-crosssource-promotion-gate-v2',
            'promotionGateAllChecks':all(item['checks'].values()),
            'verifiedAtUtc':datetime.now(timezone.utc).isoformat(),
            'scoringEffect':'none_until_verified_only_dryrun',
            'rankingEffect':'none',
            'automaticExclusionEffect':'none',
        })
        features.append(f)
        provenance.append({
            'propertyId':pid,'buildingName':item['name'],'address':item['address'],
            'propertyIdentitySources':item['propertyIdentitySources'],
            'gsi':item['gsi'],'plateau':item['plateau'],'osm':item['osm'],
            'crossSource':item['crossSource'],'checks':item['checks'],
            'decision':'formal_building_polygon_promoted_for_v10_spatial_screening',
            'parcelSeparation':'building footprint must never be reused as parcel boundary',
        })

    fc={'type':'FeatureCollection','name':'V10 formal building polygon additions 2026-08-15','features':features}
    geo=OUT/'verified-building-polygons-additions-v1.geojson'
    geo.write_text(json.dumps(fc,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'PROVENANCE.json').write_text(json.dumps({'schemaVersion':'v10-b41-formal-building-promotions-v1','generatedAt':datetime.now(timezone.utc).isoformat(),'sourceGateArtifact':'v10-b41-crosssource-promotion-gate-v2','formalPromotions':len(features),'items':provenance,'policy':{'geometryRole':'building_footprint_not_parcel','scoreChange':False,'rankChange':False,'automaticExclusionChange':False}},ensure_ascii=False,indent=2),encoding='utf-8')
    readme=['# V10 B41 formal Building Polygon promotions v1','',f'Formal verified building additions: **{len(features)}**','']
    for p in provenance:
        readme += [f"## {p['buildingName']}",f"- {p['address']}",f"- OSM way/{p['osm']['id']} v{p['osm']['version']} @ {p['osm']['timestamp']}",f"- PLATEAU control {p['plateau']['gmlId']} / {p['plateau']['buildingID']}",f"- IoU {p['crossSource']['iou']} / overlap(smaller) {p['crossSource']['overlapOfSmaller']} / Hausdorff {p['crossSource']['hausdorffM']}m",'- status: `verified_for_v10_spatial_screening`','']
    readme += ['## Guardrails','- Building footprint only. Never treat it as parcel/lot boundary.','- This package does not change score, ranking, or automatic exclusion.','- Run verified-only distance dry-run before any scoring decision.']
    (OUT/'README.md').write_text('\n'.join(readme)+'\n',encoding='utf-8')
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.name=='SHA256SUMS.txt' or not p.is_file(): continue
        sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print(json.dumps({'formalPromotions':len(features),'propertyIds':sorted(ready),'geojsonSha256':hashlib.sha256(geo.read_bytes()).hexdigest(),'scoreRankAutoExclusionChanges':0},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
