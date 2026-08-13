#!/usr/bin/env python3
"""Temporary research-branch entrypoint for the Oyama/Nishihara post-1949 acquisition.

The protected workflow still calls this historical Sugamo filename. The actual
study implementation is isolated in acquire_gsi_oyama_postmove.py. Restore the
Sugamo implementation after this acquisition artifact is fixed in Drive.
"""
import asyncio
from acquire_gsi_oyama_postmove import main

if __name__ == "__main__":
    asyncio.run(main())
