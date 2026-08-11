#!/usr/bin/env python3
"""Acquire public source evidence for Ichigaya Prison / Tokyo Prison.

This research-only workflow separates:
1. the former prison/facility extent,
2. execution or memorial locations,
3. later land use.

It uses public GSI aerial-photo services, the Tokyo archaeological map, NDL
Search/Digital Collections catalogue pages, and public municipal/archive pages.
Proxy points and archaeological extents are discovery aids only and never become
historical boundaries without independent map/cadastral corroboration.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import quote, urljoin

from playwright.async_api import async_playwright

OUT = Path("out-ichigaya-prison-sources")
QUERIES = [
    "市谷監獄",
    "市谷刑務所",
    "東京監獄 市谷",
    "市ヶ谷刑務所",
    "市谷刑務所跡",
    "富久町 刑死者 慰霊",
]
GSI_FALLBACK = (139.7186, 35.6944)
GSI_API = "https://service.gsi.go.jp/map-photos/app/api/photo"
GSI_IMAGE_BASE = "https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/"
ARCHIVE_TARGETS = [
    ("ndl_search", "https://ndlsearch.ndl.go.jp/search?cs=bib&from=0&size=100&q-title=" + quote("市谷刑務所 市谷監獄 東京監獄")),
    ("ndl_digital_search", "https://dl.ndl.go.jp/search/searchResult?searchWord=" + quote("市谷刑務所")),
    ("shinjuku_search", "https://www.city.shinjuku.lg.jp/search/index.html?q=" + quote("市谷刑務所")),
    ("tokyo_archives", "https://archives.metro.tokyo.lg.jp/"),
    ("tokyo_iseki", "https://tokyo-iseki.metro.tokyo.lg.jp/"),
]
KEY = re.compile(
    r"市谷監獄|市谷刑務所|市ヶ谷刑務所|東京監獄|刑死|処刑|慰霊|"
    r"配置図|平面図|敷地|公図|地番|刑場|富久町|余丁町|市谷台町|"
    r"ichigaya|prison|penitentiary|execution|site.?plan|plot.?plan|layout",
    re.I,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def point_in_polygon(lon: float, lat: float, corners: list[list[float]]) -> bool:
    x, y = lon, lat
    inside = False
    pts = corners + [corners[0]]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if (y1 > y) != (y2 > y):
            cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < cross:
                inside = not inside
    return inside


def hav(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def capture_page(context, label: str, url: str, payload_root: Path) -> dict:
    page = await context.new_page()
    network: list[dict] = []
    payloads: list[dict] = []
    saved: set[str] = set()

    async def on_response(resp):
        rurl = resp.url
        ct = (resp.headers.get("content-type") or "").lower()
        row = {"url": rurl, "status": resp.status, "contentType": ct}
        network.append(row)
        interesting = KEY.search(rurl) or any(x in ct for x in ["json", "xml", "javascript", "geo+json", "text/html", "text/plain"])
        if resp.status != 200 or not interesting:
            return
        try:
            body = await resp.body()
        except Exception:
            return
        if not body or len(body) > 30_000_000:
            return
        digest = hashlib.sha256(body).hexdigest()
        if digest in saved:
            return
        saved.add(digest)
        suffix = ".bin"
        if "json" in ct: suffix = ".json"
        elif "xml" in ct: suffix = ".xml"
        elif "javascript" in ct: suffix = ".js"
        elif "html" in ct: suffix = ".html"
        elif "text/plain" in ct: suffix = ".txt"
        path = payload_root / f"{label}_{len(payloads):04d}_{digest[:12]}{suffix}"
        path.write_bytes(body)
        payloads.append({**row, "savedAs": str(path.relative_to(OUT)), "bytes": len(body), "sha256": digest})

    page.on("response", lambda r: asyncio.create_task(on_response(r)))
    errors: list[str] = []
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(12_000)
    except Exception as exc:
        response = None
        errors.append(f"goto: {type(exc).__name__}: {exc}")
    # Accept public-use terms if shown.
    for text in ["同意する", "同意します", "上記に同意", "はい"]:
        try:
            loc = page.get_by_text(text, exact=False)
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=5_000)
                await page.wait_for_timeout(3_000)
                break
        except Exception:
            pass
    # On Tokyo archaeological-map pages, use visible search inputs only.
    if "tokyo-iseki" in page.url:
        for query in QUERIES[:4]:
            try:
                inputs = page.locator("input[type=text],input:not([type]),textarea")
                for i in range(min(await inputs.count(), 30)):
                    el = inputs.nth(i)
                    if not await el.is_visible():
                        continue
                    ph = ((await el.get_attribute("placeholder")) or "") + ((await el.get_attribute("aria-label")) or "")
                    if any(k in ph for k in ["遺跡", "名称", "キーワード", "検索"]):
                        await el.fill(query)
                        await el.press("Enter")
                        await page.wait_for_timeout(5_000)
                        break
            except Exception as exc:
                errors.append(f"iseki search {query}: {type(exc).__name__}: {exc}")
    try:
        await page.screenshot(path=str(OUT / f"{label}.png"), full_page=True)
    except Exception as exc:
        errors.append(f"screenshot: {type(exc).__name__}: {exc}")
    try:
        html = await page.content()
        body_text = await page.locator("body").inner_text()
    except Exception:
        html, body_text = "", ""
    (OUT / f"{label}.html").write_text(html, encoding="utf-8", errors="replace")
    (OUT / f"{label}.txt").write_text(body_text, encoding="utf-8", errors="replace")
    try:
        links = await page.locator("a").evaluate_all(
            "els => els.slice(0,3000).map(a=>({text:(a.innerText||'').trim(),href:a.href||'',title:a.title||''}))"
        )
    except Exception:
        links = []
    hits = []
    for source, text in [("body", body_text), ("html", html), ("links", json.dumps(links, ensure_ascii=False))]:
        for m in KEY.finditer(text):
            hits.append({"source": source, "needle": m.group(0), "context": text[max(0,m.start()-500):m.start()+1800]})
            if len(hits) >= 300:
                break
    result = {
        "label": label,
        "requestedUrl": url,
        "finalUrl": page.url,
        "status": response.status if response else None,
        "title": await page.title(),
        "links": links,
        "network": network,
        "payloads": payloads,
        "hits": hits,
        "errors": errors,
    }
    (OUT / f"{label}-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    await page.close()
    return result


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "payloads").mkdir(exist_ok=True)
    (OUT / "gsi-images").mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1100})

        # GSI public address search to pick an imagery-discovery point.
        geocodes = []
        center = None
        for query in QUERIES:
            try:
                rr = await context.request.get(
                    "https://msearch.gsi.go.jp/address-search/AddressSearch",
                    params={"q": query}, timeout=30_000, fail_on_status_code=False,
                )
                data = await rr.json() if rr.status == 200 else []
                geocodes.append({"query": query, "status": rr.status, "results": data})
                if data and center is None:
                    coords = (data[0].get("geometry") or {}).get("coordinates")
                    if coords and len(coords) == 2:
                        center = (float(coords[0]), float(coords[1]))
            except Exception as exc:
                geocodes.append({"query": query, "error": f"{type(exc).__name__}: {exc}"})
        if center is None:
            center = GSI_FALLBACK
        lon, lat = center
        (OUT / "gsi-geocode.json").write_text(json.dumps(geocodes, ensure_ascii=False, indent=2), encoding="utf-8")

        # GSI aerial-photo acquisition.
        page_url = f"https://service.gsi.go.jp/map-photos/app/map?search=photo&search_date_from=1936&search_date_to=1950#15/{lat}/{lon}"
        page = await context.new_page()
        api_payloads = []
        async def on_gsi(resp):
            if "/app/api/" in resp.url and resp.status == 200 and "json" in (resp.headers.get("content-type") or ""):
                try: api_payloads.append({"url": resp.url, "payload": await resp.json()})
                except Exception: pass
        page.on("response", lambda r: asyncio.create_task(on_gsi(r)))
        await page.goto(page_url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(12_000)
        agree = page.locator("#terms_dialog #agree_btn:visible")
        if await agree.count():
            await agree.first.click(timeout=10_000)
            await page.wait_for_timeout(2_000)
        yf = page.locator('#photo select[aria-label="yearfrom"]')
        yt = page.locator('#photo select[aria-label="yearto"]')
        options = await yf.locator("option").evaluate_all("els=>els.map(e=>e.value).filter(Boolean)")
        if options: await yf.select_option(options[0])
        options2 = await yt.locator("option").evaluate_all("els=>els.map(e=>e.value).filter(Boolean)")
        if "1950" in options2: await yt.select_option("1950")
        elif options2: await yt.select_option(options2[-1])
        # all planners first, to include pre-war domestic series.
        try: await page.locator("#plannerSelector").select_option(value="")
        except Exception: pass
        await page.locator("#aerial_maplink").click(timeout=20_000)
        await page.wait_for_timeout(22_000)
        await page.screenshot(path=str(OUT / "gsi-search-results.png"), full_page=True)
        rows = await page.locator("#search_result_pane .ag-center-cols-container .ag-row").evaluate_all(
            "els=>els.map(e=>({rowId:e.getAttribute('row-id'),className:e.className,text:(e.innerText||'').trim()}))"
        )
        ids = []
        for row in rows:
            rid = row.get("rowId") or ""
            if rid.isdigit(): ids.append(int(rid))
            else:
                m = re.search(r"specid-(\d+)", row.get("className") or "")
                if m: ids.append(int(m.group(1)))
        for item in api_payloads:
            ids.extend(int(x) for x in re.findall(r'"(?:specification_id|id)"\s*:\s*(\d+)', json.dumps(item["payload"], ensure_ascii=False)))
        ids = sorted(set(ids))
        metadata, errors = [], []
        for photo_id in ids:
            try:
                rr = await context.request.get(
                    f"{GSI_API}/{photo_id}", headers={"Referer": page_url, "Accept": "application/json"},
                    timeout=30_000, fail_on_status_code=False,
                )
                if rr.status != 200: continue
                result = (await rr.json()).get("results") or {}
                result["apiPhotoId"] = photo_id
                corners = [result.get("geom_image_left_top_pos"), result.get("geom_image_right_top_pos"), result.get("geom_image_right_bottom_pos"), result.get("geom_image_left_bottom_pos")]
                corners = [c for c in corners if isinstance(c, list) and len(c) == 2]
                result["containsProxyPoint"] = len(corners) == 4 and point_in_polygon(lon, lat, corners)
                c = result.get("geom_center_pos") or []
                if len(c) == 2: result["centerDistanceM"] = hav(lon, lat, c[0], c[1])
                metadata.append(result)
            except Exception as exc:
                errors.append({"photoId": photo_id, "error": f"{type(exc).__name__}: {exc}"})
        metadata.sort(key=lambda r: (not r.get("containsProxyPoint", False), r.get("centerDistanceM", 1e99), r.get("search_date", "")))
        selected = [r for r in metadata if r.get("containsProxyPoint")][:14] or metadata[:10]
        downloads = []
        for item in selected:
            rel = item.get("url_image_standard")
            if not rel: continue
            url = urljoin(GSI_IMAGE_BASE, rel)
            rr = await context.request.get(url, headers={"Referer": page_url, "Accept": "image/*,*/*;q=.8"}, timeout=120_000, fail_on_status_code=False)
            body = await rr.body()
            row = {"photoId": item.get("apiPhotoId"), "referenceNumber": item.get("reference_number"), "courseNumber": item.get("course_number"), "photoNumber": item.get("photo_number"), "date": item.get("search_date"), "scale": item.get("scale"), "url": url, "status": rr.status, "bytes": len(body)}
            if rr.status == 200 and body[:3] == b"\xff\xd8\xff":
                name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{item.get('reference_number')}-{item.get('course_number')}-{item.get('photo_number')}_id{item.get('apiPhotoId')}_400dpi.jpg")
                path = OUT / "gsi-images" / name
                path.write_bytes(body)
                row["savedAs"] = str(path.relative_to(OUT)); row["sha256"] = hashlib.sha256(body).hexdigest()
            downloads.append(row)
        for name, data in [("gsi-result-rows.json", rows), ("gsi-photo-metadata.json", metadata), ("gsi-downloads.json", downloads), ("gsi-errors.json", errors)]:
            (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        await page.close()

        archive_results = []
        for label, url in ARCHIVE_TARGETS:
            archive_results.append(await capture_page(context, label, url, OUT / "payloads"))
        (OUT / "archive-results.json").write_text(json.dumps(archive_results, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {
            "proxyPoint": [lon, lat],
            "gsiMetadataCount": len(metadata),
            "gsiCoveringPhotoCount": sum(bool(x.get("containsProxyPoint")) for x in metadata),
            "gsiDownloadedCount": sum("savedAs" in x for x in downloads),
            "archivePageCount": len(archive_results),
            "archiveHitCount": sum(len(x.get("hits", [])) for x in archive_results),
            "qualityRule": "Prison extent, execution/memorial points, and later land use remain separate. No proxy point, archaeology extent, or post-war photo changes scoring or creates a boundary by itself.",
        }
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
            for path in sorted(OUT.rglob("*")):
                if path.is_file() and path.name != "SHA256SUMS.txt": f.write(f"{sha256(path)}  {path.relative_to(OUT)}\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        await context.close(); await browser.close()

if __name__ == "__main__": asyncio.run(main())
