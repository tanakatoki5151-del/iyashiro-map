#!/usr/bin/env python3
"""Package promotion-ready PLATEAU-canonical footprints into V10 verified delta.

The workflow must first run audit_b41_plateau_canonical_promotion_gate_v1.py.
Only promotionReady PLATEAU candidate features are emitted. OSM partials remain
independent shape controls and are never used as canonical geometry in this package.
"""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

GATE=Path('out-b41-plateau-canonical-promotion-gate-v1')
OUT=Path('out-b41-plateau-canonical-promotions-v1')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    s=json.loads((GATE/'SUMMARY.json').read_text(encoding='utf-8'))
    g=json.loads((GATE/'candidate-and-control.geojson').read_text(encoding='utf-8'))
    ready={x['propertyId']:x for x in s['items'] if x['promotionReady']}
    assert set(ready)=={'BLDG-6583382c8322','BLDG-c404c81c08a5'},ready
    can={f['properties']['propertyId']:f for f in g['features'] if f['properties'].get('source')=='PLATEAU_CANONICAL_CANDIDATE'}
    feats=[];prov=[]
    now=datetime.now(timezone.utc).isoformat()
    for pid in sorted(ready):
        x=ready[pid];f=json.loads(json.dumps(can[pid]));p=f['properties']
        p.update({'propertyId':pid,'buildingName':x['name'],'address':x['address'],'geometryRole':'building_footprint_not_parcel','status':'verified_for_v10_spatial_screening','canonicalGeometrySource':'MLIT PLATEAU 2025 CityGML','plateauGmlId':x['plateau']['gmlId'],'plateauBuildingID':x['plateauBuildingID'],'plateauSourceSha256':x['plateau']['source']['sha256'],'plateauStoreys':x['plateau']['storeys'],'plateauHeightM':x['plateau']['height'],'plateauAreaM2':x['plateau']['areaM2'],'gsiAddressTitle':x['gsi']['title'],'gsiAddressLon':x['gsi']['lon'],'gsiAddressLat':x['gsi']['lat'],'independentShapeControl':'OpenStreetMap partial footprint','osmPartialWayId':x['osmPartial']['id'],'osmPartialVersion':x['osmPartial']['version'],'osmPartialTimestamp':x['osmPartial']['timestamp'],'osmPartialOverlapByPlateau':x['crossSourcePartialControl']['overlapOfOsmPartial'],'osmPartialToPlateauAreaRatio':x['crossSourcePartialControl']['osmToPlateauAreaRatio'],'promotionGate':'v10-b41-plateau-canonical-promotion-gate-v1','promotionGateAllChecks':all(x['checks'].values()),'verifiedAtUtc':now,'scoringEffect':'none_until_verified_only_b45_dryrun','rankingEffect':'none','automaticExclusionEffect':'none'})
        feats.append(f)
        prov.append({'propertyId':pid,'buildingName':x['name'],'address':x['address'],'propertyIdentitySources':x['propertyIdentitySources'],'gsi':x['gsi'],'plateau':x['plateau'],'osmPartial':x['osmPartial'],'crossSourcePartialControl':x['crossSourcePartialControl'],'checks':x['checks'],'decision':'formal_building_polygon_promoted_plateau_canonical','parcelSeparation':'building footprint must never be reused as parcel boundary'})
    fc={'type':'FeatureCollection','name':'V10 PLATEAU-canonical formal building additions 2026-08-15','features':feats}
    geo=OUT/'verified-building-polygons-plateau-additions-v1.geojson';geo.write_text(json.dumps(fc,ensure_ascii=False,indent=2),encoding='utf-8')
    provenance={'schemaVersion':'v10-b41-plateau-canonical-promotions-v1','generatedAt':now,'sourceGateArtifact':'v10-b41-plateau-canonical-promotion-gate-v1','formalPromotions':len(feats),'items':prov,'policy':{'canonicalGeometrySource':'MLIT PLATEAU 2025 CityGML','geometryRole':'building_footprint_not_parcel','scoreChange':False,'rankChange':False,'automaticExclusionChange':False}}
    (OUT/'PROVENANCE.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# V10 B41 PLATEAU-canonical formal Building promotions v1','',f"Formal additions: **{len(feats)}**",'']
    for x in prov:
        c=x['crossSourcePartialControl'];p=x['plateau']
        md += [f"## {x['buildingName']}",f"- {x['address']}",f"- canonical PLATEAU {p['gmlId']} / {p['buildingIDs']} / {p['areaM2']}m² / {p['storeys']}F",f"- GSI distance {p['distanceFromGsiM']}m / physically-plausible rank {p['physicallyPlausibleRankWithin60m']}",f"- OSM partial way/{x['osmPartial']['id']} v{x['osmPartial']['version']} / overlap contained {c['overlapOfOsmPartial']} / area ratio {c['osmToPlateauAreaRatio']}",'- status: `verified_for_v10_spatial_screening`','']
    md += ['## Guardrails','- PLATEAU is canonical for these two buildings; OSM is partial control only.','- Building footprint is never parcel/lot boundary.','- Score/rank/automatic exclusion remain unchanged until verified-only B45 dry-run.']
    (OUT/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.name=='SHA256SUMS.txt' or not p.is_file():continue
        sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print(json.dumps({'formalPromotions':len(feats),'propertyIds':sorted(ready),'geojsonSha256':hashlib.sha256(geo.read_bytes()).hexdigest(),'scoreRankAutoExclusionChanges':0},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
