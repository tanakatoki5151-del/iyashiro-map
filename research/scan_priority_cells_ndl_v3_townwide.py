#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, re, urllib.parse, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

API='https://ndlsearch.ndl.go.jp/api/opensearch'
OUT=Path('out-priority-ndl-v3'); OUT.mkdir(parents=True,exist_ok=True)
CELLS=[
(1,'東京都渋谷区上原二丁目','上原','渋谷','g194-226',89854),
(2,'東京都渋谷区上原三丁目','上原','渋谷','g195-224',90314),
(3,'東京都目黒区駒場四丁目','駒場','目黒','g199-227',92165),
(4,'東京都渋谷区大山町','大山町','渋谷','g187-221',86615),
(5,'東京都目黒区東が丘一丁目','東が丘','目黒','g233-217',107863),
(6,'東京都世田谷区北沢五丁目','北沢','世田谷','g188-216',87072),
(7,'東京都世田谷区北沢一丁目','北沢','世田谷','g199-219',92157),
(8,'東京都目黒区柿の木坂二丁目','柿の木坂','目黒','g239-220',110638),
(9,'東京都目黒区目黒本町五丁目','目黒本町','目黒','g244-243',112971),
(10,'東京都千代田区一番町','一番町','千代田','g169-281',78359)]
THEMES={
'detention_execution_pow':['刑場','監獄','拘置','刑務','捕虜','俘虜','収容'],
'cemetery_burial_remains':['墓地','埋葬','人骨','遺骨','墓'],
'crematorium':['火葬','斎場'],
'wartime_temporary_burial':['仮埋葬','戦災','空襲'],
'major_fire_explosion_incident':['火災','爆発','事故','大量死'],
'military_land_pow':['陸軍','海軍','軍用','兵営','軍施設'],
'old_watercourse':['暗渠','河川','水路','旧河道','川'],
'historic_land_use':['地籍','土地利用','古地図','旧地図','区史','町史'],
'folklore':['民俗','伝承','地名','郷土史'],
'primary_source_leads':['公図','地籍図','沿革','史料','資料集','絵図']}
NS={'atom':'http://www.w3.org/2005/Atom','dc':'http://purl.org/dc/elements/1.1/','dcterms':'http://purl.org/dc/terms/','opensearch':'http://a9.com/-/spec/opensearch/1.1/'}

def text(e,p):
 x=e.find(p,NS); return (x.text or '').strip() if x is not None and x.text else ''
def texts(e,p): return [(x.text or '').strip() for x in e.findall(p,NS) if x.text]
def parse(b):
 root=ET.fromstring(b); tt=text(root,'opensearch:totalResults')
 try: total=int(tt)
 except: total=0
 entries=root.findall('atom:entry',NS) or root.findall('item'); out=[]
 for e in entries[:100]:
  out.append({'title':text(e,'atom:title') or text(e,'title') or text(e,'dc:title'),'creator':text(e,'dc:creator'),'publisher':text(e,'dc:publisher') or text(e,'dcterms:publisher'),'date':text(e,'dc:date') or text(e,'dcterms:date'),'description':re.sub(r'\s+',' ',text(e,'dc:description') or text(e,'dcterms:description') or text(e,'atom:summary'))[:2000],'subjects':' | '.join(texts(e,'dc:subject')+texts(e,'dcterms:subject'))[:1600],'identifiers':' | '.join(texts(e,'dc:identifier')+texts(e,'dcterms:identifier'))[:1600],'links':' | '.join([x.attrib.get('href','') for x in e.findall('atom:link',NS) if x.attrib.get('href')])[:2000]})
 return total,out

def fetch(term):
 params={'any':term,'cnt':100}; url=API+'?'+urllib.parse.urlencode(params)
 try:
  r=requests.get(API,params=params,timeout=(5,20),headers={'User-Agent':'iyashiro-map-research/1.0 town metadata scan','Accept-Language':'ja,en;q=0.8'}); r.raise_for_status(); total,items=parse(r.content); err=''
 except Exception as e: total,items,err=0,[],f'{type(e).__name__}: {e}'
 return term,{'url':url,'total':total,'items':items,'error':err}

