/**
 * API client — production calls Render directly (avoids Vercel /api 401 from Deployment Protection).
 */

export const RENDER_ORIGIN = 'https://towneye-umf.onrender.com';

function resolveApiBase() {
  const fromEnv = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
  if (fromEnv) return fromEnv;
  if (import.meta.env.PROD) return RENDER_ORIGIN;
  return '';
}

export const API_BASE = resolveApiBase();
export const API_ROOT = API_BASE ? `${API_BASE}/api` : '/api';

function fetchSignal(ms) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  return { signal: ctrl.signal, cancel: () => clearTimeout(id) };
}

function looksLikeHtml(text) {
  const t = text.trim().toLowerCase();
  return t.startsWith('<!doctype') || t.startsWith('<html');
}

function friendlyFetchError(err, context) {
  if (err?.name === 'AbortError') {
    return new Error(`${context} timed out. Wait a few seconds and try again.`);
  }
  const msg = err?.message || '';
  if (msg.includes('Unexpected token') && msg.includes('DOCTYPE')) {
    return new Error(
      `${context} received a web page instead of API data. Hard refresh (Ctrl+Shift+R).`,
    );
  }
  if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
    return new Error(
      `${context} could not reach the API — check your connection or try again in a moment.`,
    );
  }
  return err instanceof Error ? err : new Error(String(err));
}

async function apiFetch(path, init = {}) {
  const p = path.startsWith('/') ? path : `/${path}`;
  const url = `${API_ROOT}${p}`;
  const mergedInit = {
    ...init,
    cache: 'no-store',
    credentials: 'omit',
    mode: 'cors',
    headers: {
      Accept: 'application/json',
      ...(init.headers || {}),
      'Cache-Control': 'no-cache',
    },
  };

  const res = await fetch(url, mergedInit);
  const bodyText = await res.text();

  if (looksLikeHtml(bodyText)) {
    throw new Error(
      `${contextLabel(path)} received a login page instead of API data (HTTP ${res.status}). ` +
        'If this persists, the API host may be misconfigured.',
    );
  }

  let parsed = null;
  try {
    parsed = bodyText.trim() ? JSON.parse(bodyText) : null;
  } catch {
    throw new Error(`Invalid JSON from API (HTTP ${res.status}).`);
  }

  return {
    ok: res.ok,
    status: res.status,
    headers: res.headers,
    async json() {
      return parsed;
    },
  };
}

function contextLabel(path) {
  if (path.includes('resolve')) return 'Address lookup';
  if (path.includes('reports')) return 'Report generation';
  return 'API request';
}

export async function getApiHealth() {
  const { signal, cancel } = fetchSignal(12000);
  try {
    const res = await apiFetch('/health', { signal });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  } finally {
    cancel();
  }
}

export async function checkApiHealth() {
  const data = await getApiHealth();
  return data?.status === 'ok';
}

export async function checkAccess(email) {
  const res = await apiFetch('/auth/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return res.json();
}

export async function joinWaitlist(data) {
  const res = await apiFetch('/auth/waitlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Waitlist failed');
  return res.json();
}

export async function fetchAddressIndex() {
  const res = await apiFetch('/parcels/address-index');
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Address index failed');
  return data;
}

export async function suggestAddresses(query, limit = 8) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const { signal, cancel } = fetchSignal(35000);
  try {
    const res = await apiFetch(`/parcels/suggest?${params}`, { signal });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Address suggest failed');
    return data.suggestions || [];
  } catch (err) {
    throw friendlyFetchError(err, 'Address search');
  } finally {
    cancel();
  }
}

export async function resolveParcel({ address, parcel_id, town_slug }) {
  const { signal, cancel } = fetchSignal(90000);
  try {
    const res = await apiFetch('/parcels/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, parcel_id, town_slug }),
      signal,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Address lookup failed');
    return data;
  } catch (err) {
    throw friendlyFetchError(err, 'Address lookup');
  } finally {
    cancel();
  }
}

export async function fetchReportAvailability({ address, parcel_id, town_slug }) {
  const { signal, cancel } = fetchSignal(25000);
  try {
    const res = await apiFetch('/reports/availability', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, parcel_id, town_slug }),
      signal,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not check report availability');
    return data;
  } catch (err) {
    throw friendlyFetchError(err, 'Report availability check');
  } finally {
    cancel();
  }
}

/** Town-scoped reports (e.g. Deal Radar) — no address required. */
export async function fetchTownReportAvailability(townSlug) {
  const { signal, cancel } = fetchSignal(25000);
  try {
    const res = await apiFetch('/reports/availability', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ town_slug: townSlug, address: '' }),
      signal,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not check report availability');
    return data;
  } catch (err) {
    throw friendlyFetchError(err, 'Report availability check');
  } finally {
    cancel();
  }
}

export async function generateReport(reportType, payload) {
  const { signal, cancel } = fetchSignal(180000);
  try {
    const res = await apiFetch(`/reports/${reportType}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Report generation failed');
    return data;
  } catch (err) {
    throw friendlyFetchError(err, 'Report generation');
  } finally {
    cancel();
  }
}
