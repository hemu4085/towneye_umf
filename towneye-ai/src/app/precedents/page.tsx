"use client";

import { useState, useEffect } from "react";
import { Search, Loader2, BookOpen, Scale, ChevronRight } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function PrecedentsPage() {
  const [address] = useSharedAddress("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [report, setReport] = useState<any>(null);

  useEffect(() => {
    if (address.trim()) {
      setIsGenerating(true);
      setReport(null);
      setTimeout(() => {
        setReport({
          address: address.replace(", undefined", ""),
          cases: [
            { id: "ZBA-2023-41", distance: "0.2 mi", topic: "Dimensional Variance (Setbacks)", outcome: "Granted", notes: "Abutters supported. Hardship proven due to lot shape." },
            { id: "CC-2022-18", distance: "0.5 mi", topic: "Wetlands Buffer Zone", outcome: "Denied", notes: "Failed to meet stormwater mitigation standards." }
          ]
        });
        setIsGenerating(false);
      }, 1400);
    } else {
      setReport(null);
    }
  }, [address]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      {!report ? (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center text-center py-20">
          <div className="w-16 h-16 bg-blue-500/10 rounded-full flex items-center justify-center mb-6">
            <Search className="h-8 w-8 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Legal Precedent Search</h2>
          <p className="text-gray-400 max-w-md mb-8">Search nearby ZBA and Planning Board decisions to establish legal precedent for your variance.</p>
          {isGenerating && <div className="text-blue-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Searching Municipal Records...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30">
                <h3 className="text-lg font-bold text-white mb-2">Precedents near {report.address}</h3>
              </div>
              <div className="p-6 space-y-4">
                {report.cases.map((c: any, i: number) => (
                  <div key={i} className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                    <div className="flex justify-between mb-2">
                      <span className="font-bold text-blue-400">{c.id}</span>
                      <span className={`text-xs font-bold px-2 py-1 rounded ${c.outcome === 'Granted' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{c.outcome}</span>
                    </div>
                    <div className="text-sm text-white mb-2">{c.topic} ({c.distance} away)</div>
                    <div className="text-xs text-gray-400 flex"><ChevronRight className="w-4 h-4 mr-1 shrink-0"/>{c.notes}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
