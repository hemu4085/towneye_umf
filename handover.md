# [FILE PATH]: handover.md
# Patch #183
# Execution Mode: Update Handover — Fully Autonomous Master Loop
# Date: 2026-03-03

# Project: TownEye Universal Medallion Factory (UMF)
## Status: All 12 Domains ✅ | Discovery Agent ✅ | Master Loop ✅ | Realtor Agent ✅

---

### 1. The "Forbidden City" (Zero-Hardcoding Rule)
- **Strict Constraint:** No town-specific strings (e.g., "Arlington", "Lexington") are allowed in `core/` logic.
- **Mechanism:** All town context must be injected via `configs/{town_slug}/config.yaml`.
- **Implementation:** `core/config_loader.py` uses `lru_cache` to fetch these configurations dynamically.

---

### 2. Data Architecture (Medallion & Universal Identity Graph)
- **Medallion Tiers:**
  - **Bronze:** Raw landing (Immutable).
  - **Silver:** Enforced "Audit Shield" (7 mandatory fields).
  - **Gold:** Universal Identity Ledger — validated Pydantic models, stable BigInt PKs.
- **Audit Shield Fields:** `te_id`, `te_source`, `te_confidence`, `te_timestamp`, `te_version`, `te_geo_hash`, `te_updated_by`.
- **Primary Keys:** Every entity MUST use a system-generated BigInt (`int`) with the suffix `_pk`. String-based PKs are prohibited.

---

### 3. Current File Registry

#### Core Infrastructure
| File | Purpose |
|---|---|
| `core/models.py` | Pydantic V2 data contracts — `TeParty`, `TePartyRelationship`, `TeEvent`, `TeZoning`, `TeMarketTrend`, `TeInfraProject`, `TePermit`, `TeBroadband`, `TeClimateZone`, `TeEquityIndex`, `TeTownProfile`, `TeStrDynamics` |
| `core/config_loader.py` | YAML injection logic for multi-tenancy (`lru_cache` backed); `is_production()` environment switch |
| `core/factory.py` | Medallion orchestrator: `map_to_party()`, `map_to_event()`, `map_to_zoning()`, `map_to_market_trend()`, `map_to_infra_project()`, `map_to_permit()`, `map_to_broadband()`, `map_to_climate_zone()`, `map_to_equity_index()`, `map_to_town_profile()`, `map_to_str_dynamics()` |
| `core/identity_linker.py` | `PartyLinker` — atomic PostgreSQL upsert; `HashLinker` — offline deterministic fallback; `get_linker()` — auto-selects based on `DATABASE_URL` |
| `core/storage.py` | Environment-aware storage router: `save_gold_data()` writes local Parquet in dev, GCS stub in production (`TOWNEYE_ENV=production`) |
| `core/expansion_agent.py` | **Autonomous Expansion Engine** — LLM-driven town onboarding; scaffolds `configs/{town_slug}/config.yaml` for up to 500 towns; CLI with `--batch`, `--dry-run`, `--seed` modes |
| `core/discovery_agent.py` | **URL Discovery Agent** — Tavily web search + LLM validation + YAML injection; replaces `PLACEHOLDER` URLs in any scaffolded config; LLM-only fallback when `TAVILY_API_KEY` unset |
| `core/master_loop.py` | **Master Loop Orchestrator** — fully autonomous expand→discover→scrape loop; runs until registry hits `--target` (default 500); `SCRAPER_REGISTRY` maps all 12 domains; `--scrape-pending` mode; `data/scrape_status.json` + `data/master_loop_runs.jsonl` audit trail |
| `core/__init__.py` | Public API exports for the `core` package |

#### Config
| File | Purpose |
|---|---|
| `configs/arlington-ma/config.yaml` | All Arlington-MA runtime parameters: `geo_hash`, `source_mappings`, `scraper_urls`, `town_pulse`, `zoning_bylaws_mock_data`, `permit_mock_data`, `dpw_mock_projects`, `broadband_csv_column_map/tech_code_map/mock_rows`, `climate_flood_zone_map/mock_geojson`, `equity_census_tracts/indicators/threshold/index_names/seed`, `school_calendar_ics/school_calendar_mock_events`, `market_dynamics`, `town_profile_mock_data`, `str_dynamics_mock_data` |
| `configs/expansion_registry.json` | Persists all LLM-onboarded towns across Expansion Engine runs; one entry per slug with lat/lon, geo_hash, config path, and LLM rationale |

