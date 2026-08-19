#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import requests

PID = "966080"
MANIFEST = f"https://dl.ndl.go.jp/api/iiif/{PID}/manifest.json"
OUT = Path("out-ndl-honjo-1912")
OUT.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "iyashiro-map historical-boundary-research/1.1"})


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
    return resource.get("@id") or resource.get("id")


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
        for x in rng.get(key) or []:
            if isinstance(x, str):
                range_refs.append(x)
            elif isinstance(x, dict):
                ref = x.get("@id") or x.get("id")
                if ref:
                    range_refs.append(ref)
honjo_indices = sorted({canvas_by_id[x] for x in range_refs if x in canvas_by_id})

# Visual audit of run 31682785600 falsified the earlier linear-offset hypothesis:
# scans 168-169 show Honjo map numbers about 15-16, not 4-5.
# The manifest's Honjo section begins at one-based scan 144 (section title), so acquire
# the complete early Honjo window 144-180 and identify map 4-5 visually from source images.
verification_one_based = set(range(144, 181))
for idx in honjo_indices[:25]:
    verification_one_based.add(idx + 1)

downloaded, errors = [], []
for one_based in sorted(verification_one_based):
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
        rec.update({"status": ir.status_code, "contentType": ir.headers.get("content-type"),
                    "bytes": len(ir.content), "sha256": sha256(ir.content)})
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
    "verificationWindowOneBased": sorted(verification_one_based),
    "priorHypothesisAudit": {
        "hypothesis": "Honjo map 4-5 near scans 168-169",
        "result": "falsified_by_visual_source_review",
        "observed": "scans 168-169 contain Honjo map numbers around 15-16",
        "action": "acquire complete early Honjo section and visually identify maps 4-5",
    },
    "downloaded": downloaded,
    "errors": errors,
    "rights": "NDL record is Internet-public with copyright information pdm. Preserve NDL provenance; source images alone do not establish modern boundary geometry.",
}
(OUT / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
print(json.dumps({"canvasCount": len(canvases), "honjoRangeLabels": report["honjoRangeLabels"],
                  "downloadedCount": len(downloaded), "errorCount": len(errors)}, ensure_ascii=False))
