"use client";

import { MapPin, Filter, Search, Building, Home, DollarSign, ArrowUpRight } from "lucide-react";
import { useState } from "react";

const properties = [
  { id: 1, address: "142 Mass Ave", type: "Commercial", status: "Zoning Change", value: "$2.4M", date: "2 days ago", coords: { top: "30%", left: "35%" } },
  { id: 2, address: "89 Appleton St", type: "Residential", status: "Demolition Permit", value: "$950K", date: "1 week ago", coords: { top: "50%", left: "20%" } },
  { id: 3, address: "250 Broadway", type: "Mixed Use", status: "Recent Sale", value: "$4.1M", date: "3 weeks ago", coords: { top: "45%", left: "75%" } },
  { id: 4, address: "12 Lake St", type: "Residential", status: "New Construction", value: "N/A", date: "1 month ago", coords: { top: "80%", left: "55%" } },
];

export default function RadarPage() {
  const [zoom, setZoom] = useState(1);

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.25, 2.5));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.25, 0.5));

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

        {/* Right Panel - Map View Mockup */}
        <div className="flex-1 relative bg-[#f1f3f4] overflow-hidden border-l border-gray-800">
          
          {/* Zoomable Map Canvas */}
          <div 
            className="absolute inset-0 transition-transform duration-300 ease-in-out origin-center"
            style={{ transform: `scale(${zoom})` }}
          >
            {/* Base map layer with subtle texture */}
            <div className="absolute inset-0 opacity-[0.02] bg-[url('https://www.transparenttextures.com/patterns/cartographer.png')] mix-blend-overlay"></div>
            
            {/* Mock Map Grid Background (scaled down for wider zoom effect) */}
            <div 
              className="absolute inset-0 opacity-[0.15]"
              style={{
                backgroundImage: 'linear-gradient(#cbd5e1 1px, transparent 1px), linear-gradient(90deg, #cbd5e1 1px, transparent 1px)',
                backgroundSize: '20px 20px'
              }}
            />
            
            {/* Mock Water Body (Mystic River/Lakes) */}
            <div className="absolute top-0 right-0 w-1/4 h-full bg-[#e3f2fd] blur-xl transform skew-x-6 translate-x-1/3 pointer-events-none" />
            <div className="absolute bottom-0 left-0 w-1/3 h-1/4 bg-[#e3f2fd] blur-xl rounded-full translate-y-1/3 -translate-x-1/4 pointer-events-none" />
            
            {/* Major arterial road mockup */}
            <div className="absolute top-1/3 left-0 w-full h-1.5 bg-white border-y border-gray-300 transform rotate-[-3deg] pointer-events-none shadow-sm" />
            <div className="absolute top-[31%] left-[20%] text-gray-500 text-[9px] font-bold tracking-widest uppercase rotate-[-3deg]">Massachusetts Ave</div>
            
            {/* Secondary road mockup */}
            <div className="absolute top-0 left-1/2 w-1.5 h-full bg-white border-x border-gray-300 transform rotate-[15deg] pointer-events-none shadow-sm opacity-60" />
            <div className="absolute top-[60%] left-[51%] text-gray-500 text-[9px] font-bold tracking-widest uppercase rotate-[15deg]">Pleasant St</div>
            
            {/* Mock Map Labels (Scaled down) */}
            <div className="absolute top-[15%] left-[25%] text-gray-400 font-bold text-xl tracking-widest uppercase opacity-80 pointer-events-none">
              Arlington Heights
            </div>
            <div className="absolute top-[75%] left-[65%] text-gray-400 font-bold text-xl tracking-widest uppercase opacity-80 pointer-events-none">
              East Arlington
            </div>
            <div className="absolute top-[45%] left-[45%] text-gray-500 font-extrabold text-sm tracking-widest uppercase opacity-60 pointer-events-none">
              Arlington Center
            </div>

            {/* Map Pins (Slightly smaller, positioned better) */}
            {properties.map((prop) => (
              <div 
                key={prop.id} 
                className="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer group"
                style={prop.coords}
              >
                {/* Pulse effect */}
                <div className="absolute inset-0 bg-blue-500 rounded-full animate-ping opacity-20 scale-125" />
                
                {/* Pin */}
                <div className={`relative flex items-center justify-center w-6 h-6 rounded-full shadow border border-white ${
                  prop.type === 'Commercial' ? 'bg-blue-500' :
                  prop.type === 'Mixed Use' ? 'bg-purple-500' : 'bg-emerald-500'
                }`}>
                  {prop.type === 'Commercial' ? <Building size={10} className="text-white" /> : 
                  prop.type === 'Mixed Use' ? <MapPin size={10} className="text-white" /> :
                  <Home size={10} className="text-white" />}
                </div>

                {/* Tooltip */}
                <div 
                  className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-white border border-gray-200 text-gray-900 text-xs py-1.5 px-2.5 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20"
                  style={{ transform: `scale(${1/zoom})`, transformOrigin: 'bottom center' }} // Counter-scale tooltip so it stays readable
                >
                  <p className="font-bold">{prop.address}</p>
                  <p className="text-gray-500 text-[10px] uppercase font-semibold mt-0.5">{prop.status}</p>
                  <div className="absolute top-full left-1/2 -translate-x-1/2 border-[3px] border-transparent border-t-white drop-shadow-sm" />
                </div>
              </div>
            ))}
          </div>

          {/* Map Controls */}
          <div className="absolute bottom-6 right-6 flex flex-col bg-white border border-gray-200 rounded-lg shadow-md overflow-hidden z-30">
            <button onClick={handleZoomIn} className="p-1.5 hover:bg-gray-50 text-gray-600 font-bold transition-colors border-b border-gray-200 text-sm active:bg-gray-100">+</button>
            <button onClick={handleZoomOut} className="p-1.5 hover:bg-gray-50 text-gray-600 font-bold transition-colors text-sm active:bg-gray-100">-</button>
          </div>
        </div>
      </div>
    </div>
  );
}
