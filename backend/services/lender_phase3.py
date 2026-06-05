"""Phase 3 lender collateral — tax, registry, violations, assessor comps."""

from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd

import re as _re

from backend.config import get_settings
from core.spatial import haversine_ft
from reports.buildability_brief import BriefData

_ADDR_STOPWORDS = frozenset({
    "ST", "STREET", "RD", "ROAD", "AVE", "AVENUE", "DR", "DRIVE",
    "LN", "LANE", "CT", "COURT", "PL", "PLACE", "MA", "UNIT",
})


def _gold_parquet(town_slug: str, domain: str):
    return get_settings().gold_data_path / town_slug / f"{domain}.parquet"


def _lender_cfg(town_cfg: dict[str, Any]) -> dict[str, Any]:
    block = town_cfg.get("lender_report")
    return block if isinstance(block, dict) else {}


def _source_slugs(town_cfg: dict[str, Any], *keys: str) -> list[str]:
    mappings = town_cfg.get("source_mappings") or {}
    return [str(mappings[k]) for k in keys if mappings.get(k)]


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_addr(value: str | None) -> str:
    if not value:
        return ""
    return _re.sub(r"\s+", " ", value.upper().strip())


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_date(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return "—"
        return ts.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(value)


def _street_tokens(address: str | None, town_cfg: dict[str, Any]) -> set[str]:
    if not address:
        return set()
    tokens = set()
    for part in _re.sub(r"[^\w\s]", " ", address.upper()).split():
        if len(part) > 2 and part not in _ADDR_STOPWORDS:
            tokens.add(part)
    aliases = _lender_cfg(town_cfg).get("infra_street_aliases") or {}
    if isinstance(aliases, dict):
        for key, values in aliases.items():
            key_up = str(key).upper()
            if key_up in tokens or any(str(v).upper() in _normalize_addr(address) for v in values):
                tokens.add(key_up)
                tokens.update(str(v).upper() for v in values if v)
    return tokens

_ACTIVE_LIEN_STATUSES = frozenset({"ACTIVE", "OPEN", "RECORDED", "PENDING"})
_OPEN_VIOLATION_STATUSES = frozenset({"OPEN", "ACTIVE", "UNDER_REVIEW", "ISSUED", "ACKNOWLEDGED"})
_TAX_DELINQUENT_STATUSES = frozenset({"DELINQUENT", "PAST_DUE", "LIEN", "TAX_TITLE"})


def _cfg_records(town_cfg: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = _lender_cfg(town_cfg).get(key) or []
    return [r for r in rows if isinstance(r, dict)]


def _load_domain_records(
    town_slug: str,
    domain: str,
    town_cfg: dict[str, Any],
    cfg_key: str,
    parcel_field: str = "parcel_id",
) -> list[dict[str, Any]]:
    path = _gold_parquet(town_slug, domain)
    if path.is_file():
        df = pd.read_parquet(path)
        if not df.empty:
            return [
                {**{k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()},
                 **(_ensure_dict(row.get("metadata")) if "metadata" in row else {})}
                for _, row in df.iterrows()
            ]
    return _cfg_records(town_cfg, cfg_key)


def _filter_parcel_records(
    records: list[dict[str, Any]],
    parcel_id: str,
    parcel_field: str = "parcel_id",
) -> list[dict[str, Any]]:
    return [r for r in records if str(r.get(parcel_field) or "") == parcel_id]


def _property_tax_records(
    data: BriefData,
    town_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    town_slug = data.inputs.town_slug
    parcel_id = data.inputs.parcel_id
    ic = _lender_cfg(town_cfg).get("invoice_cloud") or {}
    if isinstance(ic, dict) and ic.get("enabled"):
        try:
            from backend.services.invoice_cloud_client import fetch_and_cache_property_tax

            live = fetch_and_cache_property_tax(
                town_slug,
                town_cfg,
                parcel_id,
                data.parcel.address,
            )
            if live:
                return live
        except Exception:
            pass
    return _load_domain_records(
        town_slug, "property-tax", town_cfg, "property_tax_records",
    )


def _analyze_property_tax(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    parcel_id = data.inputs.parcel_id
    records = _property_tax_records(data, town_cfg)
    hits = _filter_parcel_records(records, parcel_id)
    portal = ""
    try:
        from backend.services.invoice_cloud_client import portal_url

        portal = portal_url(town_cfg)
    except Exception:
        portal = ""
    if not portal:
        portal = _lender_cfg(town_cfg).get("property_tax_portal_url") or ""

    if not hits:
        return {
            "status": "caution",
            "note": (
                "No property tax payment record matched this parcel. "
                "Confirm current/tax-lien status with the town collector or Invoice Cloud portal."
            ),
            "rows": [],
            "portal_url": portal,
            "sources": _source_slugs(town_cfg, "property_tax") or ["invoice-cloud"],
        }

    rows = []
    delinquent = False
    for rec in hits:
        status = str(rec.get("status") or rec.get("payment_status") or "UNKNOWN").upper()
        balance = rec.get("balance_due") or rec.get("amount_due")
        if status in _TAX_DELINQUENT_STATUSES or (balance is not None and float(balance) > 0
                                                   and status not in {"CURRENT", "PAID"}):
            delinquent = True
        rows.append({
            "fiscal_year": str(rec.get("fiscal_year") or "—"),
            "status": status,
            "balance_due": _fmt_money(balance),
            "due_date": _fmt_date(rec.get("due_date")),
            "last_payment": _fmt_date(rec.get("last_payment_date")),
            "bill_type": str(rec.get("bill_type") or "Real estate"),
        })

    if delinquent:
        status = "flagged"
        note = "Delinquent or unpaid property tax balance on record — title / escrow review required."
    else:
        status = "clear"
        note = "Property tax account shows current/paid status for matched fiscal year(s)."

    return {
        "status": status,
        "note": note,
        "rows": rows,
        "portal_url": portal,
        "sources": _source_slugs(town_cfg, "property_tax") or ["invoice-cloud"],
    }


def _analyze_registry(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    parcel_id = data.inputs.parcel_id
    records = _load_domain_records(
        data.inputs.town_slug, "registry-records", town_cfg, "registry_records",
    )
    hits = _filter_parcel_records(records, parcel_id)
    search_url = _lender_cfg(town_cfg).get("registry_search_url") or ""

    if not hits:
        return {
            "status": "caution",
            "note": (
                "No registry mortgage/lien records matched this parcel in TownEye Gold. "
                "Run a full Middlesex South Registry search before closing."
            ),
            "rows": [],
            "active_liens": 0,
            "search_url": search_url,
            "sources": _source_slugs(town_cfg, "registry") or ["mass-land-records"],
        }

    rows = []
    active = 0
    for rec in hits:
        rstatus = str(rec.get("status") or "RECORDED").upper()
        rtype = str(rec.get("record_type") or rec.get("instrument_type") or "—")
        if rstatus in _ACTIVE_LIEN_STATUSES and rtype.upper() not in {"DISCHARGE", "RELEASE"}:
            active += 1
        rows.append({
            "record_type": rtype,
            "status": rstatus,
            "recording_date": _fmt_date(rec.get("recording_date")),
            "amount": _fmt_money(rec.get("amount")),
            "book_page": str(rec.get("book_page") or "—"),
            "grantee": str(rec.get("grantee") or "—"),
            "grantor": str(rec.get("grantor") or "—"),
        })

    if active > 0:
        status = "caution"
        note = f"{active} active registry instrument(s) on record — verify priority and subordination with title."
    else:
        status = "clear"
        note = "Matched registry instruments are releases/discharges or inactive — no active lien flags in dataset."

    return {
        "status": status,
        "note": note,
        "rows": rows,
        "active_liens": active,
        "search_url": search_url,
        "sources": _source_slugs(town_cfg, "registry") or ["mass-land-records"],
    }


def _violation_matches(
    text: str,
    address: str | None,
    tokens: set[str],
) -> bool:
    if not text:
        return False
    upper = text.upper()
    if address and _normalize_addr(address) in _normalize_addr(upper):
        return True
    num = _re.search(r"^\d+", _normalize_addr(address or ""))
    if num and num.group(0) in upper:
        return any(t in upper for t in tokens)
    return any(t in upper for t in tokens)


def _analyze_violations(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    parcel_id = data.inputs.parcel_id
    address = data.parcel.address
    tokens = _street_tokens(address, town_cfg)

    rows: list[dict[str, str]] = []

    cfg_hits = _filter_parcel_records(
        _cfg_records(town_cfg, "code_violation_records"), parcel_id,
    )
    for rec in cfg_hits:
        rows.append({
            "source": str(rec.get("source") or "town-isd"),
            "violation_type": str(rec.get("violation_type") or "—"),
            "status": str(rec.get("status") or "—"),
            "opened": _fmt_date(rec.get("opened_date")),
            "detail": str(rec.get("detail") or rec.get("description") or "—")[:120],
        })

    path = _gold_parquet(data.inputs.town_slug, "311")
    if path.is_file():
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            if str(row.get("event_type") or "") not in ("311_REQUEST", ""):
                continue
            meta = _ensure_dict(row.get("metadata"))
            blob = " ".join(
                str(x) for x in (
                    row.get("event_name"),
                    row.get("description"),
                    meta.get("address"),
                    meta.get("summary"),
                ) if x
            )
            if not _violation_matches(blob, address, tokens):
                continue
            status = str(meta.get("status") or row.get("status") or "Open")
            rows.append({
                "source": "311-seeclickfix",
                "violation_type": str(row.get("event_name") or "311 request"),
                "status": status,
                "opened": _fmt_date(row.get("start_time")),
                "detail": str(row.get("description") or meta.get("description") or "—")[:120],
            })

    cv_path = _gold_parquet(data.inputs.town_slug, "code-violations")
    if cv_path.is_file():
        for rec in _filter_parcel_records(
            [
                {**{k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()},
                 **_ensure_dict(row.get("metadata"))}
                for _, row in pd.read_parquet(cv_path).iterrows()
            ],
            parcel_id,
        ):
            rows.append({
                "source": str(rec.get("te_source") or "code-violations"),
                "violation_type": str(rec.get("violation_type") or "—"),
                "status": str(rec.get("status") or "—"),
                "opened": _fmt_date(rec.get("opened_date")),
                "detail": str(rec.get("detail") or rec.get("description") or "—")[:120],
            })

    open_count = sum(
        1 for r in rows
        if str(r.get("status") or "").upper() in _OPEN_VIOLATION_STATUSES
    )

    if not rows:
        return {
            "status": "clear",
            "note": "No open code violations or 311 housing-order matches for this parcel.",
            "rows": [],
            "open_count": 0,
            "isd_url": _lender_cfg(town_cfg).get("isd_portal_url") or "",
            "sources": _source_slugs(town_cfg, "311-seeclickfix", "permits") or ["311", "town-isd"],
        }

    if open_count:
        status = "flagged" if any("HOUSING" in r["violation_type"].upper() for r in rows) else "caution"
        note = f"{open_count} open violation / service request(s) — confirm ISD orders and cure requirements."
    else:
        status = "clear"
        note = f"{len(rows)} historical violation/311 record(s); none open."

    return {
        "status": status,
        "note": note,
        "rows": rows,
        "open_count": open_count,
        "isd_url": _lender_cfg(town_cfg).get("isd_portal_url") or "",
        "sources": _source_slugs(town_cfg, "311-seeclickfix", "permits") or ["311", "town-isd"],
    }


def _sale_from_property_row(row: pd.Series) -> tuple[float | None, str | None, float | None]:
    meta = _ensure_dict(row.get("metadata"))
    price = meta.get("last_sale_price") or row.get("last_sale_price")
    if price is None or (isinstance(price, float) and math.isnan(price)):
        return None, None, None
    try:
        price_f = float(price)
    except (TypeError, ValueError):
        return None, None, None
    if price_f <= 0 or price_f < 1000:
        return None, None, None
    sf = meta.get("finished_area_sqft") or meta.get("finished_area_sqft_l3") or row.get("finished_area_sqft")
    try:
        sf_f = float(sf) if sf is not None and not pd.isna(sf) else None
    except (TypeError, ValueError):
        sf_f = None
    sale_date = meta.get("last_sale_date") or row.get("last_sale_date")
    return price_f, str(sale_date) if sale_date else None, sf_f


def _analyze_sale_comps(data: BriefData, town_cfg: dict[str, Any]) -> dict[str, Any]:
    cfg = _lender_cfg(town_cfg)
    radius_mi = float(cfg.get("comps_radius_mi", 0.25))
    max_comps = int(cfg.get("comps_max", 8))
    radius_ft = radius_mi * 5280.0

    town_slug = data.inputs.town_slug
    subject_id = data.inputs.parcel_id
    lat = data.parcel.centroid_lat
    lon = data.parcel.centroid_lon

    parcel_path = _gold_parquet(town_slug, "parcel")
    property_path = _gold_parquet(town_slug, "property")
    if not parcel_path.is_file() or not property_path.is_file():
        return {
            "status": "caution",
            "note": "Parcel/property Gold data unavailable for comparable sales search.",
            "rows": [],
            "radius_mi": radius_mi,
            "median_ppsf": None,
            "sources": ["property.parquet", "parcel.parquet"],
        }

    parcels = pd.read_parquet(parcel_path, columns=["parcel_id", "centroid_lat", "centroid_lon", "address"])
    props = pd.read_parquet(property_path)

    if "metadata" in props.columns:
        props["metadata"] = props["metadata"].apply(_ensure_dict)

    merged = parcels.merge(
        props[["parcel_id", "assessed_value", "metadata", "year_built"]],
        on="parcel_id",
        how="inner",
    )

    comps: list[dict[str, Any]] = []
    subject_point = (lon, lat)

    for _, row in merged.iterrows():
        pid = str(row["parcel_id"])
        if pid == subject_id:
            continue
        plat = row.get("centroid_lat")
        plon = row.get("centroid_lon")
        if plat is None or plon is None or pd.isna(plat) or pd.isna(plon):
            continue
        dist_ft = haversine_ft(subject_point, (float(plon), float(plat)))
        if dist_ft > radius_ft:
            continue
        price, sale_date, sf = _sale_from_property_row(row)
        if price is None:
            continue
        ppsf = (price / sf) if sf and sf > 0 else None
        comps.append({
            "parcel_id": pid,
            "address": str(row.get("address") or "—"),
            "distance_ft": round(dist_ft, 0),
            "sale_price": price,
            "sale_date": sale_date or "—",
            "finished_sf": sf,
            "price_per_sf": ppsf,
            "year_built": row.get("year_built"),
        })

    comps.sort(key=lambda c: c["distance_ft"])
    comps = comps[:max_comps]

    ppsf_vals = [c["price_per_sf"] for c in comps if c["price_per_sf"]]
    median_ppsf = float(pd.Series(ppsf_vals).median()) if ppsf_vals else None

    if not comps:
        status = "caution"
        note = (
            f"No assessor-recorded arm's-length sales within {radius_mi} mi in Gold data. "
            "MLS comp pull not yet connected — use appraiser comps."
        )
    else:
        status = "clear"
        note = (
            f"{len(comps)} comparable sale(s) from assessor/CAMA transfer records within "
            f"{radius_mi} mi (not MLS — verify with deed registry)."
        )

    return {
        "status": status,
        "note": note,
        "rows": comps,
        "radius_mi": radius_mi,
        "median_ppsf": median_ppsf,
        "sources": ["property.parquet", "parcel.parquet", "massgis-l3-cama"],
    }
