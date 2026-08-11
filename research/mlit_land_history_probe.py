#!/usr/bin/env python3
"""Acquire the 15 official MLIT Land History Survey GIS ZIPs required by V10.

Targets:
- five historic land-use polygon ZIPs,
- five disaster-history ZIPs,
- five landform-classification ZIPs.

The script preserves source pages/JavaScript, records every attempted URL, and
accepts a download only when it is a valid ZIP. It does not interpret any GIS
layer as evidence that a major incident did not occur.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

BASE = "https://nlftp.mlit.go.jp"
PAGES = [
    "https://nlftp.mlit.go.jp/kokjo/inspect/landclassification/land/tochi_riyou.html",
    "https://nlftp.mlit.go.jp/kokjo/inspect/landclassification/land/chikei_bunrui.html",
    "https://nlftp.mlit.go.jp/kokjo/inspect/landclassification/download.html",
]
MAPS = ("533946", "533926", "533944", "533924", "533904")
KINDS = ("landuse", "disaster", "landform")
TARGETS = [f"{m}_{k}.zip" for k in KINDS for m in MAPS]
OUT = Path(os.environ.get("OUT_DIR", "out-land-history"))
RAW = OUT / "raw"
ZIP_DIR = OUT / "zips"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (compatible; iyashiro-map-research/1.0; +https://github.com/tanakatoki5151-del/iyashiro-map)",
        "Accept-Language": "ja,en;q=0.8",
    }
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique(xs: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(x for x in xs if x))


def get(url: str, *, referer: str | None = None, stream: bool = False):
    headers = {"Referer": referer} if referer else None
    return SESSION.get(url, headers=headers, timeout=120, allow_redirects=True, stream=stream)


def candidate_urls(filename: str, page_records: list[dict], scripts: list[tuple[str, str]]) -> list[str]:
    candidates: list[str] = []
    blobs = [(p["url"], p["html"]) for p in page_records] + scripts
    for base_url, blob in blobs:
        for match in re.findall(r"(?:https?://[^\"'<>\s]+|[./A-Za-z0-9_?=&%:@~-]+\.zip(?:\?[^\"'<>\s]*)?)", blob):
            decoded = html.unescape(match).replace("\\/", "/")
            if filename in decoded:
                candidates.append(urllib.parse.urljoin(base_url, decoded))

    # Candidate paths observed across MLIT's land-classification site generations.
    stem = filename[:-4]
    patterns = [
        f"{BASE}/kokjo/inspect/landclassification/download/{filename}",
        f"{BASE}/kokjo/inspect/landclassification/data/{filename}",
        f"{BASE}/kokjo/inspect/landclassification/land/{filename}",
        f"{BASE}/kokjo/inspect/landclassification/zip/{filename}",
        f"{BASE}/kokjo/inspect/landclassification/{filename}",
        f"{BASE}/kokjo/inspect/landclassification/download.php?file={urllib.parse.quote(filename)}",
        f"{BASE}/kokjo/inspect/landclassification/download.php?filename={urllib.parse.quote(filename)}",
        f"{BASE}/kokjo/inspect/landclassification/download.php?name={urllib.parse.quote(stem)}",
        f"{BASE}/ksj/gml/data/landclassification/{filename}",
    ]
    candidates.extend(patterns)
    return unique(candidates)


def download_candidate(url: str, filename: str, referer: str) -> dict:
    rec = {"url": url, "filename": filename}
    temp = ZIP_DIR / f"{filename}.part"
    try:
        r = get(url, referer=referer, stream=True)
        rec.update(
            {
                "status": r.status_code,
                "finalUrl": r.url,
                "contentType": r.headers.get("content-type"),
                "contentLengthHeader": r.headers.get("content-length"),
            }
        )
        size = 0
        with temp.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                size += len(chunk)
                if size > 600 * 1024 * 1024:
                    raise RuntimeError("candidate exceeded 600 MiB guard")
        rec["bytes"] = temp.stat().st_size
        rec["zipValid"] = zipfile.is_zipfile(temp)
        if r.ok and rec["zipValid"]:
            dest = ZIP_DIR / filename
            temp.replace(dest)
            rec["savedAs"] = str(dest)
            rec["sha256"] = sha256(dest)
            with zipfile.ZipFile(dest) as zf:
                rec["zipMembers"] = zf.namelist()[:80]
            return rec
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        temp.unlink(missing_ok=True)
    return rec


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    ZIP_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pages": [],
        "scripts": [],
        "targets": TARGETS,
        "attempts": {},
        "downloads": {},
        "qualityRules": [
            "These layers are context/audit layers unless a separate scoring policy explicitly approves them.",
            "Coverage is not negative evidence for major history.",
            "Historical land-use polygons must retain source vintage and provenance.",
            "Disaster history must not be double-counted with current hazards or major-fatality registries.",
        ],
    }

    pages: list[dict] = []
    scripts: list[tuple[str, str]] = []
    seen_scripts: set[str] = set()
    for i, url in enumerate(PAGES):
        try:
            r = get(url)
            raw_name = f"page-{i:02d}-{Path(urllib.parse.urlparse(url).path).name}"
            (RAW / raw_name).write_bytes(r.content)
            page = {
                "url": url,
                "finalUrl": r.url,
                "status": r.status_code,
                "bytes": len(r.content),
                "sha256": hashlib.sha256(r.content).hexdigest(),
                "savedAs": raw_name,
                "html": r.text,
            }
            pages.append(page)
            report["pages"].append({k: v for k, v in page.items() if k != "html"})
            soup = BeautifulSoup(r.text, "html.parser")
            for j, tag in enumerate(soup.find_all("script")):
                src = tag.get("src")
                if src:
                    script_url = urllib.parse.urljoin(r.url, src)
                    if script_url in seen_scripts:
                        continue
                    seen_scripts.add(script_url)
                    try:
                        sr = get(script_url, referer=r.url)
                        text = sr.text
                        name = f"script-{len(scripts):03d}-{Path(urllib.parse.urlparse(script_url).path).name or 'script.js'}"
                        (RAW / name).write_text(text, encoding="utf-8", errors="replace")
                        scripts.append((script_url, text))
                        report["scripts"].append({"url": script_url, "status": sr.status_code, "bytes": len(sr.content), "savedAs": name})
                    except Exception as exc:
                        report["scripts"].append({"url": script_url, "error": f"{type(exc).__name__}: {exc}"})
                else:
                    text = tag.get_text("\n")
                    if text.strip():
                        scripts.append((r.url + f"#inline-{j}", text))
        except Exception as exc:
            report["pages"].append({"url": url, "error": f"{type(exc).__name__}: {exc}"})

    for filename in TARGETS:
        attempts: list[dict] = []
        referer = next((p["url"] for p in pages if filename in p["html"]), PAGES[2])
        for url in candidate_urls(filename, pages, scripts):
            rec = download_candidate(url, filename, referer)
            attempts.append(rec)
            if rec.get("zipValid"):
                report["downloads"][filename] = rec
                break
        report["attempts"][filename] = attempts

    downloaded = sorted(report["downloads"])
    report["downloadedCount"] = len(downloaded)
    report["downloadedTargets"] = downloaded
    report["missingTargets"] = [x for x in TARGETS if x not in report["downloads"]]
    report["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (OUT / "probe-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for path in sorted(ZIP_DIR.glob("*.zip")):
            f.write(f"{sha256(path)}  {path.name}\n")
    (OUT / "STATUS.txt").write_text(
        f"downloaded={len(downloaded)}/{len(TARGETS)}\nmissing={','.join(report['missingTargets'])}\n",
        encoding="utf-8",
    )
    print(json.dumps({"downloadedCount": len(downloaded), "missingTargets": report["missingTargets"]}, ensure_ascii=False, indent=2))
    return 0 if len(downloaded) == len(TARGETS) else 2


if __name__ == "__main__":
    sys.exit(main())
