"""
TownEye Portal — FastAPI application.

Local dev (API + Vite):
  ./scripts/start_portal.sh

Production demo (towneye.ai — single server):
  ./scripts/start_portal_prod.sh
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI
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

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(parcels.router)
app.include_router(reports.router)
app.include_router(auth.router)


@app.on_event("startup")
def _warm_address_index() -> None:
    from backend.utils.parcel_lookup import _address_index_entries

    for slug in get_settings().town_slugs:
        try:
            _address_index_entries(slug)
        except OSError:
            pass


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "towns": get_settings().town_slugs,
        "portal_url": get_settings().portal_public_url,
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
