#!/usr/bin/env python3
from __future__ import annotations
import asyncio, hashlib, json, re, traceback
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup

OUT=Path('output/portal_probes'); OUT.mkdir(parents=True,exist_ok=True)
TARGETS={
 'tokyo_liquefaction_top':'https://doboku.metro.tokyo.lg.jp/start/03-jyouhou/ekijyouka/top.aspx',
 'yokohama_portal':'https://wwwm.city.yokohama.lg.jp/yokohama/Portal',
 'yokohama_mapselect_6':'https://wwwm.city.yokohama.lg.jp/yokohama/MapSelect?mcid=6',
 'yokohama_position_6':'https://wwwm.city.yokohama.lg.jp/yokohama/PositionSelect?mid=6',
 'yokohama_map':'https://wwwm.city.yokohama.lg.jp/yokohama/Map',
 'kawasaki_source_page':'https://www.city.kawasaki.jp/601/page/0000046739.html',
 'kawasaki_hazard_map':'https://kawasaki.geocloud.jp/webgis/?bt=0&mp=143-88&p=0',
 'kawasaki_hazard_map_legacy':'https://kawasaki.geocloud.jp/webgis/?p=0&bt=0&mp=143-73',
 'kawasaki_water_map':'https://kawasaki.geocloud.jp/webgis/?bt=0&mp=229-32&p=0',
}
SIG=re.compile(r'liqu|eki(?:j|z)|液状化|mapserver|featureserver|wmts|wms|tile|layer|hazard|防災|portal|gis|geojson|query|identify|legend|mesh|risk|suikei|water',re.I)
SAVE_CT=('json','javascript','text/','xml','geo+json','octet-stream','zip','pdf')
UA='IyashirochiOfficialClosure/2026-08-22'

def sha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def slug(s:str)->str:return re.sub(r'[^A-Za-z0-9._-]+','_',s).strip('_')[:180] or 'body'

