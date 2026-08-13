#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, urllib.parse
from pathlib import Path
import requests
from pypdf import PdfReader

OUT=Path('out-jica-tokyo-1986-site-history'); OUT.mkdir(parents=True,exist_ok=True)
DETAIL='https://openjicareport.jica.go.jp/360/360/360_000_10126050.html'
UA={'User-Agent':'iyashiro-map public historical research/1.0'}
KEYWORDS=['西原','新設','用地','敷地','東京医療少年院','少年院','移転','東京国際研修センター','昭和60年6月','渋谷区']

def sha(b:bytes): return hashlib.sha256(b).hexdigest()

report={'detailUrl':DETAIL,'detail':{},'links':[],'downloads':[],'keywordHits':[],'qualityRule':'JICA public reports are used to test site succession only. No same-parcel conclusion without explicit text/map/land record. scoringEffect=none.'}
r=requests.get(DETAIL,headers=UA,timeout=90,allow_redirects=True)
report['detail']={'status':r.status_code,'finalUrl':r.url,'contentType':r.headers.get('content-type',''),'bytes':len(r.content),'sha256':sha(r.content)}
if r.status_code==200:
    (OUT/'detail.html').write_bytes(r.content)
    text=r.text
    for href in re.findall(r'href=["\']([^"\']+)["\']',text,flags=re.I):
        u=urllib.parse.urljoin(r.url,href)
        if u not in report['links']: report['links'].append(u)
    candidates=[u for u in report['links'] if any(x in u.lower() for x in ['pdf','report','download','openjicareport'])]
    for i,u in enumerate(candidates[:50]):
        row={'url':u}
        try:
            q=requests.get(u,headers=UA,timeout=120,allow_redirects=True)
            ct=q.headers.get('content-type','')
            row.update({'status':q.status_code,'finalUrl':q.url,'contentType':ct,'bytes':len(q.content),'sha256':sha(q.content)})
            if q.status_code==200 and (q.content[:4]==b'%PDF' or 'application/pdf' in ct):
                p=OUT/f'candidate-{i:02d}.pdf'; p.write_bytes(q.content); row['savedAs']=p.name
                try:
                    reader=PdfReader(str(p)); pages=[]
                    for pi,page in enumerate(reader.pages):
                        t=page.extract_text() or ''
                        if any(k in t for k in KEYWORDS):
                            snippets=[]
                            for k in KEYWORDS:
                                pos=t.find(k)
                                if pos>=0: snippets.append({'keyword':k,'snippet':re.sub(r'\s+',' ',t[max(0,pos-180):pos+420])})
                            pages.append({'pageIndex':pi,'snippets':snippets})
                    if pages: report['keywordHits'].append({'file':p.name,'pages':pages})
                except Exception as exc: row['pdfTextError']=f'{type(exc).__name__}: {exc}'
        except Exception as exc: row['error']=f'{type(exc).__name__}: {exc}'
        report['downloads'].append(row)
(OUT/'SUMMARY.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps({'detail':report['detail'],'linkCount':len(report['links']),'downloadCount':len(report['downloads']),'keywordHitFiles':len(report['keywordHits'])},ensure_ascii=False,indent=2))
