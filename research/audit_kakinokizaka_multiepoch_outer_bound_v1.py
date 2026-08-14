#!/usr/bin/env python3
"""Build conservative decision-only outer bounds around the frozen current
Kakinokizaka culvert proxy and test V10 target cells.

Independent historical aerial photographs (1947, 1963, 1971) were acquired in
prior runs and visually reviewed as a multi-epoch plausibility check. This script
does NOT claim the current proxy is the historical centerline. Instead it asks a
narrow decision question: would the two target ~100m cells be hit even if the
historical channel were displaced by an intentionally large 25/50/75/100 m from
the current proxy?

All outputs are review/decision guards, not verified historical geometry.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

INPUT=Path('research/inputs/kakinokizaka-current-culvert-proxy-v1.geojson')
OUT=Path('out-kakinokizaka-multiepoch-outer-bound-v1')
WGS=CRS.from_epsg(4326); METRIC=CRS.from_epsg(6677)
TO_M=Transformer.from_crs(WGS,METRIC,always_xy=True).transform
TO_W=Transformer.from_crs(METRIC,WGS,always_xy=True).transform
LAT_HALF=0.000898/2; LON_HALF=0.001104/2
CELLS=[
 {'cellId':'g233-217','town':'東が丘一丁目','lat':35.630340,'lon':139.669621},
 {'cellId':'g239-220','town':'柿の木坂二丁目','lat':35.624952,'lon':139.672934},
]
BUFFERS=[25,50,75,100]
PHOTO_EVIDENCE=[
 {'year':1947,'photo':'USA-M389-64','photoId':168920,'scale':9877,'coverage':'30/30 culvert samples + both target cells','role':'early independent control'},
 {'year':1963,'photo':'MKT636-C12-12','photoId':430104,'scale':10000,'coverage':'25/30 culvert samples + both target cells','role':'primary high-resolution pre-culvert control'},
 {'year':1971,'photo':'MKT711X-C8B-10','photoId':545987,'scale':20000,'coverage':'24/30 culvert samples + both target cells','role':'immediately pre-culvert control'},
]

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 fc=json.loads(INPUT.read_text(encoding='utf-8'));line=shape(fc['features'][0]['geometry']);lm=transform(TO_M,line)
 cells=[]
 for c in CELLS:
  poly=box(c['lon']-LON_HALF,c['lat']-LAT_HALF,c['lon']+LON_HALF,c['lat']+LAT_HALF);pm=transform(TO_M,poly)
  cells.append({**c,'wgs':poly,'m':pm,'baselineDistanceM':lm.distance(pm)})
 rows=[];features=[]
 for meters in BUFFERS:
  corridor=lm.buffer(meters,cap_style=2,join_style=2)
  features.append({'type':'Feature','properties':{'role':'decision_only_historical_outer_bound','bufferMeters':meters,'historicalCenterlineVerified':False,'scoringEffect':'none'},'geometry':mapping(transform(TO_W,corridor))})
  for c in cells:
   d=corridor.distance(c['m']);hit=corridor.intersects(c['m'])
   rows.append({'bufferMeters':meters,'cellId':c['cellId'],'town':c['town'],'baselineLineToCellDistanceM':round(c['baselineDistanceM'],3),'corridorIntersectsCell':hit,'clearanceAfterBufferM':round(d,3)})
 max100=[r for r in rows if r['bufferMeters']==100]
 result={
  'version':'v10-kakinokizaka-multiepoch-outer-bound-v1-20260815','generatedAt':datetime.now(timezone.utc).isoformat(),'inputSha256':sha(INPUT),'buffersMeters':BUFFERS,'photoEvidence':PHOTO_EVIDENCE,
  'visualReviewPremise':{
    'status':'reviewed_multi_epoch_no_gross_lateral_shift_toward_target_cells_observed',
    'scope':'decision guard only, not digitized historical centerline',
    'note':'1947/1963/1971 overlays keep the observed drainage/lowland corridor near the frozen current trace; exact channel digitization and georeferencing remain pending.'
  },
  'results':rows,
  'decision':{
    'buffer100mIntersectsAnyTargetCell':any(r['corridorIntersectsCell'] for r in max100),
    'buffer100mMinimumClearanceM':min(r['clearanceAfterBufferM'] for r in max100),
    'directHitDecision':'strong_negative_outer_bound' if not any(r['corridorIntersectsCell'] for r in max100) else 'unresolved',
    'historicalCenterlineVerified':False,'formalHistoricalGeometryPromotion':False,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none',
    'nextGate':'digitize 1963 channel centerline and independently cross-check 1947/1956/1971; use exact geometry for provenance, not for basic direct-hit exclusion if outer-bound remains clear.'
  }
 }
 (OUT/'SUMMARY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'outer-bounds.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False,indent=2),encoding='utf-8')
 with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
  for p in sorted(OUT.iterdir()):
   if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{sha(p)}  {p.name}\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
