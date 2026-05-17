# [FILE PATH]: scripts/verify_path_a_briefs.py
# Tier 5 / Path A verification — does any random parcel now ship a full brief?
# Date: 2026-05-07
"""
Pick a handful of random parcels in each town, generate the buildability
brief for each, and report whether the assessor section is populated.
The pre-Path-A baseline shipped fully populated briefs for ~2 of 12,644
Arlington parcels.  Post-Path-A this should be 28,449 of 28,449.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator


# Fields a "fully populated" assessor section requires.  These are the
# property.parquet columns the brief reads.
ESSENTIAL_FIELDS = ["address", "owner_name", "year_built", "assessed_value", "lot_size_sqft"]


def _check_brief_for(slug: str, parcel_id: str, gen: BuildabilityBriefGenerator) -> Dict[str, Any]:
    """Generate the brief and report which assessor fields ended up populated."""
    inputs = BriefInputs(
        town_slug=slug,
        parcel_id=parcel_id,
        prepared_for="Path A verify",
        prepared_on=date(2026, 5, 7),
    )
    data = gen.collect_data(inputs)
    pi = data.property_info
    populated = {f: getattr(pi, f, None) for f in ESSENTIAL_FIELDS if pi}
    populated_count = sum(1 for v in populated.values() if v not in (None, "", 0))
    return {
        "parcel_id":         parcel_id,
        "address":           getattr(pi, "address", None) if pi else None,
        "populated_count":   populated_count,
        "essential_total":   len(ESSENTIAL_FIELDS),
        "owner":             getattr(pi, "owner_name", None) if pi else None,
        "year_built":        getattr(pi, "year_built", None) if pi else None,
        "assessed_value":    getattr(pi, "assessed_value", None) if pi else None,
        "lot_size_sqft":     getattr(pi, "lot_size_sqft", None) if pi else None,
    }


def main() -> int:
    print("=" * 78)
    print("  Path A verification — random-parcel briefs")
    print("=" * 78)

    for slug in ["arlington-ma", "lexington-ma"]:
        parcels = pd.read_parquet(f"data/gold/{slug}/parcel.parquet")
        sample = parcels.sample(n=5, random_state=42)["parcel_id"].astype(str).tolist()
        gen = BuildabilityBriefGenerator(town_slug=slug)

        print(f"\n--- {slug}  (sample of 5 random parcels) ---")
        for pid in sample:
            r = _check_brief_for(slug, pid, gen)
            mark = "FULL " if r["populated_count"] == r["essential_total"] else "PART "
            print(
                f"  [{mark}] {pid:<22}  {r['address'][:32] if r['address'] else '(no address)':<32}"
                f"  {r['populated_count']}/{r['essential_total']} fields"
                f"  owner={(r['owner'] or '?')[:24]:<24}"
                f"  yr={r['year_built'] or '?':>4}"
                f"  val=${(r['assessed_value'] or 0):>10,}"
            )

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
