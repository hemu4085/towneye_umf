import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import PropertyChat from './PropertyChat';
import { useParcel } from '../context/ParcelContext';

export default function AppShell({ children }) {
  const { state } = useLocation();
  const { parcel, setParcel } = useParcel();

  useEffect(() => {
    if (state?.parcel?.parcel_id) {
      setParcel(state.parcel);
    }
  }, [state?.parcel, setParcel]);

  return (
    <div className="min-h-screen flex flex-col">
      <div className="flex-1">{children}</div>
      <footer className="sticky bottom-0 z-30 px-4 pb-4 pt-3 bg-navy/95 border-t border-gold/25 backdrop-blur-sm">
        <PropertyChat parcel={parcel} />
      </footer>
    </div>
  );
}
