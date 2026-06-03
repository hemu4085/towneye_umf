/**
 * API client — same-origin /api via Vercel proxy; Render fallback when response isn't JSON.
 */

const RENDER_API_ROOT = 'https://towneye-umf.onrender.com/api';

function resolveApiBase() {
  if (import.meta.env.PROD) return '';
  return (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
}

export const API_BASE = resolveApiBase();
export const API_ROOT = API_BASE ? `${API_BASE}/api` : '/api';

function fetchSignal(ms) {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  return { signal: ctrl.signal, cancel: () => clearTimeout(id) };
}

/** Long report POSTs — Render first to avoid Vercel ~60s proxy timeout. */
const SLOW_REPORT_PATH = /^\/reports\/(homeowner-full|buildability|market|risk|proforma|lender)/;
const RENDER_FIRST_PATH = /^\/parcels\/(address-index|suggest)/;
/** Property Q&A — Vercel serverless /api/property-ask (excluded from Render rewrites). */
const SAME_ORIGIN_ONLY_PATH = /^\/property-ask$/;

/** Same-origin /api first; Render direct when proxy returns HTML or 5xx. */
function apiUrls(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  const viaVercel = `${API_ROOT}${p}`;
  if (!import.meta.env.PROD || viaVercel.startsWith('http')) {
    return [viaVercel];
  }
  if (SAME_ORIGIN_ONLY_PATH.test(p)) {
    return [viaVercel];
  }
  const viaRender = `${RENDER_API_ROOT}${p}`;
  if (SLOW_REPORT_PATH.test(p) || RENDER_FIRST_PATH.test(p)) {
    return [viaRender, viaVercel];
  }
  return [viaVercel, viaRender];
}

function looksLikeHtml(text) {
  const t = text.trim().toLowerCase();
  return t.startsWith('<!doctype') || t.startsWith('<html');
}

function shouldTryNextUrl(res, bodyText) {
  const trimmed = bodyText.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) return false;
  if (res.status === 401 || res.status === 403) return true;
  if (res.status === 502 || res.status === 503 || res.status === 504) return true;
  const ct = (res.headers.get('content-type') || '').toLowerCase();
  if (ct.includes('application/json')) return false;
  if (looksLikeHtml(bodyText)) return true;
  if (trimmed) return true;
  return false;
}

function friendlyFetchError(err, context) {
  if (err?.name === 'AbortError') {
    return new Error(
      `${context} timed out. Wait a few seconds and try again.`,
    );
  }
  const msg = err?.message || '';
  if (msg.includes('Unexpected token') && msg.includes('DOCTYPE')) {
    return new Error(
      `${context} received a web page instead of API data. Hard refresh (Ctrl+Shift+R) or try again in a moment.`,
    );
  }
  if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
    return new Error(`${context} could not reach the API — try again shortly.`);
  }
  return err instanceof Error ? err : new Error(String(err));
}

async function apiFetch(path, init = {}) {
  const urls = apiUrls(path);
  const mergedInit = {
    ...init,
    cache: 'no-store',
    credentials: 'omit',
    headers: {
      Accept: 'application/json',
      ...(init.headers || {}),
      'Cache-Control': 'no-cache',
    },
  };

  let lastError = null;
  for (const url of urls) {
    try {
      const res = await fetch(url, mergedInit);
      const bodyText = await res.text();
      if (shouldTryNextUrl(res, bodyText)) {
        lastError = new Error(`Non-JSON from ${url} (HTTP ${res.status})`);
        continue;
      }
      let parsed = null;
      try {
        parsed = bodyText.trim() ? JSON.parse(bodyText) : null;
      } catch {
        if (urls.length > 1) {
          lastError = new Error(`Invalid JSON from ${url} (HTTP ${res.status})`);
          continue;
        }
        throw new Error(
          `Invalid JSON from API (HTTP ${res.status}). Hard refresh the page.`,
        );
      }
      return {
        ok: res.ok,
        status: res.status,
        headers: res.headers,
        async json() {
          return parsed;
        },
      };
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError ?? new Error('API unavailable');
}

export async function checkApiHealth() {
  const { signal, cancel } = fetchSignal(12000);
  try {
    const res = await apiFetch('/health', { signal });
    if (!res.ok) return false;
    const data = await res.json();
    return data?.status === 'ok';
  } catch {
    return false;
  } finally {
    cancel();
  }
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

export async function askPropertyQuestion({ address, parcel_id, town_slug, question, history = [] }) {
  const { signal, cancel } = fetchSignal(90000);
  try {
    const res = await apiFetch('/property-ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        address,
        parcel_id,
        town_slug,
        question,
        history,
      }),
      signal,
    });
    const data = await res.json();
    if (!res.ok) {
      const detail = data?.detail || `Could not answer question (HTTP ${res.status})`;
      throw new Error(detail);
    }
    return data;
  } catch (err) {
    throw friendlyFetchError(err, 'Property Q&A');
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
