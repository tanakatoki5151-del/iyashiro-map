#!/usr/bin/env python3
"""Browser acquisition probe for source-backed historical boundary work.

Targets:
1. GSI aerial photo id 11027 (USA-M58-A-6-135, Omori POW / Heiwajima)
2. Tokyo Metropolitan Library Hanesawa cemetery map catalogue item

The probe records DOM, screenshots, HAR/network metadata, visible links/images and
saves public image responses. It never bypasses login or access controls.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Response

OUT = Path("out-boundary-sources")
TARGETS = [
    {
        "id": "gsi_usa_m58_a_6_135",
        "url": "https://service.gsi.go.jp/map-photos/app/map?search=photo&id=11027&search_date_from=0000&search_date_to=9999#15/35.581911471/139.741696748",
        "click_texts": ["USA-M58-A-6-135", "11027", "オンライン閲覧所で閲覧", "ダウンロード", "詳細情報"],
    },
    {
        "id": "tokyo_library_hanesawa_1_600",
        "url": "https://catalog.library.metro.tokyo.lg.jp/iLisvirtual/?autoMode=1&count=50&holcd=4300345962&keycode=1&type=1",
        "click_texts": ["下澁谷村羽根澤葬祭地之圖", "画像", "閲覧", "拡大", "詳細"],
    },
]


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:150] or "resource"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def save_response(response: Response, directory: Path, rows: list[dict]) -> None:
    try:
        headers = await response.all_headers()
        ctype = headers.get("content-type", "")
        clen = headers.get("content-length")
        row = {
            "url": response.url,
            "status": response.status,
            "contentType": ctype,
            "contentLength": clen,
            "requestMethod": response.request.method,
            "resourceType": response.request.resource_type,
        }
        rows.append(row)
        if response.status != 200:
            return
        if not (ctype.startswith("image/") or "application/json" in ctype or "pdf" in ctype):
            return
        try:
            body = await response.body()
        except Exception:
            return
        # Preserve useful public source payloads; skip tiny interface icons.
        if len(body) < 12_000 and ctype.startswith("image/"):
            return
        ext = ".bin"
        if "jpeg" in ctype or "jpg" in ctype:
            ext = ".jpg"
        elif "png" in ctype:
            ext = ".png"
        elif "webp" in ctype:
            ext = ".webp"
        elif "json" in ctype:
            ext = ".json"
        elif "pdf" in ctype:
            ext = ".pdf"
        parsed = urlparse(response.url)
        stem = safe_name(Path(parsed.path).name or parsed.netloc)
        digest = hashlib.sha256(body).hexdigest()[:12]
        path = directory / "responses" / f"{stem}-{digest}{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        row["savedAs"] = str(path.relative_to(directory))
        row["bytes"] = len(body)
        row["sha256"] = hashlib.sha256(body).hexdigest()
    except Exception as exc:
        rows.append({"url": getattr(response, "url", ""), "captureError": f"{type(exc).__name__}: {exc}"})


async def run_target(browser, target: dict) -> dict:
    target_dir = OUT / target["id"]
    target_dir.mkdir(parents=True, exist_ok=True)
    har_path = target_dir / "network.har"
    context = await browser.new_context(
        accept_downloads=True,
        viewport={"width": 1600, "height": 1100},
        locale="ja-JP",
        record_har_path=str(har_path),
        record_har_content="embed",
    )
    page = await context.new_page()
    responses: list[dict] = []
    tasks: list[asyncio.Task] = []
    page.on("response", lambda r: tasks.append(asyncio.create_task(save_response(r, target_dir, responses))))
    downloads: list[dict] = []

    async def on_download(download):
        try:
            suggested = safe_name(download.suggested_filename)
            dest = target_dir / "downloads" / suggested
            dest.parent.mkdir(parents=True, exist_ok=True)
            await download.save_as(str(dest))
            downloads.append({"suggestedFilename": download.suggested_filename, "savedAs": str(dest.relative_to(target_dir)), "bytes": dest.stat().st_size, "sha256": sha256(dest)})
        except Exception as exc:
            downloads.append({"error": f"{type(exc).__name__}: {exc}"})

    page.on("download", lambda d: tasks.append(asyncio.create_task(on_download(d))))
    errors: list[str] = []
    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(15_000)
        await page.screenshot(path=str(target_dir / "initial.png"), full_page=True)
        # Click only visible public controls. Never enter credentials or bypass gates.
        for text in target["click_texts"]:
            try:
                loc = page.get_by_text(text, exact=False)
                count = await loc.count()
                if count:
                    await loc.first.click(timeout=5_000)
                    await page.wait_for_timeout(5_000)
            except Exception as exc:
                errors.append(f"click {text}: {type(exc).__name__}: {exc}")
        await page.wait_for_timeout(5_000)
        await page.screenshot(path=str(target_dir / "final.png"), full_page=True)
        (target_dir / "page.html").write_text(await page.content(), encoding="utf-8")
        (target_dir / "body.txt").write_text(await page.locator("body").inner_text(), encoding="utf-8")
        links = await page.locator("a").evaluate_all("els => els.map(e => ({text:(e.innerText||'').trim(), href:e.href, title:e.title||''}))")
        images = await page.locator("img").evaluate_all("els => els.map(e => ({src:e.currentSrc||e.src, alt:e.alt||'', width:e.naturalWidth, height:e.naturalHeight}))")
        buttons = await page.locator("button, input[type=button], input[type=submit]").evaluate_all("els => els.map(e => ({text:(e.innerText||e.value||'').trim(), disabled:!!e.disabled}))")
        (target_dir / "dom-links.json").write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
        (target_dir / "dom-images.json").write_text(json.dumps(images, ensure_ascii=False, indent=2), encoding="utf-8")
        (target_dir / "dom-buttons.json").write_text(json.dumps(buttons, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        errors.append(f"navigation: {type(exc).__name__}: {exc}")
    finally:
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await context.close()

    (target_dir / "network-responses.json").write_text(json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8")
    (target_dir / "downloads.json").write_text(json.dumps(downloads, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "id": target["id"],
        "url": target["url"],
        "networkResponses": len(responses),
        "savedNetworkPayloads": sum(1 for r in responses if r.get("savedAs")),
        "downloads": downloads,
        "errors": errors,
    }
    (target_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        summaries = []
        for target in TARGETS:
            summaries.append(await run_target(browser, target))
        await browser.close()
    (OUT / "SUMMARY.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
