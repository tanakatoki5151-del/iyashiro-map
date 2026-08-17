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

SOURCE_EPOCH = "GSI_Vector_updated_2026-04-01"


def tile_point_to_lonlat(tile_x: int, tile_y: int, extent: int, point, z: int):
    px, py = point
    n = 2 ** z
    x_norm = (tile_x + float(px) / extent) / n
    y_norm = (tile_y + (extent - float(py)) / extent) / n
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


def download_tile(item, out_dir: Path):
    z, x, y = map(int, item)
    filename = f"{z}_{x}_{y}.pbf"
    url = f"https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/{z}/{x}/{y}.pbf"
    path = out_dir / filename
    headers = {"User-Agent": "Mozilla/5.0 MEGA06R targeted research acquisition"}
    last_error = None
    for attempt in range(1, 6):
        try:
            response = requests.get(url, headers=headers, timeout=(30, 240))
            if response.status_code == 404:
                return {"status": "MISSING_404", "z": z, "x": x, "y": y, "file": filename, "url": url, "sizeBytes": 0, "error": None}
            response.raise_for_status()
            path.write_bytes(response.content)
            return {"status": "OK", "z": z, "x": x, "y": y, "file": filename, "url": url, "sizeBytes": len(response.content), "sha256": hashlib.sha256(response.content).hexdigest(), "error": None}
        except Exception as exc:
            last_error = repr(exc)
            time.sleep(min(attempt * 2, 10))
    return {"status": "FAILED", "z": z, "x": x, "y": y, "file": filename, "url": url, "sizeBytes": 0, "error": last_error}


def write_geojson_gz(path: Path, features: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--build-id", required=True)
    args = ap.parse_args()

    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    tiles = queue["tiles"]
    if len(tiles) != int(queue["tileCount"]):
        raise RuntimeError("Queue tile count mismatch")
    root = args.out
    raw_dir = root / "raw_tiles"
    root.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    statuses = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_tile, tile, raw_dir): tile for tile in tiles}
        for i, future in enumerate(as_completed(futures), start=1):
            statuses.append(future.result())
            if i % 100 == 0 or i == len(futures):
                print(f"Downloaded {i}/{len(futures)}", flush=True)
    statuses.sort(key=lambda r: (r["z"], r["x"], r["y"]))
    with (root / "DOWNLOAD_STATUS.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["status", "z", "x", "y", "file", "url", "sizeBytes", "sha256", "error"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(statuses)
    failed = [r for r in statuses if r["status"] == "FAILED"]
    if failed:
        raise SystemExit(f"Failed downloads: {len(failed)}")

    combined = []
    rivers = []
    waterareas = []
    inventory = []
    parse_errors = []
    layer_counts = Counter()
    ftcode_counts = Counter()
    geom_counts = Counter()

    paths = sorted(raw_dir.glob("*.pbf"))
    for i, path in enumerate(paths, start=1):
        z_s, x_s, y_s = path.stem.split("_")
        z, x, y = int(z_s), int(x_s), int(y_s)
        raw = path.read_bytes()
        retained = 0
        try:
            decoded = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": False})
            for layer_name in ("river", "waterarea"):
                layer = decoded.get(layer_name)
                if not layer:
                    continue
                extent = int(layer.get("extent") or 4096)
                for index, feature in enumerate(layer.get("features") or []):
                    geometry = transform_geometry(feature.get("geometry") or {}, x, y, extent, z)
                    props = dict(feature.get("properties") or {})
                    props.update({
                        "sourceLayer": layer_name,
                        "sourceZoom": z,
                        "sourceTileX": x,
                        "sourceTileY": y,
                        "sourceTileFeatureIndex": index,
                        "sourceEpoch": SOURCE_EPOCH,
                        "sourceRole": "targeted_high_resolution_current_geometry_review",
                    })
                    out = {"type": "Feature", "id": f"GSI-Z{z}-{x}-{y}-{layer_name}-{index}", "properties": props, "geometry": geometry}
                    combined.append(out)
                    (rivers if layer_name == "river" else waterareas).append(out)
                    retained += 1
                    layer_counts[layer_name] += 1
                    ftcode_counts[f"{layer_name}:{props.get('ftCode')}"] += 1
                    geom_counts[geometry["type"]] += 1
        except Exception as exc:
            parse_errors.append({"tile": path.name, "error": repr(exc)})
        inventory.append({"tile": path.name, "sizeBytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "retainedWaterFeatureCount": retained})
        if i % 100 == 0 or i == len(paths):
            print(f"Decoded {i}/{len(paths)}", flush=True)

    write_geojson_gz(root / "GSI_TARGETED_WATER_SEGMENTS.geojson.gz", combined)
    write_geojson_gz(root / "GSI_TARGETED_RIVER_SEGMENTS.geojson.gz", rivers)
    write_geojson_gz(root / "GSI_TARGETED_WATERAREA_SEGMENTS.geojson.gz", waterareas)
    with (root / "TILE_INVENTORY.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tile", "sizeBytes", "sha256", "retainedWaterFeatureCount"])
        writer.writeheader(); writer.writerows(inventory)

    status_counts = Counter(r["status"] for r in statuses)
    summary = {
        "buildId": args.build_id,
        "sourceQueueBuildId": queue.get("buildId"),
        "sourceEpoch": SOURCE_EPOCH,
        "requestedTileCount": len(tiles),
        "downloadStatusCounts": dict(status_counts),
        "decodedTileCount": len(paths),
        "parseErrorCount": len(parse_errors),
        "retainedFeatureCount": len(combined),
        "retainedRiverFeatureCount": len(rivers),
        "retainedWaterareaFeatureCount": len(waterareas),
        "layerCounts": dict(layer_counts),
        "ftCodeCounts": dict(ftcode_counts),
        "geometryTypeCounts": dict(geom_counts),
        "interpretationBoundary": [
            "Targeted z16 review only; it is not full-area coverage.",
            "W05 topology/direction and GSI z14 all-area geometry remain separate source epochs.",
            "Non-observation is not river removal and may require culvert or other current-source review.",
        ],
    }
    (root / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "QUEUE.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "PARSE_ERRORS.json").write_text(json.dumps(parse_errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if parse_errors or not rivers:
        raise SystemExit(f"parse_errors={len(parse_errors)}, rivers={len(rivers)}")

    for path in paths:
        path.unlink()
    raw_dir.rmdir()
    file_rows = []
    for path in sorted(p for p in root.iterdir() if p.is_file()):
        file_rows.append({"file": path.name, "sizeBytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (root / "FILE_INVENTORY.json").write_text(json.dumps(file_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (root / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for row in file_rows:
            f.write(f"{row['sha256']}  {row['file']}\n")


if __name__ == "__main__":
    main()
