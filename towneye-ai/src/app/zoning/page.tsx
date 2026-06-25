"use client";

import { Construction } from "lucide-react";

export default function StubPage() {
  return (
    <div className="flex-1 flex flex-col h-full bg-gray-950 items-center justify-center text-center p-8">
      <div className="bg-gray-900 border border-gray-800 p-8 rounded-2xl max-w-md">
        <div className="w-16 h-16 bg-purple-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
          <Construction className="h-8 w-8 text-purple-500" />
        </div>
        <h1 className="text-2xl font-bold text-white mb-3">Module Under Construction</h1>
        <p className="text-gray-400">
          This analytical report module is currently being wired up to the Arlington data pipeline. Check back soon!
        </p>
      </div>
    </div>
  );
}
