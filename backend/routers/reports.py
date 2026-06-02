"""Report generation endpoints."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.services import buildability, lender, market, neighborhood, proforma, risk, zoning
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
]


class ReportRequest(BaseModel):
    address: str
    parcel_id: str
    town_slug: str
    prepared_for: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class AvailabilityRequest(BaseModel):
    address: str = Field(..., min_length=5)


@router.post("/availability")
async def report_availability(body: AvailabilityRequest):
    try:
        parcel = await resolve_address(body.address)
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


def _report_response(
    report_type: str,
    html: str,
    payload: dict[str, Any] | None,
    req: ReportRequest,
) -> dict[str, Any]:
    download_url = None
    pdf_path = None
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
    }


@router.post("/buildability")
def report_buildability(req: ReportRequest):
    try:
        html = get_demo_report_html(req.town_slug, req.parcel_id, "buildability")
        if html is None:
            html = buildability.generate_buildability_html(
                req.town_slug, req.parcel_id, req.prepared_for,
            )
        return _report_response("buildability", html, None, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/zoning")
def report_zoning(req: ReportRequest):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = zoning.generate_zoning_json(data)
        html = zoning.render_zoning_html(data)
        return _report_response("zoning", html, payload, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/risk")
def report_risk(req: ReportRequest):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = risk.generate_risk_json(data)
        html = risk.render_risk_html(data)
        return _report_response("risk", html, payload, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/market")
def report_market(req: ReportRequest):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = market.generate_market_report(data)
        html = market.render_market_html(payload, req.address)
        return _report_response("market", html, payload, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/proforma")
def report_proforma(req: ReportRequest):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = proforma.generate_proforma(data)
        html = proforma.render_proforma_html(payload, req.address)
        return _report_response("proforma", html, payload, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/neighborhood")
def report_neighborhood(req: ReportRequest):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        payload = neighborhood.generate_neighborhood(data)
        html = neighborhood.render_neighborhood_html(payload, req.address)
        return _report_response("neighborhood", html, payload, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/lender")
def report_lender(req: ReportRequest):
    try:
        data = collect_brief_data(req.town_slug, req.parcel_id, req.prepared_for)
        html = lender.generate_lender_html(data, req.prepared_for)
        return _report_response("lender", html, None, req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
