#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import mapbox_vector_tile

OUT = Path("gsi_probe")
OUT.mkdir(parents=True, exist_ok=True)
Z = 14
SAMPLES = {
    "tokyo_central": (35.6812, 139.7671),
    "tokyo_west": (35.6896, 139.6917),
    "kawasaki": (35.5308, 139.7029),
    "yokohama": (35.4437, 139.6380),
    "tama_river": (35.5630, 139.6720),
}


def tile_xy(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "RYUMYAK-MEGA06R-R2/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def main() -> None:
    report: dict[str, object] = {"zoom": Z, "samples": {}, "layerSummary": {}}
    layer_counts: Counter[str] = Counter()
    layer_geometry: dict[str, Counter[str]] = defaultdict(Counter)
    layer_property_keys: dict[str, Counter[str]] = defaultdict(Counter)
    layer_ft_codes: dict[str, Counter[str]] = defaultdict(Counter)

    for name, (lat, lon) in SAMPLES.items():
        x, y = tile_xy(lat, lon, Z)
        url = f"https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/{Z}/{x}/{y}.pbf"
        raw = fetch(url)
        decoded = mapbox_vector_tile.decode(raw)
        sample_layers = {}
        for layer_name, layer in decoded.items():
            features = layer.get("features", [])
            layer_counts[layer_name] += len(features)
            examples = []
            for feature in features:
                geometry_type = feature.get("geometry", {}).get("type", "unknown")
                layer_geometry[layer_name][geometry_type] += 1
                props = feature.get("properties", {})
                for key in props:
                    layer_property_keys[layer_name][key] += 1
                if "ftCode" in props:
                    layer_ft_codes[layer_name][str(props["ftCode"])] += 1
                if len(examples) < 5:
                    examples.append({
                        "geometryType": geometry_type,
                        "properties": props,
                    })
            sample_layers[layer_name] = {
                "featureCount": len(features),
                "examples": examples,
            }
        report["samples"][name] = {
            "lat": lat,
            "lon": lon,
            "x": x,
            "y": y,
            "url": url,
            "bytes": len(raw),
            "layers": sample_layers,
        }

    for layer_name in sorted(layer_counts):
        report["layerSummary"][layer_name] = {
            "featureCountAcrossSamples": layer_counts[layer_name],
            "geometryTypes": dict(layer_geometry[layer_name]),
            "propertyKeys": [key for key, _ in layer_property_keys[layer_name].most_common()],
            "ftCodeCounts": dict(layer_ft_codes[layer_name].most_common(100)),
        }

    (OUT / "gsi_vector_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["layerSummary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
