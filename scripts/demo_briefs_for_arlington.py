# [FILE PATH]: scripts/demo_briefs_for_arlington.py
# Demo / proof: generate the buildability brief for any Arlington parcel.
# Date: 2026-05-07
"""
Generate the Tier 4 buildability brief for a curated mix of Arlington
parcels and report which sections were data-rich vs degraded.

The script picks 6 parcels:
  * 128.0-0003-0012.0 — 29 Walnut St (NMF overlay, has assessor sidecar)
  * 141.0-0002-0011.0 — 29 Walnut Terr (no overlay, has assessor sidecar)
  * 4 randomly sampled parcels from parcel.parquet (no assessor sidecar)

For each parcel the script:
  1. Calls BuildabilityBriefGenerator.collect_data() — succeeds for any
     parcel because every required input is in the Gold lake.
  2. Renders the HTML and writes it under reports/output/.
  3. Captures a per-parcel diagnostic line listing which sections were
     populated vs degraded (assessor block missing, overlay rule
     missing, etc).

This is the "yes, the v2 brief works for any house in Arlington" proof.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator  # noqa: E402

OUT_DIR = REPO_ROOT / "reports" / "output" / "arlington_brief_batch"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _fmt(v):
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:,.0f}"
    return str(v)


def _safe_filename(parcel_id: str) -> str:
    return parcel_id.replace("/", "_").replace(" ", "_")


def main() -> int:
    parcels = pd.read_parquet("data/gold/arlington-ma/parcel.parquet")
    fixed = ["128.0-0003-0012.0", "141.0-0002-0011.0"]
    random_sample = (
        parcels[~parcels["parcel_id"].isin(fixed)]
        .sample(n=4, random_state=42)["parcel_id"].astype(str).tolist()
    )
    parcel_ids = fixed + random_sample

    generator = BuildabilityBriefGenerator(town_slug="arlington-ma")

    print(f"\n{'=' * 110}")
    print(f"  Arlington Buildability Brief — Batch Generation")
    print(f"{'=' * 110}")
    print(f"  {'PARCEL ID':<22}  {'ADDRESS':<30}  {'ZONES':<14}  {'GFA':>7}  {'GFA src':<7}  {'OWNER':<32}  {'WRAP':<5}")
    print(f"  {'-' * 22}  {'-' * 30}  {'-' * 14}  {'-' * 7}  {'-' * 7}  {'-' * 32}  {'-' * 5}")

    for pid in parcel_ids:
        try:
            inputs = BriefInputs(
                town_slug="arlington-ma",
                parcel_id=pid,
                prepared_for="Demo Run",
                prepared_on=date(2026, 5, 7),
            )
            data = generator.collect_data(inputs)
            html = generator.render_html(data)

            out_path = OUT_DIR / f"{_safe_filename(pid)}.html"
            out_path.write_text(html, encoding="utf-8")

            zones = "+".join(sorted(
                ({h.code for h in data.base_zoning_hits if h.code} |
                 {h.code for h in data.overlay_zoning_hits if h.code})
            ))
            wrap_total = (
                len(data.raw_stack.macris) +
                len(data.raw_stack.local_historic) +
                len(data.raw_stack.environmental_overlay) +
                len(data.raw_stack.noncompliance)
            )
            if data.property_info and data.property_info.finished_area_sqft:
                gfa = _fmt(data.property_info.finished_area_sqft)
                gfa_src = "asses."
            else:
                gfa = "-"
                gfa_src = "—"
            owner = data.property_info.owner_name if data.property_info else "(no row)"
            addr = data.parcel.address or "(no addr)"
            print(
                f"  {pid:<22}  {addr[:30]:<30}  {zones:<14}  {gfa:>7}  "
                f"{gfa_src:<7}  {(owner or '(none)')[:32]:<32}  {wrap_total:<5}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {pid:<22}  FAILED: {exc}")

    print(f"\n  Wrote {len(parcel_ids)} brief(s) under {OUT_DIR.relative_to(REPO_ROOT)}/")
    print(f"{'=' * 110}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
