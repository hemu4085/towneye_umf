"use client";

import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Properties data
const properties = [
  { id: 1, address: "142 Mass Ave", type: "Commercial", status: "Zoning Change", value: "$2.4M", date: "2 days ago", lat: 42.410, lng: -71.144 },
  { id: 2, address: "89 Appleton St", type: "Residential", status: "Demolition Permit", value: "$950K", date: "1 week ago", lat: 42.421, lng: -71.182 },
  { id: 3, address: "250 Broadway", type: "Mixed Use", status: "Recent Sale", value: "$4.1M", date: "3 weeks ago", lat: 42.415, lng: -71.150 },
  { id: 4, address: "12 Lake St", type: "Residential", status: "New Construction", value: "N/A", date: "1 month ago", lat: 42.400, lng: -71.160 },
];

const createCustomIcon = (type: string) => {
  const bgColor = type === 'Commercial' ? '#3b82f6' : type === 'Mixed Use' ? '#a855f7' : '#10b981';
  
  return L.divIcon({
    className: 'custom-icon',
    html: `
      <div style="
        background-color: ${bgColor}; 
        width: 20px; 
        height: 20px; 
        border-radius: 50%; 
        border: 2px solid white; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
      "></div>
    `,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    popupAnchor: [0, -10]
  });
};

export default function RadarMap() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return <div className="flex-1 bg-gray-100 flex items-center justify-center">Loading map engine...</div>;

  return (
    <div className="w-full h-full z-0 relative">
      <MapContainer 
        center={[42.4154, -71.1565]} 
        zoom={13.5} 
        scrollWheelZoom={true} 
        className="w-full h-full"
        style={{ background: '#f8f9fa' }}
      >
        {/* Enterprise-grade Light Map Tiles from CartoDB (No API key required) */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />

        {properties.map((prop) => (
          <Marker 
            key={prop.id} 
            position={[prop.lat, prop.lng]} 
            icon={createCustomIcon(prop.type)}
          >
            <Popup className="custom-popup">
              <div className="font-sans">
                <div className="font-bold text-gray-900 text-sm">{prop.address}</div>
                <div className="text-xs font-semibold text-gray-500 uppercase mt-1 tracking-wide">{prop.status}</div>
                <div className="mt-2 text-sm text-gray-700">Value: <span className="font-medium text-gray-900">{prop.value}</span></div>
                <div className="mt-1 text-xs text-blue-600 font-medium cursor-pointer hover:underline">View Parcel Details &rarr;</div>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
