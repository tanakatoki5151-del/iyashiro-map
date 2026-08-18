from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import shutil
import ssl
import urllib.request
from pathlib import Path

YEARS = (2019, 2020, 2021)
OUT = Path("output")
RAW = Path("raw")
OUT.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)

TOKYO_WARDS = set(range(101, 124))
YOKOHAMA_WARDS = set(range(101, 119))
KAWASAKI_WARDS = set(range(131, 138))


def normalize_header(value: str) -> str:
    value = value.replace("\ufeff", "")
    value = value.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s_　()・]", "", value).strip()


def find_index(headers: list[str], *candidates: str) -> int:
    normalized = [normalize_header(x) for x in headers]
    for candidate in candidates:
        needle = normalize_header(candidate)
        for idx, value in enumerate(normalized):
            if value == needle:
                return idx
    for candidate in candidates:
        needle = normalize_header(candidate)
        for idx, value in enumerate(normalized):
            if needle and (needle in value or value in needle):
                return idx
    raise KeyError(f"header not found: {candidates}; headers={headers}")


def dms_to_decimal(value: str, longitude: bool = False) -> str:
    digits = re.sub(r"\D", "", value or "")
    expected = 10 if longitude else 9
    if len(digits) != expected:
        return ""
    deg_len = 3 if longitude else 2
    deg = int(digits[:deg_len])
    minute = int(digits[deg_len : deg_len + 2])
    sec_milli = int(digits[deg_len + 2 :])
    decimal = deg + minute / 60 + (sec_milli / 1000) / 3600
    return f"{decimal:.9f}"


def is_target(pref: str, municipality: str) -> bool:
    try:
        p = int(pref)
        m = int(municipality)
    except ValueError:
        return False
    if p == 30 and m in TOKYO_WARDS:
        return True
    return p == 45 and (m in YOKOHAMA_WARDS or m in KAWASAKI_WARDS)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(year: int) -> tuple[Path, str]:
    candidates = [
        f"https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/honhyo_{year}.csv",
        f"https://xs489works.xsrv.jp/pmtiles-data/traffic-accident/data/honhyo_{year}.csv",
    ]
    dest = RAW / f"honhyo_{year}.csv"
    last_error = None
    for url in candidates:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 EVENTREG research extractor"}
            )
            with urllib.request.urlopen(
                req, timeout=180, context=ssl.create_default_context()
            ) as response, dest.open("wb") as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
            if dest.stat().st_size < 1_000_000:
                raise RuntimeError(f"download too small: {dest.stat().st_size}")
            return dest, url
        except Exception as exc:
            last_error = repr(exc)
            if dest.exists():
                dest.unlink()
    raise RuntimeError(f"all downloads failed for {year}: {last_error}")


OUTPUT_FIELDS = [
    "sourceYear",
    "prefectureCode",
    "municipalityCode",
    "severityCode",
    "fatalities",
    "injuries",
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "latitude",
    "longitude",
    "policeStationCode",
    "accidentTypeCode",
    "roadShapeCode",
    "weatherCode",
    "dayNightCode",
    "sourceRow",
]

