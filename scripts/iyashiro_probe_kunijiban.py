#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import re
import traceback
from pathlib import Path

OUT = Path("output/kunijiban_probe")
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://www.kunijiban.pwri.go.jp/jp/"
SIG = re.compile(
    r"(api|wfs|wms|mapserver|featureserver|geojson|boring|borehole|column|柱状|地盤|search|xml|json|tile)",
    re.I,
)


async def main() -> None:
    from playwright.async_api import async_playwright

    requests_seen: list[dict] = []
    responses_seen: list[dict] = []
    actions: list[dict] = []
    result: dict = {"startUrl": URL, "status": "FAILED"}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                ignore_https_errors=True,
                locale="ja-JP",
                viewport={"width": 1440, "height": 1100},
                user_agent="Mozilla/5.0 IyashirochiKuniJibanProbe/2026-08-22",
            )
            page = await context.new_page()
            page.set_default_timeout(10000)
            page.on(
                "request",
                lambda q: requests_seen.append(
                    {
                        "url": q.url,
                        "method": q.method,
                        "type": q.resource_type,
                        "signal": bool(SIG.search(q.url)),
                    }
                ),
            )

            async def on_response(response) -> None:
                record = {
                    "url": response.url,
                    "status": response.status,
                    "signal": bool(SIG.search(response.url)),
                    "contentType": response.headers.get("content-type"),
                }
                if record["signal"] and any(
                    token in (record["contentType"] or "")
                    for token in ("json", "xml", "text")
                ):
                    try:
                        body = await response.body()
                        if len(body) <= 2_000_000:
                            record["bodyFile"] = f"body_{len(responses_seen):04d}.bin"
                            (OUT / record["bodyFile"]).write_bytes(body)
                    except Exception as exc:  # noqa: BLE001
                        record["bodyError"] = str(exc)
                responses_seen.append(record)

            page.on("response", on_response)
            await page.goto(URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(5000)

            async def click(patterns: list[str], phase: str) -> bool:
                for pattern in patterns:
                    try:
                        locator = page.get_by_text(re.compile(pattern, re.I)).first
                        if await locator.count() and await locator.is_visible():
                            text = (await locator.inner_text())[:200]
                            await locator.click()
                            actions.append(
                                {
                                    "phase": phase,
                                    "pattern": pattern,
                                    "text": text,
                                    "result": "clicked",
                                }
                            )
                            await page.wait_for_timeout(5000)
                            return True
                    except Exception as exc:  # noqa: BLE001
                        actions.append(
                            {
                                "phase": phase,
                                "pattern": pattern,
                                "result": "skip",
                                "error": str(exc)[:200],
                            }
                        )
                return False

            await click(
                [r"同意", r"承諾", r"利用する", r"地盤情報検索", r"検索サイト", r"地図"],
                "entry",
            )
            if len(context.pages) > 1:
                page = context.pages[-1]
                await page.wait_for_timeout(5000)
            await click([r"同意", r"承諾", r"利用する", r"OK"], "agreement")

            inputs = page.locator("input")
            for index in range(await inputs.count()):
                locator = inputs.nth(index)
                try:
                    if not await locator.is_visible():
                        continue
                    attrs = {
                        key: await locator.get_attribute(key)
                        for key in ["type", "name", "id", "placeholder", "aria-label"]
                    }
                    haystack = " ".join(str(value or "") for value in attrs.values())
                    if re.search(r"(住所|address|検索|keyword|query|place)", haystack, re.I):
                        await locator.fill("東京都目黒区東が丘2丁目4-21")
                        actions.append(
                            {"phase": "fill_address", "attrs": attrs, "result": "filled"}
                        )
                        break
                except Exception:  # noqa: BLE001
                    pass
            await click([r"^検索$", r"住所検索", r"検索する", r"移動"], "search")
            await page.wait_for_timeout(10000)
            result.update(
                {
                    "status": "SUCCESS",
                    "finalUrl": page.url,
                    "title": await page.title(),
                    "pageCount": len(context.pages),
                    "links": await page.eval_on_selector_all(
                        "a",
                        "e=>e.map(x=>({text:(x.innerText||'').trim(),href:x.href})).filter(x=>x.text||x.href)",
                    ),
                    "controls": await page.eval_on_selector_all(
                        "button,input,label,select,option",
                        "e=>e.map(x=>({tag:x.tagName,text:(x.innerText||x.value||x.getAttribute('aria-label')||x.getAttribute('placeholder')||'').trim(),id:x.id||'',name:x.name||'',type:x.type||''})).filter(x=>x.text||x.id||x.name)",
                    ),
                }
            )
            (OUT / "final.html").write_text(await page.content(), encoding="utf-8")
            await page.screenshot(path=str(OUT / "final.png"), full_page=True)
            await browser.close()
    except Exception as exc:  # noqa: BLE001
        result.update(
            {
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
    result.update(
        {
            "requestCount": len(requests_seen),
            "responseCount": len(responses_seen),
            "signalRequests": [x for x in requests_seen if x["signal"]],
            "signalResponses": [x for x in responses_seen if x["signal"]],
        }
    )
    for name, data in [
        ("PROBE_RESULT.json", result),
        ("REQUESTS.json", requests_seen),
        ("RESPONSES.json", responses_seen),
        ("ACTIONS.json", actions),
    ]:
        (OUT / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "status": result["status"],
                "finalUrl": result.get("finalUrl"),
                "signals": len(result["signalRequests"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
