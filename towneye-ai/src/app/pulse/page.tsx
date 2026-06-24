"use client";

import { useState } from "react";
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  LineChart, Line, AreaChart, Area
} from "recharts";
import { AlertTriangle, TrendingUp, CheckCircle2, Clock, Users, Calendar, Activity } from "lucide-react";
import { format, subDays } from "date-fns";

// Mock Data
const generateMockData = () => {
  return Array.from({ length: 30 }).map((_, i) => ({
    date: format(subDays(new Date(), 29 - i), "MMM dd"),
    potholes: Math.floor(Math.random() * 20) + 5,
    trash: Math.floor(Math.random() * 15) + 2,
    noise: Math.floor(Math.random() * 10) + 1,
  }));
};

const data = generateMockData();

const recentComplaints = [
  { id: 1, type: "Pothole", location: "Mass Ave & Pleasant St", status: "Open", time: "2 hours ago", sentiment: "Angry" },
  { id: 2, type: "Noise", location: "Broadway & Medford St", status: "In Progress", time: "5 hours ago", sentiment: "Frustrated" },
  { id: 3, type: "Trash", location: "Lake St & Cross St", status: "Open", time: "1 day ago", sentiment: "Neutral" },
  { id: 4, type: "Streetlight", location: "Appleton St", status: "Resolved", time: "2 days ago", sentiment: "Happy" },
];

const liveActivities = [
  { id: 1, name: "Arlington Farmers Market", location: "Russell Common", status: "Live Now", busyness: 85, trend: "increasing", type: "market" },
  { id: 2, name: "Town Day Preparations", location: "Mass Ave (Center)", status: "Upcoming", busyness: 40, trend: "stable", type: "event" },
  { id: 3, name: "Spy Pond Park", location: "Spy Pond", status: "Active", busyness: 65, trend: "decreasing", type: "park" },
];