def static_probe(label:str,url:str)->dict[str,Any]:
 d=OUT/label/'static'; d.mkdir(parents=True,exist_ok=True); s=requests.Session(); s.headers['User-Agent']=UA
 try:
  r=s.get(url,timeout=(30,120),allow_redirects=True,verify=False); r.raise_for_status(); (d/'landing.html').write_bytes(r.content)
  soup=BeautifulSoup(r.content,'html.parser',from_encoding=r.encoding or r.apparent_encoding); links=[]
  for a in soup.find_all(['a','script','link','form']):
   href=a.get('href') or a.get('src') or a.get('action')
   if href:
    full=requests.compat.urljoin(r.url,href); text=(a.get_text(' ',strip=True) or '')[:300]
    links.append({'url':full,'text':text,'signal':bool(SIG.search(full+' '+text))})
  (d/'links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
  return {'status':'SUCCESS','start_url':url,'final_url':r.url,'links':len(links),'signals':[x for x in links if x['signal']]}
 except Exception as e:return {'status':'FAILED','start_url':url,'error':f'{type(e).__name__}: {e}'}

async def browser_probe(label:str,url:str)->dict[str,Any]:
 from playwright.async_api import async_playwright
 d=OUT/label/'browser'; bodies=d/'bodies'; d.mkdir(parents=True,exist_ok=True); bodies.mkdir(parents=True,exist_ok=True)
 reqs=[]; resps=[]; actions=[]; body_index=[]; tasks=[]; result={'label':label,'start_url':url,'status':'FAILED'}
 async def capture_response(resp):
  rec={'url':resp.url,'status':resp.status,'signal':bool(SIG.search(resp.url)),'content_type':resp.headers.get('content-type','')}
  resps.append(rec)
  ct=rec['content_type'].lower(); should=rec['signal'] or any(x in ct for x in SAVE_CT)
  if not should:return
  try:
   b=await resp.body()
   if len(b)>25_000_000:return
   ext='.bin'
   if 'json' in ct:ext='.json'
   elif 'javascript' in ct:ext='.js'
   elif 'html' in ct:ext='.html'
   elif 'xml' in ct:ext='.xml'
   elif 'text/' in ct:ext='.txt'
   elif 'pdf' in ct:ext='.pdf'
   elif 'png' in ct:ext='.png'
   elif 'jpeg' in ct or 'jpg' in ct:ext='.jpg'
   fname=f'{len(body_index):04d}_{slug(resp.url.split("?")[0].split("/")[-1])}{ext}'
   (bodies/fname).write_bytes(b); body_index.append({'file':fname,'url':resp.url,'status':resp.status,'content_type':ct,'bytes':len(b),'sha256':sha_bytes(b),'signal':rec['signal']})
  except Exception as e:rec['body_error']=f'{type(e).__name__}: {e}'
 try:
  async with async_playwright() as p:
   b=await p.chromium.launch(headless=True); c=await b.new_context(ignore_https_errors=True,locale='ja-JP',user_agent=UA,viewport={'width':1440,'height':1100},accept_downloads=True)
   page=await c.new_page(); page.set_default_timeout(15000)
   page.on('request',lambda q:reqs.append({'url':q.url,'method':q.method,'type':q.resource_type,'signal':bool(SIG.search(q.url)),'post_data':q.post_data[:2000] if q.post_data else None}))
   page.on('response',lambda r:tasks.append(asyncio.create_task(capture_response(r))))
   await page.goto(url,wait_until='domcontentloaded',timeout=120000); await page.wait_for_timeout(6000)
   async def click_text(patterns:list[str],phase:str)->bool:
    for pat in patterns:
     try:
      loc=page.get_by_text(re.compile(pat,re.I)).first
      if await loc.count() and await loc.is_visible():
       txt=(await loc.inner_text())[:200]; await loc.click(); actions.append({'phase':phase,'pattern':pat,'text':txt,'result':'clicked'}); await page.wait_for_timeout(5000); return True
     except Exception as e:actions.append({'phase':phase,'pattern':pat,'result':'skip','error':str(e)[:250]})
    return False
   if label=='tokyo_liquefaction_top':
    try:
     boxes=page.locator('input[type=checkbox]')
     if await boxes.count():await boxes.first.check(force=True);actions.append({'phase':'agreement','result':'checkbox_checked'})
    except Exception as e:actions.append({'phase':'agreement','result':'checkbox_failed','error':str(e)})
    clicked=False
    for sel in ['input[type=submit]','input[type=button]','button']:
     try:
      loc=page.locator(sel).filter(has_text=re.compile('液状化予測図を見る|見る',re.I)).first
      if await loc.count() and await loc.is_visible():await loc.click();clicked=True;actions.append({'phase':'open_map','selector':sel,'result':'clicked'});break
     except Exception:pass
    if not clicked:await click_text([r'液状化予測図を見る',r'予測図を見る'],'open_map_text')
   elif label.startswith('yokohama'):
    await click_text([r'同意する',r'同意',r'利用する',r'承諾',r'OK'],'agreement')
    await click_text([r'液状化危険度',r'液状化',r'元禄型関東地震',r'東京湾北部地震',r'南海トラフ巨大地震'],'liquefaction')
   elif label.startswith('kawasaki'):
    await click_text([r'同意する',r'同意',r'利用する',r'承諾',r'OK'],'agreement')
    await click_text([r'液状化危険度',r'液状化',r'地震・水害・土砂災害',r'水辺地マップ'],'liquefaction')
   await page.wait_for_timeout(15000); pages=c.pages; active=pages[-1]
   if active is not page:
    active.on('request',lambda q:reqs.append({'url':q.url,'method':q.method,'type':q.resource_type,'signal':bool(SIG.search(q.url)),'post_data':q.post_data[:2000] if q.post_data else None}))
    active.on('response',lambda r:tasks.append(asyncio.create_task(capture_response(r)))); await active.wait_for_timeout(8000)
   try:
    controls=await active.eval_on_selector_all('button,input,label,option,select',"e=>e.map(x=>({tag:x.tagName,text:(x.innerText||x.value||x.getAttribute('aria-label')||x.name||'').trim(),type:x.type||'',id:x.id||'',name:x.name||''})).filter(x=>x.text||x.id||x.name)")
    links=await active.eval_on_selector_all('a',"e=>e.map(x=>({text:(x.innerText||'').trim(),href:x.href})).filter(x=>x.text||x.href)")
   except Exception:controls=[];links=[]
   result.update({'status':'SUCCESS','final_url':active.url,'title':await active.title(),'page_count':len(pages),'links':links,'controls':controls})
   (d/'final.html').write_text(await active.content(),encoding='utf-8'); await active.screenshot(path=str(d/'final.png'),full_page=True)
   await asyncio.gather(*tasks,return_exceptions=True); await b.close()
 except Exception as e:result.update({'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()})
 (d/'requests.json').write_text(json.dumps(reqs,ensure_ascii=False,indent=2),encoding='utf-8'); (d/'responses.json').write_text(json.dumps(resps,ensure_ascii=False,indent=2),encoding='utf-8'); (d/'actions.json').write_text(json.dumps(actions,ensure_ascii=False,indent=2),encoding='utf-8'); (d/'body_index.json').write_text(json.dumps(body_index,ensure_ascii=False,indent=2),encoding='utf-8')
 result.update({'request_count':len(reqs),'response_count':len(resps),'saved_body_count':len(body_index),'signal_requests':[x for x in reqs if x['signal']],'signal_responses':[x for x in resps if x['signal']],'saved_signal_bodies':[x for x in body_index if x['signal']]});return result

async def main()->None:
 static={k:static_probe(k,v) for k,v in TARGETS.items()}; browser=await asyncio.gather(*(browser_probe(k,v) for k,v in TARGETS.items())); status={'schema':'IYASHIRO_PORTAL_PROBE_v2','static':static,'browser':browser}
 Path('output/PORTAL_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(main())
