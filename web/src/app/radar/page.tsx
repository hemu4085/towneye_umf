"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUpRight,
  Building2,
  DollarSign,
  Filter,
  LayoutGrid,
  List,
  Loader2,
  Map as MapIcon,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import DealRadarFilterSheet from "@/components/deal-radar/DealRadarFilterSheet";
import {
  generateReport,
  type DealRadarDeal,
  type DealRadarPayload,
} from "@/lib/api";
import { useSharedParcel, writeSharedParcel } from "@/hooks/useSharedParcel";
import { readDealRadarSession, saveDealRadarSession } from "@/lib/dealRadarSession";

const RadarMap = dynamic(() => import("@/components/RadarMap"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center bg-gray-900 text-gray-500 text-sm">
      Loading map…
    </div>
  ),
});

/** Always send criteria so the API returns live JSON (not cached demo HTML with no deals). */
const DEFAULT_CRITERIA: Record<string, unknown> = { preset: "aggressive" };

function fmtMoney(value?: number | null) {
  if (value == null) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

function filterChips(criteria: Record<string, unknown> | null): string[] {
  if (!criteria || Object.keys(criteria).length === 0) return ["Aggressive"];
  const chips: string[] = [];
  if (criteria.preset) chips.push(String(criteria.preset).replace(/_/g, " "));
  if (criteria.min_owner_tenure_years != null) {
    chips.push(`Tenure ${criteria.min_owner_tenure_years}+ yr`);
  }
  if (criteria.max_utilization_pct != null) {
    chips.push(`Util ≤ ${criteria.max_utilization_pct}%`);
  }
  if (criteria.min_expansion_room_sqft != null) {
    chips.push(`+${Number(criteria.min_expansion_room_sqft).toLocaleString()} sf`);
  }
  const zones = criteria.include_zone_codes as string[] | undefined;
  if (zones?.length) chips.push(`${zones.length} zone${zones.length > 1 ? "s" : ""}`);
  if (criteria.require_no_open_permit === false) chips.push("Permits OK");
  if (chips.length === 0) chips.push("Custom filters");
  return chips;
}

type DealCardProps = {
  deal: DealRadarDeal;
  selected: boolean;
  hovered: boolean;
  compact?: boolean;
  onHover: (deal: DealRadarDeal | null) => void;
  onOpenDetails: (deal: DealRadarDeal) => void;
};

function DealCard({ deal, selected, hovered, compact, onHover, onOpenDetails }: DealCardProps) {
  const active = selected || hovered;
  return (
    <button
      type="button"
      onMouseEnter={() => onHover(deal)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(deal)}
      onBlur={() => onHover(null)}
      onClick={() => onOpenDetails(deal)}
      className={`text-left shrink-0 transition-all ${
        compact
          ? `w-[min(88vw,300px)] snap-center rounded-xl border p-3 shadow-lg ${
              active ? "border-amber-500 bg-white ring-2 ring-amber-500/40" : "border-gray-200 bg-white"
            }`
          : `w-full rounded-xl border p-4 ${
              active ? "border-amber-500/70 bg-gray-900 ring-1 ring-amber-500/30" : "border-gray-800 bg-gray-950 hover:border-blue-500/40"
            }`
      }`}
    >
      <div className="flex justify-between items-start gap-2 mb-1.5">
        <span
          className={`text-[10px] font-semibold uppercase tracking-wider flex items-center ${
            compact ? "text-blue-600" : "text-blue-400"
          }`}
        >
          <Building2 size={12} className="mr-1" />
          #{deal.rank} · {deal.zone_code || "—"}
        </span>
        <span className={`text-xs font-bold ${compact ? "text-violet-600" : "text-purple-400"}`}>
          {deal.score ?? "—"}
        </span>
      </div>
      <h3
        className={`font-bold leading-snug mb-1.5 line-clamp-2 ${
          compact ? "text-sm text-gray-900" : "text-base text-white"
        }`}
      >
        {deal.address}
      </h3>
      <div className={`flex flex-wrap gap-x-2 text-xs ${compact ? "text-gray-600" : "text-gray-400"}`}>
        <span>{deal.tenure_years ?? "—"} yr tenure</span>
        <span>·</span>
        <span>+{deal.expansion_room_sqft?.toLocaleString() ?? "—"} sf</span>
      </div>
      <div
        className={`flex items-center justify-between mt-2 pt-2 border-t text-sm font-medium ${
          compact ? "border-gray-100 text-gray-800" : "border-gray-800 text-gray-300"
        }`}
      >
        <span className="flex items-center">
          <DollarSign size={14} className={compact ? "text-gray-400 mr-0.5" : "text-gray-500 mr-0.5"} />
          {fmtMoney(deal.assessed_value)}
        </span>
        <span className={`text-xs flex items-center ${compact ? "text-blue-600" : "text-blue-400"}`}>
          View brief <ArrowUpRight size={14} className="ml-0.5" />
        </span>
      </div>
    </button>
  );
}

export default function DealRadarPage() {
  const router = useRouter();
  const [parcel] = useSharedParcel();
  const townSlug = parcel?.town_slug || "arlington-ma";
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [view, setView] = useState<"map" | "list">("map");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<DealRadarPayload | null>(null);
  const [criteria, setCriteria] = useState<Record<string, unknown> | null>(DEFAULT_CRITERIA);
  const [selected, setSelected] = useState<DealRadarDeal | null>(null);
  const [hovered, setHovered] = useState<DealRadarDeal | null>(null);
  const restoredRank = useRef<number | undefined>(undefined);
  const sessionRestored = useRef(false);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const scanAbort = useRef<AbortController | null>(null);

  const criteriaKey = useMemo(
    () => JSON.stringify(criteria ?? DEFAULT_CRITERIA),
    [criteria],
  );

  const runScan = useCallback(
    async (nextCriteria: Record<string, unknown> | null) => {
      const effective = nextCriteria && Object.keys(nextCriteria).length ? nextCriteria : DEFAULT_CRITERIA;
      scanAbort.current?.abort();
      const ctrl = new AbortController();
      scanAbort.current = ctrl;
      setLoading(true);
      setError("");
      try {
        const body: Record<string, unknown> = {
          town_slug: townSlug,
          parcel_id: parcel?.parcel_id,
          address: parcel?.address,
          criteria: effective,
        };
        const res = await generateReport("deal-radar", body);
        if (ctrl.signal.aborted) return;
        const data = (res.data as DealRadarPayload) || null;
        setPayload(data);
        if (data?.criteria) setCriteria(data.criteria);
        if (data?.deals?.length) {
          setSelected((prev) => {
            if (prev && data.deals?.some((d) => d.rank === prev.rank)) return prev;
            return data.deals![0];
          });
        } else {
          setSelected(null);
        }
      } catch (err) {
        if (ctrl.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Scan failed");
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    },
    [parcel?.address, parcel?.parcel_id, townSlug],
  );

  useEffect(() => {
    runScan(criteria);
    return () => scanAbort.current?.abort();
  }, [townSlug, criteriaKey, parcel?.parcel_id, runScan]);

  const deals = useMemo(() => {
    const rows = payload?.deals || [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (d) =>
        d.address?.toLowerCase().includes(q) ||
        d.parcel_id?.toLowerCase().includes(q) ||
        d.owner_name?.toLowerCase().includes(q),
    );
  }, [payload?.deals, search]);

  useEffect(() => {
    if (sessionRestored.current) return;
    const saved = readDealRadarSession();
    if (!saved) return;
    sessionRestored.current = true;
    if (saved.criteria) setCriteria(saved.criteria);
    if (saved.view) setView(saved.view);
    if (saved.search) setSearch(saved.search);
    if (saved.selectedRank != null) restoredRank.current = saved.selectedRank;
  }, []);

  useEffect(() => {
    if (restoredRank.current == null || !deals.length) return;
    const deal = deals.find((d) => d.rank === restoredRank.current);
    if (deal) {
      setSelected(deal);
      setHovered(deal);
    }
    restoredRank.current = undefined;
  }, [deals]);

  const chips = useMemo(() => filterChips(criteria), [criteria]);
  const activeFilterCount = criteria && Object.keys(criteria).length > 0 ? chips.length : 0;

  const openDealDetails = useCallback(
    (deal: DealRadarDeal) => {
      setSelected(deal);
      setHovered(null);
      saveDealRadarSession({
        criteria,
        selectedRank: deal.rank,
        view,
        search,
      });
      writeSharedParcel({
        address: deal.address,
        parcel_id: deal.parcel_id,
        town_slug: townSlug,
        lat: deal.lat,
        lng: deal.lng,
      });
      router.push("/briefs?from=deal-radar");
    },
    [criteria, router, search, townSlug, view],
  );

  const handleHover = useCallback((deal: DealRadarDeal | null) => {
    setHovered(deal);
    if (!deal) return;
    const key = String(deal.rank ?? deal.parcel_id);
    cardRefs.current[key]?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, []);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950">
      {/* Compact top bar — map-first */}
      <header className="shrink-0 border-b border-gray-800 bg-gray-950 z-10">
        <div className="flex items-center gap-2 px-3 py-2.5">
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-bold text-white truncate">Deal Radar</h1>
            <p className="text-[11px] text-gray-500 truncate">
              {loading
                ? "Scanning town…"
                : `${payload?.total_matches?.toLocaleString() ?? 0} matches · ${deals.length} shown`}
            </p>
          </div>

          <button
            type="button"
            onClick={() => setSearchOpen((v) => !v)}
            className="p-2.5 rounded-xl border border-gray-700 text-gray-300 hover:text-white hover:border-gray-600"
            aria-label="Search results"
          >
            <Search className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={() => setFiltersOpen(true)}
            className="relative flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
          >
            <SlidersHorizontal className="h-4 w-4" />
            <span className="hidden sm:inline">Filters</span>
            {activeFilterCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-amber-400 text-gray-900 text-[10px] font-bold flex items-center justify-center">
                {activeFilterCount}
              </span>
            )}
          </button>

          <div className="flex rounded-xl border border-gray-700 overflow-hidden">
            <button
              type="button"
              onClick={() => setView("map")}
              className={`p-2.5 ${view === "map" ? "bg-gray-800 text-white" : "text-gray-500 hover:text-gray-300"}`}
              aria-label="Map view"
            >
              <MapIcon className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setView("list")}
              className={`p-2.5 border-l border-gray-700 ${view === "list" ? "bg-gray-800 text-white" : "text-gray-500 hover:text-gray-300"}`}
              aria-label="List view"
            >
              <List className="h-4 w-4" />
            </button>
          </div>
        </div>

        {searchOpen && (
          <div className="px-3 pb-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
              <input
                type="search"
                autoFocus
                placeholder="Search address, parcel, owner…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-xl pl-9 pr-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
        )}

        <div className="flex gap-1.5 overflow-x-auto px-3 pb-2.5 scrollbar-none">
          {chips.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => setFiltersOpen(true)}
              className="shrink-0 text-xs px-2.5 py-1 rounded-full border border-gray-700 text-gray-400 hover:border-blue-500/50 hover:text-white"
            >
              {chip}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setFiltersOpen(true)}
            className="shrink-0 text-xs px-2.5 py-1 rounded-full border border-dashed border-gray-600 text-gray-500 hover:text-white flex items-center gap-1"
          >
            <Filter className="h-3 w-3" />
            Edit
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 min-h-0 relative flex">
        {error && (
          <div className="absolute top-2 left-2 right-2 z-20 bg-red-950/90 border border-red-800 text-red-300 text-xs px-3 py-2 rounded-lg">
            {error}
          </div>
        )}

        {loading && (
          <div className="absolute inset-0 z-20 bg-gray-950/50 backdrop-blur-[1px] flex items-center justify-center">
            <div className="flex items-center gap-2 bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-blue-400 text-sm shadow-xl">
              <Loader2 className="h-5 w-5 animate-spin" />
              Scanning {townSlug.replace("-ma", "")}…
            </div>
          </div>
        )}

        {/* Map layer — stay mounted (hidden in list view) so Leaflet is not torn down */}
        <div
          className={`flex-1 min-w-0 min-h-0 relative ${
            view === "list" ? "hidden" : ""
          }`}
        >
          <RadarMap
            townSlug={townSlug}
            deals={deals}
            visible={view === "map"}
            highlightParcelId={selected?.parcel_id ?? parcel?.parcel_id}
            highlightRank={selected?.rank}
            hoverRank={hovered?.rank}
            hoverDeal={hovered}
            onSelectDeal={openDealDetails}
            onHoverDeal={setHovered}
          />

          {deals.length > 0 && (
            <div className="absolute bottom-0 left-0 right-0 z-10 pointer-events-none lg:hidden">
              <div className="bg-gradient-to-t from-gray-950/90 via-gray-950/40 to-transparent pt-8 pb-3 px-2">
                <div className="flex gap-2.5 overflow-x-auto snap-x snap-mandatory scrollbar-none pointer-events-auto">
                  {deals.map((deal, index) => (
                    <div
                      key={`${deal.rank ?? index}-${deal.parcel_id}`}
                      ref={(el) => {
                        cardRefs.current[String(deal.rank ?? deal.parcel_id)] = el;
                      }}
                    >
                      <DealCard
                        deal={deal}
                        selected={selected?.rank === deal.rank}
                        hovered={hovered?.rank === deal.rank}
                        compact
                        onHover={handleHover}
                        onOpenDetails={openDealDetails}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="hidden lg:flex absolute top-3 right-3 bottom-3 w-[340px] z-10 flex-col bg-gray-950/95 backdrop-blur border border-gray-800 rounded-xl shadow-2xl overflow-hidden">
            <div className="shrink-0 px-4 py-3 border-b border-gray-800 flex items-center justify-between">
              <span className="text-sm font-semibold text-white flex items-center gap-2">
                <LayoutGrid className="h-4 w-4 text-blue-400" />
                {deals.length} opportunities
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
              {deals.map((deal, index) => (
                <DealCard
                  key={`${deal.rank ?? index}-${deal.parcel_id}`}
                  deal={deal}
                  selected={selected?.rank === deal.rank}
                  hovered={hovered?.rank === deal.rank}
                  onHover={handleHover}
                  onOpenDetails={openDealDetails}
                />
              ))}
            </div>
          </div>
        </div>

        {/* List-only view */}
        <div
          className={`flex-1 overflow-y-auto p-3 space-y-2 min-h-0 ${
            view === "list" ? "" : "hidden"
          }`}
        >
            {deals.length === 0 && !loading && (
              <div className="text-center py-16 text-gray-500 text-sm">
                No deals match your filters. Try widening criteria.
              </div>
            )}
            {deals.map((deal, index) => (
              <DealCard
                key={`${deal.rank ?? index}-${deal.parcel_id}`}
                deal={deal}
                selected={selected?.rank === deal.rank}
                hovered={hovered?.rank === deal.rank}
                onHover={handleHover}
                onOpenDetails={openDealDetails}
              />
            ))}
        </div>
      </div>

      <DealRadarFilterSheet
        open={filtersOpen}
        townSlug={townSlug}
        appliedCriteria={criteria}
        loading={loading}
        resultCount={payload?.total_matches}
        onClose={() => setFiltersOpen(false)}
        onApply={(c) => {
          setCriteria(c);
          runScan(c);
        }}
        onReset={() => {
          setCriteria(DEFAULT_CRITERIA);
          runScan(DEFAULT_CRITERIA);
        }}
      />
    </div>
  );
}
