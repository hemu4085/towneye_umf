"use client";

import { useState } from "react";
import { Send, Bot, User, FileText, Search, Loader2 } from "lucide-react";

export default function AssistantPage() {
  const [query, setQuery] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello! I am the Arlington Civic Assistant. I have been trained on the Arlington Zoning Bylaw, the last 12 months of Town Meeting minutes, and public property data. How can I help you today?",
      citations: []
    }
  ]);

  const handleSend = () => {
    if (!query.trim()) return;

    // Add user message
    const newMessages = [...messages, { role: "user", content: query, citations: [] }];
    setMessages(newMessages);
    setQuery("");
    setIsTyping(true);

    // Mock API response delay
    setTimeout(() => {
      let mockResponse = "";
      let mockCitations: any[] = [];

      if (newMessages[newMessages.length - 1].content.toLowerCase().includes("adu") || newMessages[newMessages.length - 1].content.toLowerCase().includes("accessory")) {
        mockResponse = "Based on the recent Arlington Zoning Bylaw amendments, you can build an Accessory Dwelling Unit (ADU) on a 6,000 sq ft lot in most residential districts (R0, R1, R2). The ADU cannot exceed 900 sq ft or 50% of the Gross Floor Area of the principal dwelling, whichever is smaller. No additional parking is required for the ADU.";
        mockCitations = [
          { title: "Arlington Zoning Bylaw - Section 5.9 (ADUs)", type: "pdf" },
          { title: "Town Meeting Minutes - Art. 43 (May 2024)", type: "meeting" }
        ];
      } else {
        mockResponse = "I can help with that. Based on the municipal data, recent commercial development has been heavily concentrated along the Mass Ave corridor, specifically near the Heights. There are currently 14 active commercial building permits in that zone.";
        mockCitations = [
          { title: "Building Permits Dataset (2024-YTD)", type: "data" }
        ];
      }

      setMessages([...newMessages, { role: "assistant", content: mockResponse, citations: mockCitations }]);
      setIsTyping(false);
    }, 2000);
  };

  return (
    <div className="flex-1 flex flex-col bg-gray-950 h-full">
      <div className="px-8 py-6 border-b border-gray-800 shrink-0">
        <h1 className="text-2xl font-bold text-white mb-2">Zoning AI Assistant</h1>
        <p className="text-gray-400 text-sm">Ask questions about zoning codes, meeting minutes, and municipal data.</p>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto p-8 space-y-6">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex max-w-[80%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              
              <div className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center ${
                msg.role === 'user' ? 'bg-blue-600 ml-4' : 'bg-purple-600 mr-4'
              }`}>
                {msg.role === 'user' ? <User size={20} className="text-white" /> : <Bot size={20} className="text-white" />}
              </div>

              <div className="flex flex-col">
                <div className={`p-4 rounded-2xl ${
                  msg.role === 'user' 
                    ? 'bg-blue-600 text-white rounded-tr-none' 
                    : 'bg-gray-800 text-gray-100 rounded-tl-none border border-gray-700'
                }`}>
                  <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                </div>

                {/* Citations */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {msg.citations.map((cite: any, i: number) => (
                      <div key={i} className="flex items-center text-xs px-2.5 py-1.5 bg-gray-900 border border-gray-700 text-gray-300 rounded-md cursor-pointer hover:bg-gray-800 transition-colors">
                        {cite.type === 'pdf' ? <FileText size={12} className="mr-1.5 text-red-400" /> : 
                         cite.type === 'meeting' ? <Search size={12} className="mr-1.5 text-blue-400" /> :
                         <BarChart size={12} className="mr-1.5 text-green-400" />}
                        {cite.title}
                      </div>
                    ))}
                  </div>
                )}
              </div>

            </div>
          </div>
        ))}
        
        {isTyping && (
          <div className="flex justify-start">
            <div className="flex max-w-[80%] flex-row">
              <div className="flex-shrink-0 h-10 w-10 rounded-full bg-purple-600 mr-4 flex items-center justify-center">
                <Bot size={20} className="text-white" />
              </div>
              <div className="p-4 rounded-2xl bg-gray-800 text-gray-100 rounded-tl-none border border-gray-700 flex items-center">
                <Loader2 size={18} className="animate-spin text-purple-400 mr-2" />
                <span className="text-sm text-gray-400">Searching Arlington databases...</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="p-6 bg-gray-900 border-t border-gray-800 shrink-0">
        <div className="max-w-4xl mx-auto relative">
          <textarea
            className="w-full bg-gray-950 border border-gray-700 rounded-xl py-4 pl-4 pr-14 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            rows={2}
            placeholder="E.g., Can I build an ADU on a 6,000 sq ft lot?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <button 
            onClick={handleSend}
            disabled={!query.trim() || isTyping}
            className="absolute right-3 bottom-4 p-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-lg transition-colors"
          >
            <Send size={18} />
          </button>
        </div>
        <div className="text-center mt-3 text-xs text-gray-500">
          AI can make mistakes. Verify zoning code information with the Arlington Inspectional Services Department.
        </div>
      </div>
    </div>
  );
}

// Just importing BarChart for the icon in citations
import { BarChart } from "lucide-react";
