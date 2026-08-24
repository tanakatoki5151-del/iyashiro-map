#!/usr/bin/env python3
"""ECOSCAPE F19 full-domain temporal acquisition.

The canonical 120,662-cell grid is reconstructed from a compact run-length
encoded grid contract stored in the Drive-canonical F17 folder. Each spatial
shard performs one STAC search per period/year and samples all cells in the
shard together. It never issues one catalogue query per cell.

Outputs are temporal evidence only. Canonical F16/F18 facts and rankings are
not mutated.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import planetary_computer
import rasterio
from pyproj import Transformer
from pystac import Item
from pystac_client import Client
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parent
GRID_CONTRACT = Path(os.environ.get("ECOSCAPE_F19_GRID_CONTRACT", ROOT / "ECOSCAPE_F19_GRID_CONTRACT_V1.json"))
OUT = Path(os.environ.get("ECOSCAPE_F19_OUTPUT", ROOT / "output-f19"))
OUT.mkdir(parents=True, exist_ok=True)
SHARD_INDEX = int(os.environ.get("ECOSCAPE_F19_SHARD_INDEX", "0"))
SHARD_COUNT = int(os.environ.get("ECOSCAPE_F19_SHARD_COUNT", "32"))
YEAR_START = int(os.environ.get("ECOSCAPE_F19_YEAR_START", "2019"))
YEAR_END = int(os.environ.get("ECOSCAPE_F19_YEAR_END", "2026"))
FULL_YEARS = [y for y in range(YEAR_START, min(YEAR_END, 2025) + 1)]
YEARS = list(range(YEAR_START, YEAR_END + 1))
MAX_S2_DATES = int(os.environ.get("ECOSCAPE_F19_MAX_S2_DATES", "2"))
MAX_LANDSAT_DATES = int(os.environ.get("ECOSCAPE_F19_MAX_LANDSAT_DATES", "3"))

S2_STAC = "https://earth-search.aws.element84.com/v1"
LANDSAT_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_COLLECTION = "sentinel-2-l2a"
LANDSAT_COLLECTION = "landsat-c2-l2"
PERIODS = {
    "SPRING": ((3, 15), (5, 31)),
    "EARLY_SUMMER": ((6, 1), (7, 15)),
    "PEAK_SUMMER": ((7, 16), (9, 15)),
    "AUTUMN_RECOVERY": ((9, 16), (11, 30)),
    "WINTER_DIAGNOSTIC": ((1, 1), (2, 28)),
}
INVALID_SCL = {0, 1, 3, 8, 9, 10, 11}
S2_ASSETS = {
    "blue": ["blue", "B02"],
    "red": ["red", "B04"],
    "rededge1": ["rededge1", "B05"],
    "nir": ["nir", "B08"],
    "nir08": ["nir08", "B8A"],
    "swir16": ["swir16", "B11"],
    "scl": ["scl", "SCL"],
}


def pick_asset(item: Item, names: Iterable[str]):
    lowered = {k.lower(): k for k in item.assets}
    for name in names:
        if name in item.assets:
            return item.assets[name]
        key = lowered.get(name.lower())
        if key:
            return item.assets[key]
    raise KeyError(f"assets {list(names)} absent in {item.id}")


def item_time(item: Item) -> str:
    if item.datetime:
        return item.datetime.isoformat()
    return str(item.properties.get("datetime") or item.id)


def unique_dates(items: list[Item]) -> list[list[Item]]:
    by_time: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        by_time[item_time(item)].append(item)
    groups = list(by_time.values())
    groups.sort(key=lambda g: (min(float(i.properties.get("eo:cloud_cover", 1000)) for i in g), item_time(g[0])))
    return groups


def reconstruct_cells(contract_path: Path) -> pd.DataFrame:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    rows = []
    for entry in contract["validRows"]:
        r = int(entry["row"])
        for start, end in entry["colRanges"]:
            rows.extend((r, c) for c in range(int(start), int(end) + 1))
    df = pd.DataFrame(rows, columns=["gridRow", "gridCol"])
    df["canonicalCellId"] = "g" + df.gridRow.astype(str) + "-" + df.gridCol.astype(str)
    aff = contract["affine"]
    df["x"] = aff["x"]["constant"] + aff["x"]["gridRow"] * df.gridRow + aff["x"]["gridCol"] * df.gridCol
    df["y"] = aff["y"]["constant"] + aff["y"]["gridRow"] * df.gridRow + aff["y"]["gridCol"] * df.gridCol
    back = Transformer.from_crs(contract["crs"], "EPSG:4326", always_xy=True)
    lon, lat = back.transform(df.x.to_numpy(), df.y.to_numpy())
    df["longitude"] = lon
    df["latitude"] = lat
    bounds = contract["gridBounds"]
    row_edges = np.linspace(bounds["minRow"], bounds["maxRow"] + 1, 9)
    col_edges = np.linspace(bounds["minCol"], bounds["maxCol"] + 1, 5)
    row_bin = np.clip(np.digitize(df.gridRow, row_edges[1:-1]), 0, 7)
    col_bin = np.clip(np.digitize(df.gridCol, col_edges[1:-1]), 0, 3)
    df["shardId"] = (row_bin * 4 + col_bin).astype(int)
    if len(df) != int(contract["canonicalCellCount"]):
        raise RuntimeError(f"grid reconstruction mismatch {len(df)}")
    return df


def date_window(year: int, period: str) -> tuple[str, str]:
    (m1, d1), (m2, d2) = PERIODS[period]
    return f"{year}-{m1:02d}-{d1:02d}", f"{year}-{m2:02d}-{d2:02d}"


def shard_bbox(cells: pd.DataFrame, pad_deg: float = 0.01) -> list[float]:
    return [float(cells.longitude.min() - pad_deg), float(cells.latitude.min() - pad_deg), float(cells.longitude.max() + pad_deg), float(cells.latitude.max() + pad_deg)]


def sample_asset(asset, x: np.ndarray, y: np.ndarray, source_crs: str) -> np.ndarray:
    values = np.full(len(x), np.nan, dtype="float32")
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF", GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", VSI_CACHE="TRUE", VSI_CACHE_SIZE="20000000"):
        with rasterio.open(asset.href) as ds:
            if str(ds.crs) != source_crs:
                transformer = Transformer.from_crs(source_crs, ds.crs, always_xy=True)
                xs, ys = transformer.transform(x, y)
            else:
                xs, ys = x, y
            xs = np.asarray(xs); ys = np.asarray(ys)
            inside = (xs >= ds.bounds.left) & (xs <= ds.bounds.right) & (ys >= ds.bounds.bottom) & (ys <= ds.bounds.top)
            if not inside.any():
                return values
            idx = np.where(inside)[0]
            rows, cols = rasterio.transform.rowcol(ds.transform, xs[idx], ys[idx])
            rows = np.asarray(rows, dtype=int); cols = np.asarray(cols, dtype=int)
            good = (rows >= 0) & (rows < ds.height) & (cols >= 0) & (cols < ds.width)
            if not good.any():
                return values
            idx = idx[good]; rows = rows[good]; cols = cols[good]
            r0, r1 = int(rows.min()), int(rows.max()); c0, c1 = int(cols.min()), int(cols.max())
            arr = ds.read(1, window=Window(c0, r0, c1-c0+1, r1-r0+1), boundless=False)
            sampled = arr[rows-r0, cols-c0].astype("float32")
            if ds.nodata is not None:
                sampled[sampled == ds.nodata] = np.nan
            values[idx] = sampled
    return values


def sample_group(items: list[Item], asset_names: list[str], x: np.ndarray, y: np.ndarray, source_crs: str, sign: bool = False) -> np.ndarray:
    out = np.full(len(x), np.nan, dtype="float32")
    ordered = sorted(items, key=lambda i: (float(i.properties.get("eo:cloud_cover", 1000)), i.id))
    for raw in ordered:
        item = planetary_computer.sign(raw) if sign else raw
        try:
            vals = sample_asset(pick_asset(item, asset_names), x, y, source_crs)
        except Exception:
            continue
        fill = np.isnan(out) & np.isfinite(vals)
        out[fill] = vals[fill]
        if np.isfinite(out).all():
            break
    return out


def point_cloud(cells: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    offsets = np.array([-33.0, 0.0, 33.0])
    dx, dy = np.meshgrid(offsets, offsets)
    return np.repeat(cells.x.to_numpy(), 9) + np.tile(dx.ravel(), len(cells)), np.repeat(cells.y.to_numpy(), 9) + np.tile(dy.ravel(), len(cells))


def cell_median(values: np.ndarray, n_cells: int) -> tuple[np.ndarray, np.ndarray]:
    reshaped = values.reshape(n_cells, 9)
    with np.errstate(all="ignore"):
        med = np.nanmedian(reshaped, axis=1)
    return med.astype("float32"), np.isfinite(reshaped).mean(axis=1).astype("float32")


def safe_ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    out = np.full(num.shape, np.nan, dtype="float32")
    np.divide(num, den, out=out, where=np.abs(den) > 1e-6)
    return out


def sentinel_date_metrics(items: list[Item], cells: pd.DataFrame, x: np.ndarray, y: np.ndarray, source_crs: str) -> pd.DataFrame:
    arrays = {name: sample_group(items, aliases, x, y, source_crs) for name, aliases in S2_ASSETS.items()}
    scl = np.rint(arrays["scl"]).astype("int16")
    valid = ~np.isin(scl, list(INVALID_SCL))
    blue = arrays["blue"] * 1e-4; red = arrays["red"] * 1e-4; re1 = arrays["rededge1"] * 1e-4
    nir = arrays["nir"] * 1e-4; nir08 = arrays["nir08"] * 1e-4; swir = arrays["swir16"] * 1e-4
    valid &= (blue > 0) & (red > 0) & (nir > 0) & (nir08 > 0) & (swir > 0)
    ndvi = safe_ratio(nir-red, nir+red); evi = 2.5 * safe_ratio(nir-red, nir + 6*red - 7.5*blue + 1.0)
    ndmi = safe_ratio(nir-swir, nir+swir); ndre = safe_ratio(nir08-re1, nir08+re1)
    rows = {"canonicalCellId": cells.canonicalCellId.to_numpy()}; valid_fraction = None
    for name, arr in (("ndvi",ndvi),("evi",evi),("ndmi",ndmi),("ndre",ndre)):
        arr[~valid] = np.nan; arr[(arr < -1.5) | (arr > 1.5)] = np.nan
        med, vf = cell_median(arr, len(cells)); rows[name] = med
        valid_fraction = vf if valid_fraction is None else np.minimum(valid_fraction, vf)
    rows["validPointFraction"] = valid_fraction
    return pd.DataFrame(rows)


def landsat_date_metrics(items: list[Item], cells: pd.DataFrame, x: np.ndarray, y: np.ndarray, source_crs: str) -> pd.DataFrame:
    thermal = sample_group(items, ["lwir11","lwir","ST_B10","st_b10","ST_B6","st_b6"], x, y, source_crs, sign=True)
    qa = sample_group(items, ["qa_pixel","QA_PIXEL"], x, y, source_crs, sign=True)
    qa_int = np.nan_to_num(qa, nan=65535).astype("uint16")
    invalid = np.zeros(len(qa_int), dtype=bool)
    for bit in (1,2,3,4,5): invalid |= (qa_int & (1 << bit)) != 0
    celsius = thermal * 0.00341802 + 149.0 - 273.15
    valid = (~invalid) & (thermal > 0) & np.isfinite(celsius) & (celsius > -20) & (celsius < 90)
    celsius[~valid] = np.nan; reshaped = celsius.reshape(len(cells),9)
    with np.errstate(all="ignore"):
        median = np.nanmedian(reshaped,axis=1); p90 = np.nanpercentile(reshaped,90,axis=1)
    return pd.DataFrame({"canonicalCellId":cells.canonicalCellId.to_numpy(),"lstMedianC":median,"lstP90C":p90,"validPointFraction":np.isfinite(reshaped).mean(axis=1)})


def main() -> None:
    contract = json.loads(GRID_CONTRACT.read_text(encoding="utf-8")); cells_all = reconstruct_cells(GRID_CONTRACT)
    if SHARD_COUNT != 32: raise ValueError("F19 contract fixes 32 shards")
    cells = cells_all[cells_all.shardId == SHARD_INDEX].copy().reset_index(drop=True)
    if cells.empty: raise ValueError(f"empty shard {SHARD_INDEX}")
    source_crs = contract["crs"]; x, y = point_cloud(cells); bbox = shard_bbox(cells)
    s2_client = Client.open(S2_STAC); ls_client = Client.open(LANDSAT_STAC)
    sentinel_rows=[]; landsat_rows=[]; errors=[]
    for year in YEARS:
        for period in PERIODS:
            start,end = date_window(year,period)
            try:
                items=list(s2_client.search(collections=[S2_COLLECTION],bbox=bbox,datetime=f"{start}/{end}",query={"eo:cloud_cover":{"lt":70}},max_items=250).items())
                groups=unique_dates(items)[:MAX_S2_DATES]
            except Exception as exc:
                errors.append({"source":"S2_SEARCH","year":year,"period":period,"error":repr(exc)}); groups=[]
            frames=[]
            for group in groups:
                try:
                    frame=sentinel_date_metrics(group,cells,x,y,source_crs); frame["date"]=item_time(group[0])[:10]; frames.append(frame)
                except Exception as exc:
                    errors.append({"source":"S2_DATE","year":year,"period":period,"date":item_time(group[0]),"error":repr(exc)})
            if frames:
                d=pd.concat(frames,ignore_index=True)
                a=d.groupby("canonicalCellId",as_index=False).agg(ndviMedian=("ndvi","median"),eviMedian=("evi","median"),ndmiMedian=("ndmi","median"),ndreMedian=("ndre","median"),validPointFraction=("validPointFraction","median"),distinctAcquisitionDates=("date","nunique")); a["year"]=year; a["period"]=period; sentinel_rows.append(a)
        try:
            raw=list(ls_client.search(collections=[LANDSAT_COLLECTION],bbox=bbox,datetime=f"{year}-06-01/{year}-09-15",query={"eo:cloud_cover":{"lt":70}},max_items=150).items()); raw=[i for i in raw if i.id.startswith(("LC08_","LC09_"))]; groups=unique_dates(raw)[:MAX_LANDSAT_DATES]
        except Exception as exc:
            errors.append({"source":"LANDSAT_SEARCH","year":year,"error":repr(exc)}); groups=[]
        frames=[]
        for group in groups:
            try:
                frame=landsat_date_metrics(group,cells,x,y,source_crs); frame["date"]=item_time(group[0])[:10]; frames.append(frame)
            except Exception as exc:
                errors.append({"source":"LANDSAT_DATE","year":year,"date":item_time(group[0]),"error":repr(exc)})
        if frames:
            d=pd.concat(frames,ignore_index=True); a=d.groupby("canonicalCellId",as_index=False).agg(lstMedianC=("lstMedianC","median"),lstP90C=("lstP90C","median"),validPointFraction=("validPointFraction","median"),distinctAcquisitionDates=("date","nunique")); a["year"]=year; landsat_rows.append(a)
    sentinel=pd.concat(sentinel_rows,ignore_index=True) if sentinel_rows else pd.DataFrame(); landsat=pd.concat(landsat_rows,ignore_index=True) if landsat_rows else pd.DataFrame()
    sentinel.to_csv(OUT/f"F19_SENTINEL_PERIOD_SHARD_{SHARD_INDEX:02d}.csv.gz",index=False,compression="gzip"); landsat.to_csv(OUT/f"F19_LANDSAT_SUMMER_SHARD_{SHARD_INDEX:02d}.csv.gz",index=False,compression="gzip")
    (OUT/f"F19_ERRORS_SHARD_{SHARD_INDEX:02d}.json").write_text(json.dumps(errors,ensure_ascii=False,indent=2)+"\n")
    audit={"buildId":"ecoscape-f19-full-domain-temporal-v1","shardIndex":SHARD_INDEX,"shardCount":SHARD_COUNT,"cells":len(cells),"sentinelRows":len(sentinel),"landsatRows":len(landsat),"errors":len(errors),"rankingEffect":"none","scoringEffect":"none","candidateOverride":0}
    (OUT/f"F19_AUDIT_SHARD_{SHARD_INDEX:02d}.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n"); print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
