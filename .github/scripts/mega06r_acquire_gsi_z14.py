#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import mapbox_vector_tile
import requests

BUILD_ID = "mega06r-gsi-current-water-z14-acquisition-r2"
SOURCE_EPOCH = "GSI_Vector_updated_2026-04-01"
BBOX = {
    "minLon": 139.44932429,
    "minLat": 35.31278836,
    "maxLon": 139.91862851,
    "maxLat": 35.81763924,
}


def lon_to_x(lon: float, zoom: int) -> int:
    return int(math.floor((lon + 180.0) / 360.0 * (2 ** zoom)))


def lat_to_y(lat: float, zoom: int) -> int:
    lat_rad = math.radians(lat)
    return int(math.floor((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * (2 ** zoom)))


def tile_point_to_lonlat(tile_x: int, tile_y: int, extent: int, point, z: int):
    px, py = point
    n = 2 ** z
    x_norm = (tile_x + (float(px) / extent)) / n
    y_norm = (tile_y + ((extent - float(py)) / extent)) / n
    lon = x_norm * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y_norm))))
    return [lon, lat]


def transform_geometry(geometry: dict, tile_x: int, tile_y: int, extent: int, z: int) -> dict:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    convert = lambda p: tile_point_to_lonlat(tile_x, tile_y, extent, p, z)
    if gtype == "Point":
        out = convert(coords)
    elif gtype in ("MultiPoint", "LineString"):
        out = [convert(p) for p in coords]
    elif gtype in ("MultiLineString", "Polygon"):
        out = [[convert(p) for p in part] for part in coords]
    elif gtype == "MultiPolygon":
        out = [[[convert(p) for p in ring] for ring in polygon] for polygon in coords]
    else:
        raise ValueError(f"Unsupported geometry type: {gtype}")
    return {"type": gtype, "coordinates": out}


def iter_points(coords):
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        yield coords
    else:
        for item in coords:
            yield from iter_points(item)


