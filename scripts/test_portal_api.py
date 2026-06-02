#!/usr/bin/env python3
"""Smoke test portal parcel + buildability endpoints."""
import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from backend.services.buildability import generate_buildability_html
from backend.utils.parcel_lookup import resolve_address


async def main():
    parcel = await resolve_address("29 Walnut St, Arlington MA")
    print("parcel_id:", parcel["parcel_id"])
    html = generate_buildability_html(
        parcel["town_slug"],
        parcel["parcel_id"],
        prepared_for="Portal Test",
    )
    print("html bytes:", len(html))


if __name__ == "__main__":
    asyncio.run(main())
