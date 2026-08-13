#!/usr/bin/env python3
import html, json, re, urllib.parse
from pathlib import Path
import requests
OUT=Path('out-utokyo-medical-juvenile-photo');OUT.mkdir(parents=True,exist_ok=True)
URL='https://umdb.um.u-tokyo.ac.jp/DImt/Miyake/photolist/recordlist.php?-max=100&-skip=351'
TARGET='IMTE_MK0001068'
r=requests.get(URL,timeout=60,headers={'User-Agent':'iyashiro-map historical research/1.0'})
r.raise_for_status();text=r.text;(OUT/'recordlist.html').write_text(text,encoding='utf-8')
rows=re.findall(r'<tr\b[^>]*>.*?</tr>',text,flags=re.I|re.S)
row=next((x for x in rows if TARGET in x),'')
(OUT/'target-row.html').write_text(row,encoding='utf-8')
links=[]
for href,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',row,flags=re.I|re.S):
    label=re.sub(r'<[^>]+>',' ',label);label=html.unescape(re.sub(r'\s+',' ',label)).strip()
    links.append({'label':label,'url':urllib.parse.urljoin(r.url,html.unescape(href))})
imgs=[]
for src in re.findall(r'<img\b[^>]*src=["\']([^"\']+)["\']',row,flags=re.I|re.S):
    imgs.append(urllib.parse.urljoin(r.url,html.unescape(src)))
summary={'target':TARGET,'catalogUrl':URL,'rowFound':bool(row),'rowText':html.unescape(re.sub(r'<[^>]+>',' ',row)),'links':links,'images':imgs,'scoringEffect':'none'}
(OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
