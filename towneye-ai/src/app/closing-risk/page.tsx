"use client";

import { useState, useEffect } from "react";
import { AlertTriangle, Loader2, FileDown, ShieldAlert, FileText, ArrowRight, ExternalLink } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function ClosingRiskPage() {
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
          executionTime: "1.05s",
          riskScore: "High",
          openPermits: 2,
          codeViolations: 1,
          environmentalFlags: ["Within 100ft of wetlands (Mystic River)"],
          titleIssues: "None detected in municipal records."
        });
        setIsGenerating(false);
      }, 1600);
    } else {
      setReport(null);
    }
  }, [address]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      {!report ? (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center text-center py-20">
          <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mb-6">
            <AlertTriangle className="h-8 w-8 text-red-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Closing Risk Radar</h2>
          <p className="text-gray-400 max-w-md mb-8">Scan municipal records for open permits, code violations, and environmental hazards before closing.</p>
          {isGenerating && <div className="text-red-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Scanning Municipal Records...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-white mb-2">{report.address}</h3>
                  <div className="text-sm font-medium text-red-400 flex items-center mb-3"><ShieldAlert className="w-4 h-4 mr-2"/> Overall Risk: {report.riskScore}</div>
                  <div className="flex items-center text-xs text-gray-500 bg-gray-950 px-2 py-1 rounded inline-flex border border-gray-800">
                    <span className="mr-3">Generated: {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    <span>Execution Time: {report.executionTime}</span>
                  </div>
                </div>
              </div>
              <div className="p-6 grid grid-cols-2 gap-6">
                <div className="bg-gray-950 p-5 rounded-xl border border-red-500/20 flex flex-col justify-between">
                  <div>
                    <div className="text-sm text-gray-400 mb-2">Open Building Permits</div>
                    <div className="text-3xl font-bold text-white mb-2">{report.openPermits} <span className="text-sm font-normal text-red-400 ml-2">Requires closure</span></div>
                  </div>
                  <button className="flex items-center text-xs font-medium text-blue-400 hover:text-blue-300 mt-2">
                    <ExternalLink className="w-3 h-3 mr-1" /> View ISD Permit Records
                  </button>
                </div>
                <div className="bg-gray-950 p-5 rounded-xl border border-red-500/20 flex flex-col justify-between">
                  <div>
                    <div className="text-sm text-gray-400 mb-2">Active Code Violations</div>
                    <div className="text-3xl font-bold text-white mb-2">{report.codeViolations} <span className="text-sm font-normal text-gray-500 ml-2">Trash ordinance</span></div>
                  </div>
                  <button className="flex items-center text-xs font-medium text-blue-400 hover:text-blue-300 mt-2">
                    <ExternalLink className="w-3 h-3 mr-1" /> View Violation Details
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
