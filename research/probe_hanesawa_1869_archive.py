#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, re, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

TARGET='https://dasasp03.i-repository.net/il/meta_pub/G0000002tokyoarchv03_0001165130001'
OUT=Path('out-hanesawa-1869'); OUT.mkdir(parents=True,exist_ok=True)
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map research','Accept-Language':'ja,en;q=0.8'})
report={'target':TARGET,'archiveRecord':'東京都公文書館 1869 羽根沢村牧野屋敷取調絵図2葉','pages':[],'candidates':[],'downloaded':[],'qualityRule':'pre-cemetery context/control-point source only; not the cemetery boundary'}

def sha(b): return hashlib.sha256(b).hexdigest()
def add(u,src,kind):
 if not u:return
 u=html.unescape(u).replace('\\/','/')
 if u.startswith('//'):u='https:'+u
 u=urllib.parse.urljoin(src,u)
 if u not in [x['url'] for x in report['candidates']]:report['candidates'].append({'url':u,'source':src,'kind':kind})

r=s.get(TARGET,timeout=60,allow_redirects=True); r.raise_for_status(); (OUT/'record.html').write_bytes(r.content)
report['pages'].append({'url':TARGET,'finalUrl':r.url,'status':r.status_code,'bytes':len(r.content),'sha256':sha(r.content)})
soup=BeautifulSoup(r.text,'html.parser')
for tag in soup.find_all(['img','a','iframe','source']):
 for a in ['src','href','data-src','data-url','data-original']:
  if tag.get(a): add(tag.get(a),r.url,f'{tag.name}:{a}')
for tag in soup.find_all('script'):
 src=tag.get('src')
 if src:
  u=urllib.parse.urljoin(r.url,src)
  try:
   rr=s.get(u,headers={'Referer':r.url},timeout=45); txt=rr.text; fn=f'script-{len(report["pages"]):03d}.js'; (OUT/fn).write_text(txt,encoding='utf-8',errors='replace'); report['pages'].append({'url':u,'status':rr.status_code,'bytes':len(rr.content),'savedAs':fn})
   for m in re.findall(r'''(?:https?:)?//[^\"'<>\s]+|[^\"'<>\s]+\.(?:jpg|jpeg|png|tif|tiff|jp2|pdf)(?:\?[^\"'<>\s]*)?|[^\"'<>\s]*(?:image|iiif|manifest|viewer|download|content)[^\"'<>\s]*''',txt,re.I): add(m,u,'script-token')
  except Exception as e: report['pages'].append({'url':u,'error':repr(e)})
 else:
  txt=tag.get_text('\n')
  for m in re.findall(r'''(?:https?:)?//[^\"'<>\s]+|[^\"'<>\s]+\.(?:jpg|jpeg|png|tif|tiff|jp2|pdf)(?:\?[^\"'<>\s]*)?|[^\"'<>\s]*(?:image|iiif|manifest|viewer|download|content)[^\"'<>\s]*''',txt,re.I): add(m,r.url,'inline-token')
# Try likely same-origin candidates and archive asset hosts.
for i,c in enumerate(list(report['candidates'])[:250]):
 u=c['url']; host=urllib.parse.urlparse(u).netloc
 if not any(k in host for k in ['i-repository.net','tokyo','repository']): continue
 if any(x in u.lower() for x in ['javascript:','login','logout']): continue
 try:
  rr=s.get(u,headers={'Referer':r.url},timeout=30,allow_redirects=True); ct=(rr.headers.get('content-type') or '').lower(); rec={'url':u,'status':rr.status_code,'finalUrl':rr.url,'contentType':ct,'bytes':len(rr.content),'sha256':sha(rr.content)}; c['probe']=rec
  if rr.ok and (ct.startswith('image/') or 'pdf' in ct) and len(rr.content)>50000:
   ext='pdf' if 'pdf' in ct else ('png' if 'png' in ct else 'jpg'); fn=f'asset-{len(report["downloaded"]):03d}.{ext}'; (OUT/fn).write_bytes(rr.content); rec['savedAs']=fn; report['downloaded'].append(rec)
  elif rr.ok and ('json' in ct or 'text' in ct or 'javascript' in ct) and len(rr.content)<3_000_000:
   fn=f'probe-{i:03d}.txt'; (OUT/fn).write_text(rr.text,encoding='utf-8',errors='replace'); rec['savedAs']=fn
 except Exception as e:c['probe']={'url':u,'error':repr(e)}
report['summary']={'candidateCount':len(report['candidates']),'downloadedCount':len(report['downloaded'])}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report['summary'],ensure_ascii=False))