export default function PulseDashboard() {
  return (
    <div className="flex-1 overflow-auto bg-gray-950 p-8 text-gray-100">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">311 Pulse Dashboard</h1>
        <p className="text-gray-400">Arlington Civic Health & Predictive Analytics</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <Card
          title="Total Open Requests"
          value="142"
          trend="+12% from last week"
          icon={<AlertTriangle className="h-6 w-6 text-amber-500" />}
          trendColor="text-red-400"
        />
        <Card
          title="Avg Resolution Time"
          value="3.2 days"
          trend="-0.4 days from last week"
          icon={<Clock className="h-6 w-6 text-blue-500" />}
          trendColor="text-green-400"
        />
        <Card
          title="Citizen Sentiment"
          value="Frustrated"
          trend="Trending negative in East Arlington"
          icon={<TrendingUp className="h-6 w-6 text-red-500" />}
          trendColor="text-red-400"
        />
        <Card
          title="Resolved This Week"
          value="89"
          trend="+24% from last week"
          icon={<CheckCircle2 className="h-6 w-6 text-green-500" />}
          trendColor="text-green-400"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Main Chart */}
        <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-6">311 Request Volume (30 Days)</h3>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorPotholes" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                <XAxis dataKey="date" stroke="#9ca3af" tick={{fill: '#9ca3af'}} axisLine={false} tickLine={false} />
                <YAxis stroke="#9ca3af" tick={{fill: '#9ca3af'}} axisLine={false} tickLine={false} />
                <RechartsTooltip 
                  contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', color: '#fff' }}
                  itemStyle={{ color: '#fff' }}
                />
                <Area type="monotone" dataKey="potholes" stroke="#3b82f6" fillOpacity={1} fill="url(#colorPotholes)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* AI Predictive Hotspots & Live Community Activity */}
        <div className="flex flex-col gap-6">
          {/* Live Community Activity */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 flex-1">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-semibold flex items-center">
                <Activity className="h-5 w-5 mr-2 text-green-500" />
                Live Community Pulse
              </h3>
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
              </span>
            </div>
            
            <p className="text-sm text-gray-400 mb-4">
              Real-time public activity and foot traffic data based on geolocation signals.
            </p>
            
            <div className="space-y-4">
              {liveActivities.map((activity) => (
                <div key={activity.id} className="p-3 bg-gray-800/50 rounded-lg border border-gray-800">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <h4 className="font-medium text-white text-sm flex items-center">
                        {activity.type === 'market' ? <Users className="h-3.5 w-3.5 mr-1.5 text-blue-400" /> : 
                         activity.type === 'event' ? <Calendar className="h-3.5 w-3.5 mr-1.5 text-purple-400" /> :
                         <MapIcon className="h-3.5 w-3.5 mr-1.5 text-emerald-400" />}
                        {activity.name}
                      </h4>
                      <p className="text-xs text-gray-400 mt-0.5">{activity.location}</p>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${
                      activity.status === 'Live Now' ? 'bg-green-500/20 text-green-400 border border-green-500/30' :
                      activity.status === 'Upcoming' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' :
                      'bg-gray-700 text-gray-300'
                    }`}>
                      {activity.status}
                    </span>
                  </div>
                  
                  <div className="mt-3">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-400">Busyness (Live)</span>
                      <span className="text-white font-medium">{activity.busyness}%</span>
                    </div>
                    <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div 
                        className={`h-full ${
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

          {/* AI Predictive Hotspots */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h3 className="text-lg font-semibold mb-4 flex items-center">
              <TrendingUp className="h-5 w-5 mr-2 text-purple-500" />
              Civic Hotspot Alerts
            </h3>
            
            <div className="space-y-3">
              <HotspotItem 
                title="Noise Complaints" 
                location="Capitol Square" 
                probability="85%" 
                color="bg-red-500"
              />
              <HotspotItem 
                title="Pothole Damage" 
                location="Appleton St" 
                probability="72%" 
                color="bg-amber-500"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Recent Requests Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-6">Recent Escalated Requests</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-400 uppercase bg-gray-800/50">
              <tr>
                <th className="px-6 py-3 rounded-tl-lg">Type</th>
                <th className="px-6 py-3">Location</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Time</th>
                <th className="px-6 py-3 rounded-tr-lg">Sentiment</th>
              </tr>
            </thead>
            <tbody>
              {recentComplaints.map((req) => (
                <tr key={req.id} className="border-b border-gray-800 last:border-0 hover:bg-gray-800/30 transition-colors">
                  <td className="px-6 py-4 font-medium text-white">{req.type}</td>
                  <td className="px-6 py-4 text-gray-300">{req.location}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                      req.status === 'Open' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                      req.status === 'In Progress' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                      'bg-green-500/10 text-green-400 border border-green-500/20'
                    }`}>
                      {req.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-gray-400">{req.time}</td>
                  <td className="px-6 py-4">
                    <span className={`text-xs font-medium ${
                      req.sentiment === 'Angry' ? 'text-red-400' :
                      req.sentiment === 'Frustrated' ? 'text-amber-400' :
                      req.sentiment === 'Happy' ? 'text-green-400' : 'text-gray-400'
                    }`}>
                      {req.sentiment}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Card({ title, value, trend, icon, trendColor }: any) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <div className="flex justify-between items-start mb-4">
        <div>
          <p className="text-gray-400 text-sm font-medium mb-1">{title}</p>
          <h3 className="text-3xl font-bold text-white">{value}</h3>
        </div>
        <div className="p-2 bg-gray-800 rounded-lg">
          {icon}
        </div>
      </div>
      <p className={`text-sm font-medium ${trendColor}`}>{trend}</p>
    </div>
  );
}

function HotspotItem({ title, location, probability, color }: any) {
  return (
    <div className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg border border-gray-800">
      <div>
        <h4 className="font-medium text-white text-sm">{title}</h4>
        <p className="text-xs text-gray-400">{location}</p>
      </div>
      <div className="flex items-center">
        <span className="text-xs font-semibold mr-2">{probability}</span>
        <div className="w-16 h-2 bg-gray-700 rounded-full overflow-hidden">
          <div className={`h-full ${color}`} style={{ width: probability }}></div>
        </div>
      </div>
    </div>
  );
}
