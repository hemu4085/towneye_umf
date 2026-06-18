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
  FileText
} from "lucide-react";
import { cn } from "@/lib/utils";

const navigation = [
  { name: "311 Pulse", href: "/pulse", icon: BarChart3 },
  { name: "Development Radar", href: "/radar", icon: MapIcon },
  { name: "Buildability Briefs", href: "/briefs", icon: FileText },
  { name: "Civic Assistant", href: "/assistant", icon: MessageSquare },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-64 flex-col bg-gray-900 border-r border-gray-800 text-white">
      <div className="flex h-16 shrink-0 items-center px-6 border-b border-gray-800">
        <Building2 className="h-8 w-8 text-blue-500 mr-3" />
        <span className="text-xl font-bold tracking-tight">Towneye.ai</span>
      </div>
      
      <div className="flex flex-1 flex-col overflow-y-auto px-4 py-6">
        <div className="space-y-1 mb-8">
          <p className="px-2 text-xs font-semibold uppercase tracking-wider text-gray-400 mb-4">
            Arlington MVP
          </p>
          {navigation.map((item) => {
            const isActive = pathname === item.href || (pathname === '/' && item.href === '/pulse');
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  isActive
                    ? "bg-blue-600/10 text-blue-400"
                    : "text-gray-300 hover:bg-gray-800 hover:text-white",
                  "group flex items-center rounded-md px-3 py-2.5 text-sm font-medium transition-colors"
                )}
              >
                <item.icon
                  className={cn(
                    isActive ? "text-blue-400" : "text-gray-400 group-hover:text-white",
                    "mr-3 h-5 w-5 flex-shrink-0 transition-colors"
                  )}
                  aria-hidden="true"
                />
                {item.name}
              </Link>
            );
          })}
        </div>
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
