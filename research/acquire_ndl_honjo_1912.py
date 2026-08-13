#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

PID = "966080"
MANIFEST = f"https://dl.ndl.go.jp/api/iiif/{PID}/manifest.json"
OUT = Path("out-ndl-honjo-1912")
OUT.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "iyashiro-map historical-boundary-research/1.0"})


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-zぁ-んァ-ン一-龥._-]+", "_", value or "")
    return value.strip("_")[:80] or "unlabelled"


def label_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "@value" in value:
            return str(value["@value"])
        for v in value.values():
            if isinstance(v, list) and v:
                return str(v[0])
            if isinstance(v, str):
                return v
    return str(value or "")


def resource_image_url(canvas: dict, width: int = 2600) -> str | None:
    images = canvas.get("images") or []
    if not images:
        return None
    resource = (images[0] or {}).get("resource") or {}
    service = resource.get("service")
    if isinstance(service, list):
        service = service[0] if service else None
    if isinstance(service, dict):
        sid = service.get("@id") or service.get("id")
        if sid:
            return sid.rstrip("/") + f"/full/{width},/0/default.jpg"
    rid = resource.get("@id") or resource.get("id")
    return rid


def walk_ranges(node, found: list[dict]) -> None:
    if isinstance(node, list):
        for x in node:
            walk_ranges(x, found)
        return
    if not isinstance(node, dict):
        return
    lab = label_text(node.get("label"))
    if "本所" in lab:
        found.append(node)
    for key in ("ranges", "members"):
        walk_ranges(node.get(key), found)


r = session.get(MANIFEST, timeout=90)
r.raise_for_status()
manifest_bytes = r.content
(OUT / "manifest.json").write_bytes(manifest_bytes)
manifest = r.json()

canvases = (((manifest.get("sequences") or [{}])[0]).get("canvases") or [])
canvas_by_id = {(c.get("@id") or c.get("id")): i for i, c in enumerate(canvases)}

honjo_ranges: list[dict] = []
walk_ranges(manifest.get("structures") or [], honjo_ranges)

range_refs: list[str] = []
for rng in honjo_ranges:
    for key in ("canvases", "members"):
        vals = rng.get(key) or []
        for x in vals:
            if isinstance(x, str):
                range_refs.append(x)
            elif isinstance(x, dict):
                ref = x.get("@id") or x.get("id")
                if ref:
                    range_refs.append(ref)

honjo_indices = sorted({canvas_by_id[x] for x in range_refs if x in canvas_by_id})

# NDL scan 231 is independently transcribed as Honjo map 67 in prior research.
# Therefore Honjo maps 4-5 are expected near scans 168-169 if map numbering is contiguous.
# Download a deliberately wide verification window and any manifest range hits.
estimated_one_based = set(range(160, 181))
for idx in honjo_indices[:25]:
    estimated_one_based.add(idx + 1)

downloaded = []
errors = []
for one_based in sorted(estimated_one_based):
    idx = one_based - 1
    if idx < 0 or idx >= len(canvases):
        continue
    canvas = canvases[idx]
    label = label_text(canvas.get("label"))
    url = resource_image_url(canvas)
    rec = {
        "scanOneBased": one_based,
        "canvasIndexZeroBased": idx,
        "label": label,
        "canvasId": canvas.get("@id") or canvas.get("id"),
        "imageUrl": url,
    }
    if not url:
        rec["error"] = "no_image_url"
        errors.append(rec)
        continue
    try:
        ir = session.get(url, timeout=120)
        rec.update({
            "status": ir.status_code,
            "contentType": ir.headers.get("content-type"),
            "bytes": len(ir.content),
            "sha256": sha256(ir.content),
        })
        if ir.ok and (ir.headers.get("content-type") or "").lower().startswith("image/"):
            fn = f"scan-{one_based:03d}-{safe_name(label)}.jpg"
            (OUT / fn).write_bytes(ir.content)
            rec["savedAs"] = fn
            downloaded.append(rec)
        else:
            errors.append(rec)
    except Exception as e:
        rec["error"] = repr(e)
        errors.append(rec)

report = {
    "pid": PID,
    "manifestUrl": MANIFEST,
    "manifestSha256": sha256(manifest_bytes),
    "canvasCount": len(canvases),
    "honjoRangeLabels": [label_text(x.get("label")) for x in honjo_ranges],
    "honjoRangeCanvasIndicesZeroBased": honjo_indices,
    "verificationWindowOneBased": sorted(estimated_one_based),
    "targetHypothesis": {
        "honjoMap4": "near NDL scan 168",
        "honjoMap5": "near NDL scan 169",
        "basis": "independent prior transcription: Honjo map 67 = NDL scan 231; verify visually before use",
    },
    "downloaded": downloaded,
    "errors": errors,
    "rights": "NDL record marks online access as Internet-public and copyright information as pdm. Preserve NDL provenance; do not infer boundary from this script alone.",
}
(OUT / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
print(json.dumps({
    "canvasCount": len(canvases),
    "honjoRangeLabels": report["honjoRangeLabels"],
    "downloadedCount": len(downloaded),
    "errorCount": len(errors),
}, ensure_ascii=False))
