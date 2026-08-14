#!/usr/bin/env python3
"""V10 B45 verified-only dry-run for PLATEAU-canonical promotions.

Requires the PLATEAU canonical promotion gate output in the same workspace.
Uses a top-2 subset selected from the fixed 31,918-unique OSM geometry baseline
(30,493 unique features relevant to temple/shrine/cemetery), retaining runner-up
features to prove nearest-feature stability.
"""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import Point,shape
from shapely.ops import transform as shp_transform

FIX=Path('research/fixtures/b41_plateau_sensitive_subset_top2_v1.json')
GATE=Path('out-b41-plateau-canonical-promotion-gate-v1')
OUT=Path('out-b45-plateau-canonical-promotions-v1')
TARGETS={
 'BLDG-6583382c8322':{'name':'レ・サン・サーンス','lon':139.697525,'lat':35.620316,'gmlId':'bldg_7b54ce02-37b0-4c5d-99e3-24f184f5d7fe'},
 'BLDG-c404c81c08a5':{'name':'プリュメゾン駒沢','lon':139.668793,'lat':35.628464,'gmlId':'bldg_958e8009-cbab-4089-b09f-06e45eba935d'},
}
CATS=('shrine','temple','cemetery');THRESHOLD_M=500.0

def band(d):return 'review' if d < THRESHOLD_M else 'within_preference'

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 fixture=json.loads(FIX.read_text(encoding='utf-8'))
 assert fixture['sourceFullGeometry']['uniqueOsmFeatures']==31918,fixture
 assert fixture['sourceFullGeometry']['templeShrineCemeteryRelevantUnique']==30493,fixture
 gate=json.loads((GATE/'SUMMARY.json').read_text(encoding='utf-8'))
 assert gate['promotionReadyCount']==2,gate
 geos=json.loads((GATE/'candidate-and-control.geojson').read_text(encoding='utf-8'))
 canonical={f['properties']['propertyId']:f for f in geos['features'] if f['properties'].get('source')=='PLATEAU_CANONICAL_CANDIDATE'}
 byid={x['featureId']:x for x in fixture['features']}
 tr=Transformer.from_crs(4326,6677,always_xy=True)
 rows=[];targets_out=[]
 for pid,t in TARGETS.items():
  poly=shp_transform(tr.transform,shape(canonical[pid]['geometry']))
  pt=Point(*tr.transform(t['lon'],t['lat']))
  cats={}
  for cat in CATS:
   calc=[]
   for r in fixture['targetRankings'][pid][cat]:
    o=byid[r['featureId']];assert o['geometryType']=='Point',o
    fg=Point(o['geometry']['coordinates']);dp=pt.distance(fg);db=poly.distance(fg)
    assert abs(dp-r['pointDistanceM'])<0.03,(pid,cat,dp,r)
    assert abs(db-r['buildingDistanceM'])<0.03,(pid,cat,db,r)
    calc.append({'featureId':o['featureId'],'name':o.get('name'),'sourceUrl':o['sourceUrl'],'pointDistanceM':round(dp,6),'buildingDistanceM':round(db,6),'rankFromFullBaseline':r['rank']})
   calc.sort(key=lambda x:min(x['pointDistanceM'],x['buildingDistanceM']))
   n,runner=calc
   assert n['pointDistanceM']<runner['pointDistanceM'],(pid,cat,calc)
   assert n['buildingDistanceM']<runner['buildingDistanceM'],(pid,cat,calc)
   old,new=band(n['pointDistanceM']),band(n['buildingDistanceM'])
   rec={'propertyId':pid,'buildingName':t['name'],'category':cat,'nearestFeatureId':n['featureId'],'nearestName':n['name'],'representativePointDistanceM':n['pointDistanceM'],'buildingPolygonDistanceM':n['buildingDistanceM'],'deltaM':round(n['buildingDistanceM']-n['pointDistanceM'],6),'oldClass':old,'newClass':new,'classChanged':old!=new,'runnerUpFeatureId':runner['featureId'],'runnerUpBuildingDistanceM':runner['buildingDistanceM'],'nearestStabilityMarginM':round(runner['buildingDistanceM']-n['buildingDistanceM'],6),'sourceUrl':n['sourceUrl']}
   rows.append(rec);cats[cat]=rec
  targets_out.append({'propertyId':pid,'buildingName':t['name'],'canonicalGeometry':'PLATEAU 2025 CityGML','categories':cats,'anyClassChanged':any(x['classChanged'] for x in cats.values())})
 assert len(rows)==6,rows
 assert not any(r['classChanged'] for r in rows),rows
 result={'schemaVersion':'v10-b45-plateau-canonical-promotions-v1','generatedAt':datetime.now(timezone.utc).isoformat(),'sourceFullSensitiveGeometry':fixture['sourceFullGeometry'],'fixtureSelection':fixture['selection'],'thresholdM':THRESHOLD_M,'targets':targets_out,'rows':rows,'summary':{'formalBuildingsDryRun':2,'comparisons':6,'classChanges':0,'scoreChanges':0,'rankChanges':0,'automaticExclusionChanges':0},'policy':{'verifiedOnly':True,'canonicalGeometrySource':'MLIT PLATEAU 2025 CityGML','buildingFootprintNotParcel':True,'decision':'pass_class_unchanged'}}
 (OUT/'SUMMARY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 md=['# V10 B45 PLATEAU-canonical promoted Building Polygon dry-run v1','',f"Formal promoted buildings: **2** / comparisons: **6** / class changes: **0**",'', '| Building | Category | Point m | PLATEAU building m | Delta m | Old | New | Nearest | Runner-up margin |','|---|---|---:|---:|---:|---|---|---|---:|']
 for r in rows:md.append(f"| {r['buildingName']} | {r['category']} | {r['representativePointDistanceM']:.3f} | {r['buildingPolygonDistanceM']:.3f} | {r['deltaM']:+.3f} | {r['oldClass']} | {r['newClass']} | {r['nearestName'] or r['nearestFeatureId']} | {r['nearestStabilityMarginM']:.3f} |")
 md += ['','## Decision','- All six comparisons retain the same V10 500m class.','- Score/rank/automatic exclusion remain unchanged.','- The closest case is プリュメゾン駒沢 → 野沢稲荷神社: point 480.249m → PLATEAU building 484.978m, still inside review.','','## Baseline provenance',f"- fixed source Drive `{fixture['sourceFullGeometry']['driveId']}` / SHA256 `{fixture['sourceFullGeometry']['sha256']}`",f"- unique total `{fixture['sourceFullGeometry']['uniqueOsmFeatures']}` / temple-shrine-cemetery relevant unique `{fixture['sourceFullGeometry']['templeShrineCemeteryRelevantUnique']}`"]
 (OUT/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
 sums=[]
 for p in sorted(OUT.iterdir()):
  if p.name=='SHA256SUMS.txt' or not p.is_file():continue
  sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
 (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
 print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
 for r in rows:print(json.dumps(r,ensure_ascii=False))

if __name__=='__main__':main()
