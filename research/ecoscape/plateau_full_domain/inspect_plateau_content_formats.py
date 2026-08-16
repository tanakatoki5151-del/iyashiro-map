#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import requests

B3DM_URL = "https://assets.cms.plateau.reearth.io/assets/ad/5fd83a-161b-4a01-a666-a3e8c1c23759/14100_yokohama-shi_city_2024_citygml_2_op_bldg_3dtiles_14103_nishi-ku_lod1/data/data0.b3dm"
GLB_URL = "https://assets.cms.plateau.reearth.io/assets/98/c5ff8d-d6b4-40fb-8ef9-fcca1407f9c0/13106_taito-ku_city_2025_citygml_1_op_bldg_3dtiles_lod1/18/232844/39517_bldg_Building.glb"


def read_json_chunk(raw: bytes) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    magic, version, total_length = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF":
        raise ValueError(f"not GLB: {magic!r}")
    offset = 12
    chunks = []
    gltf: dict[str, Any] | None = None
    binary = b""
    while offset + 8 <= min(total_length, len(raw)):
        length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        payload = raw[offset : offset + length]
        offset += length
        kind = struct.pack("<I", chunk_type).decode("ascii", "replace")
        chunks.append({
            "type": kind,
            "length": length,
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
        if chunk_type == 0x4E4F534A:
            gltf = json.loads(payload.decode("utf-8").rstrip("\x00 \t\r\n"))
        elif chunk_type == 0x004E4942:
            binary = payload
    if gltf is None:
        raise ValueError("GLB JSON chunk missing")
    return gltf, binary, {
        "magic": magic.decode("ascii"),
        "version": version,
        "declaredLength": total_length,
        "actualLength": len(raw),
        "chunks": chunks,
    }


def decode_b3dm(raw: bytes) -> tuple[dict[str, Any], dict[str, Any], bytes, dict[str, Any]]:
    if raw[:4] != b"b3dm":
        raise ValueError("not b3dm")
    version, byte_length, ftj, ftb, btj, btb = struct.unpack_from("<6I", raw, 4)
    offset = 28
    ft_json = json.loads(raw[offset : offset + ftj].decode("utf-8").strip() or "{}")
    offset += ftj
    ft_binary = raw[offset : offset + ftb]
    offset += ftb
    bt_json = json.loads(raw[offset : offset + btj].decode("utf-8").strip() or "{}")
    offset += btj
    bt_binary = raw[offset : offset + btb]
    offset += btb
    return ft_json, bt_json, raw[offset:], {
        "version": version,
        "declaredLength": byte_length,
        "actualLength": len(raw),
        "featureTableJsonBytes": ftj,
        "featureTableBinaryBytes": ftb,
        "batchTableJsonBytes": btj,
        "batchTableBinaryBytes": btb,
        "featureTableBinarySha256": hashlib.sha256(ft_binary).hexdigest(),
        "batchTableBinarySha256": hashlib.sha256(bt_binary).hexdigest(),
        "glbOffset": offset,
    }


def accessor_summary(gltf: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, acc in enumerate(gltf.get("accessors") or []):
        rows.append({
            "index": index,
            "bufferView": acc.get("bufferView"),
            "byteOffset": acc.get("byteOffset"),
            "componentType": acc.get("componentType"),
            "normalized": acc.get("normalized"),
            "count": acc.get("count"),
            "type": acc.get("type"),
            "min": acc.get("min"),
            "max": acc.get("max"),
            "sparse": acc.get("sparse"),
            "extensions": acc.get("extensions"),
        })
    return rows


def primitive_summary(gltf: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for mesh_index, mesh in enumerate(gltf.get("meshes") or []):
        for primitive_index, primitive in enumerate(mesh.get("primitives") or []):
            rows.append({
                "meshIndex": mesh_index,
                "meshName": mesh.get("name"),
                "primitiveIndex": primitive_index,
                "attributes": primitive.get("attributes"),
                "indices": primitive.get("indices"),
                "mode": primitive.get("mode"),
                "material": primitive.get("material"),
                "extensions": primitive.get("extensions"),
                "extras": primitive.get("extras"),
            })
    return rows


def summarize_gltf(gltf: dict[str, Any], binary: bytes, header: dict[str, Any]) -> dict[str, Any]:
    return {
        "header": header,
        "asset": gltf.get("asset"),
        "scene": gltf.get("scene"),
        "scenes": gltf.get("scenes"),
        "extensionsUsed": gltf.get("extensionsUsed"),
        "extensionsRequired": gltf.get("extensionsRequired"),
        "extensions": gltf.get("extensions"),
        "extras": gltf.get("extras"),
        "nodes": gltf.get("nodes"),
        "meshes": primitive_summary(gltf),
        "accessors": accessor_summary(gltf),
        "bufferViews": gltf.get("bufferViews"),
        "buffers": gltf.get("buffers"),
        "materials": gltf.get("materials"),
        "textures": gltf.get("textures"),
        "images": gltf.get("images"),
        "samplers": gltf.get("samplers"),
        "binaryBytes": len(binary),
        "binarySha256": hashlib.sha256(binary).hexdigest(),
    }


def fetch(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=(20, 180))
    response.raise_for_status()
    return response.content


def main() -> int:
    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "ECOSCAPE-PLATEAU-CONTENT-INSPECT/1.0"})

    b3dm_raw = fetch(session, B3DM_URL)
    glb_raw = fetch(session, GLB_URL)
    (output / "sample_yokohama_nishi_data0.b3dm").write_bytes(b3dm_raw)
    (output / "sample_taito_39517_Building.glb").write_bytes(glb_raw)

    ft, bt, embedded_glb, b3dm_header = decode_b3dm(b3dm_raw)
    b3dm_gltf, b3dm_binary, b3dm_glb_header = read_json_chunk(embedded_glb)
    taito_gltf, taito_binary, taito_header = read_json_chunk(glb_raw)

    b3dm_report = {
        "url": B3DM_URL,
        "sha256": hashlib.sha256(b3dm_raw).hexdigest(),
        "bytes": len(b3dm_raw),
        "b3dmHeader": b3dm_header,
        "featureTable": ft,
        "batchTableKeys": list(bt.keys()),
        "batchTable": bt,
        "gltf": summarize_gltf(b3dm_gltf, b3dm_binary, b3dm_glb_header),
    }
    taito_report = {
        "url": GLB_URL,
        "sha256": hashlib.sha256(glb_raw).hexdigest(),
        "bytes": len(glb_raw),
        "gltf": summarize_gltf(taito_gltf, taito_binary, taito_header),
    }
    combined = {
        "b3dm": b3dm_report,
        "taitoGlb": taito_report,
        "qaPass": b3dm_raw[:4] == b"b3dm" and glb_raw[:4] == b"glTF",
        "scoringEffect": "none",
    }
    (output / "PLATEAU_CONTENT_FORMAT_REPORT.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    names = [
        "sample_yokohama_nishi_data0.b3dm",
        "sample_taito_39517_Building.glb",
        "PLATEAU_CONTENT_FORMAT_REPORT.json",
    ]
    (output / "SHA256SUMS.txt").write_text(
        "\n".join(
            f"{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}" for name in names
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "b3dmBytes": len(b3dm_raw),
        "b3dmBatchLength": ft.get("BATCH_LENGTH"),
        "b3dmExtensions": b3dm_gltf.get("extensionsUsed"),
        "taitoBytes": len(glb_raw),
        "taitoExtensions": taito_gltf.get("extensionsUsed"),
        "taitoTopExtensions": list((taito_gltf.get("extensions") or {}).keys()),
        "taitoPrimitiveExtensions": sorted({
            key
            for mesh in taito_gltf.get("meshes") or []
            for primitive in mesh.get("primitives") or []
            for key in (primitive.get("extensions") or {}).keys()
        }),
        "qaPass": combined["qaPass"],
    }, ensure_ascii=False, indent=2))
    if not combined["qaPass"]:
        raise SystemExit("PLATEAU content format inspection failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
