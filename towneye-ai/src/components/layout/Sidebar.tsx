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
  UserCircle
} from "lucide-react";
import { cn } from "@/lib/utils";

const menuGroups = [
  {
    persona: "Platform",
    items: [
      { name: "Deal Radar", href: "/radar", icon: MapIcon },
      { name: "Zoning AI Assistant", href: "/assistant", icon: MessageSquare },
      { name: "311 Dashboard", href: "/pulse", icon: BarChart3 },
      { name: "Community Activity", href: "/community-pulse", icon: Activity },
    ]
  },
  {
    persona: "Developer & Architect",
    icon: Briefcase,
    items: [
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

// Need these extra icons
import { Clock, Search, Shield, AlertTriangle, TrendingUp } from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-64 flex-col bg-gray-900 border-r border-gray-800 text-white">
      <div className="flex h-16 shrink-0 items-center px-6 border-b border-gray-800">
        <Building2 className="h-8 w-8 text-blue-500 mr-3" />
        <span className="text-xl font-bold tracking-tight">Towneye.ai</span>
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
