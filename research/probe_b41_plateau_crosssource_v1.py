#!/usr/bin/env python3
"""Probe official MLIT PLATEAU CityGML as an independent B41 building source.

Fail-closed research probe. This script does NOT promote formal building geometry.
It queries the official PLATEAU delivery API by coordinate, downloads only the
relevant building CityGML mesh files, extracts nearby building footprints/attributes,
and writes a reproducible candidate set for later identity/shape QA.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from lxml import etree
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shp_transform

API = "https://api.plateauview.mlit.go.jp"
OUT = Path("out-b41-plateau-crosssource-v1")
RADIUS_M = 90.0
TARGETS = [
    {"propertyId":"BLDG-6583382c8322","buildingName":"レ・サン・サーンス","address":"東京都目黒区目黒本町5丁目29-12","lat":35.620316,"lon":139.697525,"expectedStoreys":3,"expectedYear":2014},
    {"propertyId":"BLDG-edf6c2448f9e","buildingName":"エスティメゾン代沢","address":"東京都世田谷区代沢2丁目39-13","lat":35.659447,"lon":139.673950,"expectedStoreys":3,"expectedYear":2010},
    {"propertyId":"BLDG-4e6c9a14c783","buildingName":"レオパレス駒場東大前","address":"東京都目黒区駒場4丁目3-21","lat":35.660763,"lon":139.680847,"expectedStoreys":2,"expectedYear":2000},
    {"propertyId":"BLDG-c404c81c08a5","buildingName":"プリュメゾン駒沢","address":"東京都目黒区東が丘1丁目16-26","lat":35.628464,"lon":139.668793,"expectedStoreys":4,"expectedYear":1991},
]


def localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def first_text(elem, names):
    for x in elem.iter():
        if localname(x.tag) in names and x.text and x.text.strip():
            return x.text.strip()
    return None


def all_text(elem, names):
    out=[]
    for x in elem.iter():
        if localname(x.tag) in names and x.text and x.text.strip():
            v=x.text.strip()
            if v not in out: out.append(v)
    return out


def epsg_from_srs(srs: str | None):
    if not srs: return None
    m=re.search(r"EPSG(?::|/0/|::)(\d+)",srs)
    if not m:
        m=re.search(r"(\d{4,5})$",srs)
    return int(m.group(1)) if m else None


def split_coords(text: str, dim: int | None):
    vals=[float(v) for v in text.split()]
    if dim not in (2,3):
        dim=3 if len(vals)%3==0 else 2
    return [tuple(vals[i:i+dim]) for i in range(0,len(vals)-dim+1,dim)]


def coord_to_lonlat(x,y,epsg):
    # PLATEAU frequently uses geographic JGD2011 compound CRS whose GML axis order
    # appears as latitude, longitude. Detect the Tokyo-looking pattern explicitly.
    if 30 <= x <= 40 and 130 <= y <= 145:
        return (y,x)
    if 130 <= x <= 145 and 30 <= y <= 40:
        return (x,y)
    if epsg:
        try:
            tr=Transformer.from_crs(CRS.from_epsg(epsg),CRS.from_epsg(4326),always_xy=True)
            lon,lat=tr.transform(x,y)
            if -180 <= lon <= 180 and -90 <= lat <= 90:
                return (lon,lat)
        except Exception:
            pass
    return None


def extract_ring(building):
    # Prefer LOD0 projected footprint. Fall back to GroundSurface, then any polygon ring.
    preferred=("lod0FootPrint","lod0RoofEdge","GroundSurface")
    containers=[]
    for p in preferred:
        containers.extend([x for x in building.iter() if localname(x.tag)==p])
    containers.append(building)
    seen=set()
    for container in containers:
        for pos in container.iter():
            if localname(pos.tag)!="posList" or not pos.text: continue
            key=pos.text.strip()
            if key in seen: continue
            seen.add(key)
            srs=pos.get("srsName")
            parent=pos.getparent()
            q=parent
            while not srs and q is not None:
                srs=q.get("srsName")
                q=q.getparent()
            dim_txt=pos.get("srsDimension")
            dim=int(dim_txt) if dim_txt and dim_txt.isdigit() else None
            coords=split_coords(key,dim)
            epsg=epsg_from_srs(srs)
            ll=[]
            for c in coords:
                p=coord_to_lonlat(c[0],c[1],epsg)
                if p: ll.append(p)
            if len(ll)>=4:
                if ll[0]!=ll[-1]: ll.append(ll[0])
                poly=Polygon(ll)
                if poly.is_valid and not poly.is_empty and poly.area>0:
                    return poly,{"srsName":srs,"epsg":epsg,"sourceElement":localname(container.tag),"pointCount":len(ll)}
    return None,None


def local_projector(lon,lat):
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs")
    fwd=Transformer.from_crs(4326,crs,always_xy=True).transform
    return fwd


def citygml_files_for_point(session,lon,lat):
    url=f"{API}/datacatalog/citygml/r:{lon},{lat}?types=bldg"
    r=session.get(url,timeout=30)
    r.raise_for_status()
    data=r.json()
    cities=data.get("cities") or data.get("citygml") or data.get("datasets") or []
    # The coordinate endpoint currently returns {cities:[...]}; retain a generic fallback.
    if isinstance(data,list): cities=data
    rows=[]
    for city in cities:
        files=(city.get("files") or {}).get("bldg") or []
        for f in files:
            if f.get("url"):
                rows.append({"cityCode":city.get("cityCode") or city.get("city_code"),"cityName":city.get("cityName") or city.get("city"),"year":city.get("year"),"registrationYear":city.get("registrationYear") or city.get("registration_year"),"spec":city.get("spec"),"meshCode":f.get("code"),"maxLod":f.get("maxLod"),"fileSize":f.get("fileSize"),"url":f.get("url")})
    if not rows:
        raise RuntimeError(f"no bldg CityGML file from {url}; top-level keys={list(data) if isinstance(data,dict) else type(data)}")
    maxyear=max((r.get("year") or 0) for r in rows)
    return url,[r for r in rows if (r.get("year") or 0)==maxyear],data


def parse_gml_bytes(blob, target):
    root=etree.fromstring(blob)
    fwd=local_projector(target["lon"],target["lat"])
    tx,ty=fwd(target["lon"],target["lat"])
    found=[]
    for b in root.iter():
        if localname(b.tag)!="Building": continue
        poly,geom_meta=extract_ring(b)
        if poly is None: continue
        pp=shp_transform(fwd,poly)
        d=pp.distance(__import__('shapely').geometry.Point(tx,ty))
        cd=pp.centroid.distance(__import__('shapely').geometry.Point(tx,ty))
        if d>RADIUS_M and cd>RADIUS_M: continue
        gid=None
        for k,v in b.attrib.items():
            if localname(k)=="id": gid=v
        attrs={
            "gmlId":gid,
            "name":all_text(b,{"name"})[:5],
            "buildingID":all_text(b,{"buildingID","buildingIDAttribute"})[:5],
            "measuredHeight":first_text(b,{"measuredHeight"}),
            "storeysAboveGround":first_text(b,{"storeysAboveGround"}),
            "yearOfConstruction":first_text(b,{"yearOfConstruction"}),
            "usage":all_text(b,{"usage"})[:5],
            "function":all_text(b,{"function"})[:5],
        }
        found.append({
            "distanceToFootprintM":round(d,3),
            "centroidDistanceM":round(cd,3),
            "areaM2":round(pp.area,2),
            "bounds":[round(x,7) for x in poly.bounds],
            "geometryMeta":geom_meta,
            "attributes":attrs,
            "geometry":mapping(poly),
        })
    found.sort(key=lambda x:(x["distanceToFootprintM"],x["centroidDistanceM"],x["areaM2"]))
    return found


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    session=requests.Session(); session.headers["User-Agent"]="iyashiro-v10-research/1.0"
    results=[]; features=[]; raw_catalog={}
    for target in TARGETS:
        query_url,files,catalog=citygml_files_for_point(session,target["lon"],target["lat"])
        raw_catalog[target["propertyId"]]={"queryUrl":query_url,"response":catalog}
        all_candidates=[]; source_files=[]
        for row in files:
            r=session.get(row["url"],timeout=60); r.raise_for_status()
            blob=r.content
            sha=hashlib.sha256(blob).hexdigest()
            source_files.append({**row,"downloadedBytes":len(blob),"sha256":sha})
            try:
                candidates=parse_gml_bytes(blob,target)
            except Exception as e:
                candidates=[]
                row={**row,"parseError":repr(e)}
            for c in candidates:
                c["sourceMeshCode"]=row.get("meshCode")
                c["sourceSha256"]=sha
                all_candidates.append(c)
        # de-duplicate same gml:id / geometry across files
        uniq=[]; seen=set()
        for c in sorted(all_candidates,key=lambda x:(x["distanceToFootprintM"],x["centroidDistanceM"])):
            k=(c["attributes"].get("gmlId"),json.dumps(c["geometry"],sort_keys=True))
            if k in seen: continue
            seen.add(k); uniq.append(c)
        for idx,c in enumerate(uniq):
            features.append({"type":"Feature","properties":{"propertyId":target["propertyId"],"targetName":target["buildingName"],"candidateRank":idx+1,"distanceToFootprintM":c["distanceToFootprintM"],"centroidDistanceM":c["centroidDistanceM"],"areaM2":c["areaM2"],**c["attributes"]},"geometry":c["geometry"]})
        results.append({**target,"catalogQueryUrl":query_url,"sourceFiles":source_files,"candidateCountWithin90m":len(uniq),"candidates":uniq,"formalPromotion":False,"scoringEffect":"none","rankingEffect":"none","automaticExclusionEffect":"none"})
    summary={"schemaVersion":"v10-b41-plateau-crosssource-v1","generatedAt":datetime.now(timezone.utc).isoformat(),"source":{"provider":"MLIT Project PLATEAU delivery API","apiBase":API,"queryMode":"coordinate range, types=bldg, latest returned year only"},"radiusM":RADIUS_M,"targets":len(TARGETS),"formalBuildingPolygonsPromoted":0,"verifiedGeometryAdded":0,"policy":{"independentSourceProbeOnly":True,"scoringEffect":"none","rankingEffect":"none","automaticExclusionEffect":"none"},"items":results}
    (OUT/"SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"plateau-candidates.geojson").write_text(json.dumps({"type":"FeatureCollection","features":features},ensure_ascii=False),encoding="utf-8")
    (OUT/"catalog-responses.json").write_text(json.dumps(raw_catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    md=["# V10 B41 PLATEAU cross-source probe v1","","Official MLIT PLATEAU CityGML independent-source probe. No formal promotion in this probe.",""]
    for item in results:
        md.append(f"## {item['buildingName']} ({item['propertyId']})")
        md.append(f"Candidates within {RADIUS_M:.0f}m: {item['candidateCountWithin90m']}")
        for i,c in enumerate(item['candidates'][:12],1):
            a=c['attributes']; md.append(f"- #{i}: d={c['distanceToFootprintM']}m centroid={c['centroidDistanceM']}m area={c['areaM2']}m² id={a.get('gmlId')} floors={a.get('storeysAboveGround')} year={a.get('yearOfConstruction')} height={a.get('measuredHeight')} names={a.get('name')} buildingID={a.get('buildingID')}")
        md.append("")
    md += ["## Policy","- formal building polygon promotion: 0","- scoring/ranking/automatic-exclusion changes: none","- next gate: compare PLATEAU candidates with frozen OSM candidates and independent property facts"]
    (OUT/"README.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    sums=[]
    for p in sorted(OUT.iterdir()):
        if p.name=="SHA256SUMS.txt" or not p.is_file(): continue
        sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (OUT/"SHA256SUMS.txt").write_text("\n".join(sums)+"\n",encoding="utf-8")
    # Compact stdout for CI logs
    print(json.dumps({"targets":len(results),"candidateCounts":{x['propertyId']:x['candidateCountWithin90m'] for x in results},"formalPromotion":0},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
