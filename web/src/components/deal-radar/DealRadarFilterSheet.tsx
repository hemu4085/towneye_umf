"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import DealRadarCriteriaPanel from "@/components/deal-radar/DealRadarCriteriaPanel";

type Props = {
  open: boolean;
  townSlug: string;
  appliedCriteria: Record<string, unknown> | null;
  loading: boolean;
  resultCount?: number;
  onClose: () => void;
  onApply: (criteria: Record<string, unknown>) => void;
  onReset: () => void;
};

export default function DealRadarFilterSheet({
  open,
  townSlug,
  appliedCriteria,
  loading,
  resultCount,
  onClose,
  onApply,
  onReset,
}: Props) {
  const sheetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[1000] flex flex-col justify-end lg:justify-center lg:items-end">
      <button
        type="button"
        aria-label="Close filters"
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
        onClick={onClose}
      />

      <div
        ref={sheetRef}
        className="relative w-full lg:w-[440px] lg:h-full bg-gray-950 border-t lg:border-t-0 lg:border-l border-gray-800 rounded-t-2xl lg:rounded-none shadow-2xl flex flex-col max-h-[92vh] lg:max-h-full animate-in slide-in-from-bottom duration-200"
      >
        <div className="shrink-0 px-4 pt-3 pb-2 border-b border-gray-800">
          <div className="w-10 h-1 bg-gray-700 rounded-full mx-auto mb-3 lg:hidden" />
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Filters</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Narrow the town-wide development scan
                {resultCount != null && !loading && (
                  <span> · {resultCount.toLocaleString()} matches</span>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0">
          <DealRadarCriteriaPanel
            layout="sheet"
            townSlug={townSlug}
            appliedCriteria={appliedCriteria}
            loading={loading}
            onApply={(c) => {
              onApply(c);
              onClose();
            }}
            onReset={() => {
              onReset();
              onClose();
            }}
          />
        </div>
      </div>
    </div>
  );
}
