#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

API = "https://ndlsearch.ndl.go.jp/api/opensearch"
OUT = Path("out-priority-ndl-v2")
OUT.mkdir(parents=True, exist_ok=True)

CELLS = [
    {"rank":1,"address":"東京都渋谷区上原二丁目","town_query":"渋谷 上原","cell_id":"g194-226","grid_index":89854},
    {"rank":2,"address":"東京都渋谷区上原三丁目","town_query":"渋谷 上原","cell_id":"g195-224","grid_index":90314},
    {"rank":3,"address":"東京都目黒区駒場四丁目","town_query":"目黒 駒場","cell_id":"g199-227","grid_index":92165},
    {"rank":4,"address":"東京都渋谷区大山町","town_query":"渋谷 大山町","cell_id":"g187-221","grid_index":86615},
    {"rank":5,"address":"東京都目黒区東が丘一丁目","town_query":"目黒 東が丘","cell_id":"g233-217","grid_index":107863},
    {"rank":6,"address":"東京都世田谷区北沢五丁目","town_query":"世田谷 北沢","cell_id":"g188-216","grid_index":87072},
    {"rank":7,"address":"東京都世田谷区北沢一丁目","town_query":"世田谷 北沢","cell_id":"g199-219","grid_index":92157},
    {"rank":8,"address":"東京都目黒区柿の木坂二丁目","town_query":"目黒 柿の木坂","cell_id":"g239-220","grid_index":110638},
    {"rank":9,"address":"東京都目黒区目黒本町五丁目","town_query":"目黒 目黒本町","cell_id":"g244-243","grid_index":112971},
    {"rank":10,"address":"東京都千代田区一番町","town_query":"千代田 一番町","cell_id":"g169-281","grid_index":78359},
]

THEMES = {
    "detention_execution_pow": ["刑場", "監獄", "拘置所", "捕虜", "俘虜", "収容所"],
    "cemetery_burial_remains": ["墓地", "埋葬", "人骨", "遺骨", "墓"],
    "crematorium": ["火葬場", "火葬", "斎場"],
    "wartime_temporary_burial": ["仮埋葬", "戦災", "空襲"],
    "major_fire_explosion_incident": ["火災", "爆発", "事故", "大量死"],
    "military_land_pow": ["軍用地", "兵営", "陸軍", "海軍", "軍施設"],
    "old_watercourse": ["暗渠", "河川", "川", "水路", "旧河道"],
    "historic_land_use": ["土地利用", "旧地図", "地籍図", "町史", "区史"],
    "folklore": ["伝承", "民俗", "地名", "郷土史"],
    "primary_source_leads": ["古地図", "公図", "地籍", "沿革", "史料"],
}

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

session = requests.Session()
session.headers.update({
    "User-Agent": "iyashiro-map-research/1.0 (non-commercial research metadata scan; contact via GitHub tanakatoki5151-del/iyashiro-map)",
    "Accept-Language": "ja,en;q=0.8",
})


def txt(el, path, ns=NS):
    x = el.find(path, ns)
    return (x.text or "").strip() if x is not None and x.text else ""


def alltxt(el, path, ns=NS):
    return [((x.text or "").strip()) for x in el.findall(path, ns) if (x.text or "").strip()]


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\u3000", " ")).strip()


def relevance_score(cell: dict, keyword: str, item: dict) -> int:
    blob = normalize(" ".join([
        item.get("title", ""), item.get("creator", ""), item.get("publisher", ""),
        item.get("description", ""), " ".join(item.get("subjects", [])), item.get("date", "")
    ])).lower()
    score = 0
    for token in cell["town_query"].split():
        if token.lower() in blob:
            score += 4
    if keyword.lower() in blob:
        score += 3
    # Older/historical material is more useful as a research lead, but never treated as factual proof.
    years = [int(y) for y in re.findall(r"(?:18|19|20)\d{2}", blob)]
    if years and min(years) <= 1960:
        score += 2
    if any(k in blob for k in ["地図", "地籍", "沿革", "史", "報告", "資料", "公文書"]):
        score += 1
    return score


