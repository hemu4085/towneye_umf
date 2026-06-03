/** Parse pilot hint e.g. "Arlington MA" or "Arlington, MA". */
export function parsePilotTownHint(townHint = 'Arlington MA') {
  const raw = (townHint || 'Arlington MA').trim();
  const commaParts = raw.split(',').map((p) => p.trim()).filter(Boolean);
  let town = commaParts[0] || 'Arlington';
  let state = commaParts[1] || '';
  if (!state && /\s+MA$/i.test(town)) {
    town = town.replace(/\s+MA$/i, '').trim();
    state = 'MA';
  }
  if (!state) state = 'MA';
  const compact = `${town} ${state}`;
  return { town, state, compact, label: compact };
}

/** Canonical display label for autocomplete (never duplicates state). */
export function formatDisplayAddress(street, townHint = 'Arlington MA') {
  const { town, state, compact } = parsePilotTownHint(townHint);
  const s = (street || '').trim().replace(/,+$/, '');
  if (!s) return compact;
  const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const hasTown = new RegExp(`\\b${esc(town)}\\b`, 'i').test(s);
  const hasState = new RegExp(`\\b${esc(state)}\\b`, 'i').test(s);
  if (hasTown && hasState) return s;
  if (hasTown && !hasState) return `${s}, ${state}`;
  return `${s}, ${compact}`;
}

/**
 * Append pilot town for API suggest when the user omitted it.
 * Matches pre-fix behavior (e.g. "24 princeton" → "24 princeton, Arlington MA").
 */
export function normalizePilotSearchQuery(query, townHint = 'Arlington MA') {
  const t = query.trim();
  if (!t) return t;
  const { town, state, compact } = parsePilotTownHint(townHint);
  const hintPattern = townHint.replace(/\s+/g, '|').replace(/,/g, '|');
  if (
    new RegExp(hintPattern, 'i').test(t) ||
    new RegExp(compact.replace(/\s+/g, '|'), 'i').test(t) ||
    new RegExp(`\\b${town.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(t)
  ) {
    if (
      new RegExp(`\\b${town.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(t) &&
      !new RegExp(`\\b${state}\\b`, 'i').test(t)
    ) {
      return `${t}, ${state}`;
    }
    return t;
  }
  return `${t}, ${compact}`;
}

export function addressesMatch(a, b) {
  const norm = (s) =>
    (s || '')
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '');
  return norm(a) === norm(b);
}
