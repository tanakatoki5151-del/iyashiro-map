#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

from discover_plateau_datasets import (
    CATALOG_URL,
    TARGET_CODES,
    candidate_rank,
    effective_code,
    slim,
)

BUILD_ID = "ecos-practical-v2-20260817-m1-plateau-leaf-inventory-48"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def select_roots(payload: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_row in payload.get("datasets") or []:
        if not isinstance(raw_row, dict):
            continue
        if raw_row.get("format") != "3D Tiles" or raw_row.get("type_en") != "bldg":
            continue
        if str(raw_row.get("lod") or "") != "1" or raw_row.get("interior") is True:
            continue
        code = effective_code(raw_row)
        if code:
            grouped[code].append(slim(raw_row))
    selected = []
    for code in TARGET_CODES:
        rows = sorted(grouped.get(code, []), key=candidate_rank, reverse=True)
        if rows:
            selected.append({"targetCode": code, **rows[0]})
    return selected


def is_json_uri(uri: str) -> bool:
    return urllib.parse.urlparse(uri).path.lower().endswith(".json")


def suffix_for(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    if "." not in path.rsplit("/", 1)[-1]:
        return "NO_EXTENSION"
    return "." + path.rsplit(".", 1)[-1]


def probe_content(session: requests.Session, url: str) -> dict[str, Any]:
    try:
        head = session.head(url, allow_redirects=True, timeout=(20, 120))
        length = head.headers.get("Content-Length")
        response = session.get(url, headers={"Range": "bytes=0-63"}, timeout=(20, 120))
        response.raise_for_status()
        body = response.content
        return {
            "status": "PASS",
            "url": url,
            "finalUrl": response.url,
            "httpStatus": response.status_code,
            "contentType": response.headers.get("Content-Type"),
            "contentRange": response.headers.get("Content-Range"),
            "contentLength": int(length) if length and length.isdigit() else None,
            "sampleBytes": len(body),
            "sampleSha256": hashlib.sha256(body).hexdigest(),
            "magicAscii": body[:4].decode("ascii", "replace"),
            "first16Hex": body[:16].hex(),
        }
    except Exception as exc:
        return {"status": "ERROR", "url": url, "error": f"{type(exc).__name__}: {exc}"}


def walk_area(session: requests.Session, row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root_url = str(row.get("url") or row.get("composite_url") or "")
    visited: set[str] = set()
    content_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def walk_tileset(tileset_url: str, depth: int) -> None:
        if tileset_url in visited:
            return
        visited.add(tileset_url)
        try:
            response = session.get(tileset_url, timeout=(20, 180))
            response.raise_for_status()
            payload = response.json()
            final_url = response.url
            base = final_url.rsplit("/", 1)[0] + "/"
        except Exception as exc:
            errors.append({"url": tileset_url, "error": f"{type(exc).__name__}: {exc}"})
            return

        def walk_tile(tile: dict[str, Any], tile_depth: int) -> None:
            children = tile.get("children") or []
            content = tile.get("content") or {}
            uri = content.get("uri") or content.get("url")
            geometric_error = tile.get("geometricError")
            if uri:
                resolved = urllib.parse.urljoin(base, str(uri))
                if is_json_uri(resolved):
                    walk_tileset(resolved, tile_depth + 1)
                else:
                    is_final = (not children) or (geometric_error is not None and float(geometric_error) == 0.0)
                    content_rows.append(
                        {
                            "targetCode": row["targetCode"],
                            "datasetId": row.get("id"),
                            "datasetYear": row.get("year"),
                            "datasetFormatVersion": row.get("format_version"),
                            "tilesetUrl": final_url,
                            "contentUrl": resolved,
                            "depth": tile_depth,
                            "geometricError": geometric_error,
                            "childCount": len(children),
                            "isFinalContent": is_final,
                            "suffix": suffix_for(resolved),
                            "boundingVolume": tile.get("boundingVolume"),
                        }
                    )
            for child in children:
                if isinstance(child, dict):
                    walk_tile(child, tile_depth + 1)

        root = payload.get("root") or {}
        if isinstance(root, dict):
            walk_tile(root, depth)

    walk_tileset(root_url, 0)
    final_rows = [item for item in content_rows if item["isFinalContent"]]
    suffix_counts = Counter(item["suffix"] for item in final_rows)
    sample = probe_content(session, final_rows[0]["contentUrl"]) if final_rows else {"status": "NO_FINAL_CONTENT"}
    report = {
        "targetCode": row["targetCode"],
        "datasetId": row.get("id"),
        "datasetYear": row.get("year"),
        "datasetFormatVersion": row.get("format_version"),
        "rootUrl": root_url,
        "tilesetsVisited": len(visited),
        "allContentTiles": len(content_rows),
        "finalContentTiles": len(final_rows),
        "parentContentTiles": len(content_rows) - len(final_rows),
        "finalSuffixCounts": dict(sorted(suffix_counts.items())),
        "traversalErrors": errors,
        "sampleContent": sample,
    }
    return report, content_rows


def main() -> int:
    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "ECOSCAPE-PLATEAU-LEAF-INVENTORY/1.0"})

    catalog_response = session.get(CATALOG_URL, timeout=(30, 240))
    catalog_response.raise_for_status()
    catalog = catalog_response.json()
    roots = select_roots(catalog)

    area_reports = []
    all_content = []
    for index, row in enumerate(roots, start=1):
        report, content = walk_area(session, row)
        area_reports.append(report)
        all_content.extend(content)
        print(
            f"PLATEAU inventory {index}/{len(roots)} {row['targetCode']} "
            f"final={report['finalContentTiles']} errors={len(report['traversalErrors'])}",
            flush=True,
        )

    final_content = [row for row in all_content if row["isFinalContent"]]
    final_urls = {row["contentUrl"] for row in final_content}
    sample_status = Counter((row.get("sampleContent") or {}).get("status") for row in area_reports)
    sample_magic = Counter((row.get("sampleContent") or {}).get("magicAscii") for row in area_reports)
    suffix_counts = Counter(row["suffix"] for row in final_content)
    zero_final = [row["targetCode"] for row in area_reports if row["finalContentTiles"] == 0]
    traversal_error_count = sum(len(row["traversalErrors"]) for row in area_reports)

    audit = {
        "buildId": BUILD_ID,
        "targetCodes": len(TARGET_CODES),
        "selectedRoots": len(roots),
        "areaReports": len(area_reports),
        "tilesetsVisited": sum(row["tilesetsVisited"] for row in area_reports),
        "allContentTiles": len(all_content),
        "finalContentTiles": len(final_content),
        "uniqueFinalContentUrls": len(final_urls),
        "duplicateFinalContentUrls": len(final_content) - len(final_urls),
        "parentContentTilesExcluded": len(all_content) - len(final_content),
        "finalSuffixCounts": dict(sorted(suffix_counts.items())),
        "sampleStatusCounts": dict(sorted(sample_status.items())),
        "sampleMagicCounts": dict(sorted((str(k), v) for k, v in sample_magic.items())),
        "zeroFinalContentCodes": zero_final,
        "traversalErrorCount": traversal_error_count,
        "catalogSha256": hashlib.sha256(canonical_bytes(catalog)).hexdigest(),
        "qaPass": len(roots) == len(TARGET_CODES) and not zero_final and traversal_error_count == 0 and len(final_content) == len(final_urls) and sample_status.get("ERROR", 0) == 0,
        "scoringEffect": "none",
    }

    (output / "PLATEAU_LEAF_AREA_REPORTS_48.json").write_text(
        json.dumps(area_reports, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "PLATEAU_CONTENT_TILE_MANIFEST_48.json").write_text(
        json.dumps(all_content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (output / "PLATEAU_LEAF_INVENTORY_AUDIT.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "README.md").write_text(
        "# ECOSCAPE PLATEAU leaf-tile inventory\n\n"
        "Traverses the selected official LOD1 building tilesets for all 48 target areas. "
        "Parent content is separated from final content so lower-detail duplicate geometry "
        "will not be counted in the practical 120,662-cell build.\n",
        encoding="utf-8",
    )
    names = [
        "PLATEAU_LEAF_AREA_REPORTS_48.json",
        "PLATEAU_CONTENT_TILE_MANIFEST_48.json",
        "PLATEAU_LEAF_INVENTORY_AUDIT.json",
        "README.md",
    ]
    lines = []
    for name in names:
        body = (output / name).read_bytes()
        lines.append(f"{hashlib.sha256(body).hexdigest()}  {name}")
    (output / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not audit["qaPass"]:
        raise SystemExit("PLATEAU leaf inventory QA failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
