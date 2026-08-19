#!/usr/bin/env python3
from __future__ import annotations

import csv, hashlib, json, re, time, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
import requests

API='https://ndlsearch.ndl.go.jp/api/opensearch'
OUT=Path('out-priority-ndl-v5-historical-aliases'); OUT.mkdir(parents=True,exist_ok=True)

CELLS=[
 {'rank':1,'address':'東京都渋谷区上原二丁目','cell_id':'g194-226','grid_index':89854,'ward':'渋谷','aliases':['上原二丁目','代々木上原町','代々木富ヶ谷町']},
 {'rank':2,'address':'東京都渋谷区上原三丁目','cell_id':'g195-224','grid_index':90314,'ward':'渋谷','aliases':['上原三丁目','代々木上原町','代々木大山町']},
 {'rank':3,'address':'東京都目黒区駒場四丁目','cell_id':'g199-227','grid_index':92165,'ward':'目黒','aliases':['駒場四丁目','駒場町','上目黒 駒場']},
 {'rank':4,'address':'東京都渋谷区大山町','cell_id':'g187-221','grid_index':86615,'ward':'渋谷','aliases':['大山町','代々木大山町','代々木西原町']},
 {'rank':5,'address':'東京都目黒区東が丘一丁目','cell_id':'g233-217','grid_index':107863,'ward':'目黒','aliases':['東が丘一丁目','芳窪町','大原町','衾 東大原','衾 東上芳窪','衾 東下芳窪']},
 {'rank':6,'address':'東京都世田谷区北沢五丁目','cell_id':'g188-216','grid_index':87072,'ward':'世田谷','aliases':['北沢五丁目','北沢']},
 {'rank':7,'address':'東京都世田谷区北沢一丁目','cell_id':'g199-219','grid_index':92157,'ward':'世田谷','aliases':['北沢一丁目','北沢']},
 {'rank':8,'address':'東京都目黒区柿の木坂二丁目','cell_id':'g239-220','grid_index':110638,'ward':'目黒','aliases':['柿の木坂二丁目','柿ノ木坂','衾 東根']},
 {'rank':9,'address':'東京都目黒区目黒本町五丁目','cell_id':'g244-243','grid_index':112971,'ward':'目黒','aliases':['目黒本町五丁目','月光町','向原町','碑文谷原']},
 {'rank':10,'address':'東京都千代田区一番町','cell_id':'g169-281','grid_index':78359,'ward':'千代田','aliases':['一番町','麹町区 一番町','麹町 一番町']},
]
THEMES={
 'incarceration_prison_detention':['監獄','刑務所','拘置','留置','拘禁'],
 'execution_ground':['刑場','御仕置場','処刑','仕置場'],
 'burial_human_remains':['埋葬','人骨','遺骨','遺骸'],
 'cemetery_former_cemetery':['墓地','墓所','葬地','共同墓地','墓'],
 'crematorium_former_crematorium':['火葬場','火葬','斎場','焼場'],
 'pow_military_detention':['捕虜','俘虜','収容所','抑留'],
 'mass_death_major_fatal_incident':['大量死','惨死','死亡','死者','火災','爆発','事故'],
 'air_raid_temporary_burial':['仮埋葬','戦災','空襲','殃死'],
 'historical_watercourse':['暗渠','水路','河川','旧河道','川','用水'],
 'historical_land_facility_use':['地籍','土地台帳','古地図','旧地図','区史','町史','軍用地','兵営','工場','屋敷','学校'],
}
NS={'atom':'http://www.w3.org/2005/Atom','dc':'http://purl.org/dc/elements/1.1/','dcterms':'http://purl.org/dc/terms/','opensearch':'http://a9.com/-/spec/opensearch/1.1/'}
SESSION=requests.Session(); SESSION.headers.update({'User-Agent':'iyashiro-map research/1.2 NDL historical alias sequential scan','Accept-Language':'ja,en;q=0.8'})

