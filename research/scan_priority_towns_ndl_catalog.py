#!/usr/bin/env python3
"""Systematic official-catalog scan for V10 priority residential towns.

The scan uses the National Diet Library Search OpenSearch API and records every
query, hit count, and top metadata result. It searches seven independent themes:
detention/execution, burial/remains, cremation, air-raid temporary burial,
major fatal fire/explosion, military/POW use, and old streams/culverts.

Critical rule: a catalogue no-hit is only a search result, never evidence that
no major history exists. A catalogue hit is only a research lead and does not
prove spatial coincidence with a 100m cell or property.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import requests

OUT = Path("out-priority-town-ndl-scan")
API = "https://ndlsearch.ndl.go.jp/api/opensearch"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "iyashiro-map-research/1.0 (evidence-first catalog scan)"})

FALLBACK_TOWNS = [
    "東京都渋谷区上原二丁目", "東京都渋谷区上原三丁目", "東京都目黒区駒場四丁目",
    "東京都渋谷区大山町", "東京都目黒区東が丘一丁目", "東京都世田谷区北沢五丁目",
    "東京都世田谷区北沢一丁目", "東京都目黒区柿の木坂二丁目", "東京都目黒区目黒本町五丁目",
    "東京都千代田区一番町", "東京都目黒区八雲四丁目", "東京都世田谷区代沢二丁目",
    "東京都大田区中馬込一丁目", "東京都品川区小山台二丁目", "東京都目黒区八雲五丁目",
    "東京都世田谷区等々力七丁目", "東京都大田区久が原四丁目", "東京都渋谷区大山町",
    "東京都目黒区東が丘一丁目", "東京都渋谷区上原二丁目",
]

THEMES = [
    {"themeId": "detention_execution", "terms": "監獄 刑務所 拘置所 刑場 処刑 牢屋敷"},
    {"themeId": "burial_remains", "terms": "墓地 埋葬 仮埋葬 人骨 遺骨 火葬供養"},
    {"themeId": "cremation", "terms": "火葬場 焼場 斎場 葬祭場"},
    {"themeId": "air_raid_burial", "terms": "戦災 空襲 仮埋葬 改葬 戦災死者"},
    {"themeId": "fatal_incident", "terms": "火災 爆発 大量死 圧死 崩落 事故"},
    {"themeId": "military_pow", "terms": "軍用地 練兵場 陸軍 海軍 捕虜収容所 POW"},
    {"themeId": "old_stream", "terms": "旧河川 暗渠 水路 川跡 谷戸 湿地"},
]


def walk(obj: Any) -> Iterable[dict]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def normalize_town(s: str) -> str:
    s = re.sub(r"\s+", "", str(s))
    s = s.replace("4丁目", "四丁目").replace("5丁目", "五丁目").replace("3丁目", "三丁目").replace("2丁目", "二丁目").replace("1丁目", "一丁目")
    return s


def discover_towns() -> list[dict]:
    candidates: dict[str, dict] = {}
    json_files = list(Path(".").rglob("*residential*ranking*.json")) + list(Path(".").rglob("*rankings*.json"))
    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for d in walk(data):
            values = {str(k).lower(): v for k, v in d.items()}
            address = None
            for k, v in values.items():
                if any(t in k for t in ["address", "town", "町丁目", "area", "name"]):
                    sv = str(v)
                    if "東京都" in sv and any(x in sv for x in ["丁目", "町"]):
                        address = sv
                        break
            if not address:
                continue
            town = normalize_town(address)
            rank = None
            cell_id = None
            for k, v in values.items():
                if rank is None and "rank" in k:
                    try: rank = int(float(v))
                    except Exception: pass
                if cell_id is None and any(x in k for x in ["cell", "grid"]):
                    cell_id = str(v)
            row = {"town": town, "rank": rank, "representativeCellId": cell_id, "sourceFile": str(path)}
            prev = candidates.get(town)
            if prev is None or (rank is not None and (prev.get("rank") is None or rank < prev["rank"])):
                candidates[town] = row
    if len(candidates) < 20:
        for i, town in enumerate(FALLBACK_TOWNS, 1):
            town = normalize_town(town)
            candidates.setdefault(town, {"town": town, "rank": i, "representativeCellId": None, "sourceFile": "fallback"})
    rows = list(candidates.values())
    rows.sort(key=lambda r: (r.get("rank") is None, r.get("rank") or 9999, r["town"]))
    return rows[:96]


def text(el: ET.Element | None) -> str:
    return "" if el is None or el.text is None else el.text.strip()


def find_text(item: ET.Element, names: list[str]) -> str:
    for el in item.iter():
        local = el.tag.split("}")[-1].lower()
        if local in names and text(el):
            return text(el)
    return ""


def parse_feed(xml_bytes: bytes) -> tuple[int | None, list[dict]]:
    root = ET.fromstring(xml_bytes)
    total = None
    for el in root.iter():
        if el.tag.split("}")[-1].lower() in {"totalresults", "totalresult"}:
            try: total = int(text(el))
            except Exception: pass
    items = []
    for item in root.iter():
        if item.tag.split("}")[-1].lower() not in {"item", "entry"}:
            continue
        title = find_text(item, ["title"])
        link = ""
        for el in item.iter():
            if el.tag.split("}")[-1].lower() == "link":
                link = el.attrib.get("href") or text(el)
                if link: break
        desc = find_text(item, ["description", "summary"])
        creator = find_text(item, ["creator", "author"])
        date = find_text(item, ["date", "issued", "pubdate"])
        identifier = find_text(item, ["identifier", "id"])
        if title or link or identifier:
            items.append({"title": title, "link": link, "description": desc, "creator": creator, "date": date, "identifier": identifier})
    return total, items


def query_ndl(q: str, cnt: int = 20) -> dict:
    params = {"any": q, "cnt": cnt}
    try:
        r = SESSION.get(API, params=params, timeout=60)
        row = {"requestUrl": r.url, "status": r.status_code, "contentType": r.headers.get("content-type"), "bytes": len(r.content)}
        if r.status_code == 200:
            total, items = parse_feed(r.content)
            row.update({"totalResults": total, "items": items})
        else:
            row.update({"totalResults": None, "items": [], "error": r.text[:500]})
        return row
    except Exception as exc:
        return {"requestUrl": API, "status": None, "totalResults": None, "items": [], "error": f"{type(exc).__name__}: {exc}"}


def relevance(town: str, theme_terms: str, item: dict) -> float:
    blob = " ".join(str(item.get(k, "")) for k in ["title", "description", "creator", "identifier"])
    score = 0.0
    ward_match = re.search(r"東京都([^区市]+[区市])", town)
    short = re.sub(r"^東京都", "", town)
    if short in blob: score += 6
    if ward_match and ward_match.group(1) in blob: score += 2
    town_leaf = re.sub(r"^東京都[^区市]+[区市]", "", town)
    if town_leaf and town_leaf in blob: score += 4
    for term in theme_terms.split():
        if term.lower() in blob.lower(): score += 1
    if item.get("link") or item.get("identifier"): score += 0.25
    return score


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    towns = discover_towns()
    (OUT / "towns.json").write_text(json.dumps(towns, ensure_ascii=False, indent=2), encoding="utf-8")
    query_rows = []
    result_rows = []
    for ti, town in enumerate(towns, 1):
        for theme in THEMES:
            query = f"{town['town']} {theme['terms']}"
            response = query_ndl(query)
            qrow = {
                "town": town["town"], "rank": town.get("rank"), "representativeCellId": town.get("representativeCellId"),
                "themeId": theme["themeId"], "query": query, "status": response.get("status"),
                "totalResults": response.get("totalResults"), "returnedItems": len(response.get("items", [])),
                "requestUrl": response.get("requestUrl"), "error": response.get("error"),
                "interpretation": "catalog_no_hit_not_negative" if not response.get("items") else "catalog_hit_manual_spatial_review_required",
            }
            query_rows.append(qrow)
            for pos, item in enumerate(response.get("items", [])[:20], 1):
                result_rows.append({
                    "town": town["town"], "rank": town.get("rank"), "representativeCellId": town.get("representativeCellId"),
                    "themeId": theme["themeId"], "query": query, "position": pos,
                    **item, "relevanceScore": relevance(town["town"], theme["terms"], item),
                    "status": "catalog_lead_unverified_spatial_match", "scoringEffect": "none",
                })
            time.sleep(0.12)
    query_rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 9999, r["town"], r["themeId"]))
    result_rows.sort(key=lambda r: (-r["relevanceScore"], r["rank"] is None, r["rank"] or 9999, r["position"]))
    with (OUT / "ndl-query-log.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(query_rows[0].keys())); w.writeheader(); w.writerows(query_rows)
    if result_rows:
        with (OUT / "ndl-catalog-leads.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(result_rows[0].keys())); w.writeheader(); w.writerows(result_rows)
    # Town-theme matrix.
    matrix = {}
    for r in query_rows:
        matrix.setdefault(r["town"], {})[r["themeId"]] = r.get("totalResults")
    (OUT / "town-theme-hit-matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    top = [r for r in result_rows if r["relevanceScore"] >= 4][:500]
    (OUT / "top-catalog-leads.json").write_text(json.dumps(top, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "version": "v1-20260811", "townCount": len(towns), "themeCount": len(THEMES),
        "queryCount": len(query_rows), "catalogLeadCount": len(result_rows), "highRelevanceLeadCount": len(top),
        "querySuccessCount": sum(r.get("status") == 200 for r in query_rows),
        "qualityRule": "A catalogue no-hit is not negative evidence. A hit is a lead only and requires primary-source reading plus spatial verification before any V10 history or boundary update.",
        "scoringEffect": "none",
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "README.md").write_text(
        f"# V10本命町丁目・NDL公式目録横断走査 v1\n\n町丁目 {len(towns)}、テーマ {len(THEMES)}、照会 {len(query_rows)} 件。\n\n"
        "no-hitは不存在証明ではない。hitは資料候補であり、タイトル一致だけで100mセル・物件との空間一致を判断しない。"
        "高関連候補は原資料を読み、旧住所・旧地番・位置・境界を別途確認する。全件scoringEffect=none。\n",
        encoding="utf-8",
    )
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
