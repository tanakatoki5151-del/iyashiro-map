from __future__ import annotations
import base64, csv, gzip, hashlib, io, json, zlib
from pathlib import Path
from typing import Any, Iterable


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_grid(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    raw = zlib.decompress(base64.b64decode(contract["maskZlibBase64"]))
    if len(raw) != int(contract["maskBytes"]):
        raise RuntimeError("canonical grid mask length mismatch")
    if sha256_bytes(raw) != contract["maskSha256"]:
        raise RuntimeError("canonical grid mask hash mismatch")
    rows = int(contract["rows"])
    cols = int(contract["columns"])
    cells: list[dict[str, Any]] = []
    for row in range(rows):
        for col in range(cols):
            bit = row * cols + col
            if raw[bit // 8] & (1 << (7 - bit % 8)):
                lat = float(contract["originNorth"]) - row * float(contract["latitudeStep"])
                lon = float(contract["originWest"]) + col * float(contract["longitudeStep"])
                cells.append({
                    "ordinal": len(cells) + 1,
                    "cellId": f"g{row}-{col}",
                    "row": row,
                    "column": col,
                    "centerLat": lat,
                    "centerLon": lon,
                    "west": lon - float(contract["longitudeStep"]) / 2,
                    "south": lat - float(contract["latitudeStep"]) / 2,
                    "east": lon + float(contract["longitudeStep"]) / 2,
                    "north": lat + float(contract["latitudeStep"]) / 2,
                })
    if len(cells) != int(contract["validCellCount"]):
        raise RuntimeError(f"canonical grid count mismatch: {len(cells)}")
    if cells[0]["cellId"] != contract["firstCellId"] or cells[-1]["cellId"] != contract["lastCellId"]:
        raise RuntimeError("canonical grid boundary mismatch")
    return contract, cells


def deterministic_csv_gz(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)


def write_sha256s(output_dir: Path, file_names: list[str]) -> Path:
    lines = [f"{sha256_file(output_dir / name)}  {name}" for name in file_names]
    target = output_dir / "SHA256SUMS.txt"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
