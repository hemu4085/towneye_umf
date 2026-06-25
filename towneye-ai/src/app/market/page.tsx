"use client";

import { useState, useEffect } from "react";
import { TrendingUp, Loader2, BarChart2 } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function MarketPage() {
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
          medianPrice: "$1,050,000",
          yoyChange: "+8.4%",
          daysOnMarket: "14 Days",
          inventory: "Low (1.2 Months)",
          prediction: "Seller's Market continuing through Q3."
        });
        setIsGenerating(false);
      }, 1200);
    } else {
      setReport(null);
    }
  }, [address]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      {!report ? (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center text-center py-20">
          <div className="w-16 h-16 bg-blue-500/10 rounded-full flex items-center justify-center mb-6">
            <TrendingUp className="h-8 w-8 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Market Trend Report</h2>
          <p className="text-gray-400 max-w-md mb-8">Analyze macroeconomic trends, supply, and demand for the selected submarket.</p>
          {isGenerating && <div className="text-blue-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Analyzing Market Data...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30">
                <h3 className="text-lg font-bold text-white mb-2">Market Area: {report.address}</h3>
                <div className="text-sm font-medium text-emerald-400 flex items-center"><BarChart2 className="w-4 h-4 mr-2"/> {report.prediction}</div>
              </div>
              <div className="p-6 grid grid-cols-4 gap-4">
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Median Price</span><span className="font-bold text-white">{report.medianPrice}</span></div>
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">YOY Change</span><span className="font-bold text-emerald-400">{report.yoyChange}</span></div>
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Days on Market</span><span className="font-bold text-white">{report.daysOnMarket}</span></div>
                <div className="bg-gray-950 p-4 rounded-xl border border-gray-800"><span className="text-xs text-gray-500 block mb-1">Inventory</span><span className="font-bold text-red-400">{report.inventory}</span></div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
