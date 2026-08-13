#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, re, time, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE='https://www.archives.metro.tokyo.lg.jp/'
LIST=urllib.parse.urljoin(BASE,'list')
OUT=Path('out-tokyo-archives-boundary-search'); OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map historical-boundary-research/1.1','Accept-Language':'ja,en;q=0.8'})
COLLECTIONS=['collection_01','collection_03','collection_04','collection_05','collection_06','collection_07','collection_09','collection_10','collection_11','collection_12','collection_13','collection_15','collection_16','collection_17']
QUERIES=[
 {'id':'kozuka_1887_exact','field':'title','term':'千住小塚原旧刑場一部払下認可'},
 {'id':'kozuka_1890_exact','field':'title','term':'小塚原刑場跡ヲ官有墓地ニ編入'},
 {'id':'kozuka_broad','field':'free','term':'小塚原 刑場'},
 {'id':'kozuka_old_exec','field':'free','term':'小塚原 旧刑場'},
 {'id':'kozuka_senju','field':'free','term':'千住 小塚原'},
 {'id':'kozuka_disposition','field':'free','term':'小塚原 払下'},
 {'id':'kozuka_cemetery','field':'free','term':'小塚原 墓地'},
 {'id':'kozuka_official_land','field':'free','term':'小塚原 官有'},
 {'id':'kozuka_land_type','field':'free','term':'小塚原 地種目'},
 {'id':'execution_disposition','field':'free','term':'刑場 払下'},
 {'id':'suzugamori_1887_exact','field':'title','term':'旧鈴ヶ森刑場払下'},
 {'id':'suzugamori_1877_exact','field':'title','term':'鈴ヶ森刑場番小屋地所払下'},
 {'id':'suzugamori_broad','field':'free','term':'鈴ヶ森 刑場'},
 {'id':'suzugamori_old_exec','field':'free','term':'鈴ヶ森 御仕置場'},
 {'id':'suzugamori_death_ground','field':'free','term':'鈴ヶ森 死刑場'},
 {'id':'suzugamori_ooi','field':'free','term':'大井村 鈴ヶ森'},
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
 for tag in ['tr','li','article','section','div']:
  x=a.find_parent(tag)
  if x:
   txt=' '.join(x.get_text(' ',strip=True).split())
   if 5 <= len(txt) <= 4000: return x,txt
 return a.parent,' '.join(a.parent.get_text(' ',strip=True).split())

def detail_fields(soup):
 fields={}
 for tr in soup.find_all('tr'):
  cells=tr.find_all(['th','td'])
  if len(cells) < 2: continue
  key=' '.join(cells[0].get_text(' ',strip=True).split())
  val=' '.join(cells[1].get_text(' ',strip=True).split())
  if key and val and len(key) < 120:
   if key in fields and fields[key] != val: fields[key] += ' | ' + val
   else: fields[key]=val
 return fields

def detail_links(soup, base):
 out=[]
 for a in soup.find_all('a',href=True):
  href=urllib.parse.urljoin(base,a['href'])
  txt=' '.join(a.get_text(' ',strip=True).split())
  low=(href+' '+txt).lower()
  if any(k in low for k in ['digital','archive','image','img','fileentry','i-repository','meta_pub','viewer','iiif','download','画像','閲覧']):
   out.append({'text':txt[:500],'url':href})
 # Deduplicate while preserving order.
 seen=set(); dedup=[]
 for x in out:
  k=(x['text'],x['url'])
  if k not in seen: seen.add(k); dedup.append(x)
 return dedup

report={'base':BASE,'listUrl':LIST,'queries':[],'uniqueRecords':[],'detailAudits':[],
'rules':['public GET search form/detail pages only','no authentication/access-control bypass','catalog metadata is a source-acquisition gate, not boundary evidence','detail record metadata or digitization link is not itself a historic boundary','scoringEffect none until source image/text and location are reviewed']}
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
  body=' '.join(soup.get_text(' ',strip=True).split())
  term_hits=[]
  for term in [x for x in re.split(r'[ 　]+',q['term']) if x]:
   pos=body.find(term)
   if pos>=0: term_hits.append({'term':term,'snippet':body[max(0,pos-300):pos+700]})
  report['queries'].append({'id':q['id'],'field':q['field'],'term':q['term'],'url':r.url,'status':r.status_code,'bytes':len(r.content),'sha256':sha(r.content),'detailRecordCount':len(records),'records':records[:100],'termHits':term_hits[:20]})
 except Exception as e:
  report['queries'].append({'id':q['id'],'field':q['field'],'term':q['term'],'error':repr(e)})
 time.sleep(1.2)

report['uniqueRecords']=sorted(unique.values(),key=lambda x:(x['cls'],x['pkey']))
# Open all records found by execution-ground-specific searches, plus the 1887 land-type register itself.
for di,rec in enumerate(report['uniqueRecords'],1):
 found=set(rec.get('foundBy') or [])
 if found == {'land_type_register'} and not (rec['cls']=='collection_03' and rec['pkey']=='000118608'):
  continue
 try:
  r=S.get(rec['url'],timeout=60,allow_redirects=True); r.raise_for_status()
  fn=f"detail_{rec['cls']}_{rec['pkey']}.html"; (OUT/fn).write_bytes(r.content)
  soup=BeautifulSoup(r.text,'html.parser')
  body=' '.join(soup.get_text(' ',strip=True).split())
  fields=detail_fields(soup)
  links=detail_links(soup,r.url)
  report['detailAudits'].append({
   'cls':rec['cls'],'pkey':rec['pkey'],'url':r.url,'foundBy':rec.get('foundBy',[]),
   'status':r.status_code,'bytes':len(r.content),'sha256':sha(r.content),'fields':fields,
   'candidateDigitizationLinks':links[:100],
   'hasImageOrDigitalArchiveSignal':bool(links) or any(k in body for k in ['画像公開','デジタルアーカイブ','電磁的記録媒体番号']),
   'bodySnippet':body[:8000]
  })
 except Exception as e:
  report['detailAudits'].append({'cls':rec['cls'],'pkey':rec['pkey'],'url':rec['url'],'foundBy':rec.get('foundBy',[]),'error':repr(e)})
 time.sleep(1.2)

report['summary']={
 'queryCount':len(QUERIES),
 'successfulQueries':sum('error' not in q for q in report['queries']),
 'failedQueries':sum('error' in q for q in report['queries']),
 'uniqueDetailRecords':len(report['uniqueRecords']),
 'openedDetailRecords':sum('error' not in x for x in report['detailAudits']),
 'detailFetchFailures':sum('error' in x for x in report['detailAudits']),
 'detailRecordsWithDigitalSignal':sum(bool(x.get('hasImageOrDigitalArchiveSignal')) for x in report['detailAudits']),
}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report['summary'],ensure_ascii=False))
for x in report['detailAudits']:
 title=(x.get('fields') or {}).get('公開件名') or (x.get('fields') or {}).get('資料名称') or ''
 print(x.get('cls'),x.get('pkey'),title,x.get('foundBy'),len(x.get('candidateDigitizationLinks') or []))
