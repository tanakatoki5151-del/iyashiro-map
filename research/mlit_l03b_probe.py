#!/usr/bin/env python3
"""Probe the official MLIT L03-b catalogue and download the eight V10 source ZIPs.

This script is deliberately evidence-first:
- it preserves the raw catalogue and relevant JavaScript;
- it records every candidate URL and HTTP response;
- it only marks a dataset downloaded when the bytes are a valid ZIP;
- it never converts land-use coverage into negative major-history evidence.
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

CATALOG = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-L03-b.html"
YEARS = ("76", "87", "91", "97")
MESHES = ("5239", "5339")
TARGETS = [f"L03-b-{y}_{m}_GML.zip" for y in YEARS for m in MESHES]
OUT = Path(os.environ.get("OUT_DIR", "out"))
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


def request(url: str, *, method: str = "GET", data=None, referer: str | None = None, stream: bool = False):
    headers = {"Referer": referer} if referer else None
    return SESSION.request(method, url, data=data, headers=headers, timeout=90, allow_redirects=True, stream=stream)


def unique(xs: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(x for x in xs if x))


def candidate_urls(filename: str, catalog_html: str, soup: BeautifulSoup, script_texts: list[tuple[str, str]]) -> list[str]:
    candidates: list[str] = []

    # Absolute and relative URLs visible anywhere in the raw catalogue/JS.
    blobs = [catalog_html, *(text for _, text in script_texts)]
    for blob in blobs:
        for match in re.findall(r"(?:https?://[^\"'<>\s]+|[./A-Za-z0-9_?=&%:-]+\.zip(?:\?[^\"'<>\s]*)?)", blob):
            decoded = html.unescape(match).replace("\\/", "/")
            if filename in decoded:
                candidates.append(urllib.parse.urljoin(CATALOG, decoded))

    # DOM attributes around the filename may carry onclick, data-url, value, action, etc.
    text_node = soup.find(string=lambda s: isinstance(s, str) and filename in s)
    if text_node:
        node = text_node.parent
        for _ in range(5):
            if node is None:
                break
            for tag in [node, *node.find_all(True)]:
                for key, value in tag.attrs.items():
                    values = value if isinstance(value, list) else [str(value)]
                    for item in values:
                        item = html.unescape(item)
                        if filename in item:
                            for token in re.findall(r"https?://[^\"'<>\s]+|[./A-Za-z0-9_?=&%:-]*" + re.escape(filename) + r"(?:\?[^\"'<>\s]*)?", item):
                                candidates.append(urllib.parse.urljoin(CATALOG, token))
            node = node.parent

    # Known historical/current MLIT path patterns. They are probed, never assumed.
    y = filename.split("-")[2].split("_")[0]
    patterns = [
        f"https://nlftp.mlit.go.jp/ksj/gml/data/L03-b/L03-b-{y}/{filename}",
        f"https://nlftp.mlit.go.jp/ksj/gml/data/L03-b/{filename}",
        f"https://nlftp.mlit.go.jp/ksj/gml/data/L03-b/L03-b-{y}/{filename.replace('_GML', '')}",
        f"https://nlftp.mlit.go.jp/ksj/jpgis/datalist/{filename}",
        f"https://nlftp.mlit.go.jp/ksj/gml/data/{filename}",
        f"https://nlftp.mlit.go.jp/ksj/gml/data/L03-b/{y}/{filename}",
    ]
    candidates.extend(patterns)
    return unique(candidates)


def download_candidate(url: str, filename: str) -> dict:
    record = {"url": url, "filename": filename}
    try:
        r = request(url, referer=CATALOG, stream=True)
        record.update(
            {
                "status": r.status_code,
                "finalUrl": r.url,
                "contentType": r.headers.get("content-type"),
                "contentLengthHeader": r.headers.get("content-length"),
            }
        )
        temp = ZIP_DIR / (filename + ".part")
        with temp.open("wb") as f:
            size = 0
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
                    # Protect the runner from accidentally downloading unrelated huge files.
                    if size > 80 * 1024 * 1024:
                        raise RuntimeError("candidate exceeded 80 MiB guard")
        record["bytes"] = temp.stat().st_size
        record["zipValid"] = zipfile.is_zipfile(temp)
        if r.ok and record["zipValid"]:
            dest = ZIP_DIR / filename
            temp.replace(dest)
            record["savedAs"] = str(dest)
            record["sha256"] = sha256(dest)
            with zipfile.ZipFile(dest) as zf:
                record["zipMembers"] = zf.namelist()[:30]
            return record
        temp.unlink(missing_ok=True)
    except Exception as exc:  # evidence is retained in the report
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    ZIP_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "catalog": CATALOG,
        "targets": TARGETS,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "catalogFetch": {},
        "scripts": [],
        "targetContext": {},
        "attempts": {},
        "downloads": {},
        "qualityRule": "Historic land-use coverage is not negative evidence for major history.",
    }

    r = request(CATALOG)
    catalog_bytes = r.content
    catalog_html = r.text
    (RAW / "catalog.html").write_bytes(catalog_bytes)
    report["catalogFetch"] = {
        "status": r.status_code,
        "finalUrl": r.url,
        "bytes": len(catalog_bytes),
        "sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "contentType": r.headers.get("content-type"),
    }
    r.raise_for_status()

    soup = BeautifulSoup(catalog_html, "html.parser")
    script_texts: list[tuple[str, str]] = []
    for i, script in enumerate(soup.find_all("script")):
        src = script.get("src")
        if src:
            url = urllib.parse.urljoin(CATALOG, src)
            try:
                sr = request(url, referer=CATALOG)
                text = sr.text
                name = f"script-{i:03d}-{Path(urllib.parse.urlparse(url).path).name or 'inline.js'}"
                (RAW / name).write_text(text, encoding="utf-8", errors="replace")
                script_texts.append((url, text))
                report["scripts"].append({"url": url, "status": sr.status_code, "bytes": len(sr.content), "savedAs": name})
            except Exception as exc:
                report["scripts"].append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
        else:
            text = script.get_text("\n")
            if text.strip():
                name = f"script-{i:03d}-inline.js"
                (RAW / name).write_text(text, encoding="utf-8")
                script_texts.append((CATALOG + f"#inline-{i}", text))

    # Preserve local DOM/HTML context for every target.
    for filename in TARGETS:
        text_node = soup.find(string=lambda s: isinstance(s, str) and filename in s)
        context = None
        if text_node:
            node = text_node.parent
            for _ in range(3):
                if node and node.parent:
                    node = node.parent
            context = str(node) if node else str(text_node.parent)
        report["targetContext"][filename] = context
        if context:
            (RAW / f"context-{filename}.html").write_text(context, encoding="utf-8")

    # First attempt direct candidates.
    for filename in TARGETS:
        attempts = []
        for url in candidate_urls(filename, catalog_html, soup, script_texts):
            rec = download_candidate(url, filename)
            attempts.append(rec)
            if rec.get("zipValid"):
                report["downloads"][filename] = rec
                break
        report["attempts"][filename] = attempts

    # Produce compact summaries and checksums.
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
        f"downloaded={len(downloaded)}/8\nmissing={','.join(report['missingTargets'])}\n",
        encoding="utf-8",
    )
    print(json.dumps({k: report[k] for k in ("downloadedCount", "downloadedTargets", "missingTargets")}, ensure_ascii=False, indent=2))
    return 0 if len(downloaded) == len(TARGETS) else 2


if __name__ == "__main__":
    sys.exit(main())
