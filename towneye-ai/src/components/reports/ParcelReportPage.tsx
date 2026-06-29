"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, MapPin } from "lucide-react";
import { generateReport, resolveParcel, type ReportResponse, type SharedParcel } from "@/lib/api";
import { useSharedParcel } from "@/hooks/useSharedParcel";
import ReportViewer from "@/components/reports/ReportViewer";

type ParcelReportPageProps = {
  title: string;
  description: string;
  reportType: string;
  emptyHint?: string;
};

export default function ParcelReportPage({
  title,
  description,
  reportType,
  emptyHint,
}: ParcelReportPageProps) {
  const [parcel] = useSharedParcel();
  const [resolved, setResolved] = useState<SharedParcel | null>(null);
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
      setResolved(target);
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
      setResolved(null);
      setError("");
      return;
    }
    if (parcel.parcel_id) {
      run(parcel);
      return;
    }
    run({ ...parcel, town_slug: parcel.town_slug || "arlington-ma" });
  }, [parcel, run]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      <div className="px-8 py-6 border-b border-gray-800 shrink-0">
        <h1 className="text-2xl font-bold text-white mb-1">{title}</h1>
        <p className="text-gray-400 text-sm">{description}</p>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        {!parcel?.address?.trim() && (
          <div className="max-w-lg mx-auto text-center py-20">
            <MapPin className="h-10 w-10 text-blue-500 mx-auto mb-4" />
            <p className="text-gray-400">
              {emptyHint || "Select a target property in the sidebar to generate this report."}
            </p>
          </div>
        )}

        {parcel?.address && loading && (
          <div className="flex items-center justify-center py-20 text-blue-400">
            <Loader2 className="h-6 w-6 animate-spin mr-3" />
            Generating report for {resolved?.address || parcel.address}…
          </div>
        )}

        {error && (
          <div className="max-w-lg mx-auto text-center py-12 text-red-400 text-sm">{error}</div>
        )}

        {report?.html && !loading && (
          <ReportViewer
            html={report.html}
            downloadUrl={report.download_url}
            generatedSeconds={report.generated_seconds}
          />
        )}
      </div>
    </div>
  );
}
