# [FILE PATH]: core/models.py
# Patch #171
# Execution Mode: Gold Tier Pydantic Model Definition (+ TeNonCompliance, TeEnvironmentalOverlay)
# Date: 2026-05-07

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PartyType(str, Enum):
    """Controlled vocabulary for Party classification."""
    INDIVIDUAL = "INDIVIDUAL"
    ORGANIZATION = "ORGANIZATION"


class AuditFields(BaseModel):
    """
    The mandatory 7-field Audit Shield (Silver / Gold tiers).

    Every record that crosses a medallion boundary MUST carry all seven
    fields.  Values are sourced from the injecting factory — never
    hardcoded in downstream logic.
    """
    te_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique UUID for end-to-end record tracing.",
    )
    te_source: str = Field(
        ...,
        description="Originating system identifier (e.g. 'invoice-cloud', 'opengov').",
    )
    te_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Data-quality confidence score [0.0 – 1.0].",
    )
    te_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC wall-clock time of record creation.",
    )
    te_version: str = Field(
        default="1.0.0",
        description="Pipeline schema / transform version that produced this record.",
    )
    te_geo_hash: Optional[str] = Field(
        None,
        max_length=12,
        description="Geohash of the town centroid (injected from town config).",
    )
    te_updated_by: str = Field(
        default="UMF_System",
        description="Agent or process that last wrote this record.",
    )


# Backward-compatible alias — prefer AuditFields in new code
TownEyeAuditShield = AuditFields


class TeParty(AuditFields):
    """
    Gold-tier Party entity.  Schema mirrors gold.te_party exactly.

    The 'Tree' is the individual Party.  Collections of related parties
    form the 'Forest' expressed via TePartyRelationship.
    """
    model_config = ConfigDict(from_attributes=True)

    te_party_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by the DB sequence).",
    )
    party_type: PartyType
    legal_name: str = Field(..., max_length=255)
    display_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible sidecar for attributes outside the core schema.",
    )


# Backward-compatible alias — prefer TeParty in new code
Party = TeParty


class TePartyRelationship(AuditFields):
    """
    Gold-tier Relationship ledger.  Schema mirrors gold.te_party_relationship.

    The 'Forest' view — connects Party trees into an identity graph.
    """
    model_config = ConfigDict(from_attributes=True)

    te_relationship_pk: int = Field(
        ...,
        description="BigInt Primary Key (assigned by the DB sequence).",
    )
    from_party_pk: int
    to_party_pk: int
    relationship_type: str = Field(
        ...,
        max_length=50,
        description="Controlled-vocabulary edge label (e.g. RESIDENT_OF, OWNER_OF).",
    )
    is_active: bool = True
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


# Backward-compatible alias — prefer TePartyRelationship in new code
PartyRelationship = TePartyRelationship


class TeEvent(AuditFields):
    """
    Gold-tier civic Event entity.  Schema mirrors gold.te_event exactly.

    Represents any time-bounded municipal occurrence that the Town Pulse
    layer ingests — a board or committee meeting, a community gathering,
    a 311 / SeeClickFix service request, or a transit system alert.
    Events can be linked to Party records (e.g. the organising body or
    the affected transit agency) via TePartyRelationship.

    The 'when' dimension of the identity graph: where TeParty answers
    *who*, TeEvent answers *what happened and when*.

    Supported ``event_type`` vocabulary (open-ended ``str`` — new types
    require only a config entry, never a model change):

    =====================  ========================================
    Value                  Source
    =====================  ========================================
    ``CIVIC_MEETING``      Board / committee calendars
    ``COMMUNITY_EVENT``    Town public-events feed
    ``311_REQUEST``        SeeClickFix service requests
    ``TRANSIT_ALERT``      MBTA V3 API service alerts
    =====================  ========================================
    """
    model_config = ConfigDict(from_attributes=True)

    te_event_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by the DB sequence).",
    )
    event_type: str = Field(
        ...,
        max_length=50,
        description=(
            "Controlled-vocabulary event classifier. "
            "Current values: 'CIVIC_MEETING', 'COMMUNITY_EVENT', "
            "'311_REQUEST', 'TRANSIT_ALERT'. "
            "New types require only a config entry — no model change."
        ),
    )
    event_name: str = Field(
        ...,
        max_length=255,
        description="Human-readable name or title of the event.",
    )
    description: Optional[str] = Field(
        None,
        description=(
            "Free-text narrative, agenda summary, service-request detail, "
            "or alert header text."
        ),
    )
    start_time: datetime = Field(
        ...,
        description="UTC start time of the event.",
    )
    end_time: Optional[datetime] = Field(
        None,
        description=(
            "UTC end time of the event.  "
            "None for open-ended or point-in-time records "
            "(e.g. 311 submissions, active transit alerts)."
        ),
    )


# Backward-compatible alias — prefer TeEvent in new code
Event = TeEvent


class TeZoning(AuditFields):
    """
    Gold-tier Zoning District entity.  Schema mirrors gold.te_zoning exactly.

    Represents a single zoning classification as published in a municipality's
    bylaws or GIS zoning layer.  Each record captures the regulatory envelope
    that governs land-use decisions within a defined district.

    The 'where / what is permitted' dimension of the identity graph:
    * ``TeParty``   answers *who* (property owner / organisation)
    * ``TeEvent``   answers *what happened and when* (meeting, alert)
    * ``TeZoning``  answers *what may be built here and under what rules*

    A ``TePartyRelationship`` of type ``"ZONED_AS"`` links a parcel (``TeParty``)
    to its applicable ``TeZoning`` record.

    Supported ``zone_code`` vocabulary (open-ended ``str`` — new codes require
    only a config entry, never a model change):

    ======  =============================================
    Code    Typical description
    ======  =============================================
    R0      Single-family residential (large lots)
    R1      Single-family residential
    R2      Two-family residential
    R3      Multi-family residential
    B1      Neighbourhood business
    B2      General business
    B4      Business / mixed-use corridor
    MU      Mixed-use
    IO      Industrial / office
    ======  =============================================
    """
    model_config = ConfigDict(from_attributes=True)

    te_zoning_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by the DB sequence).",
    )
    zone_code: str = Field(
        ...,
        max_length=20,
        description=(
            "Short regulatory identifier (e.g. 'R1', 'B4', 'MU').  "
            "Drawn directly from the municipality's official bylaw table."
        ),
    )
    zone_description: str = Field(
        ...,
        max_length=255,
        description="Human-readable name of the zoning district.",
    )
    allowed_uses: List[str] = Field(
        default_factory=list,
        description=(
            "Principal permitted uses as enumerated in the bylaw "
            "(e.g. ['Single-Family Dwelling', 'Home Occupation'])."
        ),
    )
    max_height_ft: Optional[float] = Field(
        None,
        ge=0.0,
        description=(
            "Maximum building height in feet as specified by the bylaw.  "
            "None when not explicitly constrained."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for additional bylaw attributes such as "
            "min_lot_sqft, max_far, setback_front_ft, parking_spaces_per_unit, "
            "or any portal-specific fields that don't yet have a first-class column."
        ),
    )


