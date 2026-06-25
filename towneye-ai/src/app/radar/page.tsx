"use client";

import { Filter, Search, Building, Home, DollarSign, ArrowUpRight } from "lucide-react";
import dynamic from "next/dynamic";

// Dynamically import the map so Leaflet's window requirement doesn't break Next.js SSR
const RadarMap = dynamic(() => import("@/components/RadarMap"), {
  ssr: false,
  loading: () => <div className="flex-1 bg-gray-100 flex items-center justify-center text-gray-500">Initializing Map Engine...</div>
});

const properties = [
  { id: 1, address: "142 Mass Ave", type: "Commercial", status: "Zoning Change", value: "$2.4M", date: "2 days ago", coords: { lat: 42.404, lng: -71.144 } },
  { id: 2, address: "89 Appleton St", type: "Residential", status: "Demolition Permit", value: "$950K", date: "1 week ago", coords: { lat: 42.421, lng: -71.182 } },
  { id: 3, address: "250 Broadway", type: "Mixed Use", status: "Recent Sale", value: "$4.1M", date: "3 weeks ago", coords: { lat: 42.410, lng: -71.150 } },
  { id: 4, address: "12 Lake St", type: "Residential", status: "New Construction", value: "N/A", date: "1 month ago", coords: { lat: 42.400, lng: -71.160 } },
];

export default function RadarPage() {
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950">
      {/* Header */}
      <div className="px-8 py-4 border-b border-gray-800 shrink-0 flex justify-between items-center bg-gray-950 z-10">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Development Radar</h1>
          <p className="text-gray-400 text-sm">Track real estate movement, permits, and zoning changes in real-time.</p>
        </div>
        <div className="flex space-x-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search address or parcel..." 
              className="bg-gray-900 border border-gray-700 text-sm rounded-lg pl-9 pr-4 py-2 text-white focus:outline-none focus:border-blue-500 w-64"
            />
          </div>
          <button className="flex items-center px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm font-medium text-gray-200 hover:bg-gray-800 transition-colors">
            <Filter className="h-4 w-4 mr-2" />
            Filters
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel - List View */}
        <div className="w-[400px] border-r border-gray-800 flex flex-col bg-gray-900 overflow-y-auto">
          <div className="p-4 border-b border-gray-800 sticky top-0 bg-gray-900/95 backdrop-blur z-10">
            <h2 className="font-semibold text-white">Recent Activity (Arlington)</h2>
            <p className="text-xs text-gray-400 mt-1">4 high-value signals detected</p>
          </div>
          
          <div className="flex-1 p-4 space-y-4">
            {properties.map((prop) => (
              <div key={prop.id} className="bg-gray-950 border border-gray-800 rounded-xl p-4 hover:border-blue-500/50 transition-colors cursor-pointer group">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center text-blue-400 text-xs font-semibold uppercase tracking-wider">
                    {prop.type === 'Commercial' ? <Building size={14} className="mr-1.5" /> : <Home size={14} className="mr-1.5" />}
                    {prop.type}
                  </div>
                  <span className="text-xs text-gray-500">{prop.date}</span>
                </div>
                
                <h3 className="text-lg font-bold text-white mb-1">{prop.address}</h3>
                
                <div className="flex items-center mb-4">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    prop.status.includes('Zoning') ? 'bg-purple-500/10 text-purple-400' :
                    prop.status.includes('Demolition') ? 'bg-red-500/10 text-red-400' :
                    prop.status.includes('Sale') ? 'bg-green-500/10 text-green-400' :
                    'bg-blue-500/10 text-blue-400'
                  }`}>
                    {prop.status}
                  </span>
                </div>
                
                <div className="flex items-center justify-between pt-3 border-t border-gray-800">
                  <div className="flex items-center text-gray-300 font-medium">
                    <DollarSign size={16} className="text-gray-500" />
                    {prop.value}
                  </div>
                  <button className="text-gray-400 hover:text-white flex items-center text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                    View Parcel <ArrowUpRight size={16} className="ml-1" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Panel - Real Interactive Map */}
        <div className="flex-1 relative border-l border-gray-800 z-0">
          <RadarMap />
        </div>
      </div>
    </div>
  );
}
      </div>
    </div>
  );
}
