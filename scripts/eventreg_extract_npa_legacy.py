#!/usr/bin/env python3
"""Acquire JNIOSH's official 1991-2018 fatal occupational accident CSV corpus.

This runs only on the isolated EVENTREG executor branch. It creates a staging
source corpus and discovery pointers. It never creates canonical events,
100 m relations, scores, rankings, or automatic exclusions.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://www.jniosh.johas.go.jp/publication/houkoku/ROUSAIDB"
YEARS = range(1991, 2019)
EXPECTED = 44_537
OUT = Path("output")
RAW = OUT / "raw"

TOKYO = [
    "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区", "江東区",
    "品川区", "目黒区", "大田区", "世田谷区", "渋谷区", "中野区", "杉並区", "豊島区",
    "北区", "荒川区", "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区",
]
YOKOHAMA = [
    "鶴見区", "神奈川区", "西区", "中区", "南区", "港南区", "保土ケ谷区", "旭区",
    "磯子区", "金沢区", "港北区", "緑区", "青葉区", "都筑区", "戸塚区", "栄区",
    "泉区", "瀬谷区",
]
KAWASAKI = ["川崎区", "幸区", "中原区", "高津区", "宮前区", "多摩区", "麻生区"]
AMBIGUOUS = {"中央区", "港区", "北区", "西区", "中区", "南区", "旭区", "緑区", "青葉区", "泉区"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; EVENTREG-source-harvester/4.0; research)",
        "Accept": "text/csv,text/plain,*/*",
        "Accept-Language": "ja,en;q=0.8",
    }
    last = None
    for attempt in range(1, 7):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as response, path.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
                meta = {
                    "status": int(getattr(response, "status", 200)),
                    "content_type": response.headers.get("Content-Type", ""),
                    "bytes": path.stat().st_size,
                    "attempts": attempt,
                    "final_url": response.geturl(),
                }
            if path.stat().st_size < 100:
                raise RuntimeError(f"download too small: {path.stat().st_size}")
            return meta
        except Exception as exc:
            last = repr(exc)
            path.unlink(missing_ok=True)
            time.sleep(min(20, 2 ** attempt))
    raise RuntimeError(f"download failed {url}: {last}")


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError(f"missing header: {path}")
        old = list(reader.fieldnames)
        headers = [x.replace("\ufeff", "").strip() for x in old]
        rows = []
        for raw in reader:
            rows.append({
                new: ("" if raw.get(orig) is None else str(raw.get(orig)))
                for orig, new in zip(old, headers)
            })
    return headers, rows


def around(text: str, token: str, width: int = 35) -> str:
    i = text.find(token)
    return "" if i < 0 else text[max(0, i - width): i + len(token) + width]


def unique(items):
    seen, result = set(), []
    for item in items:
        key = item[:2]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def classify(narrative: str):
    text = re.sub(r"\s+", "", narrative or "")
    strong, coarse, weak = [], [], []

    for ward in TOKYO:
        for token in (f"東京都{ward}", f"東京{ward}"):
            if token in text:
                strong.append(("東京23区", ward, around(text, token)))
                break
    for ward in YOKOHAMA:
        token = f"横浜市{ward}"
        if token in text:
            strong.append(("横浜市", ward, around(text, token)))
    for ward in KAWASAKI:
        token = f"川崎市{ward}"
        if token in text:
            strong.append(("川崎市", ward, around(text, token)))

    if "東京都" in text and not any(x[0] == "東京23区" for x in strong):
        coarse.append(("東京23区", "東京都（区未確定）", around(text, "東京都")))
    if "横浜市" in text and not any(x[0] == "横浜市" for x in strong):
        coarse.append(("横浜市", "横浜市（区未確定）", around(text, "横浜市")))
    if "川崎市" in text and not any(x[0] == "川崎市" for x in strong):
        coarse.append(("川崎市", "川崎市（区未確定）", around(text, "川崎市")))

    used = {x[1] for x in strong}
    for region, wards in (("東京23区", TOKYO), ("横浜市", YOKOHAMA), ("川崎市", KAWASAKI)):
        for ward in wards:
            if ward in text and ward not in used:
                weak.append((region, ward, around(text, ward)))

    strong, coarse, weak = unique(strong), unique(coarse), unique(weak)
    chosen = strong or coarse or weak
    if not chosen:
        return {
            "target_candidate": "0",
            "target_match_class": "NO_TARGET48_STRING",
            "target_region_group": "",
            "target_municipality_candidates": "",
            "target_match_evidence": "",
            "event_registry_eligibility": "SOURCE_CORPUS_ONLY",
            "geometry_eligibility": "NO",
            "privacy_gate": "ACTIVE",
            "unknown_reason": "no explicit target48 place string",
        }

    if strong:
        match_class, eligibility = "EXPLICIT_CITY_PREFECTURE_PLUS_WARD", "DISCOVERY_REVIEW"
    elif coarse:
        match_class, eligibility = "EXPLICIT_CITY_OR_PREFECTURE_ONLY", "HOLD_SUBMUNICIPAL_LOCATION"
    else:
        match_class = (
            "AMBIGUOUS_WARD_ONLY"
            if {x[1] for x in weak} & AMBIGUOUS
            else "WARD_ONLY_WITHOUT_CITY_CONTEXT"
        )
        eligibility = "HOLD_CONTEXT_DISAMBIGUATION"

    return {
        "target_candidate": "1",
        "target_match_class": match_class,
        "target_region_group": "|".join(sorted({x[0] for x in chosen})),
        "target_municipality_candidates": "|".join(x[1] for x in chosen),
        "target_match_evidence": " || ".join(x[2] for x in chosen if x[2]),
        "event_registry_eligibility": eligibility,
        "geometry_eligibility": "NO_AUTOMATIC_100M_PROMOTION",
        "privacy_gate": "ACTIVE",
        "unknown_reason": "identity, exact place, dedup and geometry pending",
    }


def write_csv(path: Path, rows, fields, compressed: bool = False):
    if compressed:
        handle = gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=9)
    else:
        handle = path.open("w", encoding="utf-8", newline="")
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def main() -> int:
    OUT.mkdir(exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    rows_all, candidates, strong, manifest, errors = [], [], [], [], []
    headers_all, seen_headers = [], set()
    year_counts = Counter()
    accident_types = Counter()
    industries = Counter()
    classes = Counter()

    for year in YEARS:
        name = f"SHIBO_{year}.csv"
        url = f"{BASE}/{name}"
        path = RAW / name
        print(f"FETCH {year} {url}", flush=True)
        try:
            meta = download(url, path)
            headers, rows = read_csv(path)
        except Exception as exc:
            errors.append({"year": year, "url": url, "error": repr(exc)})
            print(f"ERROR {year}: {exc!r}", file=sys.stderr, flush=True)
            continue

        for header in headers:
            if header not in seen_headers:
                seen_headers.add(header)
                headers_all.append(header)
        year_counts[year] = len(rows)
        manifest.append({
            "year": year,
            "source_file": name,
            "source_url": url,
            "final_url": meta["final_url"],
            "http_status": meta["status"],
            "content_type": meta["content_type"],
            "bytes": meta["bytes"],
            "sha256": digest(path),
            "rows": len(rows),
            "headers": " | ".join(headers),
            "status": "ACQUIRED_AND_PARSED",
            "canonical_events_added": 0,
            "cell_relations_added": 0,
        })

        for row_number, source in enumerate(rows, 2):
            match = classify(source.get("災害状況", ""))
            source_id = source.get("ID", "")
            record = {
                "source_dataset": "JNIOSH_FATAL_OCCUPATIONAL_CORRECTED_CSV_1991_2018",
                "source_file": name,
                "source_url": url,
                "source_year": year,
                "source_row_number": row_number,
                "source_record_id": source_id,
                "canonical_source_identity": f"JNIOSH_SHIBO_{year}_{source_id or row_number}",
            }
            record.update(source)
            record.update(match)
            rows_all.append(record)
            accident_types[source.get("事故の型分類名", "") or "(blank)"] += 1
            industries[source.get("業種（大分類）分類名", "") or "(blank)"] += 1
            if match["target_candidate"] == "1":
                candidates.append(record)
                classes[match["target_match_class"]] += 1
                if match["target_match_class"] == "EXPLICIT_CITY_PREFECTURE_PLUS_WARD":
                    strong.append(record)

    metadata_fields = [
        "source_dataset", "source_file", "source_url", "source_year", "source_row_number",
        "source_record_id", "canonical_source_identity",
    ]
    gate_fields = [
        "target_candidate", "target_match_class", "target_region_group",
        "target_municipality_candidates", "target_match_evidence",
        "event_registry_eligibility", "geometry_eligibility", "privacy_gate", "unknown_reason",
    ]
    fields = metadata_fields + headers_all + gate_fields

    write_csv(OUT / "JNIOSH_FATAL_OCCUPATIONAL_1991_2018_ALL.csv.gz", rows_all, fields, True)
    write_csv(OUT / "TARGET48_DISCOVERY_CANDIDATES.csv", candidates, fields)
    write_csv(OUT / "TARGET48_STRONG_STRING_MATCHES.csv", strong, fields)
    write_csv(
        OUT / "SOURCE_FILE_MANIFEST.csv",
        manifest,
        [
            "year", "source_file", "source_url", "final_url", "http_status", "content_type",
            "bytes", "sha256", "rows", "headers", "status",
            "canonical_events_added", "cell_relations_added",
        ],
    )
    write_csv(
        OUT / "YEAR_COUNTS.csv",
        [{"year": key, "records": value} for key, value in sorted(year_counts.items())],
        ["year", "records"],
    )
    write_csv(
        OUT / "ACCIDENT_TYPE_SUMMARY.csv",
        [{"accident_type": key, "records": value} for key, value in accident_types.most_common()],
        ["accident_type", "records"],
    )
    write_csv(
        OUT / "INDUSTRY_SUMMARY.csv",
        [{"industry": key, "records": value} for key, value in industries.most_common()],
        ["industry", "records"],
    )
    shutil.make_archive(str(OUT / "JNIOSH_RAW_28_FILES"), "zip", RAW)

    summary = {
        "run_id": "eventreg-jniosh-44537-20260819-v4",
        "official_source": "JNIOSH corrected fatal occupational accident CSV corpus",
        "coverage": "1991-2018",
        "expected_files": 28,
        "acquired_files": len(manifest),
        "expected_records": EXPECTED,
        "acquired_records": len(rows_all),
        "official_count_match": len(manifest) == 28 and len(rows_all) == EXPECTED and not errors,
        "target48_discovery_candidates": len(candidates),
        "target48_strong_string_matches": len(strong),
        "target_match_classes": dict(classes),
        "errors": errors,
        "contracts": {
            "canonical_events_added": 0,
            "cell_relations_added": 0,
            "score_rank_exclusion_effect": 0,
            "privacy_gate": "ACTIVE",
            "no_automatic_100m_promotion": True,
            "unknown_is_not_absence": True,
        },
    }
    (OUT / "SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "README.md").write_text(
        "# EVENTREG fatal bulk corpus\n\n"
        f"Acquired **{len(rows_all):,}** official source rows from **{len(manifest)}/28** annual files. "
        f"Target48 discovery candidates: **{len(candidates):,}**. "
        "Canonical events/cell relations added: **0/0**.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 1 if not rows_all else 0


if __name__ == "__main__":
    raise SystemExit(main())