def blob(it): return ' '.join(str(it.get(k,'')) for k in ['title','creator','publisher','date','description','subjects','identifiers'])

def wr(name,rows):
 p=OUT/name
 if not rows: p.write_text('',encoding='utf-8'); return
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

terms=sorted({town for _,_,town,_,_,_ in CELLS})
cache={}
with ThreadPoolExecutor(max_workers=4) as ex:
 for fut in as_completed([ex.submit(fetch,t) for t in terms]):
  t,r=fut.result(); cache[t]=r
queries=[]; leads=[]
for rank,address,town,ward,cell,grid in CELLS:
 rec=cache[town]; queries.append({'rank':rank,'address':address,'cell_id':cell,'grid_index':grid,'town_term':town,'api_url':rec['url'],'total_results':rec['total'],'returned_items':len(rec['items']),'error':rec['error'],'interpretation':'town_catalog_result_pool_not_spatial_evidence'})
 for i,it in enumerate(rec['items'],1):
  b=blob(it); locality_score=(5 if town in b else 0)+(3 if ward in b else 0)
  for theme,kws in THEMES.items():
   hits=[k for k in kws if k in b]
   if not hits: continue
   hist=1 if re.search(r'(?:18|19)[0-6]\d',b) else 0
   src=1 if any(k in b for k in ['地図','地籍','沿革','史','資料','報告','絵図']) else 0
   sc=locality_score+3*len(hits)+hist+src
   leads.append({'rank':rank,'address':address,'cell_id':cell,'grid_index':grid,'theme':theme,'matched_keywords':' | '.join(hits),'locality_score':locality_score,'relevance_score':sc,'result_rank':i,**it,'status':'catalog_lead_manual_text_and_spatial_review_required','scoring_effect':'none'})
# de-dup within cell/theme/title/date
best={}
for r in leads:
 key=(r['cell_id'],r['theme'],r['title'],r['date'],r['identifiers']); o=best.get(key)
 if o is None or r['relevance_score']>o['relevance_score']:best[key]=r
leads=list(best.values()); leads.sort(key=lambda r:(r['rank'],r['theme'],-r['relevance_score'],r['result_rank']))
summary=[]
for rank,address,town,ward,cell,grid in CELLS:
 for theme in THEMES:
  ls=[x for x in leads if x['cell_id']==cell and x['theme']==theme]; high=[x for x in ls if x['relevance_score']>=10]
  summary.append({'rank':rank,'address':address,'cell_id':cell,'grid_index':grid,'theme':theme,'catalog_query_status':'failed' if cache[town]['error'] else 'completed','returned_town_items':len(cache[town]['items']),'theme_lead_count':len(ls),'high_relevance_count':len(high),'top_leads':' || '.join(f"[{x['relevance_score']}] {x['title']} ({x['date']})" for x in high[:5]),'quality':'catalog_lead_only_no_absence_or_location_claim'})
wr('town-query-log-v3.csv',queries); wr('catalog-leads-v3.csv',leads); wr('cell-theme-summary-v3.csv',summary)
S={'version':'priority-cells-ndl-townwide-v3-20260812','api':API,'formalCellCount':10,'uniqueTownQueries':len(terms),'successfulTownQueries':sum(not cache[t]['error'] for t in terms),'failedTownQueries':sum(bool(cache[t]['error']) for t in terms),'catalogLeadRows':len(leads),'highRelevanceRows':sum(r['relevance_score']>=10 for r in leads),'rules':['town catalog results are a lead pool only','theme keyword match is not proof of subject relevance','no theme lead is not absence','catalog lead is not V10-cell spatial match','scoringEffect none until source and location review']}
(OUT/'SUMMARY.json').write_text(json.dumps(S,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'README.md').write_text('# 本命10セル NDL町名広域目録走査 v3\n\n町名8クエリだけで上位100件を取得し、ローカルで10テーマ分類。目録語の一致は資料候補にすぎず、地点・歴史事実・境界の証拠ではない。テーマleadが0でも不存在証明にしない。高relevanceから本文/原画像を確認する。全件scoringEffect=none。\n',encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(S,ensure_ascii=False))
