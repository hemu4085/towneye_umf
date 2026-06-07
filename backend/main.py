"""
TownEye Portal — FastAPI application.

Local dev (API + Vite):
  ./scripts/start_portal.sh

Production demo (towneye.ai — single server):
  ./scripts/start_portal_prod.sh
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.routers import auth, parcels, reports

app = FastAPI(
    title="TownEye Portal API",
    description="Massachusetts real estate intelligence reports",
    version="0.1.0",
)


@app.middleware("http")
async def _stamp_request_received(request: Request, call_next):
    """Record the earliest possible request-receipt time for true round-trip timing.

    This runs before route handlers, so the stamp captures the moment the API
    receives the request — before any parcel lookup, live web scrape, or cached
    parquet read. Report endpoints read ``request.state.received_at`` to compute
    the genuine end-to-end generation time shown in each report.
    """
    request.state.received_at = time.perf_counter()
    return await call_next(request)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_origins),
    allow_origin_regex=(
        r"https://(.*\.)?(vercel\.app|demo\.towneye\.ai|towneye\.ai)(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parcels.router)
app.include_router(reports.router)
app.include_router(auth.router)


@app.on_event("startup")
def _warm_address_index() -> None:
    from backend.services.demo_reports import get_demo_report_html
    from backend.utils.parcel_lookup import _address_index_entries

    for slug in get_settings().town_slugs:
        try:
            _address_index_entries(slug)
        except OSError:
            pass
    try:
        get_demo_report_html("arlington-ma", "008.0-0001-0010.0", "buildability")
    except OSError:
        pass


@app.get("/api/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "towns": settings.town_slugs,
        "portal_url": settings.portal_public_url,
        "llm_configured": bool(settings.anthropic_api_key.strip()),
    }


@app.get("/api/files/{filename}")
def download_file(filename: str):
    path = get_settings().reports_output_path / filename
    if not path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, media_type="application/pdf", filename=filename)


def _mount_frontend() -> None:
    settings = get_settings()
    dist = settings.frontend_dist_path
    if not settings.serve_frontend or not dist.is_dir():
        return
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")


_mount_frontend()
