# [FILE PATH]: scripts/verify_29_walnut_tier3.py
# Patch #204
# Execution Mode: Tier 3 — End-to-End Resolver Smoke Test
# Date: 2026-05-07
"""
Tier 3 verification — call the unified ``OverlayResolver`` on
29 Walnut St and dump the full ``ParcelOverlayStack`` to stdout.

Golden expectation (Phases 2a-2d truth):
  • parcel resolves: parcel_id=128.0-0003-0012.0, address ends "WALNUT ST"
  • zoning_overlay   : R2 (base) + NMF (overlay)
  • macris           : 0 hits
  • local_historic   : 0 hits
  • environmental_overlay : 0 hits
  • noncompliance    : 0 hits

Run:
    .venv/bin/python scripts/verify_29_walnut_tier3.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.spatial import OverlayResolver  # noqa: E402

WALNUT_PARCEL_ID = "128.0-0003-0012.0"
TOWN = "arlington-ma"


def main() -> int:
    resolver = OverlayResolver(town_slug=TOWN)
    stack = resolver.resolve(parcel_id=WALNUT_PARCEL_ID)

    print(f"\n{'=' * 78}")
    print(f"  29 WALNUT ST — Tier 3 OverlayResolver Smoke Test")
    print(f"{'=' * 78}")
    print(f"  Town slug      : {stack.town_slug}")
    print(f"  Query kind     : {stack.query_kind}  (value={stack.query_value!r})")
    print(f"  Resolved at    : {stack.resolved_at.isoformat()}")
    if stack.parcel:
        p = stack.parcel
        print(
            f"  Parcel         : {p.parcel_id} | {p.address} | "
            f"{p.area_sqft:.0f} sqft | "
            f"perimeter={p.perimeter_ft:.0f} ft | "
            f"longest_edge={p.longest_edge_ft:.0f} ft"
        )
        print(f"  Centroid       : ({p.centroid_lat:.6f}, {p.centroid_lon:.6f})")

    def _dump(name: str, hits) -> None:
        print(f"\n  [{name}]  ({len(hits)} hit{'s' if len(hits) != 1 else ''})")
        for h in hits:
            line = (
                f"    - domain={h.domain:<22}  "
                f"match={h.match_type:<13}  "
                f"layer={h.layer!r}  code={h.code!r}  label={h.label!r}"
            )
            if h.distance_ft is not None:
                line += f"  distance_ft={h.distance_ft:.1f}"
            print(line)

    _dump("ZONING OVERLAY",        stack.zoning_overlay)
    _dump("MACRIS",                stack.macris)
    _dump("LOCAL HISTORIC",        stack.local_historic)
    _dump("ENVIRONMENTAL OVERLAY", stack.environmental_overlay)
    _dump("NONCOMPLIANCE",         stack.noncompliance)

    print(f"\n  ---")
    print(f"  Summary: {stack.summary_one_liner()}")
    print(f"{'=' * 78}\n")

    # Golden assertions (also covered by tests/test_spatial.py)
    zone_codes = sorted({h.code for h in stack.zoning_overlay if h.code})
    assert "R2" in zone_codes, f"FAIL: expected R2 in zoning, got {zone_codes}"
    assert "NMF" in zone_codes, f"FAIL: expected NMF overlay, got {zone_codes}"
    assert stack.macris == [], "FAIL: expected zero MACRIS hits"
    assert stack.local_historic == [], "FAIL: expected zero local-historic hits"
    assert stack.environmental_overlay == [], "FAIL: expected zero environmental hits"
    assert stack.noncompliance == [], "FAIL: expected zero noncompliance hits"

    print("  [OK] all golden assertions pass.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