def first_text(e, paths):
 for p in paths:
  x=e.find(p,NS)
  if x is not None and x.text:
   return x.text.strip()
 return ''
def all_text(e, paths):
 vals=[]
 for p in paths:
  vals += [(x.text or '').strip() for x in e.findall(p,NS) if x.text]
 return vals

def parse_xml(b):
 root=ET.fromstring(b)
 # OpenSearch RSS nests metadata under channel; Atom responses nest entries.
 total_el=root.find('.//opensearch:totalResults',NS)
 try: total=int((total_el.text or '0').strip()) if total_el is not None else 0
 except: total=0
 entries=root.findall('.//atom:entry',NS)
 if not entries:
  entries=root.findall('.//item')
 out=[]
 for e in entries[:30]:
  title=first_text(e,['atom:title','title','dc:title'])
  out.append({
   'title':title,
   'creator':first_text(e,['dc:creator','creator']),
   'publisher':first_text(e,['dc:publisher','dcterms:publisher','publisher']),
   'date':first_text(e,['dc:date','dcterms:date','pubDate']),
   'description':re.sub(r'\s+',' ',first_text(e,['dc:description','dcterms:description','atom:summary','description']))[:3000],
   'subjects':' | '.join(all_text(e,['dc:subject','dcterms:subject','subject']))[:2200],
   'identifiers':' | '.join(all_text(e,['dc:identifier','dcterms:identifier','guid']))[:2200],
   'links':' | '.join([x.attrib.get('href','') for x in e.findall('.//atom:link',NS) if x.attrib.get('href')] + [first_text(e,['link'])])[:2500],
  })
 return total,out,root.tag

def fetch(term):
 params={'any':term,'cnt':30}; url=API+'?'+urllib.parse.urlencode(params)
 attempts=[]
 for attempt in range(1,5):
  try:
   r=SESSION.get(API,params=params,timeout=(10,50))
   attempts.append({'attempt':attempt,'status':r.status_code,'bytes':len(r.content)})
   if r.status_code==429:
    time.sleep(min(12,2**attempt)); continue
   r.raise_for_status()
   total,items,root_tag=parse_xml(r.content)
   return {'url':url,'total':total,'items':items,'error':'','attempts':attempts,'rootTag':root_tag,'responseSha256':hashlib.sha256(r.content).hexdigest()}
  except Exception as e:
   attempts.append({'attempt':attempt,'error':f'{type(e).__name__}: {e}'})
   if attempt<4: time.sleep(min(12,2**attempt))
 time.sleep(2)
 return {'url':url,'total':0,'items':[],'error':attempts[-1].get('error','failed'),'attempts':attempts,'rootTag':'','responseSha256':''}

def blob(it): return ' '.join(str(it.get(k,'')) for k in ['title','creator','publisher','date','description','subjects','identifiers'])
def wr(name,rows):
 p=OUT/name
 if not rows: p.write_text('',encoding='utf-8'); return
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

terms=sorted({a for c in CELLS for a in c['aliases']})
cache={}
# NDL guidance asks callers to avoid concurrent/multiple access; scan sequentially.
for i,t in enumerate(terms,1):
 cache[t]=fetch(t)
 print(json.dumps({'query':i,'of':len(terms),'term':t,'total':cache[t]['total'],'items':len(cache[t]['items']),'error':cache[t]['error']},ensure_ascii=False),flush=True)
 time.sleep(1.5)

