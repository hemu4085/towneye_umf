"use client";

import { useCallback, useEffect, useMemo, useRef, useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  DollarSign,
  Loader2,
  AlertTriangle,
  FileDown,
  Printer,
  Share2,
  ArrowLeft,
  SlidersHorizontal,
  RefreshCw,
} from "lucide-react";
import {
  generateReport,
  resolveParcel,
  reportDownloadUrl,
  type ProformaPayload,
  type ProformaOverrides,
  type ReportResponse,
  type SharedParcel,
} from "@/lib/api";
import { useSharedParcel, readSharedParcel } from "@/hooks/useSharedParcel";
import ProformaReport, { proformaToCsv } from "@/components/proforma/ProformaReport";

function ProformaBackNav() {
  const searchParams = useSearchParams();
  const fromDealRadar = searchParams.get("from") === "deal-radar";

  if (!fromDealRadar) return null;

  return (
    <Link
      href="/radar"
      className="inline-flex items-center gap-2 text-sm text-gray-400 hover:text-white mb-4 transition-colors"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to Deal Radar
    </Link>
  );
}

type ProformaViewModel = {
  payload: ProformaPayload;
  generatedSeconds?: number | null;
  downloadUrl?: string | null;
};

function mapReportToView(res: ReportResponse): ProformaViewModel | null {
  const payload = res.data as ProformaPayload | undefined;
  if (!payload?.parcel_id) return null;
  return {
    payload,
    generatedSeconds: res.generated_seconds,
    downloadUrl: res.download_url,
  };
}

const PILOT_DEFAULTS: ProformaOverrides = {
  hard_cost_psf: 475,
  sale_psf: 875,
  soft_cost_pct: 0.18,
  avg_unit_sf: 900,
};

function overridesFromMarket(market?: ProformaPayload["market"]): ProformaOverrides {
  return {
    hard_cost_psf: market?.indicative_hard_cost_psf ?? PILOT_DEFAULTS.hard_cost_psf,
    sale_psf: market?.indicative_sale_psf ?? PILOT_DEFAULTS.sale_psf,
    soft_cost_pct: PILOT_DEFAULTS.soft_cost_pct,
    avg_unit_sf: PILOT_DEFAULTS.avg_unit_sf,
  };
}

