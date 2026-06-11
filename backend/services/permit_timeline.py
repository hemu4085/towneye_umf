"""Permit Timeline Intelligence Report — town-wide historical permitting timelines."""

from __future__ import annotations

import io
import csv
from datetime import date
from typing import Any

from backend.config import get_settings
from backend.services.deal_radar_config import get_town_display_name

def generate_permit_timeline(town_slug: str) -> dict[str, Any]:
    town_name = get_town_display_name(town_slug)
    
    # Prototype payload (Mock data simulating ZBA / Planning Board historicals)
    summary_stats = {
        "avg_days_residential_reno": 28,
        "avg_days_new_construction": 145,
        "avg_days_zba_special_permit": 85,
        "approval_rate_zba": "82%",
        "fastest_month": "October",
        "slowest_month": "August"
    }
    
    projects = [
        {
            "permit_type": "ZBA Special Permit",
            "project_type": "New Construction - Multi-Family",
            "approval_body": "Zoning Board of Appeals",
            "application_date": "2025-04-12",
            "decision_date": "2025-08-30",
            "calendar_days": 140,
            "outcome": "Approved with Conditions",
            "attorney": "Local Counsel A",
            "address": "45 Example St"
        },
        {
            "permit_type": "Building Permit",
            "project_type": "Addition / ADU",
            "approval_body": "Inspectional Services",
            "application_date": "2025-09-01",
            "decision_date": "2025-09-28",
            "calendar_days": 27,
            "outcome": "Approved",
            "attorney": "N/A",
            "address": "12 Mockingbird Ln"
        },
        {
            "permit_type": "Planning Board Approval",
            "project_type": "Commercial Fit-Out",
            "approval_body": "Planning Board",
            "application_date": "2025-11-05",
            "decision_date": "2026-02-10",
            "calendar_days": 97,
            "outcome": "Approved",
            "attorney": "Regional Firm B",
            "address": "900 Main St"
        },
        {
            "permit_type": "Conservation Commission",
            "project_type": "Site Work (Wetlands Buffer)",
            "approval_body": "Conservation Commission",
            "application_date": "2025-06-15",
            "decision_date": "2025-10-20",
            "calendar_days": 127,
            "outcome": "Denied (Appealed)",
            "attorney": "Specialist C",
            "address": "33 River Rd"
        }
    ]
    
    return {
        "report_type": "permit-timeline",
        "town_slug": town_slug,
        "town_name": town_name,
        "prepared_on": date.today().isoformat(),
        "summary_stats": summary_stats,
        "projects": projects,
        "pilot_message": "This is a prototype report. It uses simulated data. In production, this will ingest historical ZBA / Planning Board minutes and town permitting API endpoints.",
    }


def permit_timeline_to_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    
    writer.writerow(["--- PERMIT TIMELINE INTELLIGENCE ---"])
    writer.writerow(["Town", payload.get("town_name")])
    writer.writerow([])
    
    writer.writerow(["--- SUMMARY STATISTICS ---"])
    stats = payload.get("summary_stats", {})
    for k, v in stats.items():
        writer.writerow([k, v])
    writer.writerow([])
    
    writer.writerow(["--- RECENT DECISIONS ---"])
    projects = payload.get("projects") or []
    if projects:
        headers = ["Permit Type", "Project Type", "Approval Body", "Application Date", "Decision Date", "Calendar Days", "Outcome", "Attorney", "Address"]
        writer.writerow(headers)
        for p in projects:
            writer.writerow([
                p.get("permit_type", ""),
                p.get("project_type", ""),
                p.get("approval_body", ""),
                p.get("application_date", ""),
                p.get("decision_date", ""),
                p.get("calendar_days", ""),
                p.get("outcome", ""),
                p.get("attorney", ""),
                p.get("address", "")
            ])
    
    return buf.getvalue()


