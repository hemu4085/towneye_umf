"use client";

import { useSharedParcel } from "./useSharedParcel";

/** Address string synced with the globally selected parcel (sidebar). */
export function useSharedAddress(_initialValue = "") {
  const [parcel, setParcel] = useSharedParcel();

  const setAddress = (address: string) => {
    if (!address.trim()) {
      setParcel(null);
      return;
    }
    if (parcel) {
      setParcel({ ...parcel, address });
    }
  };

  return [parcel?.address || "", setAddress] as const;
}
