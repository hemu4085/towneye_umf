"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  BarChart3, 
  Map as MapIcon, 
  MessageSquare, 
  Building2,
  Settings,
  Bell,
  FileText,
  Home,
  Landmark,
  Activity,
  ChevronDown,
  Briefcase,
  Scale,
  Compass,
  DollarSign,
  UserCircle,
  MapPin,
  Search,
  Clock, 
  Shield, 
  AlertTriangle, 
  TrendingUp,
  Map
} from "lucide-react";
import { cn } from "@/lib/utils";

const menuGroups = [
  {
    persona: "Town Eye",
    items: [
      { name: "Town Plaza", href: "/assistant", icon: MessageSquare },
      { name: "Town Pulse", href: "/pulse", icon: BarChart3 },
      { name: "Town Activity", href: "/community-pulse", icon: Activity },
    ]
  },
  {
    persona: "Developer & Architect",
    icon: Briefcase,
    items: [
      { name: "Deal Radar", href: "/radar", icon: MapIcon },
      { name: "Buildability Brief", href: "/briefs", icon: FileText },
      { name: "Zoning Report", href: "/zoning", icon: Building2 },
      { name: "Proforma Analysis", href: "/proforma", icon: DollarSign },
      { name: "Permit Timeline", href: "/permit-timeline", icon: Clock },
    ]
  },
  {
    persona: "Zoning Attorney",
    icon: Scale,
    items: [
      { name: "Entitlements & Risk", href: "/civic-entitlements", icon: Landmark },
      { name: "Closing Risk Radar", href: "/closing-risk", icon: AlertTriangle },
      { name: "Precedent Search", href: "/precedents", icon: Search },
    ]
  },
  {
    persona: "Lender & Appraiser",
    icon: DollarSign,
    items: [
      { name: "Lender Risk Report", href: "/lender", icon: Shield },
      { name: "Market Trend Report", href: "/market", icon: TrendingUp },
    ]
  },
  {
    persona: "Realtor & Homeowner",
    icon: Home,
    items: [
      { name: "Listing Brief", href: "/realtor", icon: Home },
      { name: "Neighborhood Guide", href: "/neighborhood", icon: Compass },
      { name: "Homeowner Report", href: "/homeowner", icon: UserCircle },
    ]
  }
];

import { useState, useRef, useEffect } from "react";
import { useSharedAddress } from "@/hooks/useSharedAddress";

