"""TownEye portal configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

_EPHEMERAL = bool(
    os.getenv("RAILWAY_ENVIRONMENT")
    or os.getenv("VERCEL")
    or os.getenv("RENDER")
)


def _default_reports_path() -> Path:
    if _EPHEMERAL:
        return Path("/tmp/towneye/reports")
    return REPO_ROOT / "reports" / "output"


def _default_gold_path() -> Path:
    if os.getenv("GOLD_DATA_PATH"):
        return Path(os.getenv("GOLD_DATA_PATH"))
    return REPO_ROOT / "data" / "gold"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    gold_data_path: Path
    reports_output_path: Path
    admin_api_key: str
    supported_towns: str
    anthropic_model: str
    config_dir: Path
    approved_users_path: Path
    waitlist_path: Path
    report_request_email: str
    portal_public_url: str
    cors_origins: tuple[str, ...]
    serve_frontend: bool
    frontend_dist_path: Path

    @property
    def town_slugs(self) -> list[str]:
        return [t.strip() for t in self.supported_towns.split(",") if t.strip()]


def _parse_cors_origins(portal_public_url: str) -> tuple[str, ...]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    local = ("http://localhost:5173", "http://127.0.0.1:5173")
    if raw:
        origins = tuple(o.strip().rstrip("/") for o in raw.split(",") if o.strip())
        return origins + local

    origins: list[str] = []
    if portal_public_url:
        base = portal_public_url.rstrip("/")
        origins.append(base)
        if base.startswith("https://") and not base.startswith("https://www."):
            origins.append(base.replace("https://", "https://www.", 1))
        elif base.startswith("http://") and not base.startswith("http://www."):
            origins.append(base.replace("http://", "http://www.", 1))
    return tuple(origins + list(local))


@lru_cache
def get_settings() -> Settings:
    portal_public_url = os.getenv("PORTAL_PUBLIC_URL", "https://demo.towneye.ai").strip()
    serve_frontend = os.getenv("SERVE_FRONTEND", "").lower() in ("1", "true", "yes") or (
        os.getenv("TOWNEYE_ENV", "").lower() == "production"
    )
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        gold_data_path=_default_gold_path(),
        reports_output_path=Path(
            os.getenv("REPORTS_OUTPUT_PATH", str(_default_reports_path())),
        ),
        admin_api_key=os.getenv("ADMIN_API_KEY", "changeme"),
        supported_towns=os.getenv("SUPPORTED_TOWNS", "arlington-ma,lexington-ma"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        config_dir=Path(os.getenv("CONFIG_DIR", str(REPO_ROOT / "configs"))),
        approved_users_path=REPO_ROOT / "backend" / "data" / "approved_users.json",
        waitlist_path=REPO_ROOT / "backend" / "data" / "waitlist.json",
        report_request_email=os.getenv("REPORT_REQUEST_EMAIL", "hemuit4085@gmail.com"),
        portal_public_url=portal_public_url,
        cors_origins=_parse_cors_origins(portal_public_url),
        serve_frontend=serve_frontend,
        frontend_dist_path=Path(
            os.getenv("FRONTEND_DIST_PATH", str(REPO_ROOT / "frontend" / "dist")),
        ),
    )