def parse_feed(content: bytes) -> tuple[int, list[dict]]:
    root = ET.fromstring(content)
    total_text = txt(root, "opensearch:totalResults")
    try:
        total = int(total_text)
    except Exception:
        total = 0
    items = []
    entries = root.findall("atom:entry", NS)
    if not entries:
        entries = root.findall("item")
    for entry in entries:
        links = []
        for l in entry.findall("atom:link", NS):
            href = l.attrib.get("href")
            if href:
                links.append(href)
        if not links:
            for l in entry.findall("link"):
                if l.text:
                    links.append(l.text.strip())
        item = {
            "title": txt(entry, "atom:title") or txt(entry, "title") or txt(entry, "dc:title"),
            "creator": txt(entry, "dc:creator") or txt(entry, "author/name") or txt(entry, "atom:author/atom:name"),
            "publisher": txt(entry, "dc:publisher") or txt(entry, "dcterms:publisher"),
            "date": txt(entry, "dc:date") or txt(entry, "dcterms:date"),
            "description": txt(entry, "dc:description") or txt(entry, "dcterms:description") or txt(entry, "atom:summary"),
            "subjects": alltxt(entry, "dc:subject") + alltxt(entry, "dcterms:subject"),
            "identifiers": alltxt(entry, "dc:identifier") + alltxt(entry, "dcterms:identifier"),
            "links": links,
        }
        items.append(item)
    return total, items


query_rows = []
lead_rows = []
failures = []

# Avoid querying duplicate town/theme/keyword combinations twice (e.g. Uehara 2 and 3, Kitazawa 1 and 5).
cache: dict[tuple[str, str], dict] = {}

for cell in CELLS:
    for theme, keywords in THEMES.items():
        for keyword in keywords:
            cache_key = (cell["town_query"], keyword)
            query = f"{cell['town_query']} {keyword}"
            if cache_key not in cache:
                params = {"any": query, "cnt": 10}
                url = API + "?" + urllib.parse.urlencode(params)
                rec = {"query": query, "url": url, "http_status": None, "total_results": None, "error": ""}
                try:
                    r = session.get(API, params=params, timeout=45)
                    rec["http_status"] = r.status_code
                    if not r.ok:
                        raise RuntimeError(f"HTTP {r.status_code}")
                    total, items = parse_feed(r.content)
                    rec["total_results"] = total
                    rec["items"] = items
                    cache[cache_key] = rec
                except Exception as e:
                    rec["error"] = f"{type(e).__name__}: {e}"
                    rec["items"] = []
                    cache[cache_key] = rec
                    failures.append({"town_query": cell["town_query"], "keyword": keyword, **rec})
                time.sleep(0.75)
            rec = cache[cache_key]
            query_rows.append({
                "rank": cell["rank"], "address": cell["address"], "cell_id": cell["cell_id"], "grid_index": cell["grid_index"],
                "theme": theme, "keyword": keyword, "query": query, "url": rec["url"],
                "http_status": rec.get("http_status"), "total_results": rec.get("total_results"), "error": rec.get("error", ""),
                "interpretation": "catalog_lead_or_no_hit_only_not_spatial_evidence"
            })
            for idx, item in enumerate(rec.get("items", [])[:10], start=1):
                score = relevance_score(cell, keyword, item)
                lead_rows.append({
                    "rank": cell["rank"], "address": cell["address"], "cell_id": cell["cell_id"], "grid_index": cell["grid_index"],
                    "theme": theme, "keyword": keyword, "query": query, "query_total_results": rec.get("total_results"),
                    "result_rank": idx, "relevance_score": score, "title": item.get("title", ""),
                    "creator": item.get("creator", ""), "publisher": item.get("publisher", ""), "date": item.get("date", ""),
                    "description": normalize(item.get("description", ""))[:1000],
                    "subjects": " | ".join(item.get("subjects", []))[:1200],
                    "identifiers": " | ".join(item.get("identifiers", []))[:1200],
                    "links": " | ".join(item.get("links", []))[:1600],
                    "status": "catalog_lead_manual_primary_source_and_spatial_review_required",
                    "scoring_effect": "none"
                })

