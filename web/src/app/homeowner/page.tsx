"use client";

import { useState, useEffect } from "react";
import { UserCircle, Loader2, Wrench, Printer, Share2, FileDown } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function HomeownerPage() {
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
          homeValue: "$1,150,000",
          renovationROI: {
            "Kitchen Remodel": "72% ROI",
            "ADU Addition": "115% ROI",
            "Finished Basement": "68% ROI"
          },
          permitsRequired: "Yes (For structural or plumbing)",
          taxAssessment: "$12,450 / yr"
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
            <UserCircle className="h-8 w-8 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Homeowner Insights Report</h2>
          <p className="text-gray-400 max-w-md mb-8">Discover home value, tax assessment data, and renovation ROI for your property.</p>
          {isGenerating && <div className="text-emerald-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Valuing Property...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-white">Generated Report</h2>
              <div className="flex space-x-3">
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><Printer className="h-4 w-4 mr-2" /> Print</button>
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><Share2 className="h-4 w-4 mr-2" /> Share Link</button>
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><FileDown className="h-4 w-4 mr-2" /> Download PDF</button>
              </div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-white mb-2">Homeowner Report: {report.address}</h3>
                  <div className="flex items-center text-xs text-gray-500 bg-gray-950 px-2 py-1 rounded inline-flex border border-gray-800 mb-4">
                    <span className="mr-3">Generated: {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    <span>Execution Time: {report.executionTime || "1.40s"}</span>
                  </div>
                </div>
              </div>
              <div className="p-6">
                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Est. Home Value</span><span className="font-bold text-white text-xl">{report.homeValue}</span></div>
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Annual Tax Assessment</span><span className="font-bold text-gray-300 text-xl">{report.taxAssessment}</span></div>
                </div>
                
                <h4 className="text-sm font-semibold text-gray-400 uppercase mb-4 flex items-center"><Wrench className="w-4 h-4 mr-2 text-emerald-500"/> Renovation ROI Estimates</h4>
                <div className="space-y-2">
                  {Object.entries(report.renovationROI).map(([project, roi]) => (
                    <div key={project} className="flex justify-between items-center bg-gray-950 p-3 rounded-lg border border-gray-800">
                      <span className="text-white">{project}</span>
                      <span className="font-bold text-emerald-400">{roi as string}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
