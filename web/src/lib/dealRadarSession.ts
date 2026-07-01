const STATE_KEY = "towneye_deal_radar_state";
const RETURN_FLAG = "towneye_deal_radar_return";

export type DealRadarSessionState = {
  criteria: Record<string, unknown> | null;
  selectedRank?: number;
  view: "map" | "list";
  search: string;
};

export function saveDealRadarSession(state: DealRadarSessionState) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(STATE_KEY, JSON.stringify(state));
  sessionStorage.setItem(RETURN_FLAG, "1");
}

export function readDealRadarSession(): DealRadarSessionState | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(STATE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as DealRadarSessionState;
  } catch {
    return null;
  }
}

export function hasDealRadarReturn(): boolean {
  if (typeof window === "undefined") return false;
  return sessionStorage.getItem(RETURN_FLAG) === "1";
}

export function clearDealRadarReturn() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(RETURN_FLAG);
}
