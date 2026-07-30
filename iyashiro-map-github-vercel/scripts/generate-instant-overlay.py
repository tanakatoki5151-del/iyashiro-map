#!/usr/bin/env python3
"""Generate the instant, wide-area Iyashiro hypothesis overlay.

The detailed point diagnosis remains authoritative inside this application.
This script creates a lightweight raster preview from GSI DEM tiles so the map
has useful colour immediately, before the detailed API grid finishes.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter


ZOOM = 11
BOUNDS = {
    "south": 35.28,
    "west": 139.43,
    "north": 35.84,
    "east": 139.94,
}
BOUNDARY_URLS = {
    "tokyo": (
        "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2025/"
        "N03-20250101_13_GML.zip"
    ),
    "kanagawa": (
        "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2025/"
        "N03-20250101_14_GML.zip"
    ),
}
DEM_TEMPLATES = (
    "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png",
    "https://cyberjapandata.gsi.go.jp/xyz/dem5b_png/{z}/{x}/{y}.png",
    "https://cyberjapandata.gsi.go.jp/xyz/dem5c_png/{z}/{x}/{y}.png",
    "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png",
)
SUPPORTED_CODES = {
    *(str(code) for code in range(13101, 13124)),
    *(str(code) for code in range(14101, 14119)),
    *(str(code) for code in range(14131, 14138)),
}
SCALES = (
    (300, 0.7),
    (1_000, 1.75),
    (3_000, 3.5),
)
THEORY_LOW = np.array([127, 29, 78], dtype=np.float32)
THEORY_MIDDLE = np.array([168, 165, 155], dtype=np.float32)
THEORY_HIGH = np.array([15, 138, 120], dtype=np.float32)


def world_pixel(lat: float, lng: float, zoom: int = ZOOM) -> tuple[float, float]:
    size = (2**zoom) * 256
    x = ((lng + 180) / 360) * size
    safe_lat = max(-85.05112878, min(85.05112878, lat))
    radians = math.radians(safe_lat)
    y = ((1 - math.asinh(math.tan(radians)) / math.pi) / 2) * size
    return x, y


def meters_per_pixel(lat: float, zoom: int = ZOOM) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / (2**zoom)


def read_url(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "image/png,application/zip,*/*;q=0.5",
            "User-Agent": "iyashiro-map-overlay-generator/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def cached_download(url: str, path: Path) -> Path:
    if path.exists() and path.stat().st_size:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(read_url(url, timeout=120))
    return path


def decode_dem(data: bytes) -> np.ndarray:
    image = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))
    rgb = image[..., :3].astype(np.int32)
    unsigned = rgb[..., 0] * 65536 + rgb[..., 1] * 256 + rgb[..., 2]
    elevation = np.where(
        unsigned < 8388608,
        unsigned,
        unsigned - 16777216,
    ).astype(np.float32) * 0.01
    invalid = (unsigned == 8388608) | (image[..., 3] == 0)
    elevation[invalid] = np.nan
    return elevation


def load_dem_tile(x: int, y: int, cache_dir: Path) -> tuple[int, int, np.ndarray]:
    combined = np.full((256, 256), np.nan, dtype=np.float32)
    for source_index, template in enumerate(DEM_TEMPLATES):
        path = cache_dir / "dem" / str(ZOOM) / str(x) / f"{y}-{source_index}.png"
        try:
            data = path.read_bytes() if path.exists() else read_url(
                template.format(z=ZOOM, x=x, y=y)
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
        where=denominator > 0.45,
    )


def shifted(values: np.ndarray, dy: int, dx: int) -> np.ndarray:
    result = np.full_like(values, np.nan)
    source_y_start = max(0, -dy)
    source_y_end = values.shape[0] - max(0, dy)
    source_x_start = max(0, -dx)
    source_x_end = values.shape[1] - max(0, dx)
    target_y_start = max(0, dy)
    target_y_end = values.shape[0] - max(0, -dy)
    target_x_start = max(0, dx)
    target_x_end = values.shape[1] - max(0, -dx)
    result[target_y_start:target_y_end, target_x_start:target_x_end] = values[
        source_y_start:source_y_end,
        source_x_start:source_x_end,
    ]
    return result


def quick_crossing(
    elevation: np.ndarray,
    distance_pixels: float,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    radius = max(2, int(round(distance_pixels)))
    diagonal = max(1, int(round(radius / math.sqrt(2))))
    surface = normalized_gaussian(elevation, sigma=max(0.8, radius * 0.1))
    directions = (
        ((-radius, 0), (radius, 0)),
        ((0, -radius), (0, radius)),
        ((-diagonal, -diagonal), (diagonal, diagonal)),
        ((-diagonal, diagonal), (diagonal, -diagonal)),
    )
    high_axes = []
    low_axes = []
    valid_axes = []
    neighbours = []
    for (dy_a, dx_a), (dy_b, dx_b) in directions:
        first = shifted(surface, dy_a, dx_a)
        second = shifted(surface, dy_b, dx_b)
        neighbours.extend((first, second))
        axis_valid = (
            np.isfinite(surface) & np.isfinite(first) & np.isfinite(second)
        )
        high_strength = np.minimum(surface - first, surface - second)
        low_strength = np.minimum(first - surface, second - surface)
        high_axes.append(
            np.where(
                axis_valid,
                np.clip(high_strength / (threshold * 3), 0, 1),
                0,
            )
        )
        low_axes.append(
            np.where(
                axis_valid,
                np.clip(low_strength / (threshold * 3), 0, 1),
                0,
            )
        )
        valid_axes.append(axis_valid.astype(np.float32))

    def second_axis_crossing(axes: list[np.ndarray]) -> np.ndarray:
        ordered = np.sort(np.stack(axes), axis=0)
        return np.sqrt(ordered[-1] * ordered[-2])

    neighbour_stack = np.stack(neighbours)
    finite_neighbour = np.isfinite(neighbour_stack)
    maximum = np.max(
        np.where(finite_neighbour, neighbour_stack, -np.inf),
        axis=0,
    )
    minimum = np.min(
        np.where(finite_neighbour, neighbour_stack, np.inf),
        axis=0,
    )
    relief = np.where(
        finite_neighbour.any(axis=0),
        maximum - minimum,
        np.nan,
    )
    relief_factor = np.clip(relief / (threshold * 8), 0, 1)
    high = second_axis_crossing(high_axes) * relief_factor
    low = second_axis_crossing(low_axes) * relief_factor
    coverage = np.mean(np.stack(valid_axes), axis=0)
    return high, low, coverage


def union_evidence(values: list[np.ndarray]) -> np.ndarray:
    remaining = np.ones_like(values[0])
    for value in values:
        remaining *= 1 - value
    return 1 - remaining


def theory_surface(elevation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    resolution = meters_per_pixel(
        (BOUNDS["north"] + BOUNDS["south"]) / 2
    )
    highs = []
    lows = []
    coverages = []
    scale_evidence = []
    for meters, threshold in SCALES:
        high, low, coverage = quick_crossing(
            elevation,
            meters / resolution,
            threshold,
        )
        highs.append(high * 0.72)
        lows.append(low * 0.72)
        coverages.append(coverage)
        scale_evidence.append(np.maximum(high, low))
    high_evidence = np.clip(union_evidence(highs), 0, 1)
    low_evidence = np.clip(union_evidence(lows), 0, 1)
    score = np.clip(
        np.rint(50 + 50 * (high_evidence - low_evidence)),
        0,
        100,
    )
    coverage = np.mean(np.stack(coverages), axis=0)
    evidence_scales = np.mean(np.stack(scale_evidence) >= 0.25, axis=0)
    confidence = np.clip(
        0.35 * coverage
        + 0.4 * np.maximum(high_evidence, low_evidence)
        + 0.25 * evidence_scales,
        0,
        1,
    )
    return score, confidence


def supported_features(zip_path: Path) -> list[dict]:
    with zipfile.ZipFile(zip_path) as archive:
        geojson_name = next(
            name for name in archive.namelist() if name.endswith(".geojson")
        )
        data = json.loads(archive.read(geojson_name))
    return [
        feature
        for feature in data["features"]
        if str(feature.get("properties", {}).get("N03_007")) in SUPPORTED_CODES
    ]


def draw_geometry(
    draw: ImageDraw.ImageDraw,
    geometry: dict,
    offset_x: float,
    offset_y: float,
) -> None:
    coordinates = geometry.get("coordinates", [])
    kind = geometry.get("type")
    polygons = [coordinates] if kind == "Polygon" else coordinates
    if kind not in {"Polygon", "MultiPolygon"}:
        return
    for polygon in polygons:
        if not polygon:
            continue
        for ring_index, ring in enumerate(polygon):
            points = []
            for lng, lat, *_ in ring:
                x, y = world_pixel(lat, lng)
                points.append((x - offset_x, y - offset_y))
            if len(points) >= 3:
                draw.polygon(points, fill=255 if ring_index == 0 else 0)


def boundary_mask(
    features: list[dict],
    width: int,
    height: int,
    offset_x: float,
    offset_y: float,
) -> np.ndarray:
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    for feature in features:
        draw_geometry(
            draw,
            feature.get("geometry") or {},
            offset_x,
            offset_y,
        )
    return np.asarray(image) > 0


def colorize(
    score: np.ndarray,
    confidence: np.ndarray,
    mask: np.ndarray,
) -> Image.Image:
    score = np.nan_to_num(score, nan=50)
    confidence = np.nan_to_num(confidence, nan=0)
    ratio = np.clip(score / 50, 0, 1)[..., None]
    low_half = THEORY_LOW + (THEORY_MIDDLE - THEORY_LOW) * ratio
    high_ratio = np.clip((score - 50) / 50, 0, 1)[..., None]
    high_half = THEORY_MIDDLE + (THEORY_HIGH - THEORY_MIDDLE) * high_ratio
    rgb = np.where((score < 50)[..., None], low_half, high_half)
    alpha = np.where(
        mask,
        np.rint(92 + 115 * confidence),
        0,
    )
    rgba = np.concatenate((np.rint(rgb), alpha[..., None]), axis=2)
    return Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA")


def smooth_preview(
    score: np.ndarray,
    confidence: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    weight = mask.astype(np.float32)
    denominator = gaussian_filter(weight, sigma=4.2, mode="nearest")

    def masked_blur(values: np.ndarray) -> np.ndarray:
        numerator = gaussian_filter(
            np.where(mask, values, 0).astype(np.float32),
            sigma=4.2,
            mode="nearest",
        )
        return np.divide(
            numerator,
            denominator,
            out=np.zeros_like(numerator),
            where=denominator > 0.03,
        )

    smoothed_score = np.clip(
        50 + 1.15 * masked_blur(score - 50),
        0,
        100,
    )
    smoothed_confidence = np.clip(masked_blur(confidence), 0, 1)
    return smoothed_score, smoothed_confidence


def sample_report(
    score: np.ndarray,
    confidence: np.ndarray,
    samples: list[tuple[str, float, float]],
    west_pixel: float,
    north_pixel: float,
) -> None:
    for name, lat, lng in samples:
        x, y = world_pixel(lat, lng)
        column = int(round(x - west_pixel))
        row = int(round(y - north_pixel))
        if 0 <= row < score.shape[0] and 0 <= column < score.shape[1]:
            print(
                f"{name}: score={score[row, column]:.0f}, "
                f"confidence={confidence[row, column] * 100:.0f}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public/data/iyashiro-overview.png"),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(os.environ.get("IYASHIRO_CACHE", "/tmp/iyashiro-overlay")),
    )
    parser.add_argument("--tokyo-boundaries", type=Path)
    parser.add_argument("--kanagawa-boundaries", type=Path)
    args = parser.parse_args()

    tokyo_zip = args.tokyo_boundaries or cached_download(
        BOUNDARY_URLS["tokyo"],
        args.cache_dir / "N03-20250101_13_GML.zip",
    )
    kanagawa_zip = args.kanagawa_boundaries or cached_download(
        BOUNDARY_URLS["kanagawa"],
        args.cache_dir / "N03-20250101_14_GML.zip",
    )

    west_pixel, north_pixel = world_pixel(
        BOUNDS["north"], BOUNDS["west"]
    )
    east_pixel, south_pixel = world_pixel(
        BOUNDS["south"], BOUNDS["east"]
    )
    width = int(math.ceil(east_pixel - west_pixel))
    height = int(math.ceil(south_pixel - north_pixel))
    margin = 64
    mosaic_x0 = int(math.floor(west_pixel)) - margin
    mosaic_y0 = int(math.floor(north_pixel)) - margin
    mosaic_x1 = int(math.ceil(east_pixel)) + margin
    mosaic_y1 = int(math.ceil(south_pixel)) + margin
    tile_x0 = mosaic_x0 // 256
    tile_y0 = mosaic_y0 // 256
    tile_x1 = (mosaic_x1 - 1) // 256
    tile_y1 = (mosaic_y1 - 1) // 256
    tile_width = (tile_x1 - tile_x0 + 1) * 256
    tile_height = (tile_y1 - tile_y0 + 1) * 256
    mosaic = np.full((tile_height, tile_width), np.nan, dtype=np.float32)

    jobs = [
        (x, y)
        for y in range(tile_y0, tile_y1 + 1)
        for x in range(tile_x0, tile_x1 + 1)
    ]
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(load_dem_tile, x, y, args.cache_dir): (x, y)
            for x, y in jobs
        }
        for future in as_completed(futures):
            x, y, tile = future.result()
            left = (x - tile_x0) * 256
            top = (y - tile_y0) * 256
            mosaic[top : top + 256, left : left + 256] = tile

    score_mosaic, confidence_mosaic = theory_surface(mosaic)
    crop_left = int(round(west_pixel - tile_x0 * 256))
    crop_top = int(round(north_pixel - tile_y0 * 256))
    score = score_mosaic[crop_top : crop_top + height, crop_left : crop_left + width]
    confidence = confidence_mosaic[
        crop_top : crop_top + height,
        crop_left : crop_left + width,
    ]
    features = supported_features(tokyo_zip) + supported_features(kanagawa_zip)
    mask = boundary_mask(features, width, height, west_pixel, north_pixel)
    mask &= np.isfinite(score)
    score, confidence = smooth_preview(score, confidence, mask)
    output = colorize(score, confidence, mask)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.save(args.output, optimize=True)

    print(
        f"wrote {args.output} ({width}x{height}), "
        f"covered pixels={int(mask.sum())}"
    )
    sample_report(
        score,
        confidence,
        [
            ("Tokyo Station", 35.681236, 139.767125),
            ("Yokohama Station", 35.466188, 139.622715),
            ("Kawasaki hill", 35.6000, 139.5500),
        ],
        west_pixel,
        north_pixel,
    )


if __name__ == "__main__":
    main()
