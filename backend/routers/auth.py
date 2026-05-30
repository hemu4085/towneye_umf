"""Simple email whitelist + waitlist."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from backend.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AccessRequest(BaseModel):
    email: EmailStr


class WaitlistRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    user_type: str = Field(..., min_length=1)
    primary_town: str = Field(..., min_length=1)


def _load_json(path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@router.post("/check")
def check_access(body: AccessRequest):
    settings = get_settings()
    approved = _load_json(settings.approved_users_path)
    if body.email.lower() in {e.lower() for e in approved}:
        return {"approved": True, "email": body.email}
    return {"approved": False, "email": body.email}


@router.post("/waitlist")
def join_waitlist(body: WaitlistRequest):
    settings = get_settings()
    entries = _load_json(settings.waitlist_path)
    entry = {
        **body.model_dump(),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    _save_json(settings.waitlist_path, entries)
    return {"ok": True, "message": "Added to waitlist."}


@router.get("/admin/waitlist")
def admin_waitlist(x_admin_key: str | None = Header(default=None)):
    settings = get_settings()
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin key.")
    return _load_json(settings.waitlist_path)
