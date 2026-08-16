#!/usr/bin/env python3
"""ECOSCAPE B79: exact GSI z17 photo crops + RGB proxy holdout QA."""
import argparse,base64,csv,gzip,hashlib,io,json,math,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np,requests
from PIL import Image
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error,r2_score
from sklearn.model_selection import GroupKFold

BUILD="ecos-e4-gsi-deep-qa300-20260817-b79"
SOURCE="SRC-ECO-GSI-SEAMLESSPHOTO-001"
SAMPLE="https://ecoscape-qa300-aggregate.vercel.app/api/aggregate"
JAXA="https://ecoscape-jaxa-qa300-runner.vercel.app/api/run?batch={}"
SAMPLE_SHA="80573f7ceafb929af087ba88e8d822a2cd2aa583d04b4400be7aff2e988da131"
TILE="https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{}/{}/{}.jpg"
Z,N=17,2**17
DY,DX=0.0008983111749910168,0.0011042452218025757

def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def wp(lon,lat):
    return ((lon+180)/360*N*256,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*N*256)
def decode(x):
    if isinstance(x,dict):
        c,r=x.get("columns"),x.get("rows")
        if isinstance(c,list) and isinstance(r,list) and len(r)==300:
            q=[dict(zip(c,v)) for v in r]
            if all("cellId" in v and "sampleOrder" in v for v in q): return q
        for v in x.values():
            q=decode(v)
            if q:return q
    if isinstance(x,list):
        if len(x)==300 and all(isinstance(v,dict) and "cellId" in v for v in x):return x
        for v in x:
            q=decode(v)
            if q:return q

def remote_input(out):
    a=requests.get(SAMPLE,timeout=(20,120));a.raise_for_status();j=a.json();c=j.get("contract",{})
    if c.get("rows")!=300 or c.get("sampleSha256")!=SAMPLE_SHA:raise RuntimeError(c)
    s=decode(json.loads(gzip.decompress(base64.b64decode(j["payloadBase64"]))))
    if not s:raise RuntimeError("sample decode failed")
    labels={}; rec=[]
    for b in (1,2,3):
        r=requests.get(JAXA.format(b),timeout=(20,180));r.raise_for_status();x=r.json();rows=x.get("rows",[])
        if not x.get("ok") or len(rows)!=100:raise RuntimeError(f"JAXA batch {b}")
        labels.update({v["cellId"]:v for v in rows});rec.append({"batch":b,"qa":x.get("qa"),"start":x.get("start"),"finish":x.get("finish")})
    rows=[]
    for v in s:
        k=v["cellId"];x=labels[k];d=x.get("dominantClass") or {}
        rows.append({"sampleOrder":int(v["sampleOrder"]),"cellId":k,
          "municipalityCode":str(v.get("municipalityCode") or v.get("cityCode") or "UNKNOWN"),
          "municipalityName":str(v.get("municipalityName") or v.get("cityName") or "UNKNOWN"),
          "centerLat":float(x["centerLat"]),"centerLon":float(x["centerLon"]),
          "jaxaWater":float(x["waterFraction"]),"jaxaBuilt":float(x["builtFraction"]),"jaxaGreen":float(x["greenFraction"]),
          "jaxaClass":str(d.get("name") or d.get("value") or "UNKNOWN"),"jaxaSha":x.get("aggregateSha256","")})
    rows.sort(key=lambda v:v["sampleOrder"])
    if len(rows)!=300 or len({v["cellId"] for v in rows})!=300:raise RuntimeError("input gate")
    p=out/"ECOSCAPE_GSI_QA300_INPUT_B79.csv";write_csv(p,rows)
    (out/"ECOSCAPE_GSI_QA300_INPUT_RECEIPT_B79.json").write_bytes(canon({"sampleSha256":SAMPLE_SHA,"aggregateSha256":sha(a.content),"batches":rec,"inputSha256":sha(p.read_bytes())}))
    return rows

def read_input(p):
    with p.open(encoding="utf-8-sig") as f:r=list(csv.DictReader(f))
    for v in r:
        v["sampleOrder"]=int(v["sampleOrder"])
        for k in ("centerLat","centerLon","jaxaWater","jaxaBuilt","jaxaGreen"):v[k]=float(v[k])
    return sorted(r,key=lambda v:v["sampleOrder"])
