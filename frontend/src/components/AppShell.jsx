import { useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { useParcel } from '../context/ParcelContext';
import { Activity, LayoutDashboard, Search, FileText, Settings, UserCircle } from 'lucide-react';
import clsx from 'clsx';

export default function AppShell({ children }) {
  const { state, pathname } = useLocation();
  const { setParcel } = useParcel();

  useEffect(() => {
    if (state?.parcel?.parcel_id) {
      setParcel(state.parcel);
    }
  }, [state?.parcel, setParcel]);

  const isHome = pathname === '/';

  if (isHome) {
    return <div className="min-h-screen flex flex-col bg-slate-950">{children}</div>;
  }

  // Enterprise Layout for Dashboard & Reports
  return (
    <div className="min-h-screen flex bg-slate-950 text-slate-200">
      {/* Sidebar */}
      <aside className="w-64 border-r border-slate-800 bg-slate-950/50 backdrop-blur-xl flex flex-col fixed inset-y-0 left-0 z-20">
        <div className="h-16 flex items-center px-6 border-b border-slate-800">
          <Link to="/" className="flex items-center gap-2 group">
            <Activity className="w-6 h-6 text-brand-500 group-hover:text-brand-400 transition-colors" />
            <span className="font-sans font-semibold text-lg tracking-wide text-white">TownEye</span>
          </Link>
        </div>
        
        <nav className="flex-1 px-4 py-6 space-y-1">
          <div className="text-xs font-mono text-slate-500 mb-4 px-2 uppercase tracking-wider">Engine</div>
          <Link to="/" className={clsx(
            "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
            "text-slate-400 hover:text-white hover:bg-slate-800/50"
          )}>
            <Search className="w-4 h-4" />
            New Deal Search
          </Link>
          <Link to="/dashboard" className={clsx(
            "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
            pathname === '/dashboard' ? "bg-brand-500/10 text-brand-400" : "text-slate-400 hover:text-white hover:bg-slate-800/50"
          )}>
            <LayoutDashboard className="w-4 h-4" />
            Parcel Dashboard
          </Link>
          <Link to="#" className={clsx(
            "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
            pathname.startsWith('/report') ? "bg-brand-500/10 text-brand-400" : "text-slate-400 hover:text-white hover:bg-slate-800/50"
          )}>
            <FileText className="w-4 h-4" />
            Reports
          </Link>
        </nav>

        <div className="p-4 border-t border-slate-800">
          <button className="flex items-center gap-3 px-3 py-2 w-full rounded-lg text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800/50 transition-colors">
            <UserCircle className="w-4 h-4" />
            User Settings
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 ml-64 flex flex-col min-h-screen">
        {/* Top Header */}
        <header className="h-16 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-10 px-8 flex items-center justify-between">
          <div className="flex-1 flex items-center gap-4">
            <div className="relative w-96 hidden md:block">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input 
                type="text" 
                placeholder="Command Palette (Cmd+K)" 
                className="w-full bg-slate-900 border border-slate-800 rounded-md py-1.5 pl-9 pr-4 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-brand-500/50 focus:border-brand-500/50 transition-all"
                disabled
              />
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="p-2 text-slate-400 hover:text-white transition-colors">
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 bg-slate-950">
          {children}
        </div>
      </main>
    </div>
  );
}
