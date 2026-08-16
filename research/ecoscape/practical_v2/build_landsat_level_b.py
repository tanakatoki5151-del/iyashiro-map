#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, time
from collections import defaultdict
from pathlib import Path
from typing import Any
import numpy as np
import planetary_computer as pc
import pystac
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
import requests
from common import canonical_bytes, deterministic_csv_gz, load_grid, sha256_bytes, sha256_file, write_sha256s

SOURCE_ID = "SRC-ECO-LANDSAT-001"
COLLECTION = "landsat-c2-l2"
ITEM_ID = "LC09_L2SP_107035_20250724_02_T1"
ITEM_URL = f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{COLLECTION}/items/{ITEM_ID}"
BUILD_ID = "ecos-practical-v2-20260817-m1-landsat-level-b-120662"
METHOD = "ECOSCAPE_LANDSAT_SINGLE_CLEAR_SUMMER_SCENE_PIXEL_CENTER_v2"


def pick_asset(item: pystac.Item, names: list[str], contains: list[str] | None = None) -> str:
    for name in names:
        if name in item.assets:
            return name
    for key in item.assets:
        low = key.lower()
        if contains and any(token in low for token in contains):
            return key
    raise KeyError(f"Could not find asset among {names}; available={sorted(item.assets)}")


def band_scale_offset(asset: pystac.Asset, default_scale: float, default_offset: float) -> tuple[float, float]:
    bands = asset.extra_fields.get("raster:bands") or []
    band = bands[0] if bands else {}
    return float(band.get("scale", default_scale)), float(band.get("offset", default_offset))


def read_domain(asset_href: str, bbox_wgs84: tuple[float,float,float,float]) -> tuple[np.ndarray, Any, Any, dict[str, Any]]:
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF,.tif", GDAL_HTTP_MAX_RETRY="8", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(asset_href) as ds:
            project = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
            corners = [project.transform(bbox_wgs84[0], bbox_wgs84[1]), project.transform(bbox_wgs84[0], bbox_wgs84[3]), project.transform(bbox_wgs84[2], bbox_wgs84[1]), project.transform(bbox_wgs84[2], bbox_wgs84[3])]
            xs=[p[0] for p in corners]; ys=[p[1] for p in corners]
            win = from_bounds(min(xs), min(ys), max(xs), max(ys), ds.transform).round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0,0,ds.width,ds.height))
            arr = ds.read(1, window=win)
            transform = ds.window_transform(win)
            meta = {"crs": str(ds.crs), "nodata": ds.nodata, "dtype": str(arr.dtype), "shape": list(arr.shape), "window": [float(win.col_off),float(win.row_off),float(win.width),float(win.height)], "sourceWidth":ds.width, "sourceHeight":ds.height}
            return arr, transform, ds.crs, meta


