/** API base URL (no trailing slash). Empty = same origin (/api via Vite proxy or Vercel rewrite). */
export const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

const API = API_BASE ? `${API_BASE}/api` : '/api';

export async function checkAccess(email) {
  const res = await fetch(`${API}/auth/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return res.json();
}

export async function joinWaitlist(data) {
  const res = await fetch(`${API}/auth/waitlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || 'Waitlist failed');
  return res.json();
}

export async function suggestAddresses(query, limit = 8) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await fetch(`${API}/parcels/suggest?${params}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Address suggest failed');
  return data.suggestions || [];
}

export async function resolveParcel(address) {
  const res = await fetch(`${API}/parcels/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Address lookup failed');
  return data;
}

export async function fetchReportAvailability(address) {
  const res = await fetch(`${API}/reports/availability`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Could not check report availability');
  return data;
}

export async function generateReport(reportType, payload) {
  const res = await fetch(`${API}/reports/${reportType}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Report generation failed');
  return data;
}
