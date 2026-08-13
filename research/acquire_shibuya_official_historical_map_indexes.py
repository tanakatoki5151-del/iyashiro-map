#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
import requests

OUT=Path('out-shibuya-official-map-indexes');OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session();S.headers.update({'User-Agent':'iyashiro-map historical-map-research/1.0','Accept-Language':'ja,en;q=0.8'})
SOURCES=[
 {'id':'fire_insurance_index','title':'渋谷区火災保険特殊地図索引','url':'https://www.lib.city.shibuya.tokyo.jp/uploads/2022/06/99-61_kahozu_sakuin.pdf','file':'01_渋谷区火災保険特殊地図索引.pdf'},
 {'id':'old_aza_boundary','title':'明治22年〜昭和初期 渋谷区域字名・字界地図','url':'https://www.lib.city.shibuya.tokyo.jp/uploads/2022/06/meiji22nen_shouwashoki-shibuyakuikijimei-jikaitizu.pdf','file':'02_明治22年-昭和初期_渋谷区域字名・字界地図.pdf'},
 {'id':'town_boundary_overlay','title':'渋谷区町名・町界重ね地図','url':'https://www.lib.city.shibuya.tokyo.jp/uploads/2022/06/shibuyakunochoumei-choukaikasanetizu.pdf','file':'03_渋谷区町名・町界重ね地図.pdf'},
]
report={'sources':[],'rules':['official Shibuya City Library public PDFs only','preserve source URL and SHA256','these indexes/maps are control/source-discovery material, not proof of absence or major-history geometry','scoringEffect none']}
for src in SOURCES:
 rec={**src}
 try:
  r=S.get(src['url'],timeout=60,allow_redirects=True);r.raise_for_status()
  rec.update({'status':r.status_code,'finalUrl':r.url,'contentType':r.headers.get('content-type'),'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()})
  if 'pdf' in (r.headers.get('content-type') or '').lower() or r.content[:4]==b'%PDF':
   (OUT/src['file']).write_bytes(r.content);rec['saved']=True
  else:rec['saved']=False;rec['error']='response_not_pdf'
 except Exception as e:rec['error']=repr(e)
 report['sources'].append(rec);time.sleep(1)
report['summary']={'sourceCount':len(SOURCES),'success':sum(bool(x.get('saved')) for x in report['sources']),'failed':sum(not x.get('saved') for x in report['sources'])}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
