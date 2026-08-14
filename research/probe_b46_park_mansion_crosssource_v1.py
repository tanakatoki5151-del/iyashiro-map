#!/usr/bin/env python3
"""V10 B46 Park Mansion isolated PLATEAU + GSI cross-source probe v1.

Research-only geometry discovery for BLDG-8bafd187bc1e.
Reuses the already-audited SPHERE probe engines but keeps this execution on an
isolated branch. No formal promotion or score/rank/exclusion change.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import requests
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_b46_sphere_plateau_v1 as pl
import probe_b46_sphere_gsi_vector_v1 as gv

ADDRESS = "東京都目黒区東が丘2丁目13-11"
PROPERTY_ID = "BLDG-8bafd187bc1e"
NAME = "パークマンション"
OUT = Path("out-b46-park-mansion-crosssource-v1")
ATTR_API = "https://api.plateauview.mlit.go.jp/citygml/attributes"


def ftcode(c):
    p=c.get("properties") or {}
    v=p.get("ftCode",p.get("ftcode"))
    try:return int(v)
    except:return None


def bid(c):
    vals=(c.get("attributes") or {}).get("buildingID") or []
    return vals[0] if vals else None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s=requests.Session(); s.headers["User-Agent"]="iyashiro-v10-research/1.0"
    r=s.get(pl.GSI,params={"q":ADDRESS},timeout=30); r.raise_for_status(); data=r.json()
    if not data: raise RuntimeError("GSI address search returned no result")
    lon,lat=map(float,data[0]["geometry"]["coordinates"][:2])
    gsi_title=data[0].get("properties",{}).get("title")

    pl.TARGET={
        "propertyId":PROPERTY_ID,"buildingName":NAME,"address":ADDRESS,
        "lat":lat,"lon":lon,"expectedStoreys":3,"expectedYear":1968,
        "expectedUnits":None,"thresholdM":500.0,"representativeDistanceM":508.9,
        "identitySources":["HOME'S","Yahoo不動産"],
        "developerPhysicalControl":{"buildingAreaM2":1.0,"role":"unknown_not_used_for_selection"},
        "staleOsmWayId":688654246,"staleOsmReason":"candidate only; identity not assumed",
    }
    pl.OUT=Path("out-b46-park-mansion-plateau-v1")
    pl.RADIUS_M=80.0
    pl.main()

    gv.TARGET={
        "propertyId":PROPERTY_ID,"buildingName":NAME,"address":ADDRESS,
        "lon":lon,"lat":lat,"completion":"1968-12","units":None,
        "storeysAboveGround":3,"storeysBelowGround":None,
        "maxFloorPrivateAreaM2":None,"representativeTempleDistanceM":508.9,
    }
    gv.OUT=Path("out-b46-park-mansion-gsi-vector-v1")
    gv.RADIUS_M=80.0
    gv.main()

    ps=json.loads((pl.OUT/"SUMMARY.json").read_text(encoding="utf-8"))
    gs=json.loads((gv.OUT/"SUMMARY.json").read_text(encoding="utf-8"))
    pcands=[c for c in ps["candidates"] if c.get("storeysMatch") and c.get("distanceFromGsiM",999)<=30]
    gcands=[c for c in gs.get("likelyBuildingPolygons",[]) if c.get("distanceFromCurrentPointM",999)<=30]
    to6677=Transformer.from_crs(4326,6677,always_xy=True)
    rows=[]
    for p in pcands:
        pm=shp_transform(to6677.transform,shape(p["geometry"]))
        ovs=[]
        for g in gcands:
            gm=shp_transform(to6677.transform,shape(g["geometry"]))
            inter=pm.intersection(gm).area
            if inter<=0: continue
            ovs.append({
                "gsiFeatureId":g.get("featureId"),"ftCode":ftcode(g),
                "gsiAreaM2":round(gm.area,3),"intersectionM2":round(inter,3),
                "coverageOfGsi":round(inter/gm.area,6) if gm.area else 0,
                "coverageOfPlateau":round(inter/pm.area,6) if pm.area else 0,
                "gsiDistanceM":g.get("distanceFromCurrentPointM"),
            })
        ovs.sort(key=lambda x:(-x["intersectionM2"],-x["coverageOfGsi"]))
        rows.append({
            "buildingID":bid(p),"gmlId":p["attributes"].get("gmlId"),
            "distanceFromGsiM":p["distanceFromGsiM"],"areaM2":p["areaM2"],
            "storeys":p["attributes"].get("storeysAboveGround"),
            "height":p["attributes"].get("measuredHeight"),
            "localityNames":p["attributes"].get("localityNames"),
            "geometry":p["geometry"],"bestGsiOverlap":ovs[0] if ovs else None,
        })

    source_url=next((x["url"] for x in ps["sourceFiles"] if x.get("cityCode")=="13110"), ps["sourceFiles"][0]["url"])
    ids=[x["gmlId"] for x in rows if x.get("gmlId")][:20]
    attrs={"status":"not_requested","records":[]}
    if ids:
        try:
            ar=s.get(ATTR_API,params={"url":source_url,"id":",".join(ids)},timeout=120); ar.raise_for_status()
            attrs={"status":"success","requestUrl":ar.url,"records":ar.json()}
        except Exception as e:
            attrs={"status":"failed_nonblocking","error":f"{type(e).__name__}: {e}","records":[]}
    byid={x.get("gml:id"):x for x in attrs.get("records",[]) if isinstance(x,dict)}
    for row in rows:
        a=byid.get(row.get("gmlId"),{})
        row["attributeAddress"]=a.get("bldg:address")
        row["attributeClass"]=a.get("bldg:class")
        row["attributeStoreys"]=a.get("bldg:storeysAboveGround")
        row["attributeCreationDate"]=a.get("core:creationDate")
        ov=row.get("bestGsiOverlap") or {}
        row["selectionSignals"]={
            "within5m":row["distanceFromGsiM"]<=5,
            "threeStoreys":row.get("storeys")==3 or row.get("attributeStoreys")==3,
            "strongGsiOverlap":ov.get("coverageOfGsi",0)>=0.80,
            "meguroHigashigaokaAddress":any("東が丘" in str(v) for v in (row.get("attributeAddress") or [])),
        }
    rows.sort(key=lambda x:(not all(x["selectionSignals"].values()),x["distanceFromGsiM"],-(x.get("bestGsiOverlap") or {}).get("coverageOfGsi",0)))
    selected=rows[0] if rows and all(rows[0]["selectionSignals"].values()) else None

    result={
        "schemaVersion":"v10-b46-park-mansion-crosssource-v1",
        "target":{"propertyId":PROPERTY_ID,"buildingName":NAME,"address":ADDRESS,"gsiTitle":gsi_title,"lon":lon,"lat":lat,"publicFacts":{"built":"1968-12","structure":"RC","storeys":3}},
        "plateauCandidateCount3FWithin30m":len(pcands),
        "gsiBuildingCountWithin30m":len(gcands),
        "candidates":rows,
        "selectedHighConfidenceCandidate":selected,
        "attributeApi":attrs,
        "formalBuildingPolygonsPromoted":0,"verifiedGeometryAdded":0,
        "policy":{"formalPromotion":False,"scoringEffect":"none","rankingEffect":"none","automaticExclusionEffect":"none","nextGate":"compute frozen V10 sensitive distances locally for selected candidate; formalize only after identity/attribute integrity QA"},
    }
    (OUT/"SUMMARY.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"README.md").write_text("\n".join([
        "# V10 B46 Park Mansion cross-source probe v1","",
        f"- GSI anchor: {lat}, {lon} / {gsi_title}",
        f"- PLATEAU 3F candidates <=30m: {len(pcands)}",
        f"- GSI building candidates <=30m: {len(gcands)}",
        f"- selected high-confidence candidate: {selected.get('buildingID') if selected else 'NONE'}",
        "- formal promotion: 0","- score/rank/exclusion: 0",
        *[f"- #{i}: id={x['buildingID']} d={x['distanceFromGsiM']}m area={x['areaM2']}m2 storeys={x['storeys']} attr={x['attributeAddress']} overlap={x.get('bestGsiOverlap')} signals={x['selectionSignals']}" for i,x in enumerate(rows[:15],1)]
    ])+"\n",encoding="utf-8")
    print(json.dumps({"gsi":[lat,lon],"plateau3F30m":len(pcands),"gsi30m":len(gcands),"selected":selected.get("buildingID") if selected else None,"formalPromotion":0},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
