#!/usr/bin/env python3
"""Metadata-only KartaView coverage audit for ECOSCAPE P2B.

No image bytes are downloaded. The audit records public metadata only and
never changes an ECOSCAPE score or ranking.
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AREAS = [
    ("P2-001","g114-151",35.7372403881,139.5967410285,"東京都練馬区石神井台一丁目"),
    ("P2-002","g169-288",35.6878332734,139.7480226239,"東京都千代田区千代田"),
    ("P2-003","g170-250",35.6869349623,139.7060613055,"東京都新宿区内藤町"),
    ("P2-004","g79-180",35.7686812792,139.6287641399,"東京都練馬区光が丘四丁目"),
    ("P2-005","g225-263",35.6375278476,139.7204164933,"東京都港区白金台五丁目"),
    ("P2-006","g245-31",35.6195616241,139.4642316019,"神奈川県川崎市麻生区はるひ野五丁目"),
    ("P2-007","g245-89",35.6195616241,139.5282778247,"神奈川県川崎市多摩区菅馬場四丁目"),
    ("P2-008","g243-278",35.6213582465,139.7369801717,"東京都品川区北品川四丁目"),
    ("P2-009","g178-275",35.6797484729,139.7336674360,"東京都千代田区紀尾井町"),
    ("P2-010","g136-252",35.7174775422,139.7082697959,"東京都豊島区目白一丁目"),
    ("P2-011","g79-260",35.7686812792,139.7171037577,"東京都北区赤羽西三丁目"),
    ("P2-012","g475-103",35.4129500539,139.5437372578,"神奈川県横浜市戸塚区柏尾町"),
    ("P2-013","g463-197",35.4237297880,139.6475363087,"神奈川県横浜市中区矢口台"),
    ("P2-014","g439-156",35.4452892562,139.6022622546,"神奈川県横浜市保土ケ谷区岩井町"),
    ("P2-015","g457-184",35.4291196550,139.6331811208,"神奈川県横浜市南区平楽"),
    ("P2-016","g290-198",35.5791376213,139.6486405539,"神奈川県川崎市中原区今井上町"),
    ("P2-017","g395-48",35.4848149479,139.4830037706,"神奈川県横浜市瀬谷区瀬谷町"),
    ("P2-018","g288-126",35.5809342436,139.5691348979,"神奈川県川崎市宮前区鷺沼四丁目"),
    ("P2-019","g100-312",35.7498167445,139.7745245092,"東京都荒川区東尾久七丁目"),
    ("P2-020","g221-222",35.6411210923,139.6751424392,"東京都世田谷区下馬二丁目"),
    ("P2-021","g288-300",35.5809342436,139.7612735665,"東京都大田区東海三丁目"),
    ("P2-022","g230-333",35.6330362918,139.7977136589,"東京都江東区有明三丁目"),
    ("P2-023","g357-133",35.5189507725,139.5768646145,"神奈川県横浜市都筑区池辺町"),
    ("P2-024","g323-171",35.5494933525,139.6188259329,"神奈川県横浜市港北区高田西一丁目"),
    ("P2-025","g453-220",35.4327128997,139.6729339488,"神奈川県横浜市中区本牧ふ頭"),
    ("P2-026","g121-347",35.7309522098,139.8131730920,"東京都墨田区堤通二丁目"),
    ("P2-027","g198-301",35.6617822494,139.7623778118,"東京都中央区浜離宮庭園"),
    ("P2-028","g187-246",35.6716636723,139.7016443246,"東京都渋谷区代々木神園町"),
    ("P2-029","g275-290",35.5926122889,139.7502311143,"東京都品川区八潮四丁目"),
    ("P2-030","g53-247",35.7920373697,139.7027485698,"東京都北区浮間二丁目"),
]

ENDPOINT = "https://api.openstreetcam.org/2.0/photo/"
OUT = Path("p2b-kartaview-output")
OUT.mkdir(exist_ok=True)


def nested_lists(obj: Any, path: str = "root"):
    if isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj[:5]):
            yield from nested_lists(v, f"{path}[{i}]")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from nested_lists(v, f"{path}.{k}")


def extract_items(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    candidates = []
    for path, values in nested_lists(payload):
        dicts = [v for v in values if isinstance(v, dict)]
        if not dicts:
            continue
        score = sum(
            any(key in row for key in ("id", "photoId", "sequenceId", "sequence_id", "date_added", "date", "heading"))
            for row in dicts[:10]
        )
        candidates.append((score, len(dicts), path, dicts))
    if not candidates:
        return "NONE", []
    candidates.sort(reverse=True, key=lambda x: (x[0], x[1]))
    _, _, path, rows = candidates[0]
    return path, rows


def value(row: dict[str, Any], *keys: str):
    for k in keys:
        if row.get(k) not in (None, ""):
            return row.get(k)
    return None


def fetch(lat: float, lng: float) -> tuple[int, str, dict[str, Any]]:
    params = urllib.parse.urlencode({
        "lat": lat,
        "lng": lng,
        "zoomLevel": 15,
        "join": "sequence",
        "orderBy": "id",
        "orderDirection": "desc",
    })
    url = f"{ENDPOINT}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ECOSCAPE-P2B-Coverage-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return response.status, url, json.loads(raw.decode("utf-8"))


def main() -> None:
    summary = []
    raw_receipts = []
    for p2id, cell, lat, lng, label in AREAS:
        row = {
            "p2PilotId": p2id,
            "canonicalCellId": cell,
            "officialAreaLabel": label,
            "latitude": lat,
            "longitude": lng,
            "provider": "KartaView",
            "metadataOnly": True,
            "rankingEffect": "none",
            "scoringEffect": "none",
        }
        try:
            status, url, payload = fetch(lat, lng)
            path, items = extract_items(payload)
            dates = [value(item, "date_added", "date", "captured_at", "created_at") for item in items]
            dates = [str(v) for v in dates if v]
            headings = [value(item, "heading", "compass_angle") for item in items]
            headings = [v for v in headings if v is not None]
            sequences = {
                str(value(item, "sequenceId", "sequence_id", "sequenceIdStr"))
                for item in items
                if value(item, "sequenceId", "sequence_id", "sequenceIdStr") is not None
            }
            row.update({
                "httpStatus": status,
                "responseListPath": path,
                "returnedItemCount": len(items),
                "sequenceCountObserved": len(sequences),
                "headingCountObserved": len(headings),
                "latestDateText": max(dates) if dates else "",
                "coverageStatus": "COVERED_METADATA" if items else "NO_METADATA_FOUND",
                "error": "",
            })
            raw_receipts.append({"p2PilotId": p2id, "url": url, "payload": payload})
        except Exception as exc:
            row.update({
                "httpStatus": "",
                "responseListPath": "",
                "returnedItemCount": 0,
                "sequenceCountObserved": 0,
                "headingCountObserved": 0,
                "latestDateText": "",
                "coverageStatus": "REQUEST_ERROR",
                "error": repr(exc),
            })
        summary.append(row)
        time.sleep(0.7)

    fields = list(summary[0])
    with (OUT / "P2B_KARTAVIEW_COVERAGE_30.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    (OUT / "P2B_KARTAVIEW_RAW_RECEIPTS.json").write_text(
        json.dumps(raw_receipts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    counts = {}
    for row in summary:
        counts[row["coverageStatus"]] = counts.get(row["coverageStatus"], 0) + 1
    audit = {
        "buildId": "ecoscape-green-quality-p2b-kartaview-coverage-20260819-f1",
        "checkedAtUTC": datetime.now(timezone.utc).isoformat(),
        "pilotAreas": len(AREAS),
        "statusCounts": counts,
        "actualImageDownloads": 0,
        "actualSpendJPY": 0,
        "rankingEffect": "none",
        "scoringEffect": "none",
        "interpretation": "Coverage metadata only. No imagery quality or cleanliness claim.",
    }
    (OUT / "P2B_KARTAVIEW_COVERAGE_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
