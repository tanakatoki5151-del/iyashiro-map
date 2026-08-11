#!/usr/bin/env python3
"""Acquire the public 1862 Tokyo Asakusa map from David Rumsey / UC Berkeley.

Target record:
- 東京都 浅草繪圖 (Tokyo Asakusa Map)
- list no. 16147.026
- image no. 16147026.jp2

The script follows public download and IIIF-like endpoints, verifies image bytes,
records provenance and creates a lower-resolution research preview. It does not
claim that any illustrated boundary is automatically the Kozukappara legal site.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image

OUT = Path("out-rumsey-asakusa-1862")
OUT.mkdir(parents=True, exist_ok=True)

RECORD_URL = "https://www.davidrumsey.com/luna/servlet/detail/RUMSEY~8~1~364804~90132199%3A---Tokyo-Asakusa-Map-"
DOWNLOAD_URL = "https://www.davidrumsey.com/rumsey/download.pl?image=/213/16147026.jp2"
IIIF_CANDIDATES = [
    "https://www.davidrumsey.com/luna/servlet/iiif/RUMSEY~8~1~364804~90132199/manifest",
    "https://www.davidrumsey.com/luna/servlet/iiif/m/RUMSEY~8~1~364804~90132199/manifest",
    "https://www.davidrumsey.com/luna/servlet/iiif/RUMSEY~8~1~364804~90132199/info.json",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; iyashiro-map historical research)",
    "Accept-Language": "ja,en;q=0.8",
})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, path: Path, referer: str | None = None, max_bytes: int = 1_500_000_000) -> dict:
    headers = {"Referer": referer} if referer else None
    r = SESSION.get(url, headers=headers, stream=True, timeout=180, allow_redirects=True)
    row = {
        "url": url,
        "finalUrl": r.url,
        "status": r.status_code,
        "contentType": r.headers.get("content-type"),
        "contentLengthHeader": r.headers.get("content-length"),
    }
    size = 0
    with path.open("wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            size += len(chunk)
            if size > max_bytes:
                raise RuntimeError("download exceeds size guard")
    row["bytes"] = size
    row["savedAs"] = str(path.relative_to(OUT))
    row["sha256"] = sha256(path)
    return row


def main() -> None:
    report: dict = {"record": {}, "iiif": [], "downloads": [], "errors": []}
    try:
        record_path = OUT / "record.html"
        report["record"] = fetch(RECORD_URL, record_path)
    except Exception as exc:
        report["errors"].append({"stage": "record", "error": f"{type(exc).__name__}: {exc}"})

    for i, url in enumerate(IIIF_CANDIDATES, 1):
        try:
            path = OUT / f"iiif-{i}.bin"
            row = fetch(url, path, referer=RECORD_URL, max_bytes=50_000_000)
            # Rename JSON responses for readability.
            if "json" in (row.get("contentType") or ""):
                new_path = path.with_suffix(".json")
                path.rename(new_path)
                row["savedAs"] = str(new_path.relative_to(OUT))
                row["sha256"] = sha256(new_path)
            report["iiif"].append(row)
        except Exception as exc:
            report["iiif"].append({"url": url, "error": f"{type(exc).__name__}: {exc}"})

    jp2 = OUT / "16147026_asakusa_1862.jp2"
    try:
        row = fetch(DOWNLOAD_URL, jp2, referer=RECORD_URL)
        report["downloads"].append(row)
    except Exception as exc:
        report["errors"].append({"stage": "jp2", "error": f"{type(exc).__name__}: {exc}"})

    # Discover image URLs in any manifest or record response.
    discovered: list[str] = []
    for path in OUT.glob("*"):
        if path.suffix.lower() not in {".html", ".json", ".bin"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        discovered.extend(re.findall(r'https?://[^"\'<>\\ ]+(?:\.jp2|\.jpg|\.jpeg|\.png|info\.json|manifest)', text, flags=re.I))
    discovered = list(dict.fromkeys(discovered))
    (OUT / "discovered-image-urls.json").write_text(json.dumps(discovered, ensure_ascii=False, indent=2), encoding="utf-8")

    if jp2.exists() and jp2.stat().st_size > 1024:
        try:
            with Image.open(jp2) as im:
                metadata = {
                    "format": im.format,
                    "mode": im.mode,
                    "width": im.width,
                    "height": im.height,
                    "bytes": jp2.stat().st_size,
                    "sha256": sha256(jp2),
                }
                # Produce a practical visual preview while preserving the JP2 original.
                preview = im.convert("RGB")
                preview.thumbnail((6000, 6000))
                preview_path = OUT / "asakusa_1862_preview.jpg"
                preview.save(preview_path, quality=92)
                metadata["preview"] = {
                    "width": preview.width,
                    "height": preview.height,
                    "bytes": preview_path.stat().st_size,
                    "sha256": sha256(preview_path),
                }
                (OUT / "image-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            report["errors"].append({"stage": "decode", "error": f"{type(exc).__name__}: {exc}"})

    report["qualityRule"] = (
        "The 1862 map is a historical cartographic source. It must be georeferenced "
        "against independent anchors and combined with official dimensions and modern "
        "records before any Kozukappara review polygon is generated. No scoring change "
        "is allowed from acquisition alone."
    )
    (OUT / "REPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and path.name != "SHA256SUMS.txt":
                f.write(f"{sha256(path)}  {path.name}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
