#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, time, zipfile, requests
BASE='https://nlftp.mlit.go.jp/kokjo/inspect/landclassification/land/land_history_2011/mapdata'
MAPS=['533946','533926','533944','533924','533904','533942','533922','533902','523964']
out=Path('out-land-history/combined9'); out.mkdir(parents=True, exist_ok=True)
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map-research/1.0'})
report={'startedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'files':{}}
for m in MAPS:
    fn=f'{m}_gisdata.zip'; u=f'{BASE}/{m}/{fn}'; p=out/fn
    r=s.get(u,timeout=120); r.raise_for_status(); p.write_bytes(r.content)
    if not zipfile.is_zipfile(p): raise RuntimeError(f'invalid zip {fn}')
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    with zipfile.ZipFile(p) as z: members=z.namelist()
    report['files'][m]={'url':u,'bytes':p.stat().st_size,'sha256':h,'members':members}
report['finishedAt']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
(out/'combined9-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'SHA256SUMS.txt').open('w') as f:
    for m in MAPS:
        p=out/f'{m}_gisdata.zip'; f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps({'downloaded':len(MAPS),'maps':MAPS},ensure_ascii=False))
