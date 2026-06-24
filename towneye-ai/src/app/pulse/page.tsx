"use client";

import { useState, useEffect } from "react";
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  LineChart, Line, AreaChart, Area
} from "recharts";
import { AlertTriangle, TrendingUp, CheckCircle2, Clock } from "lucide-react";
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


export default function PulseDashboard() {
  const [pulseData, setPulseData] = useState<any>(null);

  useEffect(() => {
    fetch("http://localhost:8000/pulse/311")
      .then(res => res.json())
      .then(data => setPulseData(data))
      .catch(err => console.error("Failed to fetch pulse data:", err));
  }, []);

  if (!pulseData) {
    return <div className="flex-1 flex items-center justify-center bg-gray-950 text-white">Loading Pulse Data from Arlington databases...</div>;
  }

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
          value={pulseData.kpi.total_open}
          trend="+12% from last week"
          icon={<AlertTriangle className="h-6 w-6 text-amber-500" />}
          trendColor="text-red-400"
        />
        <Card
          title="Avg Resolution Time"
          value={`${pulseData.kpi.avg_resolution_days} days`}
          trend="-0.4 days from last week"
          icon={<Clock className="h-6 w-6 text-blue-500" />}
          trendColor="text-green-400"
        />
        <Card
          title="Citizen Sentiment"
          value={pulseData.kpi.sentiment}
          trend="Trending negative in East Arlington"
          icon={<TrendingUp className="h-6 w-6 text-red-500" />}
          trendColor="text-red-400"
        />
        <Card
          title="Resolved This Week"
          value={pulseData.kpi.resolved_this_week}
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

        {/* AI Predictive Hotspots */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-6 flex items-center">
            <TrendingUp className="h-5 w-5 mr-2 text-purple-500" />
            AI Predictive Hotspots
          </h3>
          <p className="text-sm text-gray-400 mb-6">
            Based on sentiment analysis and historical data, the AI predicts the following issues will escalate if not addressed.
          </p>
          
          <div className="space-y-4">
            {pulseData.hotspots.map((hotspot: any, idx: number) => (
              <HotspotItem 
                key={idx}
                title={hotspot.title} 
                location={hotspot.location} 
                probability={hotspot.probability} 
                color={hotspot.color}
              />
            ))}
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
              {pulseData.recent_complaints.map((req: any) => (
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
