#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, re, time
from collections import defaultdict
from pathlib import Path
from typing import Any
import requests
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform as geom_transform
from shapely.strtree import STRtree
try:
    from shapely.validation import make_valid
except ImportError:
    make_valid = None
from common import canonical_bytes, deterministic_csv_gz, load_grid, sha256_bytes, sha256_file, write_sha256s

SOURCE_ID = "SRC-ECO-MOE-001"
SOURCE_NAME = "環境省 現存植生図2024 関東ブロック"
SERVICE_URL = "https://svr-moej.gisservice.jp/arcgis/rest/services/Hosted/veg2024bk3/FeatureServer/0/query"
LAYER_URL = "https://svr-moej.gisservice.jp/arcgis/rest/services/Hosted/veg2024bk3/FeatureServer/0"
FIELDS = ["fid", "凡例コード", "凡例名", "植生自然度", "植生自然度区分", "植生区分", "作成年度", "地域ブロック"]
BUILD_ID = "ecos-practical-v2-20260817-m1-moe-level-b-120662"
METHOD = "ECOSCAPE_MOE_BULK_INTERSECTION_PRACTICAL_v2"
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def valid(g: Any) -> Any:
    if g.is_valid:
        return g
    return make_valid(g) if make_valid else g.buffer(0)


def natural(value: Any) -> float | None:
    m = NUM.search(str(value)) if value not in (None, "") else None
    return float(m.group(0)) if m else None


def post(session: requests.Session, data: dict[str, Any], retries: int = 7) -> requests.Response:
    error: Exception | None = None
    for attempt in range(retries):
        try:
            r = session.post(SERVICE_URL, data=data, timeout=(30, 180))
            r.raise_for_status()
            payload = r.json()
            if payload.get("error"):
                raise RuntimeError(stable(payload["error"]))
            return r
        except Exception as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(min(30, 1.2 * 2**attempt))
    raise RuntimeError(f"MOE request failed: {error}")


