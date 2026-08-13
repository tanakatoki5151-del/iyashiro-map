#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, re, time, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE='https://www.archives.metro.tokyo.lg.jp/'
LIST=urllib.parse.urljoin(BASE,'list')
OUT=Path('out-tokyo-archives-boundary-search'); OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map historical-boundary-research/1.0','Accept-Language':'ja,en;q=0.8'})
COLLECTIONS=['collection_01','collection_03','collection_04','collection_05','collection_06','collection_07','collection_09','collection_10','collection_11','collection_12','collection_13','collection_15','collection_16','collection_17']
QUERIES=[
 {'id':'kozuka_1887_exact','field':'title','term':'千住小塚原旧刑場一部払下認可'},
 {'id':'kozuka_1890_exact','field':'title','term':'小塚原刑場跡ヲ官有墓地ニ編入'},
 {'id':'kozuka_broad','field':'free','term':'小塚原 刑場'},
 {'id':'kozuka_disposition','field':'free','term':'小塚原 払下'},
 {'id':'kozuka_land_type','field':'free','term':'小塚原 地種目'},
 {'id':'suzugamori_1887_exact','field':'title','term':'旧鈴ヶ森刑場払下'},
 {'id':'suzugamori_1877_exact','field':'title','term':'鈴ヶ森刑場番小屋地所払下'},
 {'id':'suzugamori_broad','field':'free','term':'鈴ヶ森 刑場'},
 {'id':'suzugamori_disposition','field':'free','term':'鈴ヶ森 払下'},
 {'id':'land_type_register','field':'title','term':'地種目変換簿'},
]

def sha(b): return hashlib.sha256(b).hexdigest()

def params_for(q):
 p=[('secIdx','0'),('cls','top'),('pn','1')]
 for c in COLLECTIONS: p.append(('chkCls',c))
 p += [('selectedTree',''),('dispnum','100'),('sort','1'),('order','0')]
 # Public search form fields observed from official HTML:
 # c12_f = フリーワード, c13_f = 資料名/タイトル/件名.
 if q['field']=='title':
  p += [('c13_f',q['term']),('c13_a','1'),('c13_l','1')]
 else:
  p += [('c12_f',q['term']),('c12_a','1'),('c12_l','1')]
 return p

def nearest_record_container(a):
 # Prefer list/table container without swallowing the whole page.
 for tag in ['tr','li','article','section','div']:
  x=a.find_parent(tag)
  if x:
   txt=' '.join(x.get_text(' ',strip=True).split())
   if 5 <= len(txt) <= 4000:
    return x,txt
 return a.parent,' '.join(a.parent.get_text(' ',strip=True).split())

report={'base':BASE,'listUrl':LIST,'queries':[],'uniqueRecords':[],'rules':['public GET search form only','no authentication/access-control bypass','catalog metadata is a source-acquisition gate, not boundary evidence','detail record must be opened before claims about attachments/geometry']}
unique={}
for qi,q in enumerate(QUERIES,1):
 try:
  r=S.get(LIST,params=params_for(q),timeout=60,allow_redirects=True); r.raise_for_status()
  fn=f"{qi:02d}_{q['id']}.html"; (OUT/fn).write_bytes(r.content)
  soup=BeautifulSoup(r.text,'html.parser')
  records=[]
  for a in soup.find_all('a',href=True):
   href=urllib.parse.urljoin(r.url,a['href'])
   if '/detail?' not in href or 'pkey=' not in href: continue
   m=re.search(r'[?&]pkey=([^&]+)',href); pkey=urllib.parse.unquote(m.group(1)) if m else ''
   cm=re.search(r'[?&]cls=([^&]+)',href); cls=urllib.parse.unquote(cm.group(1)) if cm else ''
   _container,txt=nearest_record_container(a)
   rec={'pkey':pkey,'cls':cls,'url':href,'linkText':' '.join(a.get_text(' ',strip=True).split()),'context':txt[:3500]}
   key=(cls,pkey)
   if key not in {(x['cls'],x['pkey']) for x in records}: records.append(rec)
   if key not in unique or len(txt)>len(unique[key]['context']): unique[key]={**rec,'foundBy':[]}
   if q['id'] not in unique[key]['foundBy']: unique[key]['foundBy'].append(q['id'])
  # Save snippets of explicit terms even if no detail link.
  body=' '.join(soup.get_text(' ',strip=True).split())
  term_hits=[]
  for term in [x for x in re.split(r'[ 　]+',q['term']) if x]:
   pos=body.find(term)
   if pos>=0: term_hits.append({'term':term,'snippet':body[max(0,pos-300):pos+700]})
  report['queries'].append({'id':q['id'],'field':q['field'],'term':q['term'],'url':r.url,'status':r.status_code,'bytes':len(r.content),'sha256':sha(r.content),'detailRecordCount':len(records),'records':records[:100],'termHits':term_hits[:20]})
 except Exception as e:
  report['queries'].append({'id':q['id'],'field':q['field'],'term':q['term'],'error':repr(e)})
 time.sleep(1.5)
report['uniqueRecords']=sorted(unique.values(),key=lambda x:(x['cls'],x['pkey']))
report['summary']={'queryCount':len(QUERIES),'successfulQueries':sum('error' not in q for q in report['queries']),'failedQueries':sum('error' in q for q in report['queries']),'uniqueDetailRecords':len(report['uniqueRecords'])}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report['summary'],ensure_ascii=False))
for x in report['uniqueRecords'][:50]: print(x['cls'],x['pkey'],x['linkText'],x['foundBy'])
