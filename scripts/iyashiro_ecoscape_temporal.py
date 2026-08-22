#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import planetary_computer
import rasterio
import requests
from pystac_client import Client
from rasterio.windows import Window

OUT = Path("output/ecoscape_temporal")
OUT.mkdir(parents=True, exist_ok=True)

DRIVE_FILES = {
    "residential": "1cVbpKqaMedUiARHT-vN9IvPGIXWcNvzd",
    "pure": "1Yd3YvdiQNabkGG_1UmsjaCvYLc9zybYs",
    "tokyo23": "1bi1f-0aEin3utMYnNkR8K6X5PB8axCJ2",
}

SENTINEL_WINDOWS = {
    "2024_leaf_off": "2024-02-01/2024-04-15",
    "2024_leaf_on": "2024-06-01/2024-09-30",
    "2025_leaf_off": "2025-02-01/2025-04-15",
    "2025_leaf_on": "2025-06-01/2025-09-30",
}
LANDSAT_WINDOWS = {
    "2024_hot": "2024-07-01/2024-09-15",
    "2025_hot": "2025-07-01/2025-09-15",
}


def download_drive(file_id: str, dest: Path) -> None:
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    r = requests.get(url, timeout=(30, 180))
    r.raise_for_status()
    dest.write_bytes(r.content)


def cohort() -> pd.DataFrame:
    frames = []
    for name, file_id in DRIVE_FILES.items():
        path = OUT / f"f16_{name}.csv"
        download_drive(file_id, path)
        d = pd.read_csv(path).head(20).copy()
        d["cohortSource"] = name
        frames.append(d[["zoneId", "displayArea", "latitude", "longitude", "cohortSource"]])
    c = pd.concat(frames, ignore_index=True)
    sources = c.groupby("zoneId")["cohortSource"].agg(lambda x: "|".join(sorted(set(x))))
    c = c.drop_duplicates("zoneId").set_index("zoneId")
    c["cohortSources"] = sources
    c = c.reset_index().sort_values("zoneId")
    c.to_csv(OUT / "ECOSCAPE_F17_TOP_UNION_COHORT.csv", index=False, encoding="utf-8-sig")
    return c


def bbox(lon: float, lat: float, delta: float = 0.003) -> list[float]:
    return [lon - delta, lat - delta, lon + delta, lat + delta]


def choose_item(client: Client, collection: str, lon: float, lat: float, dt: str):
    search = client.search(
        collections=[collection],
        bbox=bbox(lon, lat),
        datetime=dt,
        query={"eo:cloud_cover": {"lt": 35}},
        max_items=15,
    )
    items = list(search.items())
    if not items:
        return None
    items.sort(key=lambda item: float(item.properties.get("eo:cloud_cover", 999)))
    return items[0]


def sample_asset(asset_href: str, lon: float, lat: float, half_pixels: int = 5) -> tuple[np.ndarray, dict[str, Any]]:
    with rasterio.open(asset_href) as src:
        x, y = rasterio.warp.transform("EPSG:4326", src.crs, [lon], [lat])
        row, col = src.index(x[0], y[0])
        window = Window(col - half_pixels, row - half_pixels, half_pixels * 2 + 1, half_pixels * 2 + 1)
        arr = src.read(1, window=window, boundless=True, masked=True).astype("float64")
        return np.asarray(arr.filled(np.nan)), {
            "crs": str(src.crs),
            "resolutionX": abs(src.transform.a),
            "resolutionY": abs(src.transform.e),
            "nodata": src.nodata,
        }


def sentinel_observation(client: Client, zone: pd.Series, label: str, dt: str) -> dict[str, Any]:
    lon = float(zone.longitude)
    lat = float(zone.latitude)
    item = choose_item(client, "sentinel-2-l2a", lon, lat, dt)
    base = {
        "zoneId": zone.zoneId,
        "displayArea": zone.displayArea,
        "sensor": "Sentinel-2 L2A",
        "period": label,
        "queryWindow": dt,
    }
    if item is None:
        return {**base, "status": "NO_ITEM"}
    try:
        signed = planetary_computer.sign(item)
        red_key = "B04" if "B04" in signed.assets else "red"
        nir_key = "B08" if "B08" in signed.assets else "nir"
        red, meta = sample_asset(signed.assets[red_key].href, lon, lat)
        nir, _ = sample_asset(signed.assets[nir_key].href, lon, lat)
        valid = np.isfinite(red) & np.isfinite(nir) & ((nir + red) != 0)
        ndvi = np.full(red.shape, np.nan)
        ndvi[valid] = (nir[valid] - red[valid]) / (nir[valid] + red[valid])
        return {
            **base,
            "status": "SUCCESS" if valid.any() else "NO_VALID_PIXEL",
            "itemId": item.id,
            "datetime": item.datetime.isoformat() if item.datetime else None,
            "cloudCover": item.properties.get("eo:cloud_cover"),
            "validPixelCount": int(valid.sum()),
            "ndviMedian": float(np.nanmedian(ndvi)) if valid.any() else None,
            "ndviMean": float(np.nanmean(ndvi)) if valid.any() else None,
            **meta,
        }
    except Exception as e:  # noqa: BLE001
        return {**base, "status": "FAILED", "itemId": item.id, "error": f"{type(e).__name__}: {e}"}


