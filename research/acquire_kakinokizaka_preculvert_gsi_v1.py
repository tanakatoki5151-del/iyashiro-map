#!/usr/bin/env python3
"""Acquire GSI pre-culvert aerial photographs for the Kakinokizaka tributary.

This is an independent historical-source lane for validating whether the 1972+
current culvert trace is a defensible proxy for the pre-culvert open channel.
Photographs and footprints are acquired from GSI's public map/photo service.
No historical centerline is promoted by this acquisition step.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

OUT = Path("out-kakinokizaka-preculvert-gsi-v1")
GSI_PAGE = (
    "https://service.gsi.go.jp/map-photos/app/map?search=photo"
    "&search_date_from=1945&search_date_to=1971#14/35.627/139.673"
)
GSI_API = "https://service.gsi.go.jp/map-photos/app/api/photo"
GSI_IMAGE_BASE = "https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/img/"
OVERPASS = "https://overpass.kumi.systems/api/interpreter"
CULVERT_WAY_ID = 588191048
BBOX = {"lon_min": 139.6625, "lon_max": 139.6815, "lat_min": 35.6165, "lat_max": 35.6385}
CELLS = [
    {"cellId": "g233-217", "town": "東が丘一丁目", "lat": 35.630340, "lon": 139.669621},
    {"cellId": "g239-220", "town": "柿の木坂二丁目", "lat": 35.624952, "lon": 139.672934},
]
ERAS = [
    {"key": "postwar_1945_1950", "start": 1945, "end": 1950, "limit": 4},
    {"key": "midcentury_1951_1960", "start": 1951, "end": 1960, "limit": 3},
    {"key": "preculvert_1961_1971", "start": 1961, "end": 1971, "limit": 5},
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def hav(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))


def point_in_poly(lon: float, lat: float, corners: list[list[float]]) -> bool:
    inside = False
    pts = corners + [corners[0]]
    for (x1,y1),(x2,y2) in zip(pts, pts[1:]):
        if (y1 > lat) != (y2 > lat):
            xc = (x2-x1)*(lat-y1)/(y2-y1) + x1
            if lon < xc:
                inside = not inside
    return inside


def sample_points(coords: list[list[float]], max_points: int = 30) -> list[dict]:
    if not coords:
        return []
    if len(coords) <= max_points:
        idxs = range(len(coords))
    else:
        idxs = sorted(set(round(i*(len(coords)-1)/(max_points-1)) for i in range(max_points)))
    return [{"id": f"culvert-{i:02d}", "lon": coords[j][0], "lat": coords[j][1], "role": "current_culvert_sample"} for i,j in enumerate(idxs)]


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    images = OUT / "images"
    images.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP", viewport={"width": 1500, "height": 1000})
        page = await context.new_page()
        await page.goto(GSI_PAGE, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(5000)
        agree = page.locator("#terms_dialog #agree_btn:visible")
        accepted = False
        if await agree.count():
            await agree.first.click(timeout=10_000)
            accepted = True
            await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT / "gsi-search-page.png"), full_page=True)

        # Acquire the current culvert trace independently for photo-coverage scoring.
        q = f"[out:json][timeout:60];way({CULVERT_WAY_ID});out meta tags geom;"
        ov = await context.request.post(OVERPASS, form={"data": q}, headers={"Accept": "application/json"}, timeout=120_000, fail_on_status_code=False)
        ov_body = await ov.body()
        (OUT / "culvert-overpass.json").write_bytes(ov_body)
        try:
            ov_json = json.loads(ov_body.decode("utf-8"))
        except Exception:
            ov_json = {}
        coords = []
        els = ov_json.get("elements") or []
        if els:
            coords = [[float(p["lon"]), float(p["lat"])] for p in els[0].get("geometry") or [] if "lon" in p and "lat" in p]
        samples = sample_points(coords)
        points = samples + [{"id": c["cellId"], "lon": c["lon"], "lat": c["lat"], "role": "target_cell_center"} for c in CELLS]

        # Search the official public photo API using the full corridor bbox.
        rows = []
        offset = 0
        api_calls = []
        while True:
            params = {
                "limit": 200,
                "offset": offset,
                "rnem": 0,
                "cnem": 0,
                "search_date_from": 1945,
                "search_date_to": 1971,
                "color_type_ids": [1,2],
                "scale_from": 0,
                "scale_to": 99999999,
                **BBOX,
            }
            url = f"{GSI_API}?{urllib.parse.urlencode(params, doseq=True)}"
            r = await context.request.get(url, headers={"Referer": GSI_PAGE, "Accept": "application/json"}, timeout=120_000, fail_on_status_code=False)
            if r.status != 200:
                api_calls.append({"url": url, "status": r.status})
                break
            payload = await r.json()
            api_calls.append({"url": url, "status": r.status, "resultset": payload.get("resultset")})
            result = payload.get("results") or []
            rows.extend(result)
            rs = payload.get("resultset") or {}
            count = int(rs.get("count") or len(result))
            total = int(rs.get("total_count") or len(result))
            offset += count
            if count == 0 or offset >= total:
                break
        ids = sorted({int(x["specification_id"]) for x in rows if x.get("specification_id") not in (None, "")})
        metadata = []
        for pid in ids:
            r = await context.request.get(f"{GSI_API}/{pid}", headers={"Referer": GSI_PAGE, "Accept": "application/json"}, timeout=60_000, fail_on_status_code=False)
            if r.status != 200:
                continue
            try:
                item = (await r.json()).get("results") or {}
            except Exception:
                continue
            if not item:
                continue
            corners = [item.get("geom_image_left_top_pos"), item.get("geom_image_right_top_pos"), item.get("geom_image_right_bottom_pos"), item.get("geom_image_left_bottom_pos")]
            corners = [x for x in corners if isinstance(x, list) and len(x) == 2]
            covered = []
            if len(corners) == 4:
                for p in points:
                    if point_in_poly(p["lon"], p["lat"], corners):
                        covered.append(p["id"])
            center = item.get("geom_center_pos") or [None,None]
            corridor_center_distance = None
            if len(center) == 2 and all(isinstance(v, (int,float)) for v in center):
                corridor_center_distance = hav(139.6730,35.6270,float(center[0]),float(center[1]))
            item["apiPhotoId"] = pid
            item["coveredPointIds"] = covered
            item["coveredCulvertSampleCount"] = sum(1 for x in covered if x.startswith("culvert-"))
            item["coversCellG233217"] = "g233-217" in covered
            item["coversCellG239220"] = "g239-220" in covered
            item["corridorCenterDistanceM"] = corridor_center_distance
            metadata.append(item)

        def year_of(item: dict) -> int:
            s = str(item.get("search_date") or item.get("photograph_date") or "")
            m = re.search(r"(19\d{2})", s)
            return int(m.group(1)) if m else 0

        selected = []
        era_summary = []
        for era in ERAS:
            subset = [x for x in metadata if era["start"] <= year_of(x) <= era["end"]]
            subset.sort(key=lambda x: (-x.get("coveredCulvertSampleCount",0), not (x.get("coversCellG233217") or x.get("coversCellG239220")), x.get("corridorCenterDistanceM") or 1e99, year_of(x)))
            take = subset[:era["limit"]]
            selected.extend(take)
            era_summary.append({
                **era,
                "availablePhotoCount": len(subset),
                "selectedPhotoIds": [x.get("apiPhotoId") for x in take],
                "bestCoveredCulvertSamples": take[0].get("coveredCulvertSampleCount",0) if take else 0,
            })

        # De-duplicate and download selected standard images.
        unique = []
        seen = set()
        for x in selected:
            pid = x.get("apiPhotoId")
            if pid in seen:
                continue
            seen.add(pid); unique.append(x)
        downloads = []
        for item in unique:
            rel = item.get("url_image_standard")
            if not rel:
                downloads.append({"photoId": item.get("apiPhotoId"), "status": "no_standard_image_url"})
                continue
            url = urljoin(GSI_IMAGE_BASE, rel)
            r = await context.request.get(url, headers={"Referer": GSI_PAGE, "Accept": "image/*,*/*;q=0.8"}, timeout=120_000, fail_on_status_code=False)
            body = await r.body()
            row = {
                "photoId": item.get("apiPhotoId"),
                "referenceNumber": item.get("reference_number"),
                "courseNumber": item.get("course_number"),
                "photoNumber": item.get("photo_number"),
                "date": item.get("search_date"),
                "scale": item.get("scale"),
                "coveredCulvertSampleCount": item.get("coveredCulvertSampleCount"),
                "coversCellG233217": item.get("coversCellG233217"),
                "coversCellG239220": item.get("coversCellG239220"),
                "footprintCorners": [item.get("geom_image_left_top_pos"), item.get("geom_image_right_top_pos"), item.get("geom_image_right_bottom_pos"), item.get("geom_image_left_bottom_pos")],
                "url": url,
                "status": r.status,
                "bytes": len(body),
            }
            if r.status == 200 and body[:3] == b"\xff\xd8\xff":
                name = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{item.get('reference_number')}-{item.get('course_number')}-{item.get('photo_number')}_id{item.get('apiPhotoId')}_{year_of(item)}.jpg")
                p = images / name
                p.write_bytes(body)
                row["savedAs"] = str(p.relative_to(OUT))
                row["sha256"] = hashlib.sha256(body).hexdigest()
            downloads.append(row)

        await context.close(); await browser.close()

    # Keep metadata compact enough for downstream review while preserving raw keys.
    (OUT / "photo-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "downloads.json").write_text(json.dumps(downloads, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "version": "v10-kakinokizaka-preculvert-gsi-v1-20260815",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "termsAcceptedInBrowser": accepted,
        "bbox": BBOX,
        "culvertWayId": CULVERT_WAY_ID,
        "culvertSampleCount": len(samples),
        "targetCells": CELLS,
        "apiCallCount": len(api_calls),
        "searchResultRows": len(rows),
        "photoMetadataCount": len(metadata),
        "eraSummary": era_summary,
        "downloadedCount": sum(1 for x in downloads if x.get("savedAs")),
        "downloads": downloads,
        "policy": {
            "source": "GSI public historical aerial photo service",
            "historicalCenterlineVerified": False,
            "formalHistoricalGeometryPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextGate": "visual/geometry review of pre-culvert channel in downloaded photos; georeference candidate channel and compare residuals to current culvert proxy",
        },
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "api-calls.json").write_text(json.dumps(api_calls, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for p in sorted(OUT.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{sha(p)}  {p.relative_to(OUT)}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
