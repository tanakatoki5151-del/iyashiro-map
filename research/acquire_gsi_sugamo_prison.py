#!/usr/bin/env python3
"""Temporary research-branch entrypoint for 1961 Oyama/Nishihara imagery."""
import asyncio
import acquire_gsi_oyama_postmove as study
study.YEAR_FROM = 1961
study.YEAR_TO = 1961
study.PLANNERS = ["国土地理院"]
if __name__ == "__main__":
    asyncio.run(study.main())
