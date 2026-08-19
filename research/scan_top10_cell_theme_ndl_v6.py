#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

API = "https://ndlsearch.ndl.go.jp/api/opensearch"
OUT = Path("out-top10-cell-theme-ndl-v6")
OUT.mkdir(parents=True, exist_ok=True)

CELLS = [
    {"rank":1,"address":"東京都渋谷区上原二丁目","cell_id":"g194-226","grid_index":89854,"ward":"渋谷","aliases":["上原二丁目","代々木上原町","代々木富ヶ谷町"]},
    {"rank":2,"address":"東京都渋谷区上原三丁目","cell_id":"g195-224","grid_index":90314,"ward":"渋谷","aliases":["上原三丁目","代々木上原町","代々木大山町"]},
    {"rank":3,"address":"東京都目黒区駒場四丁目","cell_id":"g199-227","grid_index":92165,"ward":"目黒","aliases":["駒場四丁目","駒場町","上目黒 駒場"]},
    {"rank":4,"address":"東京都渋谷区大山町","cell_id":"g187-221","grid_index":86615,"ward":"渋谷","aliases":["大山町","代々木大山町","代々木西原町"]},
    {"rank":5,"address":"東京都目黒区東が丘一丁目","cell_id":"g233-217","grid_index":107863,"ward":"目黒","aliases":["東が丘一丁目","芳窪町","衾 東上芳窪","衾 東下芳窪"]},
    {"rank":6,"address":"東京都世田谷区北沢五丁目","cell_id":"g188-216","grid_index":87072,"ward":"世田谷","aliases":["北沢五丁目","北沢町","北沢"]},
    {"rank":7,"address":"東京都世田谷区北沢一丁目","cell_id":"g199-219","grid_index":92157,"ward":"世田谷","aliases":["北沢一丁目","北沢町","北沢"]},
    {"rank":8,"address":"東京都目黒区柿の木坂二丁目","cell_id":"g239-220","grid_index":110638,"ward":"目黒","aliases":["柿の木坂二丁目","柿ノ木坂","衾 東根"]},
    {"rank":9,"address":"東京都目黒区目黒本町五丁目","cell_id":"g244-243","grid_index":112971,"ward":"目黒","aliases":["目黒本町五丁目","月光町","向原町","碑文谷原"]},
    {"rank":10,"address":"東京都千代田区一番町","cell_id":"g169-281","grid_index":78359,"ward":"千代田","aliases":["一番町","麹町区 一番町","麹町 一番町"]},
]

THEMES = {
    "incarceration_prison_detention": ["監獄", "刑務所", "拘置", "留置", "牢"],
    "execution_ground": ["刑場", "御仕置場", "処刑", "仕置場"],
    "burial_human_remains": ["埋葬", "人骨", "遺骨", "遺骸", "墓坑"],
    "cemetery_former_cemetery": ["墓地", "共同墓地", "墓所", "葬地"],
    "crematorium_former_crematorium": ["火葬場", "火葬", "焼場", "斎場"],
    "pow_military_detention": ["捕虜", "俘虜", "抑留", "収容所"],
    "mass_death_major_fatal_incident": ["大量死", "死者", "惨死", "火災", "爆発"],
    "air_raid_temporary_burial": ["仮埋葬", "戦災殃死", "戦災", "空襲"],
    "historical_watercourse": ["暗渠", "水路", "旧河道", "用水", "河川"],
    "historical_land_facility_use": ["地籍", "軍用地", "兵営", "工場", "屋敷"],
}

# False-positive geography tokens that are especially dangerous for short names such as 大山町・一番町.
OTHER_PREFECTURES = [
    "北海道","青森","岩手","宮城","秋田","山形","福島","茨城","栃木","群馬","埼玉","千葉",
    "神奈川","新潟","富山","石川","福井","山梨","長野","岐阜","静岡","愛知","三重","滋賀",
    "京都","大阪","兵庫","奈良","和歌山","鳥取","島根","岡山","広島","山口","徳島","香川",
    "愛媛","高知","福岡","佐賀","長崎","熊本","大分","宮崎","鹿児島","沖縄",
]

NS = {
    "atom":"http://www.w3.org/2005/Atom",
    "dc":"http://purl.org/dc/elements/1.1/",
    "dcterms":"http://purl.org/dc/terms/",
    "opensearch":"http://a9.com/-/spec/opensearch/1.1/",
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent":"iyashiro-map research/1.3 top10 cell-theme sequential NDL scan",
    "Accept-Language":"ja,en;q=0.8",
})


def first_text(e, paths):
    for p in paths:
        x = e.find(p, NS)
        if x is not None and x.text:
            return x.text.strip()
    return ""


def all_text(e, paths):
    vals=[]
    for p in paths:
        vals += [(x.text or "").strip() for x in e.findall(p,NS) if x.text]
    return vals


