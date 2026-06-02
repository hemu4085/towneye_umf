/**
 * Instant client-side address filter (Google-style) — mirrors backend street matching.
 */

const STREET_STOP = new Set([
  'ST', 'STREET', 'RD', 'ROAD', 'AVE', 'AVENUE', 'DR', 'DRIVE', 'LN', 'LANE', 'CT', 'COURT',
]);
const TOWN_STOP = new Set(['ARLINGTON', 'MA', 'MASSACHUSETTS', 'USA']);

function normalize(addr) {
  return (addr || '')
    .toUpperCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/ MASSACHUSETTS/g, '')
    .replace(/ MA/g, '')
    .trim();
}

function leadingNumber(addr) {
  const first = normalize(addr).split()[0] || '';
  const m = first.match(/^(\d+)/);
  return m ? m[1] : null;
}

function queryTokens(query, townNames = []) {
  const extra = new Set(TOWN_STOP);
  for (const name of townNames) {
    name
      .toUpperCase()
      .split(/\s+/)
      .forEach((p) => {
        if (p) extra.add(p);
      });
  }
  const tokens = new Set();
  for (const t of normalize(query).split(' ')) {
    if (!t || extra.has(t) || STREET_STOP.has(t)) continue;
    if (/^\d+$/.test(t)) tokens.add(t);
    else if (t.length >= 1) tokens.add(t);
  }
  return tokens;
}

function matchesStreet(street, tokens) {
  if (!tokens.size) return false;
  const norm = normalize(street);
  const digits = [...tokens].filter((t) => /^\d+$/.test(t));
  const words = [...tokens].filter((t) => !/^\d+$/.test(t));
  const lead = leadingNumber(street);

  for (const d of digits) {
    if (!lead) return false;
    if (!(lead === d || lead.startsWith(d))) return false;
  }
  for (const w of words) {
    if (w.length === 1) {
      if (!norm.split(' ').some((part) => part.startsWith(w))) return false;
    } else if (!norm.includes(w)) return false;
  }
  return true;
}

function scoreMatch(query, street, tokens) {
  const normQ = normalize(query);
  const normS = normalize(street);
  let score = 0.4;
  if (normQ && normS.includes(normQ)) score = 0.95;
  const digits = [...tokens].filter((t) => /^\d+$/.test(t));
  const lead = leadingNumber(street);
  if (digits.length && lead) {
    const d = digits.sort((a, b) => b.length - a.length)[0];
    if (lead === d) score = Math.max(score, 0.98);
    else if (lead.startsWith(d)) score = Math.max(score, 0.85);
    else return 0;
  }
  const words = [...tokens].filter((t) => !/^\d+$/.test(t));
  if (words.length && words.every((w) => normS.includes(w))) score = Math.max(score, 0.9);
  return score;
}

function formatLabel(street, townName) {
  const s = street.trim().replace(/,+$/, '');
  if (new RegExp(townName, 'i').test(s)) {
    return /\bMA\b/i.test(s) ? s : `${s}, MA`;
  }
  return `${s}, ${townName} MA`;
}

/**
 * @param {Array<{address:string,parcel_id:string,town_slug?:string}>} entries
 */
export function filterLocalSuggestions(entries, query, townName, limit = 8) {
  const q = query.trim();
  if (!q || !entries?.length) return [];

  const townNames = [townName, 'Arlington'];
  const tokens = queryTokens(q, townNames);
  if (!tokens.size) return [];

  const hits = [];

  for (const row of entries) {
    const street = row.address || '';
    const pid = row.parcel_id || '';
    if (!street || !pid) continue;
    if (!matchesStreet(street, tokens)) continue;
    const score = scoreMatch(q, street, tokens);
    if (score < 0.4) continue;
    hits.push({
      score,
      address: formatLabel(street, townName),
      parcel_id: pid,
      town_slug: row.town_slug || 'arlington-ma',
      town_name: townName,
    });
  }

  hits.sort((a, b) => b.score - a.score);
  const seen = new Set();
  const out = [];
  for (const h of hits) {
    const key = h.address.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      address: h.address,
      parcel_id: h.parcel_id,
      town_slug: h.town_slug,
      town_name: h.town_name,
      score: h.score,
    });
    if (out.length >= limit) break;
  }
  return out;
}