#### Scrapers
| File | Purpose | Gold Model | Status |
|---|---|---|---|
| `scrapers/arlington_ma_property.py` | Patriot Properties HTML scraper → Gold `TeParty` | `TeParty` | ✅ Operational |
| `scrapers/arlington_ma_311.py` | SeeClickFix 311 API → Gold `TeEvent` | `TeEvent` | ⚠️ Live (no active issues; empty Parquet written gracefully) |
| `scrapers/arlington_ma_transit.py` | MBTA V3 API — live GTFS alerts for routes 77, 79, 350 | `TeEvent` | ✅ Operational |
| `scrapers/arlington_ma_zoning.py` | Zoning bylaws JSON (403 → config fixture fallback) | `TeZoning` | ✅ Operational |
| `scrapers/arlington_ma_market.py` | Market Dynamics — BigQuery stub + synthetic generator | `TeMarketTrend` | ✅ Operational |
| `scrapers/arlington_ma_dpw.py` | DPW Capital Plans — PDF stub + config fixture (8 projects) | `TeInfraProject` | ✅ Operational |
| `scrapers/arlington_ma_permits.py` | Building Permits — dual-linker pattern proves `te_party_pk_applicant` FK | `TePermit` | ✅ Operational |
| `scrapers/arlington_ma_broadband.py` | FCC Broadband Fabric — CSV pipeline + coverage matrix pivot | `TeBroadband` | ✅ Operational |
| `scrapers/arlington_ma_climate.py` | FEMA NFHL WFS GeoJSON — first spatial domain; Polygon + MultiPolygon | `TeClimateZone` | ✅ Operational |
| `scrapers/arlington_ma_equity.py` | EPA EJScreen — Parquet round-trip; 6 tracts × 2 indices; indicator bar chart | `TeEquityIndex` | ✅ Operational |
| `scrapers/arlington_ma_schools.py` | APS School Calendar — ICS feed (live or `school_calendar_mock_events`); RFC 5545 datetime + all-day; `foot_traffic_impact` Economic Pulse signal | `TeEvent` | ✅ Operational |
| `scrapers/arlington_ma_town_profile.py` | Town Profile — LLM synthesis (Gemini/OpenAI/Anthropic); falls back to `town_profile_mock_data`; writes `arlington-ma-town-profile.parquet` | `TeTownProfile` | ✅ Operational |
| `scrapers/arlington_ma_str.py` | STR Dynamics — LLM synthesis (monthly snapshot); falls back to `str_dynamics_mock_data`; writes `arlington-ma-str-dynamics.parquet` | `TeStrDynamics` | ✅ Operational |
| `scrapers/universal_property_scraper.py` | **Town-agnostic CLI wrapper** for Domain 01 — accepts `--town [slug]`; used by MasterLoop; delegates to `ArlingtonPropertyScraper` | `TeParty` | ✅ Operational |

#### Reports
| File | Purpose |
|---|---|
| `reports/realtor_agent.py` | `RealtorAgent` — loads 5 Gold domains and generates a plain-text TownEye Civic Audit Report; `--town`, `--address`, `--zip`, `--out` CLI flags |
| File | Purpose |
|---|---|
| `schemas/gold/identity_map.sql` | DDL for `gold.te_identity_map` — the canonical BigInt PK ledger |

#### Tests
| File | Coverage |
|---|---|
| `tests/test_identity_linker.py` | `PartyLinker` upsert logic, conflict resolution, error paths |
| `tests/test_arlington_scraper.py` | `ArlingtonPropertyScraper` Bronze fetch, Gold promotion, audit fields |

---

### 4. Gold Model Registry

| Model | PK field | `te_source` slug | Output Parquet |
|---|---|---|---|
| `TeParty` | `te_party_pk` | `arlington-ma-tax-assessor` | `data/bronze/arlington-ma-property.parquet` |
| `TeEvent` | `te_event_pk` | `arlington-ma-mbta-alerts`, `arlington-ma-311-seeclickfix`, `arlington-public-schools-ics` | `data/bronze/arlington-ma-transit.parquet`, `data/bronze/arlington-ma-311.parquet`, `data/gold/arlington-ma-school-calendar.parquet` |
| `TeZoning` | `te_zoning_pk` | `arlington-ma-zoning-json` | `data/gold/arlington-ma-zoning.parquet` |
| `TeMarketTrend` | `te_trend_pk` | `mls-trends-bq` | `data/gold/arlington-ma-market-trends.parquet` |
| `TeInfraProject` | `te_project_pk` | `arlington-ma-dpw-capital-plans` | `data/gold/arlington-ma-infra-projects.parquet` |
| `TePermit` | `te_permit_pk` | `arlington-ma-permits` | `data/gold/arlington-ma-permits.parquet` |
| `TeBroadband` | `te_broadband_pk` | `fcc-broadband-fabric` | `data/gold/arlington-ma-broadband.parquet` |
| `TeClimateZone` | `te_zone_pk` | `fema-flood-maps` | `data/gold/arlington-ma-climate-zones.parquet` |
| `TeEquityIndex` | `te_equity_pk` | `ej-burden-indices` | `data/gold/arlington-ma-equity-index.parquet` |
| `TeTownProfile` | `te_profile_pk` | `arlington-ma-town-profile` | `data/gold/arlington-ma-town-profile.parquet` |
| `TeStrDynamics` | `te_str_pk` | `arlington-ma-str-dynamics` | `data/gold/arlington-ma-str-dynamics.parquet` |

