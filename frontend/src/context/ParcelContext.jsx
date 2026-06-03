import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { loadStoredParcel, storeParcel } from '../utils/parcelStorage';

const ParcelContext = createContext(null);

export function ParcelProvider({ children }) {
  const [parcel, setParcelState] = useState(() => loadStoredParcel());

  const setParcel = useCallback((next) => {
    setParcelState(next);
    storeParcel(next);
  }, []);

  const value = useMemo(() => ({ parcel, setParcel }), [parcel, setParcel]);

  return <ParcelContext.Provider value={value}>{children}</ParcelContext.Provider>;
}

export function useParcel() {
  const ctx = useContext(ParcelContext);
  if (!ctx) {
    throw new Error('useParcel must be used within ParcelProvider');
  }
  return ctx;
}
