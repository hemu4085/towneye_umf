# [FILE PATH]: reports/buildability_brief.py
# Patch #205
# Execution Mode: Tier 4 — Buildability Brief Generator
# Date: 2026-05-07
"""
reports.buildability_brief — programmatic generator for the parcel
buildability brief.

Why this module exists
----------------------
The reference deliverable ``reports/output/29_walnut_buildability_brief.html``
was hand-crafted from the ad-hoc queries in ``scripts/29_walnut_queries.py``.
Tier 2 lifted those queries into proper Gold-tier ingestors; Tier 3 added
the ``OverlayResolver`` so any consumer can ask "what overlays apply?" in
one call.  Tier 4 closes the loop: a deterministic generator that takes
``(town_slug, parcel_id)`` and emits a structurally identical HTML brief.

The split:

  * **Deterministic, data-driven sections** (executive summary verdict,
    parcel snapshot, zoning stack, buildable envelope math, wraparound
    constraints) are computed entirely from Gold parquets via
    ``OverlayResolver`` + the parcel/property/zoning frames.

  * **Narrative sections** (development options matrix, process pathway,
    open items, methodology) are rendered from a Jinja2 template using
    flags derived from the data (e.g. "NMF overlay applies → include
    multi-family rows in the options matrix").  This keeps the brief
    responsive to the parcel's actual zoning profile without requiring
    an LLM call.

The output is a single HTML string the caller writes to disk, returns
from a Streamlit app, or passes to a PDF renderer.

Design contract
---------------
``BuildabilityBriefGenerator.generate(inputs) -> str`` is pure: same
inputs + same Gold lake -> byte-identical HTML modulo the ``prepared_on``
timestamp.  All randomness / wall-clock dependencies are routed through
``BriefInputs.prepared_on``, which the caller controls.
"""

from __future__ import annotations

import json
import logging
import math
import pathlib
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from core.spatial import OverlayHit, OverlayResolver, ParcelInfo, ParcelOverlayStack

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic input + intermediate result models
# ---------------------------------------------------------------------------

class BriefInputs(BaseModel):
    """Caller-supplied parameters for one brief generation."""
    model_config = ConfigDict(from_attributes=True)

    town_slug: str = Field(..., description="Kebab-case town id (e.g. 'arlington-ma').")
    parcel_id: str = Field(..., description="Stable parcel natural key (e.g. '128.0-0003-0012.0').")
    prepared_for: Optional[str] = Field(
        None,
        description="Recipient name printed in the header.  Defaults to None.",
    )
    prepared_on: Optional[date] = Field(
        None,
        description="Report date printed in the header.  Defaults to today.",
    )


class ZoningRule(BaseModel):
    """A single base/overlay zone's bylaw rules — projected from zoning.parquet."""
    model_config = ConfigDict(from_attributes=True)

    zone_code: str
    zone_description: Optional[str] = None
    allowed_uses: List[str] = Field(default_factory=list)
    max_height_ft: Optional[float] = None
    min_lot_sqft: Optional[int] = None
    min_frontage_ft: Optional[int] = None
    max_far: Optional[float] = None
    setback_front_ft: Optional[float] = None
    setback_side_ft: Optional[float] = None
    setback_rear_ft: Optional[float] = None
    is_overlay: bool = Field(
        False,
        description=(
            "True for overlay districts (NMF / MBMF / Mass-Ave Corridor) "
            "where many dimensional minimums are intentionally waived."
        ),
    )
    notes: Optional[str] = None


class PropertyInfo(BaseModel):
    """Assessor record projected from property.parquet — all fields optional."""
    model_config = ConfigDict(from_attributes=True)

    owner_name: Optional[str] = None
    year_built: Optional[int] = None
    building_type: Optional[str] = None
    luc: Optional[str] = None
    luc_description: Optional[str] = None
    beds: Optional[int] = None
    baths: Optional[int] = None
    assessed_value: Optional[float] = None
    lot_size_sqft: Optional[float] = None
    finished_area_sqft: Optional[float] = None
    last_sale_date: Optional[str] = None
    last_sale_price: Optional[float] = None
    book_page: Optional[str] = None