def parse_xml(content: bytes):
    root = ET.fromstring(content)
    total_el = root.find(".//opensearch:totalResults", NS)
    try:
        total = int((total_el.text or "0").strip()) if total_el is not None else 0
    except Exception:
        total = 0
    entries = root.findall(".//atom:entry", NS)
    if not entries:
        entries = root.findall(".//item")
    out=[]
    for e in entries[:20]:
        out.append({
            "title": first_text(e,["atom:title","title","dc:title"]),
            "creator": first_text(e,["dc:creator","creator"]),
            "publisher": first_text(e,["dc:publisher","dcterms:publisher","publisher"]),
            "date": first_text(e,["dc:date","dcterms:date","pubDate"]),
            "description": re.sub(r"\s+"," ",first_text(e,["dc:description","dcterms:description","atom:summary","description"]))[:3000],
            "subjects": " | ".join(all_text(e,["dc:subject","dcterms:subject","subject"]))[:2000],
            "identifiers": " | ".join(all_text(e,["dc:identifier","dcterms:identifier","guid"]))[:2200],
            "links": " | ".join([x.attrib.get("href","") for x in e.findall(".//atom:link",NS) if x.attrib.get("href")] + [first_text(e,["link"])])[:2500],
        })
    return total, out, root.tag


def fetch(query: str):
    params={"any":query,"cnt":20}
    url=API+"?"+urllib.parse.urlencode(params)
    attempts=[]
    for attempt in range(1,5):
        try:
            r=SESSION.get(API,params=params,timeout=(10,50))
            attempts.append({"attempt":attempt,"status":r.status_code,"bytes":len(r.content)})
            if r.status_code==429:
                time.sleep(min(16,2**attempt)); continue
            r.raise_for_status()
            total,items,root_tag=parse_xml(r.content)
            return {
                "url":url,"total":total,"items":items,"error":"","attempts":attempts,
                "rootTag":root_tag,"responseSha256":hashlib.sha256(r.content).hexdigest(),
            }
        except Exception as exc:
            attempts.append({"attempt":attempt,"error":f"{type(exc).__name__}: {exc}"})
            if attempt<4:
                time.sleep(min(16,2**attempt))
    return {"url":url,"total":0,"items":[],"error":attempts[-1].get("error","failed"),"attempts":attempts,"rootTag":"","responseSha256":""}


def item_blob(it):
    return " ".join(str(it.get(k,"")) for k in ["title","creator","publisher","date","description","subjects","identifiers"])


def geo_class(cell, alias, blob):
    compact=blob.replace(" ","")
    alias_hit=alias.replace(" ","") in compact
    tokyo_hit="東京" in blob
    ward_hit=cell["ward"] in blob
    other_hits=[p for p in OTHER_PREFECTURES if p in blob]
    # Tokyo can legitimately coexist with publisher locations elsewhere, so never hard reject solely on other prefecture.
    if ward_hit and alias_hit:
        return "tokyo_ward_alias_supported", 6, "|".join(other_hits)
    if tokyo_hit and alias_hit:
        return "tokyo_alias_supported", 4, "|".join(other_hits)
    if alias_hit and other_hits and not tokyo_hit and not ward_hit:
        return "same_name_other_prefecture_risk", -5, "|".join(other_hits)
    if alias_hit:
        return "alias_only_geography_unresolved", 1, "|".join(other_hits)
    return "alias_not_in_metadata", -2, "|".join(other_hits)


def write_csv(name, rows):
    p=OUT/name
    if not rows:
        p.write_text("",encoding="utf-8")
        return
    with p.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


query_rows=[]
lead_rows=[]
summary_rows=[]

