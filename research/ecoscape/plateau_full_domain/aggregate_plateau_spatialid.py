#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,csv,gzip,hashlib,io,json,statistics,zlib
from collections import Counter
from pathlib import Path
GRID_SHA='c8c822568e3313e800906665652e8d2f6d9dbb862d711e13b26e70ec99f03232'
def cj(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def grid(path):
 d=json.loads(path.read_text());assert d['sourceFileSha256']==GRID_SHA
 comp=base64.b64decode(d['maskZlibBase64']);assert sha(comp)==d['compressedSha256'];m=zlib.decompress(comp);assert sha(m)==d['maskSha256'];out=[];cols=int(d['columns'])
 for r in range(int(d['rows'])):
  for c in range(cols):
   i=r*cols+c
   if m[i//8]&(1<<(7-i%8)):out.append(f'g{r}-{c}')
 assert len(out)==120662;return out
def readgz(path):
 with gzip.open(path,'rt',encoding='utf-8') as f:
  for line in f:
   if line.strip():yield json.loads(line)
def gzjson(rows):
 b=io.BytesIO()
 with gzip.GzipFile(fileobj=b,mode='wb',mtime=0) as f:
  for r in rows:f.write(cj(r)+b'\n')
 return b.getvalue()
def csvgz(rows,cols):
 s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=cols,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows);raw=s.getvalue().encode();b=io.BytesIO()
 with gzip.GzipFile(fileobj=b,mode='wb',mtime=0) as f:f.write(raw)
 return b.getvalue()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--grid',type=Path,required=True);ap.add_argument('--input',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);expected=grid(a.grid);files=sorted(a.input.rglob('PLATEAU_E3_S*_FACTS.jsonl.gz'));audits=sorted(a.input.rglob('PLATEAU_E3_S*_AUDIT.json'));assert len(files)==25,(len(files),files);assert len(audits)==25,len(audits)
 rows=[]
 for p in files:rows.extend(readgz(p))
 rows.sort(key=lambda x:int(x['ordinal']));ids=[x['cellId'] for x in rows];cnt=Counter(x['status'] for x in rows);dups=len(ids)-len(set(ids));equal=ids==expected;bad=[x for x in rows if x['status'] not in {'PASS','EXPLICIT_NO_BUILDINGS'}]
 aa=[json.loads(p.read_text()) for p in audits];request_failures=sum(int(x['requestFailures']) for x in aa);ok=len(rows)==120662 and dups==0 and equal and not bad and request_failures==0 and all(x['qaPass'] for x in aa)
 data=gzjson(rows);fp=a.out/'ECOSCAPE_PLATEAU_PRACTICAL_FULL_120662_B98.jsonl.gz';fp.write_bytes(data)
 cols=['ordinal','cellId','row','col','lat','lon','status','buildingCountIntersecting','buildingCenterCount','buildingCoverageFractionApprox','openSpaceFractionApprox','bboxCoverageFractionUpperBound','roofAreaKnownBuildingFraction','heightKnownBuildingFraction','heightMeanM','heightMedianM','heightP90M','heightMaxM','buildingCountHeight20mPlus','buildingCountHeight31mPlus','storeysMean','storeysP90','dominantAddress','dominantCityCode','dominantSurveyYear','dominantCreationYear','spatialTileCount','bboxFillRatioMedianShard','coverageMethod','geometryMethod','approximationClass','sourceId','sourceYear','provenanceUrl','requestTileManifestSha256','methodVersion','shard','missingReason','scoringEffect']
 cdata=csvgz(rows,cols);cp=a.out/'ECOSCAPE_PLATEAU_PRACTICAL_FULL_120662_B98.csv.gz';cp.write_bytes(cdata)
 vals=lambda key:[float(x[key]) for x in rows if isinstance(x.get(key),(int,float))]
 coverage=vals('buildingCoverageFractionApprox');heights=vals('heightMedianM');counts=vals('buildingCountIntersecting');hcov=vals('heightKnownBuildingFraction')
 report={'buildId':'ecos-practical-v2-20260817-b98-plateau-physical-full','source':'PLATEAU_SPATIALID','methodVersion':'PLATEAU_SPATIALID_LOD1_BBOX_APPROX_v1','expectedCells':120662,'actualCells':len(rows),'uniqueCells':len(set(ids)),'duplicateCells':dups,'canonicalSetAndOrderEqual':equal,'statusCounts':dict(sorted(cnt.items())),'badStatusCount':len(bad),'shardCount':len(files),'allShardQaPass':all(x['qaPass'] for x in aa),'requestFailures':request_failures,'uniqueSpatialTilesAcrossShards':sum(int(x['uniqueSpatialTiles']) for x in aa),'apiResponseBytesAcrossShards':sum(int(x['apiResponseBytes']) for x in aa),'buildingCoverageMedian':statistics.median(coverage) if coverage else None,'buildingCoverageP90':statistics.quantiles(coverage,n=10,method='inclusive')[8] if len(coverage)>1 else None,'buildingCountMedian':statistics.median(counts) if counts else None,'buildingCountP90':statistics.quantiles(counts,n=10,method='inclusive')[8] if len(counts)>1 else None,'heightMedianOfCellMedians':statistics.median(heights) if heights else None,'heightAttributeCoverageMedian':statistics.median(hcov) if hcov else None,'fullJsonlGzipBytes':len(data),'fullJsonlGzipSha256':sha(data),'fullCsvGzipBytes':len(cdata),'fullCsvGzipSha256':sha(cdata),'approximationClass':'LEVEL_B_NOT_EXACT_FOOTPRINT','qaPass':ok,'scoringEffect':'none','globalNexusWrites':0,'crossProjectWrites':0}
 (a.out/'ECOSCAPE_PLATEAU_PRACTICAL_FULL_120662_B98_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 (a.out/'ECOSCAPE_PLATEAU_PRACTICAL_FULL_120662_B98_REPORT.md').write_text(f"# ECOSCAPE PLATEAU Practical Full Domain B98\n\n- Cells: {len(rows):,}\n- Unique: {len(set(ids)):,}\n- Duplicate: {dups}\n- Canonical order equal: {equal}\n- Request failures: {request_failures}\n- Status: {dict(cnt)}\n- Method: LOD1 attribute bounding-box intersection with roof-edge-area allocation\n- Approximation: Level B, not exact building footprint\n- QA pass: {ok}\n- Scoring effect: none\n",encoding='utf-8')
 (a.out/'SHARD_AUDITS.json').write_text(json.dumps(aa,ensure_ascii=False,indent=2))
 (a.out/'SHA256SUMS.txt').write_text(f'{sha(data)}  {fp.name}\n{sha(cdata)}  {cp.name}\n')
 print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0 if ok else 2)
if __name__=='__main__':main()