class BuildableEnvelope(BaseModel):
    """Computed buildable envelope under one zoning regime."""
    model_config = ConfigDict(from_attributes=True)

    zone_code: str
    is_overlay: bool
    label: str = Field(..., description="Display label, e.g. 'R2 (base)' or 'NMF (overlay)'.")
    rationale: str = Field(
        ...,
        description=(
            "One-line explanation: which rule governs and how the math "
            "lands.  Example: 'lot 3,023 sf × FAR 0.50 = 1,511 sf max GFA'."
        ),
    )
    lot_sqft: float
    max_far: Optional[float] = None
    max_gfa_sqft: Optional[float] = None
    existing_gfa_sqft: Optional[float] = None
    expansion_room_sqft: Optional[float] = None
    pct_of_far_cap: Optional[float] = Field(
        None, description="existing_gfa / max_gfa, expressed 0.0–1.0+ (>1 means non-conforming).",
    )
    height_max_ft: Optional[float] = None
    height_max_stories: Optional[int] = None
    setback_front_ft: Optional[float] = None
    setback_side_ft: Optional[float] = None
    setback_rear_ft: Optional[float] = None
    qualifies: Optional[bool] = Field(
        None, description="Does the lot meet this regime's min-lot-size requirement?",
    )
    notes: Optional[str] = None


class WraparoundConstraint(BaseModel):
    """One row in the Wraparound Constraints table."""
    model_config = ConfigDict(from_attributes=True)

    label: str
    status: str = Field(..., description="One of 'clear', 'caution', 'flagged'.")
    detail: str
    source: str
    hit_count: int = 0


class BriefData(BaseModel):
    """Fully resolved data context the Jinja2 template renders against."""
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    inputs: BriefInputs
    parcel: ParcelInfo
    parcel_metadata_extras: Dict[str, Any] = Field(default_factory=dict)
    property_info: Optional[PropertyInfo] = None

    base_zoning_hits: List[OverlayHit] = Field(default_factory=list)
    overlay_zoning_hits: List[OverlayHit] = Field(default_factory=list)
    zoning_rules: Dict[str, ZoningRule] = Field(default_factory=dict)

    envelopes: List[BuildableEnvelope] = Field(default_factory=list)
    wraparound: List[WraparoundConstraint] = Field(default_factory=list)
    raw_stack: ParcelOverlayStack

    has_overlay_election: bool = False
    primary_zone_code: Optional[str] = None
    primary_overlay_code: Optional[str] = None
    headline_verdict_class: str = "v-yellow"
    headline_verdict_text: str = ""

    @property
    def report_date_text(self) -> str:
        d = self.inputs.prepared_on or date.today()
        return d.strftime("%B %-d, %Y") if hasattr(d, "strftime") else str(d)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent / "templates"
_TEMPLATE_NAME = "buildability_brief.html.j2"


