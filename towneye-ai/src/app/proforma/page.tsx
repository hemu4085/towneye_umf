"use client";

import { useState, useEffect } from "react";
import { DollarSign, Loader2, FileText, Printer, Share2, FileDown, TrendingUp, TrendingDown, ArrowRight } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function ProformaPage() {
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
          executionTime: "1.14s",
          scenario: "Tear-down & Townhouse Construction",
          acquisitionCost: "$850,000",
          hardCosts: "$1,200,000",
          softCosts: "$250,000",
          totalProjectCost: "$2,300,000",
          projectedSellout: "$3,100,000",
          roi: "34.7%",
          timeline: "14 months",
          risks: ["Interest rate volatility", "ZBA approval delay for density bonus"]
        });
        setIsGenerating(false);
      }, 2000);
    } else {
      setReport(null);
    }
  }, [address]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      {!report ? (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center text-center py-20">
          <div className="w-16 h-16 bg-blue-500/10 rounded-full flex items-center justify-center mb-6">
            <DollarSign className="h-8 w-8 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Automated Proforma Analysis</h2>
          <p className="text-gray-400 max-w-md mb-8">
            Select a property to instantly generate highest-and-best-use financial models.
          </p>
          {isGenerating && <div className="text-emerald-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Modeling Financials...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-white">Generated Proforma</h2>
              <div className="flex space-x-3">
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><Printer className="h-4 w-4 mr-2" /> Print</button>
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><Share2 className="h-4 w-4 mr-2" /> Share Link</button>
                <button className="flex items-center text-sm text-gray-400 hover:text-white bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800"><FileDown className="h-4 w-4 mr-2" /> Download PDF</button>
              </div>
            </div>
            
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-bold text-white mb-2">{report.address}</h3>
                  <div className="text-sm font-medium text-emerald-500 mb-4">Highest & Best Use: {report.scenario}</div>
                  <div className="flex items-center text-xs text-gray-500 bg-gray-950 px-2 py-1 rounded inline-flex border border-gray-800">
                    <span className="mr-3">Generated: {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    <span>Execution Time: {report.executionTime || "1.14s"}</span>
                  </div>
                </div>
              </div>

              <div className="p-6 grid grid-cols-3 gap-6 border-b border-gray-800">
                <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
                  <div className="text-sm text-gray-500 mb-1">Total Cost</div>
                  <div className="text-2xl font-bold text-white">{report.totalProjectCost}</div>
                </div>
                <div className="bg-gray-950 p-5 rounded-xl border border-gray-800">
                  <div className="text-sm text-gray-500 mb-1">Est. Sellout</div>
                  <div className="text-2xl font-bold text-emerald-400">{report.projectedSellout}</div>
                </div>
                <div className="bg-gray-950 p-5 rounded-xl border border-emerald-500/30 bg-emerald-500/5">
                  <div className="text-sm text-emerald-500/80 mb-1">Projected ROI</div>
                  <div className="text-2xl font-bold text-emerald-500 flex items-center">{report.roi} <TrendingUp className="w-5 h-5 ml-2"/></div>
                </div>
              </div>
              
              <div className="p-6">
                <h4 className="text-sm font-semibold text-gray-400 uppercase mb-4">Cost Breakdown</h4>
                <div className="space-y-3">
                  <div className="flex justify-between items-center text-sm border-b border-gray-800 pb-2"><span className="text-gray-400">Acquisition</span><span className="text-white">{report.acquisitionCost}</span></div>
                  <div className="flex justify-between items-center text-sm border-b border-gray-800 pb-2"><span className="text-gray-400">Hard Costs</span><span className="text-white">{report.hardCosts}</span></div>
                  <div className="flex justify-between items-center text-sm border-b border-gray-800 pb-2"><span className="text-gray-400">Soft Costs & Permitting</span><span className="text-white">{report.softCosts}</span></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
