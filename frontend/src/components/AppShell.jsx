import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useParcel } from '../context/ParcelContext';

/** Syncs parcel from router state; layout chrome lives on each page. */
export default function AppShell({ children }) {
  const { state } = useLocation();
  const { setParcel } = useParcel();

  useEffect(() => {
    if (state?.parcel?.parcel_id) {
      setParcel(state.parcel);
    }
  }, [state?.parcel, setParcel]);

  return <div className="min-h-screen flex flex-col">{children}</div>;
}
