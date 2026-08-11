#!/usr/bin/env python3
"""Capture official Tokyo archaeological-map evidence for Kozukappara, v2.

This version opens the dedicated map page directly, avoiding the website-wide
Google search box. It records public DOM/network evidence and search-result
metadata. Raw official map geometry is retained only inside the temporary
research artifact and must not be redistributed as a scoring layer because the
Tokyo service prohibits unauthorized copying and states that site extents are
not necessarily definitive.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("out-tokyo-iseki-kozuka-v2")
MAP_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/map.html#main"
TARGET_NAME = "小塚原刑場跡"
TARGET_MUNICIPALITY = "荒川区"
TARGET_NUMBER = "12"


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
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1700, "height": 1200})
        page = await context.new_page()
        network: list[dict] = []
        payloads: list[dict] = []

        async def on_response(response):
            url = response.url
            ctype = (response.headers.get("content-type") or "").lower()
            row = {"url": url, "status": response.status, "contentType": ctype}
            network.append(row)
            interesting = any(x in url.lower() for x in ["geo", "wfs", "wms", "arcgis", "feature", "site", "iseki", "layer", "map", "api", "search"]) or any(
                x in ctype for x in ["json", "javascript", "xml", "geo+json"]
            )
            if response.status != 200 or not interesting:
                return
            try:
                body = await response.body()
            except Exception:
                return
            if not body or len(body) > 30_000_000:
                return
            digest = hashlib.sha256(body).hexdigest()
            suffix = ".bin"
            if "json" in ctype:
                suffix = ".json"
            elif "javascript" in ctype:
                suffix = ".js"
            elif "xml" in ctype:
                suffix = ".xml"
            elif body[:4] == b"\x89PNG":
                suffix = ".png"
            elif body[:3] == b"\xff\xd8\xff":
                suffix = ".jpg"
            path = payload_dir / f"{len(payloads):04d}_{digest[:12]}{suffix}"
            path.write_bytes(body)
            row.update({"savedAs": str(path.relative_to(OUT)), "bytes": len(body), "sha256": digest})
            payloads.append(row)

        page.on("response", lambda r: asyncio.create_task(on_response(r)))
        await page.goto(MAP_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(15_000)
        await page.screenshot(path=str(OUT / "01_map_initial.png"), full_page=True)
        (OUT / "01_map_initial.html").write_text(await page.content(), encoding="utf-8")
        (OUT / "01_body.txt").write_text(await page.locator("body").inner_text(), encoding="utf-8")

        controls = await page.locator("input,button,select,textarea,a").evaluate_all(
            """els => els.slice(0,1000).map((e,i)=>({i,tag:e.tagName,type:e.type||'',id:e.id||'',name:e.name||'',value:e.value||'',placeholder:e.placeholder||'',text:(e.innerText||'').trim(),href:e.href||'',cls:e.className||'',aria:e.getAttribute('aria-label')||'',title:e.title||''}))"""
        )
        (OUT / "controls.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")

        # Identify dedicated archaeological-search fields. Exclude the global site
        # search input (name=q). Use labels/IDs when available, then positional
        # fallback within the map search panel.
        text_inputs = page.locator("input[type=text]:visible")
        input_meta = await text_inputs.evaluate_all(
            "els => els.map((e,i)=>({i,id:e.id||'',name:e.name||'',placeholder:e.placeholder||'',cls:e.className||'',outer:e.outerHTML.slice(0,500)}))"
        )
        (OUT / "text-inputs.json").write_text(json.dumps(input_meta, ensure_ascii=False, indent=2), encoding="utf-8")

        async def choose_input(keywords: list[str], fallback_index: int | None = None):
            count = await text_inputs.count()
            for i in range(count):
                el = text_inputs.nth(i)
                attrs = " ".join([
                    (await el.get_attribute("id")) or "",
                    (await el.get_attribute("name")) or "",
                    (await el.get_attribute("placeholder")) or "",
                    (await el.get_attribute("class")) or "",
                    (await el.get_attribute("aria-label")) or "",
                    (await el.get_attribute("title")) or "",
                ]).lower()
                if (await el.get_attribute("name")) == "q":
                    continue
                if any(k.lower() in attrs for k in keywords):
                    return el
            candidates = []
            for i in range(count):
                el = text_inputs.nth(i)
                if (await el.get_attribute("name")) != "q":
                    candidates.append(el)
            if fallback_index is not None and len(candidates) > fallback_index:
                return candidates[fallback_index]
            return None

        name_input = await choose_input(["name", "site", "iseki", "名称"], 0)
        town_input = await choose_input(["town", "chome", "町", "丁目"], 1)
        number_input = await choose_input(["number", "no", "遺跡番号", "siteid"], 2)
        municipality_select = page.locator("select:visible")
        selected_municipality = False
        for i in range(await municipality_select.count()):
            sel = municipality_select.nth(i)
            try:
                options = await sel.locator("option").all_text_contents()
                if any(TARGET_MUNICIPALITY in x for x in options):
                    await sel.select_option(label=TARGET_MUNICIPALITY)
                    selected_municipality = True
                    break
            except Exception:
                pass

        attempts = []
        if name_input is not None:
            await name_input.fill(TARGET_NAME)
            attempts.append("name")
        if number_input is not None:
            await number_input.fill(TARGET_NUMBER)
            attempts.append("number")

        # Locate the search action in the map panel, avoiding the global submit.
        clicked = False
        for selector in ["#searchBtn", "#btnSearch", "input[value*=検索]", "button:has-text('検索')"]:
            loc = page.locator(selector)
            for i in range(min(await loc.count(), 10)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    # Avoid the global site-search submit button.
                    parent_text = (await el.evaluate("e => (e.closest('form')?.innerText || e.parentElement?.innerText || '').slice(0,1000)"))
                    if "遺跡番号" not in parent_text and "種別選択" not in parent_text and selector == "button:has-text('検索')":
                        continue
                    await el.click(timeout=8_000)
                    clicked = True
                    break
                except Exception:
                    pass
            if clicked:
                break
        if not clicked and name_input is not None:
            await name_input.press("Enter")

        await page.wait_for_timeout(15_000)
        await page.screenshot(path=str(OUT / "02_search_results.png"), full_page=True)
        (OUT / "02_search_results.html").write_text(await page.content(), encoding="utf-8")
        body = await page.locator("body").inner_text()
        (OUT / "02_body.txt").write_text(body, encoding="utf-8")

        # Capture visible result rows and popup/details text without copying the
        # official map itself into downstream scoring data.
        tables = await page.locator("table").evaluate_all(
            "els => els.map((t,i)=>({i,text:(t.innerText||'').trim(),html:t.outerHTML.slice(0,20000)}))"
        )
        result_like = await page.locator("tr, .result, .search-result, [class*=result]").evaluate_all(
            "els => els.slice(0,1000).map((e,i)=>({i,tag:e.tagName,cls:e.className||'',text:(e.innerText||'').trim()})).filter(x=>x.text)"
        )
        (OUT / "tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "result-like-elements.json").write_text(json.dumps(result_like, ensure_ascii=False, indent=2), encoding="utf-8")

        resources = await page.evaluate("performance.getEntriesByType('resource').map(e=>e.name)")
        scripts = await page.locator("script[src]").evaluate_all("els => els.map(s=>s.src)")
        globals_hint = await page.evaluate("Object.keys(window).filter(k=>/map|site|iseki|geo|layer|feature|search/i.test(k)).slice(0,500)")
        (OUT / "resource-urls.json").write_text(json.dumps(resources, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "script-urls.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "window-global-hints.json").write_text(json.dumps(globals_hint, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "network.json").write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "payload-index.json").write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")

        hits = []
        needles = [TARGET_NAME, "小塚原", "刑場跡", "南千住", "遺跡番号", '"12"']
        for path in payload_dir.iterdir():
            if path.suffix.lower() not in {".json", ".js", ".xml", ".bin"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in needles:
                pos = text.find(needle)
                if pos >= 0:
                    hits.append({"file": path.name, "needle": needle, "context": text[max(0,pos-700):pos+2500]})
        (OUT / "target-hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")

        summary = {
            "mapUrl": MAP_URL,
            "selectedMunicipality": selected_municipality,
            "filledFields": attempts,
            "clickedSearch": clicked,
            "finalUrl": page.url,
            "bodyContainsTarget": TARGET_NAME in body or "小塚原" in body,
            "networkResponseCount": len(network),
            "savedPayloadCount": len(payloads),
            "targetHitCount": len(hits),
            "qualityRule": "The official archaeological extent is a development-review area and is not automatically the exact Edo-period execution-ground boundary. Raw official geometry must not be redistributed or used for scoring; only derived audit statistics may be retained.",
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