class BuildabilityBriefGenerator:
    """
    Render a Buildability Brief HTML for one parcel.

    Construct once per town, call ``generate(inputs)`` per parcel.

    The generator does not write to disk — callers are responsible for
    persistence (so it composes cleanly into Streamlit, FastAPI, CLI, etc.).
    """

    def __init__(
        self,
        town_slug: str,
        data_dir: str | pathlib.Path = "data/gold",
        config_dir: str | pathlib.Path = "configs",
        template_dir: Optional[str | pathlib.Path] = None,
    ) -> None:
        self.town_slug = town_slug
        self._data_dir = pathlib.Path(data_dir)
        self._config_dir = pathlib.Path(config_dir)
        self._resolver = OverlayResolver(town_slug=town_slug, data_dir=data_dir)
        env_template_dir = pathlib.Path(template_dir) if template_dir else _TEMPLATE_DIR
        self._jinja_env = Environment(
            loader=FileSystemLoader(env_template_dir),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._jinja_env.filters["fmt_int"] = _fmt_int
        self._jinja_env.filters["fmt_float"] = _fmt_float
        self._jinja_env.filters["fmt_money"] = _fmt_money

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, inputs: BriefInputs) -> str:
        """Collect data + render HTML for the requested parcel."""
        if inputs.town_slug != self.town_slug:
            raise ValueError(
                f"BriefInputs.town_slug={inputs.town_slug!r} does not match "
                f"generator town_slug={self.town_slug!r}.",
            )
        data = self.collect_data(inputs)
        return self.render_html(data)

    def collect_data(self, inputs: BriefInputs) -> BriefData:
        """Gather every piece of data the template needs."""
        stack = self._resolver.resolve(parcel_id=inputs.parcel_id)
        if stack.parcel is None:
            raise ValueError(
                f"BuildabilityBriefGenerator | parcel_id={inputs.parcel_id!r} "
                f"resolved without a ParcelInfo — town={self.town_slug!r}.",
            )

        base_hits, overlay_hits = self._partition_zoning_hits(stack.zoning_overlay)
        zoning_rules = self._load_zoning_rules(base_hits + overlay_hits)
        property_info = self._load_property_info(inputs.parcel_id)
        envelopes = self._build_envelopes(
            parcel=stack.parcel,
            property_info=property_info,
            base_hits=base_hits,
            overlay_hits=overlay_hits,
            zoning_rules=zoning_rules,
        )
        wraparound = self._build_wraparound(stack)
        verdict_class, verdict_text = self._compute_verdict(
            stack=stack, envelopes=envelopes, wraparound=wraparound,
        )

        return BriefData(
            inputs=inputs,
            parcel=stack.parcel,
            parcel_metadata_extras=stack.parcel.metadata or {},
            property_info=property_info,
            base_zoning_hits=base_hits,
            overlay_zoning_hits=overlay_hits,
            zoning_rules=zoning_rules,
            envelopes=envelopes,
            wraparound=wraparound,
            raw_stack=stack,
            has_overlay_election=bool(overlay_hits),
            primary_zone_code=(base_hits[0].code if base_hits else None),
            primary_overlay_code=(overlay_hits[0].code if overlay_hits else None),
            headline_verdict_class=verdict_class,
            headline_verdict_text=verdict_text,
        )

    def render_html(self, data: BriefData) -> str:
        template = self._jinja_env.get_template(_TEMPLATE_NAME)
        return template.render(d=data)

    # ------------------------------------------------------------------
    # Internal — data assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _partition_zoning_hits(
        hits: List[OverlayHit],
    ) -> Tuple[List[OverlayHit], List[OverlayHit]]:
        """
        Split zoning hits into (base, overlay) buckets.

        Heuristic: Arlington's GIS publishes base districts under the
        layer name ``Zoning Districts`` and overlays under
        ``Zoning Overlay Districts``.  We also recognise an explicit
        ``overlay_type``/label of ``"Base"`` as base.  Anything else is
        treated as overlay, which is the safe default — overlays are
        additive, base zones are exclusive, and the brief checks
        whether each zone code has rules in zoning.parquet downstream.
        """
        base, overlay = [], []
        for h in hits:
            layer = (h.layer or "").lower()
            label = (h.label or "").lower()
            if "overlay" in layer:
                overlay.append(h)
            elif label == "base" or layer.endswith("zoning districts"):
                base.append(h)
            else:
                overlay.append(h)
        return base, overlay

    def _load_zoning_rules(self, hits: List[OverlayHit]) -> Dict[str, ZoningRule]:
        """Read zoning.parquet and project rule metadata for each hit zone code."""
        path = self._data_dir / self.town_slug / "zoning.parquet"
        if not path.exists():
            logger.warning(
                "BuildabilityBriefGenerator | zoning.parquet missing at %s — "
                "envelope math will fall back to overlay-only labels.",
                path,
            )
            return {}
        df = pd.read_parquet(path)
        rules: Dict[str, ZoningRule] = {}
        wanted = {h.code for h in hits if h.code}
        for _, row in df.iterrows():
            zc = row.get("zone_code")
            if zc not in wanted:
                continue
            md = row.get("metadata", {}) or {}
            if isinstance(md, str):
                try:
                    md = json.loads(md)
                except Exception:  # noqa: BLE001
                    md = {}
            uses = row.get("allowed_uses", []) or []
            if isinstance(uses, str):
                try:
                    uses = json.loads(uses)
                except Exception:  # noqa: BLE001
                    uses = []
            rules[str(zc)] = ZoningRule(
                zone_code=str(zc),
                zone_description=row.get("zone_description"),
                allowed_uses=list(uses) if uses is not None else [],
                max_height_ft=_safe_float(row.get("max_height_ft")),
                min_lot_sqft=_safe_int(md.get("min_lot_sqft")),
                min_frontage_ft=_safe_int(md.get("min_frontage_ft")),
                max_far=_safe_float(md.get("max_far")),
                setback_front_ft=_safe_float(md.get("setback_front_ft")),
                setback_side_ft=_safe_float(md.get("setback_side_ft")),
                setback_rear_ft=_safe_float(md.get("setback_rear_ft")),
                is_overlay=False,
                notes=md.get("notes"),
            )
        return rules

    def _load_property_info(self, parcel_id: str) -> Optional[PropertyInfo]:
        """Pull assessor record from property.parquet, if a row matches."""
        path = self._data_dir / self.town_slug / "property.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty or "parcel_id" not in df.columns:
            return None
        hit = df[df["parcel_id"] == parcel_id]
        if hit.empty:
            return None
        row = hit.iloc[0]
        md = row.get("metadata", {}) or {}
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except Exception:  # noqa: BLE001
                md = {}
        return PropertyInfo(
            owner_name=_safe_str(row.get("owner_name")),
            year_built=_safe_int(row.get("year_built")),
            building_type=_safe_str(row.get("building_type")),
            luc=_safe_str(row.get("luc")),
            luc_description=_safe_str(row.get("luc_description")),
            beds=_safe_int(row.get("beds")),
            baths=_safe_int(row.get("baths")),
            assessed_value=_safe_float(row.get("assessed_value")),
            lot_size_sqft=_safe_float(row.get("lot_size_sqft")),
            finished_area_sqft=_safe_float(md.get("finished_area_sqft")),
            last_sale_date=_safe_str(md.get("last_sale_date")),
            last_sale_price=_safe_float(md.get("last_sale_price")),
            book_page=_safe_str(md.get("book_page")),
        )

    # ------------------------------------------------------------------
    # Internal — buildable envelope math
    # ------------------------------------------------------------------

    def _build_envelopes(
        self,
        parcel: ParcelInfo,
        property_info: Optional[PropertyInfo],
        base_hits: List[OverlayHit],
        overlay_hits: List[OverlayHit],
        zoning_rules: Dict[str, ZoningRule],
    ) -> List[BuildableEnvelope]:
        """
        Compute one BuildableEnvelope per applicable zone (base + overlays).

        Source-of-truth precedence for lot size:
          1. property.parquet.lot_size_sqft (assessor regulatory figure)
          2. parcel.parquet.area_sqft (GIS polygon — includes ROW slivers)

        Existing GFA precedence:
          1. property.parquet.finished_area_sqft (assessor)
          2. None (envelope still rendered without expansion-room math)
        """
        envelopes: List[BuildableEnvelope] = []

        regulatory_lot_sqft = (
            (property_info.lot_size_sqft if property_info and property_info.lot_size_sqft else None)
            or (parcel.area_sqft if parcel.area_sqft else 0.0)
        )
        existing_gfa = (
            property_info.finished_area_sqft if property_info and property_info.finished_area_sqft
            else None
        )

        for h in base_hits:
            envelopes.append(self._envelope_for_hit(
                hit=h, is_overlay=False, lot_sqft=regulatory_lot_sqft,
                existing_gfa=existing_gfa, rule=zoning_rules.get(h.code or ""),
            ))
        for h in overlay_hits:
            envelopes.append(self._envelope_for_hit(
                hit=h, is_overlay=True, lot_sqft=regulatory_lot_sqft,
                existing_gfa=existing_gfa, rule=zoning_rules.get(h.code or ""),
            ))
        return envelopes

    @staticmethod
    def _envelope_for_hit(
        hit: OverlayHit,
        is_overlay: bool,
        lot_sqft: float,
        existing_gfa: Optional[float],
        rule: Optional[ZoningRule],
    ) -> BuildableEnvelope:
        """Compute one envelope row for *hit* under the given lot/GFA inputs."""
        zone_code = hit.code or "(unknown)"
        label_suffix = "(overlay)" if is_overlay else "(base)"
        label = f"{zone_code} {label_suffix}"

        # Overlay districts (NMF, MBMF) intentionally waive several
        # dimensional minimums.  When zoning.parquet doesn't carry an
        # explicit rule for the overlay code we treat the dimensional
        # minimums as "None required" and document that in the rationale.
        if rule is None:
            return BuildableEnvelope(
                zone_code=zone_code,
                is_overlay=is_overlay,
                label=label,
                rationale=(
                    f"{zone_code} {label_suffix}: no machine-readable rule found "
                    f"in zoning.parquet.  Render-side reports will treat the "
                    f"dimensional minimums as 'None required' (typical for "
                    f"§3A multi-family overlays) and note the gap."
                ),
                lot_sqft=lot_sqft,
                max_far=None,
                max_gfa_sqft=None,
                existing_gfa_sqft=existing_gfa,
                expansion_room_sqft=None,
                pct_of_far_cap=None,
                qualifies=None,
                notes=("Overlay districts often waive lot-size/FAR/coverage "
                       "minimums by design — verify against the bylaw text."),
            )

        # Base zone or rule-bearing overlay
        max_gfa = (lot_sqft * rule.max_far) if rule.max_far else None
        expansion_room = (max_gfa - existing_gfa) if (max_gfa is not None and existing_gfa is not None) else None
        pct = (existing_gfa / max_gfa) if (max_gfa and existing_gfa) else None
        qualifies = (lot_sqft >= rule.min_lot_sqft) if rule.min_lot_sqft else None

        rationale_bits: List[str] = []
        if rule.max_far:
            rationale_bits.append(
                f"lot {_fmt_int(lot_sqft)} sf × FAR {rule.max_far:.2f} = "
                f"{_fmt_int(max_gfa)} sf max GFA"
            )
        if rule.min_lot_sqft:
            rationale_bits.append(
                f"min-lot {_fmt_int(rule.min_lot_sqft)} sf "
                f"({'meets' if qualifies else 'NON-CONFORMING'})"
            )
        rationale = "; ".join(rationale_bits) if rationale_bits else f"{zone_code} rules apply."

        return BuildableEnvelope(
            zone_code=zone_code,
            is_overlay=is_overlay,
            label=label,
            rationale=rationale,
            lot_sqft=lot_sqft,
            max_far=rule.max_far,
            max_gfa_sqft=max_gfa,
            existing_gfa_sqft=existing_gfa,
            expansion_room_sqft=expansion_room,
            pct_of_far_cap=pct,
            height_max_ft=rule.max_height_ft,
            height_max_stories=int(math.floor((rule.max_height_ft or 0) / 12)) if rule.max_height_ft else None,
            setback_front_ft=rule.setback_front_ft,
            setback_side_ft=rule.setback_side_ft,
            setback_rear_ft=rule.setback_rear_ft,
            qualifies=qualifies,
            notes=rule.notes,
        )

    # ------------------------------------------------------------------
    # Internal — wraparound constraints
    # ------------------------------------------------------------------

    def _build_wraparound(self, stack: ParcelOverlayStack) -> List[WraparoundConstraint]:
        """Map the 4 non-zoning OverlayResolver buckets to display rows."""
        rows: List[WraparoundConstraint] = []

        rows.append(self._summarize_constraint(
            label="MACRIS — historic resource (state)",
            hits=stack.macris,
            source="MA Historical Commission MACRIS (statewide MAPC FeatureServer)",
        ))
        rows.append(self._summarize_constraint(
            label="Local historic district / overlay / inventory",
            hits=stack.local_historic,
            source=(
                "Arlington GIS — Local_Historic_District, National_Historic_District, "
                "Historic_Overlay_Districts, Historic_Commission_Inventory_view"
            ),
        ))
        rows.append(self._summarize_constraint(
            label="Wetlands & flood overlays",
            hits=stack.environmental_overlay,
            source=(
                "Arlington GIS — ArlingtonMA_Wetlands, Arlington_Flood_Zones, "
                "Flood_Zones_Preliminary_Changes_2023"
            ),
        ))
        rows.append(self._summarize_constraint(
            label="Open zoning / land-use non-compliance",
            hits=stack.noncompliance,
            source="Arlington GIS — LandUse_NonCompliance",
        ))
        return rows

    @staticmethod
    def _summarize_constraint(
        label: str, hits: List[OverlayHit], source: str,
    ) -> WraparoundConstraint:
        """Render one wraparound row's verdict + detail text."""
        if not hits:
            return WraparoundConstraint(
                label=label,
                status="clear",
                detail="No overlap.",
                source=source,
                hit_count=0,
            )
        # Distinct labels = unique categories the parcel touches
        labels = sorted({(h.label or h.code or h.layer or "—") for h in hits})
        return WraparoundConstraint(
            label=label,
            status="flagged",
            detail=f"{len(hits)} hit(s): {', '.join(labels)}",
            source=source,
            hit_count=len(hits),
        )

    # ------------------------------------------------------------------
    # Internal — headline verdict
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_verdict(
        stack: ParcelOverlayStack,
        envelopes: List[BuildableEnvelope],
        wraparound: List[WraparoundConstraint],
    ) -> Tuple[str, str]:
        """
        Pick a CSS class + sentence for the executive summary verdict box.

        Logic:
          * v-red    if any wraparound row is flagged AND no overlay
                     election is available (truly constrained parcel).
          * v-yellow if any wraparound row is flagged but an overlay
                     election exists (mixed picture).
          * v-green  if zero wraparound flags AND at least one envelope
                     qualifies (clean parcel).
          * v-yellow otherwise.
        """
        flagged = [w for w in wraparound if w.status == "flagged"]
        overlays_in_play = any(env.is_overlay for env in envelopes)
        any_qualify = any(env.qualifies for env in envelopes if env.qualifies is not None)

        addr = stack.parcel.address if stack.parcel and stack.parcel.address else "this parcel"

        if not flagged and any_qualify:
            return ("v-green",
                    f"{addr} has a clean buildable profile: zoning permits redevelopment under "
                    f"{', '.join(sorted({e.zone_code for e in envelopes}))} and there are no "
                    f"historic, environmental, flood, or non-compliance encumbrances.")
        if flagged and overlays_in_play:
            return ("v-yellow",
                    f"{addr} carries {len(flagged)} wraparound constraint(s) but an overlay "
                    f"election is available — see §3 and §6 for the friction stack.")
        if flagged:
            return ("v-red",
                    f"{addr} carries {len(flagged)} wraparound constraint(s) and no overlay "
                    f"alternative — material redevelopment will require special permits / "
                    f"variances; see §6 for specifics.")
        return ("v-yellow",
                f"{addr}: zoning rules resolved, but lot does not meet all base-zone "
                f"dimensional minimums — see §3 and §4 for the qualification analysis.")


# ---------------------------------------------------------------------------
# Tiny formatting helpers exported to the Jinja2 template
# ---------------------------------------------------------------------------

def _safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return s if s else None


def _fmt_int(v: Any) -> str:
    n = _safe_float(v)
    if n is None:
        return "—"
    return f"{int(round(n)):,}"


def _fmt_float(v: Any, places: int = 2) -> str:
    n = _safe_float(v)
    if n is None:
        return "—"
    return f"{n:,.{places}f}"


def _fmt_money(v: Any) -> str:
    n = _safe_float(v)
    if n is None:
        return "—"
    return f"${int(round(n)):,}"


__all__ = [
    "BriefInputs",
    "ZoningRule",
    "PropertyInfo",
    "BuildableEnvelope",
    "WraparoundConstraint",
    "BriefData",
    "BuildabilityBriefGenerator",
]
