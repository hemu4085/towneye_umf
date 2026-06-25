"use client";

import { useState, useEffect } from "react";
import { Compass, Loader2, MapPin } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function NeighborhoodPage() {
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
          vibe: "Quiet, family-friendly, historic",
          walkScore: 82,
          transitScore: 65,
          schools: "Hardy Elementary (9/10), Ottoson Middle (8/10)",
          parks: "Spy Pond Park (0.4mi), Menotomy Rocks (1.2mi)"
        });
        setIsGenerating(false);
      }, 1000);
    } else {
      setReport(null);
    }
  }, [address]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      {!report ? (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center text-center py-20">
          <div className="w-16 h-16 bg-emerald-500/10 rounded-full flex items-center justify-center mb-6">
            <Compass className="h-8 w-8 text-emerald-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Neighborhood Guide</h2>
          <p className="text-gray-400 max-w-md mb-8">Generate a custom neighborhood guide for homebuyers including walkability, schools, and parks.</p>
          {isGenerating && <div className="text-emerald-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Scouting Neighborhood...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-white mb-2">Area Guide: {report.address}</h3>
                  <div className="flex items-center text-xs text-gray-500 bg-gray-950 px-2 py-1 rounded inline-flex border border-gray-800">
                    <span className="mr-3">Generated: {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    <span>Execution Time: 1.00s</span>
                  </div>
                </div>
              </div>
              <div className="p-6 grid grid-cols-2 gap-4">
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Neighborhood Vibe</span><span className="font-medium text-white">{report.vibe}</span></div>
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Schools</span><span className="font-medium text-white">{report.schools}</span></div>
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Walk Score</span><span className="font-bold text-emerald-400">{report.walkScore} / 100</span></div>
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Local Parks</span><span className="font-medium text-white">{report.parks}</span></div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
