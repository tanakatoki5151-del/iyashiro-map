#!/usr/bin/env python3
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "veil-network-out")
RAW = OUT / "raw"
REPORTS = OUT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)


def decode_bytes(data: bytes):
    for enc in ["utf-8-sig", "cp932", "shift_jis"]:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def profile(path: Path):
    data = path.read_bytes()
    text, encoding = decode_bytes(data)
    reader = csv.reader(text.splitlines())
    rows = list(reader)
    headers = rows[0] if rows else []
    joined = "|".join(headers).lower()
    has_lat = bool(re.search(r"緯度|latitude|(^|\W)lat($|\W)", joined))
    has_lon = bool(re.search(r"経度|longitude|(^|\W)(lon|lng)($|\W)", joined))
    has_address = bool(re.search(r"住所|所在地|所在|address|location|町丁目|町丁|地番", joined))
    return {
        "fileName": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "encoding": encoding,
        "rowCountIncludingHeader": len(rows),
        "recordCountApprox": max(0, len(rows) - 1),
        "columnCount": len(headers),
        "headers": headers,
        "hasLat": has_lat,
        "hasLon": has_lon,
        "hasAddress": has_address,
        "locationUsability": "LOCATABLE_TABLE_HEADER" if (has_lat and has_lon) or has_address else "TABLE_HEADER_NO_LOCATION_FIELD",
        "firstRows": rows[1:6],
    }

profiles = [profile(p) for p in sorted(RAW.glob("*.csv"))]
(REPORTS / "csv-payload-profiles.json").write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
print("VEIL_CSV_PAYLOAD_PROFILES=" + json.dumps(profiles, ensure_ascii=False))
