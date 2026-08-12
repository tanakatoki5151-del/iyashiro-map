#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, re, time, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
import requests

API='https://ndlsearch.ndl.go.jp/api/opensearch'
OUT=Path('out-priority-ndl-v2-fast'); OUT.mkdir(parents=True,exist_ok=True)
CELLS=[
(1,'東京都渋谷区上原二丁目','渋谷 上原','g194-226',89854),
(2,'東京都渋谷区上原三丁目','渋谷 上原','g195-224',90314),
(3,'東京都目黒区駒場四丁目','目黒 駒場','g199-227',92165),
(4,'東京都渋谷区大山町','渋谷 大山町','g187-221',86615),
(5,'東京都目黒区東が丘一丁目','目黒 東が丘','g233-217',107863),
(6,'東京都世田谷区北沢五丁目','世田谷 北沢','g188-216',87072),
(7,'東京都世田谷区北沢一丁目','世田谷 北沢','g199-219',92157),
(8,'東京都目黒区柿の木坂二丁目','目黒 柿の木坂','g239-220',110638),
(9,'東京都目黒区目黒本町五丁目','目黒 目黒本町','g244-243',112971),
(10,'東京都千代田区一番町','千代田 一番町','g169-281',78359)]
KEYS=[
('detention_execution_pow','刑場'),('detention_execution_pow','監獄'),
('cemetery_burial_remains','墓地'),('crematorium','火葬'),
('wartime_temporary_burial','仮埋葬'),('wartime_temporary_burial','戦災'),
('major_fire_explosion_incident','火災'),('major_fire_explosion_incident','爆発'),
('military_land_pow','陸軍'),('old_watercourse','暗渠'),
('historic_land_use','地籍図'),('folklore','民俗'),('primary_source_leads','公図')]
NS={'atom':'http://www.w3.org/2005/Atom','dc':'http://purl.org/dc/elements/1.1/','dcterms':'http://purl.org/dc/terms/','opensearch':'http://a9.com/-/spec/opensearch/1.1/'}
s=requests.Session(); s.headers.update({'User-Agent':'iyashiro-map-research/1.0 metadata scan','Accept-Language':'ja,en;q=0.8'})

def text(e,p):
 x=e.find(p,NS); return (x.text or '').strip() if x is not None and x.text else ''
def parse(b):
 root=ET.fromstring(b); tt=text(root,'opensearch:totalResults')
 try: total=int(tt)
 except: total=0
 entries=root.findall('atom:entry',NS) or root.findall('item')
 out=[]
 for e in entries[:8]:
  title=text(e,'atom:title') or text(e,'title') or text(e,'dc:title')
  creator=text(e,'dc:creator'); date=text(e,'dc:date') or text(e,'dcterms:date')
  desc=text(e,'dc:description') or text(e,'dcterms:description') or text(e,'atom:summary')
  ids=[(x.text or '').strip() for x in e.findall('dc:identifier',NS) if x.text]
  links=[x.attrib.get('href','') for x in e.findall('atom:link',NS) if x.attrib.get('href')]
  out.append({'title':title,'creator':creator,'date':date,'description':re.sub(r'\s+',' ',desc)[:1000],'identifiers':' | '.join(ids)[:1000],'links':' | '.join(links)[:1500]})
 return total,out

def score(town,kw,item):
 blob=' '.join(str(item.get(k,'')) for k in ['title','creator','date','description','identifiers']).lower(); sc=0
 for tok in town.split():
  if tok.lower() in blob: sc+=4
 if kw.lower() in blob: sc+=3
 if re.search(r'(18|19)\d{2}',blob): sc+=1
 if any(k in blob for k in ['地図','地籍','沿革','史','資料','報告']): sc+=1
 return sc

cache={}; queries=[]; leads=[]
for rank,address,town,cell,grid in CELLS:
 for theme,kw in KEYS:
  ck=(town,kw); q=f'{town} {kw}'
  if ck not in cache:
   params={'any':q,'cnt':8}; url=API+'?'+urllib.parse.urlencode(params)
   try:
    r=s.get(API,params=params,timeout=35); r.raise_for_status(); total,items=parse(r.content); err=''
   except Exception as e: total,items,err=0,[],f'{type(e).__name__}: {e}'
   cache[ck]={'url':url,'total':total,'items':items,'error':err}; time.sleep(0.35)
  rec=cache[ck]
  queries.append({'rank':rank,'address':address,'cell_id':cell,'grid_index':grid,'theme':theme,'keyword':kw,'query':q,'url':rec['url'],'total_results':rec['total'],'error':rec['error'],'interpretation':'catalog_lead_or_no_hit_only'})
  for n,it in enumerate(rec['items'],1):
   leads.append({'rank':rank,'address':address,'cell_id':cell,'grid_index':grid,'theme':theme,'keyword':kw,'query_total_results':rec['total'],'result_rank':n,'relevance_score':score(town,kw,it),**it,'status':'manual_primary_source_and_spatial_review_required','scoring_effect':'none'})

def wr(name,rows):
 p=OUT/name
 if not rows: p.write_text('',encoding='utf-8'); return
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
wr('query-log-fast.csv',queries)
# Keep only useful-looking leads in the compact table, but retain query totals for no-hit auditing.
leads.sort(key=lambda x:(x['rank'],x['theme'],-x['relevance_score'],x['result_rank']))
wr('catalog-leads-fast.csv',leads)
summary=[]
for rank,address,town,cell,grid in CELLS:
 for theme in sorted(set(t for t,_ in KEYS)):
  qs=[x for x in queries if x['cell_id']==cell and x['theme']==theme]; ls=[x for x in leads if x['cell_id']==cell and x['theme']==theme]
  high=[x for x in ls if x['relevance_score']>=7]
  summary.append({'rank':rank,'address':address,'cell_id':cell,'grid_index':grid,'theme':theme,'queries':len(qs),'queries_with_hit':sum((x['total_results'] or 0)>0 for x in qs),'lead_rows':len(ls),'high_relevance':len(high),'top_leads':' || '.join(f"[{x['relevance_score']}] {x['title']} ({x['date']})" for x in high[:5]),'status':'catalog_scan_complete_leads_only','quality':'no_hit_not_absence_hit_not_location_match'})
wr('cell-theme-summary-fast.csv',summary)
S={'version':'priority-cells-ndl-v2-fast-20260812','api':API,'formalCellCount':10,'uniqueNetworkQueries':len(cache),'cellQueryRows':len(queries),'leadRows':len(leads),'highRelevanceLeadRows':sum(x['relevance_score']>=7 for x in leads),'rules':['catalog hits are leads only','no-hit is not absence','hit is not V10 cell location match','scoringEffect none until primary text/image and spatial review']}
(OUT/'SUMMARY.json').write_text(json.dumps(S,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'README.md').write_text('# 本命10セル NDL目録テーマ走査 v2-fast\n\n13代表キーワードでNDL Search OpenSearch APIを走査。hit/no-hitはいずれも書誌目録上の探索結果で、地点一致・不存在・境界を証明しない。高relevance leadから原資料を読む。全件 scoringEffect=none。\n',encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(S,ensure_ascii=False))
