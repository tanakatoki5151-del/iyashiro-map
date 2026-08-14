#!/usr/bin/env python3
"""V10 B41 physical-plausibility audit for high-value building footprint candidates.

Purpose
-------
The existing candidate acquisition is deliberately fail-closed and sometimes selects the
nearest anonymous OSM building when no footprint contains the representative point.
This audit adds a one-way rejection gate: when published unit count, minimum private
unit area, and storey count imply a mathematical minimum floorplate larger than a
candidate footprint, that candidate cannot be the *complete* building footprint.

This script never promotes a candidate. It only rejects impossible complete-footprint
interpretations and narrows the next identity/shape QA queue.

The candidate areas below are frozen from GitHub Actions artifact 9232056324
(v10-tier1-property-footprint-candidates), digest
sha256:6b0e78b0ba04d2bd9d2e675ec5f8d20c16a8f98ef1a969f9aaabb0f6b0747f4c.
Areas were calculated from the frozen OSM geometries in that artifact.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("out-b41-physical-plausibility-v1")
SOURCE_ARTIFACT = {
    "runId": 31834779318,
    "artifactId": 9232056324,
    "name": "v10-tier1-property-footprint-candidates",
    "digest": "sha256:6b0e78b0ba04d2bd9d2e675ec5f8d20c16a8f98ef1a969f9aaabb0f6b0747f4c",
}
# Area computation/projection error is far smaller than this; 2% is intentionally generous.
AREA_TOLERANCE = 0.02

TARGETS = [
    {
        "priority": 1,
        "propertyId": "BLDG-6583382c8322",
        "buildingName": "レ・サン・サーンス",
        "address": "東京都目黒区目黒本町5丁目29-12",
        "facts": {"storeys": 3, "units": 29, "minimumPrivateUnitAreaM2": 25.28},
        "factSources": [
            "https://www.creavision.co.jp/building/911/",
            "https://www.mitsui-chintai.co.jp/rf/tatemono/69527",
        ],
        "selected": {"osmRef": "way/694173687", "distanceM": 4.791, "areaM2": 23.8},
        "candidates": [
            {"osmRef": "way/694173687", "distanceM": 4.791, "areaM2": 23.8},
            {"osmRef": "way/694173665", "distanceM": 11.553, "areaM2": 74.5},
            {"osmRef": "way/694173696", "distanceM": 11.982, "areaM2": 188.3},
            {"osmRef": "way/694173675", "distanceM": 17.726, "areaM2": 164.2},
            {"osmRef": "way/694173655", "distanceM": 19.765, "areaM2": 170.9},
            {"osmRef": "way/694173729", "distanceM": 40.389, "areaM2": 434.8},
            {"osmRef": "way/693031402", "distanceM": 42.557, "areaM2": 383.0},
            {"osmRef": "way/694173728", "distanceM": 44.264, "areaM2": 323.0},
        ],
    },
    {
        "priority": 2,
        "propertyId": "BLDG-edf6c2448f9e",
        "buildingName": "エスティメゾン代沢",
        "address": "東京都世田谷区代沢2丁目39-13",
        "facts": {"storeys": 3, "units": 71, "minimumPrivateUnitAreaM2": 25.25},
        "factSources": [
            "https://www.esty-maison.com/daizawa/outline.html",
            "https://www.homes.co.jp/archive/b-13691515/",
        ],
        "selected": {"osmRef": "way/133632890", "distanceM": 13.104, "areaM2": 205.1},
        "candidates": [
            {"osmRef": "way/133632890", "distanceM": 13.104, "areaM2": 205.1},
            {"osmRef": "way/635654530", "distanceM": 21.894, "areaM2": 102.1},
            {"osmRef": "way/133633394", "distanceM": 25.602, "areaM2": 1149.4},
            {"osmRef": "way/133632569", "distanceM": 41.462, "areaM2": 314.3},
            {"osmRef": "way/133632889", "distanceM": 50.953, "areaM2": 522.0},
            {"osmRef": "way/133632885", "distanceM": 55.109, "areaM2": 474.0, "osmName": "世田谷区池之上青少年交流センター"},
        ],
    },
    {
        "priority": 3,
        "propertyId": "BLDG-4e6c9a14c783",
        "buildingName": "レオパレス駒場東大前",
        "address": "東京都目黒区駒場4丁目3-21",
        "facts": {"storeys": 2, "units": 14, "minimumPrivateUnitAreaM2": 19.87},
        "factSources": ["https://www.leopalace21.com/"],
        "selected": {"osmRef": "way/133340630", "distanceM": 16.570, "areaM2": 191.0},
        "candidates": [
            {"osmRef": "way/133340630", "distanceM": 16.570, "areaM2": 191.0},
            {"osmRef": "way/133340621", "distanceM": 18.811, "areaM2": 399.0, "osmName": "駒場社宅"},
            {"osmRef": "way/133340633", "distanceM": 28.609, "areaM2": 188.3},
            {"osmRef": "way/1344685319", "distanceM": 36.671, "areaM2": 167.6},
            {"osmRef": "way/133340623", "distanceM": 40.933, "areaM2": 142.9},
            {"osmRef": "way/133340601", "distanceM": 42.297, "areaM2": 392.3, "osmName": "駒場社宅"},
            {"osmRef": "way/133340590", "distanceM": 48.313, "areaM2": 260.3, "osmName": "Cortile Komaba"},
            {"osmRef": "way/133340629", "distanceM": 59.440, "areaM2": 235.3},
        ],
    },
    {
        "priority": 4,
        "propertyId": "BLDG-cef1a041caab",
        "buildingName": "栄荘",
        "address": "東京都目黒区目黒本町5丁目26-23",
        "facts": {"storeys": 2, "units": None, "minimumPrivateUnitAreaM2": None},
        "factSources": ["https://www.homes.co.jp/archive/b-34416499/"],
        "selected": {"osmRef": "way/694173907", "distanceM": 6.172, "areaM2": 59.2},
        "candidates": [],
        "preExistingGuard": "same_address_temporal_identity_conflict_blocked",
    },
    {
        "priority": 5,
        "propertyId": "BLDG-c404c81c08a5",
        "buildingName": "プリュメゾン駒沢",
        "address": "東京都目黒区東が丘1丁目16-26",
        "facts": {"storeys": 4, "units": 26, "minimumPrivateUnitAreaM2": 18.46},
        "factSources": [
            "https://www.homes.co.jp/archive/b-34401606/",
            "https://www.royal-community.co.jp/build-6812226/",
        ],
        "selected": {"osmRef": "way/1207907638", "distanceM": 9.078, "areaM2": 29.1},
        "candidates": [
            {"osmRef": "way/1207907638", "distanceM": 9.078, "areaM2": 29.1},
            {"osmRef": "way/1207907637", "distanceM": 14.564, "areaM2": 36.1},
            {"osmRef": "way/689285630", "distanceM": 15.270, "areaM2": 112.4},
            {"osmRef": "way/688689707", "distanceM": 25.263, "areaM2": 126.1},
            {"osmRef": "way/689285649", "distanceM": 38.849, "areaM2": 126.6},
            {"osmRef": "way/688689714", "distanceM": 41.371, "areaM2": 141.8},
            {"osmRef": "way/694315401", "distanceM": 41.533, "areaM2": 1865.9},
            {"osmRef": "way/689285646", "distanceM": 44.714, "areaM2": 1209.3},
            {"osmRef": "way/688689672", "distanceM": 49.099, "areaM2": 136.7},
        ],
    },
    {
        "priority": 6,
        "propertyId": "BLDG-72776fe404db",
        "buildingName": "デュエル・ヤト",
        "address": "東京都目黒区東が丘1丁目2-9",
        "facts": {"storeys": 2, "units": None, "minimumPrivateUnitAreaM2": 25.28},
        "factSources": ["https://www.homes.co.jp/archive/b-34401164/"],
        "selected": {"osmRef": "way/688689754", "distanceM": 13.664, "areaM2": 98.9},
        "candidates": [],
    },
]


def minimum_complete_footprint(facts: dict) -> float | None:
    units = facts.get("units")
    storeys = facts.get("storeys")
    min_area = facts.get("minimumPrivateUnitAreaM2")
    if not units or not storeys or not min_area:
        return None
    # Total gross floor area must be >= total private unit area.
    # Gross floor area cannot exceed footprint × number of storeys for one complete building.
    return float(units) * float(min_area) / float(storeys)


def candidate_status(candidate: dict, lower_bound: float | None) -> str:
    if candidate.get("osmName"):
        return "named_non_target_excluded"
    if lower_bound is None:
        return "physical_gate_unavailable"
    if candidate["areaM2"] < lower_bound * (1.0 - AREA_TOLERANCE):
        return "too_small_for_complete_footprint"
    return "physically_plausible_only_identity_unresolved"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    rejected_selected = 0
    selected_physically_plausible = 0
    unavailable = 0

    for target in TARGETS:
        lower_bound = minimum_complete_footprint(target["facts"])
        selected = dict(target["selected"])
        selected_status = candidate_status(selected, lower_bound)
        if selected_status == "too_small_for_complete_footprint":
            rejected_selected += 1
        elif selected_status == "physically_plausible_only_identity_unresolved":
            selected_physically_plausible += 1
        else:
            unavailable += 1

        audited_candidates = []
        for candidate in target.get("candidates", []):
            c = dict(candidate)
            c["physicalStatus"] = candidate_status(c, lower_bound)
            if lower_bound:
                c["areaToLowerBoundRatio"] = round(c["areaM2"] / lower_bound, 4)
            audited_candidates.append(c)

        survivors = [
            c for c in audited_candidates
            if c["physicalStatus"] == "physically_plausible_only_identity_unresolved"
        ]
        survivors.sort(key=lambda c: (c["distanceM"], c["areaM2"], c["osmRef"]))

        if lower_bound is None:
            decision = "physical_gate_unavailable_keep_existing_identity_guard"
            next_gate = "obtain unit count or independent roof/exterior/address-to-footprint identity evidence"
        elif selected_status == "too_small_for_complete_footprint":
            decision = "selected_candidate_rejected_as_complete_footprint"
            next_gate = "shape/location QA only among physically plausible survivors; no nearest-candidate fallback"
        else:
            decision = "selected_candidate_physically_possible_but_not_identity_verified"
            next_gate = "independent shape/location QA required before any formal promotion"

        results.append({
            "priority": target["priority"],
            "propertyId": target["propertyId"],
            "buildingName": target["buildingName"],
            "address": target["address"],
            "facts": target["facts"],
            "factSources": target["factSources"],
            "minimumCompleteFootprintM2": round(lower_bound, 3) if lower_bound else None,
            "selected": {
                **selected,
                "physicalStatus": selected_status,
                "areaToLowerBoundRatio": round(selected["areaM2"] / lower_bound, 4) if lower_bound else None,
            },
            "physicallyPlausibleSurvivors": survivors,
            "preExistingGuard": target.get("preExistingGuard"),
            "decision": decision,
            "formalPromotion": False,
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "nextGate": next_gate,
        })

    summary = {
        "schemaVersion": "v10-b41-physical-plausibility-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceArtifact": SOURCE_ARTIFACT,
        "method": {
            "formula": "minimum complete footprint = units × minimum private unit area / storeys",
            "interpretation": "one-way rejection gate for a single complete building footprint",
            "areaToleranceFraction": AREA_TOLERANCE,
            "multiBuildingOrOsmPartCaveat": True,
            "nearestCandidateFallbackAllowed": False,
        },
        "counts": {
            "targets": len(TARGETS),
            "selectedCandidatesRejectedAsCompleteFootprint": rejected_selected,
            "selectedCandidatesPhysicallyPossibleButIdentityUnverified": selected_physically_plausible,
            "physicalGateUnavailable": unavailable,
            "formalBuildingPolygonsPromoted": 0,
        },
        "policy": {
            "scoringEffect": "none",
            "rankingEffect": "none",
            "automaticExclusionEffect": "none",
            "verifiedGeometryAdded": 0,
        },
        "items": results,
    }

    summary_path = OUT / "SUMMARY.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# V10 B41 physical-plausibility audit v1",
        "",
        "This is a fail-closed rejection audit. It does **not** promote any building polygon.",
        "",
        f"Source candidate artifact: `{SOURCE_ARTIFACT['artifactId']}` / `{SOURCE_ARTIFACT['digest']}`",
        "",
        "## Result",
        "",
    ]
    for item in results:
        lb = item["minimumCompleteFootprintM2"]
        s = item["selected"]
        lines.append(
            f"- {item['buildingName']}: selected `{s['osmRef']}` area={s['areaM2']}m², "
            f"lower-bound={lb}m², status=`{s['physicalStatus']}`; decision=`{item['decision']}`"
        )
        if item["physicallyPlausibleSurvivors"]:
            refs = ", ".join(
                f"{c['osmRef']}({c['areaM2']}m²/{c['distanceM']}m)"
                for c in item["physicallyPlausibleSurvivors"]
            )
            lines.append(f"  - physical survivors only: {refs}")
    lines += [
        "",
        "## Policy",
        "",
        "- formal building polygon promotion: **0**",
        "- scoring/ranking/automatic-exclusion changes: **none**",
        "- named non-target OSM buildings are excluded from survivor candidates",
        "- a physically plausible footprint still requires independent identity/shape/location evidence",
    ]
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    sha_lines = []
    for path in sorted(OUT.iterdir()):
        if path.name == "SHA256SUMS.txt" or not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sha_lines.append(f"{digest}  {path.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
