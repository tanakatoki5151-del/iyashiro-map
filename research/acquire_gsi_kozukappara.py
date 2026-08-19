#!/usr/bin/env python3
"""Acquire public GSI historical aerial photos around Kozukappara.

The proxy point is used only to discover imagery. It is not treated as the
historical execution-ground boundary. The script accepts the displayed GSI
terms, inspects the currently available year/planner options instead of assuming
a hard-coded year, and downloads public standard images in the same session.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

OUT = Path("out-gsi-kozukappara")
CENTER_LON = 139.797806
CENTER_LAT = 35.732270
PAGE_URL = f"https://service.gsi.go.jp/map-photos/app/map?search=photo#15/{CENTER_LAT}/{CENTER_LON}"
API_BASE = "https://service.gsi.go.jp/map-photos/app/api/photo"
IMAGE_BASE = "https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/"


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
            x_cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_cross:
                inside = not inside
    return inside


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def option_inventory(locator):
    return await locator.locator("option").evaluate_all(
        "els => els.map(e=>({text:(e.innerText||e.textContent||'').trim(),value:e.value,selected:e.selected}))"
    )


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    images_dir = OUT / "images"
    images_dir.mkdir(exist_ok=True)
    summary: dict = {
        "proxyPoint": [CENTER_LON, CENTER_LAT],
        "qualityRule": "The proxy point selects imagery only. Any Kozukappara boundary requires historical-map, official-dimension and archaeological-context corroboration. Acquisition alone never changes scoring.",
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1100})
        page = await context.new_page()
        api_payloads: list[dict] = []
        network_urls: list[dict] = []

        async def on_response(response):
            if "/app/api/" not in response.url:
                return
            row = {"url": response.url, "status": response.status, "contentType": response.headers.get("content-type")}
            network_urls.append(row)
            if response.status == 200 and "json" in (response.headers.get("content-type") or ""):
                try:
                    api_payloads.append({"url": response.url, "payload": await response.json()})
                except Exception:
                    pass

        page.on("response", lambda r: asyncio.create_task(on_response(r)))
        try:
            await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=120_000)
            await page.wait_for_timeout(12_000)
            agree = page.locator("#terms_dialog #agree_btn:visible")
            if await agree.count():
                await agree.first.click(timeout=10_000)
                await page.wait_for_timeout(3_000)
            summary["acceptedTerms"] = True

            year_from = page.locator('#photo select[aria-label="yearfrom"]')
            year_to = page.locator('#photo select[aria-label="yearto"]')
            planner = page.locator("#plannerSelector")
            from_options = await option_inventory(year_from)
            to_options = await option_inventory(year_to)
            planner_options = await option_inventory(planner)
            (OUT / "search-options.json").write_text(
                json.dumps({"yearFrom": from_options, "yearTo": to_options, "planner": planner_options}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            def numeric_values(rows):
                result=[]
                for row in rows:
                    try:
                        result.append((int(row["value"]), row["value"], row["text"]))
                    except (ValueError, TypeError):
                        pass
                return sorted(result)

            from_numeric = numeric_values(from_options)
            to_numeric = numeric_values(to_options)
            from_choice = next((x for x in from_numeric if x[0] >= 1935), from_numeric[0] if from_numeric else None)
            to_candidates = [x for x in to_numeric if x[0] <= 1950]
            to_choice = to_candidates[-1] if to_candidates else (to_numeric[-1] if to_numeric else None)
            if from_choice:
                await year_from.select_option(from_choice[1])
            if to_choice:
                await year_to.select_option(to_choice[1])
            summary["selectedYearFrom"] = from_choice
            summary["selectedYearTo"] = to_choice

            # Use the explicit all-planners option when available; otherwise retain the first option.
            planner_choice = next(
                (o for o in planner_options if any(k in o["text"] for k in ["全て", "すべて", "指定なし"]) or o["value"] in ["", "all", "0"]),
                planner_options[0] if planner_options else None,
            )
            if planner_choice:
                await planner.select_option(planner_choice["value"])
            summary["selectedPlanner"] = planner_choice

            await page.locator("#aerial_maplink").click(timeout=20_000)
            await page.wait_for_timeout(25_000)
            await page.screenshot(path=str(OUT / "search-results.png"), full_page=True)
            (OUT / "page.html").write_text(await page.content(), encoding="utf-8")
            (OUT / "body.txt").write_text(await page.locator("body").inner_text(), encoding="utf-8")

            rows = await page.locator("#search_result_pane .ag-center-cols-container .ag-row").evaluate_all(
                "els => els.map(e => ({rowId:e.getAttribute('row-id'), className:e.className, text:(e.innerText||'').trim()}))"
            )
            (OUT / "result-rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            ids: list[int] = []
            for row in rows:
                rid = row.get("rowId") or ""
                if rid.isdigit():
                    ids.append(int(rid))
                else:
                    m = re.search(r"specid-(\d+)", row.get("className") or "")
                    if m:
                        ids.append(int(m.group(1)))
            for item in api_payloads:
                text = json.dumps(item["payload"], ensure_ascii=False)
                ids.extend(int(x) for x in re.findall(r'"(?:specification_id|id)"\s*:\s*(\d+)', text))
            ids.extend(int(x) for x in re.findall(r"specid-(\d+)", await page.content()))
            ids = sorted(set(ids))

            metadata: list[dict] = []
            errors: list[dict] = []
            for photo_id in ids:
                try:
                    response = await context.request.get(
                        f"{API_BASE}/{photo_id}",
                        headers={"Referer": PAGE_URL, "Accept": "application/json"},
                        timeout=30_000,
                        fail_on_status_code=False,
                    )
                    if response.status != 200:
                        errors.append({"photoId": photo_id, "status": response.status})
                        continue
                    payload = await response.json()
                    result = payload.get("results") or {}
                    if not result:
                        continue
                    result["apiPhotoId"] = photo_id
                    corners = [
                        result.get("geom_image_left_top_pos"), result.get("geom_image_right_top_pos"),
                        result.get("geom_image_right_bottom_pos"), result.get("geom_image_left_bottom_pos"),
                    ]
                    corners = [c for c in corners if isinstance(c, list) and len(c) == 2]
                    result["containsProxyPoint"] = len(corners) == 4 and point_in_polygon(CENTER_LON, CENTER_LAT, corners)
                    center = result.get("geom_center_pos") or [None, None]
                    if len(center) == 2 and all(isinstance(v, (int, float)) for v in center):
                        result["centerDistanceM"] = haversine_m(CENTER_LON, CENTER_LAT, center[0], center[1])
                    metadata.append(result)
                except Exception as exc:
                    errors.append({"photoId": photo_id, "error": f"{type(exc).__name__}: {exc}"})

            metadata.sort(key=lambda r: (not r.get("containsProxyPoint", False), r.get("search_date", "9999"), r.get("centerDistanceM", 1e99)))
            (OUT / "photo-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT / "network-api.json").write_text(json.dumps(network_urls, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT / "captured-api-payloads.json").write_text(json.dumps(api_payloads, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

            selected = [r for r in metadata if r.get("containsProxyPoint")]
            if not selected:
                selected = metadata[:12]
            selected = selected[:20]
            downloads: list[dict] = []
            for item in selected:
                rel = item.get("url_image_standard")
                if not rel:
                    downloads.append({"photoId": item.get("apiPhotoId"), "status": "no_standard_image"})
                    continue
                url = urljoin(IMAGE_BASE, rel)
                response = await context.request.get(
                    url,
                    headers={"Referer": PAGE_URL, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
                    timeout=120_000,
                    fail_on_status_code=False,
                )
                body = await response.body()
                row = {
                    "photoId": item.get("apiPhotoId"), "referenceNumber": item.get("reference_number"),
                    "courseNumber": item.get("course_number"), "photoNumber": item.get("photo_number"),
                    "date": item.get("search_date"), "scale": item.get("scale"),
                    "containsProxyPoint": item.get("containsProxyPoint"), "centerDistanceM": item.get("centerDistanceM"),
                    "url": url, "status": response.status, "contentType": response.headers.get("content-type"), "bytes": len(body),
                }
                if response.status == 200 and body[:3] == b"\xff\xd8\xff":
                    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{item.get('reference_number')}-{item.get('course_number')}-{item.get('photo_number')}_id{item.get('apiPhotoId')}_400dpi.jpg")
                    path = images_dir / name
                    path.write_bytes(body)
                    row["savedAs"] = str(path.relative_to(OUT))
                    row["sha256"] = hashlib.sha256(body).hexdigest()
                else:
                    row["error"] = "not a valid JPEG"
                downloads.append(row)

            (OUT / "downloads.json").write_text(json.dumps(downloads, ensure_ascii=False, indent=2), encoding="utf-8")
            with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
                for path in sorted(images_dir.glob("*.jpg")):
                    f.write(f"{sha256(path)}  {path.name}\n")
            summary.update({
                "resultRowCount": len(rows), "metadataCount": len(metadata),
                "coveringPhotoCount": sum(1 for r in metadata if r.get("containsProxyPoint")),
                "selectedPhotoIds": [r.get("apiPhotoId") for r in selected],
                "downloadedCount": sum(1 for d in downloads if d.get("savedAs")),
                "selectedPhotoDates": sorted(set(str(r.get("search_date")) for r in selected if r.get("search_date"))),
            })
        except Exception as exc:
            summary["error"] = f"{type(exc).__name__}: {exc}"
            try:
                await page.screenshot(path=str(OUT / "error.png"), full_page=True)
                (OUT / "error-page.html").write_text(await page.content(), encoding="utf-8")
            except Exception:
                pass
        finally:
            (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
