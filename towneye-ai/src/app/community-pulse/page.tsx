"use client";

import { useState, useEffect } from "react";
import { Activity, Users, Calendar, Map as MapIcon, ChevronRight } from "lucide-react";


export default function CommunityPulsePage() {
  const [liveActivities, setLiveActivities] = useState<any[]>([]);

  useEffect(() => {
    fetch("http://localhost:8000/api/pulse/community")
      .then(res => res.json())
      .then(data => setLiveActivities(data.live_activities))
      .catch(err => console.error("Failed to fetch community pulse data:", err));
  }, []);

  if (!liveActivities.length) {
    return <div className="flex-1 flex items-center justify-center bg-gray-950 text-white">Loading Community Data...</div>;
  }

  return (
    <div className="flex-1 overflow-auto bg-gray-950 p-8 text-gray-100">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Community Pulse</h1>
        <p className="text-gray-400">Real-time public activity, events, and foot traffic monitoring.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 max-w-5xl">
        {/* Live Community Activity */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex justify-between items-center mb-8 pb-4 border-b border-gray-800">
            <div>
              <h3 className="text-xl font-semibold flex items-center text-white mb-1">
                <Activity className="h-6 w-6 mr-2 text-green-500" />
                Live Foot Traffic & Events
              </h3>
              <p className="text-sm text-gray-400">
                Aggregated from location services and public town calendars.
              </p>
            </div>
            <span className="flex items-center bg-gray-950 border border-gray-800 px-4 py-2 rounded-lg text-sm text-gray-300">
              <span className="flex h-3 w-3 relative mr-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
              </span>
              Monitoring Active
            </span>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {liveActivities.map((activity) => (
              <div key={activity.id} className="p-5 bg-gray-950 rounded-xl border border-gray-800 hover:border-gray-700 transition-colors">
                <div className="flex justify-between items-start mb-3">
                  <div className="flex-1">
                    <h4 className="font-bold text-white text-lg flex items-center mb-1">
                      {activity.type === 'market' ? <Users className="h-5 w-5 mr-2 text-blue-400" /> : 
                       activity.type === 'event' ? <Calendar className="h-5 w-5 mr-2 text-purple-400" /> :
                       <MapIcon className="h-5 w-5 mr-2 text-emerald-400" />}
                      {activity.name}
                    </h4>
                    <p className="text-sm text-gray-400 flex items-center">
                      <MapIcon className="h-3 w-3 mr-1" /> {activity.location}
                    </p>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                    activity.status === 'Live Now' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                    activity.status === 'Upcoming' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                    'bg-gray-800 text-gray-300 border border-gray-700'
                  }`}>
                    {activity.status}
                  </span>
                </div>
                
                <p className="text-sm text-gray-300 mb-5 pb-4 border-b border-gray-800/50">
                  {activity.description}
                </p>

                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-400 font-medium">Estimated Capacity / Busyness</span>
                    <span className="text-white font-bold">{activity.busyness}%</span>
                  </div>
                  <div className="w-full h-2.5 bg-gray-800 rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full ${
                        activity.busyness > 75 ? 'bg-red-500' : 
                        activity.busyness > 50 ? 'bg-amber-500' : 'bg-green-500'
                      }`} 
                      style={{ width: `${activity.busyness}%` }}
                    ></div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
