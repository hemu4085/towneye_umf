export const USER_TYPES = [
  { id: 'agent', label: 'RE Agent' },
  { id: 'developer', label: 'Developer' },
  { id: 'attorney', label: 'Attorney' },
  { id: 'architect', label: 'Architect' },
  { id: 'lender', label: 'Lender' },
  { id: 'homeowner', label: 'Homeowner' },
];

/**
 * Role × report matrix from product grid.
 * must   = must-have (primary)
 * useful = useful / secondary
 * null   = not relevant (hidden)
 */
export const REPORT_ACCESS = {
  agent: {
    buildability: 'must',
    market: 'must',
    risk: null,
    proforma: null,
    zoning: null,
    neighborhood: null,
    lender: null,
  },
  developer: {
    'deal-radar': 'must',
    buildability: 'must',
    market: null,
    risk: 'must',
    proforma: 'must',
    zoning: null,
    neighborhood: null,
    lender: null,
  },
  attorney: {
    buildability: 'must',
    market: null,
    risk: 'must',
    proforma: null,
    zoning: null,
    neighborhood: null,
    lender: null,
  },
  architect: {
    buildability: 'must',
    market: null,
    risk: 'must',
    proforma: null,
    zoning: null,
    neighborhood: null,
    lender: null,
  },
  lender: {
    buildability: 'useful',
    market: 'useful',
    risk: 'must',
    proforma: 'must',
    zoning: null,
    neighborhood: null,
    lender: 'must',
  },
  homeowner: {
    'homeowner-full': 'must',
    buildability: 'useful',
    market: 'useful',
    risk: 'useful',
    proforma: null,
    zoning: null,
    neighborhood: null,
    lender: null,
  },
};

export const REPORTS = [
  {
    id: 'deal-radar',
    icon: '📡',
    name: 'Deal Radar',
    description:
      'Town-wide ranked list — no address needed. Long tenure, underbuilt lots, no active permit; CSV export',
    time: '~instant on demo parcel · ~10–30 sec live scan',
    endpoint: 'deal-radar',
  },
  {
    id: 'homeowner-full',
    icon: '🏠',
    name: 'Full Property Report',
    description:
      'Complete home intelligence: facts, zoning, buildability, risks & market — like a professional house report',
    time: '~1–2 min live',
    endpoint: 'homeowner-full',
  },
  {
    id: 'buildability',
    icon: '🏗️',
    name: 'Buildability Brief',
    description:
      'Full zoning stack, overlay analysis, development options & permitting timeline',
    time: '~instant on demo parcel',
    endpoint: 'buildability',
  },
  {
    id: 'market',
    icon: '📊',
    name: 'Market Snapshot',
    description: 'Median price, DOM, inventory & comps within 0.25mi',
    time: '~20–60 sec live',
    endpoint: 'market',
  },
  {
    id: 'risk',
    icon: '⚠️',
    name: 'Risk & Constraints Report',
    description: 'Open permits, flood/wetland detail, historic flags & code violations',
    time: '~20–60 sec live',
    endpoint: 'risk',
  },
  {
    id: 'proforma',
    icon: '💰',
    name: 'Development Pro Forma',
    description: 'Unit yield, construction cost estimate & indicative ROI tied to zoning envelopes',
    time: '~instant on demo parcel · live LLM otherwise',
    endpoint: 'proforma',
  },
  {
    id: 'zoning',
    icon: '📋',
    name: 'Zoning Summary Card',
    description: 'Base zone, overlays, permitted uses, setbacks & FAR — one page',
    time: '~5 seconds',
    endpoint: 'zoning',
  },
  {
    id: 'neighborhood',
    icon: '📍',
    name: 'Neighborhood Intel Card',
    description: 'Schools, walkability, transit, commute times & recent permits',
    time: '~10 seconds',
    endpoint: 'neighborhood',
  },
  {
    id: 'lender',
    icon: '🏦',
    name: 'Lender Due Diligence Pack',
    description:
      'Full collateral memo: tax, liens, violations, assessor comps, zoning, permits & market',
    time: '~20–45 sec live',
    endpoint: 'lender',
  },
];

export function reportsForUserType(userType) {
  const access = REPORT_ACCESS[userType] || {};
  return REPORTS.filter((r) => access[r.id] != null);
}

export function reportTier(userType, reportId) {
  return REPORT_ACCESS[userType]?.[reportId] ?? null;
}

/** Town-wide reports — no parcel resolve required before generate. */
export const TOWN_SCOPED_REPORTS = new Set(['deal-radar']);

export function reportRequiresParcel(reportId) {
  return !TOWN_SCOPED_REPORTS.has(reportId);
}

export const LOADING_MESSAGES = [
  'Scanning assessor records…',
  'Filtering tenure & underbuilt lots…',
  'Checking open permits…',
  'Ranking opportunities…',
  'Pulling zoning data…',
  'Computing buildable envelope…',
  'Checking historic overlays…',
  'Resolving parcel constraints…',
  'Rendering report…',
];
