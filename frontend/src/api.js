/** API base URL (no trailing slash). Empty = same origin (/api via Vite proxy or Vercel rewrite). */
export const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export const API_ROOT = API_BASE ? `${API_BASE}/api` : '/api';

export async function checkApiHealth() {
  try {
    const res = await fetch(`${API_ROOT}/health`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return false;
    const data = await res.json();
    return data?.status === 'ok';
  } catch {
    return false;
  }
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
