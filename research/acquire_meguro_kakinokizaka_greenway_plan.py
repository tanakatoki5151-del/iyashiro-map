#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, requests, fitz

URL='https://www.city.meguro.tokyo.jp/documents/1026/r1sakura_keikaku_kakinoki-komazawa.pdf'
OUT=Path('out-meguro-kakinokizaka-greenway-plan'); OUT.mkdir(parents=True,exist_ok=True)
r=requests.get(URL,timeout=120,headers={'User-Agent':'iyashiro-map historical watercourse research/1.0'})
r.raise_for_status(); pdf=OUT/'official-plan.pdf'; pdf.write_bytes(r.content)
doc=fitz.open(pdf)
rendered=[]
# PDF pages 7 and 8 in human numbering are indices 6 and 7; include target-route page 2 as context too.
for i in [2,6,7,8]:
    if i>=len(doc): continue
    page=doc[i]
    pix=page.get_pixmap(matrix=fitz.Matrix(2.5,2.5),alpha=False)
    fn=OUT/f'page-{i+1:02d}.png'; pix.save(fn)
    rendered.append({'pageIndex':i,'pageNumber':i+1,'file':fn.name,'width':pix.width,'height':pix.height,'sha256':hashlib.sha256(fn.read_bytes()).hexdigest()})
summary={'sourceUrl':URL,'pdfBytes':len(r.content),'pdfSha256':hashlib.sha256(r.content).hexdigest(),'pageCount':len(doc),'rendered':rendered,'qualityRule':'Official plan proves current greenway is built over the culverted river. Exact historical centerline/cell intersection still requires map alignment; scoringEffect=none.'}
(OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