def render_permit_timeline_html(payload: dict[str, Any]) -> str:
    town = payload.get("town_name", "Town")
    prepared = payload.get("prepared_on", date.today().isoformat())
    
    import base64
    csv_text = permit_timeline_to_csv(payload)
    csv_b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
    csv_href = f"data:text/csv;base64,{csv_b64}"
    
    stats = payload.get("summary_stats", {})
    projects = payload.get("projects", [])
    
    project_rows = ""
    for p in projects:
        outcome_cls = "ok" if "Approved" in p.get("outcome", "") else "fl"
        project_rows += f'''<tr>
            <td>{p.get("permit_type")}</td>
            <td>{p.get("project_type")}</td>
            <td>{p.get("approval_body")}</td>
            <td class="num">{p.get("application_date")}</td>
            <td class="num">{p.get("decision_date")}</td>
            <td class="num"><strong>{p.get("calendar_days")}</strong></td>
            <td><span class="{outcome_cls}">{p.get("outcome")}</span></td>
            <td>{p.get("attorney")}</td>
        </tr>'''
        
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Permit Timeline Intelligence — {town}</title>
<style>
  body{{font-family:Georgia,'Times New Roman',serif;font-size:13px;line-height:1.55;color:#1a1a1a;max-width:920px;margin:36px auto;padding:0 28px;background:#fff}}
  h1{{font-size:22px;margin:0 0 4px;color:#0b2545;letter-spacing:.5px}}
  h2{{font-size:13px;letter-spacing:1.5px;text-transform:uppercase;color:#0b2545;border-bottom:2px solid #0b2545;padding:18px 0 4px;margin:18px 0 10px}}
  .hd{{border-bottom:1px solid #ccc;padding-bottom:10px;margin-bottom:8px}}
  .meta{{font-size:11px;color:#555;margin-top:6px}}
  table{{width:100%;border-collapse:collapse;margin:6px 0 10px;font-size:12px}}
  th{{background:#0b2545;color:#fff;text-align:left;padding:6px 8px;font-size:11px;letter-spacing:.4px}}
  td{{padding:5px 8px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  tr:nth-child(even) td{{background:#f7f9fc}}
  .num{{font-variant-numeric:tabular-nums}}
  .note{{font-size:12px;color:#555;font-style:italic;margin:8px 0}}
  .btn{{display:inline-block;margin:8px 0 12px;padding:8px 14px;background:#0b2545;color:#fff;text-decoration:none;border-radius:4px;font-size:12px}}
  .ok{{color:#1a7a1a;font-weight:bold}}
  .fl{{color:#a02020;font-weight:bold}}
  .logo-header {{ position: absolute; top: 20px; right: 28px; height: 32px; opacity: 0.8; }}
</style></head><body>
<div class="te-report">

<div class="hd" style="position: relative;">
  <img src="https://demo.towneye.ai/logo.png" alt="TownEye Logo" class="logo-header" />
  <h1>Permit Timeline Intelligence</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{town}, MA</div>
  <div class="meta">Prepared on {prepared}</div>
</div>

<p class="note"><strong>Pilot Phase:</strong> {payload.get("pilot_message")}</p>

<h2>1 · Executive Summary</h2>
<a class="btn" href="{csv_href}" download="permit-timeline-{town}.csv">Download Report (CSV)</a>
<table>
  <tr><th>Metric</th><th>Historical Value</th></tr>
  <tr><td>Avg Days — Residential Renovation (By-Right)</td><td class="num">{stats.get("avg_days_residential_reno")} days</td></tr>
  <tr><td>Avg Days — New Construction (By-Right)</td><td class="num">{stats.get("avg_days_new_construction")} days</td></tr>
  <tr><td>Avg Days — ZBA Special Permit</td><td class="num">{stats.get("avg_days_zba_special_permit")} days</td></tr>
  <tr><td>ZBA Approval Rate</td><td class="num">{stats.get("approval_rate_zba")}</td></tr>
  <tr><td>Fastest / Slowest Processing Months</td><td>{stats.get("fastest_month")} / {stats.get("slowest_month")}</td></tr>
</table>

<h2>2 · Historical Decisions Log</h2>
<table>
<tr><th>Permit Type</th><th>Project Type</th><th>Board</th><th>Application</th><th>Decision</th><th>Days</th><th>Outcome</th><th>Attorney / Rep</th></tr>
{project_rows}
</table>

</div>
</body></html>
"""
