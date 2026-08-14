#!/usr/bin/env python3
"""Compatibility runner for Park Mansion isolated probe v2.

The reused SPHERE PLATEAU engine formats three developer physical-control
fields in README output. Park Mansion does not yet have an independent
published area control, so provide explicit UNKNOWN sentinel values solely to
satisfy reporting. They are not used for candidate selection in the wrapper.
"""
import probe_b46_park_mansion_crosssource_v1 as w

_original = w.pl.main

def _patched_plateau_main():
    c = w.pl.TARGET.setdefault("developerPhysicalControl", {})
    c.setdefault("buildingAreaM2", 1.0)
    c.setdefault("siteAreaM2", "UNKNOWN_NOT_USED")
    c.setdefault("totalFloorAreaM2", "UNKNOWN_NOT_USED")
    c.setdefault("sourcePage", "UNKNOWN_NOT_USED")
    c.setdefault("sourceImage", "UNKNOWN_NOT_USED")
    return _original()

w.pl.main = _patched_plateau_main
w.main()
