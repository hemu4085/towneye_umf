"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  ExternalLink,
  FileDown,
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
import { useSharedParcel, writeSharedParcel } from "@/hooks/useSharedParcel";

function fmtMoney(value?: number | null) {
  if (value == null) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

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

  const runScan = useCallback(
    async (nextCriteria: Record<string, unknown> | null) => {
      setLoading(true);
      setError("");
      try {
        const body: Record<string, unknown> = {
          town_slug: townSlug,
          parcel_id: parcel?.parcel_id,
          address: parcel?.address,
        };
        if (nextCriteria && Object.keys(nextCriteria).length) {
          body.criteria = nextCriteria;
        }
        const res = await generateReport("closing-risk-radar", body);
        setPayload((res.data as ClosingRiskPayload) || null);
        setDownloadUrl(res.download_url || null);
        if (res.data && (res.data as ClosingRiskPayload).criteria) {
          setCriteria((res.data as ClosingRiskPayload).criteria || null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Scan failed");
      } finally {
        setLoading(false);
      }
    },
    [parcel?.address, parcel?.parcel_id, townSlug],
  );

  useEffect(() => {
    runScan(criteria);
  }, [runScan]);

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

  const selectParcel = (row: ClosingRiskParcel) => {
    setSelected(row);
    writeSharedParcel({
      address: row.address,
      parcel_id: row.parcel_id,
      town_slug: townSlug,
    });
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
        <div className="w-[420px] shrink-0 border-r border-gray-800 flex flex-col bg-gray-900 min-h-0">
          <ClosingRiskCriteriaPanel
            townSlug={townSlug}
            appliedCriteria={criteria}
            loading={loading}
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

          <div className="p-4 border-b border-gray-800 shrink-0">
            <h2 className="font-semibold text-white text-sm">Ranked closing risks</h2>
            <p className="text-xs text-gray-400 mt-1">
              {loading
                ? "Scanning…"
                : `${payload?.total_matches?.toLocaleString() ?? 0} matches · showing ${rows.length}`}
            </p>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
            {error && <p className="text-red-400 text-sm px-1">{error}</p>}
            {loading && (
              <div className="flex items-center justify-center py-12 text-red-400 text-sm">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                Scanning {townSlug.replace("-ma", "")}…
              </div>
            )}
            {!loading &&
              rows.map((row, index) => (
                <div
                  key={`${row.rank ?? index}-${row.parcel_id}-${row.address}`}
                  className={`bg-gray-950 border rounded-xl overflow-hidden transition-colors ${
                    selected?.rank === row.rank
                      ? "border-red-500/60"
                      : "border-gray-800"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => selectParcel(row)}
                    className="w-full text-left p-4 hover:bg-gray-900/50 group"
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-red-400 text-xs font-semibold uppercase tracking-wider flex items-center">
                        <ShieldAlert size={14} className="mr-1" />
                        #{row.rank} · {row.zone_code || "—"}
                      </span>
                      <span className="text-xs text-red-300 font-bold">
                        Risk {row.risk_score?.toFixed(1) ?? "—"}
                      </span>
                    </div>
                    <h3 className="text-base font-bold text-white mb-2 leading-snug">{row.address}</h3>
                    <div className="flex flex-wrap gap-1 mb-2">
                      {(row.signal_labels || []).slice(0, 3).map((label, labelIndex) => (
                        <span
                          key={`${label}-${labelIndex}`}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-500/20"
                        >
                          {label}
                        </span>
                      ))}
                    </div>
                    <div className="flex items-center justify-between pt-2 border-t border-gray-800 text-xs text-gray-400">
                      <span>{row.open_permit_count ?? 0} open permits</span>
                      <span>{fmtMoney(row.assessed_value)}</span>
                    </div>
                  </button>
                  <div className="px-4 pb-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => selectParcel(row)}
                      className="flex-1 flex items-center justify-center text-xs font-medium text-blue-400 hover:text-blue-300 py-1.5 rounded-lg border border-gray-800 hover:border-blue-500/40"
                    >
                      <ExternalLink className="w-3 h-3 mr-1" />
                      View permit & violation records
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>

        <div className="flex-1 min-w-0 min-h-0">
          {selected ? (
            <ParcelDossierPanel
              townSlug={townSlug}
              parcelId={selected.parcel_id}
              address={selected.address}
              onClose={() => setSelected(null)}
            />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center p-8 bg-gray-950">
              <ShieldAlert className="h-12 w-12 text-red-500/40 mb-4" />
              <h2 className="text-lg font-semibold text-white mb-2">Select a parcel to drill down</h2>
              <p className="text-gray-500 text-sm max-w-md">
                Click any ranked result to search ISD building permits, trash violations, and 311 records
                for that property — no dead links.
              </p>
              {rows.length > 0 && (
                <button
                  type="button"
                  onClick={() => selectParcel(rows[0])}
                  className="mt-6 flex items-center text-sm text-blue-400 hover:text-blue-300"
                >
                  Open top result <ArrowUpRight className="h-4 w-4 ml-1" />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