class TeMarketTrend(AuditFields):
    """
    Gold-tier Market Trend observation.  Schema mirrors gold.te_market_trend.

    Captures a single time-stamped measurement of a real-estate or housing
    market metric at a defined geographic level.  Rows are additive — each
    observation is an immutable point-in-time snapshot, not an upsert.

    The 'how much / how fast' dimension of the identity graph:
    * ``TeParty``       answers *who* (owner, buyer, renter)
    * ``TeZoning``      answers *what is permitted here*
    * ``TeMarketTrend`` answers *what is the market doing and where*

    Supported ``metric_name`` vocabulary (open-ended ``str``; new metrics
    require only a config entry, never a model change):

    ========================  =============================================
    metric_name               Unit / description
    ========================  =============================================
    ``MEDIAN_RENT_1BR``       USD / month — median asking rent, 1 bedroom
    ``MEDIAN_RENT_2BR``       USD / month — median asking rent, 2 bedrooms
    ``MEDIAN_RENT_3BR``       USD / month — median asking rent, 3 bedrooms
    ``MEDIAN_SALE_PRICE``     USD — median closed sale price
    ``AVG_DAYS_ON_MARKET``    Days — average listing-to-contract duration
    ``MONTHS_OF_SUPPLY``      Months — active listings ÷ monthly sales rate
    ``PRICE_PER_SQFT``        USD / ft² — median price per finished sqft
    ========================  =============================================

    Supported ``geo_level`` vocabulary:

    ============  =====================================================
    geo_level     geo_value example
    ============  =====================================================
    ``TOWN``      ``"arlington-ma"``
    ``ZIPCODE``   ``"02474"`` or ``"02476"``
    ``GEOHASH``   ``"drt2zh"``  (precision-6 Geohash centroid)
    ``TRACT``     ``"25017352400"``  (Census tract GEOID)
    ============  =====================================================
    """
    model_config = ConfigDict(from_attributes=True)

    te_trend_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    metric_name: str = Field(
        ...,
        max_length=50,
        description=(
            "Controlled-vocabulary metric identifier "
            "(e.g. 'MEDIAN_RENT_1BR', 'AVG_DAYS_ON_MARKET'). "
            "New metrics require only a config entry — no model change."
        ),
    )
    metric_value: float = Field(
        ...,
        description="Numeric observation value in the unit implied by metric_name.",
    )
    observation_date: datetime = Field(
        ...,
        description=(
            "Date/time the metric was observed or the reporting period ended. "
            "For monthly aggregates, use the last calendar day of the month."
        ),
    )
    geo_level: str = Field(
        ...,
        max_length=20,
        description=(
            "Geographic granularity of the observation. "
            "One of: 'TOWN', 'ZIPCODE', 'GEOHASH', 'TRACT'."
        ),
    )
    geo_value: str = Field(
        ...,
        max_length=50,
        description=(
            "Identifier for the geographic unit at geo_level "
            "(e.g. zip code '02474', geohash 'drt2zh')."
        ),
    )


class TeInfraProject(AuditFields):
    """
    Gold-tier Infrastructure / Capital Improvement Project entity.
    Schema mirrors gold.te_infra_project exactly.

    Represents a single DPW capital project as extracted from a municipality's
    Capital Improvement Plan (CIP) document, project-tracker spreadsheet, or
    PDF budget appendix.

    The 'what is being built / repaired and when' dimension of the identity graph:
    * ``TeParty``        answers *who* (contractor, abutting property owner)
    * ``TeZoning``       answers *what is permitted on the affected parcel*
    * ``TeMarketTrend``  answers *what the market is doing near the project*
    * ``TeInfraProject`` answers *what public-works investment is occurring and where*

    Supported ``project_type`` vocabulary (open-ended ``str``):

    ==================  =====================================================
    project_type        Description
    ==================  =====================================================
    ``ROAD_PAVING``     Full-depth reclamation or overlay of a roadway
    ``WATER_MAIN``      Water distribution main replacement or rehabilitation
    ``SEWER_MAIN``      Sanitary sewer main work
    ``SIDEWALK``        Sidewalk reconstruction or ADA ramp upgrade
    ``BRIDGE``          Bridge inspection, repair, or replacement
    ``PARK``            Park renovation or capital improvement
    ``STREETSCAPE``     Streetscape / urban design improvement
    ``STORMWATER``      Stormwater drainage upgrade or green infrastructure
    ``FACILITY``        Municipal building renovation or new construction
    ``OTHER``           Catch-all for projects not fitting the above types
    ==================  =====================================================

    Supported ``status`` vocabulary:

    =================  =====================================================
    status             Description
    =================  =====================================================
    ``PLANNED``        Approved and budgeted; not yet started
    ``DESIGN``         In design / engineering phase
    ``BID``            Out to bid / procurement phase
    ``IN_PROGRESS``    Active construction or implementation
    ``COMPLETED``      Work finished and accepted
    ``DEFERRED``       Postponed to a future fiscal year
    ``CANCELLED``      Project removed from the capital plan
    =================  =====================================================
    """
    model_config = ConfigDict(from_attributes=True)

    te_project_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    project_name: str = Field(
        ...,
        max_length=255,
        description="Official project name as it appears in the CIP document.",
    )
    project_type: str = Field(
        ...,
        max_length=50,
        description=(
            "Controlled-vocabulary project classifier "
            "(e.g. 'ROAD_PAVING', 'WATER_MAIN', 'SIDEWALK'). "
            "New types require only a config entry — no model change."
        ),
    )
    status: str = Field(
        ...,
        max_length=20,
        description=(
            "Current project lifecycle status. "
            "One of: 'PLANNED', 'DESIGN', 'BID', 'IN_PROGRESS', "
            "'COMPLETED', 'DEFERRED', 'CANCELLED'."
        ),
    )
    estimated_cost: Optional[float] = Field(
        None,
        ge=0.0,
        description="Total estimated project cost in USD.  None when not yet budgeted.",
    )
    start_date: Optional[datetime] = Field(
        None,
        description="Planned or actual construction start date (UTC).",
    )
    end_date: Optional[datetime] = Field(
        None,
        description=(
            "Planned or actual project completion date (UTC).  "
            "None for indefinite or multi-phase projects."
        ),
    )
    location_description: str = Field(
        ...,
        max_length=255,
        description=(
            "Human-readable description of the affected location "
            "(e.g. 'Mass Ave from Pleasant St to Lake St')."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for CIP-specific attributes such as "
            "funding_source, department, fiscal_year, ward, "
            "or PDF page reference."
        ),
    )


