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
    buildability: 'must',
    market: 'useful',
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
    buildability: 'must',
    market: 'must',
    risk: 'useful',
    proforma: null,
    zoning: null,
    neighborhood: null,
    lender: null,
  },
};

export const REPORTS = [
  {
    id: 'buildability',
    icon: '🏗️',
    name: 'Buildability Brief',
    description:
      'Full zoning stack, overlay analysis, development options & permitting timeline',
    time: '~2 seconds',
    endpoint: 'buildability',
  },
  {
    id: 'market',
    icon: '📊',
    name: 'Market Snapshot',
    description: 'Median price, DOM, inventory & comps within 0.25mi',
    time: '~8 seconds',
    endpoint: 'market',
  },
  {
    id: 'risk',
    icon: '⚠️',
    name: 'Risk & Constraints Report',
    description: 'Flood zone, wetlands, historic flags, violations & liens',
    time: '~8 seconds',
    endpoint: 'risk',
  },
  {
    id: 'proforma',
    icon: '💰',
    name: 'Development Pro Forma',
    description: 'Unit yield, construction cost estimate & indicative ROI',
    time: '~12 seconds',
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
      'Risk & Constraints + Zoning Summary + Buildability verdict — loan file format',
    time: '~20 seconds',
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

export const LOADING_MESSAGES = [
  'Pulling zoning data…',
  'Computing buildable envelope…',
  'Checking historic overlays…',
  'Resolving parcel constraints…',
  'Rendering report…',
];
