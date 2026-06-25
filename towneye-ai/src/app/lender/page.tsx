"use client";

import { useState, useEffect } from "react";
import { Shield, Loader2, FileDown, ShieldCheck } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function LenderPage() {
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
          riskScore: "Low Risk",
          floodZone: "Zone X (Minimal Risk)",
          climateRisk: "Moderate (Heat index rising)",
          collateralValue: "$1.1M - $1.3M",
          marketLiquidity: "High (Avg 14 Days on Market)"
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
            <Shield className="h-8 w-8 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Lender Risk Report</h2>
          <p className="text-gray-400 max-w-md mb-8">Analyze collateral risk, liquidity, and environmental hazards for underwriting.</p>
          {isGenerating && <div className="text-blue-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Underwriting Property...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-white mb-2">{report.address}</h3>
                  <div className="text-sm font-medium text-blue-400 flex items-center mb-3"><ShieldCheck className="w-4 h-4 mr-2"/> Appraisal Risk: {report.riskScore}</div>
                  <div className="flex items-center text-xs text-gray-500 bg-gray-950 px-2 py-1 rounded inline-flex border border-gray-800">
                    <span className="mr-3">Generated: {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    <span>Execution Time: 1.50s</span>
                  </div>
                </div>
              </div>
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-sm text-gray-500 block mb-1">Flood Zone</span><span className="font-medium text-white">{report.floodZone}</span></div>
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-sm text-gray-500 block mb-1">Climate Risk</span><span className="font-medium text-white">{report.climateRisk}</span></div>
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-sm text-gray-500 block mb-1">Collateral Range</span><span className="font-medium text-white">{report.collateralValue}</span></div>
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-sm text-gray-500 block mb-1">Liquidity</span><span className="font-medium text-white">{report.marketLiquidity}</span></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
