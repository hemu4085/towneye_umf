"""Permit Timeline Intelligence — Gold permits.parquet velocity + key-path estimates."""

from __future__ import annotations

import base64
import csv
import io
from datetime import date
from typing import Any

import pandas as pd

from backend.config import get_settings
from backend.services.deal_radar_config import get_town_display_name
from backend.services.parcel_permits import (
    _OPEN_STATUSES,
    _parse_metadata,
    _permits_frame,
    get_parcel_permits,
)

# Display order for the key-permits estimate table.
_KEY_PERMIT_ORDER = [
    "RESIDENTIAL_RENO",
    "RESIDENTIAL_NEW",
    "COMMERCIAL_BUILD",
    "DEMOLITION",
    "SOLAR",
    "ELECTRICAL",
    "PLUMBING",
    "MECHANICAL",
    "SITE_PLAN_REVIEW",
    "ZBA_SPECIAL_PERMIT",
    "CONSERVATION",
]

_TYPE_LABELS: dict[str, str] = {
    "RESIDENTIAL_RENO": "Residential renovation (building permit)",
    "RESIDENTIAL_NEW": "New residential construction",
    "COMMERCIAL_BUILD": "Commercial build / fit-out",
    "DEMOLITION": "Demolition",
    "SOLAR": "Solar / roof-mounted PV",
    "ELECTRICAL": "Electrical (trade)",
    "PLUMBING": "Plumbing (trade)",
    "MECHANICAL": "Mechanical / HVAC (trade)",
    "SIGN": "Sign permit",
    "SHORT_TERM_RENTAL": "Short-term rental permit",
    "OTHER": "Other building permit",
    "SITE_PLAN_REVIEW": "Site Plan Review / Design Review",
    "ZBA_SPECIAL_PERMIT": "ZBA Special Permit / Variance",
    "CONSERVATION": "Conservation Commission (wetlands)",
}

_APPROVAL_BODY: dict[str, str] = {
    "RESIDENTIAL_RENO": "Inspectional Services (ISD)",
    "RESIDENTIAL_NEW": "Inspectional Services (ISD)",
    "COMMERCIAL_BUILD": "Inspectional Services (ISD)",
    "DEMOLITION": "Inspectional Services (ISD)",
    "SOLAR": "Inspectional Services (ISD)",
    "ELECTRICAL": "Inspectional Services (ISD)",
    "PLUMBING": "Inspectional Services (ISD)",
    "MECHANICAL": "Inspectional Services (ISD)",
    "SIGN": "Inspectional Services (ISD)",
    "SHORT_TERM_RENTAL": "Town licensing",
    "OTHER": "Inspectional Services (ISD)",
    "SITE_PLAN_REVIEW": "Planning / Design Review Board",
    "ZBA_SPECIAL_PERMIT": "Zoning Board of Appeals",
    "CONSERVATION": "Conservation Commission",
}

# Board timelines are not in TePermit (ISD API). Town config can override these.
_BOARD_ESTIMATES: dict[str, dict[str, Any]] = {
    "SITE_PLAN_REVIEW": {
        "estimated_days_low": 56,
        "estimated_days_high": 84,
        "estimated_days_mid": 70,
        "approval_rate_pct": None,
        "note": "Not in ISD permit ledger — estimate from typical MA review-board cycles.",
        "source": "town_board_estimate",
    },
    "ZBA_SPECIAL_PERMIT": {
        "estimated_days_low": 60,
        "estimated_days_high": 120,
        "estimated_days_mid": 85,
        "approval_rate_pct": 82.0,
        "note": "Not in ISD permit ledger — estimate from typical MA ZBA calendars.",
        "source": "town_board_estimate",
    },
    "CONSERVATION": {
        "estimated_days_low": 45,
        "estimated_days_high": 120,
        "estimated_days_mid": 75,
        "approval_rate_pct": None,
        "note": "Not in ISD permit ledger — estimate when wetlands buffer / NOI required.",
        "source": "town_board_estimate",
    },
}


def _load_town_cfg(town_slug: str) -> dict[str, Any]:
    path = get_settings().config_dir / town_slug / "config.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml

        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _calendar_days(app: Any, appr: Any) -> int | None:
    if app is None or appr is None or (isinstance(appr, float) and pd.isna(appr)):
        return None
    try:
        a = pd.to_datetime(app, utc=True, errors="coerce")
        b = pd.to_datetime(appr, utc=True, errors="coerce")
        if pd.isna(a) or pd.isna(b):
            return None
        days = int((b.normalize() - a.normalize()).days)
        return days if days >= 0 else None
    except Exception:
        return None