# Cache identical alias+keyword pairs shared by multiple cells such as 北沢町.
cache={}
query_no=0
for cell in CELLS:
    for theme, keywords in THEMES.items():
        cell_theme_leads=[]
        for alias in cell["aliases"]:
            for keyword in keywords:
                query=f"{alias} {keyword}"
                if query not in cache:
                    query_no += 1
                    rec=fetch(query)
                    cache[query]=rec
                    print(json.dumps({"queryNo":query_no,"query":query,"total":rec["total"],"returned":len(rec["items"]),"error":rec["error"]},ensure_ascii=False),flush=True)
                    time.sleep(1.25)
                else:
                    rec=cache[query]
                query_rows.append({
                    "rank":cell["rank"],"address":cell["address"],"cell_id":cell["cell_id"],"grid_index":cell["grid_index"],
                    "theme":theme,"alias":alias,"keyword":keyword,"query":query,"api_url":rec["url"],
                    "total_results":rec["total"],"returned_items":len(rec["items"]),"error":rec["error"],
                    "attempts_json":json.dumps(rec["attempts"],ensure_ascii=False),"response_sha256":rec["responseSha256"],
                    "interpretation":"defined_ndl_catalog_search_only_not_absence_proof",
                })
                for idx,it in enumerate(rec["items"],1):
                    blob=item_blob(it)
                    gclass,gscore,other=geo_class(cell,alias,blob)
                    theme_hits=[k for k in THEMES[theme] if k in blob]
                    if not theme_hits:
                        continue
                    historical=2 if re.search(r"(?:17|18|19)[0-6]\d",blob) else 0
                    source=2 if any(k in blob for k in ["地図","地籍","沿革","史稿","区史","町史","報告","台帳","絵図","公文書","遺跡"]) else 0
                    exact_kw=2 if keyword in blob else 0
                    score=gscore+historical+source+exact_kw+min(len(theme_hits),3)
                    row={
                        "rank":cell["rank"],"address":cell["address"],"cell_id":cell["cell_id"],"grid_index":cell["grid_index"],
                        "theme":theme,"alias":alias,"keyword":keyword,"query":query,"result_rank":idx,
                        "geo_class":gclass,"other_prefecture_tokens":other,"relevance_score":score,
                        "matched_theme_keywords":" | ".join(theme_hits),**it,
                        "status":"catalog_candidate_open_source_and_verify_spatial_scope",
                        "scoring_effect":"none",
                    }
                    lead_rows.append(row); cell_theme_leads.append(row)
        # Summary is intentionally search-completion evidence, not negative evidence.
        credible=[r for r in cell_theme_leads if r["geo_class"] in ("tokyo_ward_alias_supported","tokyo_alias_supported") and r["relevance_score"]>=8]
        credible.sort(key=lambda r:(-r["relevance_score"],r["result_rank"]))
        failures=sum(bool(cache[f"{a} {k}"]["error"]) for a in cell["aliases"] for k in keywords)
        summary_rows.append({
            "rank":cell["rank"],"address":cell["address"],"cell_id":cell["cell_id"],"grid_index":cell["grid_index"],
            "theme":theme,"query_count":len(cell["aliases"])*len(keywords),"query_failures":failures,
            "catalog_candidate_count":len(cell_theme_leads),"credible_tokyo_metadata_candidate_count":len(credible),
            "top_candidates":" || ".join(f"[{r['relevance_score']}] {r['title']} ({r['date']}; {r['alias']}+{r['keyword']}; {r['geo_class']})" for r in credible[:8]),
            "matrix_recommendation":"candidate_source_open_required" if credible else "defined_ndl_catalog_scan_no_credible_lead_not_negative",
            "quality_rule":"catalog metadata never proves event location; zero credible leads never proves absence",
        })

# De-duplicate leads generated by overlapping keywords, retaining the strongest row.
best={}
for r in lead_rows:
    key=(r["cell_id"],r["theme"],r["title"],r["date"],r["identifiers"])
    old=best.get(key)
    if old is None or r["relevance_score"]>old["relevance_score"]:
        best[key]=r
lead_rows=list(best.values())
lead_rows.sort(key=lambda r:(r["rank"],r["theme"],-r["relevance_score"],r["result_rank"]))

write_csv("query-log-v6.csv",query_rows)
write_csv("catalog-candidates-v6.csv",lead_rows)
write_csv("cell-theme-summary-v6.csv",summary_rows)

summary={
    "version":"top10-cell-theme-ndl-v6-20260813",
    "api":API,
    "cellCount":len(CELLS),
    "themeCount":len(THEMES),
    "cellThemeCount":len(CELLS)*len(THEMES),
    "uniqueQueries":len(cache),
    "successfulQueries":sum(not r["error"] for r in cache.values()),
    "failedQueries":sum(bool(r["error"]) for r in cache.values()),
    "catalogCandidateRowsDeduped":len(lead_rows),
    "cellThemesWithCredibleTokyoMetadataCandidates":sum(r["credible_tokyo_metadata_candidate_count"]>0 for r in summary_rows),
    "cellThemesWithNoCredibleLeadUnderDefinedNDLScan":sum(r["credible_tokyo_metadata_candidate_count"]==0 and r["query_failures"]==0 for r in summary_rows),
    "rules":[
        "This is a defined-source NDL catalog scan, not a complete historical investigation.",
        "No-hit and no-credible-lead mean only no lead under the recorded NDL queries, never absence or safety.",
        "Catalog metadata must be opened and spatial scope verified before any cell-theme status can become positive evidence.",
        "Same-name geography is treated as a risk; Tokyo/ward metadata improves priority but does not prove cell intersection.",
        "All outputs have scoringEffect=none until source text/image and geometry are reviewed.",
    ],
}
(OUT/"SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
(OUT/"README.md").write_text(
    "# 本命10セル × 10テーマ NDL定義検索 v6\n\n"
    "現町名・自治体で確認済みの旧町名と、V10の10テーマ語を組み合わせてNDL Searchを逐次走査する。"
    "目的は本文確認候補の再現可能な抽出と、検索済み範囲の記録。目録no-hitは不存在証明ではない。"
    "東京/区名/aliasのメタデータ整合を優先度に使うが、資料を開いて位置を確認するまでcellId証拠へ昇格しない。"
    "全件scoringEffect=none。\n",
    encoding="utf-8",
)
with (OUT/"SHA256SUMS.txt").open("w",encoding="utf-8") as f:
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!="SHA256SUMS.txt":
            f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
print(json.dumps(summary,ensure_ascii=False))
