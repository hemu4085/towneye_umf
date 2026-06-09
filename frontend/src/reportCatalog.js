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
    'listing-radar': 'must',
    'buyer-briefing': 'must',
    buildability: 'useful',
    market: 'useful',
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
    'closing-risk-radar': 'must',
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

/** deterministic | hybrid | llm — shown as Data-backed / Data+AI / AI-synthesized badges */
export const REPORT_ENGINE = {
  'deal-radar': 'deterministic',
  'closing-risk-radar': 'deterministic',
  'listing-radar': 'deterministic',
  'buyer-briefing': 'hybrid',
  'homeowner-full': 'hybrid',
  buildability: 'deterministic',
  market: 'hybrid',
  risk: 'deterministic',
  proforma: 'hybrid',
  zoning: 'deterministic',
  neighborhood: 'llm',
  lender: 'deterministic',
};

export const REPORTS = [
  {
    id: 'listing-radar',
    icon: '📋',
    name: 'Listing Radar',
    description:
      'Town-wide ranked prospects — tenure window, listing story utilization, no open permit; CSV export',
    time: '~instant on demo · ~10–30 sec live scan',
    endpoint: 'listing-radar',
    report_engine: 'deterministic',
  },
  {
    id: 'buyer-briefing',
    icon: '🗂️',
    name: 'Buyer Briefing Card',
    description:
      'Pre-showing one-pager — flood/historic/permit flags, zoning headline, agent talking points',
    time: '~instant on demo parcel · ~20–60 sec live',
    endpoint: 'buyer-briefing',
    report_engine: 'hybrid',
  },
  {
    id: 'deal-radar',
    icon: '📡',
    name: 'Deal Radar',
    description:
      'Town-wide ranked list — no address needed. Long tenure, underbuilt lots, no active permit; CSV export',
    time: '~instant on demo parcel · ~10–30 sec live scan',
    endpoint: 'deal-radar',
    report_engine: 'deterministic',
  },
  {
    id: 'closing-risk-radar',
    icon: '⚖️',
    name: 'Closing Risk Radar',
    description:
      'Town-wide due-diligence scan — open/expired permits, flood SFHA, wetlands, historic flags; CSV export',
    time: '~instant on demo · ~15–45 sec live scan',
    endpoint: 'closing-risk-radar',
    report_engine: 'deterministic',
  },
  {
    id: 'homeowner-full',
    icon: '🏠',
    name: 'Full Property Report',
    description:
      'Complete home intelligence: facts, zoning, buildability, risks & market — like a professional house report',
    time: '~1–2 min live',
    endpoint: 'homeowner-full',
    report_engine: 'hybrid',
  },
  {
    id: 'buildability',
    icon: '🏗️',
    name: 'Buildability Brief',
    description:
      'Full zoning stack, overlay analysis, development options & permitting timeline',
    time: '~instant on demo parcel',
    endpoint: 'buildability',
    report_engine: 'deterministic',
  },
  {
    id: 'market',
    icon: '📊',
    name: 'Market Snapshot',
    description: 'Median price, DOM, inventory & comps within 0.25mi',
    time: '~20–60 sec live',
    endpoint: 'market',
    report_engine: 'hybrid',
  },
  {
    id: 'risk',
    icon: '⚠️',
    name: 'Risk & Constraints Report',
    description: 'Open permits, flood/wetland detail, historic flags & code violations',
    time: '~20–60 sec live',
    endpoint: 'risk',
    report_engine: 'deterministic',
  },
  {
    id: 'proforma',
    icon: '💰',
    name: 'Development Pro Forma',
    description: 'Unit yield, construction cost estimate & indicative ROI tied to zoning envelopes',
    time: '~instant on demo parcel · live LLM otherwise',
    endpoint: 'proforma',
    report_engine: 'hybrid',
  },
  {
    id: 'zoning',
    icon: '📋',
    name: 'Zoning Summary Card',
    description: 'Base zone, overlays, permitted uses, setbacks & FAR — one page',
    time: '~5 seconds',
    endpoint: 'zoning',
    report_engine: 'deterministic',
  },
  {
    id: 'neighborhood',
    icon: '📍',
    name: 'Neighborhood Intel Card',
    description: 'Schools, walkability, transit, commute times & recent permits',
    time: '~10 seconds',
    endpoint: 'neighborhood',
    report_engine: 'llm',
  },
  {
    id: 'lender',
    icon: '🏦',
    name: 'Lender Due Diligence Pack',
    description:
      'Full collateral memo: tax, liens, violations, assessor comps, zoning, permits & market',
    time: '~20–45 sec live',
    endpoint: 'lender',
    report_engine: 'deterministic',
  },
];

export function reportsForUserType(userType) {
  const access = REPORT_ACCESS[userType] || {};
  return REPORTS.filter((r) => access[r.id] != null);
}

export function reportTier(userType, reportId) {
  return REPORT_ACCESS[userType]?.[reportId] ?? null;
}

export function reportEngine(reportId) {
  return REPORT_ENGINE[reportId] || REPORTS.find((r) => r.id === reportId)?.report_engine || 'deterministic';
}

/** Town-wide reports — no parcel resolve required before generate. */
export const TOWN_SCOPED_REPORTS = new Set([
  'deal-radar',
  'closing-risk-radar',
  'listing-radar',
]);

export function reportRequiresParcel(reportId) {
  return !TOWN_SCOPED_REPORTS.has(reportId);
}

export const LOADING_MESSAGES = [
  'Scanning assessor records…',
  'Filtering tenure & listing story lots…',
  'Checking open permits…',
  'Ranking opportunities…',
  'Pulling zoning data…',
  'Computing buildable envelope…',
  'Checking historic overlays…',
  'Resolving parcel constraints…',
  'Rendering report…',
];
