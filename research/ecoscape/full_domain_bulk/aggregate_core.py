#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,gzip,hashlib,io,json,zlib
from collections import Counter
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def cj(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def grid(path):
 d=json.loads(path.read_text()); comp=base64.b64decode(d['maskZlibBase64']); assert sha(comp)==d['compressedSha256']; mask=zlib.decompress(comp); assert sha(mask)==d['maskSha256']; out=[]
 for r in range(int(d['rows'])):
  for c in range(int(d['columns'])):
   i=r*int(d['columns'])+c
   if mask[i//8]&(1<<(7-i%8)): out.append(f'g{r}-{c}')
 assert len(out)==120662 and out[0]==d['firstCellId'] and out[-1]==d['lastCellId']; return out

def readgz(p):
 with gzip.open(p,'rt',encoding='utf-8') as f:
  for line in f:
   if line.strip(): yield json.loads(line)
def gz(rows):
 b=io.BytesIO()
 with gzip.GzipFile(fileobj=b,mode='wb',mtime=0) as g:
  for r in rows:g.write(cj(r)+b'\n')
 return b.getvalue()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--grid',type=Path,required=True); ap.add_argument('--input',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
 exp=grid(a.grid); files=sorted(a.input.rglob(f'{a.source.upper()}_E3_S*_FACTS.jsonl.gz')); assert len(files)==25,len(files); rows=[]
 for p in files:rows.extend(readgz(p))
 rows.sort(key=lambda x:int(x['ordinal'])); ids=[x['cellId'] for x in rows]; cnt=Counter(x['status'] for x in rows); errors=cnt.get('ERROR',0); dup=len(ids)-len(set(ids)); missing=len(exp)-len(rows); equal=ids==exp
 ok=len(rows)==120662 and dup==0 and missing==0 and equal and errors==0
 data=gz(rows); fp=a.out/f'ECOSCAPE_{a.source.upper()}_E3_FULL_120662_B80.jsonl.gz'; fp.write_bytes(data)
 manifests=sorted(a.input.rglob(f'{a.source.upper()}_E3_S*_MANIFEST.json')); shard_sha=[hashlib.sha256(p.read_bytes()).hexdigest() for p in manifests]
 report={'buildId':f'ecos-e3-b80-{a.source}-full-domain','source':a.source,'expectedCells':120662,'actualCells':len(rows),'uniqueCells':len(set(ids)),'duplicateCount':dup,'silentMissing':missing,'canonicalSetAndOrderEqual':equal,'statusCounts':dict(cnt),'shardCount':len(files),'shardManifestSha256':shard_sha,'fullFactsSha256':sha(data),'qaPass':ok,'scoringEffect':'none','globalNexusWrites':0,'crossProjectWrites':0}
 (a.out/f'ECOSCAPE_{a.source.upper()}_E3_FULL_120662_B80_AUDIT.json').write_bytes(cj(report)); (a.out/'SHA256SUMS.txt').write_text(f"{sha(data)}  {fp.name}\n",encoding='utf-8'); print(json.dumps(report,ensure_ascii=False,indent=2)); raise SystemExit(0 if ok else 2)
if __name__=='__main__':main()
