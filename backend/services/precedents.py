"""Precedent Search — board decision research for zoning attorneys.

Merges (1) Gold ``civic_minutes.parquet`` when present with (2) town-config
``precedent_search.corpus`` entries curated from publicly posted agendas.
Never invents cite-ready outcomes; agenda-index rows stay verify-before-cite.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from backend.config import get_settings

_STREET_SUFFIXES = (
    " STREET",
    " ST",
    " AVENUE",
    " AVE",
    " ROAD",
    " RD",
    " DRIVE",
    " DR",
    " LANE",
    " LN",
    " COURT",
    " CT",
    " PLACE",
    " PL",
    " WAY",
    " TERRACE",
    " TER",
)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").upper()).strip()


def _street_core(address: str | None) -> str:
    needle = _norm(address).split(",")[0]
    for token in _STREET_SUFFIXES:
        if needle.endswith(token):
            return needle[: -len(token)].strip()
    return needle


@lru_cache(maxsize=8)
def _town_cfg(town_slug: str) -> dict[str, Any]:
    path = Path("configs") / town_slug / "config.yaml"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _precedent_cfg(town_slug: str) -> dict[str, Any]:
    cfg = _town_cfg(town_slug).get("precedent_search") or {}
    return cfg if isinstance(cfg, dict) else {}


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _citation_block(row: dict[str, Any]) -> str:
    parts = [
        f"{row.get('board') or 'Board'} Docket {row.get('docket') or '—'}",
        row.get("address") or "",
    ]
    relief = row.get("relief_types") or []
    if relief:
        parts.append("Relief: " + ", ".join(str(x) for x in relief))
    if row.get("decision"):
        parts.append(f"Status: {row['decision']}")
    if row.get("hearing_date"):
        parts.append(f"Agenda/hearing: {row['hearing_date']}")
    if row.get("summary"):
        parts.append(str(row["summary"]))
    parts.append(
        "VERIFY: Pull the signed decision / minutes from the Town Clerk or board "
        "document folder before citing in a filing. Towneye agenda-index rows are "
        "research aids, not certified holdings."
    )
    return "\n".join(p for p in parts if p)


def _load_gold_minutes(town_slug: str) -> list[dict[str, Any]]:
    gold = Path(get_settings().gold_data_path) / town_slug / "civic_minutes.parquet"
    if not gold.exists():
        return []
    try:
        df = pd.read_parquet(gold)
    except Exception:  # noqa: BLE001
        return []
    if df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, raw in df.iterrows():
        md = _parse_metadata(raw.get("metadata"))
        docket = raw.get("docket")
        if docket is not None and str(docket) in ("", "nan", "None"):
            docket = None
        decision = str(raw.get("status") or md.get("status") or md.get("decision_status") or "—")
        board = str(md.get("board") or md.get("board_name") or raw.get("board") or "—")
        address = str(raw.get("address") or md.get("address") or "")
        summary = str(md.get("summary") or raw.get("summary") or "")
        relief = md.get("relief_types") or md.get("relief_type") or []
        if isinstance(relief, str):
            relief = [relief]
        row = {
            "id": f"gold:{docket or raw.get('te_event_pk') or len(rows)}",
            "docket": str(docket) if docket is not None else None,
            "address": address,
            "board": board,
            "relief_types": list(relief),
            "decision": decision.upper() if decision else "—",
            "hearing_date": str(md.get("hearing_date") or md.get("meeting_date") or "")[:10] or None,
            "summary": summary,
            "zbl_sections": list(md.get("zbl_sections") or []),
            "source_kind": "gold_civic_minutes",
            "provenance": "TownEye Gold civic_minutes.parquet",
            "source_url": md.get("source_url") or None,
            "cite_ready": False,
            "parcel_id": str(raw.get("parcel_id") or md.get("parcel_id") or "") or None,
        }
        row["citation"] = _citation_block(row)
        rows.append(row)
    return rows


def _load_config_corpus(town_slug: str) -> list[dict[str, Any]]:
    corpus = _precedent_cfg(town_slug).get("corpus") or []
    rows: list[dict[str, Any]] = []
    for i, item in enumerate(corpus):
        if not isinstance(item, dict):
            continue
        relief = item.get("relief_types") or []
        if isinstance(relief, str):
            relief = [relief]
        sections = item.get("zbl_sections") or []
        if isinstance(sections, str):
            sections = [sections]
        row = {
            "id": f"corpus:{item.get('docket') or i}",
            "docket": str(item.get("docket") or "") or None,
            "address": str(item.get("address") or ""),
            "board": str(item.get("board") or "—"),
            "relief_types": [str(x) for x in relief],
            "decision": str(item.get("decision") or "HEARING_LISTED").upper(),
            "hearing_date": str(item.get("hearing_date") or "")[:10] or None,
            "summary": str(item.get("summary") or ""),
            "zbl_sections": [str(x) for x in sections],
            "source_kind": str(item.get("source_kind") or "agenda_index"),
            "provenance": str(item.get("provenance") or "Town-config research corpus"),
            "source_url": item.get("source_url") or None,
            "cite_ready": bool(item.get("cite_ready", False)),
            "parcel_id": str(item.get("parcel_id") or "") or None,
            "neighborhood": str(item.get("neighborhood") or "") or None,
            "memo_tip": str(item.get("memo_tip") or "") or None,
        }
        row["citation"] = _citation_block(row)
        rows.append(row)
    return rows


def _relevance(
    row: dict[str, Any],
    *,
    query: str,
    parcel_address: str | None,
    parcel_id: str | None,
) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    q = _norm(query)
    hay = _norm(
        " ".join(
            [
                str(row.get("docket") or ""),
                str(row.get("address") or ""),
                str(row.get("board") or ""),
                str(row.get("decision") or ""),
                str(row.get("summary") or ""),
                " ".join(row.get("relief_types") or []),
                " ".join(row.get("zbl_sections") or []),
                str(row.get("neighborhood") or ""),
            ]
        )
    )
    if q:
        tokens = [t for t in q.split() if len(t) > 1]
        hits = sum(1 for t in tokens if t in hay)
        if hits:
            score += hits * 12
            reasons.append("query match")
        if q in hay:
            score += 20

    if parcel_id and row.get("parcel_id") and str(row["parcel_id"]) == str(parcel_id):
        score += 100
        reasons.append("same parcel")

    if parcel_address:
        core = _street_core(parcel_address)
        row_core = _street_core(row.get("address"))
        if core and row_core and (core in row_core or row_core in core):
            score += 40
            reasons.append("same street")
        # House number proximity on same street stem
        parcel_num = re.match(r"^(\d+)", _norm(parcel_address).split(",")[0])
        row_num = re.match(r"^(\d+)", _norm(row.get("address")).split(",")[0])
        if (
            parcel_num
            and row_num
            and core
            and row_core
            and core.split()[-1:] == row_core.split()[-1:]
        ):
            try:
                delta = abs(int(parcel_num.group(1)) - int(row_num.group(1)))
                if delta <= 50:
                    score += 15
                    reasons.append("nearby street numbers")
            except ValueError:
                pass

    if row.get("source_kind") == "gold_civic_minutes":
        score += 5

    return score, ", ".join(reasons) if reasons else "corpus"


def search_precedents(
    *,
    town_slug: str,
    query: str = "",
    board: str | None = None,
    relief: str | None = None,
    decision: str | None = None,
    parcel_id: str | None = None,
    address: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    cfg = _precedent_cfg(town_slug)
    gold_rows = _load_gold_minutes(town_slug)
    corpus_rows = _load_config_corpus(town_slug)

    # Prefer Gold when same docket exists in both
    by_key: dict[str, dict[str, Any]] = {}
    for row in corpus_rows + gold_rows:
        key = f"{_norm(row.get('board'))}|{_norm(row.get('docket'))}|{_norm(row.get('address'))}"
        by_key[key] = row
    pool = list(by_key.values())

    board_f = _norm(board) if board and board.lower() not in ("", "all") else ""
    relief_f = _norm(relief) if relief and relief.lower() not in ("", "all") else ""
    decision_f = _norm(decision) if decision and decision.lower() not in ("", "all") else ""

    filtered: list[dict[str, Any]] = []
    for row in pool:
        if board_f and board_f not in _norm(row.get("board")):
            continue
        if relief_f:
            reliefs = [_norm(x) for x in (row.get("relief_types") or [])]
            blob = " ".join(reliefs) + " " + _norm(row.get("summary"))
            if relief_f not in blob:
                continue
        if decision_f and decision_f not in _norm(row.get("decision")):
            continue
        score, why = _relevance(
            row,
            query=query,
            parcel_address=address,
            parcel_id=parcel_id,
        )
        if query.strip() and score <= 0:
            continue
        out = dict(row)
        out["relevance_score"] = score
        out["relevance_reason"] = why if score else "browse"
        filtered.append(out)

    def _date_key(r: dict[str, Any]) -> int:
        digits = str(r.get("hearing_date") or "").replace("-", "")[:8]
        return int(digits) if digits.isdigit() else 0

    filtered.sort(key=lambda r: (-int(r.get("relevance_score") or 0), -_date_key(r)))

    limit = max(1, min(int(limit or 50), 100))
    results = filtered[:limit]

    boards = sorted({str(r.get("board")) for r in pool if r.get("board")})
    reliefs = sorted(
        {
            str(x)
            for r in pool
            for x in (r.get("relief_types") or [])
            if x
        }
    )
    decisions = sorted({str(r.get("decision")) for r in pool if r.get("decision")})

    sources = cfg.get("official_sources") or []
    if not isinstance(sources, list):
        sources = []

    gold_present = bool(gold_rows)
    data_tier = (
        "gold+corpus"
        if gold_present and corpus_rows
        else "gold"
        if gold_present
        else "agenda_index_corpus"
        if corpus_rows
        else "empty"
    )

    disclaimer = str(
        cfg.get("disclaimer")
        or (
            "Agenda-index and Gold minute extracts are research aids. "
            "Verify the signed decision with the Town Clerk before citing."
        )
    )

    return {
        "town_slug": town_slug,
        "query": query,
        "parcel_id": parcel_id,
        "address": address,
        "data_tier": data_tier,
        "disclaimer": disclaimer,
        "gold_minutes_count": len(gold_rows),
        "corpus_count": len(corpus_rows),
        "total_indexed": len(pool),
        "result_count": len(results),
        "results": results,
        "facets": {
            "boards": boards,
            "relief_types": reliefs,
            "decisions": decisions,
        },
        "official_sources": sources,
        "research_tips": cfg.get("research_tips") or [],
    }
