#!/usr/bin/env python3
from __future__ import annotations
import asyncio, json, re, traceback
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup

OUT=Path('output/portal_probes'); OUT.mkdir(parents=True,exist_ok=True)
TARGETS={'yokohama':'https://wwwm.city.yokohama.lg.jp/yokohama/Portal','kawasaki':'https://www.city.kawasaki.jp/601/page/0000046739.html'}
SIG=re.compile(r'liqu|eki(?:j|z)|液状化|mapserver|featureserver|wmts|wms|tile|layer|hazard|防災|portal|gis',re.I)
UA='IyashirochiOfficialClosure/2026-08-22'

def static_probe(label:str,url:str)->dict[str,Any]:
 d=OUT/label/'static'; d.mkdir(parents=True,exist_ok=True); s=requests.Session(); s.headers['User-Agent']=UA
 try:
  r=s.get(url,timeout=(30,120),allow_redirects=True); r.raise_for_status(); (d/'landing.html').write_bytes(r.content)
  soup=BeautifulSoup(r.text,'html.parser'); links=[]
  for a in soup.find_all(['a','script','link']):
   href=a.get('href') or a.get('src')
   if href:
    full=requests.compat.urljoin(r.url,href); text=(a.get_text(' ',strip=True) or '')[:300]
    links.append({'url':full,'text':text,'signal':bool(SIG.search(full+' '+text))})
  (d/'links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
  return {'status':'SUCCESS','start_url':url,'final_url':r.url,'links':len(links),'signals':[x for x in links if x['signal']]}
 except Exception as e: return {'status':'FAILED','start_url':url,'error':f'{type(e).__name__}: {e}'}

async def browser_probe(label:str,url:str)->dict[str,Any]:
 from playwright.async_api import async_playwright
 d=OUT/label/'browser'; d.mkdir(parents=True,exist_ok=True); reqs=[]; resps=[]; actions=[]; result={'label':label,'start_url':url,'status':'FAILED'}
 try:
  async with async_playwright() as p:
   b=await p.chromium.launch(headless=True); c=await b.new_context(ignore_https_errors=True,locale='ja-JP',user_agent=UA,viewport={'width':1440,'height':1100}); page=await c.new_page(); page.set_default_timeout(12000)
   page.on('request',lambda q:reqs.append({'url':q.url,'method':q.method,'type':q.resource_type,'signal':bool(SIG.search(q.url))}))
   page.on('response',lambda r:resps.append({'url':r.url,'status':r.status,'signal':bool(SIG.search(r.url))}))
   await page.goto(url,wait_until='domcontentloaded',timeout=120000); await page.wait_for_timeout(4000)
   async def click(patterns:list[str],phase:str)->bool:
    for pat in patterns:
     try:
      loc=page.get_by_text(re.compile(pat,re.I)).first
      if await loc.count() and await loc.is_visible():
       txt=(await loc.inner_text())[:200]; await loc.click(); actions.append({'phase':phase,'pattern':pat,'text':txt,'result':'clicked'}); await page.wait_for_timeout(3500); return True
     except Exception as e: actions.append({'phase':phase,'pattern':pat,'result':'skip','error':str(e)[:250]})
    return False
   await click([r'同意する',r'同意',r'利用する',r'承諾',r'OK',r'進む'],'agreement')
   if label=='yokohama':
    await click([r'わいわい防災',r'防災マップ',r'防災'],'open_map'); await click([r'液状化危険度',r'液状化'],'liquefaction')
   else:
    await click([r'ガイドマップかわさき',r'ガイドマップ',r'地図を開く'],'open_map'); await click([r'同意する',r'同意',r'利用する',r'承諾',r'OK'],'agreement2'); await click([r'液状化危険度',r'液状化'],'liquefaction')
   await page.wait_for_timeout(7000); pages=c.pages; active=pages[-1]
   result.update({'status':'SUCCESS','final_url':active.url,'title':await active.title(),'page_count':len(pages),'links':await active.eval_on_selector_all('a',"e=>e.map(x=>({text:(x.innerText||'').trim(),href:x.href})).filter(x=>x.text||x.href)"),'controls':await active.eval_on_selector_all('button,input,label,option',"e=>e.map(x=>({tag:x.tagName,text:(x.innerText||x.value||x.getAttribute('aria-label')||'').trim(),type:x.type||''})).filter(x=>x.text)")})
   (d/'final.html').write_text(await active.content(),encoding='utf-8'); await active.screenshot(path=str(d/'final.png'),full_page=True); await b.close()
 except Exception as e: result.update({'error':f'{type(e).__name__}: {e}','traceback':traceback.format_exc()})
 (d/'requests.json').write_text(json.dumps(reqs,ensure_ascii=False,indent=2),encoding='utf-8'); (d/'responses.json').write_text(json.dumps(resps,ensure_ascii=False,indent=2),encoding='utf-8'); (d/'actions.json').write_text(json.dumps(actions,ensure_ascii=False,indent=2),encoding='utf-8')
 result.update({'request_count':len(reqs),'response_count':len(resps),'signal_requests':[x for x in reqs if x['signal']],'signal_responses':[x for x in resps if x['signal']]}); return result

async def main()->None:
 static={k:static_probe(k,v) for k,v in TARGETS.items()}; browser=await asyncio.gather(*(browser_probe(k,v) for k,v in TARGETS.items())); status={'schema':'IYASHIRO_PORTAL_PROBE_v1','static':static,'browser':browser}
 Path('output/PORTAL_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__': asyncio.run(main())
