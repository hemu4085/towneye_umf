"""Smoke-check homeowner insights. Run: PYTHONPATH=. python scripts/_smoke_homeowner.py"""
from __future__ import annotations

import traceback
from pathlib import Path

from backend.services.buildability import collect_brief_data
from backend.services.homeowner import generate_homeowner_report, render_homeowner_html

OUT = Path(__file__).resolve().parent / "_homeowner_smoke_out.txt"


def main() -> None:
    lines: list[str] = []
    try:
        for pid, addr in [
            ("008.0-0001-0010.0", "5-7 Belknap St"),
            ("164.0-0004-0004.0", "34 ACTON ST"),
        ]:
            data = collect_brief_data("arlington-ma", pid, None)
            payload = generate_homeowner_report(data)
            html = render_homeowner_html(payload, addr)
            lines.append(f"ADDR {addr}")
            lines.append(f" assessed {(payload.get('assessor') or {}).get('assessed_value')}")
            lines.append(f" zhvi {(payload.get('market') or {}).get('zhvi_latest')}")
            lines.append(f" ideas {len(payload.get('renovation_ideas') or [])}")
            lines.append(f" actions {len(payload.get('action_items') or [])}")
            lines.append(f" fake_roi {'72% ROI' in html or '115% ROI' in html}")
            lines.append(f" roi_note {'ROI' in (payload.get('roi_note') or '')}")
            lines.append(f" tax_portal {bool((payload.get('tax') or {}).get('portal_url'))}")
            assert "72% ROI" not in html
            assert payload.get("roi_status") == "unavailable"
        a = generate_homeowner_report(collect_brief_data("arlington-ma", "008.0-0001-0010.0", None))
        b = generate_homeowner_report(collect_brief_data("arlington-ma", "164.0-0004-0004.0", None))
        assert (a.get("assessor") or {}).get("assessed_value") != (b.get("assessor") or {}).get(
            "assessed_value"
        )
        lines.append("OK")
    except Exception:
        lines.append(traceback.format_exc())
        lines.append("FAIL")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
