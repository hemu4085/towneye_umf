# [FILE PATH]: scripts/verify_path_a_briefs_v2.py
# Tier 5 / Path A verification (corrected) — render real HTML briefs and
# check that the rendered output carries the assessor signal.
# Date: 2026-05-07
"""
Path-A verification, take 2.  v1 looked for ``PropertyInfo.address``,
which doesn't exist on the model — address comes from ParcelInfo.  This
version renders the actual HTML brief and greps for the same strings a
human would expect to see (owner name, year built, assessed value).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator


def _check_one(slug: str, parcel_id: str, gen: BuildabilityBriefGenerator) -> dict:
    inputs = BriefInputs(
        town_slug=slug,
        parcel_id=parcel_id,
        prepared_for="Path A v2",
        prepared_on=date(2026, 5, 7),
    )
    data = gen.collect_data(inputs)
    html = gen.render_html(data)
    pi = data.property_info
    parcel = data.parcel
    owner = (pi.owner_name if pi else None) or ""
    has_owner    = bool(owner) and owner.upper() in html.upper()
    has_year     = bool(pi and pi.year_built) and str(pi.year_built) in html
    has_value    = bool(pi and pi.assessed_value) and (
        f"{int(pi.assessed_value):,}" in html or f"{pi.assessed_value:,.0f}" in html
    )
    has_lotsize  = bool(pi and pi.lot_size_sqft) and (
        f"{int(pi.lot_size_sqft):,}" in html or f"{pi.lot_size_sqft:,.0f}" in html
    )
    has_address  = bool(parcel.address) and parcel.address.upper() in html.upper()
    return {
        "parcel_id":   parcel_id,
        "address":     parcel.address,
        "html_kb":     len(html) / 1024.0,
        "owner_ok":    has_owner,
        "year_ok":     has_year,
        "value_ok":    has_value,
        "lotsize_ok":  has_lotsize,
        "address_ok":  has_address,
        "owner":       owner,
        "value":       pi.assessed_value if pi else None,
    }


def main() -> int:
    print("=" * 78)
    print("  Path A verification v2 — actual HTML render checks")
    print("=" * 78)

    overall_ok = 0
    overall_total = 0
    for slug in ["arlington-ma", "lexington-ma"]:
        parcels = pd.read_parquet(f"data/gold/{slug}/parcel.parquet")
        sample = parcels.sample(n=5, random_state=42)["parcel_id"].astype(str).tolist()
        gen = BuildabilityBriefGenerator(town_slug=slug)
        print(f"\n--- {slug}  (5 random parcels rendered to HTML) ---")
        for pid in sample:
            r = _check_one(slug, pid, gen)
            checks = [r["address_ok"], r["owner_ok"], r["year_ok"], r["value_ok"], r["lotsize_ok"]]
            score = sum(checks)
            overall_ok += score
            overall_total += len(checks)
            mark = "FULL " if score == 5 else (" SOME " if score >= 3 else "STUB ")
            print(
                f"  [{mark}] {pid:<22}  {(r['address'] or '?')[:30]:<30}  "
                f"score={score}/5  "
                f"addr={'y' if r['address_ok'] else '-'}  "
                f"own={'y' if r['owner_ok'] else '-'}  "
                f"yr={'y' if r['year_ok'] else '-'}  "
                f"val={'y' if r['value_ok'] else '-'}  "
                f"lot={'y' if r['lotsize_ok'] else '-'}  "
                f"({r['html_kb']:.1f} KB)"
            )

    print(f"\n{'=' * 78}")
    print(f"  Overall: {overall_ok}/{overall_total} brief sections "
          f"({100 * overall_ok / overall_total:.0f}% populated)")
    print(f"{'=' * 78}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