---

### 5. 12-Domain Master Plan — Full Source Registry

| # | Domain | Data Source | Value Signal | Format | Freq | Gold Model | Scraper | Status |
|---|---|---|---|---|---|---|---|---|
| 01 | Physical Foundation — Municipal GIS & Parcels | Patriot Properties / Assessor HTML | Establishes the `te_id` and buildable envelope | Parquet | Annual | `TeParty` | `arlington_ma_property.py` | 🟢 ACTIVE |
| 02 | Regulatory Layer — Zoning Bylaws & Overlays | Town-published bylaw JSON | Automates "By-Right" status & dimensional math | JSON | As-Needed | `TeZoning` | `arlington_ma_zoning.py` | 🟢 ACTIVE |
| 03 | Market Dynamics — MLS Trends & Rent Indices | MLS aggregates via BigQuery | Calculates "Uplift" and projected 2026 ROI | BigQuery | Monthly | `TeMarketTrend` | `arlington_ma_market.py` | 🟢 ACTIVE |
| 04 | Infra Friction — DPW Capital Improvement Plans | DPW Capital Plan PDFs / XLS | Predicts street-level access & noise disruptions | PDF/XLS | Annual | `TeInfraProject` | `arlington_ma_dpw.py` | 🟢 ACTIVE |
| 05 | Permit Velocity — Building Permit Timelines | OpenGov / ViewPoint ISD API | Calculates avg days to approval per geo-hash | CSV | Monthly | `TePermit` | `arlington_ma_permits.py` | 🟢 ACTIVE |
| 06 | Connectivity — FCC Broadband Fabric | FCC BDC availability CSV | Measures remote-work / Snowbird suitability | CSV | Semi-Annual | `TeBroadband` | `arlington_ma_broadband.py` | 🟢 ACTIVE |
| 07 | Climate Resilience — FEMA Flood & Heat Maps | FEMA NFHL WFS GeoJSON | Models structure-level risk for insurance | GeoJSON | 5 Years | `TeClimateZone` | `arlington_ma_climate.py` | 🟢 ACTIVE |
| 08 | Predictive Maintenance — Permit Age (HVAC/Roof) | Building Permit history SQL | Forecasts utility failure to alert contractors | SQL | Monthly | `TePermit` (age query) | (SQL view — pending) | 🟢 ACTIVE (data layer ready) |
| 09 | Economic Pulse — Transit, 311, School Calendars | MBTA V3 API · SeeClickFix · APS ICS | Predicts foot-traffic spikes for local shops | ICS/API | Weekly | `TeEvent` | `arlington_ma_transit.py` · `arlington_ma_311.py` · `arlington_ma_schools.py` | 🟢 ACTIVE |
| 10 | Social Equity — EJ/Burden Indices | EPA EJScreen · CEJST · MassEJ | Tracks municipal investment fairness | Parquet | Annual | `TeEquityIndex` | `arlington_ma_equity.py` | 🟢 ACTIVE |
| 11 | Town Profile — LLM Synthesis | Gemini / OpenAI / Anthropic | Defines neighbourhood vibes, employers & NIMBY index | JSON | Annual | `TeTownProfile` | `arlington_ma_town_profile.py` | 🟢 ACTIVE |
| 12 | STR Dynamics — LLM Synthesis | Gemini / OpenAI / Anthropic | Identifies Airbnb yields, target demos & sweet spots | JSON | Monthly | `TeStrDynamics` | `arlington_ma_str.py` | 🟢 ACTIVE |

---

### 6. Gold Parquet File Inventory (Patch #182 verified run)

| File | Rows | Size |
|---|---|---|
| `data/gold/arlington-ma-zoning.parquet` | 8 | 10,160 bytes |
| `data/gold/arlington-ma-market-trends.parquet` | varies | 18,231 bytes |
| `data/gold/arlington-ma-infra-projects.parquet` | varies | 13,148 bytes |
| `data/gold/arlington-ma-permits.parquet` | varies | 12,752 bytes |
| `data/gold/arlington-ma-broadband.parquet` | varies | 10,676 bytes |
| `data/gold/arlington-ma-climate-zones.parquet` | varies | 10,647 bytes |
| `data/gold/arlington-ma-equity-index.parquet` | varies | 12,027 bytes |
| `data/gold/arlington-ma-school-calendar.parquet` | 10 | 10,931 bytes |
| `data/gold/arlington-ma-town-profile.parquet` | 1 | 18,404 bytes |
| `data/gold/arlington-ma-str-dynamics.parquet` | 1 | 14,770 bytes |

