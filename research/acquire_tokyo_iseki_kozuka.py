#!/usr/bin/env python3
"""Capture the official Tokyo archaeological-map extent for Kozukappara.

This automation only uses the public Tokyo Metropolitan Government service and
accepts the displayed terms. It records DOM, screenshots, resource URLs and
JSON/GeoJSON-like responses. It does not copy the map into a scoring layer and
never treats the archaeological extent as the exact historical execution-ground
boundary.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

OUT = Path("out-tokyo-iseki-kozuka")
START_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/"
SEARCH_TERMS = ["小塚原刑場跡", "南千住二丁目34番5号", "南千住2-34-5"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload_dir = OUT / "payloads"
    payload_dir.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1100})
        page = await context.new_page()
        network: list[dict] = []
        payloads: list[dict] = []

        async def on_response(response):
            url = response.url
            ct = (response.headers.get("content-type") or "").lower()
            row = {"url": url, "status": response.status, "contentType": ct}
            network.append(row)
            if response.status != 200:
                return
            interesting = any(x in url.lower() for x in ["geo", "wfs", "wms", "arcgis", "feature", "site", "iseki", "map", "api"]) or any(
                x in ct for x in ["json", "javascript", "xml", "geo+json"]
            )
            if not interesting:
                return
            try:
                body = await response.body()
            except Exception:
                return
            if not body or len(body) > 25_000_000:
                return
            digest = hashlib.sha256(body).hexdigest()
            suffix = ".bin"
            if "json" in ct:
                suffix = ".json"
            elif "javascript" in ct:
                suffix = ".js"
            elif "xml" in ct:
                suffix = ".xml"
            elif body[:4] == b"\x89PNG":
                suffix = ".png"
            elif body[:3] == b"\xff\xd8\xff":
                suffix = ".jpg"
            name = f"{len(payloads):04d}_{digest[:12]}{suffix}"
            path = payload_dir / name
            path.write_bytes(body)
            payloads.append({**row, "savedAs": str(path.relative_to(OUT)), "bytes": len(body), "sha256": digest})

        page.on("response", lambda r: asyncio.create_task(on_response(r)))
        await page.goto(START_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(4_000)
        await page.screenshot(path=str(OUT / "00_terms.png"), full_page=True)
        (OUT / "00_terms.html").write_text(await page.content(), encoding="utf-8")

        # Accept the displayed public-use terms. Try visible labels and generic form controls.
        accepted = False
        for label in ["同意する", "同意します", "はい", "利用条件に同意", "上記に同意"]:
            loc = page.get_by_text(label, exact=False)
            if await loc.count():
                try:
                    await loc.first.click(timeout=5_000)
                    accepted = True
                    break
                except Exception:
                    pass
        if not accepted:
            for selector in ["input[type=submit]", "button", "input[type=button]", "input[type=image]"]:
                for i in range(min(await page.locator(selector).count(), 20)):
                    el = page.locator(selector).nth(i)
                    try:
                        text = ((await el.inner_text()) or "") + " " + ((await el.get_attribute("value")) or "")
                        if any(k in text for k in ["同意", "はい", "進む", "利用"]):
                            await el.click(timeout=5_000)
                            accepted = True
                            break
                    except Exception:
                        pass
                if accepted:
                    break
        await page.wait_for_timeout(10_000)
        await page.screenshot(path=str(OUT / "01_after_terms.png"), full_page=True)
        (OUT / "01_after_terms.html").write_text(await page.content(), encoding="utf-8")
        (OUT / "01_body.txt").write_text(await page.locator("body").inner_text(), encoding="utf-8")

        # Inventory visible controls and resource URLs before searching.
        controls = await page.locator("input,button,select,textarea,a").evaluate_all(
            """els => els.slice(0,500).map((e,i)=>({i,tag:e.tagName,type:e.type||'',id:e.id||'',name:e.name||'',value:e.value||'',placeholder:e.placeholder||'',text:(e.innerText||'').trim(),href:e.href||'',cls:e.className||''}))"""
        )
        (OUT / "controls.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")

        search_attempts = []
        text_inputs = page.locator("input[type=text], input:not([type]), textarea")
        for term in SEARCH_TERMS:
            tried = False
            for i in range(min(await text_inputs.count(), 20)):
                el = text_inputs.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    await el.fill(term)
                    tried = True
                    # Press Enter first, then click likely search buttons.
                    await el.press("Enter")
                    await page.wait_for_timeout(5_000)
                    for label in ["検索", "住所検索", "遺跡検索", "調書検索"]:
                        loc = page.get_by_text(label, exact=False)
                        if await loc.count():
                            try:
                                await loc.first.click(timeout=3_000)
                                await page.wait_for_timeout(6_000)
                                break
                            except Exception:
                                pass
                    break
                except Exception as exc:
                    search_attempts.append({"term": term, "input": i, "error": f"{type(exc).__name__}: {exc}"})
            search_attempts.append({"term": term, "tried": tried, "url": page.url})
            await page.screenshot(path=str(OUT / f"search_{re.sub(r'[^0-9A-Za-z一-龠ぁ-んァ-ン]+','_',term)}.png"), full_page=True)
            (OUT / f"body_{len(search_attempts):02d}.txt").write_text(await page.locator("body").inner_text(), encoding="utf-8")

        resources = await page.evaluate("performance.getEntriesByType('resource').map(e=>e.name)")
        globals_hint = await page.evaluate(
            "Object.keys(window).filter(k=>/map|site|iseki|geo|layer|feature/i.test(k)).slice(0,300)"
        )
        (OUT / "resource-urls.json").write_text(json.dumps(resources, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "window-global-hints.json").write_text(json.dumps(globals_hint, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "network.json").write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "payload-index.json").write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "search-attempts.json").write_text(json.dumps(search_attempts, ensure_ascii=False, indent=2), encoding="utf-8")

        # Search captured textual payloads for the target label and site number 12.
        hits = []
        for p in payload_dir.iterdir():
            if p.suffix.lower() not in {".json", ".js", ".xml", ".bin"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for needle in ["小塚原", "刑場跡", "遺跡番号12", '"12"']:
                if needle in text:
                    hits.append({"file": p.name, "needle": needle, "context": text[max(0,text.find(needle)-500):text.find(needle)+1500]})
        (OUT / "target-hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {
            "acceptedTerms": accepted,
            "finalUrl": page.url,
            "controlCount": len(controls),
            "networkResponseCount": len(network),
            "savedPayloadCount": len(payloads),
            "targetHitCount": len(hits),
            "qualityRule": "The official archaeological extent is a development-review area, not automatically the exact Edo-period execution-ground boundary. No score change is allowed from this probe alone.",
        }
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
            for path in sorted(OUT.rglob("*")):
                if path.is_file() and path.name != "SHA256SUMS.txt":
                    f.write(f"{sha256(path)}  {path.relative_to(OUT)}\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
