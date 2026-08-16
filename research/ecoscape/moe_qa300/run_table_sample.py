#!/usr/bin/env python3
"""Compatibility wrapper for the compact Sentinel aggregate table."""
from __future__ import annotations

from typing import Any

import run_moe_qa300 as app


def decode_rows(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, dict):
        columns = value.get("columns")
        rows = value.get("rows")
        if (
            isinstance(columns, list)
            and isinstance(rows, list)
            and len(rows) == 300
            and all(isinstance(row, list) and len(row) == len(columns) for row in rows)
        ):
            decoded = [dict(zip(columns, row, strict=True)) for row in rows]
            if all("cellId" in row and "sampleOrder" in row for row in decoded):
                return decoded
        for child in value.values():
            found = decode_rows(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        if len(value) == 300 and all(isinstance(row, dict) and "cellId" in row for row in value):
            return value
        for child in value:
            found = decode_rows(child)
            if found is not None:
                return found
    return None


app.find_sample_rows = decode_rows
raise SystemExit(app.main())
