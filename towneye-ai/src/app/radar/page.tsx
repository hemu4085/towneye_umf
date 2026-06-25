"use client";

import { MapPin, Filter, Search, Building, Home, DollarSign, ArrowUpRight } from "lucide-react";
import { useState } from "react";
import Map, { Marker, NavigationControl } from "react-map-gl";
import 'mapbox-gl/dist/mapbox-gl.css';

// For the demo to run locally, please add NEXT_PUBLIC_MAPBOX_TOKEN to your .env.local file
const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

const properties = [
  { id: 1, address: "142 Mass Ave", type: "Commercial", status: "Zoning Change", value: "$2.4M", date: "2 days ago", coords: { lat: 42.404, lng: -71.144 } },
  { id: 2, address: "89 Appleton St", type: "Residential", status: "Demolition Permit", value: "$950K", date: "1 week ago", coords: { lat: 42.421, lng: -71.182 } },
  { id: 3, address: "250 Broadway", type: "Mixed Use", status: "Recent Sale", value: "$4.1M", date: "3 weeks ago", coords: { lat: 42.410, lng: -71.150 } },
  { id: 4, address: "12 Lake St", type: "Residential", status: "New Construction", value: "N/A", date: "1 month ago", coords: { lat: 42.400, lng: -71.160 } },
];

export default function RadarPage() {
  const [viewState, setViewState] = useState({
    longitude: -71.1565,
    latitude: 42.4154, // Centered roughly on Arlington, MA
    zoom: 12.5
  });

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
        <div className="flex-1 relative border-l border-gray-800">
          {!MAPBOX_TOKEN ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900 text-gray-400 p-8 text-center">
              <MapPin className="w-12 h-12 mb-4 text-gray-600" />
              <h3 className="text-lg font-bold text-white mb-2">Mapbox Token Required</h3>
              <p>To view the professional interactive map, please add a <code className="bg-gray-800 px-1 rounded text-blue-400">NEXT_PUBLIC_MAPBOX_TOKEN</code> to your <code className="bg-gray-800 px-1 rounded text-blue-400">.env.local</code> file.</p>
              <a href="https://account.mapbox.com/access-tokens/" target="_blank" className="mt-4 text-blue-500 hover:underline">Get a free token here</a>
            </div>
          ) : (
            <Map
              {...viewState}
              onMove={evt => setViewState(evt.viewState)}
              mapStyle="mapbox://styles/mapbox/light-v11"
              mapboxAccessToken={MAPBOX_TOKEN}
              style={{ width: "100%", height: "100%" }}
            >
              <NavigationControl position="bottom-right" />
              
              {/* Map Pins */}
              {properties.map((prop) => (
                <Marker 
                  key={prop.id} 
                  longitude={prop.coords.lng} 
                  latitude={prop.coords.lat} 
                  anchor="center"
                >
                  <div className="relative group cursor-pointer">
                    {/* Pulse effect */}
                    <div className="absolute inset-0 bg-blue-500 rounded-full animate-ping opacity-30 scale-150" />
                    
                    {/* Pin */}
                    <div className={`relative flex items-center justify-center w-8 h-8 rounded-full shadow-md border-2 border-white ${
                      prop.type === 'Commercial' ? 'bg-blue-500' :
                      prop.type === 'Mixed Use' ? 'bg-purple-500' : 'bg-emerald-500'
                    }`}>
                      {prop.type === 'Commercial' ? <Building size={14} className="text-white" /> : 
                       prop.type === 'Mixed Use' ? <MapPin size={14} className="text-white" /> :
                       <Home size={14} className="text-white" />}
                    </div>

                    {/* Tooltip */}
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-3 bg-white border border-gray-200 text-gray-900 text-xs py-2 px-3 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20">
                      <p className="font-bold">{prop.address}</p>
                      <p className="text-gray-500 font-medium mt-0.5">{prop.status}</p>
                      <div className="absolute top-full left-1/2 -translate-x-1/2 border-[5px] border-transparent border-t-white" />
                    </div>
                  </div>
                </Marker>
              ))}
            </Map>
          )}
        </div>
      </div>
    </div>
  );
}
      </div>
    </div>
  );
}
