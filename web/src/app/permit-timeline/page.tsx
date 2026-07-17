"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Clock,
  Loader2,
  AlertTriangle,
  FileDown,
  Printer,
  Share2,
} from "lucide-react";
import {
  generateReport,
  reportDownloadUrl,
  type PermitTimelinePayload,
  type ReportResponse,
} from "@/lib/api";
import { useSharedParcel } from "@/hooks/useSharedParcel";
import PermitTimelineReport, {
  permitTimelineToCsv,
} from "@/components/permit-timeline/PermitTimelineReport";

type ViewModel = {
  payload: PermitTimelinePayload;
  generatedSeconds?: number | null;
  downloadUrl?: string | null;
};

function mapReportToView(res: ReportResponse): ViewModel | null {
  const payload = res.data as PermitTimelinePayload | undefined;
  if (!payload?.town_slug) return null;
  return {
    payload,
    generatedSeconds: res.generated_seconds,
    downloadUrl: res.download_url,
  };
}

export default function PermitTimelinePage() {
  const [parcel] = useSharedParcel();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ViewModel | null>(null);
  const fetchGen = useRef(0);

  const runReport = useCallback(async () => {
    const gen = ++fetchGen.current;
    setLoading(true);
    setError("");
    setReport(null);

    try {
      const townSlug = parcel?.town_slug || "arlington-ma";
      const result = await generateReport("permit-timeline", {
        town_slug: townSlug,
        parcel_id: parcel?.parcel_id || "_town",
        address: parcel?.address || "Arlington, MA",
      });

      if (gen !== fetchGen.current) return;

      const view = mapReportToView(result);
      if (!view) {
        setError("Report returned without permit timeline data.");
        return;
      }
      setReport(view);
    } catch (err) {
      if (gen !== fetchGen.current) return;
      setError(err instanceof Error ? err.message : "Permit timeline generation failed");
    } finally {
      if (gen === fetchGen.current) setLoading(false);
    }
  }, [parcel?.town_slug, parcel?.parcel_id, parcel?.address]);

  useEffect(() => {
    runReport();
  }, [runReport]);

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
    const csv = permitTimelineToCsv(report.payload);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `permit-timeline-${report.payload.town_slug}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100 print:bg-white print:text-black">
      <div className="px-6 py-5 border-b border-gray-800 shrink-0 bg-gray-950 z-10 print:hidden">
        <div className="flex justify-between items-start gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">Permit Timeline</h1>
            <p className="text-gray-400 text-sm max-w-2xl">
              Town permitting velocity from Gold ISD history — key permit duration estimates,
              recent decisions, and optional parcel path for carry planning.
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
        {loading && (
          <div className="flex flex-col items-center justify-center py-24 text-blue-400">
            <Loader2 className="h-8 w-8 animate-spin mb-4" />
            <p className="text-sm">Computing permit velocity from Gold ledger…</p>
            <p className="text-xs text-gray-600 mt-2">application_date → approval_date</p>
          </div>
        )}

        {error && !loading && (
          <div className="max-w-xl mx-auto text-center py-16">
            <AlertTriangle className="h-10 w-10 text-red-400 mx-auto mb-4" />
            <p className="text-red-300 text-sm mb-4">{error}</p>
            <button
              type="button"
              onClick={runReport}
              className="text-sm text-blue-400 hover:text-blue-300 underline"
            >
              Retry
            </button>
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
              <button
                type="button"
                onClick={handleCsvDownload}
                className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"
              >
                <FileDown className="h-4 w-4 mr-2" /> Download CSV
              </button>
            </div>

            <PermitTimelineReport
              data={report.payload}
              generatedSeconds={report.generatedSeconds}
            />
          </div>
        )}

        {!loading && !error && !report && (
          <div className="w-full flex flex-col items-center justify-center text-center py-24 bg-gray-900 border border-gray-800 rounded-2xl">
            <Clock className="h-10 w-10 text-blue-500 mb-4" />
            <h2 className="text-xl font-bold text-white mb-2">Permit Timeline</h2>
            <p className="text-gray-400 max-w-md">Town permit velocity will appear here.</p>
          </div>
        )}
      </div>
    </div>
  );
}
