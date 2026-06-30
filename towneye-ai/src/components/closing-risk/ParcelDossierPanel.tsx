"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ExternalLink,
  FileText,
  Loader2,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import { fetchParcelDossier, type ParcelDossier } from "@/lib/api";

type Props = {
  townSlug: string;
  parcelId: string;
  address: string;
  onClose?: () => void;
};

function statusClass(status: string) {
  const s = status.toUpperCase();
  if (["OPEN", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "INSPECTIONS"].some((x) => s.includes(x))) {
    return "text-red-400 bg-red-500/10 border-red-500/30";
  }
  if (s.includes("CLOSED")) return "text-emerald-400 bg-emerald-500/10 border-emerald-500/30";
  return "text-gray-400 bg-gray-800 border-gray-700";
}

export default function ParcelDossierPanel({ townSlug, parcelId, address, onClose }: Props) {
  const [dossier, setDossier] = useState<ParcelDossier | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"permits" | "violations">("permits");
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchParcelDossier({ town_slug: townSlug, parcel_id: parcelId, address });
      setDossier(data);
      if (data.permits.open_count > 0) setTab("permits");
      else if (data.violations.open_count > 0) setTab("violations");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load parcel records");
    } finally {
      setLoading(false);
    }
  }, [townSlug, parcelId, address]);

  useEffect(() => {
    load();
  }, [load]);

  const q = query.trim().toLowerCase();

  const permits = useMemo(() => {
    const rows = dossier?.permits.permits || [];
    if (!q) return rows;
    return rows.filter((r) =>
      [r.permit_number, r.permit_type, r.status, r.description, r.address]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [dossier, q]);

  const violations = useMemo(() => {
    const rows = dossier?.violations.rows || [];
    if (!q) return rows;
    return rows.filter((r) =>
      [r.violation_type, r.status, r.detail, r.source, r.opened]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [dossier, q]);

  const isdUrl = dossier?.violations.isd_url;

  return (
    <div className="flex flex-col h-full bg-gray-950 text-gray-100">
      <div className="px-5 py-4 border-b border-gray-800 shrink-0 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-red-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <ShieldAlert className="h-4 w-4" />
            Parcel dossier
          </div>
          <h2 className="text-lg font-bold text-white truncate">{address}</h2>
          <p className="text-xs text-gray-500 mt-0.5">Parcel {parcelId}</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white shrink-0"
            aria-label="Close dossier"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {loading && (
        <div className="flex-1 flex items-center justify-center text-blue-400 text-sm">
          <Loader2 className="h-5 w-5 animate-spin mr-2" />
          Loading ISD permits & violation records…
        </div>
      )}

      {error && !loading && (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <p className="text-red-400 text-sm mb-3">{error}</p>
          <button
            type="button"
            onClick={load}
            className="text-sm px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg hover:text-white"
          >
            Retry
          </button>
        </div>
      )}

      {dossier && !loading && (
        <>
          <div className="px-5 py-3 border-b border-gray-800 shrink-0 flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search permits, violations, trash, ISD…"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            {isdUrl && (
              <a
                href={isdUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center text-xs text-blue-400 hover:text-blue-300 no-underline"
              >
                <ExternalLink className="h-3.5 w-3.5 mr-1" />
                Town ISD portal
              </a>
            )}
          </div>

          <div className="px-5 pt-3 flex gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setTab("permits")}
              className={`text-sm px-3 py-1.5 rounded-lg border ${
                tab === "permits"
                  ? "bg-blue-600/20 border-blue-500/50 text-blue-300"
                  : "border-gray-700 text-gray-400"
              }`}
            >
              Permits ({dossier.permits.total_count})
              {dossier.permits.open_count > 0 && (
                <span className="ml-1 text-red-400">{dossier.permits.open_count} open</span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setTab("violations")}
              className={`text-sm px-3 py-1.5 rounded-lg border ${
                tab === "violations"
                  ? "bg-red-600/20 border-red-500/50 text-red-300"
                  : "border-gray-700 text-gray-400"
              }`}
            >
              Violations & 311 ({dossier.violations.rows.length})
              {dossier.violations.open_count > 0 && (
                <span className="ml-1 text-red-400">{dossier.violations.open_count} open</span>
              )}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-5 min-h-0">
            {tab === "permits" && (
              <>
                {permits.length === 0 ? (
                  <p className="text-gray-500 text-sm text-center py-12">
                    {q ? "No permits match your search." : "No building permits on file for this parcel."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                          <th className="pb-2 pr-3">Permit #</th>
                          <th className="pb-2 pr-3">Type</th>
                          <th className="pb-2 pr-3">Status</th>
                          <th className="pb-2 pr-3">Applied</th>
                          <th className="pb-2">Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {permits.map((p, i) => (
                          <tr key={`${p.permit_number}-${i}`} className="border-b border-gray-800/80">
                            <td className="py-2.5 pr-3 font-mono text-xs text-gray-300">
                              {String(p.permit_number ?? "") || "—"}
                            </td>
                            <td className="py-2.5 pr-3 text-gray-300">{String(p.permit_type ?? "") || "—"}</td>
                            <td className="py-2.5 pr-3">
                              <span className={`text-xs px-2 py-0.5 rounded border ${statusClass(String(p.status || ""))}`}>
                                {String(p.status ?? "") || "—"}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-gray-400 text-xs">{String(p.application_date ?? "") || "—"}</td>
                            <td className="py-2.5 text-gray-400 text-xs max-w-xs">
                              {String(p.description || "—")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}

            {tab === "violations" && (
              <>
                <p className="text-xs text-gray-500 mb-3 flex items-center gap-1">
                  <FileText className="h-3.5 w-3.5" />
                  {dossier.violations.note}
                </p>
                {violations.length === 0 ? (
                  <p className="text-gray-500 text-sm text-center py-12">
                    {q ? "No violations match your search." : "No code violations or 311 records for this parcel."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                          <th className="pb-2 pr-3">Type</th>
                          <th className="pb-2 pr-3">Status</th>
                          <th className="pb-2 pr-3">Opened</th>
                          <th className="pb-2 pr-3">Source</th>
                          <th className="pb-2">Detail</th>
                        </tr>
                      </thead>
                      <tbody>
                        {violations.map((v, i) => (
                          <tr key={`${v.violation_type}-${i}`} className="border-b border-gray-800/80">
                            <td className="py-2.5 pr-3 text-gray-200">{v.violation_type || "—"}</td>
                            <td className="py-2.5 pr-3">
                              <span className={`text-xs px-2 py-0.5 rounded border ${statusClass(String(v.status || ""))}`}>
                                {v.status || "—"}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-gray-400 text-xs">{v.opened || "—"}</td>
                            <td className="py-2.5 pr-3 text-gray-500 text-xs">{v.source || "—"}</td>
                            <td className="py-2.5 text-gray-400 text-xs max-w-sm">{v.detail || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
