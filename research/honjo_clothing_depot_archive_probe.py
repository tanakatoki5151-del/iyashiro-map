#!/usr/bin/env python3
# Reproducible acquisition of the official 1932 Honjo clothing-depot archive.
from pathlib import Path
import hashlib,json,re,zipfile,requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
BASE='https://tokyoireikyoukai.or.jp/museum/archive/hifukusyouseki.html'
out=Path('out-honjo'); out.mkdir(exist_ok=True)
s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0 iyashiro-map research'
r=s.get(BASE,timeout=60); r.raise_for_status(); (out/'catalog.html').write_bytes(r.content)
soup=BeautifulSoup(r.text,'html.parser')
links=[]
for a in soup.find_all('a',href=True):
 u=urljoin(BASE,a['href']); txt=a.get_text(' ',strip=True)
 if '被服廠跡' in txt or u.lower().endswith('.zip'): links.append({'text':txt,'url':u})
(out/'links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
report=[]
for i,x in enumerate(links):
 try:
  rr=s.get(x['url'],timeout=180); rec={'text':x['text'],'url':x['url'],'status':rr.status_code,'bytes':len(rr.content),'contentType':rr.headers.get('content-type')}
  p=out/f'download-{i}.bin'; p.write_bytes(rr.content); rec['sha256']=hashlib.sha256(rr.content).hexdigest(); rec['zipValid']=zipfile.is_zipfile(p)
  if rec['zipValid']:
   zp=out/f'download-{i}.zip'; p.replace(zp); rec['savedAs']=zp.name
   with zipfile.ZipFile(zp) as z: rec['members']=z.namelist()
  report.append(rec)
 except Exception as e: report.append({'text':x['text'],'url':x['url'],'error':repr(e)})
(out/'download-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
short=[]
for zp in out.glob('download-*.zip'):
 with zipfile.ZipFile(zp) as z:
  for n in z.namelist():
   if re.search(r'(第?0?8|第八|敷地|区画|配置|平面|図|map|plan)',n,re.I): short.append({'zip':zp.name,'member':n})
(out/'shortlist.json').write_text(json.dumps(short,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'links':len(links),'archives':sum(1 for x in report if x.get('zipValid')),'shortlist':len(short)},ensure_ascii=False))
