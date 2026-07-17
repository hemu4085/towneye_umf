"""Entitlements & Risk — Gold pathway + optional board dockets (civic minutes)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from reports.buildability_brief import BriefData

from backend.config import get_settings
from backend.services.buildability import (
    _build_detailed_wraparound,
    _fmt_num,
    _open_items,
    _overlay_narrative,
    _process_pathway,
    _process_pathway_footnote,
)
from backend.services.zoning import (
    _overlay_election_recommendation,
    _zoning_constraints,
    _zoning_development_paths,
)


def _load_civic_dockets(town_slug: str, parcel_id: str, address: str | None) -> dict[str, Any]:
    """Return dockets from civic_minutes.parquet when the domain exists."""
    gold = Path(get_settings().gold_data_path) / town_slug / "civic_minutes.parquet"
    if not gold.exists():
        return {
            "status": "missing",
            "detail": (
                "civic_minutes.parquet is not in TownEye Gold for this town. "
                "In-flight ZBA / Planning / ARB / Conservation dockets are unavailable — "
                "confirm with the Town Clerk before a clear-path opinion."
            ),
            "dockets": [],
        }

    try:
        df = pd.read_parquet(gold)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "missing",
            "detail": f"civic_minutes.parquet could not be read ({exc}).",
            "dockets": [],
        }

    if df.empty:
        return {
            "status": "empty",
            "detail": "civic_minutes.parquet is present but contains no records.",
            "dockets": [],
        }

    hits = pd.DataFrame()
    if "parcel_id" in df.columns and parcel_id:
        hits = df[df["parcel_id"].astype(str) == str(parcel_id)]
    if hits.empty and address and "address" in df.columns:
        needle = address.upper().strip()
        # Strip common street suffixes for loose match
        for token in (" STREET", " ST", " AVENUE", " AVE", " ROAD", " RD"):
            if needle.endswith(token):
                needle = needle[: -len(token)].strip()
                break
        hits = df[
            df["address"].astype(str).str.upper().str.contains(needle, regex=False, na=False)
        ]

    dockets: list[dict[str, Any]] = []
    for _, row in hits.iterrows():
        md_raw = row.get("metadata", {}) or {}
        if isinstance(md_raw, str):
            try:
                md = json.loads(md_raw)
            except Exception:  # noqa: BLE001
                md = {}
        else:
            md = md_raw if isinstance(md_raw, dict) else {}
        dockets.append({
            "event_type": str(row.get("event_type") or md.get("event_type") or "—"),
            "address": str(row.get("address") or address or "—"),
            "docket": (
                str(row.get("docket"))
                if row.get("docket") is not None and str(row.get("docket")) not in ("", "nan", "None")
                else None
            ),
            "status": str(row.get("status") or md.get("status") or "—"),
            "board": str(md.get("board") or row.get("board") or "—"),
            "summary": str(md.get("summary") or row.get("summary") or ""),
        })

    if dockets:
        return {
            "status": "found",
            "detail": f"{len(dockets)} docket record(s) matched this parcel in civic_minutes.parquet.",
            "dockets": dockets,
        }
    return {
        "status": "none_matched",
        "detail": (
            "No civic_minutes records matched this parcel address. "
            "This is not proof of a clear entitlement path — verify with the Town Clerk."
        ),
        "dockets": [],
    }


def _risk_signals(data: BriefData, dockets_meta: dict[str, Any]) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    base_env = next((e for e in data.envelopes if not e.is_overlay), None)
    if base_env and base_env.qualifies is False:
        signals.append({
            "signal": "Base lot non-conformance",
            "severity": "warning",
            "detail": (
                f"Lot does not meet {base_env.zone_code} minimum lot size for new construction — "
                f"tear-down/rebuild under base zoning typically needs ZBA relief unless the "
                f"overlay is elected."
            ),
        })
    if data.has_overlay_election:
        signals.append({
            "signal": "Overlay election required",
            "severity": "info",
            "detail": (
                f"Elect {data.primary_overlay_code or 'overlay'} OR "
                f"{data.primary_zone_code or 'base'} — regimes do not stack "
                f"(Arlington ZBL §5.8 / M.G.L. c. 40A §3A)."
            ),
        })
    flagged = [c for c in _zoning_constraints(data) if c.get("status") == "flagged"]
    for c in flagged[:4]:
        signals.append({
            "signal": c["label"],
            "severity": "warning",
            "detail": f"{c.get('detail')} — cite: {c.get('source') or 'GIS'}",
        })
    # Domain-not-ingested is a data-coverage note, not a parcel risk signal.
    if dockets_meta.get("status") == "found":
        signals.append({
            "signal": "Prior board activity on parcel",
            "severity": "warning",
            "detail": dockets_meta["detail"],
        })
    return signals


def generate_civic_entitlements_json(data: BriefData) -> dict[str, Any]:
    prop = data.property_info
    address = data.parcel.address
    dockets_meta = _load_civic_dockets(
        data.inputs.town_slug,
        data.parcel.parcel_id,
        address,
    )
    election = _overlay_election_recommendation(data)
    zone_label = data.primary_zone_code or "—"
    if data.primary_overlay_code:
        zone_label = f"{zone_label} + {data.primary_overlay_code}"

    return {
        "address": address,
        "parcel_id": data.parcel.parcel_id,
        "town_slug": data.inputs.town_slug,
        "report_date": data.report_date_text,
        "zoning_district": zone_label,
        "primary_zone_code": data.primary_zone_code,
        "primary_overlay_code": data.primary_overlay_code,
        "has_overlay_election": data.has_overlay_election,
        "has_mbta_communities_overlay": data.has_mbta_communities_overlay,
        "headline_verdict_class": data.headline_verdict_class,
        "headline_verdict_text": data.headline_verdict_text,
        "overlay_narrative": _overlay_narrative(data),
        "overlay_election": election,
        "process_pathway": _process_pathway(data),
        "process_pathway_footnote": _process_pathway_footnote(data),
        "development_paths": _zoning_development_paths(data),
        "zoning_constraints": _zoning_constraints(data),
        "wraparound": _build_detailed_wraparound(data),
        "risk_signals": _risk_signals(data, dockets_meta),
        "board_dockets_status": {
            "status": dockets_meta["status"],
            "detail": dockets_meta["detail"],
        },
        "dockets": dockets_meta["dockets"],
        "open_items": _open_items(data)[:8],
        "lot_size_sqft": (
            prop.lot_size_sqft if prop and prop.lot_size_sqft else data.parcel.area_sqft
        ),
        "existing_gfa_sqft": prop.finished_area_sqft if prop else None,
        "sources": (
            f"Sources: {data.inputs.town_slug} zoning GIS + zoning.parquet / §3A config fixture; "
            f"OverlayResolver wraparound layers; permits.parquet (ISD). "
            f"Board-minute docket ingest is optional; when absent, pathway/constraints still "
            f"reflect Gold zoning facts."
        ),
    }


def render_civic_entitlements_html(data: BriefData) -> str:
    payload = generate_civic_entitlements_json(data)

    def esc(text: Any) -> str:
        return (
            str(text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    path_rows = "".join(
        f"<tr><td>{esc(r.get('stage'))}</td><td>{esc(r.get('body'))}</td>"
        f"<td>{esc(r.get('path_type') or '—')}</td>"
        f"<td>{esc(r.get('duration'))}</td>"
        f"<td>{'Gold' if r.get('duration_basis') == 'gold' else 'Estimate'}</td></tr>"
        for r in payload.get("process_pathway") or []
    )
    dockets = payload.get("dockets") or []
    docket_rows = (
        "".join(
            f"<tr><td>{esc(d.get('board'))}</td><td>{esc(d.get('docket') or '—')}</td>"
            f"<td>{esc(d.get('status'))}</td><td>{esc(d.get('summary'))}</td></tr>"
            for d in dockets
        )
        or "<tr><td colspan='4'>No matched board dockets in Gold.</td></tr>"
    )
    signals = "".join(
        f"<li><strong>{esc(s.get('signal'))}</strong> — {esc(s.get('detail'))}</li>"
        for s in payload.get("risk_signals") or []
    )
    election = payload.get("overlay_election") or {}
    election_html = ""
    if election:
        election_html = (
            f"<p><strong>Overlay election:</strong> {esc(election.get('recommended_regime'))} "
            f"(alt {esc(election.get('alternative_regime'))}). "
            f"{esc(election.get('election_type'))}. "
            f"Citation: {esc(election.get('legal_basis'))}</p>"
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Entitlements &amp; Risk — {esc(payload.get('address'))}</title>
<style>
  body{{font-family:Georgia,serif;color:#0B1F3A;max-width:860px;margin:24px auto;padding:0 20px}}
  h1{{font-size:22px;border-bottom:3px solid #C9A84C;padding-bottom:8px}}
  h2{{font-size:14px;margin-top:28px;border-bottom:1px solid #e5e5e5;padding-bottom:6px}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}}
  th{{background:#0B1F3A;color:#F5F0E8;text-align:left;padding:8px}}
  td{{padding:8px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
  .meta,.src{{font-size:12px;color:#555}}
</style></head><body>
<h1>Entitlements &amp; Risk Brief</h1>
<p class="meta"><strong>{esc(payload.get('address'))}</strong> · Parcel {esc(payload.get('parcel_id'))}<br>
District: <strong>{esc(payload.get('zoning_district'))}</strong> · Lot {_fmt_num(payload.get('lot_size_sqft'))} sf</p>
{election_html}
<h2>Risk signals</h2><ul>{signals or '<li>None flagged</li>'}</ul>
<h2>Entitlement process pathway</h2>
<table><tr><th>Stage</th><th>Body</th><th>Path</th><th>Duration</th><th>Basis</th></tr>
{path_rows}</table>
<p class="src">{esc(payload.get('process_pathway_footnote'))}</p>
<h2>Board docket history (Gold)</h2>
<table><tr><th>Board</th><th>Docket</th><th>Status</th><th>Summary</th></tr>
{docket_rows}</table>
<p class="src">{esc(payload.get('sources'))}</p>
</body></html>"""