class TePermit(AuditFields):
    """
    Gold-tier Building / Development Permit entity.
    Schema mirrors gold.te_permit exactly.

    Captures a single permit application as issued by a municipality's
    Building Department, Inspectional Services Division (ISD), or
    OpenGov / ViewPoint permit-management platform.

    Cross-model linkage
    -------------------
    ``te_party_pk_applicant`` is a **foreign key into** ``gold.te_party``.
    This proves that the Permit model is a *first-class citizen* of the
    Universal Identity Graph: a permit record can be joined back to the
    full owner / contractor ``TeParty`` record without string matching.

    The 'what was built / altered and who asked' dimension:
    * ``TeParty``        answers *who* (applicant / contractor)
    * ``TeZoning``       answers *what is permitted on this parcel*
    * ``TeInfraProject`` answers *what public-works work is nearby*
    * ``TePermit``       answers *what private construction was permitted and when*

    Supported ``permit_type`` vocabulary (open-ended ``str``):

    ======================  =====================================================
    permit_type             Description
    ======================  =====================================================
    ``COMMERCIAL_BUILD``    New commercial construction
    ``RESIDENTIAL_NEW``     New residential construction
    ``RESIDENTIAL_RENO``    Residential addition / alteration / renovation
    ``ELECTRICAL``          Electrical installation or upgrade
    ``PLUMBING``            Plumbing installation or repair
    ``MECHANICAL``          HVAC or mechanical system work
    ``DEMOLITION``          Full or partial building demolition
    ``SIGN``                Signage installation or replacement
    ``SOLAR``               Solar panel / PV system installation
    ``SHORT_TERM_RENTAL``   Short-term rental registration
    ``OTHER``               Catch-all for unlisted permit types
    ======================  =====================================================

    Supported ``status`` vocabulary:

    ================  =====================================================
    status            Description
    ================  =====================================================
    ``SUBMITTED``     Application received; not yet reviewed
    ``UNDER_REVIEW``  Inspector / plan review in progress
    ``APPROVED``      Permit issued; work may commence
    ``INSPECTIONS``   Active inspections phase
    ``CLOSED``        Final inspection passed; permit closed
    ``EXPIRED``       Permit lapsed without final inspection
    ``REVOKED``       Permit withdrawn or cancelled by the town
    ================  =====================================================
    """
    model_config = ConfigDict(from_attributes=True)

    te_permit_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    permit_number: str = Field(
        ...,
        max_length=50,
        description=(
            "Official permit number as issued by the Building Department "
            "(e.g. 'B-26-0451').  Used as the stable natural key for "
            "identity resolution."
        ),
    )
    permit_type: str = Field(
        ...,
        max_length=50,
        description=(
            "Controlled-vocabulary permit classifier "
            "(e.g. 'RESIDENTIAL_RENO', 'COMMERCIAL_BUILD', 'SOLAR'). "
            "New types require only a config entry — no model change."
        ),
    )
    status: str = Field(
        ...,
        max_length=20,
        description=(
            "Current permit lifecycle status. "
            "One of: 'SUBMITTED', 'UNDER_REVIEW', 'APPROVED', "
            "'INSPECTIONS', 'CLOSED', 'EXPIRED', 'REVOKED'."
        ),
    )
    application_date: datetime = Field(
        ...,
        description="Date the permit application was submitted (UTC-aware).",
    )
    approval_date: Optional[datetime] = Field(
        None,
        description=(
            "Date the permit was issued / approved (UTC-aware).  "
            "None when the permit is still under review."
        ),
    )
    estimated_value: Optional[float] = Field(
        None,
        ge=0.0,
        description=(
            "Declared project value in USD as stated on the permit application.  "
            "None when not disclosed."
        ),
    )
    te_party_pk_applicant: int = Field(
        ...,
        description=(
            "Foreign key → ``gold.te_party.te_party_pk``.  "
            "Identifies the permit applicant (owner or contractor) as a "
            "resolved Party entity in the Universal Identity Graph."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for portal-specific attributes such as "
            "contractor_license, parcel_id, address, inspector_name, "
            "number_of_units, or OpenGov record URL."
        ),
    )


class TeBroadband(AuditFields):
    """
    Gold-tier Broadband / Digital Connectivity record.
    Schema mirrors gold.te_broadband exactly.

    Captures a single provider-technology-location availability record as
    published in the FCC Broadband Fabric (Form 477 / BDC filing) or an
    equivalent state / municipal broadband survey.

    Each row answers: "At this location, provider X offers technology Y at
    speeds of up to D Mbps down / U Mbps up."  Multiple rows may share the
    same ``geo_value`` — one per (provider, technology) combination serving
    that location.

    The 'who can connect and at what speed' dimension of the identity graph:
    * ``TeParty``     answers *who* owns the parcel / lives at the address
    * ``TeZoning``    answers *what is permitted at this address*
    * ``TePermit``    answers *what was recently built / altered here*
    * ``TeBroadband`` answers *what connectivity is available at this address*

    Supported ``geo_level`` vocabulary:

    =============  =====================================================
    geo_level      geo_value example
    =============  =====================================================
    ``ADDRESS``    ``"14 Magnolia St, Arlington MA 02474"``
    ``GEOHASH``    ``"drt2zh"``  (precision-6 centroid)
    ``BLOCK``      ``"250173524001000"``  (Census block GEOID 15-char)
    ``ZIPCODE``    ``"02474"``
    ``TRACT``      ``"25017352400"``  (Census tract GEOID 11-char)
    =============  =====================================================

    Supported ``tech_type`` vocabulary (maps to FCC Technology Code):

    ==========  ====  =====================================================
    tech_type   Code  Description
    ==========  ====  =====================================================
    ``FIBER``     50  Fiber-to-the-premises (FTTP)
    ``CABLE``     40  Cable / HFC (DOCSIS 3.x)
    ``DSL``       10  Asymmetric DSL (ADSL / VDSL)
    ``FIXED_W``   70  Licensed fixed wireless (e.g. CBRS, mmWave)
    ``SATELLITE`` 60  Geostationary or LEO satellite
    ``LTE``       30  LTE / 4G mobile broadband
    ``NR``        31  5G NR (New Radio) fixed / mobile
    ``OTHER``      0  Unlisted technology
    ==========  ====  =====================================================
    """
    model_config = ConfigDict(from_attributes=True)

    te_broadband_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    geo_level: str = Field(
        ...,
        max_length=20,
        description=(
            "Geographic granularity of the record. "
            "One of: 'ADDRESS', 'GEOHASH', 'BLOCK', 'ZIPCODE', 'TRACT'."
        ),
    )
    geo_value: str = Field(
        ...,
        max_length=255,
        description=(
            "Identifier for the geographic unit at geo_level "
            "(e.g. a full street address or a 15-char Census block GEOID)."
        ),
    )
    provider_name: str = Field(
        ...,
        max_length=100,
        description=(
            "Broadband provider / ISP name as it appears in the FCC filing "
            "(e.g. 'Verizon', 'Comcast', 'RCN')."
        ),
    )
    tech_type: str = Field(
        ...,
        max_length=20,
        description=(
            "Controlled-vocabulary technology classifier "
            "(e.g. 'FIBER', 'CABLE', 'DSL'). "
            "Maps to FCC Technology Code; new types require only a config "
            "entry — no model change."
        ),
    )
    max_down_mbps: float = Field(
        ...,
        ge=0.0,
        description=(
            "Maximum advertised download speed in Mbps as declared in the "
            "FCC BDC filing.  0.0 when unavailable."
        ),
    )
    max_up_mbps: float = Field(
        ...,
        ge=0.0,
        description=(
            "Maximum advertised upload speed in Mbps as declared in the "
            "FCC BDC filing.  0.0 when unavailable."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for FCC-specific attributes such as "
            "fcc_tech_code, frn, provider_id, holding_company, "
            "low_latency_flag, business_residential_code, or filing_date."
        ),
    )


