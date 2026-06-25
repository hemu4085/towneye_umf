"use client";

import { useState, useEffect } from "react";
import { Building2, Loader2, FileText, Printer, Share2, FileDown, CheckCircle2, AlertTriangle, BookOpen } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function ZoningReportPage() {
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
          zoningDistrict: "R2 - Two-Family Residential",
          overlayDistricts: ["None"],
          executionTime: "0.82s",
          allowedUses: ["Single Family", "Two-Family", "ADU"],
          specialPermitUses: ["Townhouse (3-4 units)", "Child Care Facility"],
          setbacks: { front: "20 ft", side: "10 ft", rear: "15 ft" },
          maxHeight: "35 ft (2.5 stories)",
          parking: "1 space per unit (ADU exempt)"
        });
        setIsGenerating(false);
      }, 1500);
    } else {
      setReport(null);
    }
  }, [address]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      {!report ? (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center text-center py-20">
          <div className="w-16 h-16 bg-blue-500/10 rounded-full flex items-center justify-center mb-6">
            <Building2 className="h-8 w-8 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Comprehensive Zoning Report</h2>
          <p className="text-gray-400 max-w-md mb-8">
            Select a property in the sidebar to generate a full breakdown of zoning codes, overlays, and dimensional requirements.
          </p>
          {isGenerating && <div className="text-blue-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Extracting Zoning Code...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-white">Generated Report</h2>
              <div className="flex space-x-3">
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><Printer className="h-4 w-4 mr-2" /> Print</button>
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><Share2 className="h-4 w-4 mr-2" /> Share</button>
                <button className="flex items-center text-sm text-white bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded-lg"><FileDown className="h-4 w-4 mr-2" /> Download PDF</button>
              </div>
            </div>
            
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-white mb-2">{report.address}</h3>
                  <div className="flex items-center text-xs text-gray-500 bg-gray-950 px-2 py-1 rounded inline-flex border border-gray-800">
                    <span className="mr-3">Generated: {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    <span>Execution Time: {report.executionTime}</span>
                  </div>
                </div>
              </div>

              <div className="p-6 grid grid-cols-2 gap-8">
                <div>
                  <h4 className="text-sm font-semibold text-gray-400 uppercase mb-4 flex items-center"><BookOpen className="w-4 h-4 mr-2 text-blue-500"/> District info</h4>
                  <div className="space-y-4">
                    <div className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                      <div className="text-xs text-gray-500 mb-1">Base Zoning</div>
                      <div className="font-medium text-white">{report.zoningDistrict}</div>
                    </div>
                    <div className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                      <div className="text-xs text-gray-500 mb-1">Overlays</div>
                      <div className="font-medium text-white">{report.overlayDistricts.join(", ")}</div>
                    </div>
                  </div>
                </div>
                
                <div>
                  <h4 className="text-sm font-semibold text-gray-400 uppercase mb-4 flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-green-500"/> Dimensional Rules</h4>
                  <div className="space-y-2">
                    {Object.entries(report.setbacks).map(([key, val]) => (
                      <div key={key} className="flex justify-between bg-gray-950 p-3 rounded-lg border border-gray-800">
                        <span className="text-gray-400 capitalize">{key} Setback</span>
                        <span className="text-white font-medium">{val as string}</span>
                      </div>
                    ))}
                    <div className="flex justify-between bg-gray-950 p-3 rounded-lg border border-gray-800">
                      <span className="text-gray-400">Max Height</span>
                      <span className="text-white font-medium">{report.maxHeight}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