def stats(values: np.ndarray) -> dict[str, float | None]:
    if values.size == 0:
        return {"mean":None,"median":None,"p10":None,"p90":None,"min":None,"max":None}
    return {"mean":float(np.mean(values)),"median":float(np.median(values)),"p10":float(np.percentile(values,10)),"p90":float(np.percentile(values,90)),"min":float(np.min(values)),"max":float(np.max(values))}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--grid",type=Path,required=True); ap.add_argument("--output-dir",type=Path,required=True)
    args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    contract,cells=load_grid(args.grid)
    bbox=(min(c["west"] for c in cells),min(c["south"] for c in cells),max(c["east"] for c in cells),max(c["north"] for c in cells))
    response=requests.get(ITEM_URL,timeout=(30,120)); response.raise_for_status(); payload=response.json(); item=pc.sign(pystac.Item.from_dict(payload))
    temp_key=pick_asset(item,["lwir11","st_b10"],["lwir","temperature"])
    qa_key=pick_asset(item,["qa_pixel"],["qa_pixel"])
    stqa_key=pick_asset(item,["st_qa"],["st_qa"])
    temp_asset=item.assets[temp_key]; qa_asset=item.assets[qa_key]; stqa_asset=item.assets[stqa_key]
    temp_raw,tform,crs,temp_meta=read_domain(temp_asset.href,bbox)
    qa_raw,qa_tform,qa_crs,qa_meta=read_domain(qa_asset.href,bbox)
    stqa_raw,stqa_tform,stqa_crs,stqa_meta=read_domain(stqa_asset.href,bbox)
    if temp_raw.shape!=qa_raw.shape or temp_raw.shape!=stqa_raw.shape or tform!=qa_tform or tform!=stqa_tform or crs!=qa_crs or crs!=stqa_crs:
        raise RuntimeError("Landsat assets are not aligned")
    temp_scale,temp_offset=band_scale_offset(temp_asset,0.00341802,149.0)
    stqa_scale,stqa_offset=band_scale_offset(stqa_asset,0.01,0.0)
    project=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    a,b,c,d,e,f=tform.a,tform.b,tform.c,tform.d,tform.e,tform.f
    rows=[]; counts=defaultdict(int)
    height,width=temp_raw.shape
    for n,cell in enumerate(cells,start=1):
        corners=[project.transform(cell["west"],cell["south"]),project.transform(cell["west"],cell["north"]),project.transform(cell["east"],cell["south"]),project.transform(cell["east"],cell["north"])]
        xs=[p[0] for p in corners]; ys=[p[1] for p in corners]; xmin,xmax=min(xs),max(xs); ymin,ymax=min(ys),max(ys)
        win=from_bounds(xmin,ymin,xmax,ymax,tform).round_offsets().round_lengths()
        r0=max(0,int(math.floor(win.row_off))); c0=max(0,int(math.floor(win.col_off))); r1=min(height,int(math.ceil(win.row_off+win.height))); c1=min(width,int(math.ceil(win.col_off+win.width)))
        if r1<=r0 or c1<=c0:
            status="OUTSIDE_SCENE"; pixel_count=0; valid=np.zeros(0,dtype=bool); land=np.zeros(0,dtype=bool); water=np.zeros(0,dtype=bool); temp=np.zeros(0); uncertainty=np.zeros(0)
        else:
            rr,cc=np.mgrid[r0:r1,c0:c1]
            x=c+(cc+0.5)*a+(rr+0.5)*b; y=f+(cc+0.5)*d+(rr+0.5)*e
            inside=(x>=xmin)&(x<=xmax)&(y>=ymin)&(y<=ymax)
            t=temp_raw[r0:r1,c0:c1][inside]; q=qa_raw[r0:r1,c0:c1][inside].astype(np.uint32); sq=stqa_raw[r0:r1,c0:c1][inside]
            pixel_count=int(t.size)
            fill=(q&(1<<0))!=0; dilated=(q&(1<<1))!=0; cirrus=(q&(1<<2))!=0; cloud=(q&(1<<3))!=0; shadow=(q&(1<<4))!=0; snow=(q&(1<<5))!=0; water=(q&(1<<7))!=0
            valid=(t>0)&~(fill|dilated|cirrus|cloud|shadow|snow); land=valid&~water
            temp=t.astype(np.float64)*temp_scale+temp_offset-273.15; uncertainty=sq.astype(np.float64)*stqa_scale+stqa_offset
            status="PASS" if np.any(land) else "NO_VALID_CLEAR_LAND_PIXEL"
        counts[status]+=1
        all_stats=stats(temp[valid]); land_stats=stats(temp[land])
        valid_count=int(np.count_nonzero(valid)); land_count=int(np.count_nonzero(land)); water_count=int(np.count_nonzero(water)) if pixel_count else 0
        uncertainty_mean=float(np.mean(uncertainty[valid])) if valid_count else None
        valid_frac=valid_count/pixel_count if pixel_count else 0.0; land_frac=land_count/pixel_count if pixel_count else 0.0
        confidence="HIGH" if status=="PASS" and land_frac>=0.6 and (uncertainty_mean is None or uncertainty_mean<=5) else ("MEDIUM" if status=="PASS" else "LOW")
        row={"ordinal":cell["ordinal"],"cellId":cell["cellId"],"row":cell["row"],"column":cell["column"],"centerLat":f"{cell['centerLat']:.12f}","centerLon":f"{cell['centerLon']:.12f}","status":status,"nativePixelCount":pixel_count,"qualityValidCount":valid_count,"qualityValidFraction":f"{valid_frac:.8f}","landValidCount":land_count,"landValidFraction":f"{land_frac:.8f}","waterFraction":f"{(water_count/pixel_count if pixel_count else 0):.8f}","lstAllClearMeanC":"" if all_stats["mean"] is None else f"{all_stats['mean']:.6f}","lstAllClearMedianC":"" if all_stats["median"] is None else f"{all_stats['median']:.6f}","lstLandMeanC":"" if land_stats["mean"] is None else f"{land_stats['mean']:.6f}","lstLandMedianC":"" if land_stats["median"] is None else f"{land_stats['median']:.6f}","lstLandP10C":"" if land_stats["p10"] is None else f"{land_stats['p10']:.6f}","lstLandP90C":"" if land_stats["p90"] is None else f"{land_stats['p90']:.6f}","stUncertaintyMeanK":"" if uncertainty_mean is None else f"{uncertainty_mean:.6f}","confidenceLevel":confidence,"itemId":ITEM_ID,"acquisitionDate":str(item.datetime.date()) if item.datetime else "2025-07-24","sourceId":SOURCE_ID,"methodVersion":METHOD,"provenanceUrl":ITEM_URL,"missingReason":"" if status=="PASS" else status,"buildId":BUILD_ID,"scoringEffect":"none"}
        rows.append(row)
        if n%10000==0: print(f"Landsat cells {n}/{len(cells)}",flush=True)
    facts=args.output_dir/"ECOSCAPE_LANDSAT_LEVEL_B_120662.csv.gz"; deterministic_csv_gz(facts,list(rows[0]),rows)
    source_manifest={"sourceId":SOURCE_ID,"collection":COLLECTION,"itemId":ITEM_ID,"itemUrl":ITEM_URL,"acquisitionDate":str(item.datetime.date()) if item.datetime else "2025-07-24","assetKeys":{"temperature":temp_key,"qaPixel":qa_key,"stQa":stqa_key},"temperatureScale":temp_scale,"temperatureOffset":temp_offset,"stQaScale":stqa_scale,"stQaOffset":stqa_offset,"domainBboxWgs84":bbox,"temperatureRaster":temp_meta,"qaPixelRaster":qa_meta,"stQaRaster":stqa_meta,"stacItemSha256":sha256_bytes(canonical_bytes(payload)),"retrievedAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    audit={"buildId":BUILD_ID,"canonicalCells":len(cells),"rows":len(rows),"uniqueCells":len({r['cellId'] for r in rows}),"duplicateCount":len(rows)-len({r['cellId'] for r in rows}),"silentMissing":len(cells)-len(rows),"statusCounts":dict(sorted(counts.items())),"outsideScene":counts.get("OUTSIDE_SCENE",0),"provenanceCoverage":1.0,"gridContractId":contract["contractId"],"gridMaskSha256":contract["maskSha256"],"factsGzipSha256":sha256_file(facts),"sourceManifestSha256":sha256_bytes(canonical_bytes(source_manifest)),"singleScenePracticalLevelB":True,"scoringEffect":"none","qaPass":len(rows)==len(cells) and len({r['cellId'] for r in rows})==len(cells) and counts.get("OUTSIDE_SCENE",0)==0}
    (args.output_dir/"LANDSAT_SOURCE_MANIFEST.json").write_text(json.dumps(source_manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (args.output_dir/"LANDSAT_FULL_AUDIT.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    (args.output_dir/"README.md").write_text("# ECOSCAPE Landsat practical Level B\n\nOne clear summer Landsat 9 surface-temperature scene is aggregated to every canonical 100 m cell. Land and water are separated; cloud/shadow/snow are masked. This is an area-comparison layer, not air temperature and not a final score.\n",encoding="utf-8")
    write_sha256s(args.output_dir,["ECOSCAPE_LANDSAT_LEVEL_B_120662.csv.gz","LANDSAT_SOURCE_MANIFEST.json","LANDSAT_FULL_AUDIT.json","README.md"])
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    if not audit["qaPass"]: raise SystemExit("Landsat QA failed")
    return 0
if __name__=="__main__": raise SystemExit(main())