def _percentile(series: pd.Series, q: float) -> float | None:
    if series.empty:
        return None
    return round(float(series.quantile(q)), 1)


def _fallback_estimate(permit_type: str) -> dict[str, Any]:
    defaults = {
        "RESIDENTIAL_RENO": (14, 28, 45),
        "RESIDENTIAL_NEW": (60, 100, 150),
        "COMMERCIAL_BUILD": (45, 90, 150),
        "DEMOLITION": (10, 21, 40),
        "SOLAR": (10, 18, 35),
        "ELECTRICAL": (5, 10, 21),
        "PLUMBING": (5, 10, 21),
        "MECHANICAL": (5, 12, 24),
        "SIGN": (7, 14, 30),
        "SHORT_TERM_RENTAL": (14, 30, 60),
        "OTHER": (14, 30, 60),
    }
    low, mid, high = defaults.get(permit_type, (14, 30, 60))
    return {
        "estimated_days_low": low,
        "estimated_days_mid": mid,
        "estimated_days_high": high,
    }


def _type_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if df.empty or "permit_type" not in df.columns:
        return rows

    work = df.copy()
    work["_days"] = [
        _calendar_days(a, b)
        for a, b in zip(work.get("application_date"), work.get("approval_date"))
    ]
    for ptype, grp in work.groupby(work["permit_type"].astype(str)):
        days = pd.Series(
            [d for d in grp["_days"] if d is not None and not (isinstance(d, float) and pd.isna(d))],
            dtype=float,
        )
        statuses = grp["status"].astype(str).str.upper()
        approved_like = int(statuses.isin({"APPROVED", "CLOSED", "INSPECTIONS"}).sum())
        total = len(grp)
        open_n = int(statuses.isin(_OPEN_STATUSES).sum())
        rows.append({
            "permit_type": ptype,
            "label": _TYPE_LABELS.get(ptype, ptype.replace("_", " ").title()),
            "approval_body": _APPROVAL_BODY.get(ptype, "Inspectional Services (ISD)"),
            "sample_size": int(total),
            "issued_sample_size": int(len(days)),
            "open_count": open_n,
            "avg_days": round(float(days.mean()), 1) if len(days) else None,
            "median_days": round(float(days.median()), 1) if len(days) else None,
            "p25_days": _percentile(days, 0.25),
            "p75_days": _percentile(days, 0.75),
            "min_days": int(days.min()) if len(days) and pd.notna(days.min()) else None,
            "max_days": int(days.max()) if len(days) and pd.notna(days.max()) else None,
            "approval_rate_pct": round(100.0 * approved_like / total, 1) if total else None,
            "source": "gold_permits",
        })
    rows.sort(key=lambda r: (-(r["issued_sample_size"] or 0), r["label"]))
    return rows


def _month_extremes(df: pd.DataFrame) -> dict[str, Any]:
    work = df.copy()
    work["_days"] = [
        _calendar_days(a, b)
        for a, b in zip(work.get("application_date"), work.get("approval_date"))
    ]
    work = work[work["_days"].notna()].copy()
    if work.empty:
        return {"fastest_month": None, "slowest_month": None, "by_month": []}
    work["_month"] = pd.to_datetime(
        work["application_date"], utc=True, errors="coerce",
    ).dt.month_name()
    by_m = (
        work.groupby("_month", dropna=True)["_days"]
        .agg(["median", "count"])
        .reset_index()
    )
    by_m = by_m[by_m["count"] >= 1]
    if by_m.empty:
        return {"fastest_month": None, "slowest_month": None, "by_month": []}
    fastest = by_m.loc[by_m["median"].idxmin()]
    slowest = by_m.loc[by_m["median"].idxmax()]
    return {
        "fastest_month": str(fastest["_month"]),
        "slowest_month": str(slowest["_month"]),
        "by_month": [
            {
                "month": str(r["_month"]),
                "median_days": round(float(r["median"]), 1),
                "count": int(r["count"]),
            }
            for _, r in by_m.iterrows()
        ],
    }


