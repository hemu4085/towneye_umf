"""Smoke-check neighborhood guide. Run: PYTHONPATH=. python scripts/_smoke_neighborhood.py"""
from __future__ import annotations

import traceback
from pathlib import Path

from backend.services.buildability import collect_brief_data
from backend.services.neighborhood import generate_neighborhood, render_neighborhood_html

OUT = Path(__file__).resolve().parent / "_neighborhood_smoke_out.txt"


def main() -> None:
    lines: list[str] = []
    try:
        for pid, addr in [
            ("008.0-0001-0010.0", "5-7 Belknap St"),
            ("164.0-0004-0004.0", "34 ACTON ST"),
        ]:
            data = collect_brief_data("arlington-ma", pid, None)
            payload = generate_neighborhood(data)
            html = render_neighborhood_html(payload, addr)
            lines.append(f"ADDR {addr}")
            lines.append(f" assessed {(payload.get('assessor') or {}).get('assessed_value')}")
            lines.append(f" neighbors {len(payload.get('neighbors') or [])}")
            lines.append(f" street_median {(payload.get('street') or {}).get('median_assessed')}")
            lines.append(f" transit {len(payload.get('transit_alerts') or [])}")
            lines.append(f" calendar {len(payload.get('school_calendar') or [])}")
            lines.append(f" infra {len(payload.get('infra_projects') or [])}")
            lines.append(f" walk {payload.get('walk_score')} schools {payload.get('schools')}")
            lines.append(f" highlights {len(payload.get('highlights') or [])}")
            lines.append(f" hardy_in_html {'Hardy' in html}")
            lines.append(f" same_street {'Same-street' in html}")
            assert payload.get("walk_score") is None
            assert "Hardy" not in html
        lines.append("OK")
    except Exception:
        lines.append(traceback.format_exc())
        lines.append("FAIL")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
