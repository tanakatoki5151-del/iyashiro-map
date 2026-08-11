#!/usr/bin/env python3
"""Capture official Tokyo archaeological-map evidence for Kozukappara.

The workflow accepts the public terms, navigates explicitly to map.html, uses
only the archaeological map's own controls, records the search result and
captures public network payloads needed to understand the official extent.

Quality boundary:
- the archaeological extent is a development-review area;
- it is not automatically the exact Edo-period execution-ground boundary;
- no scoring change or confirmed historical-site polygon is produced here.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from playwright.async_api import Locator, async_playwright

OUT = Path("out-tokyo-iseki-kozuka")
START_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/"
MAP_URL = "https://tokyo-iseki.metro.tokyo.lg.jp/map.html"
TARGET_NAME = "小塚原刑場跡"
TARGET_NUMBER = "12"
TARGET_MUNICIPALITY = "荒川区"
TARGET_ADDRESS = "南千住二丁目34番5号"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z一-龠ぁ-んァ-ン._-]+", "_", value)[:100]


async def first_visible(locator: Locator) -> Locator | None:
    for i in range(await locator.count()):
        item = locator.nth(i)
        try:
            if await item.is_visible():
                return item
        except Exception:
            continue
    return None


async def click_terms(page) -> bool:
    for label in ["同意する", "同意します", "上記の利用条件の全てに同意", "はい"]:
        loc = page.get_by_text(label, exact=False)
        item = await first_visible(loc)
        if item:
            try:
                await item.click(timeout=8_000)
                return True
            except Exception:
                pass
    for selector in ["input[type=submit]", "button", "input[type=button]", "input[type=image]"]:
        loc = page.locator(selector)
        for i in range(min(await loc.count(), 30)):
            item = loc.nth(i)
            try:
                text = " ".join(
                    filter(
                        None,
                        [
                            await item.inner_text(),
                            await item.get_attribute("value"),
                            await item.get_attribute("alt"),
                            await item.get_attribute("title"),
                        ],
                    )
                )
                if any(k in text for k in ["同意", "はい", "進む"]):
                    await item.click(timeout=8_000)
                    return True
            except Exception:
                pass
    return False


async def inventory_controls(page, filename: str) -> list[dict[str, Any]]:
    rows = await page.locator("input,button,select,textarea,a").evaluate_all(
        """els => els.slice(0,1000).map((e,i)=>{
          const ancestors=[];
          let p=e;
          for(let j=0;j<5 && p;j++,p=p.parentElement){
            const t=(p.innerText||p.textContent||'').replace(/\s+/g,' ').trim();
            if(t) ancestors.push(t.slice(0,500));
          }
          return {
            i, tag:e.tagName, type:e.type||'', id:e.id||'', name:e.name||'',
            value:e.value||'', placeholder:e.placeholder||'',
            text:(e.innerText||'').replace(/\s+/g,' ').trim(),
            href:e.href||'', cls:String(e.className||''),
            ariaLabel:e.getAttribute('aria-label')||'', title:e.title||'',
            outerHTML:e.outerHTML.slice(0,2000), ancestors
          };
        })"""
    )
    (OUT / filename).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


async def tag_contextual_controls(page) -> list[dict[str, Any]]:
    """Add stable data-probe IDs and capture nearby labels for map controls."""
    return await page.evaluate(
        """() => {
          const result=[];
          const els=[...document.querySelectorAll('input,select,textarea,button')];
          els.forEach((e,i)=>{
            e.dataset.probeId=String(i);
            const label=e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
            let p=e.parentElement;
            const contexts=[];
            for(let j=0;j<6 && p;j++,p=p.parentElement){
              const t=(p.innerText||p.textContent||'').replace(/\s+/g,' ').trim();
              if(t) contexts.push(t.slice(0,800));
            }
            result.push({
              probeId:String(i), tag:e.tagName, type:e.type||'', id:e.id||'', name:e.name||'',
              value:e.value||'', placeholder:e.placeholder||'', ariaLabel:e.getAttribute('aria-label')||'',
              labelText:label ? (label.innerText||label.textContent||'').trim() : '', contexts
            });
          });
          return result;
        }"""
    )


def choose_control(rows: list[dict[str, Any]], keywords: list[str], *, tag: str | None = None) -> str | None:
    scored: list[tuple[int, str]] = []
    for row in rows:
        if tag and row.get("tag") != tag:
            continue
        hay = " ".join(
            [
                row.get("id", ""), row.get("name", ""), row.get("placeholder", ""),
                row.get("ariaLabel", ""), row.get("labelText", ""),
                " ".join(row.get("contexts", [])[:3]),
            ]
        )
        score = sum(10 for k in keywords if k in hay)
        if row.get("name") == "q":  # global Google CSE field
            score -= 100
        if row.get("type") in {"hidden", "image"}:
            score -= 50
        if score > 0:
            scored.append((score, row["probeId"]))
    scored.sort(reverse=True)
    return scored[0][1] if scored else None


async def fill_probe(page, probe_id: str | None, value: str) -> bool:
    if probe_id is None:
        return False
    loc = page.locator(f'[data-probe-id="{probe_id}"]')
    try:
        if await loc.count() and await loc.first.is_visible():
            await loc.first.fill(value)
            return True
    except Exception:
        return False
    return False


async def select_option_text(page, probe_id: str | None, text: str) -> bool:
    if probe_id is None:
        return False
    loc = page.locator(f'[data-probe-id="{probe_id}"]')
    try:
        if not await loc.count():
            return False
        options = await loc.locator("option").evaluate_all(
            "els => els.map(e=>({text:(e.innerText||e.textContent||'').trim(),value:e.value}))"
        )
        exact = next((o for o in options if text == o["text"]), None)
        partial = next((o for o in options if text in o["text"]), None)
        chosen = exact or partial
        if chosen:
            await loc.select_option(chosen["value"])
            return True
    except Exception:
        return False
    return False


async def click_map_search(page, controls: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for row in controls:
        if row.get("tag") not in {"BUTTON", "INPUT"}:
            continue
        hay = " ".join(
            [row.get("value", ""), row.get("labelText", ""), row.get("ariaLabel", ""), " ".join(row.get("contexts", [])[:2])]
        )
        score = 0
        if "検索結果" in hay:
            score += 30
        if "遺跡" in hay and "検索" in hay:
            score += 20
        if "検索" in hay:
            score += 10
        if row.get("name") == "sa" or "Google" in hay:
            score -= 100
        if score > 0:
            candidates.append((score, row["probeId"], row))
    candidates.sort(reverse=True, key=lambda x: x[0])
    errors=[]
    for score, probe_id, row in candidates:
        loc = page.locator(f'[data-probe-id="{probe_id}"]')
        try:
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=8_000)
                return {"clicked": True, "score": score, "control": row}
        except Exception as exc:
            errors.append({"probeId": probe_id, "error": f"{type(exc).__name__}: {exc}"})
    return {"clicked": False, "errors": errors, "candidates": candidates[:10]}


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload_dir = OUT / "payloads"
    payload_dir.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1100})
        page = await context.new_page()
        network: list[dict[str, Any]] = []
        payloads: list[dict[str, Any]] = []

        async def on_response(response):
            url = response.url
            ct = (response.headers.get("content-type") or "").lower()
            row = {"url": url, "status": response.status, "contentType": ct}
            network.append(row)
            if response.status != 200:
                return
            interesting = any(x in url.lower() for x in ["geo", "wfs", "wms", "arcgis", "feature", "iseki", "遺跡", "map", "api", "json", "data"]) or any(
                x in ct for x in ["json", "javascript", "xml", "geo+json", "octet-stream"]
            )
            if not interesting:
                return
            try:
                body = await response.body()
            except Exception:
                return
            if not body or len(body) > 30_000_000:
                return
            digest = hashlib.sha256(body).hexdigest()
            suffix = ".bin"
            if "json" in ct:
                suffix = ".json"
            elif "javascript" in ct:
                suffix = ".js"
            elif "xml" in ct:
                suffix = ".xml"
            elif body[:8] == b"\x89PNG\r\n\x1a\n":
                suffix = ".png"
            elif body[:3] == b"\xff\xd8\xff":
                suffix = ".jpg"
            path = payload_dir / f"{len(payloads):04d}_{digest[:12]}{suffix}"
            path.write_bytes(body)
            payloads.append({**row, "savedAs": str(path.relative_to(OUT)), "bytes": len(body), "sha256": digest})

        page.on("response", lambda r: asyncio.create_task(on_response(r)))
        await page.goto(START_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(3_000)
        await page.screenshot(path=str(OUT / "00_terms.png"), full_page=True)
        accepted = await click_terms(page)
        await page.wait_for_timeout(3_000)

        # Critical v2 fix: navigate explicitly to the archaeological map page.
        await page.goto(MAP_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(15_000)
        await page.screenshot(path=str(OUT / "01_map_initial.png"), full_page=True)
        (OUT / "01_map_initial.html").write_text(await page.content(), encoding="utf-8")
        (OUT / "01_map_initial_body.txt").write_text(await page.locator("body").inner_text(), encoding="utf-8")
        await inventory_controls(page, "01_map_controls_full.json")
        controls = await tag_contextual_controls(page)
        (OUT / "02_contextual_controls.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")

        selected = {
            "name": choose_control(controls, ["名称", "遺跡名", "name"]),
            "municipality": choose_control(controls, ["区市町村", "市区町村", "municipality"], tag="SELECT"),
            "town": choose_control(controls, ["町丁目", "町 丁 目", "所在地"]),
            "number": choose_control(controls, ["遺跡番号", "番号"]),
        }
        actions = {
            "selectedControls": selected,
            "filledName": await fill_probe(page, selected["name"], TARGET_NAME),
            "selectedMunicipality": await select_option_text(page, selected["municipality"], TARGET_MUNICIPALITY),
            "filledNumber": await fill_probe(page, selected["number"], TARGET_NUMBER),
        }
        await page.screenshot(path=str(OUT / "02_search_form_filled.png"), full_page=True)
        actions["searchClick"] = await click_map_search(page, controls)
        await page.wait_for_timeout(15_000)
        await page.screenshot(path=str(OUT / "03_search_results.png"), full_page=True)
        (OUT / "03_search_results.html").write_text(await page.content(), encoding="utf-8")
        result_body = await page.locator("body").inner_text()
        (OUT / "03_search_results_body.txt").write_text(result_body, encoding="utf-8")

        result_rows = await page.locator("tr").evaluate_all(
            "els => els.map((e,i)=>({i,text:(e.innerText||'').replace(/\s+/g,' ').trim(),html:e.outerHTML.slice(0,6000)})).filter(x=>x.text)"
        )
        (OUT / "04_result_rows.json").write_text(json.dumps(result_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        target_rows = [r for r in result_rows if TARGET_NAME in r["text"] or (TARGET_NUMBER in r["text"] and "南千住" in r["text"])]
        (OUT / "04_target_rows.json").write_text(json.dumps(target_rows, ensure_ascii=False, indent=2), encoding="utf-8")

        map_click = {"clicked": False}
        row = page.locator("tr").filter(has_text=TARGET_NAME)
        if await row.count():
            for selector in ["a", "button", "input[type=button]", "input[type=image]"]:
                items = row.first.locator(selector)
                for i in range(await items.count()):
                    item = items.nth(i)
                    try:
                        attrs = {
                            "text": (await item.inner_text()).strip(),
                            "title": await item.get_attribute("title"),
                            "alt": await item.get_attribute("alt"),
                            "href": await item.get_attribute("href"),
                            "onclick": await item.get_attribute("onclick"),
                        }
                        hay = " ".join(str(v or "") for v in attrs.values())
                        if "地図" in hay or selector != "a":
                            await item.click(timeout=8_000)
                            map_click = {"clicked": True, "selector": selector, "attrs": attrs}
                            break
                    except Exception as exc:
                        map_click.setdefault("errors", []).append(f"{selector}[{i}]: {type(exc).__name__}: {exc}")
                if map_click.get("clicked"):
                    break
        actions["mapClick"] = map_click
        await page.wait_for_timeout(15_000)
        await page.screenshot(path=str(OUT / "05_target_map.png"), full_page=True)
        (OUT / "05_target_map.html").write_text(await page.content(), encoding="utf-8")
        (OUT / "05_target_map_body.txt").write_text(await page.locator("body").inner_text(), encoding="utf-8")

        canvas_meta = await page.locator("canvas,svg,.ol-viewport,.leaflet-container,[class*=map],[id*=map]").evaluate_all(
            """els => els.slice(0,300).map((e,i)=>{const r=e.getBoundingClientRect();return {i,tag:e.tagName,id:e.id||'',cls:String(e.className||''),x:r.x,y:r.y,width:r.width,height:r.height,html:e.outerHTML.slice(0,3000)}})"""
        )
        (OUT / "06_map_elements.json").write_text(json.dumps(canvas_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        resources = await page.evaluate("performance.getEntriesByType('resource').map(e=>e.name)")
        globals_hint = await page.evaluate("Object.keys(window).filter(k=>/map|site|iseki|geo|layer|feature|openlayer|leaflet/i.test(k)).slice(0,500)")
        (OUT / "07_resource_urls.json").write_text(json.dumps(resources, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "07_window_global_hints.json").write_text(json.dumps(globals_hint, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "07_network.json").write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "07_payload_index.json").write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "07_actions.json").write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

        hits=[]
        needles=[TARGET_NAME,"小塚原","刑場跡","南千住","遺跡番号",'"12"',"site_no","iseki_no"]
        for p in payload_dir.iterdir():
            if p.suffix.lower() not in {".json",".js",".xml",".bin"}:
                continue
            try:
                text=p.read_text(encoding="utf-8",errors="ignore")
            except Exception:
                continue
            for needle in needles:
                pos=text.find(needle)
                if pos >= 0:
                    hits.append({"file":p.name,"needle":needle,"context":text[max(0,pos-1000):pos+4000]})
        (OUT / "08_target_payload_hits.json").write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")

        summary={
            "acceptedTerms":accepted,
            "mapUrl":MAP_URL,
            "finalUrl":page.url,
            "targetName":TARGET_NAME,
            "searchResultContainsTarget":TARGET_NAME in result_body,
            "targetResultRowCount":len(target_rows),
            "mapClick":map_click,
            "networkResponseCount":len(network),
            "savedPayloadCount":len(payloads),
            "targetPayloadHitCount":len(hits),
            "actions":actions,
            "qualityRule":"The official archaeological extent is a development-review area, not automatically the exact Edo-period execution-ground boundary. No scoring change is allowed from this probe alone.",
        }
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        with (OUT / "SHA256SUMS.txt").open("w",encoding="utf-8") as f:
            for path in sorted(OUT.rglob("*")):
                if path.is_file() and path.name != "SHA256SUMS.txt":
                    f.write(f"{sha256(path)}  {path.relative_to(OUT)}\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
