#!/usr/bin/env python3
"""Direct-bbox GSI aerial acquisition for the Oyama/Nishihara institution study.

Avoids the map UI entirely. GSI's public photo search API is queried with a
small Shibuya bbox and explicit date windows. Search results are accepted only
when the official date falls inside the requested window and the official
four-corner photo footprint intersects the bbox. Detail API is then used to get
public standard-image URLs. Imagery can reveal facility-change candidates but
cannot identify Tokyo Medical Juvenile Training School or change scoring alone.
"""
from __future__ import annotations
import hashlib, json, math, re, time
from pathlib import Path
from urllib.parse import urljoin
import requests

OUT=Path('out-gsi-oyama-direct-bbox'); OUT.mkdir(parents=True,exist_ok=True)
IM=OUT/'images'; IM.mkdir(exist_ok=True)
API='https://service.gsi.go.jp/map-photos/app/api/photo'
IMG='https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/'
W,S,E,N=139.65797586230588,35.660278821538085,139.69230813769747,35.67945402690383
OYAMA=(139.675142,35.669867)
JICA=(139.6752,35.67341)  # comparison point only; not historical proof
WINDOWS=[(1949,1956),(1957,1965),(1966,1978)]
SESSION=requests.Session();SESSION.headers.update({'User-Agent':'iyashiro-map research/1.0 direct GSI bbox','Accept-Language':'ja'})

def pip(lon,lat,c):
    z=False;q=c+[c[0]]
    for (x1,y1),(x2,y2) in zip(q,q[1:]):
        if (y1>lat)!=(y2>lat):
            xc=(x2-x1)*(lat-y1)/(y2-y1)+x1
            if lon<xc:z=not z
    return z

def bb(c):
    xs=[x[0] for x in c];ys=[x[1] for x in c];return min(xs),min(ys),max(xs),max(ys)
def inter(a,b):return not(a[2]<b[0] or b[2]<a[0] or a[3]<b[1] or b[3]<a[1])
def hav(a,b):
    lo1,la1=a;lo2,la2=b;r=6371008.8;p1,p2=map(math.radians,(la1,la2));dp=math.radians(la2-la1);dl=math.radians(lo2-lo1)
    v=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(v))
def get(url,params=None,tries=4):
    log=[]
    for i in range(1,tries+1):
        try:
            r=SESSION.get(url,params=params,timeout=(15,90));log.append({'try':i,'status':r.status_code,'bytes':len(r.content),'url':r.url})
            if r.status_code in (429,502,503,504):time.sleep(2**i);continue
            r.raise_for_status();return r,log
        except Exception as e:
            log.append({'try':i,'error':f'{type(e).__name__}: {e}'});time.sleep(2**i)
    return None,log

allrows=[]; querylogs=[]
for y0,y1 in WINDOWS:
    offset=0
    while True:
        params={'limit':200,'offset':offset,'rnem':0,'cnem':0,'search_date_from':y0,'search_date_to':y1,'color_type_ids':[1,2],'scale_from':0,'scale_to':99999999,'lon_min':W,'lon_max':E,'lat_min':S,'lat_max':N}
        r,logs=get(API,params); querylogs += [{'window':[y0,y1],'offset':offset,**x} for x in logs]
        if r is None:break
        payload=r.json();results=payload.get('results') or [];rs=payload.get('resultset') or {}
        for x in results:
            c=[x.get('geom_image_left_top_pos'),x.get('geom_image_right_top_pos'),x.get('geom_image_right_bottom_pos'),x.get('geom_image_left_bottom_pos')];c=[v for v in c if isinstance(v,list) and len(v)==2]
            try:yr=int(str(x.get('search_date'))[:4])
            except:yr=0
            valid_date=y0<=yr<=y1; valid_bbox=len(c)==4 and inter(bb(c),(W,S,E,N))
            if not(valid_date and valid_bbox):continue
            x['queryWindow']=[y0,y1];x['coversOyama']=pip(*OYAMA,c);x['coversJica']=pip(*JICA,c);cen=x.get('geom_center_pos') or [None,None]
            if len(cen)==2 and all(isinstance(v,(int,float)) for v in cen):x['centerDistanceOyamaM']=hav(OYAMA,(cen[0],cen[1]));x['centerDistanceJicaM']=hav(JICA,(cen[0],cen[1]))
            allrows.append(x)
        count=int(rs.get('count') or len(results));total=int(rs.get('total_count') or len(results));offset += count
        if count==0 or offset>=total:break
        time.sleep(1)

