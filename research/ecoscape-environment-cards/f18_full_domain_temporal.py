#!/usr/bin/env python3
"""ECOSCAPE F17/F18 full-domain temporal acquisition.

Build one annual wide table for all 120,662 canonical cells from public STAC
imagery. Sentinel-2 is summarized independently by phenological period.
Landsat surface temperature is summarized across the summer window.

The script never mutates B114/B120, never ranks cells, and preserves missing
observations as UNKNOWN (NaN).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
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
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT

S2_STAC = "https://earth-search.aws.element84.com/v1"
S2_COLLECTION = "sentinel-2-l2a"
LANDSAT_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
LANDSAT_COLLECTION = "landsat-c2-l2"
TARGET_CRS = "EPSG:32654"
TARGET_RESOLUTION_M = 100.0

PERIODS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "WINTER_DIAGNOSTIC": ((1, 1), (2, 28)),
    "SPRING": ((3, 15), (5, 31)),
    "EARLY_SUMMER": ((6, 1), (7, 15)),
    "PEAK_SUMMER": ((7, 16), (9, 15)),
    "AUTUMN_RECOVERY": ((9, 16), (11, 30)),
}
INVALID_SCL = {0, 1, 3, 8, 9, 10, 11}
S2_ASSETS = {
    "blue": ("blue", "B02"),
    "red": ("red", "B04"),
    "rededge1": ("rededge1", "B05"),
    "nir": ("nir", "B08"),
    "nir08": ("nir08", "B8A"),
    "swir16": ("swir16", "B11"),
    "scl": ("scl", "SCL"),
}
GDAL_ENV = {
    "AWS_NO_SIGN_REQUEST": "YES",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "100000000",
    "GDAL_HTTP_RETRY_COUNT": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
}


def read_b120_index(zip_path: Path) -> pd.DataFrame:
    import io
    import zipfile

    with zipfile.ZipFile(zip_path) as archive:
        payload = archive.read("ECOSCAPE_PROPERTY_PROFILE_INDEX_120662_B120.csv.gz")
    frame = pd.read_csv(io.BytesIO(payload), compression="gzip", low_memory=False)
    required = {
        "canonicalCellId",
        "latitude",
        "longitude",
        "gridRow",
        "gridColumn",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"B120 is missing columns: {missing}")
    if len(frame) != 120_662:
        raise ValueError(f"Expected 120662 cells, received {len(frame)}")
    if frame["canonicalCellId"].duplicated().any():
        raise ValueError("Duplicate canonicalCellId in B120")
    return frame.sort_values("canonicalCellId").reset_index(drop=True)


def target_grid(cells: pd.DataFrame) -> dict[str, Any]:
    transformer = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    xs, ys = transformer.transform(
        cells["longitude"].to_numpy(),
        cells["latitude"].to_numpy(),
    )
    pad = 250.0
    xmin = math.floor((float(np.min(xs)) - pad) / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M
    xmax = math.ceil((float(np.max(xs)) + pad) / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M
    ymin = math.floor((float(np.min(ys)) - pad) / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M
    ymax = math.ceil((float(np.max(ys)) + pad) / TARGET_RESOLUTION_M) * TARGET_RESOLUTION_M
    width = int(round((xmax - xmin) / TARGET_RESOLUTION_M))
    height = int(round((ymax - ymin) / TARGET_RESOLUTION_M))
    transform = from_origin(xmin, ymax, TARGET_RESOLUTION_M, TARGET_RESOLUTION_M)
    rows = np.floor((ymax - ys) / TARGET_RESOLUTION_M).astype("int32")
    cols = np.floor((xs - xmin) / TARGET_RESOLUTION_M).astype("int32")
    if np.any(rows < 0) or np.any(rows >= height) or np.any(cols < 0) or np.any(cols >= width):
        raise ValueError("Canonical cells fall outside target grid")
    bbox = [
        float(cells["longitude"].min()) - 0.01,
        float(cells["latitude"].min()) - 0.01,
        float(cells["longitude"].max()) + 0.01,
        float(cells["latitude"].max()) + 0.01,
    ]
    return {
        "transformer": transformer,
        "transform": transform,
        "width": width,
        "height": height,
        "rows": rows,
        "cols": cols,
        "bbox": bbox,
        "bounds_utm": [xmin, ymin, xmax, ymax],
    }


def pick_asset(item: Item, candidates: Iterable[str]):
    for name in candidates:
        if name in item.assets:
            return item.assets[name]
    lower = {key.lower(): key for key in item.assets}
    for name in candidates:
        if name.lower() in lower:
            return item.assets[lower[name.lower()]]
    raise KeyError(
        f"None of assets {list(candidates)} in {item.id}; keys={sorted(item.assets)}"
    )


def date_window(year: int, period: str, as_of: dt.date) -> tuple[str, str] | None:
    (m1, d1), (m2, d2) = PERIODS[period]
    start = dt.date(year, m1, d1)
    end = dt.date(year, m2, d2)
    if start > as_of:
        return None
    if year == as_of.year:
        end = min(end, as_of)
    return start.isoformat(), end.isoformat()


def property_value(item: Item, names: Iterable[str], fallback: str) -> str:
    for name in names:
        value = item.properties.get(name)
        if value not in (None, ""):
            return str(value)
    return fallback


def select_s2_items(
    client: Client,
    bbox: list[float],
    start: str,
    end: str,
    per_tile: int,
) -> list[Item]:
    search = client.search(
        collections=[S2_COLLECTION],
        bbox=bbox,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": 85}},
        max_items=500,
    )
    groups: dict[str, list[Item]] = defaultdict(list)
    for item in search.items():
        tile = property_value(
            item,
            ("s2:mgrs_tile", "mgrs:tile", "grid:code"),
            "UNKNOWN_TILE",
        )
        groups[tile].append(item)
    selected: list[Item] = []
    for tile, items in sorted(groups.items()):
        ordered = sorted(
            items,
            key=lambda x: (
                float(x.properties.get("eo:cloud_cover", 1000) or 1000),
                x.datetime.isoformat() if x.datetime else x.id,
                x.id,
            ),
        )
        seen_dates: set[str] = set()
        for item in ordered:
            key = (
                item.datetime.date().isoformat()
                if item.datetime
                else str(item.properties.get("datetime") or item.id)[:10]
            )
            if key in seen_dates:
                continue
            seen_dates.add(key)
            selected.append(item)
            if len(seen_dates) >= per_tile:
                break
    return selected


def select_landsat_items(
    client: Client,
    bbox: list[float],
    year: int,
    as_of: dt.date,
    per_pathrow: int,
) -> list[Item]:
    start = dt.date(year, 6, 1)
    end = dt.date(year, 9, 15)
    if start > as_of:
        return []
    if year == as_of.year:
        end = min(end, as_of)
    search = client.search(
        collections=[LANDSAT_COLLECTION],
        bbox=bbox,
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        query={"eo:cloud_cover": {"lt": 85}},
        max_items=500,
    )
    groups: dict[str, list[Item]] = defaultdict(list)
    for item in search.items():
        if not item.id.startswith(("LC08_", "LC09_")):
            continue
        path = property_value(item, ("landsat:wrs_path",), "X")
        row = property_value(item, ("landsat:wrs_row",), "X")
        groups[f"{path}_{row}"].append(item)
    selected: list[Item] = []
    for _, items in sorted(groups.items()):
        ordered = sorted(
            items,
            key=lambda x: (
                float(x.properties.get("eo:cloud_cover", 1000) or 1000),
                x.datetime.isoformat() if x.datetime else x.id,
                x.id,
            ),
        )
        seen_dates: set[str] = set()
        for item in ordered:
            key = (
                item.datetime.date().isoformat()
                if item.datetime
                else str(item.properties.get("datetime") or item.id)[:10]
            )
            if key in seen_dates:
                continue
            seen_dates.add(key)
            selected.append(item)
            if len(seen_dates) >= per_pathrow:
                break
    return selected


def read_warped(
    href: str,
    grid: dict[str, Any],
    *,
    resampling: Resampling,
    nodata: float = np.nan,
) -> np.ndarray:
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(href) as source:
            with WarpedVRT(
                source,
                crs=TARGET_CRS,
                transform=grid["transform"],
                width=grid["width"],
                height=grid["height"],
                resampling=resampling,
                nodata=nodata,
            ) as vrt:
                return vrt.read(1, out_dtype="float32")


def asset_scale_offset(asset: Any, default_scale: float, default_offset: float) -> tuple[float, float]:
    bands = asset.extra_fields.get("raster:bands", [{}])
    metadata = bands[0] if bands else {}
    return (
        float(metadata.get("scale", default_scale)),
        float(metadata.get("offset", default_offset)),
    )


def safe_ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    output = np.full(num.shape, np.nan, dtype="float32")
    np.divide(num, den, out=output, where=np.abs(den) > 1e-6)
    return output


def sentinel_composite(items: list[Item], grid: dict[str, Any]) -> dict[str, np.ndarray]:
    metric_stacks: dict[str, list[np.ndarray]] = {
        "ndvi": [],
        "evi": [],
        "ndmi": [],
        "ndre": [],
    }
    valid_stacks: list[np.ndarray] = []
    for item in items:
        arrays: dict[str, np.ndarray] = {}
        for key, candidates in S2_ASSETS.items():
            asset = pick_asset(item, candidates)
            arrays[key] = read_warped(
                asset.href,
                grid,
                resampling=Resampling.nearest if key == "scl" else Resampling.bilinear,
            )
        scl = np.rint(arrays["scl"]).astype("int16")
        valid = np.isfinite(arrays["scl"]) & (~np.isin(scl, list(INVALID_SCL)))
        reflectance: dict[str, np.ndarray] = {}
        for key in ("blue", "red", "rededge1", "nir", "nir08", "swir16"):
            asset = pick_asset(item, S2_ASSETS[key])
            scale, offset = asset_scale_offset(asset, 1e-4, 0.0)
            arr = arrays[key] * scale + offset
            reflectance[key] = arr
            valid &= np.isfinite(arr) & (arr > 0) & (arr < 1.5)
        ndvi = safe_ratio(
            reflectance["nir"] - reflectance["red"],
            reflectance["nir"] + reflectance["red"],
        )
        evi = 2.5 * safe_ratio(
            reflectance["nir"] - reflectance["red"],
            reflectance["nir"]
            + 6.0 * reflectance["red"]
            - 7.5 * reflectance["blue"]
            + 1.0,
        )
        ndmi = safe_ratio(
            reflectance["nir"] - reflectance["swir16"],
            reflectance["nir"] + reflectance["swir16"],
        )
        ndre = safe_ratio(
            reflectance["nir08"] - reflectance["rededge1"],
            reflectance["nir08"] + reflectance["rededge1"],
        )
        for name, arr in (("ndvi", ndvi), ("evi", evi), ("ndmi", ndmi), ("ndre", ndre)):
            arr = arr.astype("float32")
            arr[~valid] = np.nan
            arr[(arr < -1.5) | (arr > 1.5)] = np.nan
            metric_stacks[name].append(arr)
        valid_stacks.append(valid.astype("uint8"))
    if not items:
        shape = (grid["height"], grid["width"])
        return {
            "ndvi": np.full(shape, np.nan, dtype="float32"),
            "evi": np.full(shape, np.nan, dtype="float32"),
            "ndmi": np.full(shape, np.nan, dtype="float32"),
            "ndre": np.full(shape, np.nan, dtype="float32"),
            "valid_count": np.zeros(shape, dtype="uint8"),
        }
    return {
        **{
            name: np.nanmedian(np.stack(values, axis=0), axis=0).astype("float32")
            for name, values in metric_stacks.items()
        },
        "valid_count": np.sum(np.stack(valid_stacks, axis=0), axis=0).astype("uint8"),
    }


def landsat_composite(items: list[Item], grid: dict[str, Any]) -> dict[str, np.ndarray]:
    temperature_stack: list[np.ndarray] = []
    valid_stack: list[np.ndarray] = []
    for raw_item in items:
        item = planetary_computer.sign(raw_item)
        thermal_asset = pick_asset(
            item,
            ("lwir11", "lwir", "ST_B10", "st_b10", "ST_B6", "st_b6"),
        )
        qa_asset = pick_asset(item, ("qa_pixel", "QA_PIXEL"))
        thermal = read_warped(
            thermal_asset.href,
            grid,
            resampling=Resampling.bilinear,
        )
        qa = np.rint(
            read_warped(
                qa_asset.href,
                grid,
                resampling=Resampling.nearest,
            )
        ).astype("uint16")
        scale, offset = asset_scale_offset(thermal_asset, 0.00341802, 149.0)
        celsius = thermal * scale + offset - 273.15
        invalid = np.zeros(qa.shape, dtype=bool)
        for bit in (1, 2, 3, 4, 5):
            invalid |= (qa & (1 << bit)) != 0
        valid = (
            (~invalid)
            & np.isfinite(celsius)
            & (thermal > 0)
            & (celsius > -20)
            & (celsius < 90)
        )
        celsius = celsius.astype("float32")
        celsius[~valid] = np.nan
        temperature_stack.append(celsius)
        valid_stack.append(valid.astype("uint8"))
    if not items:
        shape = (grid["height"], grid["width"])
        return {
            "lst": np.full(shape, np.nan, dtype="float32"),
            "valid_count": np.zeros(shape, dtype="uint8"),
        }
    return {
        "lst": np.nanmedian(np.stack(temperature_stack, axis=0), axis=0).astype("float32"),
        "valid_count": np.sum(np.stack(valid_stack, axis=0), axis=0).astype("uint8"),
    }


def sample_grid(array: np.ndarray, grid: dict[str, Any]) -> np.ndarray:
    return array[grid["rows"], grid["cols"]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--b120", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", default="2026-08-24")
    parser.add_argument("--s2-per-tile", type=int, default=3)
    parser.add_argument("--landsat-per-pathrow", type=int, default=5)
    args = parser.parse_args()

    as_of = dt.date.fromisoformat(args.as_of)
    if args.year < 2019 or args.year > as_of.year:
        raise ValueError(f"Unsupported year {args.year}")

    args.output.mkdir(parents=True, exist_ok=True)
    cells = read_b120_index(args.b120)
    grid = target_grid(cells)
    output = cells[
        ["canonicalCellId", "gridRow", "gridColumn", "latitude", "longitude"]
    ].copy()

    s2_client = Client.open(S2_STAC)
    landsat_client = Client.open(LANDSAT_STAC)
    source_manifest: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for period in PERIODS:
        window = date_window(args.year, period, as_of)
        prefix = period.lower()
        if window is None:
            for metric in ("ndvi", "evi", "ndmi", "ndre"):
                output[f"{prefix}_{metric}"] = np.nan
            output[f"{prefix}_valid_scene_count"] = 0
            continue
        start, end = window
        try:
            items = select_s2_items(
                s2_client,
                grid["bbox"],
                start,
                end,
                args.s2_per_tile,
            )
            for item in items:
                source_manifest.append(
                    {
                        "source": "SENTINEL_2_L2A",
                        "year": args.year,
                        "period": period,
                        "itemId": item.id,
                        "datetime": item.datetime.isoformat() if item.datetime else "",
                        "cloudCover": item.properties.get("eo:cloud_cover"),
                        "tile": property_value(
                            item,
                            ("s2:mgrs_tile", "mgrs:tile", "grid:code"),
                            "UNKNOWN_TILE",
                        ),
                    }
                )
            composite = sentinel_composite(items, grid)
            for metric in ("ndvi", "evi", "ndmi", "ndre"):
                output[f"{prefix}_{metric}"] = sample_grid(composite[metric], grid)
            output[f"{prefix}_valid_scene_count"] = sample_grid(
                composite["valid_count"],
                grid,
            )
        except Exception as exc:
            errors.append(
                {
                    "source": "SENTINEL_2_L2A",
                    "year": args.year,
                    "period": period,
                    "error": repr(exc),
                }
            )
            for metric in ("ndvi", "evi", "ndmi", "ndre"):
                output[f"{prefix}_{metric}"] = np.nan
            output[f"{prefix}_valid_scene_count"] = 0

    try:
        landsat_items = select_landsat_items(
            landsat_client,
            grid["bbox"],
            args.year,
            as_of,
            args.landsat_per_pathrow,
        )
        for item in landsat_items:
            source_manifest.append(
                {
                    "source": "LANDSAT_C2_L2",
                    "year": args.year,
                    "period": "SUMMER_HEAT",
                    "itemId": item.id,
                    "datetime": item.datetime.isoformat() if item.datetime else "",
                    "cloudCover": item.properties.get("eo:cloud_cover"),
                    "tile": (
                        f"{item.properties.get('landsat:wrs_path', 'X')}_"
                        f"{item.properties.get('landsat:wrs_row', 'X')}"
                    ),
                }
            )
        thermal = landsat_composite(landsat_items, grid)
        output["summer_lst_c"] = sample_grid(thermal["lst"], grid)
        output["summer_heat_valid_scene_count"] = sample_grid(
            thermal["valid_count"],
            grid,
        )
    except Exception as exc:
        errors.append(
            {
                "source": "LANDSAT_C2_L2",
                "year": args.year,
                "period": "SUMMER_HEAT",
                "error": repr(exc),
            }
        )
        output["summer_lst_c"] = np.nan
        output["summer_heat_valid_scene_count"] = 0

    output["year"] = args.year
    output["asOfDate"] = args.as_of
    output_path = args.output / f"ECOSCAPE_TEMPORAL_{args.year}_120662.parquet"
    output.to_parquet(output_path, index=False, compression="zstd")
    pd.DataFrame(source_manifest).to_csv(
        args.output / f"ECOSCAPE_TEMPORAL_SOURCE_MANIFEST_{args.year}.csv",
        index=False,
    )
    audit = {
        "buildId": f"ecoscape-full-domain-temporal-{args.year}-f17",
        "year": args.year,
        "asOfDate": args.as_of,
        "cells": int(len(output)),
        "duplicateCellIds": int(output["canonicalCellId"].duplicated().sum()),
        "targetGrid": {
            "crs": TARGET_CRS,
            "resolutionM": TARGET_RESOLUTION_M,
            "width": grid["width"],
            "height": grid["height"],
            "boundsUTM": grid["bounds_utm"],
        },
        "sentinelSelectedItems": int(
            sum(row["source"] == "SENTINEL_2_L2A" for row in source_manifest)
        ),
        "landsatSelectedItems": int(
            sum(row["source"] == "LANDSAT_C2_L2" for row in source_manifest)
        ),
        "errors": errors,
        "rankingEffect": "none",
        "scoringEffect": "none",
        "candidateOverride": 0,
        "releaseState": "TEMPORAL_YEAR_PAYLOAD",
    }
    (args.output / f"ECOSCAPE_TEMPORAL_AUDIT_{args.year}.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