def _recent_decisions(df: pd.DataFrame, limit: int = 25) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        md = _parse_metadata(row.get("metadata"))
        days = _calendar_days(row.get("application_date"), row.get("approval_date"))
        app = str(row.get("application_date") or "")[:10] or None
        appr = str(row.get("approval_date") or "")[:10] or None
        ptype = str(row.get("permit_type") or "OTHER")
        rows.append({
            "permit_number": row.get("permit_number"),
            "permit_type": ptype,
            "permit_type_label": _TYPE_LABELS.get(ptype, ptype),
            "approval_body": _APPROVAL_BODY.get(ptype, "ISD"),
            "application_date": app,
            "decision_date": appr,
            "calendar_days": days,
            "outcome": str(row.get("status") or ""),
            "address": md.get("address") or "—",
            "parcel_id": md.get("parcel_id"),
            "description": md.get("description"),
            "estimated_value": row.get("estimated_value"),
        })
    rows.sort(key=lambda r: r.get("application_date") or "", reverse=True)
    return rows[:limit]


def _board_rows(town_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    section = (town_cfg.get("permit_timeline") or {}).get("board_estimates") or {}
    out: list[dict[str, Any]] = []
    for key in ("SITE_PLAN_REVIEW", "ZBA_SPECIAL_PERMIT", "CONSERVATION"):
        base = dict(_BOARD_ESTIMATES[key])
        override = section.get(key) or {}
        base.update({k: override[k] for k in override if override[k] is not None})
        mid = base.get("estimated_days_mid")
        out.append({
            "permit_type": key,
            "label": _TYPE_LABELS[key],
            "approval_body": _APPROVAL_BODY[key],
            "sample_size": 0,
            "issued_sample_size": 0,
            "open_count": 0,
            "avg_days": mid,
            "median_days": mid,
            "p25_days": base.get("estimated_days_low"),
            "p75_days": base.get("estimated_days_high"),
            "min_days": base.get("estimated_days_low"),
            "max_days": base.get("estimated_days_high"),
            "approval_rate_pct": base.get("approval_rate_pct"),
            "estimated_days_low": base.get("estimated_days_low"),
            "estimated_days_mid": mid,
            "estimated_days_high": base.get("estimated_days_high"),
            "confidence": "low",
            "note": base.get("note"),
            "source": "town_board_estimate",
        })
    return out


def _key_permits_table(
    type_stats: list[dict[str, Any]],
    town_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    by_type = {r["permit_type"]: r for r in type_stats}
    board = {r["permit_type"]: r for r in _board_rows(town_cfg)}
    rows: list[dict[str, Any]] = []

    for key in _KEY_PERMIT_ORDER:
        if key in board:
            rows.append(board[key])
            continue
        if key in by_type:
            r = dict(by_type[key])
            med = r.get("median_days")
            p25 = r.get("p25_days")
            p75 = r.get("p75_days")
            n = r.get("issued_sample_size") or 0
            if med is not None and n >= 1:
                if n >= 2 and p25 is not None and p75 is not None:
                    low = int(round(p25))
                    high = int(round(p75))
                else:
                    # Single issued sample — show mid ± modest band for planning
                    low = max(1, int(round(med * 0.75)))
                    high = int(round(med * 1.35))
                r["estimated_days_low"] = low
                r["estimated_days_high"] = high
                r["estimated_days_mid"] = med
                r["confidence"] = "high" if n >= 5 else ("medium" if n >= 2 else "low")
                r["note"] = (
                    f"Median {med} days filed→issued from {n} Gold permit(s) "
                    f"({r.get('sample_size')} total records of this type)."
                )
            else:
                fallback = _fallback_estimate(key)
                r.update(fallback)
                r["confidence"] = "low"
                r["note"] = (
                    f"{r.get('sample_size', 0)} Gold record(s) of this type — none with both "
                    "application and approval dates yet. Range shown is category fallback."
                )
                r["source"] = "category_fallback"
            rows.append(r)
            continue

        fallback = _fallback_estimate(key)
        rows.append({
            "permit_type": key,
            "label": _TYPE_LABELS.get(key, key),
            "approval_body": _APPROVAL_BODY.get(key, "ISD"),
            "sample_size": 0,
            "issued_sample_size": 0,
            "open_count": 0,
            "avg_days": fallback["estimated_days_mid"],
            "median_days": fallback["estimated_days_mid"],
            "p25_days": fallback["estimated_days_low"],
            "p75_days": fallback["estimated_days_high"],
            "min_days": fallback["estimated_days_low"],
            "max_days": fallback["estimated_days_high"],
            "approval_rate_pct": None,
            **fallback,
            "confidence": "low",
            "note": "No Gold permits of this type in current town ledger — category fallback.",
            "source": "category_fallback",
        })

    return rows


def _summary_from_stats(
    type_stats: list[dict[str, Any]],
    months: dict[str, Any],
    total: int,
    open_n: int,
) -> dict[str, Any]:
    def _med_for(*types: str) -> float | None:
        for t in types:
            for r in type_stats:
                if r["permit_type"] == t and r.get("median_days") is not None:
                    return r["median_days"]
        return None

    return {
        "total_permits": total,
        "open_permits": open_n,
        "closed_or_issued": total - open_n,
        "avg_days_residential_reno": _med_for("RESIDENTIAL_RENO"),
        "avg_days_new_construction": _med_for("RESIDENTIAL_NEW"),
        "avg_days_commercial": _med_for("COMMERCIAL_BUILD"),
        "avg_days_zba_special_permit": _BOARD_ESTIMATES["ZBA_SPECIAL_PERMIT"][
            "estimated_days_mid"
        ],
        "approval_rate_zba": (
            f"{_BOARD_ESTIMATES['ZBA_SPECIAL_PERMIT']['approval_rate_pct']:.0f}%"
        ),
        "fastest_month": months.get("fastest_month"),
        "slowest_month": months.get("slowest_month"),
        "types_with_velocity": sum(
            1 for r in type_stats if r.get("issued_sample_size")
        ),
    }


def _parcel_context(
    town_slug: str,
    parcel_id: str | None,
    address: str | None,
    key_permits: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not parcel_id or parcel_id.startswith("_"):
        return None
    permits = get_parcel_permits(town_slug, parcel_id, address or "")
    by_type = {r["permit_type"]: r for r in key_permits}
    path: list[dict[str, Any]] = []
    for key in ("ZBA_SPECIAL_PERMIT", "SITE_PLAN_REVIEW", "RESIDENTIAL_NEW"):
        r = by_type.get(key)
        if not r:
            continue
        path.append({
            "step": r["label"],
            "body": r["approval_body"],
            "estimated_days_low": r.get("estimated_days_low"),
            "estimated_days_high": r.get("estimated_days_high"),
            "estimated_days_mid": r.get("median_days") or r.get("estimated_days_mid"),
            "optional": key in ("ZBA_SPECIAL_PERMIT", "SITE_PLAN_REVIEW"),
            "note": (
                "Include if special permit / site plan required for your regime."
                if key != "RESIDENTIAL_NEW"
                else "ISD building permit — filed→issued from town Gold where available."
            ),
        })

    return {
        "parcel_id": parcel_id,
        "address": address,
        "parcel_permit_count": len(permits),
        "parcel_permits": permits[:15],
        "suggested_path": path,
    }


def generate_permit_timeline(
    town_slug: str,
    parcel_id: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    town_name = get_town_display_name(town_slug)
    town_cfg = _load_town_cfg(town_slug)
    df = _permits_frame(town_slug)

    if df.empty:
        return {
            "report_type": "permit-timeline",
            "town_slug": town_slug,
            "town_name": town_name,
            "prepared_on": date.today().isoformat(),
            "summary_stats": {},
            "type_stats": [],
            "key_permits": _key_permits_table([], town_cfg),
            "recent_decisions": [],
            "parcel_context": None,
            "data_sources": ["permits.parquet (missing)"],
            "pilot_message": (
                f"No permits.parquet found for {town_slug}. "
                "Showing category fallback timelines only."
            ),
            "fallback": True,
        }

    statuses = df["status"].astype(str).str.upper()
    open_n = int(statuses.isin(_OPEN_STATUSES).sum())
    type_stats = _type_stats(df)
    months = _month_extremes(df)
    key_permits = _key_permits_table(type_stats, town_cfg)
    decisions = _recent_decisions(df)
    summary = _summary_from_stats(type_stats, months, len(df), open_n)
    parcel_ctx = _parcel_context(town_slug, parcel_id, address, key_permits)
    gold_with_dates = sum(1 for r in type_stats if (r.get("issued_sample_size") or 0) > 0)

    return {
        "report_type": "permit-timeline",
        "town_slug": town_slug,
        "town_name": town_name,
        "prepared_on": date.today().isoformat(),
        "summary_stats": summary,
        "type_stats": type_stats,
        "key_permits": key_permits,
        "recent_decisions": decisions,
        "month_extremes": months,
        "parcel_context": parcel_ctx,
        "data_sources": [
            f"TownEye Gold permits.parquet ({len(df)} records)",
            "Filed→issued calendar days from application_date → approval_date",
            "Board paths (ZBA / Site Plan / Conservation): town estimate until board docket ingest",
        ],
        "pilot_message": (
            f"Velocity computed from {len(df)} Gold permits "
            f"({gold_with_dates} types with issued dates). "
            "ZBA / Planning / Conservation timelines are estimates — "
            "ISD ledger does not include board dockets."
        ),
        "fallback": False,
    }


def permit_timeline_to_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["--- PERMIT TIMELINE INTELLIGENCE ---"])
    writer.writerow(["Town", payload.get("town_name")])
    writer.writerow(["Prepared", payload.get("prepared_on")])
    writer.writerow([])

    writer.writerow(["--- KEY PERMIT TIMELINE ESTIMATES ---"])
    writer.writerow([
        "Permit", "Body", "Est. Low (days)", "Est. Mid/Median", "Est. High (days)",
        "Sample (issued)", "Confidence", "Source", "Note",
    ])
    for r in payload.get("key_permits") or []:
        writer.writerow([
            r.get("label", ""),
            r.get("approval_body", ""),
            r.get("estimated_days_low", ""),
            r.get("median_days") or r.get("estimated_days_mid", ""),
            r.get("estimated_days_high", ""),
            r.get("issued_sample_size", ""),
            r.get("confidence", ""),
            r.get("source", ""),
            r.get("note", ""),
        ])
    writer.writerow([])

    writer.writerow(["--- RECENT DECISIONS (GOLD) ---"])
    writer.writerow([
        "Permit #", "Type", "Body", "Application", "Decision", "Days", "Status", "Address",
    ])
    for p in payload.get("recent_decisions") or []:
        writer.writerow([
            p.get("permit_number", ""),
            p.get("permit_type_label") or p.get("permit_type", ""),
            p.get("approval_body", ""),
            p.get("application_date", ""),
            p.get("decision_date", ""),
            p.get("calendar_days", ""),
            p.get("outcome", ""),
            p.get("address", ""),
        ])
    return buf.getvalue()


def _fmt_days(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value)))} days"
    except (TypeError, ValueError):
        return "—"


