#!/usr/bin/env python3
from __future__ import annotations
import hashlib, html, json, re, sys, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

TARGET='https://catalog.library.metro.tokyo.lg.jp/iLisvirtual/?keycode=1&holcd=1123363915&type=1&count=50&autoMode=1'
OUT=Path('out-firemap-dbs'); OUT.mkdir(parents=True,exist_ok=True)
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 iyashiro-map research','Accept-Language':'ja,en;q=0.8'})
report={'target':TARGET,'materialCode':'1123363915','title':'本所区・向島区 [1933-1935]','pages':[],'scripts':[],'candidates':[],'downloadedImages':[],'rightsRule':'internal research only; do not publicly redistribute provider images without separate permission/terms check'}

def sha(b): return hashlib.sha256(b).hexdigest()
def get(url,ref=None,timeout=60):
    h={'Referer':ref} if ref else {}
    return s.get(url,headers=h,timeout=timeout,allow_redirects=True)

def add_candidate(u,source,kind):
    if not u: return
    u=html.unescape(u).replace('\\/','/')
    if u.startswith('//'): u='https:'+u
    u=urllib.parse.urljoin(source,u)
    if u not in [x['url'] for x in report['candidates']]: report['candidates'].append({'url':u,'source':source,'kind':kind})

r=get(TARGET); (OUT/'bookshelf.html').write_bytes(r.content)
report['pages'].append({'url':TARGET,'finalUrl':r.url,'status':r.status_code,'bytes':len(r.content),'sha256':sha(r.content)})
text=r.text
soup=BeautifulSoup(text,'html.parser')
# collect links/images/scripts
for tag in soup.find_all(['img','a','iframe','source']):
    for attr in ['src','href','data-src','data-original','data-url']:
        if tag.get(attr): add_candidate(tag.get(attr),r.url,f'{tag.name}:{attr}')
for tag in soup.find_all('script'):
    src=tag.get('src')
    if src:
        u=urllib.parse.urljoin(r.url,src)
        try:
            rr=get(u,r.url); body=rr.text; fn=f'script-{len(report["scripts"]):03d}.js'; (OUT/fn).write_text(body,encoding='utf-8',errors='replace')
            report['scripts'].append({'url':u,'status':rr.status_code,'bytes':len(rr.content),'savedAs':fn})
            for m in re.findall(r'''(?:https?:)?//[^\"'<>\s]+|[^\"'<>\s]+\.(?:jpg|jpeg|png|tif|tiff|jp2|pdf)(?:\?[^\"'<>\s]*)?|[^\"'<>\s]*(?:image|img|viewer|book|page|virtual)[^\"'<>\s]*''',body,re.I): add_candidate(m,u,'script-token')
        except Exception as e: report['scripts'].append({'url':u,'error':repr(e)})
    else:
        body=tag.get_text('\n')
        for m in re.findall(r'''(?:https?:)?//[^\"'<>\s]+|[^\"'<>\s]+\.(?:jpg|jpeg|png|tif|tiff|jp2|pdf)(?:\?[^\"'<>\s]*)?|[^\"'<>\s]*(?:image|img|viewer|book|page|virtual)[^\"'<>\s]*''',body,re.I): add_candidate(m,r.url,'inline-script-token')
# also regex whole HTML for onclick/API strings
for m in re.findall(r'''(?:https?:)?//[^\"'<>\s]+|[^\"'<>\s]+\.(?:jpg|jpeg|png|tif|tiff|jp2|pdf)(?:\?[^\"'<>\s]*)?|[^\"'<>\s]*(?:getimage|imageview|imageload|viewer|virtual|ajax|json)[^\"'<>\s]*''',text,re.I): add_candidate(m,r.url,'html-token')

# Probe same-origin candidates likely to reveal metadata or images.
seen=0
for c in list(report['candidates']):
    u=c['url']
    if urllib.parse.urlparse(u).netloc not in ('catalog.library.metro.tokyo.lg.jp','archive.library.metro.tokyo.lg.jp'): continue
    if any(x in u.lower() for x in ['logout','login','javascript:','mailto:']): continue
    if seen>=120: break
    seen+=1
    try:
        rr=get(u,r.url,30)
        ct=(rr.headers.get('content-type') or '').lower()
        rec={'url':u,'status':rr.status_code,'finalUrl':rr.url,'contentType':ct,'bytes':len(rr.content),'sha256':sha(rr.content)}
        c['probe']=rec
        if rr.ok and ct.startswith('image/') and len(rr.content)>50000:
            ext='jpg' if 'jpeg' in ct else ('png' if 'png' in ct else 'bin')
            fn=f'image-{len(report["downloadedImages"]):03d}.{ext}'
            (OUT/fn).write_bytes(rr.content)
            report['downloadedImages'].append({**rec,'savedAs':fn,'sourceCandidate':u})
        elif rr.ok and ('json' in ct or 'text' in ct or 'javascript' in ct) and len(rr.content)<5_000_000:
            body=rr.text
            fn=f'probe-{seen:03d}.txt'; (OUT/fn).write_text(body,encoding='utf-8',errors='replace')
            rec['savedAs']=fn
    except Exception as e: c['probe']={'url':u,'error':repr(e)}

report['summary']={'candidateCount':len(report['candidates']),'downloadedImageCount':len(report['downloadedImages'])}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w') as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report['summary'],ensure_ascii=False))
