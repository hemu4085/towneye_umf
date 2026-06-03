import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import FlowSteps from '../components/FlowSteps';
import ReportGrid from '../components/ReportGrid';
import { useParcel } from '../context/ParcelContext';
import { resolveParcel } from '../api';

export default function Dashboard() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const { parcel, setParcel } = useParcel();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const address = state?.address;
  const userType = state?.userType || 'agent';
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
      <div className="min-h-screen flex flex-col items-center justify-center px-4">
        <FlowSteps current="dashboard" />
        <p className="text-gold animate-pulse">Resolving parcel…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen p-8 text-center">
        <p className="text-red-400 mb-4">{error}</p>
        <Link to="/" className="btn-outline inline-block">
          ← Back
        </Link>
      </div>
    );
  }

  const snap = parcel?.assessor_snapshot || {};

  return (
    <div className="min-h-screen px-4 py-8 max-w-6xl mx-auto">
      <FlowSteps current="pick" />

      <Link to="/" className="text-gold text-sm hover:underline">
        ← New search
      </Link>

      <div className="card mt-6">
        <h1 className="font-display text-2xl text-gold">{parcel.address}</h1>
        <p className="text-graytown text-sm mt-1">
          Parcel {parcel.parcel_id} · {parcel.town_name}, MA
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 text-sm">
          <div>
            <span className="text-graytown block">Owner</span>
            <span>{snap.owner || '—'}</span>
          </div>
          <div>
            <span className="text-graytown block">Lot size</span>
            <span>{snap.lot_size_sqft ? `${Math.round(snap.lot_size_sqft).toLocaleString()} sf` : '—'}</span>
          </div>
          <div>
            <span className="text-graytown block">Year built</span>
            <span>{snap.year_built || '—'}</span>
          </div>
          <div>
            <span className="text-graytown block">Zoning</span>
            <span>
              {snap.zoning_base || '—'}
              {snap.zoning_overlay ? ` + ${snap.zoning_overlay}` : ''}
            </span>
          </div>
          <div>
            <span className="text-graytown block">Assessed</span>
            <span>
              {snap.assessed_value
                ? `$${Math.round(snap.assessed_value).toLocaleString()}`
                : '—'}
            </span>
          </div>
          <div>
            <span className="text-graytown block">Use</span>
            <span>{snap.current_use || '—'}</span>
          </div>
        </div>
      </div>

      <h2 className="font-display text-xl mt-10 text-cream">Select a report</h2>
      <ReportGrid userType={userType} onGenerate={handleGenerate} />
    </div>
  );
}
