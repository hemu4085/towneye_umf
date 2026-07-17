export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

export const API_ROOT = `${API_BASE}/api`;

export type SharedParcel = {
  address: string;
  parcel_id: string;
  town_slug: string;
  town_name?: string;
  lat?: number | null;
  lng?: number | null;
};

export type AddressSuggestion = {
  address: string;
  town_slug: string;
  town_name: string;
  parcel_id: string;
  score?: number;
};

export type ReportResponse = {
  report_type: string;
  html: string;
  data?: unknown;
  pdf_path?: string | null;
  download_url?: string | null;
  generated_seconds?: number | null;
};

function fetchSignal(ms: number) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  return { signal: ctrl.signal, cancel: () => clearTimeout(id) };
}

function friendlyFetchError(err: unknown, context: string): Error {
  if (err instanceof Error && err.name === "AbortError") {
    return new Error(`${context} timed out. Wait a few seconds and try again.`);
  }
  const msg = err instanceof Error ? err.message : String(err);
  if (msg === "Failed to fetch" || msg.includes("NetworkError")) {
    return new Error(
      `${context} could not reach the API at ${API_BASE}. Is the backend running?`,
    );
  }
  return err instanceof Error ? err : new Error(msg);
}

async function apiFetch(path: string, init: RequestInit = {}) {
  const url = `${API_ROOT}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init.headers || {}),
    },
  });
  const bodyText = await res.text();
  let parsed: unknown = null;
  try {
    parsed = bodyText.trim() ? JSON.parse(bodyText) : null;
  } catch {
    throw new Error(`Invalid JSON from API (HTTP ${res.status}).`);
  }
  return { ok: res.ok, status: res.status, json: async () => parsed };
}

export async function getApiHealth() {
  const { signal, cancel } = fetchSignal(12000);
  try {
    const res = await apiFetch("/health", { signal });
    if (!res.ok) return null;
    return res.json() as Promise<{ status?: string; towns?: string[] }>;
  } catch {
    return null;
  } finally {
    cancel();
  }
}

export async function suggestAddresses(
  query: string,
  townSlug?: string,
  limit = 8,
): Promise<AddressSuggestion[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (townSlug) params.set("town_slug", townSlug);
  const { signal, cancel } = fetchSignal(35000);
  try {
    const res = await apiFetch(`/parcels/suggest?${params}`, { signal });
    const data = (await res.json()) as { detail?: string; suggestions?: AddressSuggestion[] };
    if (!res.ok) throw new Error(data.detail || "Address suggest failed");
    return data.suggestions || [];
  } catch (err) {
    throw friendlyFetchError(err, "Address search");
  } finally {
    cancel();
  }
}

export async function resolveParcel(input: {
  address: string;
  parcel_id?: string;
  town_slug?: string;
}): Promise<SharedParcel> {
  const { signal, cancel } = fetchSignal(90000);
  try {
    const res = await apiFetch("/parcels/resolve", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    const data = (await res.json()) as SharedParcel & { detail?: string };
    if (!res.ok) throw new Error(data.detail || "Address lookup failed");
    return data;
  } catch (err) {
    throw friendlyFetchError(err, "Address lookup");
  } finally {
    cancel();
  }
}

export async function generateReport(
  reportType: string,
  payload: Record<string, unknown>,
): Promise<ReportResponse> {
  const { signal, cancel } = fetchSignal(180000);
  try {
    const res = await apiFetch(`/reports/${reportType}`, {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = (await res.json()) as ReportResponse & { detail?: string };
    if (!res.ok) throw new Error(data.detail || "Report generation failed");
    return data;
  } catch (err) {
    throw friendlyFetchError(err, "Report generation");
  } finally {
    cancel();
  }
}

export function reportDownloadUrl(downloadUrl: string | null | undefined): string | null {
  if (!downloadUrl) return null;
  if (downloadUrl.startsWith("http")) return downloadUrl;
  return `${API_BASE}${downloadUrl.startsWith("/") ? downloadUrl : `/${downloadUrl}`}`;
}

export async function fetchDealRadarConfig(townSlug: string) {
  const params = new URLSearchParams({ town_slug: townSlug });
  const { signal, cancel } = fetchSignal(25000);
  try {
    const res = await apiFetch(`/reports/deal-radar/config?${params}`, { signal });
    const data = (await res.json()) as { detail?: string };
    if (!res.ok) throw new Error(data.detail || "Could not load Deal Radar config");
    return data;
  } finally {
    cancel();
  }
}

export async function fetchClosingRiskRadarConfig(townSlug: string) {
  const params = new URLSearchParams({ town_slug: townSlug });
  const { signal, cancel } = fetchSignal(25000);
  try {
    const res = await apiFetch(`/reports/closing-risk-radar/config?${params}`, { signal });
    const data = (await res.json()) as { detail?: string };
    if (!res.ok) throw new Error(data.detail || "Could not load Closing Risk config");
    return data;
  } finally {
    cancel();
  }
}

export type DealRadarDeal = {
  rank?: number;
  parcel_id: string;
  address: string;
  owner_name?: string | null;
  zone_code?: string | null;
  score?: number;
  tenure_years?: number;
  assessed_value?: number | null;
  expansion_room_sqft?: number | null;
  utilization_pct?: number | null;
  signals?: string[];
  lat?: number | null;
  lng?: number | null;
};

export type DealRadarPayload = {
  executive_summary?: string;
  total_matches?: number;
  parcels_scanned?: number;
  deals?: DealRadarDeal[];
  criteria?: Record<string, unknown>;
};

export type ClosingRiskParcel = {
  rank?: number;
  parcel_id: string;
  address: string;
  owner_name?: string | null;
  zone_code?: string | null;
  risk_score?: number;
  open_permit_count?: number;
  expired_permit_count?: number;
  signals?: string[];
  signal_labels?: string[];
  assessed_value?: number | null;
  tenure_years?: number | null;
};

export type ClosingRiskPayload = {
  executive_summary?: string;
  total_matches?: number;
  parcels_scanned?: number;
  parcels?: ClosingRiskParcel[];
  criteria?: Record<string, unknown>;
};

export type BuildabilityAllowableUse = {
  use: string;
  status: string;
  zone_code: string;
};

export type BuildabilityDimensionalControl = {
  metric: string;
  limit: string;
  current: string;
};

export type BuildabilityEnvelope = {
  zone_code: string;
  label: string;
  is_overlay: boolean;
  rationale: string;
  lot_sqft: number;
  max_far?: number | null;
  max_gfa_sqft?: number | null;
  existing_gfa_sqft?: number | null;
  expansion_room_sqft?: number | null;
  pct_of_far_cap?: number | null;
  height_max_ft?: number | null;
  height_max_stories?: number | null;
  setback_front_ft?: number | null;
  setback_side_ft?: number | null;
  setback_rear_ft?: number | null;
  qualifies?: boolean | null;
};

export type BuildabilityWraparound = {
  label: string;
  status: string;
  detail: string;
  source: string;
  hit_count?: number;
};

export type BuildabilityZone = {
  code?: string | null;
  label?: string | null;
  layer?: string | null;
  rule?: {
    zone_code?: string;
    description?: string | null;
    allowed_uses?: string[];
    max_far?: number | null;
    min_lot_sqft?: number | null;
    min_frontage_ft?: number | null;
    max_height_ft?: number | null;
    setback_front_ft?: number | null;
    setback_side_ft?: number | null;
    setback_rear_ft?: number | null;
    is_overlay?: boolean;
    notes?: string | null;
  } | null;
};

export type BuildabilityDimensionalComparison = {
  columns: string[];
  rows: { standard: string; values: string[] }[];
};

export type BuildabilityEnvelopeCalc = {
  label: string;
  rationale: string;
  lines: string[];
  notes?: string | null;
};

export type BuildabilityDevelopmentOption = {
  num: number | string;
  option: string;
  path: string;
  process: string;
  lot_qualifies?: string;
  scale?: string;
  time_to_permit?: string;
  available: string;
  status: string;
};

export type BuildabilityProcessStage = {
  stage: string;
  body: string;
  duration: string;
  duration_basis?: string;
  path_type?: string;
};

export type BuildabilityPayload = {
  address?: string;
  parcel_id: string;
  town_slug: string;
  report_date?: string;
  map_block_lot?: string | null;
  headline_verdict_class?: string;
  headline_verdict_text?: string;
  overlay_narrative?: string;
  adu_law_note?: string;
  executive_sources?: string;
  primary_zone_code?: string | null;
  primary_overlay_code?: string | null;
  zoning_district?: string;
  has_overlay_election?: boolean;
  has_mbta_communities_overlay?: boolean;
  has_property_record?: boolean;
  property?: {
    owner_name?: string | null;
    year_built?: number | null;
    building_type?: string | null;
    luc?: string | null;
    luc_description?: string | null;
    beds?: number | null;
    baths?: number | null;
    book_page?: string | null;
    assessed_value?: number | null;
    lot_size_sqft?: number | null;
    finished_area_sqft?: number | null;
    last_sale_date?: string | null;
    last_sale_price?: number | null;
  };
  parcel?: {
    area_sqft?: number | null;
    longest_edge_ft?: number | null;
    perimeter_ft?: number | null;
    edges_ft?: number[];
    lot_shape?: string | null;
    centroid_lat?: number;
    centroid_lon?: number;
  };
  base_zones?: BuildabilityZone[];
  overlay_zones?: BuildabilityZone[];
  dimensional_comparison?: BuildabilityDimensionalComparison;
  envelopes?: BuildabilityEnvelope[];
  envelope_calcs?: BuildabilityEnvelopeCalc[];
  development_options?: BuildabilityDevelopmentOption[];
  development_options_footnote?: string | null;
  wraparound?: BuildabilityWraparound[];
  wraparound_section_title?: string;
  wraparound_summary?: string;
  process_pathway?: BuildabilityProcessStage[];
  process_pathway_footnote?: string | null;
  open_items?: string[];
  allowable_uses?: BuildabilityAllowableUse[];
  dimensional_controls?: BuildabilityDimensionalControl[];
  opportunity_score?: number;
  insights?: string[];
};

export type ZoningAllowableUse = BuildabilityAllowableUse;
export type ZoningDimensionalControl = BuildabilityDimensionalControl;
export type ZoningDimensionalComparison = BuildabilityDimensionalComparison;
export type ZoningZone = BuildabilityZone;

export type ZoningEnvelopeSummary = {
  zone_code?: string;
  label?: string;
  is_overlay?: boolean;
  max_gfa_sqft?: number | null;
  existing_gfa_sqft?: number | null;
  expansion_room_sqft?: number | null;
  max_far?: number | null;
  max_gfa_display?: string;
  existing_gfa_display?: string;
  expansion_display?: string;
};

export type ZoningGisMetadata = {
  district_name?: string | null;
  adoption_reference?: string | null;
  gis_notes?: string | null;
};

export type ZoningRegulatorySignal = {
  signal: string;
  severity: string;
  detail: string;
};

export type ZoningOverlayElection = {
  recommended_regime?: string;
  alternative_regime?: string | null;
  election_type?: string;
  rationale?: string;
  does_not_stack?: boolean;
  legal_basis?: string;
  citation?: string;
  memo_text?: string;
};

export type ZoningDevelopmentPath = {
  option: string;
  path: string;
  process: string;
  scale?: string;
  time_to_permit?: string;
  available?: string;
  lot_qualifies?: string;
  status?: string;
};

export type ZoningConstraint = {
  label: string;
  status: string;
  detail: string;
  source?: string;
};

export type ZoningProcessStage = {
  stage: string;
  body: string;
  duration: string;
  duration_basis?: string;
  path_type?: string;
};

export type ZoningPayload = {
  address?: string;
  parcel_id: string;
  town_slug: string;
  report_date?: string;
  primary_zone_code?: string | null;
  primary_overlay_code?: string | null;
  zoning_district?: string;
  has_overlay_election?: boolean;
  has_mbta_communities_overlay?: boolean;
  headline_verdict_class?: string;
  headline_verdict_text?: string;
  zoning_opportunity_score?: number;
  overlay_narrative?: string;
  overlay_election?: ZoningOverlayElection | null;
  regulatory_signals?: ZoningRegulatorySignal[];
  zoning_insights?: string[];
  base_zones?: (ZoningZone & { gis?: ZoningGisMetadata })[];
  overlay_zones?: (ZoningZone & { gis?: ZoningGisMetadata })[];
  base_labels?: string[];
  overlay_labels?: string[];
  allowable_uses?: ZoningAllowableUse[];
  dimensional_controls?: ZoningDimensionalControl[];
  dimensional_comparison?: ZoningDimensionalComparison;
  envelopes?: BuildabilityEnvelope[];
  envelope_summary?: ZoningEnvelopeSummary[];
  development_paths?: ZoningDevelopmentPath[];
  development_paths_footnote?: string | null;
  zoning_constraints?: ZoningConstraint[];
  process_pathway?: ZoningProcessStage[];
  process_pathway_footnote?: string | null;
  open_items?: string[];
  board_dockets_status?: { status?: string; detail?: string } | null;
  sources?: string;
  lot_size_sqft?: number | null;
  existing_gfa_sqft?: number | null;
  assessor_use_code?: string | null;
};

export type EntitlementsDocket = {
  event_type?: string;
  address?: string;
  docket?: string | null;
  status?: string;
  board?: string;
  summary?: string;
};

export type EntitlementsPayload = {
  address?: string;
  parcel_id: string;
  town_slug: string;
  report_date?: string;
  zoning_district?: string;
  primary_zone_code?: string | null;
  primary_overlay_code?: string | null;
  has_overlay_election?: boolean;
  has_mbta_communities_overlay?: boolean;
  headline_verdict_class?: string;
  headline_verdict_text?: string;
  overlay_narrative?: string;
  overlay_election?: ZoningOverlayElection | null;
  process_pathway?: ZoningProcessStage[];
  process_pathway_footnote?: string | null;
  development_paths?: ZoningDevelopmentPath[];
  zoning_constraints?: ZoningConstraint[];
  wraparound?: BuildabilityWraparound[];
  risk_signals?: ZoningRegulatorySignal[];
  board_dockets_status?: { status?: string; detail?: string } | null;
  dockets?: EntitlementsDocket[];
  open_items?: string[];
  lot_size_sqft?: number | null;
  existing_gfa_sqft?: number | null;
  sources?: string;
};

export type ProformaSiteSnapshot = {
  address?: string;
  parcel_id?: string;
  owner?: string | null;
  year_built?: number | null;
  building_type?: string | null;
  assessed_value?: number | null;
  lot_sqft_gis?: number | null;
  lot_sqft_regulatory?: number | null;
  finished_area_sqft?: number | null;
  last_sale_price?: number | null;
  last_sale_date?: string | null;
  primary_zone?: string | null;
  primary_overlay?: string | null;
  verdict_class?: string;
  verdict_text?: string;
};

export type ProformaMarket = {
  median_sale_price?: number | null;
  median_dom?: number | null;
  months_of_inventory?: number | null;
  months_supply?: number | null;
  price_per_sqft?: number | null;
  zipcode?: string | null;
  assessed_value?: number | null;
  indicative_sale_psf?: number;
  indicative_hard_cost_psf?: number;
  exit_pricing?: ProformaExitPricing;
};

export type ProformaExitPricing = {
  sale_psf_used?: number;
  method?: string;
  comp_median_resale_psf?: number | null;
  comp_adjusted_new_psf?: number | null;
  zip_price_per_sqft?: number | null;
  zip_adjusted_new_psf?: number | null;
  config_indicative_psf?: number;
  new_construction_premium_pct?: number;
};

export type ProformaComp = {
  parcel_id?: string;
  address?: string;
  distance_ft?: number;
  sale_price?: number;
  sale_date?: string;
  finished_sf?: number | null;
  price_per_sf?: number | null;
  year_built?: number | null;
};

export type ProformaComps = {
  status?: string;
  note?: string;
  rows?: ProformaComp[];
  radius_mi?: number;
  median_ppsf?: number | null;
  sources?: string[];
};

export type ProformaEquityReturns = {
  ltc_pct?: number;
  construction_loan?: number;
  equity_required?: number;
  net_sale_proceeds?: number;
  equity_profit?: number;
  equity_multiple?: number | null;
  equity_irr_pct?: number | null;
  hold_months?: number;
};

export type ProformaOverlayEconomics = {
  base_scenario?: string;
  primary_scenario?: string;
  profit_delta?: number;
  roi_delta_pct?: number;
  units_delta?: number;
  gfa_delta?: number;
  equity_multiple_delta?: number | null;
};

export type ProformaInvestorVerdict = {
  rating?: "pursue" | "caution" | "pass" | string;
  label?: string;
  summary?: string;
};

export type ProformaInvestorExhibit = {
  report_title?: string;
  address?: string;
  parcel_id?: string;
  prepared_on?: string;
  investor_verdict?: string;
  investor_verdict_label?: string;
  investor_thesis?: string;
  recommended_regime?: string | null;
  units?: number | null;
  total_gfa?: number | null;
  equity_required?: number | null;
  equity_profit?: number | null;
  equity_multiple?: number | null;
  equity_irr_pct?: number | null;
  project_roi_pct?: number | null;
  sale_proceeds?: number | null;
  total_project_cost?: number | null;
  exit_sale_psf?: number | null;
  exit_pricing_method?: string;
  land_basis?: number | null;
  land_basis_source?: string;
  overlay_profit_uplift?: number | null;
  overlay_equity_uplift?: number | null;
  key_risks?: string[];
};

export type ProformaEnvelope = {
  label: string;
  max_far?: number | null;
  max_gfa_sqft?: number | null;
  qualifies?: boolean | null;
  height_max_ft?: number | null;
  rationale?: string;
};

export type ProformaScenario = {
  name: string;
  zone_code?: string;
  is_overlay?: boolean;
  units: number;
  total_gfa: number;
  avg_unit_sf?: number;
  hard_cost: number;
  soft_cost: number;
  land_basis: number;
  permit_fees?: number;
  permit_fee_lines?: { label: string; amount: number }[];
  contingency?: number;
  carry_cost?: number;
  total_cost: number;
  sale_price: number;
  profit: number;
  margin_pct?: number;
  cost_per_sf?: number | null;
  sale_per_sf?: number | null;
  sale_per_unit?: number | null;
  cost_per_unit?: number | null;
  roi_pct: number;
  equity_returns?: ProformaEquityReturns;
  qualifies?: boolean | null;
  max_far?: number | null;
  notes?: string;
};

export type ProformaConstraint = {
  label: string;
  status: string;
  status_label: string;
  detail: string;
};

export type ProformaIrrGrid = {
  columns: string[];
  rows: { label: string; cells: number[] }[];
};

export type ProformaSensitivity = {
  low: number;
  mid: number;
  high: number;
};

export type ProformaOverrides = {
  hard_cost_psf?: number;
  sale_psf?: number;
  soft_cost_pct?: number;
  avg_unit_sf?: number;
  land_basis_mode?: "assessed" | "last_sale" | "acquisition";
  acquisition_price?: number;
  financing?: {
    annual_carry_pct?: number;
    construction_months?: number;
  };
  investor_financing?: {
    ltc_pct?: number;
    sellout_months?: number;
  };
};

export type ProformaPayload = {
  report_kind?: string;
  headline?: string;
  parcel_id: string;
  lot_sqft?: number | null;
  primary_zone?: string | null;
  primary_overlay?: string | null;
  assessed_value?: number | null;
  prepared_on?: string;
  site_snapshot?: ProformaSiteSnapshot;
  market?: ProformaMarket;
  exit_pricing?: ProformaExitPricing;
  comps?: ProformaComps;
  envelopes?: ProformaEnvelope[];
  scenarios?: ProformaScenario[];
  primary_scenario?: string | null;
  overlay_economics?: ProformaOverlayEconomics | null;
  investor_verdict?: ProformaInvestorVerdict;
  investor_exhibit?: ProformaInvestorExhibit;
  executive_summary?: string;
  irr_grid?: ProformaIrrGrid;
  return_sensitivity?: ProformaIrrGrid;
  sensitivity?: ProformaSensitivity;
  sensitivity_detail?: { case: string; roi_pct: number }[];
  constraints?: ProformaConstraint[];
  assumptions?: string[];
  data_sources?: string[];
  fallback?: boolean;
};

export type PermitTimelineKeyPermit = {
  permit_type: string;
  label: string;
  approval_body: string;
  sample_size?: number;
  issued_sample_size?: number;
  open_count?: number;
  avg_days?: number | null;
  median_days?: number | null;
  p25_days?: number | null;
  p75_days?: number | null;
  min_days?: number | null;
  max_days?: number | null;
  approval_rate_pct?: number | null;
  estimated_days_low?: number | null;
  estimated_days_mid?: number | null;
  estimated_days_high?: number | null;
  confidence?: string;
  note?: string;
  source?: string;
};

export type PermitTimelineDecision = {
  permit_number?: string;
  permit_type?: string;
  permit_type_label?: string;
  approval_body?: string;
  application_date?: string | null;
  decision_date?: string | null;
  calendar_days?: number | null;
  outcome?: string;
  address?: string;
  parcel_id?: string | null;
  description?: string | null;
  estimated_value?: number | null;
};

export type PermitTimelineSummary = {
  total_permits?: number;
  open_permits?: number;
  closed_or_issued?: number;
  avg_days_residential_reno?: number | null;
  avg_days_new_construction?: number | null;
  avg_days_commercial?: number | null;
  avg_days_zba_special_permit?: number | null;
  approval_rate_zba?: string;
  fastest_month?: string | null;
  slowest_month?: string | null;
  types_with_velocity?: number;
};

export type PermitTimelinePathStep = {
  step: string;
  body: string;
  estimated_days_low?: number | null;
  estimated_days_high?: number | null;
  estimated_days_mid?: number | null;
  optional?: boolean;
  note?: string;
};

export type PermitTimelinePayload = {
  report_type?: string;
  town_slug: string;
  town_name?: string;
  prepared_on?: string;
  summary_stats?: PermitTimelineSummary;
  type_stats?: PermitTimelineKeyPermit[];
  key_permits?: PermitTimelineKeyPermit[];
  recent_decisions?: PermitTimelineDecision[];
  month_extremes?: {
    fastest_month?: string | null;
    slowest_month?: string | null;
    by_month?: { month: string; median_days: number; count: number }[];
  };
  parcel_context?: {
    parcel_id?: string;
    address?: string | null;
    parcel_permit_count?: number;
    parcel_permits?: Array<Record<string, unknown>>;
    suggested_path?: PermitTimelinePathStep[];
  } | null;
  data_sources?: string[];
  pilot_message?: string;
  fallback?: boolean;
};

export type ParcelDossier = {
  town_slug: string;
  parcel_id: string;
  address: string;
  isd_url?: string;
  permits_portal_url?: string;
  permits_activity_url?: string;
  permits: {
    permits: Array<Record<string, unknown>>;
    open_count: number;
    expired_count: number;
    total_count: number;
  };
  violations: {
    status: string;
    note: string;
    rows: Array<{
      source?: string;
      violation_type?: string;
      status?: string;
      opened?: string;
      detail?: string;
      detail_full?: string;
      detail_url?: string | null;
      external_id?: string | null;
      link_kind?: string | null;
      link_label?: string | null;
      search_hint?: string | null;
    }>;
    open_count: number;
    isd_url?: string;
  };
};

export async function fetchParcelDossier(input: {
  town_slug: string;
  parcel_id: string;
  address?: string;
}): Promise<ParcelDossier> {
  const params = new URLSearchParams({
    town_slug: input.town_slug,
    parcel_id: input.parcel_id,
  });
  if (input.address) params.set("address", input.address);
  const { signal, cancel } = fetchSignal(60000);
  try {
    const res = await apiFetch(`/parcels/dossier?${params}`, { signal });
    const data = (await res.json()) as ParcelDossier & { detail?: string };
    if (!res.ok) throw new Error(data.detail || "Could not load parcel dossier");
    return data;
  } catch (err) {
    throw friendlyFetchError(err, "Parcel dossier");
  } finally {
    cancel();
  }
}

export type PrecedentResult = {
  id: string;
  docket?: string | null;
  address?: string;
  board?: string;
  relief_types?: string[];
  decision?: string;
  hearing_date?: string | null;
  summary?: string;
  zbl_sections?: string[];
  source_kind?: string;
  provenance?: string;
  source_url?: string | null;
  cite_ready?: boolean;
  parcel_id?: string | null;
  neighborhood?: string | null;
  memo_tip?: string | null;
  citation?: string;
  relevance_score?: number;
  relevance_reason?: string;
};

export type PrecedentSearchResponse = {
  town_slug: string;
  query: string;
  parcel_id?: string | null;
  address?: string | null;
  data_tier: string;
  disclaimer: string;
  gold_minutes_count: number;
  corpus_count: number;
  total_indexed: number;
  result_count: number;
  results: PrecedentResult[];
  facets: {
    boards: string[];
    relief_types: string[];
    decisions: string[];
  };
  official_sources: Array<{ label: string; url: string; note?: string }>;
  research_tips: string[];
};

export async function searchPrecedents(input: {
  town_slug: string;
  q?: string;
  board?: string;
  relief?: string;
  decision?: string;
  parcel_id?: string;
  address?: string;
  limit?: number;
}): Promise<PrecedentSearchResponse> {
  const params = new URLSearchParams({ town_slug: input.town_slug });
  if (input.q) params.set("q", input.q);
  if (input.board) params.set("board", input.board);
  if (input.relief) params.set("relief", input.relief);
  if (input.decision) params.set("decision", input.decision);
  if (input.parcel_id) params.set("parcel_id", input.parcel_id);
  if (input.address) params.set("address", input.address);
  if (input.limit) params.set("limit", String(input.limit));
  const { signal, cancel } = fetchSignal(45000);
  try {
    const res = await apiFetch(`/precedents/search?${params}`, { signal });
    const data = (await res.json()) as PrecedentSearchResponse & { detail?: string };
    if (!res.ok) throw new Error(data.detail || "Precedent search failed");
    return data;
  } catch (err) {
    throw friendlyFetchError(err, "Precedent search");
  } finally {
    cancel();
  }
}

