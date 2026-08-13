#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE='https://www.archives.metro.tokyo.lg.jp/'
OUT=Path('out-tokyo-archives-search-probe'); OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map historical research','Accept-Language':'ja,en;q=0.8'})

def sha(b): return hashlib.sha256(b).hexdigest()

r=S.get(BASE,timeout=60); r.raise_for_status()
(OUT/'root.html').write_bytes(r.content)
soup=BeautifulSoup(r.text,'html.parser')
forms=[]
for fi,form in enumerate(soup.find_all('form')):
    rec={'index':fi,'action':urllib.parse.urljoin(r.url,form.get('action') or ''),'method':(form.get('method') or 'get').lower(),'controls':[]}
    for tag in form.find_all(['input','select','textarea','button']):
        c={'tag':tag.name,'name':tag.get('name'),'type':tag.get('type'),'value':tag.get('value'),'id':tag.get('id')}
        if tag.name=='select':
            c['options']=[{'value':o.get('value'),'text':o.get_text(' ',strip=True),'selected':o.has_attr('selected')} for o in tag.find_all('option')[:100]]
        rec['controls'].append(c)
    forms.append(rec)
(OUT/'FORMS.json').write_text(json.dumps(forms,ensure_ascii=False,indent=2),encoding='utf-8')

# Record the form signatures only. A second-stage search script should be generated after reviewing these names;
# do not guess request fields and do not crawl arbitrary records.
report={'base':BASE,'status':r.status_code,'bytes':len(r.content),'sha256':sha(r.content),'formCount':len(forms),'forms':[{'index':x['index'],'action':x['action'],'method':x['method'],'namedControls':[c['name'] for c in x['controls'] if c.get('name')]} for x in forms]}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report,ensure_ascii=False))
