"use client";

import { FileDown, Printer, Share2 } from "lucide-react";

type ReportActionBarProps = {
  title?: string;
  executionTime?: string;
  downloadUrl?: string | null;
};

export default function ReportActionBar({
  title = "Generated Report",
  executionTime,
  downloadUrl,
}: ReportActionBarProps) {
  return (
    <div className="flex flex-wrap justify-between items-center gap-3 mb-6 w-full">
      <h2 className="text-xl font-bold text-white">{title}</h2>
      <div className="flex items-center gap-2">
        {executionTime && (
          <span className="text-xs text-gray-500 mr-2 hidden sm:inline">Execution: {executionTime}</span>
        )}
        <button
          type="button"
          onClick={() => window.print()}
          className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"
        >
          <Printer className="h-4 w-4 mr-2" /> Print
        </button>
        <button
          type="button"
          className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"
        >
          <Share2 className="h-4 w-4 mr-2" /> Share
        </button>
        {downloadUrl ? (
          <a
            href={downloadUrl}
            download
            className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800 no-underline"
          >
            <FileDown className="h-4 w-4 mr-2" /> Download
          </a>
        ) : (
          <button
            type="button"
            className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"
          >
            <FileDown className="h-4 w-4 mr-2" /> Download PDF
          </button>
        )}
      </div>
    </div>
  );
}
