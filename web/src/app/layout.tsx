import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "Towneye.ai | Arlington Municipal Intelligence",
  description: "AI-powered municipal intelligence for Real Estate Developers, City Planners, and Citizens.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans bg-gray-950 text-gray-50 h-screen flex overflow-hidden antialiased">
        <Sidebar />
        <main className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 relative">
          {children}
        </main>
      </body>
    </html>
  );
}
