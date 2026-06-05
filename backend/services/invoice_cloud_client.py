"""Live Invoice Cloud guest lookup for property tax payment status."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from backend.config import get_settings
from core.storage import get_parquet_path, save_gold_data

logger = logging.getLogger(__name__)

_MONEY_RE = re.compile(r"\$[\d,]+\.?\d*")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
)
_DELINQUENT_WORDS = frozenset({
    "DELINQUENT", "PAST DUE", "PAST_DUE", "UNPAID", "OVERDUE", "LIEN",
})
_PAID_WORDS = frozenset({"PAID", "CURRENT", "CLOSED", "SATISFIED"})


def _lender_cfg(town_cfg: dict[str, Any]) -> dict[str, Any]:
    block = town_cfg.get("lender_report")
    return block if isinstance(block, dict) else {}


def _ic_cfg(town_cfg: dict[str, Any]) -> dict[str, Any]:
    block = _lender_cfg(town_cfg).get("invoice_cloud")
    return block if isinstance(block, dict) else {}


def _gold_tax_path(town_slug: str):
    return get_settings().gold_data_path / town_slug / "property-tax.parquet"


def _parse_money(text: str) -> float | None:
    m = _MONEY_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _parse_date(text: str) -> str | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    raw = m.group(0)
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _infer_status(balance: float | None, text: str) -> str:
    upper = (text or "").upper()
    if any(w in upper for w in _DELINQUENT_WORDS):
        return "DELINQUENT"
    if balance is not None and balance > 0.009:
        if any(w in upper for w in _PAID_WORDS):
            return "OPEN"
        return "PAST_DUE"
    if any(w in upper for w in _PAID_WORDS):
        return "CURRENT"
    if balance is not None and balance <= 0.009:
        return "CURRENT"
    return "UNKNOWN"


def _hidden_fields(soup: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for inp in soup.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        if name:
            out[name] = inp.get("value") or ""
    return out


def _locator_field_name(soup: BeautifulSoup, lookup_mode: str) -> str | None:
    want = "parcel" if lookup_mode == "parcel_id" else "service address"
    for inp in soup.find_all("input"):
        if (inp.get("type") or "text").lower() not in {"text", "search", "tel"}:
            continue
        name = inp.get("name")
        if not name:
            continue
        hint = " ".join(
            filter(
                None,
                [
                    inp.get("title") or "",
                    inp.get("placeholder") or "",
                    inp.get("id") or "",
                ],
            ),
        ).lower()
        if want in hint:
            return name
    for inp in soup.find_all("input", {"type": "text"}):
        name = inp.get("name")
        if name and "txtvalue" in name.lower():
            return name
    return None


def _postback_target(soup: BeautifulSoup) -> str | None:
    for tag in soup.find_all(["a", "button", "input"]):
        for attr in ("href", "onclick"):
            raw = tag.get(attr) or ""
            m = re.search(r"__doPostBack\(\s*'([^']+)'", raw)
            if m and re.search(r"search|locate|continue", m.group(1), re.I):
                return m.group(1).replace("&#39;", "'")
    for tag in soup.find_all(["a", "button", "input"]):
        for attr in ("href", "onclick"):
            raw = tag.get(attr) or ""
            m = re.search(r"__doPostBack\(\s*'([^']+)'", raw)
            if m:
                return m.group(1)
    return None


def _submit_button(soup: BeautifulSoup) -> tuple[str, str] | None:
    for inp in soup.find_all("input", {"type": "submit"}):
        name = inp.get("name")
        if name:
            return name, inp.get("value") or "Search"
    for btn in soup.find_all("button"):
        name = btn.get("name")
        if name:
            return name, btn.get_text(strip=True) or "Search"
    return None


def _extract_session(html: str) -> str | None:
    m = re.search(r"/portal/\(S\(([^)]+)\)\)/2", html)
    return m.group(1) if m else None


def _session_base(html: str, fallback_url: str) -> str | None:
    sess = _extract_session(html)
    if sess:
        return f"https://www.invoicecloud.com/portal/(S({sess}))/2"
    m = re.search(r"(https://www\.invoicecloud\.com/portal/\(S\([^)]+\)\)/2)", fallback_url)
    return m.group(1) if m else None


def _locator_url(base: str, ic: dict[str, Any]) -> str:
    bg = ic["biller_guid"]
    iti = ic.get("invoice_type_id", 8)
    vsii = ic.get("virtual_site_item_id", 346)
    return (
        f"{base}/customerlocator.aspx"
        f"?iti={iti}&bg={bg}&vsii={vsii}&return=1"
    )


def _follow_account_link(session: requests.Session, html: str, base: str, query: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    query_up = query.upper()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True).upper()
        if query_up in text or query_up.replace(".", "") in text.replace(".", ""):
            if "customer" in href.lower() or "account" in href.lower():
                return session.get(urljoin(base + "/", href), timeout=30).text
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(k in href for k in ("customerselected", "customerstdetail", "customeraccount")):
            return session.get(urljoin(base + "/", a["href"]), timeout=30).text
    return html


def _parse_invoice_tables(html: str, parcel_id: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, Any]] = []
    parcel_up = parcel_id.upper()

    if parcel_up not in html.upper() and parcel_up.replace(".", "") not in html.replace(".", ""):
        # Address-only searches may not echo parcel id — still parse if tables exist.
        if not soup.find("table"):
            return []

    for table in soup.find_all("table"):
        headers = [
            th.get_text(" ", strip=True).lower()
            for th in table.find_all("th")
        ]
        if not headers:
            first_row = table.find("tr")
            if first_row:
                headers = [
                    td.get_text(" ", strip=True).lower()
                    for td in first_row.find_all(["th", "td"])
                ]
        rows = table.find_all("tr")
        for tr in rows[1:] if headers else rows:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            row_text = " | ".join(cells)
            if not _MONEY_RE.search(row_text):
                continue

            balance = None
            due_date = None
            status_text = row_text
            bill_type = "Real estate"

            amount = None
            for idx, hdr in enumerate(headers):
                if idx >= len(cells):
                    break
                val = cells[idx]
                if "balance" in hdr or "amount due" in hdr:
                    balance = _parse_money(val)
                elif hdr == "amount" or hdr.startswith("amount "):
                    amount = _parse_money(val)
                if "due" in hdr:
                    due_date = _parse_date(val) or due_date
                if "status" in hdr:
                    status_text = val
                if "type" in hdr or "description" in hdr:
                    bill_type = val or bill_type

            if balance is None:
                balance = amount
            if balance is None:
                balance = _parse_money(row_text)

            status = _infer_status(balance, status_text)
            fy = None
            if due_date:
                try:
                    fy = int(due_date[:4])
                    if int(due_date[5:7]) >= 7:
                        fy += 1
                except ValueError:
                    fy = None

            records.append({
                "parcel_id": parcel_id,
                "fiscal_year": fy or datetime.now(timezone.utc).year,
                "status": status,
                "balance_due": balance if balance is not None else 0,
                "due_date": due_date,
                "last_payment_date": None,
                "bill_type": bill_type,
                "source_note": row_text[:160],
            })

    if records:
        return records

    # Summary blocks without tables
    text = soup.get_text("\n", strip=True)
    balance = _parse_money(text)
    if balance is None and not re.search(r"paid|current|no open|no balance", text, re.I):
        return []

    status = _infer_status(balance, text)
    return [{
        "parcel_id": parcel_id,
        "fiscal_year": datetime.now(timezone.utc).year,
        "status": status,
        "balance_due": balance if balance is not None else 0,
        "due_date": _parse_date(text),
        "last_payment_date": None,
        "bill_type": "Real estate",
        "source_note": text[:160],
    }]


def lookup_property_tax_live(
    town_cfg: dict[str, Any],
    parcel_id: str,
    address: str | None = None,
) -> list[dict[str, Any]]:
    """Guest lookup via Invoice Cloud customerlocator (no API key)."""
    ic = _ic_cfg(town_cfg)
    if not ic.get("enabled"):
        return []

    vanity = ic.get("vanity_url") or ""
    biller_guid = ic.get("biller_guid") or ""
    if not vanity or not biller_guid:
        logger.warning("invoice_cloud enabled but vanity_url/biller_guid missing")
        return []

    timeout = int(ic.get("request_timeout_s") or 25)
    ua = ic.get("user_agent") or (
        "Mozilla/5.0 (compatible; TownEye-UMF/1.0; +https://towneye.ai)"
    )
    lookup_mode = str(ic.get("lookup_mode") or "parcel_id").lower()
    query = parcel_id if lookup_mode == "parcel_id" else (address or parcel_id)
    if not query:
        return []

    session = requests.Session()
    session.headers["User-Agent"] = ua

    try:
        landing = session.get(vanity, timeout=timeout)
        landing.raise_for_status()
        base = _session_base(landing.text, landing.url)
        if not base:
            logger.warning("Invoice Cloud session not found for %s", vanity)
            return []

        locator_url = _locator_url(base, ic)
        loc_resp = session.get(locator_url, timeout=timeout)
        loc_resp.raise_for_status()
        soup = BeautifulSoup(loc_resp.text, "html.parser")
        field = ic.get("search_field_name") or _locator_field_name(soup, lookup_mode)
        postback = ic.get("postback_target") or _postback_target(soup)
        button = _submit_button(soup)
        if not field or (not postback and not button):
            logger.warning("Invoice Cloud locator form not found")
            return []

        data = _hidden_fields(soup)
        data[field] = query
        if postback:
            data["__EVENTTARGET"] = postback
            data["__EVENTARGUMENT"] = ""
        else:
            data[button[0]] = button[1]

        result = session.post(locator_url, data=data, timeout=timeout)
        result.raise_for_status()
        html = result.text
        base = _session_base(html, result.url) or base
        html = _follow_account_link(session, html, base, query)
        return _parse_invoice_tables(html, parcel_id)
    except requests.RequestException as exc:
        logger.warning("Invoice Cloud lookup failed: %s", exc)
        return []


def _cached_records(
    town_slug: str,
    parcel_id: str,
    ttl_hours: float,
) -> list[dict[str, Any]] | None:
    path = _gold_tax_path(town_slug)
    if not path.is_file():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    if df.empty or "parcel_id" not in df.columns:
        return None

    hits = df[df["parcel_id"].astype(str) == parcel_id]
    if hits.empty:
        return None

    if "te_timestamp" in hits.columns:
        try:
            ts = pd.Timestamp(hits["te_timestamp"].max())
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            age_h = (pd.Timestamp.now(tz="UTC") - ts).total_seconds() / 3600
            if age_h > ttl_hours:
                return None
        except (TypeError, ValueError):
            pass

    return [
        {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        for _, row in hits.iterrows()
    ]


def _upsert_cache(
    town_slug: str,
    records: list[dict[str, Any]],
    te_source: str,
) -> None:
    if not records:
        return
    path = _gold_tax_path(town_slug)
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for rec in records:
        rows.append({
            **rec,
            "te_source": te_source,
            "te_timestamp": now,
            "te_confidence": 0.85,
            "te_version": "invoice-cloud-guest-v1",
            "te_updated_by": "invoice_cloud_client",
        })

    new_df = pd.DataFrame(rows)
    if path.is_file():
        try:
            old = pd.read_parquet(path)
            if not old.empty and "parcel_id" in old.columns:
                drop_ids = {str(r.get("parcel_id")) for r in records}
                old = old[~old["parcel_id"].astype(str).isin(drop_ids)]
                new_df = pd.concat([old, new_df], ignore_index=True)
        except Exception:
            pass

    save_gold_data(new_df, town_slug, "property-tax")


def fetch_and_cache_property_tax(
    town_slug: str,
    town_cfg: dict[str, Any],
    parcel_id: str,
    address: str | None = None,
) -> list[dict[str, Any]]:
    """Return tax rows, refreshing from Invoice Cloud when cache is stale."""
    ic = _ic_cfg(town_cfg)
    if not ic.get("enabled"):
        return []

    ttl = float(ic.get("cache_ttl_hours") or 24)
    cached = _cached_records(town_slug, parcel_id, ttl)
    if cached:
        return cached

    live = lookup_property_tax_live(town_cfg, parcel_id, address)
    if live:
        mappings = town_cfg.get("source_mappings") or {}
        te_source = str(mappings.get("property_tax") or "invoice-cloud")
        _upsert_cache(town_slug, live, te_source)
        return live
    return []


def portal_url(town_cfg: dict[str, Any]) -> str:
    ic = _ic_cfg(town_cfg)
    return (
        ic.get("vanity_url")
        or _lender_cfg(town_cfg).get("property_tax_portal_url")
        or ""
    )