export function Sidebar() {
  const pathname = usePathname();
  const [address, setAddress] = useSharedAddress("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedTown, setSelectedTown] = useState("arlington-ma");
  const [showTownDropdown, setShowTownDropdown] = useState(false);
  
  const dropdownRef = useRef<HTMLDivElement>(null);
  const townDropdownRef = useRef<HTMLDivElement>(null);

  const towns = [
    { id: "arlington-ma", name: "Arlington, MA" },
    { id: "lexington-ma", name: "Lexington, MA", disabled: true },
    { id: "cambridge-ma", name: "Cambridge, MA", disabled: true }
  ];

  // Fetch real suggestions from the backend API as the user types
  useEffect(() => {
    if (!address.trim()) {
      setSuggestions([]);
      return;
    }
    
    const timeoutId = setTimeout(() => {
      fetch(`http://localhost:8000/api/parcels/suggest?q=${encodeURIComponent(address)}&town_slug=${selectedTown}&limit=5`)
        .then(res => res.json())
        .then(data => {
          if (data && data.suggestions) {
            setSuggestions(data.suggestions.map((s: any) => `${s.address}, ${s.town_name || s.town}`));
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
      if (townDropdownRef.current && !townDropdownRef.current.contains(event.target as Node)) {
        setShowTownDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="flex h-full w-64 flex-col bg-gray-900 border-r border-gray-800 text-white">
      <div className="flex h-16 shrink-0 items-center px-6 border-b border-gray-800 bg-gray-950">
        <Building2 className="h-8 w-8 text-blue-500 mr-3" />
        <span className="text-xl font-bold tracking-tight">Towneye.ai</span>
      </div>

      {/* Town / Market Selector */}
      <div className="p-4 border-b border-gray-800 bg-gray-900/80 relative" ref={townDropdownRef}>
        <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2 px-1">Active Market</div>
        <button 
          onClick={() => setShowTownDropdown(!showTownDropdown)}
          className="w-full flex items-center justify-between bg-gray-950 border border-gray-700 hover:border-gray-600 rounded-lg px-3 py-2 transition-colors"
        >
          <div className="flex items-center text-sm font-medium text-white">
            <Map className="h-4 w-4 mr-2 text-blue-400" />
            {towns.find(t => t.id === selectedTown)?.name}
          </div>
          <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${showTownDropdown ? 'rotate-180' : ''}`} />
        </button>

        {showTownDropdown && (
          <div className="absolute top-[80px] left-4 right-4 bg-gray-900 border border-gray-700 rounded-lg shadow-2xl z-[110] overflow-hidden">
            {towns.map(town => (
              <div 
                key={town.id}
                onClick={() => {
                  if (!town.disabled) {
                    setSelectedTown(town.id);
                    setShowTownDropdown(false);
                    setAddress(""); // Clear address when switching towns
                  }
                }}
                className={`px-4 py-3 flex items-center justify-between border-b border-gray-800 last:border-0 ${
                  town.disabled 
                    ? 'opacity-50 cursor-not-allowed bg-gray-900/50' 
                    : 'cursor-pointer hover:bg-gray-800 transition-colors'
                }`}
              >
                <span className="text-sm font-medium text-gray-200">{town.name}</span>
                {town.id === selectedTown && <div className="h-2 w-2 rounded-full bg-blue-500"></div>}
                {town.disabled && <span className="text-[10px] uppercase tracking-wider text-gray-500 bg-gray-800 px-2 py-0.5 rounded">Coming Soon</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Global Address Search */}
      <div className="p-4 border-b border-gray-800 bg-gray-900/30">
        <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2 px-1">Target Property</div>
        <div className="relative" ref={dropdownRef}>
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input 
            type="text" 
            placeholder={`Search within ${towns.find(t => t.id === selectedTown)?.name.split(',')[0]}...`}
            className="w-full bg-gray-950 border border-gray-700 rounded-lg py-2 pl-9 pr-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            value={address}
            onChange={(e) => {
              setAddress(e.target.value);
              setShowSuggestions(true);
            }}
            onFocus={() => setShowSuggestions(true)}
          />
          
          {/* Autofill Dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute top-full left-0 w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-2xl z-[100] overflow-hidden">
              {suggestions.map((suggestion, idx) => {
                const matchIndex = address.length > 0 ? suggestion.toLowerCase().indexOf(address.toLowerCase()) : -1;
                return (
                  <div 
                    key={idx}
                    className="px-3 py-2 hover:bg-gray-700 cursor-pointer text-xs text-gray-300 hover:text-white flex items-center transition-colors border-b border-gray-700 last:border-0"
                    onClick={() => {
                      setAddress(suggestion);
                      setShowSuggestions(false);
                    }}
                  >
                    <MapPin className="h-3 w-3 mr-2 text-blue-400 shrink-0" />
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
      </div>
      
      <div className="flex flex-1 flex-col overflow-y-auto px-4 py-6">
        {menuGroups.map((group, groupIdx) => (
          <div key={group.persona} className="mb-6">
            <div className="px-2 mb-2 flex items-center text-xs font-bold uppercase tracking-wider text-gray-500">
              {group.persona}
            </div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const isActive = pathname === item.href || (pathname === '/' && item.href === '/radar');
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className={cn(
                      isActive
                        ? "bg-purple-600/10 text-purple-400 border border-purple-500/20"
                        : "text-gray-300 hover:bg-gray-800 hover:text-white border border-transparent",
                      "group flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors"
                    )}
                  >
                    <item.icon
                      className={cn(
                        isActive ? "text-purple-400" : "text-gray-500 group-hover:text-gray-300",
                        "mr-3 h-4 w-4 flex-shrink-0 transition-colors"
                      )}
                      aria-hidden="true"
                    />
                    {item.name}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      
      <div className="flex shrink-0 p-4 border-t border-gray-800 space-x-2">
        <button className="flex-1 flex justify-center items-center py-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-md transition-colors">
          <Settings className="h-5 w-5" />
        </button>
        <button className="flex-1 flex justify-center items-center py-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-md transition-colors relative">
          <Bell className="h-5 w-5" />
          <span className="absolute top-2 right-4 block h-2 w-2 rounded-full bg-blue-500 ring-2 ring-gray-900" />
        </button>
      </div>
    </div>
  );
}
