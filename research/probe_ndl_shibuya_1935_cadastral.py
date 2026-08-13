#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,time
from pathlib import Path
import requests

OUT=Path('out-ndl-shibuya-1935-probe'); OUT.mkdir(parents=True,exist_ok=True)
PIDS=['8311641','8311642']
S=requests.Session(); S.headers.update({'User-Agent':'iyashiro-map historical-cadastral-research/1.0','Accept-Language':'ja,en;q=0.8'})

def lab(v):
    if isinstance(v,str): return v
    if isinstance(v,dict):
        if '@value' in v:return str(v['@value'])
        for x in v.values():
            if isinstance(x,list) and x:return str(x[0])
            if isinstance(x,str):return x
    return str(v or '')

def image_url(canvas,width=1600):
    imgs=canvas.get('images') or []
    if not imgs:return None
    r=(imgs[0] or {}).get('resource') or {}
    svc=r.get('service')
    if isinstance(svc,list): svc=svc[0] if svc else None
    if isinstance(svc,dict):
        sid=svc.get('@id') or svc.get('id')
        if sid:return sid.rstrip('/')+f'/full/{width},/0/default.jpg'
    return r.get('@id') or r.get('id')

def walk(node,out):
    if isinstance(node,list):
        for x in node:walk(x,out)
    elif isinstance(node,dict):
        l=lab(node.get('label'))
        if any(k in l for k in ['代々木','上原','大山','富ヶ谷','幡ヶ谷','西原','笹塚']):
            out.append({'label':l,'id':node.get('@id') or node.get('id'),'canvases':node.get('canvases'),'members':node.get('members')})
        for k in ['ranges','members']:walk(node.get(k),out)

report={'pids':[],'rules':['public unauthenticated requests only','do not bypass individual-transmission authentication','manifest success does not imply image access','no boundary or cell evidence from access probe alone']}
for pid in PIDS:
    rec={'pid':pid,'manifestUrl':f'https://dl.ndl.go.jp/api/iiif/{pid}/manifest.json'}
    try:
        r=S.get(rec['manifestUrl'],timeout=60,allow_redirects=True)
        rec.update({'manifestStatus':r.status_code,'manifestContentType':r.headers.get('content-type'),'manifestBytes':len(r.content),'manifestFinalUrl':r.url,'manifestSha256':hashlib.sha256(r.content).hexdigest()})
        (OUT/f'{pid}_manifest_response.bin').write_bytes(r.content)
        if r.ok and 'json' in (r.headers.get('content-type') or '').lower():
            m=r.json(); (OUT/f'{pid}_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
            canv=(((m.get('sequences') or [{}])[0]).get('canvases') or [])
            rec['canvasCount']=len(canv)
            hits=[];walk(m.get('structures') or [],hits);rec['rangeHits']=hits[:100]
            sample_indices=sorted(set([0,max(0,len(canv)//4),max(0,len(canv)//2),max(0,3*len(canv)//4),max(0,len(canv)-1)])) if canv else []
            samples=[]
            for idx in sample_indices:
                c=canv[idx];u=image_url(c);samp={'index':idx,'oneBased':idx+1,'label':lab(c.get('label')),'imageUrl':u}
                if u:
                    try:
                        ir=S.get(u,timeout=45,allow_redirects=True)
                        samp.update({'status':ir.status_code,'finalUrl':ir.url,'contentType':ir.headers.get('content-type'),'bytes':len(ir.content)})
                        if ir.ok and (ir.headers.get('content-type') or '').lower().startswith('image/'):
                            fn=f'{pid}_sample_{idx+1:03d}.jpg';(OUT/fn).write_bytes(ir.content);samp['savedAs']=fn;samp['sha256']=hashlib.sha256(ir.content).hexdigest()
                    except Exception as e:samp['error']=repr(e)
                samples.append(samp);time.sleep(0.7)
            rec['imageSamples']=samples
    except Exception as e:rec['error']=repr(e)
    report['pids'].append(rec);time.sleep(1.5)
report['summary']={
 'manifestOk':sum(x.get('manifestStatus')==200 for x in report['pids']),
 'publicImageSamplesOk':sum(sum(1 for s in x.get('imageSamples',[]) if s.get('status')==200 and str(s.get('contentType','')).lower().startswith('image/')) for x in report['pids'])
}
(OUT/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS.txt':f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
print(json.dumps(report['summary'],ensure_ascii=False))
for x in report['pids']:
    print(x['pid'],x.get('manifestStatus'),x.get('canvasCount'),[(s.get('oneBased'),s.get('status'),s.get('contentType'),s.get('finalUrl')) for s in x.get('imageSamples',[])])
