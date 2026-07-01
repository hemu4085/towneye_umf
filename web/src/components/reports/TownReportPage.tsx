"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { generateReport, type ReportResponse } from "@/lib/api";
import { useSharedParcel } from "@/hooks/useSharedParcel";
import ReportViewer from "@/components/reports/ReportViewer";

type TownReportPageProps = {
  title: string;
  description: string;
  reportType: string;
  townSlug?: string;
  /** permit-timeline expects a ReportRequest-shaped body */
  payloadShape?: "town-scan" | "report-request";
};

export default function TownReportPage({
  title,
  description,
  reportType,
  townSlug = "arlington-ma",
  payloadShape = "town-scan",
}: TownReportPageProps) {
  const [parcel] = useSharedParcel();
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const run = useCallback(async () => {
    setLoading(true);
    setError("");
    setReport(null);
    try {
      const slug = parcel?.town_slug || townSlug;
      const payload =
        payloadShape === "report-request"
          ? {
              town_slug: slug,
              parcel_id: parcel?.parcel_id || "_town",
              address: parcel?.address || "Arlington, MA",
            }
          : {
              town_slug: slug,
              parcel_id: parcel?.parcel_id,
              address: parcel?.address,
            };
      const result = await generateReport(reportType, payload);
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report failed");
    } finally {
      setLoading(false);
    }
  }, [parcel, payloadShape, reportType, townSlug]);

  useEffect(() => {
    run();
  }, [run]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      <div className="px-8 py-6 border-b border-gray-800 shrink-0">
        <h1 className="text-2xl font-bold text-white mb-1">{title}</h1>
        <p className="text-gray-400 text-sm">{description}</p>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        {loading && (
          <div className="flex items-center justify-center py-20 text-blue-400">
            <Loader2 className="h-6 w-6 animate-spin mr-3" />
            Scanning town records…
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
