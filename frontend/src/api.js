/**
 * API client — same-origin /api via Vercel, with Render direct fallback on 502.
 */

const RENDER_API_ROOT = 'https://towneye-umf.onrender.com/api';

function resolveApiBase() {
  if (import.meta.env.PROD) return '';
  return (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
}

export const API_BASE = resolveApiBase();
export const API_ROOT = API_BASE ? `${API_BASE}/api` : '/api';

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function apiUrls(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  const primary = `${API_ROOT}${p}`;
  if (primary.startsWith('http') || !import.meta.env.PROD) {
    return [primary];
  }
  const direct = `${RENDER_API_ROOT}${p}`;
  return primary === direct ? [primary] : [primary, direct];
}

/** Fetch API routes; retry 502/503 and fall back to Render when Vercel proxy is cold. */
async function apiFetch(path, init = {}) {
  const urls = apiUrls(path);
  const mergedInit = {
    ...init,
    cache: 'no-store',
    credentials: 'omit',
    headers: {
      ...(init.headers || {}),
      'Cache-Control': 'no-cache',
    },
  };

  let lastError = null;
  for (const url of urls) {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const res = await fetch(url, mergedInit);
        if (res.status === 502 || res.status === 503) {
          lastError = new Error(`HTTP ${res.status}`);
          await sleep(800 * (attempt + 1));
          continue;
        }
        return res;
      } catch (err) {
        lastError = err;
        await sleep(800 * (attempt + 1));
      }
    }
  }
  throw lastError ?? new Error('API unavailable');
}

export async function checkApiHealth() {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const res = await apiFetch('/health', {
        signal: AbortSignal.timeout(25000),
      });
      if (!res.ok) {
        await sleep(2000);
        continue;
      }
      const data = await res.json();
      if (data?.status === 'ok') return true;
    } catch {
      await sleep(2000);
    }
  }
  return false;
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

export async function suggestAddresses(query, limit = 8, signal) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await apiFetch(`/parcels/suggest?${params}`, {
    signal: signal ?? AbortSignal.timeout(45000),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Address suggest failed');
  return data.suggestions || [];
}

export async function resolveParcel(address) {
  const res = await apiFetch('/parcels/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address }),
    signal: AbortSignal.timeout(60000),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Address lookup failed');
  return data;
}

export async function fetchReportAvailability(address) {
  const res = await apiFetch('/reports/availability', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address }),
    signal: AbortSignal.timeout(60000),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Could not check report availability');
  return data;
}

export async function generateReport(reportType, payload) {
  const res = await apiFetch(`/reports/${reportType}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(120000),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Report generation failed');
  return data;
}
