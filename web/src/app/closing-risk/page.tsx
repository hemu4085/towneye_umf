"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  FileDown,
  GripHorizontal,
  Loader2,
  Printer,
  Search,
  ShieldAlert,
} from "lucide-react";
import ClosingRiskCriteriaPanel from "@/components/closing-risk/ClosingRiskCriteriaPanel";
import ParcelDossierPanel from "@/components/closing-risk/ParcelDossierPanel";
import {
  generateReport,
  reportDownloadUrl,
  type ClosingRiskParcel,
  type ClosingRiskPayload,
} from "@/lib/api";
import { useSharedParcel } from "@/hooks/useSharedParcel";

const PARAMS_MIN = 120;
const PARAMS_MAX_RATIO = 0.65;
/** ~2″ taller than prior default (~200px) so more filters show without scrolling. */
const PARAMS_DEFAULT = 392;

type RankedListProps = {
  rows: ClosingRiskParcel[];
  selectedParcelId: string | null;
  loading: boolean;
  error: string;
  onSelect: (row: ClosingRiskParcel) => void;
};

/** Stable list UI — selection only changes highlight classes, not data fetch. */
const RankedClosingRisksList = memo(function RankedClosingRisksList({
  rows,
  selectedParcelId,
  loading,
  error,
  onSelect,
}: RankedListProps) {
  return (
    <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-0">
      {error && <p className="text-red-400 text-sm px-1">{error}</p>}
      {loading && rows.length === 0 && (
        <div className="flex items-center justify-center py-10 text-red-400 text-sm">
          <Loader2 className="h-5 w-5 animate-spin mr-2" />
          Scanning…
        </div>
      )}
      {rows.map((row, index) => {
        const selected = selectedParcelId === row.parcel_id;
        return (
          <button
            key={`${row.rank ?? index}-${row.parcel_id}`}
            type="button"
            onClick={() => onSelect(row)}
            className={`w-full text-left p-3 rounded-lg border transition-colors ${
              selected
                ? "border-red-500/60 bg-red-950/20"
                : "border-gray-800 bg-gray-950 hover:border-gray-600"
            }`}
          >
            <div className="flex justify-between items-start gap-2 mb-1">
              <span className="text-red-400 text-[10px] font-semibold uppercase tracking-wider">
                #{row.rank} · {row.zone_code || "—"}
              </span>
              <span className="text-xs text-red-300 font-bold shrink-0">
                {row.risk_score?.toFixed(1) ?? "—"}
              </span>
            </div>
            <h3 className="text-sm font-semibold text-white leading-snug line-clamp-2">
              {row.address}
            </h3>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {(row.signal_labels || []).slice(0, 2).map((label, i) => (
                <span
                  key={`${label}-${i}`}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-500/20"
                >
                  {label}
                </span>
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
});

export default function ClosingRiskPage() {
  const [parcel] = useSharedParcel();
  const townSlug = parcel?.town_slug || "arlington-ma";
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<ClosingRiskPayload | null>(null);
  const [criteria, setCriteria] = useState<Record<string, unknown> | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [selected, setSelected] = useState<ClosingRiskParcel | null>(null);

  const leftColRef = useRef<HTMLDivElement>(null);
  const [paramsHeight, setParamsHeight] = useState(PARAMS_DEFAULT);
  const [paramsOpen, setParamsOpen] = useState(true);
  const dragging = useRef(false);
  const scanGen = useRef(0);

  /** Town-level scan only — never depends on the selected dossier parcel. */
  const runScan = useCallback(
    async (nextCriteria: Record<string, unknown> | null) => {
      const gen = ++scanGen.current;
      setLoading(true);
      setError("");
      try {
        const body: Record<string, unknown> = {
          town_slug: townSlug,
        };
        if (nextCriteria && Object.keys(nextCriteria).length) {
          body.criteria = nextCriteria;
        }
        const res = await generateReport("closing-risk-radar", body);
        if (gen !== scanGen.current) return;
        setPayload((res.data as ClosingRiskPayload) || null);
        setDownloadUrl(res.download_url || null);
        if (res.data && (res.data as ClosingRiskPayload).criteria) {
          setCriteria((res.data as ClosingRiskPayload).criteria || null);
        }
      } catch (err) {
        if (gen !== scanGen.current) return;
        setError(err instanceof Error ? err.message : "Scan failed");
      } finally {
        if (gen === scanGen.current) setLoading(false);
      }
    },
    [townSlug],
  );

  // Re-scan only when town changes — not when a result row is selected.
  useEffect(() => {
    runScan(criteria);
    // intentionally omit criteria: Apply/Reset call runScan explicitly
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [townSlug, runScan]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current || !leftColRef.current) return;
      const rect = leftColRef.current.getBoundingClientRect();
      const max = Math.floor(rect.height * PARAMS_MAX_RATIO);
      const next = Math.min(max, Math.max(PARAMS_MIN, e.clientY - rect.top));
      setParamsHeight(next);
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const rows = useMemo(() => {
    const list = payload?.parcels || [];
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (r) =>
        r.address?.toLowerCase().includes(q) ||
        r.parcel_id?.toLowerCase().includes(q) ||
        r.owner_name?.toLowerCase().includes(q) ||
        r.signal_labels?.some((l) => l.toLowerCase().includes(q)),
    );
  }, [payload?.parcels, search]);

  /** Selection updates dossier only — do not rewrite shared parcel / re-scan. */
  const selectParcel = useCallback((row: ClosingRiskParcel) => {
    setSelected(row);
  }, []);

  const startResize = () => {
    dragging.current = true;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950">
      <div className="px-6 py-4 border-b border-gray-800 shrink-0 flex flex-wrap gap-4 items-center justify-between bg-gray-950">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1 flex items-center gap-2">
            <AlertTriangle className="h-6 w-6 text-red-500" />
            Closing Risk Radar
          </h1>
          <p className="text-gray-400 text-sm max-w-2xl">
            {payload?.executive_summary ||
              "Town-wide scan for open permits, violations, flood, wetlands, and historic flags before closing."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Filter results…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-gray-900 border border-gray-700 text-sm rounded-lg pl-9 pr-4 py-2 text-white w-56 focus:outline-none focus:border-red-500"
            />
          </div>
          {reportDownloadUrl(downloadUrl) && (
            <a
              href={reportDownloadUrl(downloadUrl)!}
              download
              className="flex items-center px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-gray-300 hover:text-white no-underline"
            >
              <FileDown className="h-4 w-4 mr-2" /> CSV / PDF
            </a>
          )}
          <button
            type="button"
            onClick={() => window.print()}
            className="flex items-center px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-gray-300 hover:text-white"
          >
            <Printer className="h-4 w-4 mr-2" /> Print
          </button>
        </div>
      </div>

      <div className="flex-1 flex min-h-0 overflow-hidden">
        <div
          ref={leftColRef}
          className="w-[300px] xl:w-[340px] shrink-0 border-r border-gray-800 flex flex-col bg-gray-900 min-h-0"
        >
          <div
            className="shrink-0 flex flex-col min-h-0 border-b border-gray-800 overflow-hidden"
            style={{ height: paramsOpen ? paramsHeight : 44 }}
          >
            <ClosingRiskCriteriaPanel
              townSlug={townSlug}
              appliedCriteria={criteria}
              loading={loading}
              fillHeight
              onOpenChange={setParamsOpen}
              onApply={(c) => {
                setCriteria(c);
                runScan(c);
              }}
              onReset={() => {
                setCriteria(null);
                setSelected(null);
                runScan(null);
              }}
            />
          </div>

          {paramsOpen && (
            <button
              type="button"
              aria-label="Resize parameters panel"
              onMouseDown={startResize}
              className="shrink-0 h-2.5 flex items-center justify-center border-b border-gray-800 bg-gray-950 hover:bg-gray-800 cursor-row-resize group"
            >
              <GripHorizontal className="h-3.5 w-3.5 text-gray-600 group-hover:text-gray-300" />
            </button>
          )}

          <div className="p-3 border-b border-gray-800 shrink-0 flex items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold text-white text-sm">Ranked closing risks</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                {loading && rows.length === 0
                  ? "Scanning…"
                  : `${payload?.total_matches?.toLocaleString() ?? 0} matches · ${rows.length} shown`}
                {loading && rows.length > 0 && (
                  <span className="text-gray-600"> · refreshing…</span>
                )}
              </p>
            </div>
          </div>

          <RankedClosingRisksList
            rows={rows}
            selectedParcelId={selected?.parcel_id ?? null}
            loading={loading}
            error={error}
            onSelect={selectParcel}
          />
        </div>

        {/* Right: dossier only changes with selection; list stays mounted */}
        <div className="flex-1 min-w-0 min-h-0 flex flex-col bg-gray-950">
          {selected ? (
            <ParcelDossierPanel
              key={selected.parcel_id}
              townSlug={townSlug}
              parcelId={selected.parcel_id}
              address={selected.address}
              onClose={() => setSelected(null)}
            />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center p-8">
              <ShieldAlert className="h-12 w-12 text-red-500/40 mb-4" />
              <h2 className="text-lg font-semibold text-white mb-2">
                Select a parcel for the dossier
              </h2>
              <p className="text-gray-500 text-sm max-w-md">
                Click any result in Ranked closing risks to load ISD permits and violation records
                for that property. The ranked list will not re-scan.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