def landsat_observation(client: Client, zone: pd.Series, label: str, dt: str) -> dict[str, Any]:
    lon = float(zone.longitude)
    lat = float(zone.latitude)
    item = choose_item(client, "landsat-c2-l2", lon, lat, dt)
    base = {
        "zoneId": zone.zoneId,
        "displayArea": zone.displayArea,
        "sensor": "Landsat Collection 2 L2",
        "period": label,
        "queryWindow": dt,
    }
    if item is None:
        return {**base, "status": "NO_ITEM"}
    try:
        signed = planetary_computer.sign(item)
        candidates = ["lwir11", "st", "surface_temperature"]
        key = next((k for k in candidates if k in signed.assets), None)
        if key is None:
            return {**base, "status": "ASSET_NOT_FOUND", "itemId": item.id, "assetKeys": sorted(signed.assets)}
        arr, meta = sample_asset(signed.assets[key].href, lon, lat, half_pixels=3)
        asset = signed.assets[key]
        scale = None
        offset = None
        rb = asset.extra_fields.get("raster:bands") or []
        if rb:
            scale = rb[0].get("scale")
            offset = rb[0].get("offset")
        values = arr.copy()
        if scale is not None:
            values = values * float(scale)
        if offset is not None:
            values = values + float(offset)
        valid = np.isfinite(values) & (values > 0)
        med = float(np.nanmedian(values[valid])) if valid.any() else None
        # Planetary Computer may expose Kelvin-scaled values. Keep raw metadata and add Celsius only when plausible.
        celsius = med - 273.15 if med is not None and 200 <= med <= 400 else None
        return {
            **base,
            "status": "SUCCESS" if valid.any() else "NO_VALID_PIXEL",
            "itemId": item.id,
            "datetime": item.datetime.isoformat() if item.datetime else None,
            "cloudCover": item.properties.get("eo:cloud_cover"),
            "assetKey": key,
            "validPixelCount": int(valid.sum()),
            "temperatureMedianNative": med,
            "temperatureMedianC": celsius,
            "scale": scale,
            "offset": offset,
            **meta,
        }
    except Exception as e:  # noqa: BLE001
        return {**base, "status": "FAILED", "itemId": item.id, "error": f"{type(e).__name__}: {e}"}


def summarize(cohort_df: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, zone in cohort_df.iterrows():
        z = observations[observations.zoneId == zone.zoneId]
        s = z[(z.sensor == "Sentinel-2 L2A") & (z.status == "SUCCESS")]
        l = z[(z.sensor == "Landsat Collection 2 L2") & (z.status == "SUCCESS")]
        leaf_off = pd.to_numeric(s[s.period.str.contains("leaf_off", na=False)].ndviMedian, errors="coerce")
        leaf_on = pd.to_numeric(s[s.period.str.contains("leaf_on", na=False)].ndviMedian, errors="coerce")
        hot = pd.to_numeric(l.temperatureMedianC, errors="coerce")
        ndvi_vals = pd.to_numeric(s.ndviMedian, errors="coerce")
        rows.append(
            {
                "zoneId": zone.zoneId,
                "displayArea": zone.displayArea,
                "cohortSources": zone.cohortSources,
                "sentinelValidObservations": int(ndvi_vals.notna().sum()),
                "landsatValidObservations": int(hot.notna().sum()),
                "leafOffNdviMean": float(leaf_off.mean()) if leaf_off.notna().any() else None,
                "leafOnNdviMean": float(leaf_on.mean()) if leaf_on.notna().any() else None,
                "seasonalNdviAmplitude": float(leaf_on.mean() - leaf_off.mean()) if leaf_on.notna().any() and leaf_off.notna().any() else None,
                "ndviInterannualStd": float(ndvi_vals.std(ddof=0)) if ndvi_vals.notna().sum() >= 2 else None,
                "hotSeasonTemperatureMeanC": float(hot.mean()) if hot.notna().any() else None,
                "temporalEvidenceState": "MULTIYEAR_MULTISEASON" if ndvi_vals.notna().sum() >= 4 else ("PARTIAL_TEMPORAL" if ndvi_vals.notna().sum() >= 2 else "TEMPORAL_UNKNOWN"),
                "productionRankingEffect": 0,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    c = cohort()
    client = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    observations: list[dict[str, Any]] = []
    for _, zone in c.iterrows():
        for label, dt in SENTINEL_WINDOWS.items():
            observations.append(sentinel_observation(client, zone, label, dt))
        for label, dt in LANDSAT_WINDOWS.items():
            observations.append(landsat_observation(client, zone, label, dt))
    obs = pd.DataFrame(observations)
    obs.to_csv(OUT / "ECOSCAPE_F17_TEMPORAL_OBSERVATIONS_V1.csv", index=False, encoding="utf-8-sig")
    summary = summarize(c, obs)
    summary.to_csv(OUT / "ECOSCAPE_F17_TEMPORAL_ZONE_SUMMARY_V1.csv", index=False, encoding="utf-8-sig")
    report = {
        "schema": "ECOSCAPE_F17_TEMPORAL_RUN_REPORT_V3",
        "generatedUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "zoneCount": int(len(c)),
        "observationRows": int(len(obs)),
        "statusCounts": obs.status.value_counts(dropna=False).to_dict(),
        "temporalEvidenceCounts": summary.temporalEvidenceState.value_counts(dropna=False).to_dict(),
        "rules": [
            "single scene is never treated as time series",
            "cloud/no-item remains unknown",
            "same sensor-date family counts once",
            "F16 ranking is not mutated by this run",
        ],
        "sourceWrites": 0,
        "rankingEffect": 0,
    }
    (OUT / "ECOSCAPE_F17_TEMPORAL_RUN_REPORT_V3.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
