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

export type ParcelDossier = {
  town_slug: string;
  parcel_id: string;
  address: string;
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
