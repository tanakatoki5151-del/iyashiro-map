#!/usr/bin/env python3
"""Acquire the public NDL digital map for Tokyo 1:5,000 sheet no.1.

Target: 東京北東部 淺草及下谷 ([五千分一東京圖] ; 第1號), surveyed 1884,
printed 1886/1887. The script follows ordinary public pages, records page and
network provenance, and saves public IIIF/image resources when exposed. It does
not bypass authentication or restricted-view controls.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

OUT = Path("out-ndl-tokyo-5000-asakusa")
SEARCH_URL = (
    "https://ndlsearch.ndl.go.jp/search?cs=bib&from=0&size=20"
    "&q-title=%E6%9D%B1%E4%BA%AC%E5%8C%97%E6%9D%B1%E9%83%A8%20%E6%B7%BA%E8%8D%89%E5%8F%8A%E4%B8%8B%E8%B0%B7"
)
TARGET_TEXTS = [
    "東京北東部 淺草及下谷",
    "東京北東部淺草及下谷",
    "第1號",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(url: str, index: int, content_type: str | None) -> str:
    path = Path(urlparse(url).path)
    name = path.name or f"payload-{index:04d}"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if "." not in name:
        ext = {
            "application/json": ".json",
            "application/ld+json": ".json",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/pdf": ".pdf",
            "application/xml": ".xml",
            "text/xml": ".xml",
        }.get((content_type or "").split(";")[0], ".bin")
        name += ext
    return f"{index:04d}_{name}"


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload_dir = OUT / "network-payloads"
    payload_dir.mkdir(exist_ok=True)
    images_dir = OUT / "images"
    images_dir.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1200})
        page = await context.new_page()
        network: list[dict] = []
        payload_count = 0

        async def on_response(response):
            nonlocal payload_count
            url = response.url
            ctype = response.headers.get("content-type", "")
            row = {"url": url, "status": response.status, "contentType": ctype}
            network.append(row)
            interesting = (
                "iiif" in url.lower()
                or "manifest" in url.lower()
                or "canvas" in url.lower()
                or "info.json" in url.lower()
                or "dl.ndl.go.jp" in url.lower()
                or "image" in ctype.lower()
                or "json" in ctype.lower()
            )
            if not interesting or response.status != 200:
                return
            try:
                body = await response.body()
            except Exception:
                return
            if not body or len(body) > 80 * 1024 * 1024:
                return
            payload_count += 1
            name = safe_name(url, payload_count, ctype)
            path = payload_dir / name
            path.write_bytes(body)
            row["savedAs"] = str(path.relative_to(OUT))
            row["bytes"] = len(body)
            row["sha256"] = sha256_bytes(body)

        page.on("response", lambda r: asyncio.create_task(on_response(r)))
        await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(8_000)
        await page.screenshot(path=str(OUT / "01_ndl_search.png"), full_page=True)
        (OUT / "01_ndl_search.html").write_text(await page.content(), encoding="utf-8")

        # Prefer a link whose text contains the exact sheet title.
        target = None
        for text in TARGET_TEXTS[:2]:
            loc = page.get_by_text(text, exact=False)
            if await loc.count():
                target = loc.first
                break
        if target is None:
            # Fallback: inspect all links and choose a likely child item.
            links = await page.locator("a").evaluate_all(
                "els => els.map(a => ({text:(a.innerText||'').trim(), href:a.href}))"
            )
            (OUT / "search-links.json").write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
            href = next((x["href"] for x in links if "浅草" in x["text"] and "下谷" in x["text"]), None)
            if href:
                await page.goto(href, wait_until="domcontentloaded", timeout=120_000)
        else:
            # Search cards may render the title inside a hidden span. Resolve its
            # ancestor href and navigate directly instead of depending on a click.
            anchor = target.locator("xpath=ancestor::a[1]")
            href = await anchor.get_attribute("href") if await anchor.count() else None
            if not href:
                href = await target.evaluate(
                    "el => (el.closest('a') && el.closest('a').href) || "
                    "(el.parentElement && el.parentElement.closest('a') && el.parentElement.closest('a').href) || null"
                )
            if href:
                await page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=120_000)
            else:
                await target.click(timeout=20_000, force=True)
            await page.wait_for_timeout(8_000)

        await page.screenshot(path=str(OUT / "02_child_item.png"), full_page=True)
        (OUT / "02_child_item.html").write_text(await page.content(), encoding="utf-8")
        child_url = page.url

        # Follow the public digital-collection link.
        digital_link = None
        for pattern in ["収録元データベースで確認する", "インターネットで資料を読む", "国立国会図書館デジタルコレクション"]:
            loc = page.get_by_text(pattern, exact=False)
            if await loc.count():
                digital_link = loc.first
                break
        if digital_link:
            try:
                async with page.expect_popup(timeout=10_000) as popup_info:
                    await digital_link.click(timeout=15_000)
                digital_page = await popup_info.value
                await digital_page.wait_for_load_state("domcontentloaded", timeout=120_000)
                page = digital_page
            except Exception:
                await digital_link.click(timeout=15_000)
                await page.wait_for_timeout(10_000)

        await page.wait_for_timeout(12_000)
        await page.screenshot(path=str(OUT / "03_digital_collection.png"), full_page=True)
        (OUT / "03_digital_collection.html").write_text(await page.content(), encoding="utf-8")
        digital_url = page.url

        # Record all visible links, images and scripts. Public image endpoints are
        # fetched with the same browser context and referer.
        links = await page.locator("a").evaluate_all(
            "els => els.map(a => ({text:(a.innerText||'').trim(), href:a.href}))"
        )
        imgs = await page.locator("img").evaluate_all(
            "els => els.map(i => ({src:i.src, currentSrc:i.currentSrc, alt:i.alt, width:i.naturalWidth, height:i.naturalHeight}))"
        )
        scripts = await page.locator("script[src]").evaluate_all("els => els.map(s => s.src)")
        (OUT / "digital-links.json").write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "digital-images.json").write_text(json.dumps(imgs, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "digital-scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=2), encoding="utf-8")

        candidates = []
        for item in imgs:
            for key in ("currentSrc", "src"):
                u = item.get(key)
                if u and u.startswith("http"):
                    candidates.append(u)
        for x in links:
            u = x.get("href")
            if u and any(t in u.lower() for t in ("iiif", "manifest", "image", "download")):
                candidates.append(u)
        for row in network:
            u = row["url"]
            if any(t in u.lower() for t in ("iiif", "manifest", "info.json")):
                candidates.append(u)
        candidates = list(dict.fromkeys(candidates))

        acquired: list[dict] = []
        for i, url in enumerate(candidates[:80], 1):
            try:
                resp = await context.request.get(
                    url,
                    headers={"Referer": digital_url, "Accept": "image/avif,image/webp,image/apng,image/*,application/json,*/*;q=0.8"},
                    timeout=120_000,
                    fail_on_status_code=False,
                )
                body = await resp.body()
                ctype = resp.headers.get("content-type", "")
                row = {"url": url, "status": resp.status, "contentType": ctype, "bytes": len(body)}
                if resp.status == 200 and body and len(body) <= 100 * 1024 * 1024:
                    name = safe_name(url, i, ctype)
                    path = images_dir / name
                    path.write_bytes(body)
                    row["savedAs"] = str(path.relative_to(OUT))
                    row["sha256"] = sha256_bytes(body)
                acquired.append(row)
            except Exception as exc:
                acquired.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})

        (OUT / "network.json").write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "acquired.json").write_text(json.dumps(acquired, ensure_ascii=False, indent=2), encoding="utf-8")
        with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
            for path in sorted(OUT.rglob("*")):
                if path.is_file() and path.name != "SHA256SUMS.txt":
                    f.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(OUT)}\n")

        summary = {
            "searchUrl": SEARCH_URL,
            "childItemUrl": child_url,
            "digitalCollectionUrl": digital_url,
            "networkResponseCount": len(network),
            "savedNetworkPayloadCount": sum(1 for r in network if r.get("savedAs")),
            "candidateResourceCount": len(candidates),
            "acquiredResourceCount": sum(1 for r in acquired if r.get("savedAs")),
            "qualityRule": "Only public resources reached through ordinary pages are retained. Restricted pages are not bypassed. A map image must be independently georeferenced and reviewed before any historical boundary is promoted.",
        }
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
