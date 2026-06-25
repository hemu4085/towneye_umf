"use client";

import { useState, useRef, useEffect } from "react";
import { 
  FileText, Search, Loader2, Landmark, Clock, AlertCircle, 
  CheckCircle2, Building, Scale, ArrowRight
} from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function CivicEntitlementsPage() {
  const [address] = useSharedAddress("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [report, setReport] = useState<any>(null);

  const handleGenerate = () => {
    if (!address.trim()) return;
    
    setIsGenerating(true);
    setReport(null);

    // Simulate AI generation for Civic Entitlements
    setTimeout(() => {
      setReport({
        address: address,
        projectType: "Mixed-Use Redevelopment",
        jurisdiction: "Arlington, MA",
        estimatedTimeline: "12-18 Months",
        complexityScore: "High",
        requiredPermits: [
          { name: "Special Permit (Zoning Board of Appeals)", status: "Required", risk: "High Risk", detail: "Required for mixed-use in B4 district." },
          { name: "Environmental / Conservation Commission", status: "Required", risk: "Medium Risk", detail: "Proximity to Mystic River watershed." },
          { name: "Design Review Committee", status: "Required", risk: "Low Risk", detail: "Standard facade review." },
          { name: "Traffic & Parking Assessment", status: "Required", risk: "High Risk", detail: "Mass Ave traffic impact study needed." }
        ],
        recentPrecedents: [
          { project: "100 Mass Ave (Approved 2023)", outcome: "Approved with conditions", insight: "ZBA focused heavily on parking minimums. Required 10% affordable units." },
          { project: "250 Broadway (Denied 2022)", outcome: "Denied", insight: "Conservation Commission rejected due to stormwater runoff concerns." }
        ],
        politicalSentiment: {
          status: "Mixed",
          summary: "Based on recent town meeting minutes, the Board of Selectmen is pushing for more commercial tax base, but local abutters in this specific precinct strongly oppose height variances above 3 stories."
        }
      });
      setIsGenerating(false);
    }, 3000);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      <div className="px-8 py-6 border-b border-gray-800 shrink-0 bg-gray-950 z-10">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">Entitlements & Risk Brief</h1>
            <p className="text-gray-400 text-sm">Predict permit requirements, timeline, and political risk for proposed developments.</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto mb-10">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-xl relative">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-amber-500 to-orange-500 rounded-t-2xl"></div>
            <h2 className="text-lg font-semibold text-white mb-4">Analyze Entitlement Risk</h2>
            <div className="flex gap-4">
              <div className="flex-1 bg-gray-950 border border-gray-700 rounded-xl py-3 px-4 text-white flex items-center">
                <Building className="h-5 w-5 text-amber-500 mr-3 shrink-0" />
                <span className={address ? "text-white font-medium truncate" : "text-gray-500 italic"}>
                  {address || "Use the global search bar in the left menu to select a project address..."}
                </span>
              </div>
              <button 
                onClick={handleGenerate}
                disabled={!address.trim() || isGenerating}
                className="bg-amber-600 hover:bg-amber-700 disabled:bg-gray-800 disabled:text-gray-500 text-white px-6 py-3 rounded-xl font-medium transition-colors flex items-center shadow-lg shadow-amber-900/20 whitespace-nowrap"
              >
                {isGenerating ? <><Loader2 className="animate-spin h-5 w-5 mr-2" /> Analyzing Risk...</> : <><Landmark className="h-5 w-5 mr-2" /> Run Analysis</>}
              </button>
            </div>
          </div>
        </div>

        {report && (
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              
              {/* Header */}
              <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex justify-between items-start">
                <div>
                  <h3 className="text-3xl font-bold text-white mb-2">{report.address}</h3>
                  <div className="flex items-center text-amber-500 text-sm font-medium">
                    <Building className="w-4 h-4 mr-1.5" /> Proposed: {report.projectType}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-gray-400 mb-1 flex items-center justify-end"><Clock className="w-4 h-4 mr-1"/> Est. Timeline</div>
                  <div className="text-xl font-bold text-white">{report.estimatedTimeline}</div>
                </div>
              </div>

              <div className="p-6 space-y-8">
                
                {/* Permits Table */}
                <section>
                  <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4 flex items-center">
                    <Scale className="h-4 w-4 mr-2 text-amber-500" /> Required Boards & Permits
                  </h4>
                  <div className="overflow-hidden rounded-lg border border-gray-800">
                    <table className="w-full text-sm text-left">
                      <thead className="text-xs text-gray-400 bg-gray-950">
                        <tr>
                          <th className="px-4 py-3 font-medium">Board / Commission</th>
                          <th className="px-4 py-3 font-medium">Risk Level</th>
                          <th className="px-4 py-3 font-medium">AI Insight</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800 bg-gray-900">
                        {report.requiredPermits.map((item: any, idx: number) => (
                          <tr key={idx}>
                            <td className="px-4 py-4 text-white font-medium">{item.name}</td>
                            <td className="px-4 py-4">
                              <span className={`px-2 py-1 rounded text-xs font-medium ${
                                item.risk === 'High Risk' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                                item.risk === 'Medium Risk' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                                'bg-green-500/10 text-green-400 border border-green-500/20'
                              }`}>
                                {item.risk}
                              </span>
                            </td>
                            <td className="px-4 py-4 text-gray-400">{item.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {/* Political Sentiment */}
                  <section>
                    <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4 flex items-center">
                      <Users className="h-4 w-4 mr-2 text-blue-500" /> Town Sentiment Analysis
                    </h4>
                    <div className="bg-gray-950 border border-gray-800 rounded-xl p-5">
                      <div className="flex items-center mb-3">
                        <span className="text-sm text-gray-400 mr-3">Current Stance:</span>
                        <span className="bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded text-xs font-bold uppercase">{report.politicalSentiment.status}</span>
                      </div>
                      <p className="text-gray-300 text-sm leading-relaxed">
                        {report.politicalSentiment.summary}
                      </p>
                    </div>
                  </section>

                  {/* Precedents */}
                  <section>
                    <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4 flex items-center">
                      <Landmark className="h-4 w-4 mr-2 text-gray-400" /> Recent Precedents
                    </h4>
                    <div className="space-y-3">
                      {report.recentPrecedents.map((item: any, idx: number) => (
                        <div key={idx} className="bg-gray-950 border border-gray-800 rounded-xl p-4">
                          <div className="flex justify-between items-start mb-2">
                            <span className="text-white font-medium text-sm">{item.project}</span>
                            <span className={`text-xs font-medium ${item.outcome.includes('Approved') ? 'text-green-400' : 'text-red-400'}`}>
                              {item.outcome}
                            </span>
                          </div>
                          <p className="text-xs text-gray-400 flex items-start">
                            <ArrowRight className="w-3 h-3 mr-1.5 mt-0.5 shrink-0" /> {item.insight}
                          </p>
                        </div>
                      ))}
                    </div>
                  </section>
                </div>

              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