# Deduplicate lead records inside each cell/theme by title/date/identifiers, keeping best relevance and first result.
dedup = {}
for row in lead_rows:
    key = (row["cell_id"], row["theme"], row["title"], row["date"], row["identifiers"])
    old = dedup.get(key)
    if old is None or (row["relevance_score"], -row["result_rank"]) > (old["relevance_score"], -old["result_rank"]):
        dedup[key] = row
lead_rows = list(dedup.values())
lead_rows.sort(key=lambda r: (r["rank"], r["theme"], -r["relevance_score"], r["result_rank"], r["title"]))

# Summary per cell/theme.
summary_rows = []
for cell in CELLS:
    for theme in THEMES:
        q = [r for r in query_rows if r["cell_id"] == cell["cell_id"] and r["theme"] == theme]
        leads = [r for r in lead_rows if r["cell_id"] == cell["cell_id"] and r["theme"] == theme]
        high = [r for r in leads if r["relevance_score"] >= 7]
        summary_rows.append({
            "rank": cell["rank"], "address": cell["address"], "cell_id": cell["cell_id"], "grid_index": cell["grid_index"], "theme": theme,
            "keyword_query_count": len(q), "queries_with_results": sum(1 for r in q if (r.get("total_results") or 0) > 0),
            "total_results_sum_not_unique": sum((r.get("total_results") or 0) for r in q),
            "dedup_lead_count": len(leads), "high_relevance_lead_count": len(high),
            "top_leads": " || ".join(f"[{r['relevance_score']}] {r['title']} ({r['date']})" for r in high[:5]),
            "status": "catalog_scan_complete_leads_only",
            "quality_rule": "no_hit_is_not_absence_hit_is_not_location_match_scoring_effect_none"
        })


def write_csv(name, rows):
    p = OUT / name
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

write_csv("query-log-v2.csv", query_rows)
write_csv("catalog-leads-v2.csv", lead_rows)
write_csv("cell-theme-summary-v2.csv", summary_rows)
write_csv("failures-v2.csv", failures)

run_summary = {
    "version": "priority-cells-ndl-catalog-scan-v2-20260812",
    "api": API,
    "cellCount": len(CELLS),
    "themeCount": len(THEMES),
    "uniqueNetworkQueries": len(cache),
    "cellQueryRows": len(query_rows),
    "deduplicatedLeadRows": len(lead_rows),
    "highRelevanceLeadRows": sum(1 for r in lead_rows if r["relevance_score"] >= 7),
    "failureCount": len(failures),
    "qualityRules": [
        "NDL catalog hits are research leads only.",
        "No-hit is not evidence that a historical fact/site did not exist.",
        "Catalog hit is not evidence that the event/facility was inside the V10 cell.",
        "No scoring, auto exclusion, distance penalty or ranking change is permitted from this scan alone.",
        "Primary text/image and spatial correspondence must be reviewed before promotion."
    ],
    "cells": CELLS,
    "themes": THEMES,
}
(OUT / "SUMMARY.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "README.md").write_text(
    "# V10 本命10セル NDL公式目録テーマ再走査 v2\n\n"
    "国立国会図書館サーチ OpenSearch APIを用い、現行住宅代表10セルについてテーマ別の資料候補を探索した。\n"
    "これは書誌目録のlead抽出であり、歴史事実・地点一致・境界・不存在を証明しない。\n"
    "`catalog-leads-v2.csv` の高relevance項目から本文/原画像を手動確認し、住所・旧地番・図葉・本文記述をV10セルへ照合する。\n"
    "no-hitも安全判定には使わない。全件scoring_effect=none。\n",
    encoding="utf-8"
)

import hashlib
with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")

print(json.dumps(run_summary, ensure_ascii=False))
