#!/usr/bin/env python3
"""ECOSCAPE F15 automated, license-aware open imagery pipeline.

Sources
- Wikimedia Commons geotagged images with an explicit reusable license.
- Mapillary Graph API when MAPILLARY_ACCESS_TOKEN is configured.

Google imagery is never fetched, stored, or analyzed. Image bytes are used only
inside a temporary directory and are deleted before release artifacts are made.
Only source/license records and numerical model proxies are retained.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from PIL import Image

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MAPILLARY_API = "https://graph.mapillary.com/images"
USER_AGENT = "ECOSCAPE-GreenQuality-F15/1.0 (license-aware research)"
ALLOWED_LICENSE = re.compile(r"(CC\s*BY(?:-SA)?|CC0|PUBLIC\s*DOMAIN|PDM)", re.I)
BLOCKED_LICENSE = re.compile(r"(NC|NONCOMMERCIAL|ND|NO\s*DERIVATIVES|ALL\s*RIGHTS\s*RESERVED)", re.I)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def text_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return "" if value is None else str(value)


def allowed_license(short_name: str, usage_terms: str) -> bool:
    combined = f"{short_name} {usage_terms}".strip()
    return bool(ALLOWED_LICENSE.search(combined)) and not bool(BLOCKED_LICENSE.search(combined))


def commons_candidates(case: pd.Series, radius_m: int, limit: int) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "geosearch",
        "ggsprimary": "all",
        "ggsnamespace": "6",
        "ggsradius": min(radius_m, 10_000),
        "ggscoord": f"{float(case.lat)}|{float(case.lng)}",
        "ggslimit": min(limit, 100),
        "prop": "imageinfo|coordinates",
        "iiprop": "url|extmetadata|timestamp|mime|size",
        "iiurlwidth": 1024,
        "colimit": "max",
    }
    response = requests.get(COMMONS_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=45)
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for page in response.json().get("query", {}).get("pages", []):
        infos = page.get("imageinfo") or []
        coords = page.get("coordinates") or []
        if not infos or not coords:
            continue
        info, coord = infos[0], coords[0]
        metadata = info.get("extmetadata") or {}
        license_short = text_value(metadata.get("LicenseShortName"))
        usage_terms = text_value(metadata.get("UsageTerms"))
        if not allowed_license(license_short, usage_terms):
            continue
        if not str(info.get("mime", "")).startswith("image/"):
            continue
        image_url = info.get("thumburl") or info.get("url")
        if not image_url:
            continue
        lat, lon = float(coord["lat"]), float(coord["lon"])
        distance = haversine_m(float(case.lat), float(case.lng), lat, lon)
        if distance > radius_m:
            continue
        rows.append({
            "caseId": case.caseId,
            "canonicalCellId": case.canonicalCellId,
            "source": "WIKIMEDIA_COMMONS",
            "sourceId": str(page.get("pageid", "")),
            "title": str(page.get("title", "")),
            "lat": lat,
            "lng": lon,
            "distanceM": round(distance, 2),
            "capturedOrUploadedAt": info.get("timestamp", ""),
            "imageUrl": image_url,
            "pageUrl": info.get("descriptionurl", ""),
            "license": license_short or usage_terms,
            "artist": text_value(metadata.get("Artist")),
            "credit": text_value(metadata.get("Credit")),
            "captureDateConfidence": "UPLOAD_TIMESTAMP_ONLY",
        })
    return rows


def mapillary_candidates(case: pd.Series, radius_m: int, limit: int, token: str) -> list[dict[str, Any]]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / max(111_320.0 * math.cos(math.radians(float(case.lat))), 1.0)
    bbox = ",".join(map(str, [float(case.lng)-dlon, float(case.lat)-dlat, float(case.lng)+dlon, float(case.lat)+dlat]))
    params = {
        "access_token": token,
        "bbox": bbox,
        "limit": min(limit, 100),
        "fields": "id,computed_geometry,captured_at,thumb_1024_url,compass_angle,sequence",
    }
    response = requests.get(MAPILLARY_API, params=params, timeout=45)
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for item in response.json().get("data", []):
        coords = (item.get("computed_geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or not item.get("thumb_1024_url"):
            continue
        lon, lat = map(float, coords[:2])
        distance = haversine_m(float(case.lat), float(case.lng), lat, lon)
        if distance > radius_m:
            continue
        rows.append({
            "caseId": case.caseId,
            "canonicalCellId": case.canonicalCellId,
            "source": "MAPILLARY",
            "sourceId": str(item.get("id", "")),
            "title": "",
            "lat": lat,
            "lng": lon,
            "distanceM": round(distance, 2),
            "capturedOrUploadedAt": item.get("captured_at", ""),
            "imageUrl": item["thumb_1024_url"],
            "pageUrl": f"https://www.mapillary.com/app/?pKey={item.get('id','')}",
            "license": "MAPILLARY_PLATFORM_LICENSE_RECORD_REQUIRED",
            "artist": "",
            "credit": "Mapillary contributor",
            "captureDateConfidence": "CAPTURE_TIMESTAMP",
        })
    return rows


def probe(args: argparse.Namespace) -> None:
    queue = pd.read_csv(args.queue)
    required = {"caseId", "canonicalCellId", "lat", "lng"}
    missing = sorted(required - set(queue.columns))
    if missing:
        raise SystemExit(f"Missing queue columns: {missing}")
    token = os.environ.get("MAPILLARY_ACCESS_TOKEN", "").strip()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for case in queue.itertuples(index=False):
        series = pd.Series(case._asdict())
        radius = int(getattr(case, "analysisRadiusM", args.radius) or args.radius)
        source_limit = max(args.max_images * 5, 20)
        try:
            rows.extend(commons_candidates(series, radius, source_limit))
        except Exception as exc:
            errors.append({"caseId": case.caseId, "source": "WIKIMEDIA_COMMONS", "error": repr(exc)})
        if token:
            try:
                rows.extend(mapillary_candidates(series, radius, source_limit, token))
            except Exception as exc:
                errors.append({"caseId": case.caseId, "source": "MAPILLARY", "error": repr(exc)})

    columns = [
        "caseId","canonicalCellId","source","sourceId","title","lat","lng","distanceM",
        "capturedOrUploadedAt","imageUrl","pageUrl","license","artist","credit","captureDateConfidence",
    ]
    candidates = pd.DataFrame(rows, columns=columns).sort_values(["caseId", "distanceM", "source"], kind="stable") if rows else pd.DataFrame(columns=columns)
    selected = candidates.groupby("caseId", group_keys=False).head(args.max_images).reset_index(drop=True) if len(candidates) else candidates.copy()
    coverage = queue[["caseId", "canonicalCellId"]].copy()
    counts = selected.groupby("caseId").size().rename("selectedImages") if len(selected) else pd.Series(dtype=int, name="selectedImages")
    sources = selected.groupby("caseId")["source"].agg(lambda x: ",".join(sorted(set(x)))).rename("sources") if len(selected) else pd.Series(dtype=str, name="sources")
    coverage = coverage.merge(counts, on="caseId", how="left").merge(sources, on="caseId", how="left")
    coverage["selectedImages"] = coverage["selectedImages"].fillna(0).astype(int)
    coverage["sources"] = coverage["sources"].fillna("")
    coverage["readyForAutomatedAnalysis"] = coverage["selectedImages"] > 0

    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(out / "F15_OPEN_IMAGE_CANDIDATES.csv", index=False)
    selected.to_csv(out / "F15_SELECTED_IMAGE_MANIFEST.csv", index=False)
    coverage.to_csv(out / "F15_CASE_COVERAGE.csv", index=False)
    (out / "F15_PROBE_ERRORS.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2)+"\n")
    audit = {
        "buildId": "ecoscape-open-imagery-f15-probe-20260820",
        "cases": int(len(queue)),
        "mapillaryTokenPresent": bool(token),
        "candidateImages": int(len(candidates)),
        "selectedImages": int(len(selected)),
        "casesReadyForAutomatedAnalysis": int(coverage["readyForAutomatedAnalysis"].sum()),
        "commonsSelectedImages": int((selected["source"] == "WIKIMEDIA_COMMONS").sum()) if len(selected) else 0,
        "mapillarySelectedImages": int((selected["source"] == "MAPILLARY").sum()) if len(selected) else 0,
        "errorCount": len(errors),
        "googleImageryUsed": False,
        "imageBytesPersisted": 0,
        "rankingEffect": "none",
        "scoringEffect": "none",
        "candidateOverride": 0,
        "releaseState": "READY_FOR_AUTOMATED_ANALYSIS" if coverage["readyForAutomatedAnalysis"].any() else "NO_OPEN_IMAGE_COVERAGE",
    }
    (out / "F15_COVERAGE_AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


def hsv_fractions(image: Image.Image) -> dict[str, float]:
    rgb = np.asarray(image.resize((512, 512)).convert("RGB"), dtype=np.float32) / 255.0
    import colorsys
    flat = rgb.reshape(-1, 3)
    hsv = np.array([colorsys.rgb_to_hsv(*pixel) for pixel in flat], dtype=np.float32)
    h, s, v = hsv[:,0], hsv[:,1], hsv[:,2]
    green = ((h >= 0.18) & (h <= 0.48) & (s >= 0.20) & (v >= 0.12)).mean()
    dark = (v <= 0.20).mean()
    top = rgb[:256].reshape(-1, 3)
    top_hsv = np.array([colorsys.rgb_to_hsv(*pixel) for pixel in top], dtype=np.float32)
    sky_blue = ((top_hsv[:,0] >= 0.50) & (top_hsv[:,0] <= 0.72) & (top_hsv[:,1] >= 0.12) & (top_hsv[:,2] >= 0.45)).mean()
    return {"greenPixelFraction": float(green), "darkPixelFraction": float(dark), "topHalfBlueSkyProxy": float(sky_blue)}


def analyze(args: argparse.Namespace) -> None:
    manifest = pd.read_csv(args.manifest)
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    if manifest.empty:
        (out / "F15_ANALYSIS_AUDIT.json").write_text(json.dumps({"imagesAnalyzed":0,"casesAnalyzed":0,"imageBytesPersisted":0,"releaseState":"NO_IMAGES"}, indent=2)+"\n")
        return
    import torch
    from transformers import CLIPModel, CLIPProcessor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_name = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(model_name).to(device).eval()
    processor = CLIPProcessor.from_pretrained(model_name)
    groups = {
        "scene": ["a street-level outdoor residential scene", "an aerial or satellite image", "an indoor scene", "a close-up object or portrait"],
        "vegetation": ["well-maintained healthy urban vegetation", "overgrown neglected vegetation", "dead or declining vegetation"],
        "cleanliness": ["a clean well-maintained street", "a street with visible litter or dumping"],
        "openness": ["an open street with visible sky and airflow", "a narrow enclosed street canyon"],
    }
    def probs(image: Image.Image, prompts: list[str]) -> list[float]:
        inputs = processor(text=prompts, images=image, return_tensors="pt", padding=True)
        inputs = {k:v.to(device) for k,v in inputs.items()}
        with torch.no_grad():
            values = model(**inputs).logits_per_image.softmax(dim=1)[0]
        return [float(v) for v in values.cpu()]

    rows: list[dict[str, Any]] = []
    session = requests.Session(); session.headers["User-Agent"] = USER_AGENT
    tmp = Path(tempfile.mkdtemp(prefix="ecoscape-f15-"))
    try:
        for item in manifest.itertuples(index=False):
            record = item._asdict()
            try:
                response = session.get(record["imageUrl"], timeout=60); response.raise_for_status()
                image = Image.open(io.BytesIO(response.content)).convert("RGB")
                scene, vegetation = probs(image, groups["scene"]), probs(image, groups["vegetation"])
                cleanliness, openness = probs(image, groups["cleanliness"]), probs(image, groups["openness"])
                pixels = hsv_fractions(image)
                rows.append({
                    **{k:record.get(k) for k in ("caseId","canonicalCellId","source","sourceId","distanceM","capturedOrUploadedAt","pageUrl","license","artist","credit","captureDateConfidence")},
                    "streetSceneProbability": scene[0], "aerialProbability": scene[1], "indoorProbability": scene[2], "closeupProbability": scene[3],
                    "healthyMaintenanceProbability": vegetation[0], "overgrownProbability": vegetation[1], "deadDecliningProbability": vegetation[2],
                    "cleanStreetProbability": cleanliness[0], "litterProbability": cleanliness[1],
                    "openAirProbability": openness[0], "enclosedCanyonProbability": openness[1],
                    **pixels,
                    "analysisUsable": scene[0] >= 0.45,
                    "evidenceMaturity": "OPEN_IMAGE_MODEL_PROXY",
                })
            except Exception as exc:
                rows.append({"caseId":record.get("caseId"),"canonicalCellId":record.get("canonicalCellId"),"source":record.get("source"),"sourceId":record.get("sourceId"),"pageUrl":record.get("pageUrl"),"license":record.get("license"),"analysisUsable":False,"analysisError":repr(exc),"evidenceMaturity":"ERROR"})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    images = pd.DataFrame(rows); images.to_csv(out / "F15_IMAGE_LEVEL_FEATURES.csv", index=False)
    usable = images[images["analysisUsable"].fillna(False).astype(bool)].copy()
    if len(usable):
        cases = usable.groupby(["caseId","canonicalCellId"], as_index=False).agg(
            usableImages=("sourceId","count"), greenPixelFraction=("greenPixelFraction","mean"), topHalfBlueSkyProxy=("topHalfBlueSkyProxy","mean"),
            healthyMaintenanceProbability=("healthyMaintenanceProbability","mean"), overgrownProbability=("overgrownProbability","mean"), deadDecliningProbability=("deadDecliningProbability","mean"),
            cleanStreetProbability=("cleanStreetProbability","mean"), litterProbability=("litterProbability","mean"), openAirProbability=("openAirProbability","mean"), enclosedCanyonProbability=("enclosedCanyonProbability","mean"),
        )
        cases["imageEvidenceStatus"] = np.where(cases["usableImages"] >= 2, "MULTI_IMAGE_PROXY", "SINGLE_IMAGE_PROXY")
    else:
        cases = pd.DataFrame(columns=["caseId","canonicalCellId","usableImages","imageEvidenceStatus"])
    cases.to_csv(out / "F15_CASE_LEVEL_FEATURES.csv", index=False)
    audit = {"buildId":"ecoscape-open-imagery-f15-analysis-20260820","imagesAttempted":int(len(manifest)),"imagesAnalyzed":int(len(images)),"usableStreetImages":int(len(usable)),"casesAnalyzed":int(cases["caseId"].nunique()) if len(cases) else 0,"googleImageryUsed":False,"imageBytesPersisted":0,"rankingEffect":"none","scoringEffect":"none","candidateOverride":0,"releaseState":"MODEL_PROXY_INFORMATION_ONLY"}
    (out / "F15_ANALYSIS_AUDIT.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


def self_test(_: argparse.Namespace) -> None:
    assert haversine_m(35,139,35,139) == 0
    assert allowed_license("CC BY-SA 4.0", "")
    assert allowed_license("CC0", "")
    assert not allowed_license("CC BY-NC", "")
    assert not allowed_license("All rights reserved", "")
    print(json.dumps({"tests":5,"passed":5,"googleImageryUsed":False,"rankingEffect":"none","scoringEffect":"none","candidateOverride":0}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe"); p.add_argument("--queue", required=True); p.add_argument("--output", required=True); p.add_argument("--radius", type=int, default=500); p.add_argument("--max-images", type=int, default=4); p.set_defaults(func=probe)
    p = sub.add_parser("analyze"); p.add_argument("--manifest", required=True); p.add_argument("--output", required=True); p.set_defaults(func=analyze)
    p = sub.add_parser("self-test"); p.set_defaults(func=self_test)
    args = parser.parse_args(); args.func(args)


if __name__ == "__main__":
    main()
