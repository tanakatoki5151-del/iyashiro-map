#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, re, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

OUT=Path('out-priority-ndl-leads-v1'); OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map historical research/1.0','Accept-Language':'ja,en;q=0.8'})
LEADS=[
 {'id':'shibuya_cadastral_1935','url':'https://ndlsearch.ndl.go.jp/books/R100000039-I8311642','expected':'東京市渋谷区地籍図 地籍図 下巻'},
 {'id':'ichibancho_archaeology_1994','url':'https://ndlsearch.ndl.go.jp/books/R000000025-I011440005068493','expected':'一番町遺跡発掘調査報告書'},
 {'id':'ichibancho_fire_1943','url':'https://ndlsearch.ndl.go.jp/books/R100000103-I031_2798992','expected':'一番町橋木氏で火災'},
 {'id':'kitazawa_imai_factory_1929','url':'https://ndlsearch.ndl.go.jp/books/R100000002-I000000613751','expected':'噫今井工場長'},
 {'id':'meguro_historic_walk_1977','url':'https://ndlsearch.ndl.go.jp/books/R100000002-I000001361836','expected':'目黒区史跡散歩'},
]

def sha(b):return hashlib.sha256(b).hexdigest()
def compact(x):return ' '.join((x or '').split())

def parse_page(r):
 s=BeautifulSoup(r.text,'html.parser')
 title=compact((s.find('h1') or s.find('title')).get_text(' ',strip=True) if (s.find('h1') or s.find('title')) else '')
 text=compact(s.get_text(' ',strip=True))
 links=[]
 for a in s.find_all('a',href=True):
  href=urllib.parse.urljoin(r.url,a['href']); lab=compact(a.get_text(' ',strip=True))
  if href not in [x['href'] for x in links]: links.append({'label':lab[:500],'href':href})
 return title,text,links

report={'leads':[],'rules':['official NDL record page only in this stage','title/catalog metadata is not proof of spatial match or fatalities','outgoing provider links are recorded but not treated as evidence until fetched','scoringEffect none']}
for i,lead in enumerate(LEADS,1):
 rec={**lead}
 try:
  r=S.get(lead['url'],timeout=60,allow_redirects=True); r.raise_for_status()
  (OUT/f'{i:02d}_{lead["id"]}.html').write_bytes(r.content)
  title,text,links=parse_page(r)
  rec.update({'status':r.status_code,'finalUrl':r.url,'bytes':len(r.content),'sha256':sha(r.content),'pageTitle':title,'expectedTitleFound':lead['expected'] in text,'textPreview':text[:10000],'links':links[:150]})
  # High-signal snippets for this research workflow.
  snippets=[]
  for term in ['火災','死亡','死者','焼死','負傷','一番町','千代田区教育委員会','遺跡','代々木上原町','代々木大山町','代々木富ケ谷町','代々木西原町','工場','北沢']:
   p=text.find(term)
   if p>=0: snippets.append({'term':term,'snippet':text[max(0,p-400):p+1000]})
  rec['snippets']=snippets
 except Exception as e:
  rec['error']=repr(e)
 report['leads'].append(rec)
report['summary']={'leadCount':len(LEADS),'successful':sum('error' not in x for x in report['leads']),'failed':sum('error' in x for x in report['leads'])}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report['summary'],ensure_ascii=False))
for x in report['leads']:
 print('\n',x['id'],x.get('pageTitle'), 'expected=',x.get('expectedTitleFound'), 'error=',x.get('error'))
 for s in x.get('snippets',[]):print(s['term'],s['snippet'][:800])
