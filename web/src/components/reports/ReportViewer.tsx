"use client";

import { extractReportBody, extractReportStyles } from "@/lib/reportHtml";
import { reportDownloadUrl } from "@/lib/api";
import { FileDown, Printer, Share2 } from "lucide-react";

const SHELL_CSS = `
  .towneye-report-shell {
    width: 100%;
    max-width: none;
    box-sizing: border-box;
  }
  .towneye-report-shell * {
    box-sizing: border-box;
  }
`;

type ReportViewerProps = {
  html: string;
  downloadUrl?: string | null;
  generatedSeconds?: number | null;
  fullWidth?: boolean;
};

export default function ReportViewer({
  html,
  downloadUrl,
  generatedSeconds,
  fullWidth = false,
}: ReportViewerProps) {
  const pdfHref = reportDownloadUrl(downloadUrl);
  const reportStyles = extractReportStyles(html);
  const reportBody = extractReportBody(html);

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
    <div className={fullWidth ? "w-full" : "w-full max-w-5xl mx-auto"}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="text-xs text-gray-500">
          {generatedSeconds != null && (
            <span>Generated in {generatedSeconds.toFixed(1)}s</span>
          )}
        </div>
        <div className="flex items-center gap-2">
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
            <span className="text-xs text-gray-600">PDF on production tier</span>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-2xl overflow-x-auto report-frame">
        <style>{SHELL_CSS}</style>
        {reportStyles ? <style>{reportStyles}</style> : null}
        <div
          className="towneye-report-shell"
          dangerouslySetInnerHTML={{ __html: reportBody }}
        />
      </div>
    </div>
  );
}