class TeClimateZone(AuditFields):
    """
    Gold-tier Climate / Environmental Risk Zone entity.
    Schema mirrors gold.te_climate_zone exactly.

    Captures a single spatial risk zone as published in FEMA's National Flood
    Hazard Layer (NFHL), NOAA heat-island datasets, EPA wetland maps, or any
    other raster/vector climate-risk source.  Each record stores the zone
    classification and its GeoJSON geometry so it can be spatially joined to
    any other entity in the identity graph (parcel, census tract, address).

    The 'what environmental risk exists here' dimension:
    * ``TeParty``        answers *who* owns the affected parcel
    * ``TeZoning``       answers *what is permitted* at this location
    * ``TePermit``       answers *what was recently built* here
    * ``TeBroadband``    answers *what connectivity* is available
    * ``TeClimateZone``  answers *what environmental risk* overlaps this location

    Supported ``zone_type`` vocabulary (open-ended ``str``):

    ===================  =====================================================
    zone_type            Description / source
    ===================  =====================================================
    ``FLOOD_100YR``      FEMA 1% annual chance flood zone (AE / AH / AO)
    ``FLOOD_500YR``      FEMA 0.2% annual chance flood zone (X-shaded)
    ``FLOOD_FLOODWAY``   FEMA regulatory floodway (zero-rise corridor)
    ``HEAT_ISLAND``      Urban heat island — surface temp anomaly ≥ 3 °C
    ``WETLAND``          NWI wetland / riparian buffer (EPA / USFWS)
    ``COASTAL_EROSION``  NOAA coastal erosion hazard area
    ``DROUGHT``          USDM Drought Monitor intensity zone
    ``WILDFIRE``         CAL FIRE / USFS wildfire hazard severity zone
    ``OTHER``            Catch-all for unlisted zone types
    ===================  =====================================================

    Supported ``risk_level`` vocabulary:

    ==============  =====================================================
    risk_level      Description
    ==============  =====================================================
    ``HIGH``        Immediate life-safety or property hazard
    ``MODERATE``    Significant risk; insurance / mitigation advisable
    ``LOW``         Residual or background risk
    ``UNDETERMINED``Zone present but risk not yet quantified
    ==============  =====================================================

    Spatial geometry
    ----------------
    ``geometry_type`` and ``geometry_coordinates`` mirror the GeoJSON
    ``geometry`` object fields exactly, so a Gold record can be
    reconstructed into a valid ``shapely`` geometry or written to a
    GeoDataFrame without any transformation:

    .. code-block:: python

        import shapely.geometry
        geom = shapely.geometry.shape({
            "type": record["geometry_type"],
            "coordinates": record["geometry_coordinates"],
        })
    """
    model_config = ConfigDict(from_attributes=True)

    te_zone_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    zone_type: str = Field(
        ...,
        max_length=30,
        description=(
            "Controlled-vocabulary risk zone classifier "
            "(e.g. 'FLOOD_100YR', 'HEAT_ISLAND', 'WETLAND'). "
            "New types require only a config entry — no model change."
        ),
    )
    risk_level: str = Field(
        ...,
        max_length=15,
        description=(
            "Risk severity classification. "
            "One of: 'HIGH', 'MODERATE', 'LOW', 'UNDETERMINED'."
        ),
    )
    geometry_type: str = Field(
        ...,
        max_length=20,
        description=(
            "GeoJSON geometry type string "
            "(e.g. 'Polygon', 'MultiPolygon', 'Point', 'LineString')."
        ),
    )
    geometry_coordinates: Any = Field(
        ...,
        description=(
            "GeoJSON coordinate array matching the geometry_type.  "
            "Stored as a native Python list/dict — serialised to JSON "
            "before writing to Parquet to preserve type fidelity."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for source-specific attributes such as "
            "fema_flood_zone, fema_dfirm_id, fip_code, effective_date, "
            "source_dataset, census_tract, or feature_id."
        ),
    )


