"use client";

import { useState, useEffect } from "react";
import { Clock, Loader2, Calendar, FileDown, CheckCircle2, Circle, Printer, Share2 } from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function TimelinePage() {
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
          executionTime: "0.91s",
          totalDuration: "8-10 Months",
          phases: [
            { name: "Pre-Filing & Conservation Comm", duration: "2 Months", status: "past", detail: "Wetlands review required before ZBA." },
            { name: "Zoning Board of Appeals (ZBA)", duration: "4 Months", status: "current", detail: "Requires special permit for multi-family. High abutters opposition expected." },
            { name: "Building Permit Issuance", duration: "2 Months", status: "upcoming", detail: "Standard ISD backlog." },
            { name: "Construction & Inspections", duration: "TBD", status: "upcoming", detail: "Dependent on contractor scheduling." }
          ]
        });
        setIsGenerating(false);
      }, 1800);
    } else {
      setReport(null);
    }
  }, [address]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      {!report ? (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center text-center py-20">
          <div className="w-16 h-16 bg-blue-500/10 rounded-full flex items-center justify-center mb-6">
            <Clock className="h-8 w-8 text-blue-500" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Permit Timeline Prediction</h2>
          <p className="text-gray-400 max-w-md mb-8">Select a property to forecast bureaucratic delays and hearing schedules.</p>
          {isGenerating && <div className="text-blue-500 flex items-center"><Loader2 className="animate-spin h-5 w-5 mr-2" /> Calculating Delays...</div>}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-8">
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-white">Estimated Timeline</h2>
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
                  <div className="text-sm text-gray-400 mb-3">Total Pre-Construction: <span className="font-bold text-white">{report.totalDuration}</span></div>
                <div className="flex items-center text-xs text-gray-500 bg-gray-950 px-2 py-1 rounded inline-flex border border-gray-800">
                  <span className="mr-3">Generated: {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                  <span>Execution Time: {report.executionTime || "0.91s"}</span>
                </div>
                </div>
              </div>

              <div className="p-8">
                <div className="space-y-8 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-gray-800 before:to-transparent">
                  {report.phases.map((phase: any, idx: number) => (
                    <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                      <div className={`flex items-center justify-center w-10 h-10 rounded-full border-4 border-gray-900 bg-gray-950 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow flex-shrink-0 ${phase.status === 'past' ? 'text-green-500' : phase.status === 'current' ? 'text-blue-500' : 'text-gray-600'}`}>
                        {phase.status === 'past' ? <CheckCircle2 className="w-5 h-5"/> : <Circle className="w-5 h-5"/>}
                      </div>
                      <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] bg-gray-950 border border-gray-800 p-4 rounded-xl shadow">
                        <div className="flex items-center justify-between mb-1">
                          <h4 className="font-bold text-white text-sm">{phase.name}</h4>
                          <span className="text-xs font-medium text-gray-500 bg-gray-900 px-2 py-1 rounded">{phase.duration}</span>
                        </div>
                        <p className="text-sm text-gray-400">{phase.detail}</p>
                      </div>
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
