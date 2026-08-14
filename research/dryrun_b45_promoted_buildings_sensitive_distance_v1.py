#!/usr/bin/env python3
"""V10 B45 verified-only dry-run for the two newly promoted Building Polygons.

The full fixed sensitive-feature baseline has 9,657 features and is preserved in Drive.
A top-2-per-target/category subset was selected from that exact frozen file using
min(representative-point distance, promoted-building distance). This script re-computes
those distances independently from live-frozen building geometries and the frozen subset,
checks nearest-feature stability, and applies the existing 500 m review/preference band.

No score/rank/automatic-exclusion change is performed by this script.
"""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import requests
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import transform as shp_transform

from research.audit_b41_crosssource_promotion_gate_v1 import TARGETS,gsi,osm_way

FIX=Path('research/fixtures/b41_sensitive_subset_top2_v1.json')
OUT=Path('out-b45-promoted-buildings-sensitive-distance-v1')
TARGET_IDS={'BLDG-edf6c2448f9e','BLDG-4e6c9a14c783'}
CATS=('shrine','temple','cemetery')
THRESHOLD_M=500.0


def class_band(d):
    # Existing V10 sensitive-distance band relevant to these cases.
    return 'review' if d < THRESHOLD_M else 'within_preference'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    fixture=json.loads(FIX.read_text(encoding='utf-8'))
    byid={x['featureId']:x for x in fixture['features']}
    session=requests.Session();session.headers['User-Agent']='iyashiro-v10-research/1.0'
    targets={x['propertyId']:x for x in TARGETS if x['propertyId'] in TARGET_IDS}
    tr=Transformer.from_crs(4326,6677,always_xy=True)
    rows=[];targets_out=[]
    for pid in sorted(TARGET_IDS):
        t=targets[pid]
        gp0=gsi(session,t['address'])
        pt=Point(*tr.transform(gp0['lon'],gp0['lat']))
        opoly,ometa=osm_way(session,t['osmWayId'])
        bg=shp_transform(tr.transform,opoly)
        cats_out={}
        for cat in CATS:
            declared=fixture['targetRankings'][pid][cat]
            calc=[]
            for r in declared:
                o=byid[r['featureId']]
                assert o['geometryType']=='Point',o
                fg=Point(o['geometry']['coordinates'])
                dp=pt.distance(fg);db=bg.distance(fg)
                calc.append({'rankFromFullBaseline':r['rank'],'featureId':o['featureId'],'name':o.get('name'),'sourceUrl':o['sourceUrl'],'pointDistanceM':round(dp,6),'buildingDistanceM':round(db,6),'declaredPointDistanceM':r['pointDistanceM'],'declaredBuildingDistanceM':r['buildingDistanceM']})
                assert abs(dp-r['pointDistanceM'])<0.03,(pid,cat,o['featureId'],dp,r['pointDistanceM'])
                assert abs(db-r['buildingDistanceM'])<0.03,(pid,cat,o['featureId'],db,r['buildingDistanceM'])
            calc.sort(key=lambda x:min(x['pointDistanceM'],x['buildingDistanceM']))
            nearest=calc[0];runner=calc[1]
            # Stable nearest under both representations.
            assert nearest['pointDistanceM'] < runner['pointDistanceM'],(pid,cat,calc)
            assert nearest['buildingDistanceM'] < runner['buildingDistanceM'],(pid,cat,calc)
            old=class_band(nearest['pointDistanceM']);new=class_band(nearest['buildingDistanceM'])
            rec={'propertyId':pid,'buildingName':t['name'],'category':cat,'nearestFeatureId':nearest['featureId'],'nearestName':nearest['name'],'representativePointDistanceM':nearest['pointDistanceM'],'buildingPolygonDistanceM':nearest['buildingDistanceM'],'deltaM':round(nearest['buildingDistanceM']-nearest['pointDistanceM'],6),'oldClass':old,'newClass':new,'classChanged':old!=new,'runnerUpFeatureId':runner['featureId'],'runnerUpBuildingDistanceM':runner['buildingDistanceM'],'nearestStabilityMarginM':round(runner['buildingDistanceM']-nearest['buildingDistanceM'],6),'sourceUrl':nearest['sourceUrl']}
            rows.append(rec);cats_out[cat]=rec
        targets_out.append({'propertyId':pid,'buildingName':t['name'],'address':t['address'],'osm':ometa,'categories':cats_out,'anyClassChanged':any(x['classChanged'] for x in cats_out.values())})
    assert len(rows)==6,rows
    assert not any(x['classChanged'] for x in rows),rows
    result={'schemaVersion':'v10-b45-promoted-buildings-sensitive-distance-v1','generatedAt':datetime.now(timezone.utc).isoformat(),'sourceFullSensitiveGeometry':fixture['sourceFullGeometry'],'fixtureSelection':fixture['selection'],'thresholdM':THRESHOLD_M,'targets':targets_out,'rows':rows,'summary':{'formalBuildingsDryRun':2,'comparisons':6,'classChanges':0,'scoreChanges':0,'rankChanges':0,'automaticExclusionChanges':0},'policy':{'verifiedOnly':True,'buildingFootprintNotParcel':True,'decision':'pass_class_unchanged'}}
    (OUT/'SUMMARY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    md=['# V10 B45 promoted Building Polygon sensitive-distance dry-run v1','',f"Formal promoted buildings: **2** / comparisons: **6** / class changes: **0**",'', '| Building | Category | Point m | Building m | Delta m | Old | New | Nearest | Runner-up margin |','|---|---|---:|---:|---:|---|---|---|---:|']
    for r in rows:
        md.append(f"| {r['buildingName']} | {r['category']} | {r['representativePointDistanceM']:.3f} | {r['buildingPolygonDistanceM']:.3f} | {r['deltaM']:+.3f} | {r['oldClass']} | {r['newClass']} | {r['nearestName'] or r['nearestFeatureId']} | {r['nearestStabilityMarginM']:.3f} |")
    md += ['','## Decision','- All six category comparisons remain in the same V10 distance class.','- Therefore score, ranking, and automatic exclusion remain unchanged.','- The closest threshold case is レオパレス駒場東大前 → 聖徳寺: point 502.116m → building 504.357m, still outside the 500m review band.','','## Provenance',f"- Full fixed sensitive geometry: Drive `{fixture['sourceFullGeometry']['driveId']}` / SHA256 `{fixture['sourceFullGeometry']['sha256']}`",'- Top-2 fixture preserves the nearest and runner-up from the full 9,657-feature frozen baseline.','- Building geometry is re-fetched from the exact OSM way IDs fixed by the formal promotion gate.']
    (OUT/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.name=='SHA256SUMS.txt' or not p.is_file():continue
        sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
    for r in rows:print(json.dumps(r,ensure_ascii=False))

if __name__=='__main__':main()
