"use client";

import { useEffect, useState } from "react";
import type { SharedParcel } from "@/lib/api";

const PARCEL_KEY = "towneye_shared_parcel";
const ADDRESS_KEY = "towneye_shared_address";
const PARCEL_EVENT = "towneye_parcel_changed";

export function readSharedParcel(): SharedParcel | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(PARCEL_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SharedParcel;
  } catch {
    return null;
  }
}

export function writeSharedParcel(parcel: SharedParcel | null) {
  if (typeof window === "undefined") return;
  if (parcel) {
    sessionStorage.setItem(PARCEL_KEY, JSON.stringify(parcel));
    sessionStorage.setItem(ADDRESS_KEY, parcel.address);
  } else {
    sessionStorage.removeItem(PARCEL_KEY);
    sessionStorage.removeItem(ADDRESS_KEY);
  }
  window.dispatchEvent(new CustomEvent(PARCEL_EVENT, { detail: parcel }));
}

export function useSharedParcel() {
  const [parcel, setParcelState] = useState<SharedParcel | null>(null);

  useEffect(() => {
    setParcelState(readSharedParcel());

    const onSync = () => setParcelState(readSharedParcel());
    window.addEventListener(PARCEL_EVENT, onSync);
    return () => window.removeEventListener(PARCEL_EVENT, onSync);
  }, []);

  const setParcel = (next: SharedParcel | null) => {
    setParcelState(next);
    writeSharedParcel(next);
  };

  return [parcel, setParcel] as const;
}
