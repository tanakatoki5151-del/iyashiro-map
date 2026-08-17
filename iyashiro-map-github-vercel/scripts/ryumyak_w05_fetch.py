#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BUILD_ID = "ryumyak-mega06r-r2-w05-acquisition-v2"
ROOT = Path("artifacts")
UNPACKED = ROOT / "unpacked"

# 13/14 are the target prefectures. 11/12 are read-only boundary context so
# rivers touching Tokyo are not truncated at the Saitama/Chiba borders.
SOURCES = {
    pref: [
        f"https://nlftp.mlit.go.jp/ksj/gml/data/W05/W05-08/W05-08_{pref}_GML.zip",
        f"https://nlftp.mlit.go.jp/ksj/gml/data/W05/W05-08/W05-08_{pref}.zip",
    ]
    for pref in ("11", "12", "13", "14")
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RYUMYAK-MEGA06R-R2/1.0"},
    )
    with urllib.request.urlopen(request, timeout=300) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def fetch_pref(pref: str) -> tuple[Path, str]:
    target = ROOT / f"W05-08_{pref}_GML.zip"
    errors: list[str] = []
    for url in SOURCES[pref]:
        try:
            print(f"fetch {pref}: {url}", flush=True)
            download(url, target)
            head = target.read_bytes()[:16]
            if head[:2] != b"PK":
                raise RuntimeError(f"not ZIP, first16={head.hex()}")
            if target.stat().st_size < 100_000:
                raise RuntimeError(f"archive unexpectedly small: {target.stat().st_size}")
            with zipfile.ZipFile(target) as archive:
                bad = archive.testzip()
                if bad is not None:
                    raise RuntimeError(f"corrupt ZIP member: {bad}")
                destination = UNPACKED / pref
                destination.mkdir(parents=True, exist_ok=True)
                archive.extractall(destination)
            return target, url
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
            target.unlink(missing_ok=True)
    raise RuntimeError(" | ".join(errors))


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    UNPACKED.mkdir(parents=True, exist_ok=True)

    selected_urls: dict[str, str] = {}
    for pref in SOURCES:
        target, selected_url = fetch_pref(pref)
        selected_urls[pref] = selected_url
        print(f"verified {target} bytes={target.stat().st_size} sha256={sha256(target)}", flush=True)

    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        files.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "firstHex": path.read_bytes()[:16].hex(),
            }
        )

    manifest = {
        "buildId": BUILD_ID,
        "generatedAtUTC": datetime.now(timezone.utc).isoformat(),
        "source": "MLIT National Land Numerical Information W05",
        "sourceVintage": "FY2008 Kanto hydrography",
        "targetPrefectures": ["13", "14"],
        "boundaryContextPrefectures": ["11", "12"],
        "selectedUrls": selected_urls,
        "interpretationBoundary": (
            "Official FY2008 hydrography backbone; not a claim of complete 2026 current geometry. "
            "Saitama and Chiba are topology context only and never become target-area cells."
        ),
        "files": files,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
