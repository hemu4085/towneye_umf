# [FILE PATH]: scripts/benchmark_brief_latency.py
# Performance probe — answers "if someone asks for a random brief right now,
# how long do they wait?" against the current Arlington Gold lake.
# Date: 2026-05-07
"""
End-to-end latency benchmark for the Tier 4 BuildabilityBriefGenerator
against the Arlington-MA Gold lake as it exists today (no further
ingestion).

What gets measured
------------------
Two interaction modes are timed because they answer different
questions:

  1. **Cold start** — a fresh process that imports modules, builds the
     generator, resolves one parcel, and renders the HTML.  Models the
     latency a user sees when they click "Generate Brief" the first
     time after the app boots.

  2. **Warm path** — the second-and-subsequent parcels in the same
     process.  The OverlayResolver caches parquet frames in-memory,
     so the dominant cost collapses to the per-parcel spatial join
     and template render.

Inside each mode we also break the cost down by phase:

  * Resolver construction (one-time per process).
  * collect_data() — parcel lookup + 6 parquet loads + spatial joins.
  * render_html() — Jinja2 + ~13 KB of HTML.

Sample size: 25 random parcels (via a fixed seed for reproducibility).

Run:
    .venv/bin/python scripts/benchmark_brief_latency.py
"""

from __future__ import annotations

import statistics
import sys
import time
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

# Phase A: process startup — these imports get charged to the cold start.
_t_import_start = time.perf_counter()
from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator  # noqa: E402
_t_import_end = time.perf_counter()
import_ms = (_t_import_end - _t_import_start) * 1000


SAMPLE_SIZE = 25


def _ms(start: float, end: float) -> float:
    return (end - start) * 1000.0


def main() -> int:
    print(f"\n{'=' * 78}")
    print("  Buildability Brief — Cold-Start + Warm-Path Latency Benchmark")
    print(f"{'=' * 78}")
    print(f"  Module import (one-time)           : {import_ms:>7.1f} ms")

    # Pick a random sample of parcels.
    parcels = pd.read_parquet("data/gold/arlington-ma/parcel.parquet")
    sample = parcels.sample(n=SAMPLE_SIZE, random_state=42)["parcel_id"].astype(str).tolist()

    # ---------- Cold start ----------
    t0 = time.perf_counter()
    gen = BuildabilityBriefGenerator(town_slug="arlington-ma")
    t1 = time.perf_counter()
    print(f"  Generator construction             : {_ms(t0, t1):>7.1f} ms")

    cold_pid = sample[0]
    t2 = time.perf_counter()
    cold_data = gen.collect_data(BriefInputs(
        town_slug="arlington-ma", parcel_id=cold_pid,
        prepared_for="Bench", prepared_on=date(2026, 5, 7),
    ))
    t3 = time.perf_counter()
    cold_html = gen.render_html(cold_data)
    t4 = time.perf_counter()

    cold_collect_ms = _ms(t2, t3)
    cold_render_ms = _ms(t3, t4)
    cold_total_ms = import_ms + _ms(t0, t4)

    print()
    print(f"  --- Cold start (parcel #1, {cold_pid}) ---")
    print(f"    collect_data (loads 6 parquets + spatial joins): {cold_collect_ms:>7.1f} ms")
    print(f"    render_html  (Jinja2 -> {len(cold_html):>5,} bytes)        : {cold_render_ms:>7.1f} ms")
    print(f"    end-to-end (import + construct + collect + render): {cold_total_ms:>7.1f} ms")

    # ---------- Warm path ----------
    warm_collect: list[float] = []
    warm_render: list[float] = []
    warm_total: list[float] = []

    for pid in sample[1:]:
        t_a = time.perf_counter()
        data = gen.collect_data(BriefInputs(
            town_slug="arlington-ma", parcel_id=pid,
            prepared_for="Bench", prepared_on=date(2026, 5, 7),
        ))
        t_b = time.perf_counter()
        _ = gen.render_html(data)
        t_c = time.perf_counter()
        warm_collect.append(_ms(t_a, t_b))
        warm_render.append(_ms(t_b, t_c))
        warm_total.append(_ms(t_a, t_c))

    def _stats(name: str, vals: list[float]) -> None:
        vals_sorted = sorted(vals)
        median = statistics.median(vals)
        mean   = statistics.mean(vals)
        p95    = vals_sorted[max(0, int(0.95 * len(vals)) - 1)]
        print(
            f"    {name:<10}  n={len(vals):>2}  "
            f"min={min(vals):>6.1f}  median={median:>6.1f}  "
            f"mean={mean:>6.1f}  p95={p95:>6.1f}  max={max(vals):>6.1f}  ms"
        )

    print()
    print(f"  --- Warm path (parcels #2-{SAMPLE_SIZE}, parquets cached) ---")
    _stats("collect", warm_collect)
    _stats("render",  warm_render)
    _stats("total",   warm_total)

    # ---------- Headline numbers ----------
    print()
    print("  --- Headline ---")
    print(f"    Random user, first brief of the session : {cold_total_ms:>7.0f} ms"
          f"  ({cold_total_ms / 1000:.1f} s)")
    print(f"    Same user, next brief in same session   : {statistics.median(warm_total):>7.0f} ms"
          f"  ({statistics.median(warm_total) / 1000:.2f} s, median)")
    print(f"{'=' * 78}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
