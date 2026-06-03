const STORAGE_KEY = 'towneye_portal_parcel';

export function loadStoredParcel() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    return p?.parcel_id ? p : null;
  } catch {
    return null;
  }
}

export function storeParcel(parcel) {
  try {
    if (parcel?.parcel_id) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(parcel));
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* private mode / quota */
  }
}
