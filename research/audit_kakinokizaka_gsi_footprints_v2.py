#!/usr/bin/env python3
"""Re-score 1945-1971 GSI photo footprints using the frozen 62-vertex current culvert proxy.

This repairs v1's live-Overpass timeout without changing or re-interpreting the acquired photographs.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path("out-kakinokizaka-gsi-footprints-v2")
CULVERT = Path("research/inputs/kakinokizaka-current-culvert-proxy-v1.geojson")
GSI_API = "https://service.gsi.go.jp/map-photos/app/api/photo"
GSI_PAGE = "https://service.gsi.go.jp/map-photos/app/map?search=photo&search_date_from=1945&search_date_to=1971#14/35.627/139.673"
BBOX = {"lon_min": 139.6625, "lon_max": 139.6815, "lat_min": 35.6165, "lat_max": 35.6385}
CELLS = [
    {"cellId": "g233-217", "lat": 35.630340, "lon": 139.669621},
    {"cellId": "g239-220", "lat": 35.624952, "lon": 139.672934},
]
S = requests.Session()
S.headers.update({"User-Agent":"iyashiro-map-v10-gsi-footprint-audit/2.0","Referer":GSI_PAGE,"Accept":"application/json"})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point_in_poly(lon: float, lat: float, corners: list[list[float]]) -> bool:
    inside = False
    pts = corners + [corners[0]]
    for (x1,y1),(x2,y2) in zip(pts, pts[1:]):
        if (y1 > lat) != (y2 > lat):
            xc=(x2-x1)*(lat-y1)/(y2-y1)+x1
            if lon < xc: inside = not inside
    return inside


def sample_vertices(coords: list[list[float]], max_points: int = 30) -> list[dict]:
    if len(coords) <= max_points:
        idxs=list(range(len(coords)))
    else:
        idxs=sorted(set(round(i*(len(coords)-1)/(max_points-1)) for i in range(max_points)))
    return [{"id":f"culvert-{i:02d}","lon":coords[j][0],"lat":coords[j][1]} for i,j in enumerate(idxs)]


def year_of(item: dict) -> int:
    m=re.search(r"(19\d{2})",str(item.get("search_date") or ""))
    return int(m.group(1)) if m else 0


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True)
    frozen=json.loads(CULVERT.read_text(encoding="utf-8"))
    coords=frozen["features"][0]["geometry"]["coordinates"]
    samples=sample_vertices(coords)
    points=samples+[{"id":c["cellId"],"lon":c["lon"],"lat":c["lat"]} for c in CELLS]

    params={"limit":200,"offset":0,"rnem":0,"cnem":0,"search_date_from":1945,"search_date_to":1971,"color_type_ids":[1,2],"scale_from":0,"scale_to":99999999,**BBOX}
    url=f"{GSI_API}?{urllib.parse.urlencode(params,doseq=True)}"
    r=S.get(url,timeout=120);r.raise_for_status();payload=r.json()
    rows=payload.get("results") or []
    ids=sorted({int(x["specification_id"]) for x in rows if x.get("specification_id") not in (None,"")})
    scored=[]
    for pid in ids:
        dr=S.get(f"{GSI_API}/{pid}",timeout=60)
        if dr.status_code!=200: continue
        item=(dr.json().get("results") or {})
        corners=[item.get("geom_image_left_top_pos"),item.get("geom_image_right_top_pos"),item.get("geom_image_right_bottom_pos"),item.get("geom_image_left_bottom_pos")]
        corners=[c for c in corners if isinstance(c,list) and len(c)==2]
        if len(corners)!=4: continue
        covered=[p["id"] for p in points if point_in_poly(p["lon"],p["lat"],corners)]
        scored.append({
            "photoId":pid,"date":item.get("search_date"),"year":year_of(item),"referenceNumber":item.get("reference_number"),"courseNumber":item.get("course_number"),"photoNumber":item.get("photo_number"),"scale":item.get("scale"),
            "coveredCulvertSamples":sum(1 for x in covered if x.startswith("culvert-")),
            "coversCellG233217":"g233-217" in covered,"coversCellG239220":"g239-220" in covered,"coveredPointIds":covered,"footprintCorners":corners,
        })
    scored.sort(key=lambda x:(-x["coveredCulvertSamples"],-(int(x["coversCellG233217"])+int(x["coversCellG239220"])),abs(x["year"]-1971)))
    era={}
    for key,a,b in [("1945_1950",1945,1950),("1951_1960",1951,1960),("1961_1971",1961,1971)]:
        subset=[x for x in scored if a<=x["year"]<=b]
        era[key]={"photoCount":len(subset),"fullCulvertCoverageCount":sum(1 for x in subset if x["coveredCulvertSamples"]==len(samples)),"best":subset[:5]}
    summary={
        "version":"v10-kakinokizaka-gsi-footprints-v2-20260815","generatedAt":datetime.now(timezone.utc).isoformat(),"frozenCulvertInputSha256":sha(CULVERT),"frozenVertexCount":len(coords),"sampleCount":len(samples),"searchRows":len(rows),"metadataCount":len(scored),"eras":era,"topPhotos":scored[:12],
        "policy":{"historicalCenterlineVerified":False,"formalHistoricalGeometryPromotion":False,"scoringEffect":"none","rankingEffect":"none","automaticExclusionEffect":"none","note":"photo footprint coverage only; visual channel tracing remains separate QA"}
    }
    (OUT/"SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"all-scored-photo-footprints.json").write_text(json.dumps(scored,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"SHA256SUMS.txt").open("w",encoding="utf-8") as f:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p.name!="SHA256SUMS.txt": f.write(f"{sha(p)}  {p.name}\n")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