class TeEquityIndex(AuditFields):
    """
    Gold-tier Environmental Justice / Equity Burden Index record.
    Schema mirrors gold.te_equity_index exactly.

    Captures a single EJ indicator score for a defined geographic unit, as
    derived from EPA EJScreen, the White House CEJST (Climate and Economic
    Justice Screening Tool), MassEJ, or any equivalent burden-index dataset.

    Each row answers: "At this geographic unit, this EJ index assigns a burden
    score of X (at the Y-th national percentile) — and therefore qualifies /
    does not qualify as a disadvantaged community."

    The 'who bears disproportionate environmental burden' dimension:
    * ``TeParty``        answers *who* lives or owns property at the location
    * ``TeZoning``       answers *what is permitted* at this location
    * ``TeClimateZone``  answers *what physical hazard* overlaps this location
    * ``TeEquityIndex``  answers *what cumulative burden* this community carries

    Supported ``index_name`` vocabulary (open-ended ``str``):

    ===============  =====================================================
    index_name       Description / source
    ===============  =====================================================
    ``EPA_EJSCREEN``  EPA EJScreen — 13 environmental + 6 demographic indicators
    ``CEQ_CEJST``     White House CEJST — 8 burden categories, DOE/DOT/EPA
    ``MASS_EJ``       MA EEA Environmental Justice Policy populations
    ``CDC_SVI``       CDC Social Vulnerability Index (4 themes, 15 vars)
    ``CUSTOM``        Municipality-defined composite index
    ===============  =====================================================

    Supported ``geo_level`` vocabulary:

    ================  =====================================================
    geo_level         geo_value example
    ================  =====================================================
    ``CENSUS_TRACT``  ``"25017352400"``  (11-char Census GEOID)
    ``BLOCK_GROUP``   ``"250173524001"`` (12-char Census GEOID)
    ``ZIPCODE``       ``"02474"``
    ``GEOHASH``       ``"drt2zh"``  (precision-6)
    ``TOWN``          ``"arlington-ma"``
    ================  =====================================================
    """
    model_config = ConfigDict(from_attributes=True)

    te_equity_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    geo_level: str = Field(
        ...,
        max_length=20,
        description=(
            "Geographic granularity of the record. "
            "One of: 'CENSUS_TRACT', 'BLOCK_GROUP', 'ZIPCODE', 'GEOHASH', 'TOWN'."
        ),
    )
    geo_value: str = Field(
        ...,
        max_length=50,
        description=(
            "Identifier for the geographic unit at geo_level "
            "(e.g. Census GEOID '25017352400' or zip '02474')."
        ),
    )
    index_name: str = Field(
        ...,
        max_length=30,
        description=(
            "Controlled-vocabulary EJ index identifier "
            "(e.g. 'EPA_EJSCREEN', 'CEQ_CEJST', 'MASS_EJ'). "
            "New indices require only a config entry — no model change."
        ),
    )
    burden_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description=(
            "Composite burden / percentile score for this geographic unit "
            "as reported by the source index.  Range is 0.0–100.0 where "
            "100 = highest burden.  Semantics vary by index_name."
        ),
    )
    is_disadvantaged: bool = Field(
        ...,
        description=(
            "True when the source index classifies this unit as a "
            "'disadvantaged' or 'EJ' community under its threshold criteria."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for index-specific indicator breakdowns such as "
            "pm25_percentile, lead_paint_pct, low_income_pct, "
            "superfund_proximity, reference_year, or data_version."
        ),
    )


class TeTownProfile(AuditFields):
    """
    Gold-tier Town Profile entity — LLM Synthesis (Domain 11).
    Schema mirrors gold.te_town_profile exactly.

    Captures the AI-synthesised narrative intelligence for a municipality:
    neighbourhood vibes, major employers, political landscape, housing
    character, and the NIMBY/YIMBY index that predicts development friction.

    Generated by an LLM (Gemini, OpenAI, or Anthropic) from publicly
    available signals.  Each record is a snapshot — append-only, never
    updated in place.

    The 'what kind of place is this' dimension of the identity graph.
    """
    model_config = ConfigDict(from_attributes=True)

    te_profile_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    profile_type: str = Field(
        ...,
        max_length=30,
        description=(
            "Profile variant classifier. "
            "Current values: 'FULL', 'SUMMARY', 'NEIGHBORHOOD'. "
            "New types require only a config entry — no model change."
        ),
    )
    town_name: str = Field(
        ...,
        max_length=100,
        description="Official municipality name (e.g. 'Arlington').",
    )
    state: str = Field(
        ...,
        max_length=2,
        description="2-letter USPS state abbreviation (e.g. 'MA').",
    )
    neighborhood_vibes: str = Field(
        ...,
        description=(
            "LLM-generated 2–4 sentence characterisation of the town's "
            "built environment, social character, and residential feel."
        ),
    )
    major_employers: List[str] = Field(
        default_factory=list,
        description="Top employers in the municipality as identified by the LLM.",
    )
    nimby_index: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description=(
            "LLM-assigned NIMBY/development-friction score (0=pro-development, "
            "10=highly resistant).  Used to predict permit approval timelines."
        ),
    )
    housing_character: str = Field(
        ...,
        max_length=50,
        description=(
            "Housing stock descriptor, e.g. 'OWNER_DOMINATED', "
            "'MIXED_TENURE', 'RENTER_MAJORITY'."
        ),
    )
    political_lean: str = Field(
        ...,
        max_length=20,
        description=(
            "Political characterisation, e.g. 'PROGRESSIVE', 'MODERATE', "
            "'CONSERVATIVE', 'MIXED'."
        ),
    )
    llm_model: str = Field(
        ...,
        max_length=60,
        description="LLM model identifier that generated this profile.",
    )
    generation_prompt_hash: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "SHA-256 hex digest of the prompt used to generate this record — "
            "enables cache invalidation and reproducibility checks."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for additional LLM outputs such as "
            "walkability_score, transit_score, school_rating, "
            "or raw LLM response tokens."
        ),
    )


class TeStrDynamics(AuditFields):
    """
    Gold-tier Short-Term Rental (STR) Dynamics entity — LLM Synthesis (Domain 12).
    Schema mirrors gold.te_str_dynamics exactly.

    Captures AI-synthesised STR market intelligence for a town: estimated
    Airbnb / VRBO yields, target guest demographics, peak seasons, and
    regulatory posture.

    Generated by an LLM from publicly available signals (Airbnb density,
    permit data, zoning overlays, event calendars).  Each record is a
    monthly snapshot — append-only.

    The 'what STR yield and regulatory risk exists here' dimension.
    """
    model_config = ConfigDict(from_attributes=True)

    te_str_pk: int = Field(
        ...,
        description="System-generated BigInt Primary Key (assigned by DB sequence).",
    )
    observation_month: str = Field(
        ...,
        max_length=7,
        description=(
            "Month of the STR snapshot in ISO format 'YYYY-MM' "
            "(e.g. '2026-03')."
        ),
    )
    estimated_yield_pct: float = Field(
        ...,
        ge=0.0,
        description=(
            "LLM-estimated annual gross rental yield as a percentage "
            "(e.g. 8.5 = 8.5 % gross yield)."
        ),
    )
    avg_nightly_rate_usd: float = Field(
        ...,
        ge=0.0,
        description="Estimated average nightly rate for a typical STR unit in USD.",
    )
    occupancy_rate_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Estimated annual occupancy rate as a percentage (0–100).",
    )
    target_guest_demo: str = Field(
        ...,
        max_length=50,
        description=(
            "Primary guest demographic segment, e.g. 'WEEKEND_TRIPPER', "
            "'REMOTE_WORKER', 'FAMILY_VACATION', 'SNOWBIRD'."
        ),
    )
    regulatory_posture: str = Field(
        ...,
        max_length=20,
        description=(
            "STR regulatory environment: 'PERMISSIVE', 'MODERATE', "
            "'RESTRICTIVE', 'BANNED'."
        ),
    )
    peak_seasons: List[str] = Field(
        default_factory=list,
        description=(
            "List of peak demand seasons, e.g. ['SUMMER', 'FALL_FOLIAGE', "
            "'MARATHON_WEEKEND']."
        ),
    )
    llm_model: str = Field(
        ...,
        max_length=60,
        description="LLM model identifier that generated this record.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for additional STR signals such as "
            "active_listings_count, yoy_yield_change, sweet_spot_neighborhoods, "
            "or regulatory_notes."
        ),
    )


