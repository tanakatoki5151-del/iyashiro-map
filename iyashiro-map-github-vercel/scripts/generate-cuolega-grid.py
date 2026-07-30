#!/usr/bin/env python3
"""Generate calibrated 100 m Iyashiro terrain grids.

The original-theory decision is intentionally isolated from the auxiliary
terrain score:

* originalScore: high-line/high-line versus low-line/low-line crossings
* auxiliaryTerrainScore: relative elevation, drainage proxy and slope
* detailScore: 80% originalScore + 20% auxiliaryTerrainScore

The generator supports the Cuolega 4.5 km circle and the Tokyu Den-en-toshi
Line corridor from Shibuya through Futako-tamagawa. The output is consumed
both as an instant raster overlay and as compact JSON for address/click
diagnosis. It is a reproducible terrain proxy, not a measurement of biological
or medical effects.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter, map_coordinates, maximum_filter


ZOOM = 14
CUOLEGA_CENTER = {
    "lat": 35.667228,
    "lng": 139.759732,
    "name": "株式会社クオレガ 東京本社",
    "address": "東京都港区新橋1丁目10-6 新橋M-SQUARE",
}
DENENTOSHI_CENTER = {
    "lat": 35.635663,
    "lng": 139.664424,
    "name": "東急田園都市線 渋谷〜二子玉川",
    "address": "渋谷駅から二子玉川駅までの線路中心1km帯",
}
DENENTOSHI_STATIONS = (
    {"name": "渋谷", "lat": 35.659939, "lng": 139.699738},
    {"name": "池尻大橋", "lat": 35.650869, "lng": 139.684594},
    {"name": "三軒茶屋", "lat": 35.643726, "lng": 139.671962},
    {"name": "駒沢大学", "lat": 35.633193, "lng": 139.661156},
    {"name": "桜新町", "lat": 35.631724, "lng": 139.645369},
    {"name": "用賀", "lat": 35.626437, "lng": 139.633264},
    {"name": "二子玉川", "lat": 35.611387, "lng": 139.629109},
)
CENTER = dict(CUOLEGA_CENTER)
RADIUS_METERS = 4_500
DENENTOSHI_BUFFER_METERS = 1_000
DENENTOSHI_HALF_EXTENT_METERS = 4_500
STEP_METERS = 100
NEIGHBORHOOD_METERS = 500
NEARBY_BEST_METERS = 1_000
ANALYSIS_MARGIN_METERS = 4_800
SCALES = (
    # scale, absolute TPI floor, final weight
    (300, 0.45, 0.45),
    (1_000, 1.20, 0.35),
    (3_000, 2.80, 0.20),
)
# Lock the calibration to the already-published Cuolega grid so scores remain
# directly comparable when another precomputed region is added.
REFERENCE_THRESHOLDS = (0.499, 1.20, 2.80)
DIRECTIONS = tuple(index * 22.5 for index in range(8))
DEM_TEMPLATES = (
    "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png",
    "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png",
)

LABELS = {
    "iyashiro": "イヤシロチ候補",
    "kegare": "ケガレチ候補",
    "ordinary": "普通地",
    "mixed": "高低混在",
    "weak": "通常・弱い傾向",
    "insufficient": "判定材料不足",
}
LABEL_CODES = {
    "insufficient": 0,
    "iyashiro": 1,
    "kegare": 2,
    "ordinary": 3,
    "mixed": 4,
    "weak": 5,
}


def clamp(value: np.ndarray, minimum: float = 0, maximum: float = 1) -> np.ndarray:
    return np.clip(value, minimum, maximum)


def world_pixel(lat: float | np.ndarray, lng: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    size = (2**ZOOM) * 256
    latitude = np.asarray(lat, dtype=np.float64)
    longitude = np.asarray(lng, dtype=np.float64)
    x = ((longitude + 180) / 360) * size
    safe_lat = np.clip(latitude, -85.05112878, 85.05112878)
    radians = np.radians(safe_lat)
    y = ((1 - np.arcsinh(np.tan(radians)) / math.pi) / 2) * size
    return x, y


def meters_per_pixel(lat: float) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / (2**ZOOM)


def offset_coordinates(
    east_meters: np.ndarray | float,
    north_meters: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray]:
    east = np.asarray(east_meters, dtype=np.float64)
    north = np.asarray(north_meters, dtype=np.float64)
    lat = CENTER["lat"] + north / 111_320
    lng = CENTER["lng"] + east / (
        111_320 * math.cos(math.radians(CENTER["lat"]))
    )
    return lat, lng


def coordinate_offsets(lat: float, lng: float) -> tuple[float, float]:
    north = (lat - CENTER["lat"]) * 111_320
    east = (
        (lng - CENTER["lng"])
        * 111_320
        * math.cos(math.radians(CENTER["lat"]))
    )
    return east, north


def corridor_mask(
    east_grid: np.ndarray,
    north_grid: np.ndarray,
) -> np.ndarray:
    route = np.array(
        [
            coordinate_offsets(station["lat"], station["lng"])
            for station in DENENTOSHI_STATIONS
        ],
        dtype=np.float64,
    )
    shortest = np.full(east_grid.shape, np.inf, dtype=np.float64)
    for start, end in zip(route[:-1], route[1:]):
        segment = end - start
        length_squared = float(np.dot(segment, segment))
        projection = (
            (east_grid - start[0]) * segment[0]
            + (north_grid - start[1]) * segment[1]
        ) / length_squared
        projection = np.clip(projection, 0, 1)
        closest_east = start[0] + projection * segment[0]
        closest_north = start[1] + projection * segment[1]
        distance = np.hypot(
            east_grid - closest_east,
            north_grid - closest_north,
        )
        shortest = np.minimum(shortest, distance)
    return shortest <= DENENTOSHI_BUFFER_METERS + 1


def nearest_station(lat: float, lng: float) -> tuple[str, int]:
    distances = []
    for station in DENENTOSHI_STATIONS:
        north = (lat - station["lat"]) * 111_320
        east = (
            (lng - station["lng"])
            * 111_320
            * math.cos(math.radians((lat + station["lat"]) / 2))
        )
        distances.append((math.hypot(east, north), station["name"]))
    distance, name = min(distances)
    return name, int(round(distance))


def read_url(url: str, timeout: int = 15) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "image/png,image/*;q=0.8",
            "User-Agent": "iyashiro-map-grid-generator/2.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def decode_dem(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as source:
        image = np.asarray(source.convert("RGBA"))
    rgb = image[..., :3].astype(np.int32)
    unsigned = rgb[..., 0] * 65536 + rgb[..., 1] * 256 + rgb[..., 2]
    elevation = np.where(
        unsigned < 8388608,
        unsigned,
        unsigned - 16777216,
    ).astype(np.float32) * 0.01
    elevation[(unsigned == 8388608) | (image[..., 3] == 0)] = np.nan
    return elevation


def load_dem_tile(
    x: int,
    y: int,
    cache_dir: Path,
) -> tuple[int, int, np.ndarray]:
    combined = np.full((256, 256), np.nan, dtype=np.float32)
    for source_index, template in enumerate(DEM_TEMPLATES):
        path = (
            cache_dir
            / "dem"
            / str(ZOOM)
            / str(x)
            / f"{y}-{source_index}.png"
        )
        try:
            data = (
                path.read_bytes()
                if path.exists()
                else read_url(template.format(z=ZOOM, x=x, y=y))
            )
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            tile = decode_dem(data)
        except Exception:
            continue
        missing = ~np.isfinite(combined) & np.isfinite(tile)
        combined[missing] = tile[missing]
        if np.isfinite(combined).all():
            break
    return x, y, combined


def normalized_gaussian(values: np.ndarray, sigma: float) -> np.ndarray:
    valid = np.isfinite(values)
    numerator = gaussian_filter(
        np.where(valid, values, 0).astype(np.float32),
        sigma=max(0.6, sigma),
        mode="nearest",
    )
    denominator = gaussian_filter(
        valid.astype(np.float32),
        sigma=max(0.6, sigma),
        mode="nearest",
    )
    return np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan),
        where=denominator > 0.35,
    )


def sample_raster(
    values: np.ndarray,
    lat: np.ndarray,
    lng: np.ndarray,
    tile_x0: int,
    tile_y0: int,
    *,
    order: int = 1,
) -> np.ndarray:
    x, y = world_pixel(lat, lng)
    rows = y - tile_y0 * 256
    columns = x - tile_x0 * 256
    return map_coordinates(
        values,
        [rows, columns],
        order=order,
        mode="constant",
        cval=np.nan,
        prefilter=False,
    )


def axis_crossing(axes: list[np.ndarray]) -> np.ndarray:
    pairs: list[np.ndarray] = []
    for first in range(len(axes)):
        for second in range(first + 1, len(axes)):
            raw = abs(DIRECTIONS[first] - DIRECTIONS[second]) % 180
            angle = min(raw, 180 - raw)
            if angle < 22:
                continue
            angle_quality = math.sin(math.radians(angle))
            pairs.append(
                np.sqrt(axes[first] * axes[second]) * angle_quality
            )
    ordered = np.sort(np.stack(pairs), axis=0)
    strongest = ordered[-1]
    second = ordered[-2] if len(pairs) > 1 else 0
    return clamp(1 - (1 - strongest) * (1 - 0.45 * second))


def high_low_crossing(
    high_axes: list[np.ndarray],
    low_axes: list[np.ndarray],
) -> np.ndarray:
    pairs: list[np.ndarray] = []
    for high_index, high_axis in enumerate(high_axes):
        for low_index, low_axis in enumerate(low_axes):
            raw = abs(DIRECTIONS[high_index] - DIRECTIONS[low_index]) % 180
            angle = min(raw, 180 - raw)
            if angle < 22:
                continue
            pairs.append(
                np.sqrt(high_axis * low_axis)
                * math.sin(math.radians(angle))
            )
    ordered = np.sort(np.stack(pairs), axis=0)
    return clamp(1 - (1 - ordered[-1]) * (1 - 0.35 * ordered[-2]))


def combine_scale_evidence(
    values: list[np.ndarray],
    weights: np.ndarray,
) -> np.ndarray:
    stacked = np.stack(values)
    weighted = np.average(stacked, axis=0, weights=weights)
    peak = np.max(stacked, axis=0)
    return clamp(0.62 * weighted + 0.38 * peak)


def line_strengths(
    tpi: np.ndarray,
    threshold: float,
    grid_east: np.ndarray,
    grid_north: np.ndarray,
    scale: int,
    tile_x0: int,
    tile_y0: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high_axes: list[np.ndarray] = []
    low_axes: list[np.ndarray] = []
    for angle in DIRECTIONS:
        radians = math.radians(angle)
        east_unit = math.sin(radians)
        north_unit = math.cos(radians)
        high_samples: list[np.ndarray] = []
        low_samples: list[np.ndarray] = []
        for factor in (-1.5, -0.5, 0.5, 1.5):
            lat, lng = offset_coordinates(
                grid_east + factor * scale * east_unit,
                grid_north + factor * scale * north_unit,
            )
            sampled = sample_raster(
                tpi,
                lat,
                lng,
                tile_x0,
                tile_y0,
            )
            high_samples.append(
                clamp((sampled - 0.18 * threshold) / (1.55 * threshold))
            )
            low_samples.append(
                clamp((-sampled - 0.18 * threshold) / (1.55 * threshold))
            )

        def line_axis(samples: list[np.ndarray]) -> np.ndarray:
            negative = 0.62 * samples[1] + 0.38 * samples[0]
            positive = 0.62 * samples[2] + 0.38 * samples[3]
            continuity = np.mean(np.stack(samples), axis=0)
            return clamp(
                np.sqrt(negative * positive) * (0.68 + 0.32 * continuity)
            )

        high_axes.append(line_axis(high_samples))
        low_axes.append(line_axis(low_samples))
    return (
        axis_crossing(high_axes),
        axis_crossing(low_axes),
        high_low_crossing(high_axes, low_axes),
    )


def label_key(high: float, low: float, ordinary: float) -> str:
    strongest = max(high, low, ordinary)
    if strongest < 0.11:
        return "insufficient"
    if high >= 0.19 and high >= low + 0.045 and high >= ordinary - 0.015:
        return "iyashiro"
    if low >= 0.19 and low >= high + 0.045 and low >= ordinary - 0.015:
        return "kegare"
    if ordinary >= 0.18 and ordinary >= max(high, low) - 0.025:
        return "ordinary"
    if high >= 0.15 and low >= 0.15 and abs(high - low) < 0.055:
        return "mixed"
    return "weak"


def local_normalized(values: np.ndarray, mask: np.ndarray, sigma: float) -> np.ndarray:
    valid = mask & np.isfinite(values)
    numerator = gaussian_filter(
        np.where(valid, values, 0).astype(np.float32),
        sigma=sigma,
        mode="nearest",
    )
    denominator = gaussian_filter(
        valid.astype(np.float32),
        sigma=sigma,
        mode="nearest",
    )
    return np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan),
        where=denominator > 0.02,
    )


def make_overlay(
    output_path: Path,
    label_codes: np.ndarray,
    original_score: np.ndarray,
    confidence: np.ndarray,
    grid_mask: np.ndarray,
) -> None:
    scale = 10
    size = label_codes.shape[0]
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    base_colors = {
        0: (148, 151, 146),
        1: (11, 126, 105),
        2: (137, 34, 71),
        3: (184, 141, 35),
        4: (104, 91, 142),
        5: (130, 132, 127),
    }
    for row in range(size):
        for column in range(size):
            if not grid_mask[row, column]:
                continue
            code = int(label_codes[row, column])
            base = np.array(base_colors[code], dtype=np.float32)
            direction = abs(float(original_score[row, column]) - 50) / 50
            saturation = 0.58 + 0.42 * direction
            color = np.rint(242 + (base - 242) * saturation).astype(np.uint8)
            alpha = int(round(130 + 100 * float(confidence[row, column])))
            draw.rectangle(
                (
                    column * scale,
                    row * scale,
                    (column + 1) * scale - 1,
                    (row + 1) * scale - 1,
                ),
                fill=(*map(int, color), min(230, alpha)),
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, optimize=True)


def main() -> None:
    global CENTER

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--region",
        choices=("cuolega", "denentoshi"),
        default="cuolega",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--overlay-output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(
            os.environ.get("IYASHIRO_CACHE", "/tmp/iyashiro-overlay")
        ),
    )
    args = parser.parse_args()

    if args.region == "denentoshi":
        CENTER = dict(DENENTOSHI_CENTER)
        region_half_extent = DENENTOSHI_HALF_EXTENT_METERS
        region_name = "田園都市線 渋谷〜二子玉川・線路中心1km帯"
        region_kind = "corridor"
        output_stem = "denentoshi-shibuya-futako-grid-v2"
    else:
        CENTER = dict(CUOLEGA_CENTER)
        region_half_extent = RADIUS_METERS
        region_name = "クオレガ東京本社4.5km圏"
        region_kind = "circle"
        output_stem = "cuolega-grid-v2"

    json_output = args.json_output or Path(f"public/data/{output_stem}.json")
    overlay_output = args.overlay_output or Path(f"public/data/{output_stem}.png")
    extent = region_half_extent + ANALYSIS_MARGIN_METERS
    north_lat, west_lng = offset_coordinates(-extent, extent)
    south_lat, east_lng = offset_coordinates(extent, -extent)
    west_pixel, north_pixel = world_pixel(float(north_lat), float(west_lng))
    east_pixel, south_pixel = world_pixel(float(south_lat), float(east_lng))
    tile_x0 = int(math.floor(float(west_pixel) / 256))
    tile_y0 = int(math.floor(float(north_pixel) / 256))
    tile_x1 = int(math.floor(float(east_pixel) / 256))
    tile_y1 = int(math.floor(float(south_pixel) / 256))
    mosaic = np.full(
        (
            (tile_y1 - tile_y0 + 1) * 256,
            (tile_x1 - tile_x0 + 1) * 256,
        ),
        np.nan,
        dtype=np.float32,
    )

    jobs = [
        (x, y)
        for y in range(tile_y0, tile_y1 + 1)
        for x in range(tile_x0, tile_x1 + 1)
    ]
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(load_dem_tile, x, y, args.cache_dir): (x, y)
            for x, y in jobs
        }
        for future in as_completed(futures):
            x, y, tile = future.result()
            left = (x - tile_x0) * 256
            top = (y - tile_y0) * 256
            mosaic[top : top + 256, left : left + 256] = tile

    offsets = np.arange(
        -region_half_extent,
        region_half_extent + STEP_METERS,
        STEP_METERS,
        dtype=np.float64,
    )
    east_grid, north_grid_top = np.meshgrid(offsets, offsets[::-1])
    grid_mask = (
        corridor_mask(east_grid, north_grid_top)
        if args.region == "denentoshi"
        else east_grid**2 + north_grid_top**2 <= RADIUS_METERS**2 + 1
    )
    grid_east = east_grid[grid_mask]
    grid_north = north_grid_top[grid_mask]
    grid_lat, grid_lng = offset_coordinates(grid_east, grid_north)

    mpp = meters_per_pixel(CENTER["lat"])
    weights = np.array([entry[2] for entry in SCALES], dtype=np.float32)
    high_scales: list[np.ndarray] = []
    low_scales: list[np.ndarray] = []
    ordinary_scales: list[np.ndarray] = []
    center_tpi_scales: list[np.ndarray] = []
    coverages: list[np.ndarray] = []
    scale_thresholds: list[float] = []

    valid_mosaic = np.isfinite(mosaic)
    for scale_index, (scale, _absolute_floor, _weight) in enumerate(SCALES):
        inner = normalized_gaussian(mosaic, sigma=max(0.8, scale / mpp / 10))
        outer = normalized_gaussian(mosaic, sigma=max(1.2, scale / mpp / 2.2))
        tpi = inner - outer
        threshold = REFERENCE_THRESHOLDS[scale_index]
        scale_thresholds.append(threshold)
        high, low, ordinary = line_strengths(
            tpi,
            threshold,
            grid_east,
            grid_north,
            scale,
            tile_x0,
            tile_y0,
        )
        high_scales.append(np.nan_to_num(high, nan=0))
        low_scales.append(np.nan_to_num(low, nan=0))
        ordinary_scales.append(np.nan_to_num(ordinary, nan=0))
        center_tpi_scales.append(
            np.tanh(
                np.nan_to_num(
                    sample_raster(
                        tpi,
                        grid_lat,
                        grid_lng,
                        tile_x0,
                        tile_y0,
                    ),
                    nan=0,
                )
                / (1.7 * threshold)
            )
        )
        coverage_surface = normalized_gaussian(
            valid_mosaic.astype(np.float32),
            sigma=max(1.0, scale / mpp / 4),
        )
        coverages.append(
            clamp(
                np.nan_to_num(
                    sample_raster(
                        coverage_surface,
                        grid_lat,
                        grid_lng,
                        tile_x0,
                        tile_y0,
                    ),
                    nan=0,
                )
            )
        )

    high = combine_scale_evidence(high_scales, weights)
    low = combine_scale_evidence(low_scales, weights)
    ordinary = combine_scale_evidence(ordinary_scales, weights)
    ordinary_pull = 1 - 0.38 * ordinary
    original_score = np.rint(
        clamp(50 + 50 * (high - low) * ordinary_pull, 0, 100)
    ).astype(np.int16)

    tpi_index = np.average(np.stack(center_tpi_scales), axis=0, weights=weights)
    relative_score = clamp(50 + 45 * tpi_index, 0, 100)
    drainage_score = clamp(50 + 40 * tpi_index - 18 * low, 0, 100)

    smooth = normalized_gaussian(mosaic, sigma=max(0.8, 35 / mpp))
    gradient_y, gradient_x = np.gradient(smooth, mpp, mpp)
    slope_degrees = np.degrees(np.arctan(np.hypot(gradient_x, gradient_y)))
    sampled_slope = np.nan_to_num(
        sample_raster(
            slope_degrees,
            grid_lat,
            grid_lng,
            tile_x0,
            tile_y0,
        ),
        nan=30,
    )
    slope_score = clamp(
        np.where(
            sampled_slope <= 8,
            92 - 1.2 * np.abs(sampled_slope - 4),
            92 - 4.0 * (sampled_slope - 8),
        ),
        0,
        100,
    )
    auxiliary_score = np.rint(
        0.48 * relative_score + 0.32 * drainage_score + 0.20 * slope_score
    ).astype(np.int16)
    detail_score = np.rint(
        0.80 * original_score + 0.20 * auxiliary_score
    ).astype(np.int16)

    stacked = np.stack([high_scales, low_scales, ordinary_scales])
    winners = np.argmax(stacked, axis=0)
    dominant_by_scale = np.max(stacked, axis=0)
    dominant_class = np.argmax(
        np.stack([high, low, ordinary]),
        axis=0,
    )
    agreement = np.mean(
        winners == dominant_class[np.newaxis, :],
        axis=0,
    )
    evidence_strength = np.max(np.stack([high, low, ordinary]), axis=0)
    coverage = np.average(np.stack(coverages), axis=0, weights=weights)
    active_scales = np.mean(dominant_by_scale >= 0.12, axis=0)
    confidence = np.rint(
        100
        * clamp(
            0.38 * coverage
            + 0.34 * evidence_strength
            + 0.18 * agreement
            + 0.10 * active_scales
        )
    ).astype(np.int16)

    keys = np.array(
        [label_key(float(h), float(l), float(o)) for h, l, o in zip(high, low, ordinary)]
    )
    label_codes_flat = np.array([LABEL_CODES[key] for key in keys], dtype=np.int8)

    matrix_size = len(offsets)
    detail_matrix = np.full((matrix_size, matrix_size), np.nan, dtype=np.float32)
    confidence_matrix = np.full_like(detail_matrix, np.nan)
    original_matrix = np.full_like(detail_matrix, np.nan)
    label_matrix = np.zeros((matrix_size, matrix_size), dtype=np.int8)
    detail_matrix[grid_mask] = detail_score
    confidence_matrix[grid_mask] = confidence / 100
    original_matrix[grid_mask] = original_score
    label_matrix[grid_mask] = label_codes_flat

    neighborhood = local_normalized(
        detail_matrix,
        grid_mask,
        sigma=NEIGHBORHOOD_METERS / STEP_METERS / 2,
    )
    neighborhood_score = np.rint(neighborhood[grid_mask]).astype(np.int16)

    iyashiro_surface = np.where(
        (label_matrix == LABEL_CODES["iyashiro"])
        & (confidence_matrix >= 0.48),
        detail_matrix,
        -np.inf,
    )
    local_maximum = (
        iyashiro_surface
        == maximum_filter(
            iyashiro_surface,
            size=5,
            mode="constant",
            cval=-np.inf,
        )
    ) & np.isfinite(iyashiro_surface)
    hotspot_rows, hotspot_columns = np.where(local_maximum)
    order = np.argsort(iyashiro_surface[local_maximum])[::-1]
    selected_hotspots: list[tuple[int, int]] = []
    for position in order:
        row = int(hotspot_rows[position])
        column = int(hotspot_columns[position])
        if any(
            math.hypot(row - prior_row, column - prior_column)
            * STEP_METERS
            < 350
            for prior_row, prior_column in selected_hotspots
        ):
            continue
        selected_hotspots.append((row, column))
        if len(selected_hotspots) >= 60:
            break

    hotspot_payload = []
    for row, column in selected_hotspots:
        east = float(east_grid[row, column])
        north = float(north_grid_top[row, column])
        lat, lng = offset_coordinates(east, north)
        hotspot = {
            "lat": round(float(lat), 6),
            "lng": round(float(lng), 6),
            "detailScore": int(detail_matrix[row, column]),
            "originalScore": int(original_matrix[row, column]),
            "confidence": int(round(confidence_matrix[row, column] * 100)),
            "label": LABELS["iyashiro"],
        }
        if args.region == "denentoshi":
            station_name, station_distance = nearest_station(
                float(lat),
                float(lng),
            )
            hotspot["nearestStation"] = station_name
            hotspot["stationDistanceMeters"] = station_distance
        hotspot_payload.append(hotspot)

    nearby_best_index = np.full(len(grid_lat), -1, dtype=np.int16)
    nearby_best_distance = np.full(len(grid_lat), np.nan, dtype=np.float32)
    for index, (east, north) in enumerate(zip(grid_east, grid_north)):
        best: tuple[float, float, int] | None = None
        for hotspot_index, hotspot in enumerate(hotspot_payload):
            hotspot_east = (
                (hotspot["lng"] - CENTER["lng"])
                * 111_320
                * math.cos(math.radians(CENTER["lat"]))
            )
            hotspot_north = (hotspot["lat"] - CENTER["lat"]) * 111_320
            distance = math.hypot(
                float(east) - hotspot_east,
                float(north) - hotspot_north,
            )
            if distance > NEARBY_BEST_METERS:
                continue
            score = float(hotspot["detailScore"])
            candidate = (score, -distance, hotspot_index)
            if best is None or candidate > best:
                best = candidate
        if best is not None:
            nearby_best_index[index] = best[2]
            nearby_best_distance[index] = -best[1]

    cell_half = STEP_METERS / 2
    cells = []
    for index in range(len(grid_lat)):
        key = str(keys[index])
        south, west = offset_coordinates(
            grid_east[index] - cell_half,
            grid_north[index] - cell_half,
        )
        north, east = offset_coordinates(
            grid_east[index] + cell_half,
            grid_north[index] + cell_half,
        )
        cells.append(
            {
                "lat": round(float(grid_lat[index]), 6),
                "lng": round(float(grid_lng[index]), 6),
                "bounds": [
                    [round(float(south), 6), round(float(west), 6)],
                    [round(float(north), 6), round(float(east), 6)],
                ],
                "label": LABELS[key],
                "labelCode": int(label_codes_flat[index]),
                "originalScore": int(original_score[index]),
                "originalFit": int(
                    round(100 * max(high[index], low[index], ordinary[index]))
                ),
                "highEvidence": round(float(high[index]), 3),
                "lowEvidence": round(float(low[index]), 3),
                "ordinaryEvidence": round(float(ordinary[index]), 3),
                "auxiliaryTerrainScore": int(auxiliary_score[index]),
                "detailScore": int(detail_score[index]),
                "neighborhoodScore": int(neighborhood_score[index]),
                "confidence": int(confidence[index]),
                "nearbyBestIndex": int(nearby_best_index[index]),
                "nearbyBestDistanceMeters": (
                    int(round(float(nearby_best_distance[index])))
                    if np.isfinite(nearby_best_distance[index])
                    else None
                ),
            }
        )

    south, west = offset_coordinates(-region_half_extent, -region_half_extent)
    north, east = offset_coordinates(region_half_extent, region_half_extent)
    region_payload = {
        "id": args.region,
        "kind": region_kind,
        "name": region_name,
        "stepMeters": STEP_METERS,
    }
    if args.region == "denentoshi":
        region_payload.update(
            {
                "bufferMeters": DENENTOSHI_BUFFER_METERS,
                "stations": list(DENENTOSHI_STATIONS),
            }
        )
    else:
        region_payload["radiusMeters"] = RADIUS_METERS
    payload = {
        "schemaVersion": "2.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "engine": {
            "name": "directional-line-crossing-v2",
            "originalWeight": 0.80,
            "auxiliaryWeight": 0.20,
            "scalesMeters": [entry[0] for entry in SCALES],
            "thresholdsMeters": [round(value, 3) for value in scale_thresholds],
            "neighborhoodMeters": NEIGHBORHOOD_METERS,
            "nearbyBestMeters": NEARBY_BEST_METERS,
        },
        "center": {
            **CENTER,
            "stepMeters": STEP_METERS,
            **(
                {"radiusMeters": RADIUS_METERS}
                if args.region == "cuolega"
                else {"bufferMeters": DENENTOSHI_BUFFER_METERS}
            ),
        },
        "region": region_payload,
        "bounds": [
            [round(float(south), 6), round(float(west), 6)],
            [round(float(north), 6), round(float(east), 6)],
        ],
        "cells": cells,
        "hotspots": hotspot_payload,
        "disclaimer": (
            "原典判定は高位指向線・低位指向線の交会をDEMで再現した"
            "仮説指標です。補助地形点と判定信頼度は原典の効能を証明する"
            "確率ではありません。"
        ),
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    make_overlay(
        overlay_output,
        label_matrix,
        original_matrix,
        confidence_matrix,
        grid_mask,
    )

    counts = {
        LABELS[key]: int(np.sum(keys == key))
        for key in LABELS
    }
    print(
        json.dumps(
            {
                "region": args.region,
                "json": str(json_output),
                "overlay": str(overlay_output),
                "cells": len(cells),
                "hotspots": len(hotspot_payload),
                "counts": counts,
                "originalRange": [
                    int(np.min(original_score)),
                    int(np.max(original_score)),
                ],
                "detailRange": [
                    int(np.min(detail_score)),
                    int(np.max(detail_score)),
                ],
                "confidenceRange": [
                    int(np.min(confidence)),
                    int(np.max(confidence)),
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