def geometry_bbox(geometry: dict):
    points = list(iter_points(geometry["coordinates"]))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def bbox_intersects(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def download_tile(item, tiles_dir: Path):
    z, x, y, url, filename = item
    output = tiles_dir / filename
    headers = {"User-Agent": "Mozilla/5.0 MEGA06R research acquisition"}
    last_error = None
    for attempt in range(1, 6):
        try:
            response = requests.get(url, headers=headers, timeout=(30, 240))
            if response.status_code == 404:
                return {"status": "MISSING_404", "z": z, "x": x, "y": y, "file": filename, "sizeBytes": 0, "error": None}
            response.raise_for_status()
            output.write_bytes(response.content)
            return {
                "status": "OK",
                "z": z,
                "x": x,
                "y": y,
                "file": filename,
                "sizeBytes": len(response.content),
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "error": None,
            }
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(min(2 * attempt, 10))
    return {"status": "FAILED", "z": z, "x": x, "y": y, "file": filename, "sizeBytes": 0, "error": last_error}


def write_geojson_gz(path: Path, features: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--zoom", type=int, default=14)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()
    root = args.out
    tiles_dir = root / "raw_tiles"
    root.mkdir(parents=True, exist_ok=True)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    z = args.zoom
    xmin = lon_to_x(BBOX["minLon"], z) - 1
    xmax = lon_to_x(BBOX["maxLon"], z) + 1
    ymin = lat_to_y(BBOX["maxLat"], z) - 1
    ymax = lat_to_y(BBOX["minLat"], z) + 1
    requests_list = []
    for x in range(xmin, xmax + 1):
        for y in range(ymin, ymax + 1):
            url = f"https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/{z}/{x}/{y}.pbf"
            requests_list.append((z, x, y, url, f"{z}_{x}_{y}.pbf"))

    request_manifest = {
        "buildId": BUILD_ID,
        "zoom": z,
        "studyBboxWgs84": BBOX,
        "oneTileBufferApplied": True,
        "xRange": [xmin, xmax],
        "yRange": [ymin, ymax],
        "tileRequestCount": len(requests_list),
        "sourceUrlTemplate": "https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/{z}/{x}/{y}.pbf",
        "sourceRole": "current-geometry delta only; W05 topology and flow direction remain authoritative",
    }
    (root / "REQUEST_MANIFEST.json").write_text(json.dumps(request_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    statuses = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_tile, item, tiles_dir): item for item in requests_list}
        for i, future in enumerate(as_completed(futures), start=1):
            statuses.append(future.result())
            if i % 100 == 0 or i == len(futures):
                print(f"Downloaded {i}/{len(futures)}", flush=True)

    statuses.sort(key=lambda r: (r["z"], r["x"], r["y"]))
    with (root / "DOWNLOAD_STATUS.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["status", "z", "x", "y", "file", "sizeBytes", "sha256", "error"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(statuses)

    failed = [r for r in statuses if r["status"] == "FAILED"]
    if failed:
        raise SystemExit(f"GSI downloads failed: {len(failed)}")

    clip_bbox = (BBOX["minLon"], BBOX["minLat"], BBOX["maxLon"], BBOX["maxLat"])
    combined_features = []
    river_features = []
    waterarea_features = []
    tile_rows = []
    layer_counts = Counter()
    ftcode_counts = Counter()
    geometry_counts = Counter()
    parse_errors = []

    downloaded_paths = sorted(tiles_dir.glob("*.pbf"))
    for i, path in enumerate(downloaded_paths, start=1):
        z_s, x_s, y_s = path.stem.split("_")
        tile_x, tile_y = int(x_s), int(y_s)
        raw = path.read_bytes()
        tile_feature_count = 0
        try:
            decoded = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": False})
            for layer_name in ("river", "waterarea"):
                layer = decoded.get(layer_name)
                if not layer:
                    continue
                extent = int(layer.get("extent") or 4096)
                for index, feature in enumerate(layer.get("features") or []):
                    geometry = transform_geometry(feature.get("geometry") or {}, tile_x, tile_y, extent, z)
                    if not bbox_intersects(geometry_bbox(geometry), clip_bbox):
                        continue
                    props = dict(feature.get("properties") or {})
                    props.update({
                        "sourceLayer": layer_name,
                        "sourceZoom": z,
                        "sourceTileX": tile_x,
                        "sourceTileY": tile_y,
                        "sourceTileFeatureIndex": index,
                        "sourceEpoch": SOURCE_EPOCH,
                        "sourceRole": "current_geometry_delta_not_flow_topology",
                    })
                    output_feature = {
                        "type": "Feature",
                        "id": f"GSI-Z{z}-{tile_x}-{tile_y}-{layer_name}-{index}",
                        "properties": props,
                        "geometry": geometry,
                    }
                    combined_features.append(output_feature)
                    if layer_name == "river":
                        river_features.append(output_feature)
                    else:
                        waterarea_features.append(output_feature)
                    tile_feature_count += 1
                    layer_counts[layer_name] += 1
                    ftcode_counts[f"{layer_name}:{props.get('ftCode')}"] += 1
                    geometry_counts[geometry["type"]] += 1
        except Exception as exc:
            parse_errors.append({"tile": path.name, "error": repr(exc)})
        tile_rows.append({
            "tile": path.name,
            "sizeBytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "retainedWaterFeatureCount": tile_feature_count,
        })
        if i % 100 == 0 or i == len(downloaded_paths):
            print(f"Decoded {i}/{len(downloaded_paths)}", flush=True)

    write_geojson_gz(root / "GSI_CURRENT_WATER_Z14_SEGMENTS.geojson.gz", combined_features)
    write_geojson_gz(root / "GSI_CURRENT_RIVER_Z14_SEGMENTS.geojson.gz", river_features)
    write_geojson_gz(root / "GSI_CURRENT_WATERAREA_Z14_SEGMENTS.geojson.gz", waterarea_features)

    with (root / "TILE_INVENTORY.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tile", "sizeBytes", "sha256", "retainedWaterFeatureCount"])
        writer.writeheader()
        writer.writerows(tile_rows)

    status_counts = Counter(r["status"] for r in statuses)
    summary = {
        "buildId": BUILD_ID,
        "sourceEpoch": SOURCE_EPOCH,
        "zoom": z,
        "studyBboxWgs84": BBOX,
        "requestedTileCount": len(requests_list),
        "downloadStatusCounts": dict(status_counts),
        "decodedTileCount": len(downloaded_paths),
        "parseErrorCount": len(parse_errors),
        "parseErrors": parse_errors[:50],
        "retainedFeatureCount": len(combined_features),
        "retainedRiverFeatureCount": len(river_features),
        "retainedWaterareaFeatureCount": len(waterarea_features),
        "layerCounts": dict(layer_counts),
        "ftCodeCounts": dict(ftcode_counts),
        "geometryTypeCounts": dict(geometry_counts),
        "interpretationBoundary": [
            "GSI geometry is used as a 2026 current-geometry delta layer.",
            "W05 topology and direction are not overwritten.",
            "Absence at zoom 14 is NOT interpreted as river removal and triggers targeted zoom-16 review where material.",
        ],
    }
    (root / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "PARSE_ERRORS.json").write_text(json.dumps(parse_errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if parse_errors:
        raise SystemExit(f"GSI tile parse errors: {len(parse_errors)}")
    if len(river_features) == 0:
        raise SystemExit("No GSI river features retained")

    for path in downloaded_paths:
        path.unlink()
    tiles_dir.rmdir()
    inventory = []
    for path in sorted(p for p in root.iterdir() if p.is_file()):
        inventory.append({"file": path.name, "sizeBytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    with (root / "FILE_INVENTORY.json").open("w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)
    with (root / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for item in inventory:
            f.write(f"{item['sha256']}  {item['file']}\n")


if __name__ == "__main__":
    main()
