import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import ReportGrid from '../components/ReportGrid';
import { useParcel } from '../context/ParcelContext';
import { resolveParcel } from '../api';
import { Building2, MapPin, Tag, User, Banknote, Calendar } from 'lucide-react';

export default function Dashboard() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const { parcel, setParcel } = useParcel();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const address = state?.address;
  const userType = state?.userType || 'developer';
  const preparedFor = state?.preparedFor;

  useEffect(() => {
    if (!address) {
      navigate('/');
      return;
    }
    (async () => {
      try {
        const data = await resolveParcel({ address });
        setParcel(data);
        if (preparedFor) {
          sessionStorage.setItem('towneye_prepared_for', preparedFor);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [address, navigate, preparedFor, setParcel]);

  function handleGenerate(report) {
    navigate(`/report/${report.id}`, {
      state: {
        report,
        parcel,
        preparedFor,
        userType,
      },
    });
  }

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12">
        <div className="w-8 h-8 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mb-4"></div>
        <p className="text-slate-400 font-mono text-sm uppercase tracking-wider animate-pulse">Resolving Parcel Geometry...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center max-w-lg mx-auto mt-12">
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6">
          <p className="text-red-400 mb-6">{error}</p>
          <Link to="/" className="btn-outline inline-flex items-center gap-2">
            ← Return to Search
          </Link>
        </div>
      </div>
    );
  }

  const snap = parcel?.assessor_snapshot || {};

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      {/* Header Area */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className="px-2.5 py-1 rounded bg-slate-800 text-slate-300 text-xs font-mono border border-slate-700">
              Parcel {parcel.parcel_id}
            </span>
            <span className="px-2.5 py-1 rounded bg-brand-500/10 text-brand-400 text-xs font-mono border border-brand-500/20">
              {parcel.town_name}, MA
            </span>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">{parcel.address}</h1>
        </div>
        <Link to="/" className="text-sm text-slate-400 hover:text-white transition-colors flex items-center gap-1">
          ← New Search
        </Link>
      </div>

      {/* Snapshot Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <div className="glass-panel p-4 hover:border-slate-700 transition-colors">
          <div className="text-slate-500 mb-2 flex items-center gap-2">
            <User className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Owner</span>
          </div>
          <div className="text-sm text-slate-200 truncate" title={snap.owner}>{snap.owner || '—'}</div>
        </div>
        
        <div className="glass-panel p-4 hover:border-slate-700 transition-colors">
          <div className="text-slate-500 mb-2 flex items-center gap-2">
            <MapPin className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Lot Size</span>
          </div>
          <div className="text-sm text-slate-200">
            {snap.lot_size_sqft ? `${Math.round(snap.lot_size_sqft).toLocaleString()} sf` : '—'}
          </div>
        </div>

        <div className="glass-panel p-4 hover:border-slate-700 transition-colors">
          <div className="text-slate-500 mb-2 flex items-center gap-2">
            <Calendar className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Year Built</span>
          </div>
          <div className="text-sm text-slate-200">{snap.year_built || '—'}</div>
        </div>

        <div className="glass-panel p-4 hover:border-slate-700 transition-colors lg:col-span-2">
          <div className="text-slate-500 mb-2 flex items-center gap-2">
            <Building2 className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Zoning</span>
          </div>
          <div className="text-sm text-slate-200">
            <span className="font-mono text-brand-300">{snap.zoning_base || '—'}</span>
            {snap.zoning_overlay && <span className="text-slate-400"> + {snap.zoning_overlay}</span>}
          </div>
        </div>

        <div className="glass-panel p-4 hover:border-slate-700 transition-colors">
          <div className="text-slate-500 mb-2 flex items-center gap-2">
            <Banknote className="w-4 h-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Assessed</span>
          </div>
          <div className="text-sm text-slate-200">
            {snap.assessed_value ? `$${Math.round(snap.assessed_value).toLocaleString()}` : '—'}
          </div>
        </div>
      </div>

      {/* Reports Section */}
      <div className="pt-8 border-t border-slate-800">
        <h2 className="text-lg font-semibold text-white mb-6">Engine Modules</h2>
        <ReportGrid userType={userType} onGenerate={handleGenerate} />
      </div>
    </div>
  );
}