def _fmt_range(low: Any, mid: Any, high: Any) -> str:
    if mid is None and low is None and high is None:
        return "—"
    if low is not None and high is not None:
        mid_s = "—" if mid is None else str(int(round(float(mid))))
        return f"{int(round(float(low)))}–{int(round(float(high)))} days (mid {mid_s})"
    return _fmt_days(mid)


def render_permit_timeline_html(payload: dict[str, Any]) -> str:
    town = payload.get("town_name", "Town")
    prepared = payload.get("prepared_on", date.today().isoformat())
    stats = payload.get("summary_stats") or {}
    key_permits = payload.get("key_permits") or []
    decisions = payload.get("recent_decisions") or []
    sources = payload.get("data_sources") or []
    parcel_ctx = payload.get("parcel_context")

    csv_b64 = base64.b64encode(permit_timeline_to_csv(payload).encode("utf-8")).decode("ascii")
    csv_href = f"data:text/csv;base64,{csv_b64}"

    key_rows = ""
    for r in key_permits:
        conf = r.get("confidence") or "—"
        key_rows += f"""<tr>
          <td><strong>{r.get('label', '—')}</strong><div class="small">{r.get('permit_type', '')}</div></td>
          <td>{r.get('approval_body', '—')}</td>
          <td class="num">{_fmt_range(r.get('estimated_days_low'), r.get('median_days') or r.get('estimated_days_mid'), r.get('estimated_days_high'))}</td>
          <td class="num">{r.get('issued_sample_size', 0)}</td>
          <td>{conf}</td>
          <td class="small">{r.get('note', '')}</td>
        </tr>"""

    decision_rows = ""
    for p in decisions:
        outcome = str(p.get("outcome") or "")
        cls = (
            "ok" if outcome in ("APPROVED", "CLOSED", "INSPECTIONS")
            else ("wn" if outcome in ("SUBMITTED", "UNDER_REVIEW") else "fl")
        )
        days = p.get("calendar_days")
        decision_rows += f"""<tr>
          <td class="num">{p.get('permit_number') or '—'}</td>
          <td>{p.get('permit_type_label') or p.get('permit_type') or '—'}</td>
          <td class="num">{p.get('application_date') or '—'}</td>
          <td class="num">{p.get('decision_date') or '—'}</td>
          <td class="num"><strong>{days if days is not None else '—'}</strong></td>
          <td><span class="{cls}">{outcome or '—'}</span></td>
          <td>{p.get('address') or '—'}</td>
        </tr>"""

    parcel_block = ""
    if parcel_ctx:
        path_rows = ""
        for s in parcel_ctx.get("suggested_path") or []:
            opt = " (if required)" if s.get("optional") else ""
            path_rows += f"""<tr>
              <td>{s.get('step')}{opt}</td>
              <td>{s.get('body')}</td>
              <td class="num">{_fmt_range(s.get('estimated_days_low'), s.get('estimated_days_mid'), s.get('estimated_days_high'))}</td>
              <td class="small">{s.get('note', '')}</td>
            </tr>"""
        parcel_block = f"""
<h2>4 · Parcel Context — {parcel_ctx.get('address') or parcel_ctx.get('parcel_id')}</h2>
<p class="small">{parcel_ctx.get('parcel_permit_count', 0)} permit(s) matched to this parcel in Gold.</p>
<table>
<tr><th>Path step</th><th>Body</th><th>Estimated duration</th><th>Note</th></tr>
{path_rows or "<tr><td colspan='4'>No path estimate</td></tr>"}
</table>
"""

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
  .small{{font-size:11px;color:#555}}
  .note{{font-size:12px;color:#555;font-style:italic;margin:8px 0}}
  .btn{{display:inline-block;margin:8px 0 12px;padding:8px 14px;background:#0b2545;color:#fff;text-decoration:none;border-radius:4px;font-size:12px}}
  .ok{{color:#1a7a1a;font-weight:bold}}
  .wn{{color:#a06b00;font-weight:bold}}
  .fl{{color:#a02020;font-weight:bold}}
  .logo-header {{ position: absolute; top: 20px; right: 28px; height: 32px; opacity: 0.8; }}
  .footnote{{font-size:10.5px;color:#555;margin-top:16px;border-top:1px solid #ddd;padding-top:10px}}
</style></head><body>

<div class="hd" style="position: relative;">
  <img src="https://demo.towneye.ai/logo.png" alt="TownEye Logo" class="logo-header" />
  <h1>Permit Timeline Intelligence</h1>
  <div style="font-size:15px;color:#0b2545;font-weight:bold">{town}, MA</div>
  <div class="meta">Prepared on {prepared} &nbsp;·&nbsp; {stats.get('total_permits', 0)} Gold permits</div>
</div>

<p class="note">{payload.get("pilot_message", "")}</p>
<a class="btn" href="{csv_href}" download="permit-timeline-{payload.get('town_slug', 'town')}.csv">Download Report (CSV)</a>

<h2>1 · Town Velocity Snapshot</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Gold permits (ledger)</td><td class="num">{stats.get('total_permits', 0)} total · {stats.get('open_permits', 0)} open</td></tr>
  <tr><td>Median filed→issued — Residential reno</td><td class="num">{_fmt_days(stats.get('avg_days_residential_reno'))}</td></tr>
  <tr><td>Median filed→issued — New construction</td><td class="num">{_fmt_days(stats.get('avg_days_new_construction'))}</td></tr>
  <tr><td>Median filed→issued — Commercial</td><td class="num">{_fmt_days(stats.get('avg_days_commercial'))}</td></tr>
  <tr><td>ZBA special permit (board estimate)</td><td class="num">{_fmt_days(stats.get('avg_days_zba_special_permit'))} · approval rate {stats.get('approval_rate_zba', '—')}</td></tr>
  <tr><td>Fastest / slowest filing month</td><td>{stats.get('fastest_month') or '—'} / {stats.get('slowest_month') or '—'}</td></tr>
</table>

<h2>2 · Key Permit Timeline Estimates</h2>
<p class="small">Use this table for carry planning. ISD rows are from Gold application_date→approval_date. Board rows are labeled estimates.</p>
<table>
<tr><th>Permit / path</th><th>Body</th><th>Estimated duration</th><th>Issued n</th><th>Confidence</th><th>Note</th></tr>
{key_rows or "<tr><td colspan='6'>No estimates</td></tr>"}
</table>

<h2>3 · Recent Decisions (Gold ledger)</h2>
<table>
<tr><th>Permit #</th><th>Type</th><th>Filed</th><th>Issued</th><th>Days</th><th>Status</th><th>Address</th></tr>
{decision_rows or "<tr><td colspan='7'>No permits in Gold</td></tr>"}
</table>

{parcel_block}

<p class="footnote">
  Sources: {', '.join(sources) if sources else 'TownEye Gold'}.
  Filed→issued days exclude open applications without approval_date.
  Board timelines are indicative until ZBA/Planning minutes are ingested.
  Not a guarantee of municipal processing time.
</p>
</body></html>"""
