"use client";

import { useState, useRef, useEffect } from "react";
import { 
  FileText, MapPin, Loader2, Home, TrendingUp, DollarSign, 
  Users, CheckCircle2, ChevronRight, FileDown, BookOpen
} from "lucide-react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export default function RealtorBriefPage() {
  const [address, setAddress] = useSharedAddress("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch real suggestions from the backend API as the user types
  useEffect(() => {
    if (!address.trim()) {
      setSuggestions([]);
      return;
    }
    
    const timeoutId = setTimeout(() => {
      fetch(`http://localhost:8000/api/parcels/suggest?q=${encodeURIComponent(address)}&limit=5`)
        .then(res => res.json())
        .then(data => {
          if (data && data.suggestions) {
            setSuggestions(data.suggestions.map((s: any) => `${s.address}, ${s.town}`));
          }
        })
        .catch(err => console.error("Autocomplete failed:", err));
    }, 150);
    
    return () => clearTimeout(timeoutId);
  }, [address]);

  // Handle clicking outside to close dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleGenerate = () => {
    if (!address.trim()) return;
    
    setIsGenerating(true);
    setReport(null);

    // Simulate AI generation for Realtor Brief
    setTimeout(() => {
      setReport({
        address: address,
        propertyType: "Single Family",
        estimatedValue: "$1,150,000",
        marketTrend: "+4.2% YOY",
        neighborhood: "East Arlington",
        schools: [
          { name: "Hardy Elementary", rating: "9/10", distance: "0.4 mi" },
          { name: "Ottoson Middle", rating: "8/10", distance: "1.2 mi" }
        ],
        zoningHighlights: [
          "Recently rezoned to allow ADUs by-right, increasing property appeal to multi-generational families.",
          "Not located in a flood zone.",
          "Eligible for historic preservation tax credits if renovated."
        ],
        marketComparables: [
          { address: "42 Jason St", soldPrice: "$1.2M", date: "2 weeks ago" },
          { address: "18 Pleasant St", soldPrice: "$1.05M", date: "1 month ago" }
        ],
        sellingPoints: [
          "Walking distance to Mass Ave transit corridor.",
          "High demand area for young families leaving Cambridge/Somerville.",
          "Large backyard suitable for ADU addition."
        ]
      });
      setIsGenerating(false);
    }, 2500);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      <div className="px-8 py-6 border-b border-gray-800 shrink-0 bg-gray-950 z-10">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">Realtor Listing Briefs</h1>
            <p className="text-gray-400 text-sm">Generate AI-powered neighborhood insights, comps, and zoning selling points for your listings.</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto mb-10">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-xl relative">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-500 to-teal-500 rounded-t-2xl"></div>
            <h2 className="text-lg font-semibold text-white mb-4">Select Property for Listing Brief</h2>
            <div className="flex gap-4 relative" ref={dropdownRef}>
              <div className="relative flex-1">
                <MapPin className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                <input 
                  type="text" 
                  placeholder="Enter property address..." 
                  className="w-full bg-gray-950 border border-gray-700 rounded-xl py-3 pl-12 pr-4 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  value={address}
                  onChange={(e) => {
                    setAddress(e.target.value);
                    setShowSuggestions(true);
                  }}
                  onFocus={() => setShowSuggestions(true)}
                  onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
                />
                
                {/* Autofill Dropdown */}
                {showSuggestions && suggestions.length > 0 && (
                  <div className="absolute top-full left-0 w-full mt-2 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-[100] overflow-hidden">
                    {suggestions.map((suggestion, idx) => {
                      // Highlight the matching part
                      const matchIndex = address.length > 0 ? suggestion.toLowerCase().indexOf(address.toLowerCase()) : -1;
                      
                      return (
                        <div 
                          key={idx}
                          className="px-4 py-3 hover:bg-gray-800 cursor-pointer text-gray-300 hover:text-white flex items-center transition-colors border-b border-gray-800 last:border-0"
                          onClick={() => {
                            setAddress(suggestion);
                            setShowSuggestions(false);
                          }}
                        >
                          <MapPin className="h-4 w-4 mr-3 text-emerald-500 shrink-0" />
                          <span className="truncate">
                            {matchIndex >= 0 ? (
                              <>
                                {suggestion.substring(0, matchIndex)}
                                <strong className="text-white font-bold">{suggestion.substring(matchIndex, matchIndex + address.length)}</strong>
                                {suggestion.substring(matchIndex + address.length)}
                              </>
                            ) : (
                              suggestion
                            )}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              <button 
                onClick={handleGenerate}
                disabled={!address.trim() || isGenerating}
                className="bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-800 disabled:text-gray-500 text-white px-6 py-3 rounded-xl font-medium transition-colors flex items-center shadow-lg shadow-emerald-900/20 whitespace-nowrap"
              >
                {isGenerating ? <><Loader2 className="animate-spin h-5 w-5 mr-2" /> Generating...</> : <><Home className="h-5 w-5 mr-2" /> Generate</>}
              </button>
            </div>
          </div>
        </div>

        {report && (
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-white">Listing Brief</h2>
              <button className="flex items-center text-sm text-gray-400 hover:text-white transition-colors bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800">
                <FileDown className="h-4 w-4 mr-2" /> Export PDF
              </button>
            </div>

            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-gray-800 bg-gray-800/30">
                <h3 className="text-3xl font-bold text-white mb-4">{report.address}</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                    <div className="text-gray-400 text-sm mb-1 flex items-center"><DollarSign className="w-4 h-4 mr-1"/> Est. Value</div>
                    <div className="text-2xl font-bold text-white">{report.estimatedValue}</div>
                  </div>
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                    <div className="text-gray-400 text-sm mb-1 flex items-center"><TrendingUp className="w-4 h-4 mr-1 text-emerald-500"/> Trend</div>
                    <div className="text-2xl font-bold text-emerald-400">{report.marketTrend}</div>
                  </div>
                  <div className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                    <div className="text-gray-400 text-sm mb-1 flex items-center"><MapPin className="w-4 h-4 mr-1"/> Neighborhood</div>
                    <div className="text-xl font-bold text-white">{report.neighborhood}</div>
                  </div>
                </div>
              </div>

              <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-8">
                <section>
                  <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4 flex items-center">
                    <CheckCircle2 className="h-4 w-4 mr-2 text-emerald-500" /> Key Selling Points
                  </h4>
                  <ul className="space-y-3">
                    {report.sellingPoints.map((point: string, idx: number) => (
                      <li key={idx} className="flex items-start bg-gray-950 p-3 rounded-lg border border-gray-800">
                        <ChevronRight className="h-5 w-5 mr-2 text-emerald-500 shrink-0" />
                        <span className="text-sm text-gray-300">{point}</span>
                      </li>
                    ))}
                  </ul>
                </section>

                <section>
                  <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4 flex items-center">
                    <BookOpen className="h-4 w-4 mr-2 text-blue-500" /> Zoning & Property Highlights
                  </h4>
                  <ul className="space-y-3">
                    {report.zoningHighlights.map((highlight: string, idx: number) => (
                      <li key={idx} className="flex items-start bg-gray-950 p-3 rounded-lg border border-gray-800">
                        <ChevronRight className="h-5 w-5 mr-2 text-blue-500 shrink-0" />
                        <span className="text-sm text-gray-300">{highlight}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