class TePropertyAssessment(AuditFields):
    """
    Gold-tier Property Assessment record.

    One row per assessed parcel. Promotes all analytically useful fields from
    the assessor's Bronze record to first-class columns so the SQL agent can
    query them directly without unpacking the metadata JSON blob.

    The 'property.parquet' domain uses this model in place of TeParty.
    Owner identity is still linked via te_party_pk (FK → gold.te_party).
    """
    model_config = ConfigDict(from_attributes=True)

    te_property_pk: int = Field(
        ...,
        description="System PK assigned by identity linker (hash of parcel_id + te_source).",
    )
    parcel_id: str = Field(..., max_length=64, description="Assessor parcel identifier (natural key).")
    address: str = Field(..., max_length=255, description="Full street address.")
    zone_code: Optional[str] = Field(None, max_length=32, description="Zoning district code (e.g. 'R-2').")
    assessed_value: Optional[float] = Field(None, description="Total assessed value in USD.")
    year_built: Optional[int] = Field(None, description="Year structure was built.")
    building_type: Optional[str] = Field(None, max_length=64, description="Architectural style or building class.")
    lot_size_sqft: Optional[float] = Field(None, description="Lot area in square feet.")
    luc: Optional[str] = Field(None, max_length=16, description="Land use code (e.g. '101').")
    luc_description: Optional[str] = Field(None, max_length=128, description="Human-readable land use description.")
    beds: Optional[int] = Field(None, description="Number of bedrooms.")
    baths: Optional[float] = Field(None, description="Number of bathrooms (e.g. 2.5).")
    owner_name: Optional[str] = Field(None, max_length=255, description="Denormalized owner name (from TeParty.legal_name).")
    te_party_pk: Optional[int] = Field(None, description="FK → gold.te_party (property owner).")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible sidecar for remaining assessor fields (living_area, stories, etc.).",
    )


class TeParcel(AuditFields):
    """
    Gold-tier Parcel Geometry record.  Schema mirrors gold.te_parcel exactly.

    Captures the **authoritative GIS polygon** for a single parcel as
    published by the municipality's parcel feature service (e.g.
    Arlington's ``Parcels with CAMA`` ArcGIS layer).

    Why a separate model from ``TePropertyAssessment``?
    ---------------------------------------------------
    * ``TePropertyAssessment`` is the *assessor's tax record* — beds, baths,
      assessed value, year built.  Sourced from the Patriot Properties
      portal HTML scrape (Domain 01).
    * ``TeParcel`` is the *GIS parcel polygon* — geometry, lot size, edges,
      perimeter, longest edge, centroid.  Sourced from the town's own
      ArcGIS feature service.

    They are joined by ``parcel_id`` (the assessor's natural key).  Every
    parcel polygon should resolve cleanly to at most one assessment row;
    every assessment row should resolve to exactly one polygon.

    Computed fields
    ---------------
    Each polygon is enriched at scrape time with three computed numbers
    that are otherwise expensive to derive at report time:

    * ``edges_ft``         — list of ring edge lengths, feet (haversine).
    * ``perimeter_ft``     — sum of edge lengths, feet.
    * ``longest_edge_ft``  — longest single edge, feet (proxy for the
                              "frontage" dimension when the parcel touches
                              a street).
    * ``area_sqft``        — polygon area in square feet (shoelace formula
                              on the haversine-projected ring).
    * ``centroid_lat`` / ``centroid_lon`` — mean of ring vertices.

    Geometry
    --------
    ``geometry_type`` and ``geometry_coordinates`` mirror the GeoJSON
    ``geometry`` object exactly so a Gold record reconstructs into a valid
    ``shapely`` geometry without transformation.
    """
    model_config = ConfigDict(from_attributes=True)

    te_parcel_pk: int = Field(
        ...,
        description="System PK assigned by identity linker (hash of parcel_id + te_source).",
    )
    parcel_id: str = Field(
        ...,
        max_length=64,
        description="Assessor parcel identifier (natural key, e.g. '128.0-0003-0012.0').",
    )
    address: Optional[str] = Field(
        None,
        max_length=255,
        description="Full street address from the GIS attributes (may differ slightly from assessor record).",
    )
    geometry_type: str = Field(
        ...,
        max_length=20,
        description="GeoJSON geometry type ('Polygon' or 'MultiPolygon').",
    )
    geometry_coordinates: Any = Field(
        ...,
        description=(
            "GeoJSON coordinate array matching geometry_type.  Stored as a "
            "native Python list — serialised to JSON before Parquet write."
        ),
    )
    area_sqft: Optional[float] = Field(
        None,
        description="Polygon area in square feet (shoelace on haversine-projected ring).",
    )
    perimeter_ft: Optional[float] = Field(
        None,
        description="Polygon perimeter in feet (sum of haversine edge lengths).",
    )
    longest_edge_ft: Optional[float] = Field(
        None,
        description="Longest single edge of the outer ring in feet.",
    )
    edges_ft: List[float] = Field(
        default_factory=list,
        description="Ordered list of outer-ring edge lengths in feet.",
    )
    centroid_lat: Optional[float] = Field(
        None,
        description="Centroid latitude (mean of ring vertices, WGS-84).",
    )
    centroid_lon: Optional[float] = Field(
        None,
        description="Centroid longitude (mean of ring vertices, WGS-84).",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for source-specific GIS attributes such as "
            "MAP_PAR_ID, CAMA_ID, LOC_ID, owner name, land-use code, "
            "assessed values from the CAMA join, layer_id, source_dataset."
        ),
    )