summaries = []
for release_year in YEARS:
    raw_path, source_url = download(release_year)
    target_path = OUT / (
        f"EVENTREG_NPA_{release_year}_TOKYO_KANAGAWA_"
        "ALL_INJURY_LEGACY_REPAIRED_v1.csv.gz"
    )
    diagnostics_path = OUT / (
        f"EVENTREG_NPA_{release_year}_LEGACY_SCHEMA_DIAGNOSTIC_v1.json"
    )

    with raw_path.open("r", encoding="cp932", errors="replace", newline="") as src:
        reader = csv.reader(src)
        headers = next(reader)
        indices = {
            "material": find_index(headers, "資料区分"),
            "pref": find_index(headers, "都道府県コード"),
            "station": find_index(headers, "警察署等コード"),
            "ticket": find_index(headers, "本票番号"),
            "severity": find_index(headers, "事故内容"),
            "fatalities": find_index(headers, "死者数"),
            "injuries": find_index(headers, "負傷者数"),
            "municipality": find_index(headers, "市区町村コード"),
            "year": find_index(headers, "発生日時年", "発生日時_年"),
            "month": find_index(headers, "発生日時月", "発生日時_月"),
            "day": find_index(headers, "発生日時日", "発生日時_日"),
            "hour": find_index(headers, "発生日時時", "発生日時_時"),
            "minute": find_index(headers, "発生日時分", "発生日時_分"),
            "daynight": find_index(headers, "昼夜"),
            "weather": find_index(headers, "天候"),
            "roadshape": find_index(headers, "道路形状"),
            "accidenttype": find_index(headers, "事故類型"),
            "lat": find_index(headers, "地点緯度北緯", "地点_緯度北緯"),
            "lon": find_index(headers, "地点経度東経", "地点_経度東経"),
        }
        nationwide = target = fatal = coordinates = 0
        pref_counts: dict[str, int] = {}
        with gzip.open(
            target_path, "wt", encoding="utf-8", newline="", compresslevel=9
        ) as dst:
            writer = csv.DictWriter(dst, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            for source_row, row in enumerate(reader, start=2):
                if not row or len(row) <= max(indices.values()):
                    continue
                nationwide += 1
                pref = row[indices["pref"]].strip()
                municipality = row[indices["municipality"]].strip()
                pref_counts[pref] = pref_counts.get(pref, 0) + 1
                if not is_target(pref, municipality):
                    continue
                lat = dms_to_decimal(row[indices["lat"]], longitude=False)
                lon = dms_to_decimal(row[indices["lon"]], longitude=True)
                fatalities = row[indices["fatalities"]].strip()
                writer.writerow(
                    {
                        "sourceYear": str(release_year),
                        "prefectureCode": pref,
                        "municipalityCode": municipality,
                        "severityCode": row[indices["severity"]].strip(),
                        "fatalities": fatalities,
                        "injuries": row[indices["injuries"]].strip(),
                        "year": row[indices["year"]].strip(),
                        "month": row[indices["month"]].strip(),
                        "day": row[indices["day"]].strip(),
                        "hour": row[indices["hour"]].strip(),
                        "minute": row[indices["minute"]].strip(),
                        "latitude": lat,
                        "longitude": lon,
                        "policeStationCode": row[indices["station"]].strip(),
                        "accidentTypeCode": row[indices["accidenttype"]].strip(),
                        "roadShapeCode": row[indices["roadshape"]].strip(),
                        "weatherCode": row[indices["weather"]].strip(),
                        "dayNightCode": row[indices["daynight"]].strip(),
                        "sourceRow": str(source_row),
                    }
                )
                target += 1
                if int(fatalities or "0") > 0:
                    fatal += 1
                if lat and lon:
                    coordinates += 1

    diagnostics = {
        "sourceYear": release_year,
        "sourceUrl": source_url,
        "rawBytes": raw_path.stat().st_size,
        "rawSha256": sha256(raw_path),
        "headerCount": len(headers),
        "headers": headers,
        "indices": indices,
        "nationwideRows": nationwide,
        "target48Rows": target,
        "fatalTarget48Rows": fatal,
        "coordinateRows": coordinates,
        "prefectureCounts": pref_counts,
        "outputFile": target_path.name,
        "outputBytes": target_path.stat().st_size,
        "outputSha256": sha256(target_path),
    }
    diagnostics_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summaries.append(diagnostics)
    print(
        json.dumps(
            {
                key: diagnostics[key]
                for key in (
                    "sourceYear",
                    "nationwideRows",
                    "target48Rows",
                    "fatalTarget48Rows",
                    "coordinateRows",
                )
            },
            ensure_ascii=False,
        )
    )

total = {
    "buildId": "EVENTREG_NPA_2019_2021_LEGACY_REPAIR_v1",
    "status": "COMPLETE" if all(x["target48Rows"] > 0 for x in summaries) else "FAIL",
    "years": summaries,
    "totals": {
        "nationwideRows": sum(x["nationwideRows"] for x in summaries),
        "target48Rows": sum(x["target48Rows"] for x in summaries),
        "fatalTarget48Rows": sum(x["fatalTarget48Rows"] for x in summaries),
        "coordinateRows": sum(x["coordinateRows"] for x in summaries),
    },
    "semantics": (
        "Source extraction only. No score, rank, automatic exclusion or "
        "verified-absence claim."
    ),
}
(OUT / "EVENTREG_NPA_2019_2021_LEGACY_REPAIR_SUMMARY_v1.json").write_text(
    json.dumps(total, ensure_ascii=False, indent=2), encoding="utf-8"
)
if total["status"] != "COMPLETE":
    raise SystemExit("legacy repair produced empty target year")
