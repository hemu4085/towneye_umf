# [FILE PATH]: scripts/benchmark_tier5_final.py
# Tier 5 final benchmark — measure brief latency for both towns post-Path-A.
# Date: 2026-05-07
"""
After Path A (L3 -> property.parquet promotion) and the two cleanups
(zoning_overlay max_features bump, local_historic per-source layer
filtering), this benchmark re-measures end-to-end brief generation
latency for Arlington and Lexington and reports:

  * cold-start time (first brief in a fresh process)
  * warm-path latency (subsequent briefs, parquets cached)
  * percentage of randomly sampled briefs that ship a fully populated
    assessor section (the ~"is the brief useful" metric)

The numbers are what we'd quote when answering "if a user randomly asks
for a brief right now in town X, how long do they wait and how much
real data do they get?".
"""

from __future__ import annotations

import statistics
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

t_imp_0 = time.perf_counter()
from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator  # noqa: E402
t_imp_1 = time.perf_counter()
import_ms = (t_imp_1 - t_imp_0) * 1000.0


def _ms(a: float, b: float) -> float:
    return (b - a) * 1000.0


def bench_town(slug: str, n: int = 25) -> Dict[str, float]:
    parcels = pd.read_parquet(f"data/gold/{slug}/parcel.parquet")
    sample = parcels.sample(n=n, random_state=42)["parcel_id"].astype(str).tolist()

    t0 = time.perf_counter()
    gen = BuildabilityBriefGenerator(town_slug=slug)
    t1 = time.perf_counter()

    cold_pid = sample[0]
    cold_data = gen.collect_data(BriefInputs(
        town_slug=slug, parcel_id=cold_pid,
        prepared_for="Tier-5 bench", prepared_on=date(2026, 5, 7),
    ))
    t2 = time.perf_counter()
    cold_html = gen.render_html(cold_data)
    t3 = time.perf_counter()

    warm_collect: List[float] = []
    warm_render:  List[float] = []
    full_count = 0

    for pid in sample[1:]:
        ta = time.perf_counter()
        data = gen.collect_data(BriefInputs(
            town_slug=slug, parcel_id=pid,
            prepared_for="Tier-5 bench", prepared_on=date(2026, 5, 7),
        ))
        tb = time.perf_counter()
        html = gen.render_html(data)
        tc = time.perf_counter()
        warm_collect.append(_ms(ta, tb))
        warm_render.append(_ms(tb, tc))
        pi = data.property_info
        if pi and pi.owner_name and pi.year_built and pi.assessed_value and pi.lot_size_sqft:
            full_count += 1

    return {
        "cold_total_ms":  _ms(t0, t3),
        "cold_collect":   _ms(t1, t2),
        "cold_render":    _ms(t2, t3),
        "warm_collect_p50": statistics.median(warm_collect),
        "warm_collect_p95": sorted(warm_collect)[int(0.95 * len(warm_collect)) - 1],
        "warm_render_p50":  statistics.median(warm_render),
        "warm_total_p50":   statistics.median(warm_collect) + statistics.median(warm_render),
        "n_full_briefs":    full_count + (1 if cold_data.property_info and cold_data.property_info.owner_name else 0),
        "n_total":          n,
        "cold_html_kb":     len(cold_html) / 1024.0,
    }


def main() -> int:
    print("=" * 78)
    print("  Tier 5 final benchmark — both towns post-Path-A + cleanups")
    print("=" * 78)
    print(f"  module import (one-time): {import_ms:>7.1f} ms\n")

    out: Dict[str, Dict[str, float]] = {}
    for slug in ["arlington-ma", "lexington-ma"]:
        print(f"  --- {slug} (n=25 random parcels) ---")
        b = bench_town(slug, n=25)
        out[slug] = b
        print(f"    cold start (1st brief)    : {b['cold_total_ms']:>7.1f} ms"
              f"   (collect={b['cold_collect']:.1f} + render={b['cold_render']:.1f}, "
              f"{b['cold_html_kb']:.1f} KB)")
        print(f"    warm collect  (p50 / p95) : {b['warm_collect_p50']:>7.1f} ms"
              f"  /  {b['warm_collect_p95']:.1f} ms")
        print(f"    warm render   (p50)       : {b['warm_render_p50']:>7.1f} ms")
        print(f"    warm total    (p50)       : {b['warm_total_p50']:>7.1f} ms")
        print(f"    fully populated briefs    : {b['n_full_briefs']}/{b['n_total']}"
              f"  ({100 * b['n_full_briefs'] / b['n_total']:.0f}%)")
        print()

    print("=" * 78)
    print("  Side-by-side")
    print("=" * 78)
    print(f"  {'metric':<32}  {'Arlington':>14}  {'Lexington':>14}")
    print(f"  {'-'*32}  {'-'*14:>14}  {'-'*14:>14}")
    for label, key, suffix in [
        ("cold-start total",       "cold_total_ms",   "ms"),
        ("warm collect p50",       "warm_collect_p50","ms"),
        ("warm render  p50",       "warm_render_p50", "ms"),
        ("warm total   p50",       "warm_total_p50",  "ms"),
    ]:
        a = out["arlington-ma"][key]
        l = out["lexington-ma"][key]
        print(f"  {label:<32}  {a:>11.1f} {suffix}  {l:>11.1f} {suffix}")

    afull = f"{out['arlington-ma']['n_full_briefs']}/{out['arlington-ma']['n_total']}"
    lfull = f"{out['lexington-ma']['n_full_briefs']}/{out['lexington-ma']['n_total']}"
    print(f"  {'fully populated':<32}  {afull:>14}  {lfull:>14}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
