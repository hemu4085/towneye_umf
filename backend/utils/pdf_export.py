"""Portal PDF export with TownEye branding."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from reports.html_to_pdf import convert_html_to_pdf, format_report_date, patch_prepared_for

from backend.config import get_settings

_BRAND_HEADER = """
<div style="background:#0B1F3A;color:#F5F0E8;padding:14px 20px;border-bottom:3px solid #C9A84C;
            font-family:'DM Sans',Arial,sans-serif;">
  <div style="font-size:20px;font-weight:700;letter-spacing:1px;">TownEye</div>
  <div style="font-size:12px;color:#C9A84C;margin-top:4px;">{address}</div>
  <div style="font-size:11px;color:#8A9BB0;margin-top:2px;">
    {date_text}{prepared_line}
  </div>
</div>
"""

_BRAND_FOOTER = """
<div style="margin-top:24px;padding:12px 20px;border-top:1px solid #C9A84C;
            font-size:10px;color:#8A9BB0;text-align:center;font-family:'DM Sans',Arial,sans-serif;">
  Prepared by TownEye · towneye.ai · For informational purposes only
</div>
"""


_MAX_FILENAME_LEN = 200

# Short slugs for report types (kept compact for path limits).
REPORT_SLUGS: dict[str, str] = {
    "buildability": "buildability_brief",
    "market": "market_snapshot",
    "risk": "risk_constraints",
    "proforma": "pro_forma",
    "zoning": "zoning_summary",
    "neighborhood": "neighborhood_intel",
    "lender": "lender_pack",
}


def _slugify_text(value: str) -> str:
    s = value.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s or "report"


def _slugify_address(address: str) -> str:
    """e.g. '24 Princeton Road, Arlington MA' → '24_princeton_road_arlington_ma'."""
    return _slugify_text(address) or "address"


def _slugify_report(report_type: str) -> str:
    return REPORT_SLUGS.get(report_type, _slugify_text(report_type.replace("_", " ")))


def _pdf_date_time_parts(when: datetime | None = None) -> tuple[str, str]:
    """e.g. May 26 2026 3:15 PM → ('5262026', '3_15_pm')."""
    now = when or datetime.now()
    date_part = f"{now.month}{now.day}{now.year}"
    hour_12 = now.hour % 12 or 12
    ampm = "am" if now.hour < 12 else "pm"
    time_part = f"{hour_12}_{now.minute:02d}_{ampm}"
    return date_part, time_part


def portal_pdf_filename(
    address: str,
    report_type: str,
    when: datetime | None = None,
) -> str:
    address_slug = _slugify_address(address)
    report_slug = _slugify_report(report_type)
    date_part, time_part = _pdf_date_time_parts(when)
    suffix = f"_{report_slug}_{date_part}_{time_part}.pdf"
    max_address_len = max(8, _MAX_FILENAME_LEN - len(suffix))
    if len(address_slug) > max_address_len:
        address_slug = address_slug[:max_address_len].rstrip("_")
    return f"{address_slug}{suffix}"


def wrap_report_html(
    body_html: str,
    *,
    address: str,
    prepared_for: str | None = None,
    prepared_on: date | None = None,
) -> str:
    """Inject TownEye header/footer around report body."""
    prepared_line = f" · Prepared for {prepared_for}" if prepared_for else ""
    header = _BRAND_HEADER.format(
        address=address,
        date_text=format_report_date(prepared_on or date.today()),
        prepared_line=prepared_line,
    )
    if "<body" in body_html.lower():
        body_html = re.sub(
            r"(<body[^>]*>)",
            rf"\1{header}",
            body_html,
            count=1,
            flags=re.I,
        )
        body_html = re.sub(r"</body>", f"{_BRAND_FOOTER}</body>", body_html, count=1, flags=re.I)
    else:
        body_html = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{header}{body_html}{_BRAND_FOOTER}</body></html>"
    if prepared_for or prepared_on:
        body_html = patch_prepared_for(
            body_html,
            prepared_for=prepared_for,
            prepared_on=prepared_on,
        )
    return body_html


def export_portal_pdf(
    html: str,
    *,
    town_slug: str,
    parcel_id: str,
    report_type: str,
    address: str,
    prepared_for: str | None = None,
) -> tuple[Path, str]:
    """Write branded PDF; return path and download URL path."""
    settings = get_settings()
    settings.reports_output_path.mkdir(parents=True, exist_ok=True)
    filename = portal_pdf_filename(address, report_type)
    pdf_path = settings.reports_output_path / filename
    html_path = pdf_path.with_suffix(".html")
    branded = wrap_report_html(html, address=address, prepared_for=prepared_for)
    html_path.write_text(branded, encoding="utf-8")
    convert_html_to_pdf(html_path, pdf_path, prepared_for=prepared_for, prepared_on=date.today())
    return pdf_path, f"/api/files/{filename}"
