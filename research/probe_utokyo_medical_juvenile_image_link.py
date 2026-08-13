#!/usr/bin/env python3
import hashlib, html, json, re, urllib.parse
from pathlib import Path
import requests

OUT=Path('out-utokyo-medical-juvenile-photo'); OUT.mkdir(parents=True,exist_ok=True)
URL='https://umdb.um.u-tokyo.ac.jp/DImt/Miyake/photolist/recordlist.php?-max=100&-skip=351'
TARGET='IMTE_MK0001068'
UA={'User-Agent':'iyashiro-map historical research/1.1'}

r=requests.get(URL,timeout=60,headers=UA)
r.raise_for_status(); text=r.text; (OUT/'recordlist.html').write_text(text,encoding='utf-8')
rows=re.findall(r'<tr\b[^>]*>.*?</tr>',text,flags=re.I|re.S)
row=next((x for x in rows if TARGET in x),'')
(OUT/'target-row.html').write_text(row,encoding='utf-8')
links=[]
for href,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',row,flags=re.I|re.S):
    label=re.sub(r'<[^>]+>',' ',label); label=html.unescape(re.sub(r'\s+',' ',label)).strip()
    links.append({'label':label,'url':urllib.parse.urljoin(r.url,html.unescape(href))})
imgs=[]
for src in re.findall(r'<img\b[^>]*src=["\']([^"\']+)["\']',row,flags=re.I|re.S):
    imgs.append(urllib.parse.urljoin(r.url,html.unescape(src)))

probes=[]
for thumb in imgs:
    candidates=[thumb]
    for dirname in ['Photo','PhotoLARGE','PhotoBIG','PhotoFULL','PhotoIMAGE']:
        candidates.append(thumb.replace('/PhotoTHUMB/',f'/{dirname}/'))
    for u in dict.fromkeys(candidates):
        rec={'url':u}
        try:
            q=requests.get(u,timeout=60,headers=UA,allow_redirects=True)
            rec.update({'status':q.status_code,'contentType':q.headers.get('content-type',''),'bytes':len(q.content),'finalUrl':q.url})
            if q.status_code==200 and q.content and (q.headers.get('content-type','').startswith('image/') or q.content[:3]==b'\xff\xd8\xff'):
                digest=hashlib.sha256(q.content).hexdigest(); rec['sha256']=digest
                name=re.sub(r'[^A-Za-z0-9._-]+','_',urllib.parse.urlparse(u).path.strip('/'))
                path=OUT/name; path.write_bytes(q.content); rec['savedAs']=path.name
        except Exception as exc:
            rec['error']=f'{type(exc).__name__}: {exc}'
        probes.append(rec)

summary={
    'target':TARGET,
    'catalogUrl':URL,
    'rowFound':bool(row),
    'rowText':html.unescape(re.sub(r'<[^>]+>',' ',row)),
    'links':links,
    'images':imgs,
    'publicImageProbes':probes,
    'qualityRule':'Only public HTTP image responses are saved. A photo image can support visual facility-form comparison but cannot by itself establish the historical parcel. scoringEffect=none.',
    'scoringEffect':'none'
}
(OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS.txt':
            f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
