"""Report generation endpoints."""

from __future__ import annotations

import re
import time
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.services import buildability, homeowner_full, lender, market, neighborhood, proforma, risk, zoning
from backend.services.buildability import collect_brief_data
from backend.services.demo_reports import get_demo_report_html
from backend.services.report_availability import get_report_availability
from backend.utils.parcel_lookup import (
    ParcelNotFoundError,
    UnsupportedTownError,
    resolve_address,
)
from backend.utils.pdf_export import export_portal_pdf, wrap_report_html

router = APIRouter(prefix="/api/reports", tags=["reports"])

ReportType = Literal[
    "buildability",
    "market",
    "risk",
    "proforma",
    "zoning",
    "neighborhood",
    "lender",
    "homeowner-full",
]


class ReportRequest(BaseModel):
    address: str
    parcel_id: str
    town_slug: str
    prepared_for: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class AvailabilityRequest(BaseModel):
    address: str = Field(..., min_length=3)
    parcel_id: Optional[str] = None
    town_slug: Optional[str] = None


@router.post("/availability")
async def report_availability(body: AvailabilityRequest):
    try:
        parcel = await resolve_address(
            body.address,
            parcel_id=body.parcel_id,
            town_slug=body.town_slug,
        )
    except UnsupportedTownError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ParcelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    reports = get_report_availability(parcel["town_slug"], parcel["parcel_id"])
    return {
        "reports": reports,
        "parcel": {
            "address": parcel["address"],
            "parcel_id": parcel["parcel_id"],
            "town_slug": parcel["town_slug"],
            "town_name": parcel["town_name"],
            "lat": parcel.get("lat"),
            "lng": parcel.get("lng"),
        },
        "report_request_email": get_settings().report_request_email,
    }


def _elapsed_seconds(request: Request | None) -> float | None:
    """True round-trip seconds since the API received the request.

    Reads the timestamp stamped by the ``_stamp_request_received`` middleware
    (set before any route logic runs), so the value spans parcel lookup, live
    web scrapes (e.g. Invoice Cloud), and cached parquet reads through to the
    moment the report content is assembled.
    """
    if request is None:
        return None
    start = getattr(request.state, "received_at", None)
    if start is None:
        return None
    return max(0.0, time.perf_counter() - start)


def _inject_timing_badge(html: str, seconds: float | None) -> str:
    """Insert a 'Generated in N seconds' badge into the report HTML.

    Uses fully inline styles so it renders identically in the inline preview,
    the exported PDF, and any context where external <style> blocks are stripped.
    """
    if not html or seconds is None:
        return html

    label = f"Generated live in {seconds:.2f} seconds"
    badge = (
        '<div class="te-gen-badge" style="display:inline-flex;align-items:center;'
        "gap:6px;margin:0 0 14px;padding:5px 12px;border-radius:999px;"
        "background:#0B1F3A;color:#fff;font-size:12px;font-weight:600;"
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'letter-spacing:.2px;box-shadow:0 1px 3px rgba(11,31,58,.25)">'
        f'<span aria-hidden="true">\u26a1</span>{label}</div>'
    )

    # Prefer placing the badge at the top of the report card.
    m = re.search(r'<div[^>]*class="[^"]*te-report[^"]*"[^>]*>', html, re.I)
    if m:
        idx = m.end()
        return html[:idx] + badge + html[idx:]

    m = re.search(r"<body[^>]*>", html, re.I)
    if m:
        idx = m.end()
        return html[:idx] + badge + html[idx:]

    return badge + html


def _report_response(
    report_type: str,
    html: str,
    payload: dict[str, Any] | None,
    req: ReportRequest,
    request: Request | None = None,
    *,
    skip_pdf: bool = False,
) -> dict[str, Any]:
    # Measure once the report content (live scrapes + parquet lookups + render)
    # is fully assembled, then stamp the badge into the HTML so the PDF export
    # below embeds the same number the inline preview shows.
    elapsed = _elapsed_seconds(request)
    html = _inject_timing_badge(html, elapsed)

    download_url = None
    pdf_path = None
    if not skip_pdf and not get_settings().portal_skip_pdf:
        try:
            pdf_path, download_url = export_portal_pdf(
                html,
                town_slug=req.town_slug,
                parcel_id=req.parcel_id,
                report_type=report_type,
                address=req.address,
                prepared_for=req.prepared_for,
            )
        except Exception:
            pass

    return {
        "report_type": report_type,
        "html": html,
        "data": payload,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "download_url": download_url,
        "generated_seconds": round(elapsed, 2) if elapsed is not None else None,
    }


@router.post("/buildability")
def report_buildability(req: ReportRequest, request: Request):
    try:
        html = get_demo_report_html(req.town_slug, req.parcel_id, "buildability")
        from_cache = html is not None
        if html is None:
            html = buildability.generate_buildability_html(
                req.town_slug, req.parcel_id, req.prepared_for,
            )
        return _report_response("buildability", html, None, req, request, skip_pdf=from_cache)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/zoning")
def report_zoning(req: ReportRequest, request: Request):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = zoning.generate_zoning_json(data)
        html = zoning.render_zoning_html(data)
        return _report_response("zoning", html, payload, req, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/risk")
def report_risk(req: ReportRequest, request: Request):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = risk.generate_risk_json(data)
        html = risk.render_risk_html(data)
        return _report_response("risk", html, payload, req, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/market")
def report_market(req: ReportRequest, request: Request):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = market.generate_market_report(data)
        html = market.render_market_html(payload, req.address)
        return _report_response("market", html, payload, req, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/proforma")
def report_proforma(req: ReportRequest, request: Request):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = proforma.generate_proforma(data)
        html = proforma.render_proforma_html(payload, req.address)
        return _report_response("proforma", html, payload, req, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/neighborhood")
def report_neighborhood(req: ReportRequest, request: Request):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = neighborhood.generate_neighborhood(data)
        html = neighborhood.render_neighborhood_html(payload, req.address)
        return _report_response("neighborhood", html, payload, req, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/lender")
def report_lender(req: ReportRequest, request: Request):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        html = lender.generate_lender_html(data, req.prepared_for)
        return _report_response("lender", html, None, req, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/homeowner-full")
def report_homeowner_full(req: ReportRequest, request: Request):
    try:
        html = get_demo_report_html(req.town_slug, req.parcel_id, "homeowner-full")
        if html is None:
            html = homeowner_full.generate_homeowner_full_html(
                req.town_slug, req.parcel_id, req.prepared_for,
            )
        return _report_response("homeowner-full", html, None, req, request, skip_pdf=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
