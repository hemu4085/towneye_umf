/**
 * API base URL (no trailing slash).
 * Production uses same-origin /api — vercel.json rewrites to Render (no CORS).
 * Dev uses Vite proxy when VITE_API_URL is unset; direct URL when set.
 */
function resolveApiBase() {
  if (import.meta.env.PROD) return '';
  return (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
}

export const API_BASE = resolveApiBase();
export const API_ROOT = API_BASE ? `${API_BASE}/api` : '/api';

const HEALTH_TIMEOUT_MS = 20000;

export async function checkApiHealth() {
  const url = `${API_ROOT}/health`;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const res = await fetch(url, {
        signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
        cache: 'no-store',
      });
      if (!res.ok) continue;
      const data = await res.json();
      if (data?.status === 'ok') return true;
    } catch {
      /* Render free tier cold start — retry once */
    }
  }
  return false;
}

export async function checkAccess(email) {
  const res = await fetch(`${API_ROOT}/auth/check`, {    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return res.json();
}

export async function joinWaitlist(data) {
  const res = await fetch(`${API_ROOT}/auth/waitlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Waitlist failed');
  return res.json();
}

export async function suggestAddresses(query, limit = 8) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await fetch(`${API_ROOT}/parcels/suggest?${params}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Address suggest failed');
  return data.suggestions || [];
}

export async function resolveParcel(address) {
  const res = await fetch(`${API_ROOT}/parcels/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Address lookup failed');
  return data;
}

export async function fetchReportAvailability(address) {
  const res = await fetch(`${API_ROOT}/reports/availability`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Could not check report availability');
  return data;
}

export async function generateReport(reportType, payload) {
  const res = await fetch(`${API_ROOT}/reports/${reportType}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Report generation failed');
  return data;
}
