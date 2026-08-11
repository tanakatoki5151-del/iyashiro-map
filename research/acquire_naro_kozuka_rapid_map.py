#!/usr/bin/env python3
"""Acquire a reproducible NARO Rapid Survey Map view around Kozukappara.

The script opens the official NARO Historical Agro-Environment viewer at the
Kozukappara study point, saves rendered map screenshots, DOM/network evidence,
and every public raster response needed to reproduce the view. It also probes
OpenLayers-like global map objects for exact center, zoom, extent and viewport
metadata.

The output is research-only. A rapid-map view is not, by itself, an exact legal
or historical parcel boundary and must not change scoring.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

OUT = Path("out-naro-kozuka")
LAT = 35.732335
LON = 139.797859
ZOOMS = (15, 16, 17)
BASE = "https://habs.rad.naro.go.jp/habs_map.html"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(url: str, idx: int, content_type: str | None) -> str:
    parsed = urlparse(url)
    base = Path(parsed.path).name or f"response-{idx:04d}"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    if "." not in base:
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "application/javascript": ".js",
            "text/javascript": ".js",
            "text/css": ".css",
            "application/json": ".json",
        }.get((content_type or "").split(";")[0], ".bin")
        base += ext
    return f"{idx:04d}_{base}"


async def inspect_map(page):
    return await page.evaluate(
        """() => {
          const result = {globals: [], candidates: [], images: [], mapElements: []};
          for (const k of Object.keys(window)) {
            try {
              const v = window[k];
              if (v && typeof v === 'object') {
                const methods = ['getCenter','getZoom','getExtent','getResolution','getSize'];
                const present = methods.filter(m => typeof v[m] === 'function');
                if (present.length >= 2) {
                  const row = {name:k, methods:present};
                  try { const c=v.getCenter?.(); row.center=c ? {lon:c.lon,lat:c.lat,x:c.x,y:c.y} : null; } catch(e) {}
                  try { row.zoom=v.getZoom?.(); } catch(e) {}
                  try { const e=v.getExtent?.(); row.extent=e ? {left:e.left,bottom:e.bottom,right:e.right,top:e.top} : null; } catch(e) {}
                  try { const s=v.getSize?.(); row.size=s ? {w:s.w,h:s.h} : null; } catch(e) {}
                  try { row.resolution=v.getResolution?.(); } catch(e) {}
                  result.candidates.push(row);
                }
              }
            } catch(e) {}
          }
          for (const el of document.querySelectorAll('img')) {
            const r=el.getBoundingClientRect();
            if (r.width>0 && r.height>0) result.images.push({src:el.currentSrc||el.src,x:r.x,y:r.y,w:r.width,h:r.height,opacity:getComputedStyle(el).opacity,transform:getComputedStyle(el).transform});
          }
          for (const el of document.querySelectorAll('[id*=map], .olMap, .olMapViewport, canvas')) {
            const r=el.getBoundingClientRect();
            if (r.width>100 && r.height>100) result.mapElements.push({tag:el.tagName,id:el.id,className:el.className,x:r.x,y:r.y,w:r.width,h:r.height});
          }
          result.href=location.href;
          result.title=document.title;
          result.bodyText=(document.body?.innerText||'').slice(0,20000);
          return result;
        }"""
    )


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT / "network"
    raw_dir.mkdir(exist_ok=True)
    report = {"centerLonLat": [LON, LAT], "views": [], "license": "CC BY 2.1 JP; attribution: 農研機構農業環境研究部門", "qualityRule": "Rapid Survey Map rendering is a historical map context layer, not an exact parcel boundary. scoringEffect=none."}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1800, "height": 1400}, device_scale_factor=1)

        saved_by_hash: dict[str, str] = {}
        network_rows: list[dict] = []
        response_idx = 0

        async def save_response(response):
            nonlocal response_idx
            url = response.url
            ctype = response.headers.get("content-type", "")
            relevant = (
                "habs.rad.naro.go.jp" in url
                or "finds.jp" in url
                or "tile" in url.lower()
                or ctype.startswith("image/")
            )
            if not relevant:
                return
            row = {"url": url, "status": response.status, "contentType": ctype}
            try:
                body = await response.body()
                row["bytes"] = len(body)
                row["sha256"] = sha256_bytes(body)
                if response.status == 200 and body and len(body) <= 20_000_000:
                    digest = row["sha256"]
                    if digest in saved_by_hash:
                        row["duplicateOf"] = saved_by_hash[digest]
                    else:
                        name = safe_name(url, response_idx, ctype)
                        response_idx += 1
                        (raw_dir / name).write_bytes(body)
                        saved_by_hash[digest] = name
                        row["savedAs"] = f"network/{name}"
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            network_rows.append(row)

        for zoom in ZOOMS:
            page = await context.new_page()
            page.on("response", lambda r: asyncio.create_task(save_response(r)))
            url = f"{BASE}?lat={LAT}&layers=B0&lon={LON}&zoom={zoom}"
            await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            await page.wait_for_timeout(25_000)
            await page.screenshot(path=str(OUT / f"page-z{zoom}.png"), full_page=True)
            html = await page.content()
            (OUT / f"page-z{zoom}.html").write_text(html, encoding="utf-8")
            inspect = await inspect_map(page)
            (OUT / f"inspect-z{zoom}.json").write_text(json.dumps(inspect, ensure_ascii=False, indent=2), encoding="utf-8")

            # Prefer the largest map-like element and capture it separately.
            elements = inspect.get("mapElements") or []
            largest = max(elements, key=lambda e: e.get("w",0)*e.get("h",0), default=None)
            map_capture = None
            if largest:
                selector = None
                if largest.get("id"):
                    selector = f"#{largest['id']}"
                elif largest.get("className") and isinstance(largest["className"], str):
                    cls = largest["className"].split()[0]
                    if cls:
                        selector = f".{cls}"
                if selector:
                    try:
                        locator = page.locator(selector).first
                        await locator.screenshot(path=str(OUT / f"map-z{zoom}.png"))
                        map_capture = {"selector": selector, "file": f"map-z{zoom}.png"}
                    except Exception as exc:
                        map_capture = {"selector": selector, "error": f"{type(exc).__name__}: {exc}"}
            report["views"].append({"zoomRequested": zoom, "url": url, "inspect": f"inspect-z{zoom}.json", "pageScreenshot": f"page-z{zoom}.png", "mapCapture": map_capture, "largestMapElement": largest})
            await page.close()

        await context.close()
        await browser.close()

    (OUT / "network-responses.json").write_text(json.dumps(network_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    report["networkResponseCount"] = len(network_rows)
    report["savedUniquePayloadCount"] = len(saved_by_hash)
    (OUT / "SUMMARY.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for path in sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
            f.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(OUT)}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
