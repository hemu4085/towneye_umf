"""Risk & Constraints report from wraparound layers."""

from __future__ import annotations

from reports.buildability_brief import BriefData

_STATUS_CLASS = {"clear": "ok", "caution": "wn", "flagged": "fl"}
_STATUS_LABEL = {"clear": "Clear", "caution": "Caution", "flagged": "Flagged"}


def generate_risk_json(data: BriefData) -> dict:
    items = []
    for c in data.wraparound:
        items.append({
            "label": c.label,
            "status": c.status,
            "status_label": _STATUS_LABEL.get(c.status, c.status),
            "detail": c.detail,
            "source": c.source,
            "hit_count": c.hit_count,
        })
    flagged = sum(1 for i in items if i["status"] == "flagged")
    caution = sum(1 for i in items if i["status"] == "caution")
    overall = "flagged" if flagged else ("caution" if caution else "clear")
    return {
        "address": data.parcel.address,
        "parcel_id": data.parcel.parcel_id,
        "overall_status": overall,
        "constraints": items,
    }


def render_risk_html(data: BriefData) -> str:
    payload = generate_risk_json(data)
    rows = ""
    for c in payload["constraints"]:
        pill = {"clear": "#1a7a1a", "caution": "#a06b00", "flagged": "#a02020"}.get(c["status"], "#555")
        rows += f"""<tr>
          <td>{c['label']}</td>
          <td><span style="color:{pill};font-weight:bold">{c['status_label']}</span></td>
          <td>{c['detail']}</td>
          <td style="font-size:11px;color:#666">{c['source']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  body{{font-family:'DM Sans',Arial,sans-serif;color:#0B1F3A;max-width:780px;margin:24px auto;padding:0 20px}}
  h1{{font-family:Georgia,serif;border-bottom:3px solid #C9A84C;padding-bottom:8px}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}}
  th{{background:#0B1F3A;color:#F5F0E8;text-align:left;padding:8px}}
  td{{padding:8px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
</style></head><body>
<h1>Risk &amp; Constraints Report</h1>
<p><strong>{payload['address']}</strong> · Overall: <strong>{payload['overall_status'].upper()}</strong></p>
<table>
<tr><th>Constraint</th><th>Status</th><th>Detail</th><th>Source</th></tr>
{rows}
</table>
</body></html>"""
