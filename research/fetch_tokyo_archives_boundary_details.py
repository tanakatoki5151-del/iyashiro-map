#!/usr/bin/env python3
from __future__ import annotations

import hashlib,json,re,time,urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

OUT=Path('out-tokyo-archives-boundary-details'); OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map historical-boundary-research/1.0','Accept-Language':'ja,en;q=0.8'})
RECORDS=[
 ('suzugamori_1876_instruction','collection_04','313497'),
 ('suzugamori_1876_draft','collection_04','313498'),
 ('suzugamori_1876_disposition','collection_04','322882'),
 ('suzugamori_1877_hut_application','collection_04','326830'),
 ('suzugamori_1877_hut_handover','collection_05','1636974'),
 ('kozukappara_1871_abolition','collection_05','1640119'),
 ('land_type_register_1887','collection_03','000118608'),
]
BASE='https://www.archives.metro.tokyo.lg.jp/detail'

def sha(b):return hashlib.sha256(b).hexdigest()
def compact(s):return ' '.join((s or '').split())

def parse_table(soup):
 data={}
 for tr in soup.find_all('tr'):
  cells=tr.find_all(['th','td'])
  if len(cells)>=2:
   k=compact(cells[0].get_text(' ',strip=True)); v=compact(' '.join(c.get_text(' ',strip=True) for c in cells[1:]))
   if k and v:
    if k in data: data[k]+=' | '+v
    else:data[k]=v
 return data

report={'records':[],'rules':['public detail pages only','copy/viewing metadata does not imply image is online','record title/metadata may define a disposal action but not its exact geometry','scoringEffect none']}
for i,(rid,cls,pkey) in enumerate(RECORDS,1):
 url=BASE+'?'+urllib.parse.urlencode({'cls':cls,'pkey':pkey})
 rec={'id':rid,'cls':cls,'pkey':pkey,'url':url}
 try:
  r=S.get(url,timeout=60,allow_redirects=True); r.raise_for_status(); (OUT/f'{i:02d}_{rid}.html').write_bytes(r.content)
  soup=BeautifulSoup(r.text,'html.parser'); text=compact(soup.get_text(' ',strip=True)); data=parse_table(soup)
  links=[]
  for a in soup.find_all('a',href=True):
   href=urllib.parse.urljoin(r.url,a['href']); lab=compact(a.get_text(' ',strip=True))
   if href not in [x['href'] for x in links]:links.append({'label':lab,'href':href})
  image_like=[]
  for tag in soup.find_all(['img','a'],href=True) + soup.find_all('img',src=True):
   u=tag.get('href') or tag.get('src'); u=urllib.parse.urljoin(r.url,u)
   if any(x in u.lower() for x in ['image','img','file','download','viewer','jpg','jpeg','png','tif','pdf']): image_like.append(u)
  rec.update({'status':r.status_code,'finalUrl':r.url,'bytes':len(r.content),'sha256':sha(r.content),'title':compact((soup.find('h1') or soup.find('title')).get_text(' ',strip=True) if (soup.find('h1') or soup.find('title')) else ''),'fields':data,'textPreview':text[:12000],'links':links[:150],'imageLikeUrls':list(dict.fromkeys(image_like))[:100]})
  snippets=[]
  for term in ['払下','御仕置場','刑場','番小屋','面積','坪','反','畝','歩','図','絵図','添付','地番','大井村','小塚原','地種目','複写','撮影','画像']:
   p=text.find(term)
   if p>=0: snippets.append({'term':term,'snippet':text[max(0,p-500):p+1200]})
  rec['snippets']=snippets
 except Exception as e:rec['error']=repr(e)
 report['records'].append(rec);time.sleep(1)
report['summary']={'recordCount':len(RECORDS),'success':sum('error' not in x for x in report['records']),'failed':sum('error' in x for x in report['records']),'onlineImageCandidateCount':sum(len(x.get('imageLikeUrls',[])) for x in report['records'])}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report['summary'],ensure_ascii=False))
for r in report['records']:
 print('\n',r['id'],r.get('title'),r.get('error'))
 for k in ['資料名称','公開件名','文書年度（西暦）','起案年月日（西暦）','収録先の名称','収録先簿冊の資料ＩＤ','請求番号','綴込番号','公開区分','利用条件','複写コード','複写条件','検索手段','16mmMFコマ番号','電磁的記録媒体番号']:
  if k in r.get('fields',{}):print(k,':',r['fields'][k])
