#!/usr/bin/env python3
"""Discover and acquire adjacent GSI aerial photos for Omori POW boundary review.

The script uses the public GSI map-photo page, accepts the displayed terms, queries
public photo metadata around photo id 11027, and downloads public 400dpi standard
images for the same course M58-A-6 around photo number 135.

No login is used and no access control is bypassed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

OUT = Path("out-gsi-omori-adjacent")
PAGE_URL = "https://service.gsi.go.jp/map-photos/app/map?search=photo&id=11027&search_date_from=0000&search_date_to=9999#15/35.581911471/139.741696748"
API_BASE = "https://service.gsi.go.jp/map-photos/app/api/photo"
IMAGE_BASE = "https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/"
COURSE = "M58-A-6"
CENTER_PHOTO = 135
PHOTO_NUMBERS = {133, 134, 135, 136, 137}
ID_RANGE = range(10960, 11095)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    images_dir = OUT / "images"
    images_dir.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1500, "height": 1000})
        page = await context.new_page()
        await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(12_000)

        agree = page.locator("#terms_dialog #agree_btn:visible")
        if await agree.count():
            await agree.first.click(timeout=10_000)
            await page.wait_for_timeout(2_000)

        discovered: list[dict] = []
        errors: list[dict] = []
        for photo_id in ID_RANGE:
            try:
                response = await context.request.get(
                    f"{API_BASE}/{photo_id}",
                    headers={"Referer": PAGE_URL, "Accept": "application/json"},
                    timeout=20_000,
                    fail_on_status_code=False,
                )
                if response.status != 200:
                    continue
                payload = await response.json()
                result = payload.get("results") or {}
                if result.get("course_number") != COURSE:
                    continue
                photo_no = result.get("photo_number")
                if photo_no not in PHOTO_NUMBERS:
                    continue
                result["apiPhotoId"] = photo_id
                result["apiUrl"] = f"{API_BASE}/{photo_id}"
                discovered.append(result)
            except Exception as exc:
                errors.append({"photoId": photo_id, "error": f"{type(exc).__name__}: {exc}"})

        discovered.sort(key=lambda r: int(r.get("photo_number") or 0))
        (OUT / "adjacent-photo-metadata.json").write_text(
            json.dumps(discovered, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        downloads: list[dict] = []
        for item in discovered:
            photo_no = int(item["photo_number"])
            rel = item.get("url_image_standard")
            if not rel:
                downloads.append({"photoNumber": photo_no, "status": "standard_image_unavailable"})
                continue
            url = urljoin(IMAGE_BASE, rel)
            try:
                response = await context.request.get(
                    url,
                    headers={
                        "Referer": PAGE_URL,
                        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    },
                    timeout=120_000,
                    fail_on_status_code=False,
                )
                body = await response.body()
                row = {
                    "photoId": item["apiPhotoId"],
                    "photoNumber": photo_no,
                    "referenceNumber": item.get("reference_number"),
                    "courseNumber": item.get("course_number"),
                    "searchDate": item.get("search_date"),
                    "scale": item.get("scale"),
                    "url": url,
                    "status": response.status,
                    "contentType": response.headers.get("content-type"),
                    "bytes": len(body),
                }
                if response.status == 200 and body[:3] == b"\xff\xd8\xff":
                    path = images_dir / f"USA-M58-A-6-{photo_no}_400dpi.jpg"
                    path.write_bytes(body)
                    row["savedAs"] = str(path.relative_to(OUT))
                    row["sha256"] = hashlib.sha256(body).hexdigest()
                else:
                    row["error"] = "response was not a valid JPEG"
                downloads.append(row)
            except Exception as exc:
                downloads.append({"photoNumber": photo_no, "url": url, "error": f"{type(exc).__name__}: {exc}"})

        await page.screenshot(path=str(OUT / "gsi-page-after-consent.png"), full_page=True)
        (OUT / "downloads.json").write_text(json.dumps(downloads, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
        with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
            for path in sorted(images_dir.glob("*.jpg")):
                f.write(f"{sha256(path)}  {path.name}\n")

        summary = {
            "course": COURSE,
            "centerPhoto": CENTER_PHOTO,
            "queriedIdRange": [ID_RANGE.start, ID_RANGE.stop - 1],
            "discovered": [
                {
                    "photoId": r.get("apiPhotoId"),
                    "photoNumber": r.get("photo_number"),
                    "date": r.get("search_date"),
                    "scale": r.get("scale"),
                    "center": r.get("geom_center_pos"),
                    "corners": {
                        "leftTop": r.get("geom_image_left_top_pos"),
                        "leftBottom": r.get("geom_image_left_bottom_pos"),
                        "rightTop": r.get("geom_image_right_top_pos"),
                        "rightBottom": r.get("geom_image_right_bottom_pos"),
                    },
                }
                for r in discovered
            ],
            "downloadedCount": sum(1 for d in downloads if d.get("savedAs")),
            "downloads": downloads,
            "qualityRule": "Adjacent photos are independent views for review; they do not automatically promote the boundary or change scoring.",
        }
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
