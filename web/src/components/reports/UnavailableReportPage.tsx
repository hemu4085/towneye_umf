"use client";

import { Construction } from "lucide-react";

type UnavailableReportPageProps = {
  title: string;
  description: string;
  reason: string;
};

export default function UnavailableReportPage({
  title,
  description,
  reason,
}: UnavailableReportPageProps) {
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      <div className="px-8 py-6 border-b border-gray-800 shrink-0">
        <h1 className="text-2xl font-bold text-white mb-1">{title}</h1>
        <p className="text-gray-400 text-sm">{description}</p>
      </div>
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-md text-center">
          <Construction className="h-10 w-10 text-amber-500 mx-auto mb-4" />
          <p className="text-gray-300 mb-2">Not available in this pilot</p>
          <p className="text-gray-500 text-sm">{reason}</p>
        </div>
      </div>
    </div>
  );
}
