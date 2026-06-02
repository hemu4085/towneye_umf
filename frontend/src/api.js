/**
 * API client — Vercel proxies /api to Render; long report jobs call Render directly.
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

function isReportPath(path) {
  return path.startsWith('/reports/');
}

/** Report POSTs hit Render first — avoids Vercel ~60s proxy timeout on slow generation. */
function apiUrls(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  const viaVercel = `${API_ROOT}${p}`;
  if (!import.meta.env.PROD || viaVercel.startsWith('http')) {
    return [viaVercel];
  }
  const viaRender = `${RENDER_API_ROOT}${p}`;
  if (isReportPath(path)) {
    return [viaRender, viaVercel];
  }
  return [viaVercel, viaRender];
}

function friendlyFetchError(err, context) {
  if (err?.name === 'AbortError') {
    return new Error(
      `${context} timed out while the server was waking up. Wait 30 seconds and try again.`,
    );
  }
  const msg = err?.message || '';
  if (msg === 'Failed to fetch' || msg.includes('NetworkError') || msg.includes('Load failed')) {
    return new Error(
      `${context} could not reach the API. The server may be starting (Render free tier) — try again shortly.`,
    );
  }
  return err instanceof Error ? err : new Error(String(err));
}

async function apiFetch(path, init = {}) {
  const urls = apiUrls(path);
  const mergedInit = {
    ...init,
    cache: 'no-store',
    credentials: 'omit',
    headers: { ...(init.headers || {}), 'Cache-Control': 'no-cache' },
  };

  let lastError = null;
  for (const url of urls) {
    try {
      const res = await fetch(url, mergedInit);
      if (res.status === 502 || res.status === 503) {
        lastError = new Error(`HTTP ${res.status}`);
        continue;
      }
      return res;
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

export async function suggestAddresses(query, limit = 8) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const { signal, cancel } = fetchSignal(35000);
  try {
    const res = await apiFetch(`/parcels/suggest?${params}`, { signal });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Address suggest failed');
    return data.suggestions || [];
  } finally {
    cancel();
  }
}

export async function resolveParcel(address) {
  const { signal, cancel } = fetchSignal(90000);
  try {
    const res = await apiFetch('/parcels/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
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

export async function fetchReportAvailability(address) {
  const { signal, cancel } = fetchSignal(90000);
  try {
    const res = await apiFetch('/reports/availability', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
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
