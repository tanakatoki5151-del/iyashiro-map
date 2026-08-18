#!/usr/bin/env python3
import csv
import gzip
import hashlib
import json
import time
import urllib.request
from pathlib import Path

YEARS = range(2019, 2025)
PREF_CODES = {"30", "45"}  # Tokyo, Kanagawa in NPA code system
OUT = Path("eventreg_npa_bulk")
OUT.mkdir(exist_ok=True)


def dms_to_deg(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        s = str(int(float(value))).rjust(10, "0")
        sec = int(s[-5:]) / 1000.0
        minute = int(s[-7:-5])
        deg = int(s[:-7])
        return deg + minute / 60.0 + sec / 3600.0
    except Exception:
        return None


def download(year: int) -> Path:
    url = f"https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/honhyo_{year}.csv"
    dest = OUT / f"honhyo_{year}.csv"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EVENTREG-data-pipeline/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as w:
                while True:
                    b = r.read(1024 * 1024)
                    if not b:
                        break
                    w.write(b)
            return dest
        except Exception as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"download failed for {year}: {last}")


def parse_year(year: int, path: Path):
    out = OUT / f"EVENTREG_NPA_{year}_TOKYO_KANAGAWA_ALL_INJURY_v1.csv.gz"
    fields = [
        "sourceYear","prefectureCode","municipalityCode","severityCode","fatalities","injuries",
        "year","month","day","hour","minute","latitude","longitude","policeStationCode",
        "accidentTypeCode","roadShapeCode","weatherCode","dayNightCode","sourceRow"
    ]
    total = kept = fatal = coordinate_ok = 0
    with open(path, "r", encoding="cp932", errors="replace", newline="") as f, \
         gzip.open(out, "wt", encoding="utf-8", newline="") as g:
        r = csv.reader(f)
        w = csv.DictWriter(g, fieldnames=fields)
        w.writeheader()
        next(r, None)
        for rowno, row in enumerate(r, start=2):
            if not row:
                continue
            total += 1
            if len(row) < 64 or row[0].strip() != "1":
                continue
            pref = row[1].strip()
            if pref not in PREF_CODES:
                continue
            lat = dms_to_deg(row[60])
            lon = dms_to_deg(row[61])
            if lat is not None and lon is not None:
                coordinate_ok += 1
            sev = row[4].strip()
            if sev == "1":
                fatal += 1
            kept += 1
            w.writerow({
                "sourceYear": year,
                "prefectureCode": pref,
                "municipalityCode": row[9].strip(),
                "severityCode": sev,
                "fatalities": row[5].strip(),
                "injuries": row[6].strip(),
                "year": row[10].strip(),
                "month": row[11].strip(),
                "day": row[12].strip(),
                "hour": row[13].strip(),
                "minute": row[14].strip(),
                "latitude": "" if lat is None else f"{lat:.9f}",
                "longitude": "" if lon is None else f"{lon:.9f}",
                "policeStationCode": row[2].strip(),
                "accidentTypeCode": row[35].strip(),
                "roadShapeCode": row[23].strip(),
                "weatherCode": row[20].strip(),
                "dayNightCode": row[15].strip(),
                "sourceRow": rowno,
            })
    h = hashlib.sha256(out.read_bytes()).hexdigest()
    return {
        "year": year,
        "nationwideRowsParsed": total,
        "tokyoKanagawaRows": kept,
        "fatalRowsTokyoKanagawa": fatal,
        "coordinateRows": coordinate_ok,
        "artifact": out.name,
        "sha256": h,
        "bytes": out.stat().st_size,
    }


def main():
    results = []
    for year in YEARS:
        print(f"== {year} ==", flush=True)
        raw = download(year)
        result = parse_year(year, raw)
        print(result, flush=True)
        results.append(result)
        raw.unlink(missing_ok=True)
    summary = {
        "buildId": "eventreg-npa-2019-2024-tokyo-kanagawa-stage1-v1",
        "source": "National Police Agency traffic accident open data main tables",
        "sourceUrls": [f"https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{y}/honhyo_{y}.csv" for y in YEARS],
        "filter": {"prefectureCodes": sorted(PREF_CODES), "meaning": "Tokyo and Kanagawa; target48 municipality/cell filtering occurs in stage2 against canonical cell universe"},
        "years": results,
        "totals": {
            "nationwideRowsParsed": sum(x["nationwideRowsParsed"] for x in results),
            "tokyoKanagawaRows": sum(x["tokyoKanagawaRows"] for x in results),
            "fatalRowsTokyoKanagawa": sum(x["fatalRowsTokyoKanagawa"] for x in results),
            "coordinateRows": sum(x["coordinateRows"] for x in results),
        },
        "semantics": "Bulk traffic layer. No land score/rank/exclusion. Coordinates remain source points until target48 + 100m cell edge QA in stage2.",
    }
    (OUT / "EVENTREG_NPA_2019_2024_TOKYO_KANAGAWA_STAGE1_SUMMARY_v1.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["totals"], ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
