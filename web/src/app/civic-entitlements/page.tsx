"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Landmark,
  Loader2,
  AlertTriangle,
  FileDown,
  Printer,
  Share2,
} from "lucide-react";
import {
  generateReport,
  resolveParcel,
  reportDownloadUrl,
  type EntitlementsPayload,
  type ReportResponse,
  type SharedParcel,
} from "@/lib/api";
import { useSharedParcel, readSharedParcel } from "@/hooks/useSharedParcel";
import EntitlementsReport from "@/components/entitlements/EntitlementsReport";

type ViewModel = {
  payload: EntitlementsPayload;
  generatedSeconds?: number | null;
  downloadUrl?: string | null;
};

function mapReportToView(res: ReportResponse): ViewModel | null {
  const payload = res.data as EntitlementsPayload | undefined;
  if (!payload?.parcel_id) return null;
  return {
    payload,
    generatedSeconds: res.generated_seconds,
    downloadUrl: res.download_url,
  };
}

export default function CivicEntitlementsPage() {
  const [parcel] = useSharedParcel();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ViewModel | null>(null);
  const fetchGen = useRef(0);

  const parcelKey = useMemo(() => {
    if (!parcel?.parcel_id || !parcel?.town_slug) return null;
    return `${parcel.town_slug}:${parcel.parcel_id}`;
  }, [parcel?.parcel_id, parcel?.town_slug]);

  const runReport = useCallback(async (target: SharedParcel) => {
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

      const result = await generateReport("civic-entitlements", {
        address: resolved.address,
        parcel_id: resolved.parcel_id,
        town_slug: resolved.town_slug,
        lat: resolved.lat ?? undefined,
        lng: resolved.lng ?? undefined,
      });

      if (gen !== fetchGen.current) return;

      const view = mapReportToView(result);
      if (!view) {
        setError("Report returned without entitlements data. Check parcel selection.");
        return;
      }
      setReport(view);
    } catch (err) {
      if (gen !== fetchGen.current) return;
      setError(err instanceof Error ? err.message : "Entitlements report generation failed");
    } finally {
      if (gen === fetchGen.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!parcelKey) {
      setReport(null);
      setError("");
      return;
    }
    const current = readSharedParcel();
    if (!current?.address?.trim()) return;
    runReport(current);
  }, [parcelKey, runReport]);

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

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100 print:bg-white print:text-black">
      <div className="px-6 py-5 border-b border-gray-800 shrink-0 bg-gray-950 z-10 print:hidden">
        <div className="flex justify-between items-start gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">Entitlements &amp; Risk</h1>
            <p className="text-gray-400 text-sm max-w-2xl">
              Gold zoning pathway, overlay election, risk signals, and cited constraints for
              land-use counsel. Board dockets appear only when present in Gold.
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
            <Landmark className="h-10 w-10 text-blue-500 mb-4" />
            <h2 className="text-xl font-bold text-white mb-2">Select a Target Property</h2>
            <p className="text-gray-400 max-w-md">
              Choose a parcel in the sidebar to generate an entitlements pathway brief from Gold
              zoning data.
            </p>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-24 text-blue-400">
            <Loader2 className="h-8 w-8 animate-spin mb-4" />
            <p className="text-sm">
              Generating entitlements brief for {parcel?.address || "selected parcel"}…
            </p>
            <p className="text-xs text-gray-600 mt-2">Gold zoning + pathway resolver</p>
          </div>
        )}

        {error && !loading && (
          <div className="max-w-xl mx-auto text-center py-16">
            <AlertTriangle className="h-10 w-10 text-red-400 mx-auto mb-4" />
            <p className="text-red-300 text-sm mb-4">{error}</p>
            {parcel && (
              <button
                type="button"
                onClick={() => runReport(parcel)}
                className="text-sm text-blue-400 hover:text-blue-300 underline"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {report?.payload && !loading && (
          <div className="w-full animate-in fade-in duration-300">
            <div className="flex flex-wrap justify-end items-center gap-2 mb-5 print:hidden">
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
                <span className="text-xs text-gray-600 px-2">PDF on production tier</span>
              )}
            </div>

            <EntitlementsReport
              data={report.payload}
              generatedSeconds={report.generatedSeconds}
            />
          </div>
        )}
      </div>
    </div>
  );
}
