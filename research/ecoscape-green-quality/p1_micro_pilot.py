#!/usr/bin/env python3
"""ECOSCAPE P1 micro-pilot.

Queries public STAC catalogues and reads small COG windows around fixed 500 m
pilot areas. It creates multi-year seasonal vegetation statistics and
multi-date summer surface-temperature statistics. It does not rank or rescore
ECOSCAPE cells.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import planetary_computer
import rasterio
from pystac import Item
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parent
AREAS_CSV = Path(
    os.environ.get("ECOSCAPE_P1_AREAS_CSV", ROOT / "P1_MICRO_PILOT_AREAS.csv")
)
SHARD_INDEX = int(os.environ.get("ECOSCAPE_P1_SHARD_INDEX", "0"))
SHARD_COUNT = int(os.environ.get("ECOSCAPE_P1_SHARD_COUNT", "1"))
BUILD_ID = os.environ.get(
    "ECOSCAPE_P1_BUILD_ID", "ecoscape-green-quality-p1-micro-20260819-v2"
)
OUT = Path(os.environ.get("ECOSCAPE_P1_OUTPUT", ROOT / "output"))
OUT.mkdir(parents=True, exist_ok=True)

S2_STAC = "https://earth-search.aws.element84.com/v1"
LANDSAT_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_COLLECTION = "sentinel-2-l2a"
LANDSAT_COLLECTION = "landsat-c2-l2"

SEASONS = {
    "WINTER": ((1, 1), (2, 28)),
    "SPRING": ((3, 1), (5, 31)),
    "SUMMER": ((6, 1), (8, 31)),
    "AUTUMN": ((9, 1), (11, 30)),
}
YEARS = list(range(2019, 2027))

S2_ASSET_CANDIDATES = {
    "blue": ["blue", "B02"],
    "red": ["red", "B04"],
    "rededge1": ["rededge1", "B05"],
    "nir": ["nir", "B08"],
    "nir08": ["nir08", "B8A"],
    "swir16": ["swir16", "B11"],
    "scl": ["scl", "SCL"],
}
INVALID_SCL = {0, 1, 3, 8, 9, 10, 11}


@dataclass(frozen=True)
class PilotArea:
    pilot_id: str
    category: str
    cell_id: str
    lat: float
    lon: float
    label: str


def read_areas() -> list[PilotArea]:
    df = pd.read_csv(AREAS_CSV)
    required = {
        "pilotId",
        "pilotCategory",
        "canonicalCellId",
        "latitude",
        "longitude",
        "officialAreaLabel",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing pilot columns: {sorted(missing)}")
    areas = [
        PilotArea(
            pilot_id=str(r.pilotId),
            category=str(r.pilotCategory),
            cell_id=str(r.canonicalCellId),
            lat=float(r.latitude),
            lon=float(r.longitude),
            label=str(r.officialAreaLabel),
        )
        for r in df.sort_values("pilotId").itertuples(index=False)
    ]
    if SHARD_COUNT < 1 or not (0 <= SHARD_INDEX < SHARD_COUNT):
        raise ValueError(f"Invalid shard index/count: {SHARD_INDEX}/{SHARD_COUNT}")
    if SHARD_COUNT > 1:
        areas = [
            area
            for ordinal, area in enumerate(areas)
            if ordinal % SHARD_COUNT == SHARD_INDEX
        ]
    if not areas:
        raise ValueError(
            f"No pilot areas selected from {AREAS_CSV} "
            f"for shard {SHARD_INDEX}/{SHARD_COUNT}"
        )
    return areas


def pick_asset(item: Item, names: Iterable[str]) -> Any:
    for name in names:
        if name in item.assets:
            return item.assets[name]
    lowered = {key.lower(): key for key in item.assets}
    for name in names:
        if name.lower() in lowered:
            return item.assets[lowered[name.lower()]]
    raise KeyError(
        f"None of assets {list(names)} in {item.id}; keys={sorted(item.assets)}"
    )


def dedupe_items_by_datetime(items: Iterable[Item]) -> tuple[list[Item], int]:
    """Keep one item per acquisition time, preferring lower cloud cover.

    Sentinel acquisitions can appear once per overlapping MGRS tile. Treating
    those tiles as separate dates would overweight one observation.
    """
    original = list(items)
    best: dict[str, Item] = {}
    for item in original:
        dt = (
            item.datetime.isoformat()
            if item.datetime
            else str(item.properties.get("datetime") or item.id)
        )
        current = best.get(dt)
        if current is None or item.properties.get(
            "eo:cloud_cover", 1000
        ) < current.properties.get("eo:cloud_cover", 1000):
            best[dt] = item
    unique = sorted(
        best.values(),
        key=lambda x: (x.properties.get("eo:cloud_cover", 1000), x.id),
    )
    return unique, max(0, len(original) - len(unique))


def read_point_window(
    asset: Any,
    lon: float,
    lat: float,
    *,
    size_m: float = 500.0,
    out_px: int = 25,
    resampling: Resampling = Resampling.bilinear,
) -> np.ndarray:
    with rasterio.Env(
        AWS_NO_SIGN_REQUEST="YES",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
        GDAL_HTTP_MULTIRANGE="YES",
        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
        VSI_CACHE="TRUE",
        VSI_CACHE_SIZE="5000000",
    ):
        with rasterio.open(asset.href) as ds:
            xs, ys = transform("EPSG:4326", ds.crs, [lon], [lat])
            half = size_m / 2.0
            window = from_bounds(
                xs[0] - half,
                ys[0] - half,
                xs[0] + half,
                ys[0] + half,
                ds.transform,
            )
            arr = ds.read(
                1,
                window=window,
                out_shape=(out_px, out_px),
                boundless=True,
                fill_value=ds.nodata if ds.nodata is not None else 0,
                resampling=resampling,
            )
            return arr.astype("float32")


def safe_ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    out = np.full(num.shape, np.nan, dtype="float32")
    np.divide(num, den, out=out, where=np.abs(den) > 1e-6)
    return out


def percentile(values: np.ndarray, q: float) -> float | None:
    vals = values[np.isfinite(values)]
    return float(np.nanpercentile(vals, q)) if vals.size else None


def median(values: np.ndarray) -> float | None:
    vals = values[np.isfinite(values)]
    return float(np.nanmedian(vals)) if vals.size else None


def s2_scene_metrics(item: Item, area: PilotArea) -> dict[str, Any]:
    arrays: dict[str, np.ndarray] = {}
    for key, candidates in S2_ASSET_CANDIDATES.items():
        arrays[key] = read_point_window(
            pick_asset(item, candidates),
            area.lon,
            area.lat,
            resampling=(
                Resampling.nearest if key == "scl" else Resampling.bilinear
            ),
        )
    scl = np.rint(arrays["scl"]).astype("int16")
    valid = ~np.isin(scl, list(INVALID_SCL))
    blue = arrays["blue"] * 1e-4
    red = arrays["red"] * 1e-4
    re1 = arrays["rededge1"] * 1e-4
    nir = arrays["nir"] * 1e-4
    nir08 = arrays["nir08"] * 1e-4
    swir = arrays["swir16"] * 1e-4
    valid &= (
        (blue > 0)
        & (red > 0)
        & (nir > 0)
        & (nir08 > 0)
        & (swir > 0)
    )
    ndvi = safe_ratio(nir - red, nir + red)
    evi = 2.5 * safe_ratio(nir - red, nir + 6 * red - 7.5 * blue + 1.0)
    ndmi = safe_ratio(nir - swir, nir + swir)
    ndre = safe_ratio(nir08 - re1, nir08 + re1)
    for arr in (ndvi, evi, ndmi, ndre):
        arr[~valid] = np.nan
        arr[(arr < -1.5) | (arr > 1.5)] = np.nan
    dt = (
        item.datetime.isoformat()
        if item.datetime
        else item.properties.get("datetime")
    )
    return {
        "pilotId": area.pilot_id,
        "pilotCategory": area.category,
        "canonicalCellId": area.cell_id,
        "officialAreaLabel": area.label,
        "itemId": item.id,
        "datetime": dt,
        "sceneCloudCover": item.properties.get("eo:cloud_cover"),
        "validFraction500m": float(valid.mean()),
        "ndviMedian": median(ndvi),
        "ndviP10": percentile(ndvi, 10),
        "ndviP90": percentile(ndvi, 90),
        "eviMedian": median(evi),
        "ndmiMedian": median(ndmi),
        "ndreMedian": median(ndre),
    }


def search_s2(
    client: Client, area: PilotArea, start: str, end: str
) -> list[Item]:
    delta = 0.006
    search = client.search(
        collections=[S2_COLLECTION],
        bbox=[
            area.lon - delta,
            area.lat - delta,
            area.lon + delta,
            area.lat + delta,
        ],
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": 60}},
        max_items=20,
    )
    return sorted(
        search.items(),
        key=lambda x: (x.properties.get("eo:cloud_cover", 1000), x.id),
    )


def landsat_scene_metrics(raw_item: Item, area: PilotArea) -> dict[str, Any]:
    item = planetary_computer.sign(raw_item)
    thermal_asset = pick_asset(item, ["lwir11", "ST_B10", "st_b10"])
    qa_asset = pick_asset(item, ["qa_pixel", "QA_PIXEL"])
    thermal = read_point_window(thermal_asset, area.lon, area.lat)
    qa = np.rint(
        read_point_window(
            qa_asset,
            area.lon,
            area.lat,
            resampling=Resampling.nearest,
        )
    ).astype("uint16")
    raster_meta = thermal_asset.extra_fields.get("raster:bands", [{}])[0]
    scale = float(raster_meta.get("scale", 0.00341802))
    offset = float(raster_meta.get("offset", 149.0))
    celsius = thermal * scale + offset - 273.15
    invalid = np.zeros(qa.shape, dtype=bool)
    for bit in (1, 2, 3, 4, 5):
        invalid |= (qa & (1 << bit)) != 0
    valid = (
        (~invalid)
        & (thermal > 0)
        & np.isfinite(celsius)
        & (celsius > -20)
        & (celsius < 90)
    )
    celsius[~valid] = np.nan
    dt = (
        item.datetime.isoformat()
        if item.datetime
        else item.properties.get("datetime")
    )
    return {
        "pilotId": area.pilot_id,
        "pilotCategory": area.category,
        "canonicalCellId": area.cell_id,
        "officialAreaLabel": area.label,
        "itemId": item.id,
        "datetime": dt,
        "sceneCloudCover": item.properties.get("eo:cloud_cover"),
        "validFraction500m": float(valid.mean()),
        "lstMedianC": median(celsius),
        "lstP10C": percentile(celsius, 10),
        "lstP90C": percentile(celsius, 90),
    }


def search_landsat(client: Client, area: PilotArea, year: int) -> list[Item]:
    delta = 0.006
    search = client.search(
        collections=[LANDSAT_COLLECTION],
        bbox=[
            area.lon - delta,
            area.lat - delta,
            area.lon + delta,
            area.lat + delta,
        ],
        datetime=f"{year}-06-01/{year}-09-15",
        query={"eo:cloud_cover": {"lt": 70}},
        max_items=20,
    )
    items = [
        item
        for item in search.items()
        if item.id.startswith(("LC08_", "LC09_"))
    ]
    return sorted(
        items,
        key=lambda x: (x.properties.get("eo:cloud_cover", 1000), x.id),
    )


def date_window(year: int, season: str) -> tuple[str, str]:
    (m1, d1), (m2, d2) = SEASONS[season]
    return f"{year}-{m1:02d}-{d1:02d}", f"{year}-{m2:02d}-{d2:02d}"


def seasonal_summary(scene_df: pd.DataFrame) -> pd.DataFrame:
    if scene_df.empty:
        return pd.DataFrame()
    metrics = [
        "ndviMedian",
        "eviMedian",
        "ndmiMedian",
        "ndreMedian",
        "validFraction500m",
    ]
    keys = [
        "pilotId",
        "pilotCategory",
        "canonicalCellId",
        "officialAreaLabel",
        "year",
        "season",
    ]
    grouped = scene_df.groupby(keys, dropna=False)
    out = grouped[metrics].median().reset_index()
    out = out.merge(grouped.size().rename("acceptedSceneCount").reset_index())
    out = out.merge(
        grouped["datetime"]
        .agg(lambda x: "|".join(sorted(str(v) for v in x)))
        .rename("sceneDates")
        .reset_index()
    )
    return out


def thermal_summary(scene_df: pd.DataFrame) -> pd.DataFrame:
    if scene_df.empty:
        return pd.DataFrame()
    metrics = [
        "lstMedianC",
        "lstP10C",
        "lstP90C",
        "validFraction500m",
    ]
    keys = [
        "pilotId",
        "pilotCategory",
        "canonicalCellId",
        "officialAreaLabel",
        "year",
    ]
    grouped = scene_df.groupby(keys, dropna=False)
    out = grouped[metrics].median().reset_index()
    out = out.merge(grouped.size().rename("acceptedSceneCount").reset_index())
    out = out.merge(
        grouped["datetime"]
        .agg(lambda x: "|".join(sorted(str(v) for v in x)))
        .rename("sceneDates")
        .reset_index()
    )
    return out


def main() -> None:
    areas = read_areas()
    s2_client = Client.open(S2_STAC)
    landsat_client = Client.open(LANDSAT_STAC)
    s2_rows: list[dict[str, Any]] = []
    ls_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    sentinel_duplicate_candidates_skipped = 0

    for area in areas:
        for year in YEARS:
            for season in SEASONS:
                start, end = date_window(year, season)
                try:
                    items = search_s2(s2_client, area, start, end)
                    items, skipped = dedupe_items_by_datetime(items)
                    sentinel_duplicate_candidates_skipped += skipped
                except Exception as exc:
                    errors.append(
                        {
                            "source": "S2_SEARCH",
                            "pilotId": area.pilot_id,
                            "year": year,
                            "season": season,
                            "error": repr(exc),
                        }
                    )
                    continue
                accepted = 0
                for item in items[:6]:
                    try:
                        row = s2_scene_metrics(item, area)
                        if row["validFraction500m"] >= 0.45:
                            row.update({"year": year, "season": season})
                            s2_rows.append(row)
                            accepted += 1
                        if accepted >= 3:
                            break
                    except Exception as exc:
                        errors.append(
                            {
                                "source": "S2_SCENE",
                                "pilotId": area.pilot_id,
                                "year": year,
                                "season": season,
                                "itemId": item.id,
                                "error": repr(exc),
                            }
                        )
            try:
                items = search_landsat(landsat_client, area, year)
            except Exception as exc:
                errors.append(
                    {
                        "source": "LANDSAT_SEARCH",
                        "pilotId": area.pilot_id,
                        "year": year,
                        "error": repr(exc),
                    }
                )
                continue
            accepted = 0
            for item in items[:10]:
                try:
                    row = landsat_scene_metrics(item, area)
                    if (
                        row["validFraction500m"] >= 0.35
                        and row["lstMedianC"] is not None
                    ):
                        row.update({"year": year})
                        ls_rows.append(row)
                        accepted += 1
                    if accepted >= 4:
                        break
                except Exception as exc:
                    errors.append(
                        {
                            "source": "LANDSAT_SCENE",
                            "pilotId": area.pilot_id,
                            "year": year,
                            "itemId": item.id,
                            "error": repr(exc),
                        }
                    )

    s2_df = pd.DataFrame(s2_rows)
    ls_df = pd.DataFrame(ls_rows)
    s2_df.to_csv(OUT / "P1_SENTINEL_SCENES.csv", index=False)
    ls_df.to_csv(OUT / "P1_LANDSAT_SUMMER_SCENES.csv", index=False)
    seasonal_summary(s2_df).to_csv(
        OUT / "P1_SENTINEL_SEASONAL_COMPOSITES.csv", index=False
    )
    thermal_summary(ls_df).to_csv(
        OUT / "P1_LANDSAT_MULTI_SUMMER_COMPOSITES.csv", index=False
    )
    (OUT / "P1_ERRORS.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    coverage = []
    for area in areas:
        s2a = (
            s2_df[s2_df.pilotId == area.pilot_id]
            if not s2_df.empty
            else pd.DataFrame()
        )
        lsa = (
            ls_df[ls_df.pilotId == area.pilot_id]
            if not ls_df.empty
            else pd.DataFrame()
        )
        coverage.append(
            {
                "pilotId": area.pilot_id,
                "pilotCategory": area.category,
                "canonicalCellId": area.cell_id,
                "officialAreaLabel": area.label,
                "sentinelAcceptedScenes": len(s2a),
                "sentinelCoveredYearSeasons": (
                    int(s2a[["year", "season"]].drop_duplicates().shape[0])
                    if not s2a.empty
                    else 0
                ),
                "landsatAcceptedSummerScenes": len(lsa),
                "landsatCoveredYears": (
                    int(lsa[["year"]].drop_duplicates().shape[0])
                    if not lsa.empty
                    else 0
                ),
            }
        )
    pd.DataFrame(coverage).to_csv(
        OUT / "P1_COVERAGE_SUMMARY.csv", index=False
    )
    audit = {
        "buildId": BUILD_ID,
        "pilotAreas": len(areas),
        "areasCsv": str(AREAS_CSV),
        "shardIndex": SHARD_INDEX,
        "shardCount": SHARD_COUNT,
        "sentinelSceneRows": len(s2_df),
        "landsatSceneRows": len(ls_df),
        "errorCount": len(errors),
        "sentinelDuplicateCandidatesSkipped": (
            sentinel_duplicate_candidates_skipped
        ),
        "landsatPlatformFilter": "Landsat 8/9 only",
        "sentinelYearSeasonTargetPerArea": len(YEARS) * len(SEASONS),
        "landsatYearTargetPerArea": len(YEARS),
        "rankingEffect": "none",
        "scoringEffect": "none",
        "note": (
            "Feasibility pilot only; labels remain proxies until QA gates pass."
        ),
    }
    (OUT / "P1_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
