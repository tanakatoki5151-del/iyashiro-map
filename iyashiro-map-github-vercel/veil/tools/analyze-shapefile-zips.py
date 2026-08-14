#!/usr/bin/env python3
import csv
import json
import math
import struct
import sys
import zipfile
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "veil-network-out")
RAW = OUT / "raw"
REPORTS = OUT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

SHAPE_TYPES = {
    0: "NullShape", 1: "Point", 3: "PolyLine", 5: "Polygon", 8: "MultiPoint",
    11: "PointZ", 13: "PolyLineZ", 15: "PolygonZ", 18: "MultiPointZ",
    21: "PointM", 23: "PolyLineM", 25: "PolygonM", 28: "MultiPointM",
    31: "MultiPatch",
}


def read_shp_header(data: bytes):
    if len(data) < 100:
        return {"valid": False, "reason": "shp_header_lt_100"}
    file_code = struct.unpack(">i", data[0:4])[0]
    version = struct.unpack("<i", data[28:32])[0]
    shape_type = struct.unpack("<i", data[32:36])[0]
    bbox = struct.unpack("<4d", data[36:68])
    return {
        "valid": file_code == 9994,
        "fileCode": file_code,
        "version": version,
        "shapeTypeCode": shape_type,
        "shapeType": SHAPE_TYPES.get(shape_type, f"Unknown({shape_type})"),
        "bbox": {"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3]},
    }


def read_dbf_header(data: bytes):
    if len(data) < 32:
        return {"valid": False, "reason": "dbf_header_lt_32", "fields": []}
    record_count = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    record_len = struct.unpack("<H", data[10:12])[0]
    fields = []
    pos = 32
    while pos + 32 <= min(header_len, len(data)):
        if data[pos] == 0x0D:
            break
        chunk = data[pos:pos+32]
        name = chunk[:11].split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        field_type = chr(chunk[11]) if chunk[11] else ""
        length = chunk[16]
        decimals = chunk[17]
        if name:
            fields.append({"name": name, "type": field_type, "length": length, "decimals": decimals})
        pos += 32
    return {
        "valid": True,
        "recordCount": record_count,
        "headerLength": header_len,
        "recordLength": record_len,
        "fields": fields,
    }


def semantic_class(name: str, fields):
    text = (name + " " + " ".join(f.get("name", "") for f in fields)).lower()
    rules = [
        ("archaeology", ["maizou", "archae", "遺跡", "埋蔵"]),
        ("cemetery_or_memorial", ["墓", "cemet", "memorial", "記念", "碑"]),
        ("hydrography", ["河川", "水路", "water", "river", "hydro", "海岸", "池", "湖"]),
        ("building", ["建物", "building", "bldg", "家屋"]),
        ("road", ["道路", "road", "street", "中心線"]),
        ("boundary", ["界", "boundary", "行政区", "町丁目", "街区"]),
        ("terrain", ["等高", "contour", "標高", "terrain"]),
        ("place_name_or_annotation", ["地名", "注記", "annotation", "text", "名称"]),
    ]
    hits = [label for label, terms in rules if any(term.lower() in text for term in terms)]
    return hits or ["unclassified"]


def infer_crs(prj_text: str):
    t = (prj_text or "").upper()
    hints = []
    for key in ["JGD2011", "JGD_2011", "JGD2000", "JGD_2000", "TOKYO", "WGS_1984", "WGS 84"]:
        if key in t:
            hints.append(key)
    if "TRANSVERSE_MERCATOR" in t or "TRANSVERSE MERCATOR" in t:
        hints.append("TRANSVERSE_MERCATOR")
    if "GEOGCS" in t or "GEOGCRS" in t:
        hints.append("GEOGRAPHIC_CRS_WKT")
    if "PROJCS" in t or "PROJCRS" in t:
        hints.append("PROJECTED_CRS_WKT")
    return sorted(set(hints))


def analyze_zip(zip_path: Path):
    report = {
        "zipName": zip_path.name,
        "zipBytes": zip_path.stat().st_size,
        "layers": [],
        "ancillaryFiles": [],
        "errors": [],
    }
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            lower_map = {n.lower(): n for n in names}
            shp_names = [n for n in names if n.lower().endswith(".shp") and not n.endswith("/")]
            for shp_name in sorted(shp_names):
                base = shp_name[:-4]
                dbf_name = lower_map.get((base + ".dbf").lower())
                prj_name = lower_map.get((base + ".prj").lower())
                cpg_name = lower_map.get((base + ".cpg").lower())
                try:
                    shp_header = read_shp_header(zf.read(shp_name)[:100])
                except Exception as exc:
                    shp_header = {"valid": False, "error": repr(exc)}
                dbf = {"valid": False, "reason": "dbf_missing", "fields": []}
                if dbf_name:
                    try:
                        dbf = read_dbf_header(zf.read(dbf_name)[:65536])
                    except Exception as exc:
                        dbf = {"valid": False, "error": repr(exc), "fields": []}
                prj = ""
                if prj_name:
                    try:
                        prj = zf.read(prj_name).decode("utf-8", errors="replace")
                    except Exception:
                        try:
                            prj = zf.read(prj_name).decode("cp932", errors="replace")
                        except Exception as exc:
                            prj = f"READ_ERROR:{exc!r}"
                cpg = None
                if cpg_name:
                    try:
                        cpg = zf.read(cpg_name).decode("ascii", errors="replace").strip()
                    except Exception:
                        cpg = None
                layer = {
                    "shpPath": shp_name,
                    "baseName": Path(base).name,
                    "shpHeader": shp_header,
                    "dbf": dbf,
                    "prjPath": prj_name,
                    "prjWkt": prj,
                    "crsHints": infer_crs(prj),
                    "cpg": cpg,
                    "semanticClasses": semantic_class(Path(base).name, dbf.get("fields", [])),
                }
                report["layers"].append(layer)
            report["ancillaryFiles"] = [
                n for n in names
                if not n.endswith("/") and Path(n).suffix.lower() not in {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx"}
            ][:500]
    except Exception as exc:
        report["errors"].append(repr(exc))
    report["layerCount"] = len(report["layers"])
    report["shapeTypes"] = sorted(set(l.get("shpHeader", {}).get("shapeType") for l in report["layers"] if l.get("shpHeader", {}).get("shapeType")))
    report["crsHintSets"] = sorted({"|".join(l.get("crsHints", [])) for l in report["layers"] if l.get("crsHints")})
    report["recordCountTotal"] = sum(int(l.get("dbf", {}).get("recordCount") or 0) for l in report["layers"])
    return report


reports = []
for zip_path in sorted(RAW.glob("*.zip")):
    print(f"analyze {zip_path}")
    reports.append(analyze_zip(zip_path))

summary = {
    "zipCount": len(reports),
    "zips": [
        {
            "zipName": r["zipName"],
            "zipBytes": r["zipBytes"],
            "layerCount": r["layerCount"],
            "recordCountTotal": r["recordCountTotal"],
            "shapeTypes": r["shapeTypes"],
            "crsHintSets": r["crsHintSets"],
            "errors": r["errors"],
        }
        for r in reports
    ],
}

(REPORTS / "shapefile-inventory.json").write_text(json.dumps({"summary": summary, "archives": reports}, ensure_ascii=False, indent=2), encoding="utf-8")

with (REPORTS / "shapefile-layers.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["zipName","shpPath","shapeType","recordCount","bbox","crsHints","semanticClasses","fieldNames","cpg"])
    for archive in reports:
        for layer in archive["layers"]:
            w.writerow([
                archive["zipName"],
                layer["shpPath"],
                layer.get("shpHeader", {}).get("shapeType"),
                layer.get("dbf", {}).get("recordCount"),
                json.dumps(layer.get("shpHeader", {}).get("bbox"), ensure_ascii=False),
                "|".join(layer.get("crsHints", [])),
                "|".join(layer.get("semanticClasses", [])),
                "|".join(x.get("name", "") for x in layer.get("dbf", {}).get("fields", [])),
                layer.get("cpg"),
            ])

print("VEIL_SHAPEFILE_INVENTORY_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
