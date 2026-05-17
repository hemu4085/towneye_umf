# [FILE PATH]: scripts/_emit_path_a_snapshots.py
"""Emit four showcase briefs after the Path A backfill."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")

from reports.buildability_brief import BriefInputs, BuildabilityBriefGenerator

CASES = [
    ("arlington-ma", "128.0-0003-0012.0", "29_walnut_path_a.html"),
    ("arlington-ma", "071.0-0002-0016.0", "arlington_random_path_a.html"),
    ("lexington-ma", "11-16",             "lexington_16_benjamin_path_a.html"),
    ("lexington-ma", "20-187",            "lexington_random_path_a.html"),
]

out_dir = Path("reports/output")
for slug, pid, fname in CASES:
    gen = BuildabilityBriefGenerator(town_slug=slug)
    data = gen.collect_data(BriefInputs(
        town_slug=slug, parcel_id=pid,
        prepared_for="Path A snapshot",
        prepared_on=date(2026, 5, 7),
    ))
    html = gen.render_html(data)
    p = out_dir / fname
    p.write_text(html)
    pi = data.property_info
    print(
        f"  {slug:<14} {pid:<22} -> {p}  ({len(html) // 1024} KB)  "
        f"owner={pi.owner_name if pi else None!r}  "
        f"val={pi.assessed_value if pi else None}  "
        f"yr={pi.year_built if pi else None}"
    )
