#!/usr/bin/env python3
"""V10 B46 A3 Duel Yato cross-source geometry probe v1.

Reuses the fail-closed A2 probe engine with an A3 target configuration.
No formal geometry promotion and no score/rank/automatic-exclusion change.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import probe_b46_a2_park_mansion_crosssource_v1 as engine

OUT = Path("out-b46-a3-duel-yato-crosssource-v1")
TARGET = {
    "propertyId": "BLDG-72776fe404db",
    "buildingName": "デュエル・ヤト",
    "address": "東京都目黒区東が丘1丁目2-9",
    "expectedStoreys": 2,
    "expectedStructure": "軽量鉄骨",
    "built": "1987-01",
    "osmCandidateWayId": 688689754,
    "representativeSensitiveDistanceM": 475.5,
    "thresholdM": 500.0,
}


def main():
    engine.OUT = OUT
    engine.TARGET = TARGET
    engine.OSM_FULL = f"https://api.openstreetmap.org/api/0.6/way/{TARGET['osmCandidateWayId']}/full"
    engine.main()

    p = OUT / "SUMMARY.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    s["schemaVersion"] = "v10-b46-a3-duel-yato-crosssource-v1"
    s["policy"]["nextGate"] = "identify one current building only if exact-address + 2F identity and independent PLATEAU/GSI/OSM shape evidence are coherent; then calculate fixed-sensitive-geometry 500m threshold"
    p.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = OUT / "README.md"
    txt = readme.read_text(encoding="utf-8")
    txt = txt.replace("V10 B46 A2 Park Mansion cross-source probe v1", "V10 B46 A3 Duel Yato cross-source probe v1")
    readme.write_text(txt, encoding="utf-8")

    sums = []
    for f in sorted(OUT.iterdir()):
        if f.name == "SHA256SUMS.txt" or not f.is_file():
            continue
        sums.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
