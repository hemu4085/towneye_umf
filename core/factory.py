# [FILE PATH]: core/factory.py
# Patch #165
# Execution Mode: Universal Medallion Factory — Core Engine
# Date: 2026-03-01

"""
MedallionFactory
================
The single, town-agnostic engine that drives Bronze → Silver → Gold
transformations for every municipality onboarded to TownEye.

Philosophy
----------
* **Tree**  — each Party record is a precisely shaped leaf: validated,
  audited, and traceable.
* **Forest** — PartyRelationship records wire those leaves into a living
  identity graph that spans the whole town.

Zero-Hardcoding contract
------------------------
No town name, geo-hash, or source identifier may appear as a literal
string in this file.  All town-specific context is injected at runtime
from `configs/{town_slug}/config.yaml` via ConfigLoader.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from .config_loader import ConfigLoader
from .models import (
    PartyType,
    TeBroadband,
    TeClimateZone,
    TeEnvironmentalOverlay,
    TeEquityIndex,
    TeEvent,
    TeHistoricResource,
    TeInfraProject,
    TeMarketTrend,
    TeNonCompliance,
    TeParcel,
    TeParty,
    TePartyRelationship,
    TePermit,
    TePropertyAssessment,
    TeStrDynamics,
    TeTownProfile,
    TeZoning,
    TeZoningOverlay,
)


class MedallionFactory:
    """
    Town-agnostic transformation engine.

    Instantiate once per town slug; the factory self-configures by loading
    the corresponding YAML config through ConfigLoader.

    Parameters
    ----------
    town_slug : str
        Kebab-case municipality identifier (e.g. ``'arlington-ma'``).
        Must match a directory under ``configs/``.
    config_base_dir : str, optional
        Root directory that holds per-town config folders.
        Defaults to ``'configs'``.

    Example
    -------
    >>> factory = MedallionFactory("arlington-ma")
    >>> party = factory.map_to_party(raw, "INDIVIDUAL")
    """

    def __init__(self, town_slug: str, config_base_dir: str = "configs") -> None:
        loader = ConfigLoader(base_dir=config_base_dir)
        self.config: Dict[str, Any] = loader.get_town_config(town_slug)
        self.town_slug: str = town_slug

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _inject_audit_fields(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build the 7-field Audit Shield from runtime context + town config.

        Precedence (highest → lowest):
          1. Caller-supplied value already present in *record*.
          2. Town-level default from ``config.yaml``.
          3. Factory-level fallback constant.

        Parameters
        ----------
        record : dict
            The raw or in-flight data dictionary being promoted.

        Returns
        -------
        dict
            A new dict containing exactly the 7 mandatory ``te_`` audit
            fields.  Merge it into your target payload with ``{**audit,
            **domain_fields}``.
        """
        return {
            "te_id": record.get(
                "te_id",
                str(uuid.uuid4()),
            ),
            "te_source": record.get(
                "te_source",
                self.config.get("default_source", f"{self.town_slug}-umf"),
            ),
            "te_confidence": record.get(
                "te_confidence",
                float(self.config.get("default_confidence", 1.0)),
            ),
            "te_timestamp": record.get(
                "te_timestamp",
                datetime.utcnow(),
            ),
            "te_version": record.get(
                "te_version",
                self.config.get("version", "1.0.0"),
            ),
            "te_geo_hash": record.get(
                "te_geo_hash",
                self.config.get("geo_hash"),
            ),
            "te_updated_by": record.get(
                "te_updated_by",
                self.config.get("updated_by", "UMF_System"),
            ),
        }

    # ------------------------------------------------------------------
    # Public transformation methods
    # ------------------------------------------------------------------

    def map_to_party(
        self,
        raw_data: Dict[str, Any],
        party_type: str,
    ) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold Party dict.

        The method promotes data through two logical medallion stops:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit
          fields, completing the Silver-quality record.
        * **Gold gate** — ``TeParty`` Pydantic model validates the full
          payload; a ``ValidationError`` is raised and propagates to the
          caller if any constraint is violated.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze layer.  Must contain at least:

            * ``te_party_pk`` — BigInt PK (typically assigned upstream or
              via a DB sequence mock during testing).
            * ``legal_name``  — Official registered name.

            Optional fields (``display_name``, ``te_source``, ``metadata``,
            any of the 7 audit fields) are accepted and forwarded.

        party_type : str
            One of ``"INDIVIDUAL"`` or ``"ORGANIZATION"``.

        Returns
        -------
        dict
            A fully validated Gold-tier payload whose keys match the
            ``gold.te_party`` schema.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        KeyError
            If ``te_party_pk`` or ``legal_name`` is absent from *raw_data*.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_party_pk": raw_data["te_party_pk"],
            "party_type": PartyType(party_type),
            "legal_name": raw_data["legal_name"],
            "display_name": raw_data.get("display_name"),
            "metadata": raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeParty = TeParty(**gold_payload)
        return validated.model_dump()

    def produce_gold_identity(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convenience entry-point: promote a raw Bronze record to a Gold
        ``INDIVIDUAL`` Party in one call.

        This is the canonical method called by ``main.py`` and ingestors
        that deal exclusively with person records.  For organisations or
        when ``party_type`` must be explicit, use :meth:`map_to_party`
        directly.

        Parameters
        ----------
        raw_data : dict
            Bronze-layer record.  Must contain ``te_party_pk`` and
            ``legal_name``; all other fields are optional.

        Returns
        -------
        dict
            Fully validated Gold-tier ``TeParty`` payload.
        """
        return self.map_to_party(raw_data, "INDIVIDUAL")

    def map_to_relationship(
        self,
        raw_data: Dict[str, Any],
        relationship_type: str,
        *,
        from_party_pk: Optional[int] = None,
        to_party_pk: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Transform raw edge data into a validated Gold PartyRelationship dict.

        Parameters
        ----------
        raw_data : dict
            Source record.  Must contain ``te_relationship_pk``,
            ``from_party_pk``, ``to_party_pk`` (or pass them explicitly).
        relationship_type : str
            Controlled-vocabulary edge label (e.g. ``"RESIDENT_OF"``).
        from_party_pk : int, optional
            Override ``raw_data['from_party_pk']`` if provided.
        to_party_pk : int, optional
            Override ``raw_data['to_party_pk']`` if provided.

        Returns
        -------
        dict
            Validated Gold-tier payload matching ``gold.te_party_relationship``.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_relationship_pk": raw_data["te_relationship_pk"],
            "from_party_pk": from_party_pk if from_party_pk is not None else raw_data["from_party_pk"],
            "to_party_pk": to_party_pk if to_party_pk is not None else raw_data["to_party_pk"],
            "relationship_type": relationship_type,
            "is_active": raw_data.get("is_active", True),
            "valid_from": raw_data.get("valid_from"),
            "valid_to": raw_data.get("valid_to"),
            **audit,
        }

        validated: TePartyRelationship = TePartyRelationship(**gold_payload)
        return validated.model_dump()

    def map_to_event(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold Event dict.

        Promotes data through the same two medallion stops as
        :meth:`map_to_party`:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit
          fields, completing the Silver-quality record.
        * **Gold gate** — ``TeEvent`` Pydantic model validates the full
          payload; a ``ValidationError`` is raised and propagates to the
          caller if any constraint is violated.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze layer.  Must contain at least:

            * ``te_event_pk``  — BigInt PK (assigned by the DB sequence or
              identity linker upstream).
            * ``event_type``   — Controlled-vocabulary classifier string
              (e.g. ``"CIVIC_MEETING"``, ``"COMMUNITY_EVENT"``,
              ``"311_REQUEST"``).
            * ``event_name``   — Human-readable title of the event.
            * ``start_time``   — UTC start time (``datetime`` or ISO-8601
              string; Pydantic coerces strings automatically).

            Optional fields accepted and forwarded:

            * ``description``  — Free-text narrative or agenda summary.
            * ``end_time``     — UTC end time; ``None`` for open-ended events.
            * Any of the 7 audit fields (caller values take highest precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload whose keys match the
            ``gold.te_event`` schema.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        KeyError
            If ``te_event_pk``, ``event_type``, ``event_name``, or
            ``start_time`` is absent from *raw_data*.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_event_pk":  raw_data["te_event_pk"],
            "event_type":   raw_data["event_type"],
            "event_name":   raw_data["event_name"],
            "description":  raw_data.get("description"),
            "start_time":   raw_data["start_time"],
            "end_time":     raw_data.get("end_time"),
            **audit,
        }

        validated: TeEvent = TeEvent(**gold_payload)
        return validated.model_dump()

    def map_to_zoning(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold Zoning dict.

        Promotes data through the same two medallion stops as the other
        ``map_to_*`` methods:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit
          fields.
        * **Gold gate** — ``TeZoning`` Pydantic model validates the full
          payload; a ``ValidationError`` propagates to the caller if any
          constraint is violated.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze layer.  Must contain at least:

            * ``te_zoning_pk``      — BigInt PK (assigned by the DB sequence
              or identity linker upstream).
            * ``zone_code``         — Short regulatory identifier (e.g. ``"R1"``).
            * ``zone_description``  — Human-readable district name.

            Optional fields accepted and forwarded:

            * ``allowed_uses``    — ``list[str]`` of permitted uses.
            * ``max_height_ft``   — ``float`` or ``None``.
            * ``metadata``        — ``dict`` of additional bylaw attributes.
            * Any of the 7 audit fields (caller values take precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload whose keys match the
            ``gold.te_zoning`` schema.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        KeyError
            If ``te_zoning_pk``, ``zone_code``, or ``zone_description`` is
            absent from *raw_data*.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_zoning_pk":     raw_data["te_zoning_pk"],
            "zone_code":        raw_data["zone_code"],
            "zone_description": raw_data["zone_description"],
            "allowed_uses":     raw_data.get("allowed_uses", []),
            "max_height_ft":    raw_data.get("max_height_ft"),
            "metadata":         raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeZoning = TeZoning(**gold_payload)
        return validated.model_dump()

    def map_to_market_trend(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold MarketTrend dict.

        Promotes data through the same two medallion stops as the other
        ``map_to_*`` methods:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit fields.
        * **Gold gate** — ``TeMarketTrend`` Pydantic model validates the full
          payload; a ``ValidationError`` propagates to the caller on failure.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / mock-data layer.  Must contain:

            * ``te_trend_pk``       — BigInt PK (assigned by linker upstream).
            * ``metric_name``       — Controlled-vocabulary metric identifier.
            * ``metric_value``      — Numeric observation (``float``).
            * ``observation_date``  — ``datetime`` or ISO-8601 string.
            * ``geo_level``         — Geographic granularity string.
            * ``geo_value``         — Geographic unit identifier string.

            Optional: any of the 7 audit fields (caller values take precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload matching ``gold.te_market_trend``.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_trend_pk":      raw_data["te_trend_pk"],
            "metric_name":      raw_data["metric_name"],
            "metric_value":     float(raw_data["metric_value"]),
            "observation_date": raw_data["observation_date"],
            "geo_level":        raw_data["geo_level"],
            "geo_value":        raw_data["geo_value"],
            **audit,
        }

        validated: TeMarketTrend = TeMarketTrend(**gold_payload)
        return validated.model_dump()

    def map_to_infra_project(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold InfraProject dict.

        Promotes data through the standard two medallion stops:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit fields.
        * **Gold gate** — ``TeInfraProject`` Pydantic model validates the full
          payload; a ``ValidationError`` propagates to the caller on failure.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / PDF-extracted layer.  Must contain:

            * ``te_project_pk``        — BigInt PK (assigned by linker upstream).
            * ``project_name``         — Official CIP project name.
            * ``project_type``         — Controlled-vocabulary type classifier.
            * ``status``               — Lifecycle status string.
            * ``location_description`` — Human-readable location string.

            Optional fields accepted and forwarded:

            * ``estimated_cost``   — ``float`` USD total; ``None`` if unbudgeted.
            * ``start_date``       — ``datetime`` or ISO-8601 string.
            * ``end_date``         — ``datetime`` or ISO-8601 string.
            * ``metadata``         — ``dict`` of additional CIP attributes.
            * Any of the 7 audit fields (caller values take precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload matching ``gold.te_infra_project``.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_project_pk":        raw_data["te_project_pk"],
            "project_name":         raw_data["project_name"],
            "project_type":         raw_data["project_type"],
            "status":               raw_data["status"],
            "estimated_cost":       raw_data.get("estimated_cost"),
            "start_date":           raw_data.get("start_date"),
            "end_date":             raw_data.get("end_date"),
            "location_description": raw_data["location_description"],
            "metadata":             raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeInfraProject = TeInfraProject(**gold_payload)
        return validated.model_dump()

    def map_to_permit(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold Permit dict.

        Promotes data through the standard two medallion stops:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit fields.
        * **Gold gate** — ``TePermit`` Pydantic model validates the full
          payload; a ``ValidationError`` propagates to the caller on failure.

        Cross-model linkage
        -------------------
        The caller is responsible for resolving **two** identities before
        calling this method:

        1. ``te_permit_pk`` — the permit's own canonical PK, resolved via
           ``PartyLinker.resolve(te_source, permit_number)``.
        2. ``te_party_pk_applicant`` — the applicant's Party PK, resolved via
           ``PartyLinker.resolve(applicant_te_source, applicant_id)``.

        This dual-resolution pattern is what links the Permit entity back
        into the Universal Identity Graph.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / API-extracted layer.  Must contain:

            * ``te_permit_pk``          — BigInt PK (own identity).
            * ``permit_number``         — Official permit number (natural key).
            * ``permit_type``           — Controlled-vocabulary type classifier.
            * ``status``                — Lifecycle status string.
            * ``application_date``      — ``datetime`` or ISO-8601 string.
            * ``te_party_pk_applicant`` — BigInt FK → ``gold.te_party``.

            Optional fields accepted and forwarded:

            * ``approval_date``     — ``datetime`` or ISO-8601 string.
            * ``estimated_value``   — ``float`` USD declared value.
            * ``metadata``          — ``dict`` of portal-specific attributes.
            * Any of the 7 audit fields (caller values take precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload matching ``gold.te_permit``.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_permit_pk":          raw_data["te_permit_pk"],
            "permit_number":         raw_data["permit_number"],
            "permit_type":           raw_data["permit_type"],
            "status":                raw_data["status"],
            "application_date":      raw_data["application_date"],
            "approval_date":         raw_data.get("approval_date"),
            "estimated_value":       (
                float(raw_data["estimated_value"])
                if raw_data.get("estimated_value") is not None else None
            ),
            "te_party_pk_applicant": int(raw_data["te_party_pk_applicant"]),
            "metadata":              raw_data.get("metadata", {}),
            **audit,
        }

        validated: TePermit = TePermit(**gold_payload)
        return validated.model_dump()

    def map_to_broadband(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold Broadband dict.

        Promotes data through the standard two medallion stops:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit fields.
        * **Gold gate** — ``TeBroadband`` Pydantic model validates the full
          payload; a ``ValidationError`` propagates to the caller on failure.

        Source data
        -----------
        FCC Broadband Fabric / BDC filings are distributed as CSV files.
        The scraper is responsible for parsing the CSV and normalising
        column names before calling this method.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / CSV-parsed layer.  Must contain:

            * ``te_broadband_pk`` — BigInt PK (assigned by linker upstream).
            * ``geo_level``       — Geographic granularity string.
            * ``geo_value``       — Geographic unit identifier string.
            * ``provider_name``   — ISP name as in the FCC filing.
            * ``tech_type``       — Controlled-vocabulary tech classifier.
            * ``max_down_mbps``   — ``float`` download speed in Mbps.
            * ``max_up_mbps``     — ``float`` upload speed in Mbps.

            Optional fields accepted and forwarded:

            * ``metadata``  — ``dict`` of FCC-specific attributes.
            * Any of the 7 audit fields (caller values take precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload matching ``gold.te_broadband``.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_broadband_pk": raw_data["te_broadband_pk"],
            "geo_level":       raw_data["geo_level"],
            "geo_value":       raw_data["geo_value"],
            "provider_name":   raw_data["provider_name"],
            "tech_type":       raw_data["tech_type"],
            "max_down_mbps":   float(raw_data["max_down_mbps"]),
            "max_up_mbps":     float(raw_data["max_up_mbps"]),
            "metadata":        raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeBroadband = TeBroadband(**gold_payload)
        return validated.model_dump()

    def map_to_climate_zone(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze GeoJSON feature into a validated Gold
        ClimateZone dict.

        Promotes data through the standard two medallion stops:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit fields.
        * **Gold gate** — ``TeClimateZone`` Pydantic model validates the full
          payload; a ``ValidationError`` propagates to the caller on failure.

        GeoJSON geometry handling
        -------------------------
        The caller extracts ``geometry.type`` and ``geometry.coordinates``
        from the raw GeoJSON Feature and passes them as ``geometry_type`` /
        ``geometry_coordinates``.  The factory stores coordinates as a native
        Python structure (list of rings / list of lists); the scraper is
        responsible for serialising to JSON before Parquet persistence.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / GeoJSON-parsed layer.  Must contain:

            * ``te_zone_pk``             — BigInt PK (assigned by linker).
            * ``zone_type``              — Controlled-vocabulary zone classifier.
            * ``risk_level``             — Risk severity string.
            * ``geometry_type``          — GeoJSON geometry type string.
            * ``geometry_coordinates``   — GeoJSON coordinate array.

            Optional fields accepted and forwarded:

            * ``metadata``  — ``dict`` of source-specific attributes.
            * Any of the 7 audit fields (caller values take precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload matching ``gold.te_climate_zone``.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_zone_pk":             raw_data["te_zone_pk"],
            "zone_type":              raw_data["zone_type"],
            "risk_level":             raw_data["risk_level"],
            "geometry_type":          raw_data["geometry_type"],
            "geometry_coordinates":   raw_data["geometry_coordinates"],
            "metadata":               raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeClimateZone = TeClimateZone(**gold_payload)
        return validated.model_dump()

    def map_to_equity_index(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze record into a validated Gold EquityIndex dict.

        Promotes data through the standard two medallion stops:

        * **Silver gate** — ``_inject_audit_fields`` stamps the 7 audit fields.
        * **Gold gate** — ``TeEquityIndex`` Pydantic model validates the full
          payload; a ``ValidationError`` propagates to the caller on failure.

        Source data
        -----------
        EJ burden indices are typically distributed as:
        * EPA EJScreen — CSV download from EJScreen portal.
        * CEJST — Parquet / GeoJSON from justice40.whitehouse.gov.
        * MassEJ — Shapefile / GeoJSON from MassGIS.

        The scraper normalises each source into the Bronze dict schema below
        before calling this method.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / Parquet-read layer.  Must contain:

            * ``te_equity_pk``    — BigInt PK (assigned by linker upstream).
            * ``geo_level``       — Geographic granularity string.
            * ``geo_value``       — Geographic unit identifier string.
            * ``index_name``      — Controlled-vocabulary index identifier.
            * ``burden_score``    — ``float`` 0.0–100.0 percentile score.
            * ``is_disadvantaged``— ``bool`` EJ community flag.

            Optional fields accepted and forwarded:

            * ``metadata``  — ``dict`` of indicator breakdowns.
            * Any of the 7 audit fields (caller values take precedence).

        Returns
        -------
        dict
            A fully validated Gold-tier payload matching ``gold.te_equity_index``.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_equity_pk":   raw_data["te_equity_pk"],
            "geo_level":      raw_data["geo_level"],
            "geo_value":      raw_data["geo_value"],
            "index_name":     raw_data["index_name"],
            "burden_score":   float(raw_data["burden_score"]),
            "is_disadvantaged": bool(raw_data["is_disadvantaged"]),
            "metadata":       raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeEquityIndex = TeEquityIndex(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 01 — Property Assessment
    # ------------------------------------------------------------------

    def map_to_property_assessment(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze assessor record into a validated Gold
        PropertyAssessment dict.

        All analytically useful assessor fields are promoted to first-class
        columns so the SQL agent can filter and aggregate them directly.
        Remaining Bronze fields are stored in ``metadata``.

        Parameters
        ----------
        raw_data : dict
            Must contain:

            * ``te_property_pk`` — BigInt PK (assigned by identity linker).
            * ``parcel_id``      — Assessor's natural key string.
            * ``address``        — Full street address.

            Optional fields promoted to columns:

            * ``zone_code``      — Zoning district (e.g. ``"R-2"``).
            * ``assessed_value`` / ``total_value`` — USD value (string or float).
            * ``year_built``     — Integer year.
            * ``building_type``  — Architectural style string.
            * ``lot_size_sqft``  / ``lot_size`` — Area in sqft.
            * ``luc``            — Land use code.
            * ``luc_description``— Land use description.
            * ``beds``           — Bedroom count.
            * ``baths``          — Bathroom count (float for half-baths).
            * ``owner_name``     — Denormalized owner string.
            * ``te_party_pk``    — FK to the owner's Party record.
            * ``metadata``       — Dict of remaining Bronze fields.

        Returns
        -------
        dict
            A fully validated Gold-tier payload whose keys match
            ``gold.te_property_assessment``.
        """
        audit = self._inject_audit_fields(raw_data)

        def _to_float(v: Any) -> Optional[float]:
            if v is None:
                return None
            try:
                return float(str(v).replace("$", "").replace(",", "").strip())
            except (ValueError, TypeError):
                return None

        def _to_int(v: Any) -> Optional[int]:
            if v is None:
                return None
            try:
                return int(str(v).strip())
            except (ValueError, TypeError):
                return None

        gold_payload = {
            "te_property_pk":  int(raw_data["te_property_pk"]),
            "parcel_id":       str(raw_data["parcel_id"]),
            "address":         str(raw_data.get("address", "")),
            "zone_code":       raw_data.get("zone_code"),
            "assessed_value":  _to_float(
                raw_data.get("assessed_value") or raw_data.get("total_value")
            ),
            "year_built":      _to_int(raw_data.get("year_built")),
            "building_type":   raw_data.get("building_type"),
            "lot_size_sqft":   _to_float(
                raw_data.get("lot_size_sqft") or raw_data.get("lot_size")
            ),
            "luc":             raw_data.get("luc"),
            "luc_description": raw_data.get("luc_description"),
            "beds":            _to_int(raw_data.get("beds")),
            "baths":           _to_float(raw_data.get("baths")),
            "owner_name":      (
                raw_data.get("owner_name")
                or raw_data.get("owner")
                or raw_data.get("legal_name")
            ),
            "te_party_pk":     raw_data.get("te_party_pk"),
            "metadata":        raw_data.get("metadata", {}),
            **audit,
        }

        validated: TePropertyAssessment = TePropertyAssessment(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 14 — Parcel Geometry (GIS polygons + computed dimensions)
    # ------------------------------------------------------------------

    def map_to_parcel(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze GIS parcel feature into a validated Gold
        ``TeParcel`` record.

        ``TeParcel`` is the **GIS polygon counterpart** to
        ``TePropertyAssessment``.  The two domains share ``parcel_id`` as
        a join key but live in separate Parquet files because they have
        different update cadences and different source-of-truth contracts:

        * ``TePropertyAssessment`` — assessor's tax record (annual roll)
        * ``TeParcel``             — GIS authoritative polygon (continuous)

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / GeoJSON-parsed feature.  Must contain:

            * ``te_parcel_pk``         — BigInt PK (assigned by linker).
            * ``parcel_id``            — Assessor-style natural key.
            * ``geometry_type``        — ``"Polygon"`` or ``"MultiPolygon"``.
            * ``geometry_coordinates`` — GeoJSON coordinate array.

            Optional fields promoted to columns when present:

            * ``address``         — Site address from the GIS attributes.
            * ``area_sqft``       — Polygon area in square feet.
            * ``perimeter_ft``    — Polygon perimeter in feet.
            * ``longest_edge_ft`` — Longest outer-ring edge in feet.
            * ``edges_ft``        — Ordered list of edge lengths in feet.
            * ``centroid_lat`` / ``centroid_lon`` — Polygon centroid.
            * ``metadata``        — Sidecar dict for everything else.

        Returns
        -------
        dict
            Validated Gold-tier payload matching ``gold.te_parcel``.

        Raises
        ------
        pydantic.ValidationError
            If required fields are missing or type constraints are violated.
        """
        audit = self._inject_audit_fields(raw_data)

        def _to_float(v: Any) -> Optional[float]:
            if v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        gold_payload = {
            "te_parcel_pk":         int(raw_data["te_parcel_pk"]),
            "parcel_id":            str(raw_data["parcel_id"]),
            "address":              raw_data.get("address"),
            "geometry_type":        raw_data["geometry_type"],
            "geometry_coordinates": raw_data["geometry_coordinates"],
            "area_sqft":            _to_float(raw_data.get("area_sqft")),
            "perimeter_ft":         _to_float(raw_data.get("perimeter_ft")),
            "longest_edge_ft":      _to_float(raw_data.get("longest_edge_ft")),
            "edges_ft":             list(raw_data.get("edges_ft", [])),
            "centroid_lat":         _to_float(raw_data.get("centroid_lat")),
            "centroid_lon":         _to_float(raw_data.get("centroid_lon")),
            "metadata":             raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeParcel = TeParcel(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 15 — Zoning Overlay Polygons (GIS spatial counterpart of TeZoning)
    # ------------------------------------------------------------------

    def map_to_zoning_overlay(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze GIS overlay feature into a validated Gold
        ``TeZoningOverlay`` record.

        Where ``map_to_zoning`` produces *textual* bylaw rows (allowed_uses,
        max_height_ft, min_lot_sqft), this method produces the *spatial*
        polygon that says where each rule-set applies on the map.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / GeoJSON-parsed feature.  Must
            contain:

            * ``te_overlay_pk``        — BigInt PK (assigned by linker).
            * ``layer_name``           — Name of the source GIS layer.
            * ``geometry_type``        — ``"Polygon"`` or ``"MultiPolygon"``.
            * ``geometry_coordinates`` — GeoJSON coordinate array.

            Optional fields promoted to columns:

            * ``zone_code``    — Short code, e.g. ``"R2"`` or ``"NMF"``.
            * ``overlay_type`` — Classification, e.g. ``"Base"`` /
                                 ``"Multi-Family"`` / ``"Historic"``.
            * ``metadata``     — Sidecar dict (layer_id, source_dataset,
                                 plus the full raw_attributes payload).

        Returns
        -------
        dict
            Validated Gold-tier payload matching ``gold.te_zoning_overlay``.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_overlay_pk":        int(raw_data["te_overlay_pk"]),
            "layer_name":           str(raw_data["layer_name"]),
            "zone_code":            raw_data.get("zone_code"),
            "overlay_type":         raw_data.get("overlay_type"),
            "geometry_type":        raw_data["geometry_type"],
            "geometry_coordinates": raw_data["geometry_coordinates"],
            "metadata":             raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeZoningOverlay = TeZoningOverlay(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 16 — Historic Resources (MACRIS / NRHP / Local Inventory)
    # ------------------------------------------------------------------

    def map_to_historic_resource(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze MACRIS / historic-inventory feature into a
        validated Gold ``TeHistoricResource`` record.

        Used for both **points** (individual buildings, burial grounds,
        objects) and **polygons** (historic districts, NRHP-listed areas).
        The geometry difference is captured in the ``geometry_type`` field;
        every other field carries the same MACRIS attribute schema.

        Parameters
        ----------
        raw_data : dict
            Source record from the Bronze / GeoJSON-parsed feature.  Must
            contain:

            * ``te_resource_pk``       — BigInt PK (assigned by linker).
            * ``town_name``            — Municipality (filter value).
            * ``geometry_type``        — ``"Point"`` / ``"Polygon"`` / ``"MultiPolygon"``.
            * ``geometry_coordinates`` — GeoJSON coordinate array.

            Optional MACRIS-attribute fields promoted to columns: ``mhcn``,
            ``resource_kind``, ``legend``, ``designation``,
            ``designation_date``, ``historic_name``, ``common_name``,
            ``address``, ``construction_date``, ``architectural_style``,
            ``architect``, ``use_type``, ``significance``, ``demolished``.

        Returns
        -------
        dict
            Validated Gold-tier payload matching ``gold.te_historic_resource``.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_resource_pk":       int(raw_data["te_resource_pk"]),
            "mhcn":                 raw_data.get("mhcn"),
            "resource_kind":        raw_data.get("resource_kind"),
            "legend":               raw_data.get("legend"),
            "designation":          raw_data.get("designation"),
            "designation_date":     raw_data.get("designation_date"),
            "historic_name":        raw_data.get("historic_name"),
            "common_name":          raw_data.get("common_name"),
            "address":              raw_data.get("address"),
            "town_name":            str(raw_data["town_name"]),
            "construction_date":    raw_data.get("construction_date"),
            "architectural_style":  raw_data.get("architectural_style"),
            "architect":            raw_data.get("architect"),
            "use_type":             raw_data.get("use_type"),
            "significance":         raw_data.get("significance"),
            "demolished":           raw_data.get("demolished"),
            "geometry_type":        raw_data["geometry_type"],
            "geometry_coordinates": raw_data["geometry_coordinates"],
            "metadata":             raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeHistoricResource = TeHistoricResource(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 17 — Land-Use / Zoning Non-Compliance (descriptive polygons)
    # ------------------------------------------------------------------

    def map_to_noncompliance(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a raw Bronze land-use / zoning non-compliance polygon
        feature into a validated Gold ``TeNonCompliance`` record.

        These polygons are *descriptive* (legal pre-existing non-conforming
        use, expansion-restricted parcels) rather than enforcement cases,
        so the model focuses on classification fields rather than dates
        or case numbers.

        Required keys in *raw_data*:
          * ``te_violation_pk``      — BigInt PK assigned by linker.
          * ``geometry_type``        — ``"Polygon"`` / ``"MultiPolygon"``.
          * ``geometry_coordinates`` — GeoJSON coordinate array.

        Optional keys promoted to columns: ``land_use_code``,
        ``zone_code_numeric``, ``land_use_zone_diff``, ``status``,
        ``metadata``.
        """
        audit = self._inject_audit_fields(raw_data)

        def _to_int(v: Any) -> Optional[int]:
            if v is None:
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        gold_payload = {
            "te_violation_pk":      int(raw_data["te_violation_pk"]),
            "land_use_code":        raw_data.get("land_use_code"),
            "zone_code_numeric":    _to_int(raw_data.get("zone_code_numeric")),
            "land_use_zone_diff":   _to_int(raw_data.get("land_use_zone_diff")),
            "status":               raw_data.get("status"),
            "geometry_type":        raw_data["geometry_type"],
            "geometry_coordinates": raw_data["geometry_coordinates"],
            "metadata":             raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeNonCompliance = TeNonCompliance(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 19 — Environmental Overlay (wetlands + flood zones unified)
    # ------------------------------------------------------------------

    def map_to_environmental_overlay(
        self, raw_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Transform a raw Bronze wetlands / flood-zone polygon feature into
        a validated Gold ``TeEnvironmentalOverlay`` record.

        The ``category`` field discriminates wetland vs flood-effective vs
        flood-preliminary; downstream report code uses the category to
        choose the appropriate label and severity.

        Required keys in *raw_data*: ``te_overlay_pk``, ``category``,
        ``source_layer_name``, ``geometry_type``, ``geometry_coordinates``.
        Optional: ``zone_code``, ``zone_subtype``, ``sfha_flag``,
        ``static_bfe``, ``metadata``.
        """
        audit = self._inject_audit_fields(raw_data)

        def _to_float(v: Any) -> Optional[float]:
            if v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        gold_payload = {
            "te_overlay_pk":        int(raw_data["te_overlay_pk"]),
            "category":             str(raw_data["category"]),
            "zone_code":            raw_data.get("zone_code"),
            "zone_subtype":         raw_data.get("zone_subtype"),
            "sfha_flag":            raw_data.get("sfha_flag"),
            "static_bfe":           _to_float(raw_data.get("static_bfe")),
            "source_layer_name":    str(raw_data["source_layer_name"]),
            "geometry_type":        raw_data["geometry_type"],
            "geometry_coordinates": raw_data["geometry_coordinates"],
            "metadata":             raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeEnvironmentalOverlay = TeEnvironmentalOverlay(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 11 — Town Profile (LLM Synthesis)
    # ------------------------------------------------------------------

    def map_to_town_profile(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Promote a raw LLM-generated town profile dict to a Gold
        ``TeTownProfile`` record.

        Parameters
        ----------
        raw_data : dict
            Must contain:

            * ``te_profile_pk``          — BigInt PK (assigned by linker).
            * ``profile_type``           — ``str`` e.g. ``"FULL"``.
            * ``town_name``              — ``str`` official municipality name.
            * ``state``                  — ``str`` 2-letter state abbreviation.
            * ``neighborhood_vibes``     — ``str`` LLM narrative.
            * ``major_employers``        — ``list[str]``.
            * ``nimby_index``            — ``float`` 0–10.
            * ``housing_character``      — ``str``.
            * ``political_lean``         — ``str``.
            * ``llm_model``              — ``str`` model identifier.

            Optional:

            * ``generation_prompt_hash`` — ``str`` SHA-256 hex digest.
            * ``metadata``               — ``dict``.

        Returns
        -------
        dict
            Validated Gold-tier payload matching ``gold.te_town_profile``.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_profile_pk":          int(raw_data["te_profile_pk"]),
            "profile_type":           str(raw_data["profile_type"]),
            "town_name":              str(raw_data["town_name"]),
            "state":                  str(raw_data["state"]).upper()[:2],
            "neighborhood_vibes":     str(raw_data["neighborhood_vibes"]),
            "major_employers":        list(raw_data.get("major_employers", [])),
            "nimby_index":            float(raw_data["nimby_index"]),
            "housing_character":      str(raw_data["housing_character"]),
            "political_lean":         str(raw_data["political_lean"]),
            "llm_model":              str(raw_data["llm_model"]),
            "generation_prompt_hash": raw_data.get("generation_prompt_hash"),
            "metadata":               raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeTownProfile = TeTownProfile(**gold_payload)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Domain 12 — STR Dynamics (LLM Synthesis)
    # ------------------------------------------------------------------

    def map_to_str_dynamics(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Promote a raw LLM-generated STR dynamics dict to a Gold
        ``TeStrDynamics`` record.

        Parameters
        ----------
        raw_data : dict
            Must contain:

            * ``te_str_pk``             — BigInt PK (assigned by linker).
            * ``observation_month``     — ``str`` ``"YYYY-MM"``.
            * ``estimated_yield_pct``   — ``float`` gross yield %.
            * ``avg_nightly_rate_usd``  — ``float`` USD.
            * ``occupancy_rate_pct``    — ``float`` 0–100.
            * ``target_guest_demo``     — ``str`` e.g. ``"REMOTE_WORKER"``.
            * ``regulatory_posture``    — ``str`` e.g. ``"MODERATE"``.
            * ``peak_seasons``          — ``list[str]``.
            * ``llm_model``             — ``str`` model identifier.

            Optional:

            * ``metadata``  — ``dict``.

        Returns
        -------
        dict
            Validated Gold-tier payload matching ``gold.te_str_dynamics``.
        """
        audit = self._inject_audit_fields(raw_data)

        gold_payload = {
            "te_str_pk":            int(raw_data["te_str_pk"]),
            "observation_month":    str(raw_data["observation_month"]),
            "estimated_yield_pct":  float(raw_data["estimated_yield_pct"]),
            "avg_nightly_rate_usd": float(raw_data["avg_nightly_rate_usd"]),
            "occupancy_rate_pct":   float(raw_data["occupancy_rate_pct"]),
            "target_guest_demo":    str(raw_data["target_guest_demo"]),
            "regulatory_posture":   str(raw_data["regulatory_posture"]),
            "peak_seasons":         list(raw_data.get("peak_seasons", [])),
            "llm_model":            str(raw_data["llm_model"]),
            "metadata":             raw_data.get("metadata", {}),
            **audit,
        }

        validated: TeStrDynamics = TeStrDynamics(**gold_payload)
        return validated.model_dump()


# core/factory.py
# End of Patch #179