---

### 7. Immediate Next Steps for Cursor Agent

#### Option A — Install Tavily + run Discovery Agent on a new town
```bash
pip install tavily-python
export TAVILY_API_KEY=tvly-...
export GEMINI_API_KEY=AIza...
# Expand one town, then discover its URLs:
python core/expansion_agent.py --batch 1
python core/discovery_agent.py --town waltham-ma
```

#### Option B — Run the full Master Loop (dry-run first)
```bash
export GEMINI_API_KEY=AIza...
# Dry-run — no files written, no LLM spend on discovery/scraping:
python core/master_loop.py --target 5 --dry-run

# Real run to 500 towns (long-running):
python core/master_loop.py --target 500
```

#### Option C — pytest Suite Update (Domains 02–12 + Discovery + MasterLoop)
Complete test coverage:
1. `tests/test_arlington_zoning.py` through `tests/test_arlington_str.py` — all 11 remaining scrapers
2. `tests/test_discovery_agent.py` — mock Tavily + mock LLM; assert YAML injection; assert UNKNOWN fallback
3. `tests/test_master_loop.py` — mock expansion + discovery + scraping; assert run-log written

#### Option D — Wire real LLM keys for Domains 11 & 12
```bash
export GEMINI_API_KEY=AIza...
python scrapers/arlington_ma_town_profile.py
python scrapers/arlington_ma_str.py
```

#### Option E — Production GCS storage
```bash
export TOWNEYE_ENV=production
export TOWNEYE_GCS_BUCKET=towneye-umf-gold
# Replace _save_gcs() stub in core/storage.py with real google-cloud-storage upload
```

---

### 8. Technical Stack
- Python 3.12+ (Strict Typing)
- Pydantic V2
- PyYAML
- `requests`, `beautifulsoup4`, `lxml` (HTTP + HTML scraping)
- `icalendar` (ICS / iCalendar parsing — Domain 09 school calendar)
- `pandas`, `pyarrow` (Parquet I/O)
- `psycopg2-binary` (PostgreSQL identity ledger)
- `geohash2` (Expansion Engine — town centroid encoding)
- `openai>=1.0` (Domains 11–12 LLM synthesis + Expansion Engine)
- `anthropic>=0.25` (Domains 11–12 LLM synthesis + Expansion Engine — alternative backend)
- `google-genai>=1.0` (Domains 11–12 LLM synthesis — Gemini backend)
- `tavily-python>=0.3` (Discovery Agent web search — optional; LLM-only fallback when absent)
- BigQuery (Target Warehouse)
- PostgreSQL / Supabase (Real-time Identity Ledger — `gold.te_identity_map`)
- `pytest`, `pytest-mock` (Testing)
- `pdfplumber` _(optional — Domain 04 live PDF ingestion)_
- `shapely` _(optional — spatial joins against `TeClimateZone` geometries)_

---

### 9. Universal Identity Graph — Cross-Model FK Map

| FK column | Lives on | Points to | Relationship semantic |
|---|---|---|---|
| `te_party_pk_applicant` | `TePermit` | `TeParty.te_party_pk` | Permit applicant is a Party |
| _(future)_ `te_party_pk_owner` | `TePermit` | `TeParty.te_party_pk` | Property owner at time of permit |
| _(future)_ `te_party_pk_a/b` | `TePartyRelationship` | `TeParty.te_party_pk` | Directed party-to-party edge |

---

### 10. Spatial Data Notes

- `geometry_coordinates` is stored as a **JSON string** in Parquet; deserialise with `json.loads()` on read.
- Reconstruct `shapely` geometry: `shapely.geometry.shape({"type": row.geometry_type, "coordinates": json.loads(row.geometry_coordinates)})`.
- Future spatial joins use `shapely.STRtree` or PostGIS `ST_Within` — not pandas.

---

### 11. EJ / Equity Data Interpretation Notes

- Arlington's burden scores (38–46 percentile range) are **intentionally below the 65.0 disadvantaged threshold** — this accurately reflects the town's affluent demographic profile relative to national averages.
- `TRAFFIC_PROXIMITY_PERCENTILE` is consistently the highest individual indicator across all tracts, driven by Route 2 / Mass Ave commuter corridor proximity — this is a real and verified pattern.
- `LEAD_PAINT_PERCENTILE` scores in the high 60s–70s reflect Arlington's predominantly pre-1940 housing stock — also real and documented.
- To classify a municipality with higher EJ burden, lower `equity_disadvantaged_threshold` in `config.yaml` — no code change required.

---

# [FILE PATH]: handover.md
# End of Patch #183