def bbox(v):
    lon,lat=v["centerLon"],v["centerLat"];l,t=wp(lon-DX/2,lat+DY/2);r,b=wp(lon+DX/2,lat-DY/2);return l,t,r,b
def tiles(v):
    l,t,r,b=bbox(v);return [(x,y) for y in range(int(t//256),int((b-1e-9)//256)+1) for x in range(int(l//256),int((r-1e-9)//256)+1)]
def fetch_tile(q,raw):
    x,y=q;key=f"{Z}/{x}/{y}";p=raw/f"{Z}_{x}_{y}.jpg";u=TILE.format(Z,x,y);err=""
    for n in range(1,6):
        try:
            r=requests.get(u,headers={"User-Agent":"ECOSCAPE-B79/1.0"},timeout=(15,60));r.raise_for_status();im=Image.open(io.BytesIO(r.content));im.verify()
            if im.size!=(256,256):raise RuntimeError(im.size)
            p.write_bytes(r.content);z={"tileKey":key,"url":u,"status":"PASS","bytes":len(r.content),"sha256":sha(r.content),"attempt":n,"etag":r.headers.get("etag"),"sourceVintage":"VARIABLE_UNRESOLVED"};(raw/f"{Z}_{x}_{y}.json").write_bytes(canon(z));return z
        except Exception as e:err=f"{type(e).__name__}:{e}";time.sleep(min(8,2**(n-1)))
    z={"tileKey":key,"url":u,"status":"ERROR","error":err};(raw/f"{Z}_{x}_{y}.json").write_bytes(canon(z));return z
def crop(v,raw):
    q=tiles(v);l,t,r,b=bbox(v);x0,y0=min(x for x,y in q),min(y for x,y in q);x1,y1=max(x for x,y in q),max(y for x,y in q);m=Image.new("RGB",((x1-x0+1)*256,(y1-y0+1)*256))
    for x,y in q:
        p=raw/f"{Z}_{x}_{y}.jpg"
        if not p.exists():return None,[f"{Z}/{a}/{b}" for a,b in q],f"MISSING:{x}/{y}"
        with Image.open(p) as im:m.paste(im.convert("RGB"),((x-x0)*256,(y-y0)*256))
    return m.crop((int(l-x0*256),int(t-y0*256),math.ceil(r-x0*256),math.ceil(b-y0*256))),[f"{Z}/{a}/{b}" for a,b in q],""
def feat(im):
    a=np.asarray(im,dtype=np.float32)/255;r,g,b=a[:,:,0],a[:,:,1],a[:,:,2];mx=a.max(2);mn=a.min(2);sat=np.divide(mx-mn,mx,out=np.zeros_like(mx),where=mx>0);ex=2*g-r-b;gr=g/np.maximum(r+g+b,1e-4);gray=.299*r+.587*g+.114*b
    dx=np.abs(np.diff(gray,axis=1));dy=np.abs(np.diff(gray,axis=0))
    return {"rMean":float(r.mean()),"gMean":float(g.mean()),"bMean":float(b.mean()),"rStd":float(r.std()),"gStd":float(g.std()),"bStd":float(b.std()),"satMean":float(sat.mean()),"exgMean":float(ex.mean()),"exgStd":float(ex.std()),"greenDom":float(((g>r*1.05)&(g>b*1.05)&(sat>.12)).mean()),"blueDom":float(((b>r*1.05)&(b>g*1.05)&(sat>.1)).mean()),"ngr":float(gr.mean()),"dark":float((mx<.22).mean()),"bright":float((mx>.78).mean()),"edge":float(((dx>.1).mean()+(dy>.1).mean())/2)}
def write_csv(p,rows):
    keys=[]
    for v in rows:
        for k in v:
            if k not in keys:keys.append(k)
    with p.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for v in rows:
            q=dict(v)
            if isinstance(q.get("tileKeys"),list):q["tileKeys"]=json.dumps(q["tileKeys"],separators=(",",":"))
            w.writerow(q)
def evaluate(rows):
    names=["rMean","gMean","bMean","rStd","gStd","bStd","satMean","exgMean","exgStd","greenDom","blueDom","ngr","dark","bright","edge"]
    q=[v for v in rows if v["status"]=="PASS"];X=np.array([[v[k] for k in names] for v in q]);groups=np.array([v["municipalityCode"] for v in q]);n=min(5,len(set(groups)));out={}
    for label,target,limit,improve in (("green","jaxaGreen",.20,.10),("built","jaxaBuilt",.20,.10),("water","jaxaWater",.12,.05)):
        y=np.array([float(v[target]) for v in q]);pred=np.zeros(len(y));base=np.zeros(len(y))
        for i,(tr,te) in enumerate(GroupKFold(n_splits=n).split(X,y,groups),1):
            m=ExtraTreesRegressor(n_estimators=250,min_samples_leaf=4,max_features=.75,random_state=20260817+i,n_jobs=-1);m.fit(X[tr],y[tr]);pred[te]=np.clip(m.predict(X[te]),0,1);base[te]=y[tr].mean()
        mae=mean_absolute_error(y,pred);bmae=mean_absolute_error(y,base);imp=1-mae/bmae if bmae else None
        out[label]={"mae":float(mae),"baselineMae":float(bmae),"improvement":float(imp) if imp is not None else None,"r2":float(r2_score(y,pred)),"pass":bool(mae<=limit and imp is not None and imp>=improve)}
    return {"features":names,"method":"ExtraTrees GroupKFold by municipality","targets":out,"allTargetsPass":all(v["pass"] for v in out.values())}
def main():
    a=argparse.ArgumentParser();a.add_argument("--input",type=Path);a.add_argument("--raw-dir",type=Path,required=True);a.add_argument("--output-dir",type=Path,required=True);a.add_argument("--mode",choices=("fetch","replay"),required=True);a.add_argument("--workers",type=int,default=12);x=a.parse_args();x.raw_dir.mkdir(parents=True,exist_ok=True);x.output_dir.mkdir(parents=True,exist_ok=True)
    rows=read_input(x.input) if x.input else remote_input(x.output_dir);uq=sorted({t for v in rows for t in tiles(v)});manifest=[]
    if x.mode=="fetch":
        with ThreadPoolExecutor(max_workers=min(16,max(1,x.workers))) as pool:
            fs=[pool.submit(fetch_tile,t,x.raw_dir) for t in uq]
            for i,f in enumerate(as_completed(fs),1):z=f.result();manifest.append(z);print(f"[{i}/{len(uq)}] {z['tileKey']} {z['status']}",flush=True)
    else:
        manifest=[json.loads(p.read_bytes()) for p in x.raw_dir.glob("*.json")]
    facts=[]
    for v in rows:
        im,keys,err=crop(v,x.raw_dir);z={**v,"status":"ERROR" if err else "PASS","tileKeys":keys,"missingReason":err,"sourceId":SOURCE,"sourceVintage":"VARIABLE_UNRESOLVED","semanticCanopyClaim":False,"scoringEffect":"none","buildId":BUILD}
        if im is not None:z.update(feat(im))
        facts.append(z)
    facts.sort(key=lambda v:v["sampleOrder"]);write_csv(x.output_dir/"ECOSCAPE_GSI_QA300_RGB_FEATURES_B79.csv",facts);fb=canon(facts);(x.output_dir/"ECOSCAPE_GSI_QA300_RGB_FEATURES_B79.json").write_bytes(fb);ev=evaluate(facts);cs=Counter(v["status"] for v in facts);ts=Counter(v.get("status") for v in manifest)
    report={"buildId":BUILD,"qaRows":len(facts),"uniqueCells":len({v["cellId"] for v in facts}),"uniqueTiles":len(uq),"cellStatusCounts":dict(cs),"tileStatusCounts":dict(ts),"factsSha256":sha(fb),"sourceVintage":"VARIABLE_UNRESOLVED","semanticCanopyClaim":False,"modelValidation":ev,"promotionDecision":"PROXY_ELIGIBLE_NO_SCORING" if ev["allTargetsPass"] and not cs.get("ERROR") else "HOLD_AS_QA_EVIDENCE","fullDomainTilePlanEligible":True,"scoringEffect":"none","coreOverwrite":False,"globalNexusWrites":0,"crossProjectDirectWrites":0,"qaPass":len(facts)==300 and len({v["cellId"] for v in facts})==300 and not cs.get("ERROR")}
    (x.output_dir/"ECOSCAPE_GSI_QA300_MODEL_REPORT_B79.json").write_bytes(canon(report));(x.output_dir/"ECOSCAPE_GSI_QA300_TILE_RECEIPTS_B79.json").write_bytes(canon(sorted(manifest,key=lambda v:v["tileKey"])));print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report["qaPass"] else 2
if __name__=="__main__":raise SystemExit(main())