# Deduplicate specification ids and enforce spatial/date gate once more.
uniq={}
for x in allrows:uniq[x['specification_id']]=x
rows=list(uniq.values());rows.sort(key=lambda x:(str(x.get('search_date')),x.get('centerDistanceJicaM',1e99)))
(OUT/'search-metadata.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'query-log.json').write_text(json.dumps(querylogs,ensure_ascii=False,indent=2),encoding='utf-8')

# Prioritize photos covering the current JICA comparison point, then Oyama representative point,
# while keeping date/course diversity. This is for change detection only.
candidates=sorted(rows,key=lambda x:(not x.get('coversJica'),not x.get('coversOyama'),x.get('centerDistanceJicaM',1e99)))
selected=[];seen_date_course=set()
for x in candidates:
    key=(str(x.get('search_date')),str(x.get('reference_number')),str(x.get('course_number')))
    if key in seen_date_course and len(selected)>=12:continue
    seen_date_course.add(key);selected.append(x)
    if len(selected)>=30:break

downloads=[]
for x in selected:
    pid=x['specification_id'];r,logs=get(f'{API}/{pid}');querylogs += [{'detailPhotoId':pid,**q} for q in logs]
    if r is None:continue
    detail=(r.json().get('results') or {});rel=detail.get('url_image_standard')
    d={'photoId':pid,'date':x.get('search_date'),'planner':x.get('planning_organization'),'referenceNumber':x.get('reference_number'),'courseNumber':x.get('course_number'),'photoNumber':x.get('photo_number'),'city':x.get('city_name'),'coversOyama':x.get('coversOyama'),'coversJica':x.get('coversJica'),'centerDistanceJicaM':x.get('centerDistanceJicaM')}
    if not rel:d['status']='no_standard_image';downloads.append(d);continue
    u=urljoin(IMG,rel);img,ilogs=get(u);querylogs += [{'imagePhotoId':pid,**q} for q in ilogs]
    if img is not None and img.content[:3]==b'\xff\xd8\xff':
        name=re.sub(r'[^A-Za-z0-9._-]+','_',f"{x.get('search_date')}_{x.get('reference_number')}-{x.get('course_number')}-{x.get('photo_number')}_id{pid}.jpg");p=IM/name;p.write_bytes(img.content);d['savedAs']=str(p.relative_to(OUT));d['sha256']=hashlib.sha256(img.content).hexdigest();d['bytes']=len(img.content)
    downloads.append(d);time.sleep(.5)
(OUT/'downloads.json').write_text(json.dumps(downloads,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'query-log.json').write_text(json.dumps(querylogs,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'SHA256SUMS.txt').open('w',encoding='utf-8') as f:
    for p in sorted(IM.glob('*.jpg')):f.write(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n')
summary={'version':'oyama-nishihara-gsi-direct-bbox-v1-20260813','studyBBox':[W,S,E,N],'oyamaRepresentativePoint':OYAMA,'jicaComparisonPoint':JICA,'windows':[list(x) for x in WINDOWS],'acceptedMetadataCount':len(rows),'dates':sorted(set(str(x.get('search_date')) for x in rows)),'planningOrganizations':sorted(set(str(x.get('planning_organization')) for x in rows)),'cities':sorted(set(str(x.get('city_name')) for x in rows)),'coversJicaCount':sum(bool(x.get('coversJica')) for x in rows),'coversOyamaCount':sum(bool(x.get('coversOyama')) for x in rows),'selectedCount':len(selected),'downloadedCount':sum(bool(x.get('savedAs')) for x in downloads),'qualityRule':'Every accepted search row passed explicit GSI date + official footprint/bbox gates. JICA point is a comparison point only. Facility identity/parcel requires independent archival corroboration. scoringEffect=none.'}
(OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