class TeNonCompliance(AuditFields):
    """
    Gold-tier Land-Use / Zoning Non-Compliance polygon record.  Schema
    mirrors ``gold.te_noncompliance`` exactly.

    Despite the upstream layer being named "LandUse_NonCompliance", these
    rows are NOT regulatory enforcement cases.  They are **descriptive**
    polygons published by Arlington's planning GIS that flag every parcel
    whose recorded land-use code diverges from what its zoning permits —
    e.g. a duplex sitting in a single-family zone (legal pre-existing
    non-conforming use), or a commercial garage in a residential zone.

    Why this matters for buildability
    ---------------------------------
    A pre-existing non-conforming use can usually continue but cannot be
    expanded; a tear-down rebuild often forfeits the non-conforming
    status and the new structure must conform to current zoning.  So a
    parcel with a non-compliance polygon is materially different from a
    "clean" parcel even though both are perfectly legal today.

    The scraper writes one row per polygon — there are typically hundreds
    per town.  Report-side code resolves a parcel to its non-compliance
    rows by point-in-polygon, exactly the same pattern used by
    ``TeZoningOverlay``.
    """
    model_config = ConfigDict(from_attributes=True)

    te_violation_pk: int = Field(
        ...,
        description="System-generated BigInt PK assigned by identity linker.",
    )
    land_use_code: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "Land-use code from the assessor / planning database — typically "
            "a numeric MA Department of Revenue (DOR) classification code."
        ),
    )
    zone_code_numeric: Optional[int] = Field(
        None,
        description=(
            "Numeric internal zone code used by the GIS layer (NOT the "
            "alphanumeric bylaw code like 'R2' / 'NMF').  Resolve to the "
            "bylaw code via the parcel's TeZoning row when needed."
        ),
    )
    land_use_zone_diff: Optional[int] = Field(
        None,
        description=(
            "Divergence indicator (the layer's 'luzndiff' field) — a "
            "small-integer flag used by Arlington to grade severity of "
            "the non-compliance.  Higher values typically mean larger "
            "departure from current zoning."
        ),
    )
    status: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "Free-text status / classification published by the planning "
            "GIS (e.g. 'Pre-Existing Non-Conforming', 'Permitted Variance', "
            "'Open Violation').  Vocabulary is town-specific."
        ),
    )
    geometry_type: str = Field(
        ...,
        max_length=20,
        description="GeoJSON geometry type ('Polygon' or 'MultiPolygon').",
    )
    geometry_coordinates: Any = Field(
        ...,
        description=(
            "GeoJSON coordinate array matching geometry_type.  Stored as a "
            "native Python list — serialised to JSON before Parquet write."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for source-specific GIS attributes (raw "
            "FID, OBJECTID, source_dataset, layer_id, layer_name, "
            "Shape__Area, Shape__Length, etc.)."
        ),
    )


class TeEnvironmentalOverlay(AuditFields):
    """
    Gold-tier Environmental Overlay polygon record (wetlands + flood
    zones).  Schema mirrors ``gold.te_environmental_overlay`` exactly.

    A unified record for any **water/flood-related** spatial overlay a
    parcel might intersect.  The buildability brief uses these to answer:

      * "Is any portion of this lot inside a flood zone?" → yes/no + zone code
      * "Are there mapped wetlands on or adjacent to this lot?" → yes/no
      * "How does the preliminary 2023 FEMA update change the answer?"

    Sources merged into this single domain (one row per polygon, the
    ``category`` field discriminates):

      * "wetland"             — town wetlands inventory
      * "flood-effective"     — current FEMA NFHL panels (locally mirrored)
      * "flood-preliminary"   — preliminary FEMA updates (e.g. June 2023)

    Why one model for all three?
    ----------------------------
    The FEMA flood layers (effective + preliminary) share the same
    NFHL attribute schema (FLD_ZONE / ZONE_SUBTY / SFHA_TF / static_bfe).
    The wetlands layer publishes a different attribute set (CLASSIF /
    Acres_GIS) but answers the same "is this lot inside?" question.
    Keeping them in one parquet means the report-side spatial-join code
    runs once instead of three times and produces a unified
    "environmental constraints" section in the brief.
    """
    model_config = ConfigDict(from_attributes=True)

    te_overlay_pk: int = Field(
        ...,
        description="System-generated BigInt PK assigned by identity linker.",
    )
    category: str = Field(
        ...,
        max_length=32,
        description=(
            "Discriminator: 'wetland' / 'flood-effective' / "
            "'flood-preliminary'.  Determines which fields below are "
            "populated and how the report should label any hit."
        ),
    )
    zone_code: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "Primary classification code for the polygon — e.g. 'AE' / "
            "'X' / 'AO' for FEMA flood zones, or 'BVW' / 'IVW' / 'OW' "
            "for wetlands.  Sourced via config field-name candidates."
        ),
    )
    zone_subtype: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "Secondary classifier when present — e.g. FEMA ZONE_SUBTY "
            "('FLOODWAY', '0.2 PCT ANNUAL CHANCE FLOOD HAZARD')."
        ),
    )
    sfha_flag: Optional[str] = Field(
        None,
        max_length=8,
        description=(
            "FEMA Special Flood Hazard Area flag ('T' / 'F' / null).  "
            "Empty for wetland rows."
        ),
    )
    static_bfe: Optional[float] = Field(
        None,
        description=(
            "FEMA Base Flood Elevation in feet, where published.  "
            "Empty for wetlands and X-zone (non-SFHA) rows."
        ),
    )
    source_layer_name: str = Field(
        ...,
        max_length=128,
        description=(
            "Source FeatureServer / layer name — e.g. "
            "'ArlingtonMA_Wetlands', 'FloodHazards', "
            "'FloodHazards_Preliminary202306_clip'.  Preserves provenance "
            "so analysts can trace any row back to the upstream service."
        ),
    )
    geometry_type: str = Field(
        ...,
        max_length=20,
        description="GeoJSON geometry type ('Polygon' or 'MultiPolygon').",
    )
    geometry_coordinates: Any = Field(
        ...,
        description=(
            "GeoJSON coordinate array matching geometry_type.  Stored as a "
            "native Python list — serialised to JSON before Parquet write."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for source-specific attributes (raw FEMA "
            "fields, wetland CLASSIF / Source / Acres_GIS, layer_id, "
            "service_root, etc.)."
        ),
    )


class TeHistoricResource(AuditFields):
    """
    Gold-tier Historic Resource record.  Schema mirrors
    ``gold.te_historic_resource`` exactly.

    A unified record for any historic property — point (individual
    structure / burial ground / monument) or polygon (historic district /
    NRHP-listed area) — sourced from MACRIS, local Historic Commission
    inventories, or the National Register of Historic Places.

    Why one model for both points and polygons?
    -------------------------------------------
    The MACRIS data model uses the **same attribute schema** for the
    points layer (individual buildings) and the polygons layer (districts);
    the only difference is geometry.  Local town inventories follow the
    same pattern.  Keeping them in one Pydantic model means the buildability
    report can answer *"is this address listed?"* and *"is this address
    inside a historic district?"* with one parquet read.

    The ``resource_kind`` column ("Building", "Area", "Burial Ground",
    "Object", etc.) is the discriminator within a single geometry type;
    ``geometry_type`` tells you points-vs-polygon at the GIS level.
    """
    model_config = ConfigDict(from_attributes=True)

    te_resource_pk: int = Field(
        ...,
        description="System-generated BigInt PK assigned by identity linker.",
    )
    mhcn: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "MHC inventory number — e.g. 'ARL.123', 'BOS.10655'.  "
            "Natural key when present.  May be blank for non-MACRIS "
            "(e.g. local-only) inventory rows."
        ),
    )
    resource_kind: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "MACRIS resource type — 'Building', 'Area', 'Burial Ground', "
            "'Object', 'Structure', etc.  Sourced from the TYPE attribute."
        ),
    )
    legend: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "Short legend / classification — e.g. 'NRHP' (National Register "
            "of Historic Places), 'LHD' (Local Historic District), "
            "'NHL' (National Historic Landmark), 'Inv.' (Inventoried only)."
        ),
    )
    designation: Optional[str] = Field(
        None,
        max_length=255,
        description=(
            "Full legal historic designation string from MACRIS DESIGNATIO "
            "field — codes are space-separated (e.g. 'NRDIS NRTRA' = "
            "National Register District + National Register Travel/Transport)."
        ),
    )
    designation_date: Optional[str] = Field(
        None,
        max_length=255,
        description=(
            "Designation date string from MACRIS D_DATE — kept as string "
            "because the upstream value is multi-date semicolon-separated "
            "(e.g. '06/15/1987; 03/25/2021;')."
        ),
    )
    historic_name: Optional[str] = Field(
        None,
        max_length=512,
        description="Historic name of the resource (HISTORIC_N field).",
    )
    common_name: Optional[str] = Field(
        None,
        max_length=512,
        description="Common / current name of the resource (COMMON_NAM field).",
    )
    address: Optional[str] = Field(
        None,
        max_length=255,
        description=(
            "Street address as published by MACRIS (may be blank for "
            "districts and burial grounds).  Whitespace is collapsed."
        ),
    )
    town_name: str = Field(
        ...,
        max_length=128,
        description=(
            "Municipality name from MACRIS TOWN_NAME — the value used as "
            "the API filter when ingesting (e.g. 'Arlington', 'Boston')."
        ),
    )
    construction_date: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "Construction date as published — kept as string because the "
            "upstream values include circa values, ranges, and zeros for "
            "unknown ('c. 1880', '1880-1885', '0')."
        ),
    )
    architectural_style: Optional[str] = Field(
        None,
        max_length=255,
        description=(
            "Architectural style — sourced from ARCHITECTU on the points "
            "layer or ARCH on the polygons layer (the abbreviations differ "
            "between MACRIS layers — see config field-name candidates)."
        ),
    )
    architect: Optional[str] = Field(
        None,
        max_length=255,
        description="Architect / designer / maker (MAKER field).",
    )
    use_type: Optional[str] = Field(
        None,
        max_length=255,
        description=(
            "Historic / current use — semicolon-separated values "
            "(e.g. 'Single Dwelling; Workshop;')."
        ),
    )
    significance: Optional[str] = Field(
        None,
        max_length=2048,
        description=(
            "Historical significance themes — semicolon-separated values "
            "(e.g. 'Architecture; Community Planning; Industry;')."
        ),
    )
    demolished: Optional[str] = Field(
        None,
        max_length=16,
        description="Demolished flag from MACRIS ('Y'/'N'/blank).",
    )
    geometry_type: str = Field(
        ...,
        max_length=20,
        description=(
            "GeoJSON geometry type — 'Point' for individual structures, "
            "'Polygon'/'MultiPolygon' for historic districts, "
            "'LineString'/'MultiLineString' for polyline boundaries (e.g. "
            "Arlington's National Historic District is published as a "
            "single polyline outlining the district perimeter)."
        ),
    )
    geometry_coordinates: Any = Field(
        ...,
        description=(
            "GeoJSON coordinate array matching geometry_type.  Stored as a "
            "native Python list — serialised to JSON before Parquet write."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for source-specific attributes (raw_attributes, "
            "layer_id, layer_name, source_dataset, OBJECTID, etc.)."
        ),
    )


class TeZoningOverlay(AuditFields):
    """
    Gold-tier Zoning Overlay Polygon record.  Schema mirrors
    ``gold.te_zoning_overlay`` exactly.

    The **spatial counterpart** to ``TeZoning``.  Where ``TeZoning`` answers
    *"what does R2 / NMF / MBMF allow?"* (a textual bylaw record), this
    model answers *"where on the map does that district apply?"* — one row
    per polygon in a town's zoning + overlay GIS feature service.

    A single parcel can intersect multiple overlay polygons (base zone +
    Massachusetts §3A overlay + historic district + corridor overlay).
    Report-side point-in-polygon code joins these rows back to a parcel
    and produces the full applicable-rules stack.

    Why a separate model from ``TeClimateZone``?
    --------------------------------------------
    ``TeClimateZone`` carries a ``risk_level`` field that is meaningless
    for zoning overlays (NMF has no "HIGH / MODERATE / LOW" risk).  Keeping
    them separate avoids forcing semantically empty values into either
    schema and lets each domain evolve independently.

    Fields the scraper extracts when present, falling back to ``None`` /
    ``metadata`` otherwise — every field-name lookup is config-driven via
    ``zoning_overlay.code_field_candidates`` and
    ``zoning_overlay.type_field_candidates``.
    """
    model_config = ConfigDict(from_attributes=True)

    te_overlay_pk: int = Field(
        ...,
        description="System-generated BigInt PK assigned by identity linker.",
    )
    layer_name: str = Field(
        ...,
        max_length=128,
        description=(
            "Name of the GIS layer this polygon was sourced from "
            "(e.g. 'Zoning Districts', 'NMF Overlay'). Required."
        ),
    )
    zone_code: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "Zoning code extracted from feature attributes — e.g. 'R2', "
            "'NMF', 'MBMF', 'B2'.  May be None for layers that publish "
            "districts only by name (e.g. 'Russell Historic District')."
        ),
    )
    overlay_type: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "Classification of this polygon — e.g. 'Base', 'Multi-Family', "
            "'Historic', 'Mass Ave Corridor', 'Industrial / Office'. "
            "Sourced from the feature's OverlayType / DistrictType field "
            "where present, otherwise inferred from layer_name."
        ),
    )
    geometry_type: str = Field(
        ...,
        max_length=20,
        description="GeoJSON geometry type ('Polygon' or 'MultiPolygon').",
    )
    geometry_coordinates: Any = Field(
        ...,
        description=(
            "GeoJSON coordinate array matching geometry_type.  Stored as a "
            "native Python list — serialised to JSON before Parquet write."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Flexible sidecar for source-specific GIS attributes such as "
            "ZoneName, ZoneDesc, Notes, Article, Approval_Date, layer_id, "
            "source_dataset."
        ),
    )


# core/models.py
# End of Patch #179