def fetch_source(cells: list[dict[str, Any]], cache: Path, chunk_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache.mkdir(parents=True, exist_ok=True)
    envelope = {
        "xmin": min(c["west"] for c in cells), "ymin": min(c["south"] for c in cells),
        "xmax": max(c["east"] for c in cells), "ymax": max(c["north"] for c in cells),
        "spatialReference": {"wkid": 4326},
    }
    base = {"where": "1=1", "geometry": stable(envelope), "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects", "f": "json"}
    session = requests.Session()
    session.headers["User-Agent"] = "ECOSCAPE-Practical-v2 non-commercial-research"
    ids_payload = post(session, {**base, "returnIdsOnly": "true", "returnGeometry": "false"}).json()
    oid = ids_payload.get("objectIdFieldName") or "OBJECTID"
    ids = sorted({int(x) for x in ids_payload.get("objectIds", [])})
    source: dict[str, dict[str, Any]] = {}
    chunks: list[dict[str, Any]] = []
    for n, start in enumerate(range(0, len(ids), chunk_size)):
        part = ids[start:start + chunk_size]
        r = post(session, {
            "where": "1=1", "objectIds": ",".join(map(str, part)),
            "outFields": ",".join(dict.fromkeys([oid, *FIELDS])), "returnGeometry": "true",
            "outSR": "4326", "geometryPrecision": "8", "returnExceededLimitFeatures": "true", "f": "geojson",
        })
        raw = r.content
        path = cache / f"chunk-{n:04d}.geojson"
        path.write_bytes(raw)
        features = r.json().get("features") or []
        for feature in features:
            props = feature.get("properties") or {}
            key = str(props.get(oid) or feature.get("id") or props.get("fid") or sha256_bytes(canonical_bytes(feature)))
            source[key] = feature
        chunks.append({"chunk": n, "requested": len(part), "returned": len(features), "bytes": len(raw), "sha256": sha256_bytes(raw)})
        print(f"MOE source {n+1}/{math.ceil(len(ids)/chunk_size)}", flush=True)
    manifest = {
        "sourceId": SOURCE_ID, "sourceName": SOURCE_NAME, "serviceUrl": SERVICE_URL, "layerUrl": LAYER_URL,
        "objectIdField": oid, "objectIdCount": len(ids), "uniqueFeatureCount": len(source),
        "queryEnvelopeWgs84": envelope, "chunks": chunks, "retrievedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return [source[k] for k in sorted(source, key=lambda x: (len(x), x))], manifest


def build(cells: list[dict[str, Any]], features: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    project = Transformer.from_crs("EPSG:4326", "EPSG:6677", always_xy=True)
    geoms: list[Any] = []
    props: list[dict[str, Any]] = []
    rejected = 0
    for feature in features:
        if not feature.get("geometry"):
            continue
        try:
            g = valid(geom_transform(project.transform, valid(shape(feature["geometry"]))))
            if not g.is_empty:
                geoms.append(g); props.append(feature.get("properties") or {})
        except Exception:
            rejected += 1
    tree = STRtree(geoms)
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for i, cell in enumerate(cells, start=1):
        x1, y1 = project.transform(cell["west"], cell["south"])
        x2, y2 = project.transform(cell["east"], cell["north"])
        cg = box(min(x1,x2), min(y1,y2), max(x1,x2), max(y1,y2))
        area = float(cg.area)
        categories: dict[tuple[str,str,str,str,str], float] = defaultdict(float)
        candidate_count = 0
        for raw_idx in tree.query(cg):
            idx = int(raw_idx); candidate_count += 1
            try:
                clipped = geoms[idx].intersection(cg)
                if clipped.is_empty or clipped.area <= 0.01:
                    continue
                p = props[idx]
                key = tuple(str(p.get(k) or "") for k in ["凡例コード","凡例名","植生自然度","植生自然度区分","植生区分"])
                categories[key] += float(clipped.area)
            except Exception:
                continue
        ranked = sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))
        covered = min(1.0, sum(v for _,v in ranked) / area) if area else 0.0
        if ranked:
            key, dom_area = ranked[0]
            status = "PASS"
            confidence = "HIGH" if covered >= 0.95 else "MEDIUM"
            top = [{"legendCode":k[0] or None,"legendName":k[1] or None,"vegetationNaturalness":k[2] or None,"naturalnessClass":k[3] or None,"vegetationClass":k[4] or None,"cellFraction":min(1.0,v/area)} for k,v in ranked[:3]]
            weighted = [(natural(k[2]), v) for k,v in ranked]
            den = sum(v for n,v in weighted if n is not None)
            mean_nat = sum(n*v for n,v in weighted if n is not None)/den if den else None
            missing = ""
        else:
            key = ("","","","",""); dom_area = 0.0; status = "EXPLICIT_NO_INTERSECTION"; confidence = "MEDIUM"; top=[]; mean_nat=None
            missing = "NO_INTERSECTING_VEGETATION_POLYGON"
        counts[status] += 1
        rows.append({
            "ordinal": cell["ordinal"], "cellId": cell["cellId"], "row": cell["row"], "column": cell["column"],
            "centerLat": f"{cell['centerLat']:.12f}", "centerLon": f"{cell['centerLon']:.12f}", "status": status,
            "candidateFeatureCount": candidate_count, "coveredFraction": f"{covered:.8f}", "uncoveredFraction": f"{1-covered:.8f}",
            "categoryCount": len(ranked), "dominantLegendCode": key[0] or "", "dominantLegendName": key[1] or "",
            "dominantVegetationNaturalness": key[2] or "", "dominantNaturalnessClass": key[3] or "", "dominantVegetationClass": key[4] or "",
            "dominantCellFraction": f"{min(1.0,dom_area/area):.8f}" if area else "", "naturalnessAreaWeightedMean": "" if mean_nat is None else f"{mean_nat:.6f}",
            "topCategoriesJson": stable(top), "confidenceLevel": confidence, "sourceId": SOURCE_ID, "sourceProductYear": "2024",
            "methodVersion": METHOD, "provenanceUrl": LAYER_URL, "coverageAbsenceNotPenalty": "true", "missingReason": missing,
            "buildId": BUILD_ID, "scoringEffect": "none",
        })
        if i % 10000 == 0:
            print(f"MOE cells {i}/{len(cells)}", flush=True)
    audit = {
        "buildId": BUILD_ID, "canonicalCells": len(cells), "rows": len(rows), "uniqueCells": len({r['cellId'] for r in rows}),
        "duplicateCount": len(rows)-len({r['cellId'] for r in rows}), "silentMissing": len(cells)-len(rows),
        "statusCounts": dict(sorted(counts.items())), "sourceFeatureCount": len(features), "projectedFeatureCount": len(geoms),
        "sourceGeometryRejected": rejected, "provenanceCoverage": 1.0, "coverageAbsenceNotPenalty": True, "scoringEffect": "none",
        "qaPass": len(rows)==len(cells) and len({r['cellId'] for r in rows})==len(cells),
    }
    return rows, audit


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--grid",type=Path,required=True); ap.add_argument("--output-dir",type=Path,required=True); ap.add_argument("--chunk-size",type=int,default=300)
    args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True); cache=args.output_dir/"_cache"
    contract,cells=load_grid(args.grid); features,manifest=fetch_source(cells,cache,args.chunk_size); rows,audit=build(cells,features)
    facts=args.output_dir/"ECOSCAPE_MOE_LEVEL_B_120662.csv.gz"; deterministic_csv_gz(facts,list(rows[0]),rows)
    release={**audit,"gridContractId":contract["contractId"],"gridMaskSha256":contract["maskSha256"],"sourceManifestSha256":sha256_bytes(canonical_bytes(manifest)),"factsGzipSha256":sha256_file(facts)}
    (args.output_dir/"MOE_SOURCE_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (args.output_dir/"MOE_FULL_AUDIT.json").write_text(json.dumps(release,ensure_ascii=False,indent=2),encoding="utf-8")
    (args.output_dir/"README.md").write_text("# ECOSCAPE MOE practical Level B\n\nOfficial 2024 vegetation polygons summarized for all 120,662 canonical 100 m cells. Absence is explicit and never a penalty. scoringEffect=none.\n",encoding="utf-8")
    write_sha256s(args.output_dir,["ECOSCAPE_MOE_LEVEL_B_120662.csv.gz","MOE_SOURCE_MANIFEST.json","MOE_FULL_AUDIT.json","README.md"])
    for p in cache.glob("*"): p.unlink()
    cache.rmdir(); print(json.dumps(release,ensure_ascii=False,indent=2))
    if not release["qaPass"]: raise SystemExit("MOE QA failed")
    return 0
if __name__=="__main__": raise SystemExit(main())