queries=[]; leads=[]
for c in CELLS:
 for alias in c['aliases']:
  rec=cache[alias]
  queries.append({**{k:c[k] for k in ['rank','address','cell_id','grid_index']},'alias':alias,'api_url':rec['url'],'total_results':rec['total'],'returned_items':len(rec['items']),'error':rec['error'],'attempts_json':json.dumps(rec['attempts'],ensure_ascii=False),'root_tag':rec['rootTag'],'response_sha256':rec['responseSha256'],'interpretation':'historical_alias_catalog_pool_only'})
  for i,it in enumerate(rec['items'],1):
   b=blob(it); norm_b=b.replace(' ','')
   alias_score=6 if alias.replace(' ','') in norm_b else 0
   ward_score=2 if c['ward'] in b else 0
   historical_year=1 if re.search(r'(?:17|18|19)[0-6]\d',b) else 0
   source_score=1 if any(k in b for k in ['地図','地籍','沿革','史','資料','報告','絵図','台帳']) else 0
   for theme,kws in THEMES.items():
    hits=[k for k in kws if k in b]
    if not hits: continue
    score=alias_score+ward_score+3*min(len(hits),4)+historical_year+source_score
    leads.append({**{k:c[k] for k in ['rank','address','cell_id','grid_index']},'alias':alias,'theme':theme,'matched_keywords':' | '.join(hits),'relevance_score':score,'result_rank':i,**it,'status':'catalog_lead_manual_source_and_spatial_review_required','scoring_effect':'none'})

best={}
for r in leads:
 key=(r['cell_id'],r['theme'],r['title'],r['date'],r['identifiers'])
 o=best.get(key)
 if o is None or r['relevance_score']>o['relevance_score']: best[key]=r
leads=list(best.values()); leads.sort(key=lambda r:(r['rank'],r['theme'],-r['relevance_score'],r['result_rank']))
summary=[]
for c in CELLS:
 for theme in THEMES:
  ls=[x for x in leads if x['cell_id']==c['cell_id'] and x['theme']==theme]
  high=[x for x in ls if x['relevance_score']>=11]
  summary.append({**{k:c[k] for k in ['rank','address','cell_id','grid_index']},'theme':theme,'alias_queries':' | '.join(c['aliases']),'alias_query_failures':sum(bool(cache[a]['error']) for a in c['aliases']),'theme_lead_count':len(ls),'high_relevance_count':len(high),'top_leads':' || '.join(f"[{x['relevance_score']}] {x['title']} ({x['date']}; alias={x['alias']})" for x in high[:7]),'quality':'catalog_lead_only_no_absence_or_location_claim'})

wr('alias-query-log-v5.csv',queries); wr('catalog-leads-v5.csv',leads); wr('cell-theme-summary-v5.csv',summary)
S={'version':'priority-cells-ndl-historical-alias-v5-20260813','api':API,'formalCellCount':10,'themeCount':10,'uniqueAliasQueries':len(terms),'successfulAliasQueries':sum(not cache[t]['error'] for t in terms),'failedAliasQueries':sum(bool(cache[t]['error']) for t in terms),'totalReturnedItemsAcrossQueries':sum(len(cache[t]['items']) for t in terms),'catalogLeadRows':len(leads),'highRelevanceRows':sum(r['relevance_score']>=11 for r in leads),'v4Invalidation':['v4 parser searched direct item nodes and missed RSS channel/item nesting','v4 used concurrent requests and triggered 429/timeouts; NDL asks callers to avoid multiple concurrent access'],'rules':['historical aliases are lead-recall expansion, not spatial equivalence proof','catalog keyword hits are not evidence of the event or facility','zero leads never means absence','a source must be opened and its location checked before cell/theme status upgrade','scoringEffect none at this stage']}
(OUT/'SUMMARY.json').write_text(json.dumps(S,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'README.md').write_text('# 本命10セル NDL歴史町名目録走査 v5\n\nv4のRSSパーサと多重アクセスを監査し、channel/itemを再帰取得するパーサ、逐次アクセス、429/timeoutバックオフへ修正。自治体等で確認した旧町名・旧字名はrecall拡張にのみ使う。目録候補は本文・位置確認前には証拠へ昇格せず、ゼロ件も不存在を意味しない。全件scoringEffect=none。\n',encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p.name!='SHA256SUMS.txt': f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(S,ensure_ascii=False))
