"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, MapPin } from "lucide-react";
import {
  generateReport,
  resolveParcel,
  type ReportResponse,
  type SharedParcel,
} from "@/lib/api";
import { useSharedParcel } from "@/hooks/useSharedParcel";
import ReportViewer from "@/components/reports/ReportViewer";

type BackendReportPageProps = {
  title: string;
  description: string;
  reportType: string;
  badge?: string;
};

/** Full-width backend HTML report — used for lender-grade memos. */
export default function BackendReportPage({
  title,
  description,
  reportType,
  badge,
}: BackendReportPageProps) {
  const [parcel] = useSharedParcel();
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async (p: SharedParcel) => {
    setLoading(true);
    setError("");
    setReport(null);
    try {
      let target = p;
      if (!p.parcel_id) {
        target = await resolveParcel({
          address: p.address,
          town_slug: p.town_slug,
        });
      }
      const result = await generateReport(reportType, {
        address: target.address,
        parcel_id: target.parcel_id,
        town_slug: target.town_slug,
        lat: target.lat ?? undefined,
        lng: target.lng ?? undefined,
      });
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report failed");
    } finally {
      setLoading(false);
    }
  }, [reportType]);

  useEffect(() => {
    if (!parcel?.address?.trim()) {
      setReport(null);
      setError("");
      return;
    }
    run(parcel.parcel_id ? parcel : { ...parcel, town_slug: parcel.town_slug || "arlington-ma" });
  }, [parcel, run]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      <div className="px-6 py-5 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-2xl font-bold text-white">{title}</h1>
          {badge && (
            <span className="bg-blue-500/20 text-blue-400 text-xs px-2 py-0.5 rounded border border-blue-500/30">
              {badge}
            </span>
          )}
        </div>
        <p className="text-gray-400 text-sm">{description}</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 min-h-0">
        {!parcel?.address?.trim() && (
          <div className="flex flex-col items-center justify-center py-24 text-center w-full">
            <MapPin className="h-10 w-10 text-blue-500 mb-4" />
            <p className="text-gray-400">Select a target property in the sidebar to generate this report.</p>
          </div>
        )}

        {parcel?.address && loading && (
          <div className="flex items-center justify-center py-24 text-blue-400">
            <Loader2 className="h-6 w-6 animate-spin mr-3" />
            Generating {title} for {parcel.address}…
          </div>
        )}

        {error && <p className="text-center text-red-400 py-12 text-sm">{error}</p>}

        {report?.html && !loading && (
          <ReportViewer
            html={report.html}
            downloadUrl={report.download_url}
            generatedSeconds={report.generated_seconds}
            fullWidth
          />
        )}
      </div>
    </div>
  );
}
