/** Normalize address text for Arlington pilot search. */
export function normalizePilotSearchQuery(query, townHint = 'Arlington MA') {
  const t = query.trim();
  if (!t) return t;
  if (new RegExp(townHint.replace(/\s+/g, '|'), 'i').test(t) || /\barlington\b/i.test(t)) {
    return t;
  }
  return `${t}, ${townHint}`;
}

export function addressesMatch(a, b) {
  const norm = (s) =>
    (s || '')
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '');
  return norm(a) === norm(b);
}
