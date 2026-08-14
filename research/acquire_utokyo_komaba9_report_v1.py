#!/usr/bin/env python3
"""Acquire and slice the official UTokyo Komaba I-9 excavation report.

The public PDF is large enough to be awkward for ordinary web preview. This
script downloads the official file directly, searches its text layer for the
cremation-ossuary / Mathematics building terms, and renders matching pages plus
neighbors for spatial QA. No feature geometry is promoted by this step.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF
import requests

OUT = Path("out-utokyo-komaba9-report-v1")
PDF_URL = "https://www.aru.u-tokyo.ac.jp/img/nenpou02-b.pdf"
PUBLICATIONS = "https://www.aru.u-tokyo.ac.jp/publications-lists.html"
SITE_PAGE = "https://www.aru.u-tokyo.ac.jp/utokyo-sites.html"
TERMS = ["火葬", "蔵骨", "骨", "数理", "研究棟", "駒Ⅰ9", "駒I9", "土坑", "平面図", "配置図"]
HEADERS = {"User-Agent": "iyashiro-map-v10-komaba-archaeology/1.0 public research"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def compact(text: str, term: str, radius: int = 220) -> str:
    i = text.find(term)
    if i < 0:
        return ""
    s = max(0, i-radius); e = min(len(text), i+len(term)+radius)
    return re.sub(r"\s+", " ", text[s:e]).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    r = requests.get(PDF_URL, headers=HEADERS, timeout=180)
    r.raise_for_status()
    pdf = OUT / "utokyo-nenpou02-b.pdf"
    pdf.write_bytes(r.content)
    doc = fitz.open(pdf)
    page_rows = []
    hit_pages = set()
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        hits = [t for t in TERMS if t in text]
        if hits:
            hit_pages.add(i)
        page_rows.append({
            "pageIndex": i,
            "pageNumber": i+1,
            "textChars": len(text),
            "hits": hits,
            "snippets": {t: compact(text,t) for t in hits[:6]},
        })
    # Render hits plus one-page neighbors. If the exact terms are image-only,
    # also render first 18 pages and TOC-like pages with substantial text so QA can continue.
    render_pages = set()
    for i in hit_pages:
        for j in range(max(0,i-1), min(len(doc), i+2)):
            render_pages.add(j)
    if not render_pages:
        render_pages.update(range(min(18, len(doc))))
    # Cap to keep artifact manageable, prioritizing exact-term pages and neighbors.
    render_pages = sorted(render_pages)[:40]
    rendered = []
    render_dir = OUT / "rendered-pages"; render_dir.mkdir(exist_ok=True)
    for i in render_pages:
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(2.2,2.2), alpha=False)
        p = render_dir / f"page-{i+1:03d}.png"
        pix.save(p)
        rendered.append({
            "pageIndex": i,
            "pageNumber": i+1,
            "file": str(p.relative_to(OUT)),
            "width": pix.width,
            "height": pix.height,
            "sha256": sha(p),
            "hits": page_rows[i]["hits"],
        })
    summary = {
        "version": "v10-utokyo-komaba9-report-v1-20260815",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {"pdfUrl": PDF_URL, "publicationsPage": PUBLICATIONS, "sitePage": SITE_PAGE},
        "pdfBytes": pdf.stat().st_size,
        "pdfSha256": sha(pdf),
        "pageCount": len(doc),
        "textLayerHitPages": [i+1 for i in sorted(hit_pages)],
        "termHitCounts": {t: sum(1 for row in page_rows if t in row["hits"]) for t in TERMS},
        "renderedPages": rendered,
        "pageIndex": page_rows,
        "policy": {
            "officialSource": True,
            "excavationSiteIdentityFixed": True,
            "featureGeometryVerified": False,
            "formalHistoricalGeometryPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextGate": "inspect rendered plan pages; locate the ossuary feature inside the excavation grid/site plan, then georeference site controls to modern coordinates",
        },
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for p in sorted(OUT.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{sha(p)}  {p.relative_to(OUT)}\n")
    print(json.dumps({
        "pdfBytes": summary["pdfBytes"],
        "pageCount": summary["pageCount"],
        "textLayerHitPages": summary["textLayerHitPages"],
        "termHitCounts": summary["termHitCounts"],
        "renderedPageNumbers": [x["pageNumber"] for x in rendered],
        "policy": summary["policy"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