export default function ProformaPage() {
  const [parcel] = useSharedParcel();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ProformaViewModel | null>(null);
  const [showAssumptions, setShowAssumptions] = useState(false);
  const [overrides, setOverrides] = useState<ProformaOverrides>(PILOT_DEFAULTS);
  const [baselineOverrides, setBaselineOverrides] = useState<ProformaOverrides>(PILOT_DEFAULTS);
  const [appliedOverrides, setAppliedOverrides] = useState<ProformaOverrides | null>(null);
  const fetchGen = useRef(0);

  const parcelKey = useMemo(() => {
    if (!parcel?.parcel_id || !parcel?.town_slug) return null;
    return `${parcel.town_slug}:${parcel.parcel_id}`;
  }, [parcel?.parcel_id, parcel?.town_slug]);

  const runProforma = useCallback(
    async (target: SharedParcel, overrideValues?: ProformaOverrides | null) => {
      const gen = ++fetchGen.current;
      setLoading(true);
      setError("");
      setReport(null);

      try {
        let resolved = target;
        if (!target.parcel_id) {
          resolved = await resolveParcel({
            address: target.address,
            town_slug: target.town_slug || "arlington-ma",
          });
        }

        const payload: Record<string, unknown> = {
          address: resolved.address,
          parcel_id: resolved.parcel_id,
          town_slug: resolved.town_slug,
          lat: resolved.lat ?? undefined,
          lng: resolved.lng ?? undefined,
        };

        if (overrideValues) {
          payload.overrides = overrideValues;
        }

        const result = await generateReport("proforma", payload);

        if (gen !== fetchGen.current) return;

        const view = mapReportToView(result);
        if (!view) {
          setError("Report returned without proforma data. Check parcel selection.");
          return;
        }
        setReport(view);
        if (!overrideValues) {
          const baseline = overridesFromMarket(view.payload.market);
          setBaselineOverrides(baseline);
          setOverrides(baseline);
        }
      } catch (err) {
        if (gen !== fetchGen.current) return;
        setError(err instanceof Error ? err.message : "Proforma generation failed");
      } finally {
        if (gen === fetchGen.current) setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!parcelKey) {
      setReport(null);
      setError("");
      setAppliedOverrides(null);
      return;
    }
    const current = readSharedParcel();
    if (!current?.address?.trim()) return;
    setAppliedOverrides(null);
    runProforma(current);
  }, [parcelKey, runProforma]);

  const pdfHref = reportDownloadUrl(report?.downloadUrl);

  const handlePrint = () => window.print();

  const handleShare = async () => {
    if (!pdfHref) return;
    try {
      await navigator.clipboard.writeText(pdfHref);
    } catch {
      window.prompt("Copy report link:", pdfHref);
    }
  };

  const handleCsvDownload = () => {
    if (!report?.payload) return;
    const csv = proformaToCsv(report.payload);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `proforma-${report.payload.parcel_id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleApplyOverrides = () => {
    if (!parcel) return;
    setAppliedOverrides({ ...overrides });
    runProforma(parcel, overrides);
  };

  const handleResetOverrides = () => {
    if (!parcel) return;
    setOverrides(baselineOverrides);
    setAppliedOverrides(null);
    runProforma(parcel);
  };

  const hasOverrideChanges =
    appliedOverrides != null ||
    overrides.hard_cost_psf !== baselineOverrides.hard_cost_psf ||
    overrides.sale_psf !== baselineOverrides.sale_psf ||
    overrides.soft_cost_pct !== baselineOverrides.soft_cost_pct ||
    overrides.avg_unit_sf !== baselineOverrides.avg_unit_sf;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100 print:bg-white print:text-black">
      <div className="px-6 py-5 border-b border-gray-800 shrink-0 bg-gray-950 z-10 print:hidden">
        <Suspense fallback={null}>
          <ProformaBackNav />
        </Suspense>
        <div className="flex justify-between items-start gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h1 className="text-2xl font-bold text-white">Investor Feasibility</h1>
            </div>
            <p className="text-gray-400 text-sm max-w-2xl">
              Envelope-grounded investor exhibit — comp-backed exit pricing, equity returns, pursue/caution/pass
              verdict, and overlay election economics for investment committee screening.
            </p>
          </div>
          {parcel?.address && (
            <div className="text-right text-xs text-gray-500 shrink-0 hidden sm:block">
              <div className="text-gray-400 font-medium">{parcel.address}</div>
              {parcel.parcel_id && <div className="font-mono mt-0.5">{parcel.parcel_id}</div>}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 min-h-0">
        {!parcel?.address?.trim() && !loading && (
          <div className="w-full flex flex-col items-center justify-center text-center py-24 bg-gray-900 border border-gray-800 rounded-2xl">
            <DollarSign className="h-10 w-10 text-blue-500 mb-4" />
            <h2 className="text-xl font-bold text-white mb-2">Select a Target Property</h2>
            <p className="text-gray-400 max-w-md">
              Choose a parcel to generate an investor feasibility exhibit with comp-backed exit
              pricing, equity returns, and IC-ready pursue/caution/pass screening.
            </p>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-24 text-blue-400">
            <Loader2 className="h-8 w-8 animate-spin mb-4" />
            <p className="text-sm">
              Generating investor feasibility for {parcel?.address || "selected parcel"}…
            </p>
            <p className="text-xs text-gray-600 mt-2">Comps + envelopes + equity model</p>
          </div>
        )}

        {error && !loading && (
          <div className="max-w-xl mx-auto text-center py-16">
            <AlertTriangle className="h-10 w-10 text-red-400 mx-auto mb-4" />
            <p className="text-red-300 text-sm mb-4">{error}</p>
            {parcel && (
              <button
                type="button"
                onClick={() => runProforma(parcel, appliedOverrides)}
                className="text-sm text-blue-400 hover:text-blue-300 underline"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {report?.payload && !loading && (
          <div className="w-full animate-in fade-in duration-300">
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5 print:hidden">
              <button
                type="button"
                onClick={() => setShowAssumptions((v) => !v)}
                className={`flex items-center text-sm px-3 py-1.5 rounded-lg border transition-colors ${
                  showAssumptions
                    ? "text-blue-300 border-blue-700 bg-blue-950/40"
                    : "text-gray-400 hover:text-white border-gray-800 bg-gray-900"
                }`}
              >
                <SlidersHorizontal className="h-4 w-4 mr-2" />
                Assumptions
                {appliedOverrides && (
                  <span className="ml-2 text-[10px] uppercase tracking-wide bg-blue-600 text-white px-1.5 py-0.5 rounded-full">
                    Overridden
                  </span>
                )}
              </button>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handlePrint}
                  className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"
                >
                  <Printer className="h-4 w-4 mr-2" /> Print
                </button>
                <button
                  type="button"
                  onClick={handleShare}
                  disabled={!pdfHref}
                  className="flex items-center text-sm text-gray-400 hover:text-white disabled:opacity-40 bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"
                >
                  <Share2 className="h-4 w-4 mr-2" /> Share Link
                </button>
                {pdfHref ? (
                  <a
                    href={pdfHref}
                    download
                    className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800 no-underline"
                  >
                    <FileDown className="h-4 w-4 mr-2" /> Download PDF
                  </a>
                ) : (
                  <span className="text-xs text-gray-600 px-2 self-center">PDF on production tier</span>
                )}
                <button
                  type="button"
                  onClick={handleCsvDownload}
                  className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"
                >
                  <FileDown className="h-4 w-4 mr-2" /> Download CSV
                </button>
              </div>
            </div>

            {showAssumptions && (
              <div className="mb-5 p-4 rounded-xl border border-gray-800 bg-gray-900/60 print:hidden">
                <h3 className="text-sm font-medium text-gray-300 mb-4">
                  Model assumptions — edit to re-run live
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                  <label className="block">
                    <span className="text-xs text-gray-500">Hard cost ($/sf)</span>
                    <input
                      type="number"
                      value={overrides.hard_cost_psf ?? ""}
                      onChange={(e) =>
                        setOverrides((o) => ({
                          ...o,
                          hard_cost_psf: Number(e.target.value) || undefined,
                        }))
                      }
                      className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-gray-500">Sale price ($/sf GFA)</span>
                    <input
                      type="number"
                      value={overrides.sale_psf ?? ""}
                      onChange={(e) =>
                        setOverrides((o) => ({
                          ...o,
                          sale_psf: Number(e.target.value) || undefined,
                        }))
                      }
                      className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-gray-500">Soft costs (% of hard)</span>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      max="100"
                      value={
                        overrides.soft_cost_pct != null
                          ? Math.round(overrides.soft_cost_pct * 100)
                          : ""
                      }
                      onChange={(e) =>
                        setOverrides((o) => ({
                          ...o,
                          soft_cost_pct: (Number(e.target.value) || 0) / 100,
                        }))
                      }
                      className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-gray-500">Avg unit size (sf)</span>
                    <input
                      type="number"
                      value={overrides.avg_unit_sf ?? ""}
                      onChange={(e) =>
                        setOverrides((o) => ({
                          ...o,
                          avg_unit_sf: Number(e.target.value) || undefined,
                        }))
                      }
                      className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
                    />
                  </label>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
                  <label className="block">
                    <span className="text-xs text-gray-500">Land basis</span>
                    <select
                      value={overrides.land_basis_mode ?? "assessed"}
                      onChange={(e) =>
                        setOverrides((o) => ({
                          ...o,
                          land_basis_mode: e.target.value as ProformaOverrides["land_basis_mode"],
                        }))
                      }
                      className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
                    >
                      <option value="assessed">Assessed value (CAMA)</option>
                      <option value="last_sale">Last sale price</option>
                      <option value="acquisition">Acquisition / option price</option>
                    </select>
                  </label>
                  {overrides.land_basis_mode === "acquisition" && (
                    <label className="block">
                      <span className="text-xs text-gray-500">Acquisition price ($)</span>
                      <input
                        type="number"
                        value={overrides.acquisition_price ?? ""}
                        onChange={(e) =>
                          setOverrides((o) => ({
                            ...o,
                            acquisition_price: Number(e.target.value) || undefined,
                          }))
                        }
                        className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
                      />
                    </label>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleApplyOverrides}
                    className="flex items-center text-sm text-white bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg"
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Re-run with overrides
                  </button>
                  {hasOverrideChanges && (
                    <button
                      type="button"
                      onClick={handleResetOverrides}
                      className="text-sm text-gray-400 hover:text-white px-4 py-2 rounded-lg border border-gray-700"
                    >
                      Reset to defaults
                    </button>
                  )}
                </div>
              </div>
            )}

            <ProformaReport data={report.payload} generatedSeconds={report.generatedSeconds} />
          </div>
        )}
      </div>
    </div>
  );
}
