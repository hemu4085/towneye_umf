"use client";

import { useState, useEffect } from "react";

export function useSharedAddress(initialValue: string = "") {
  const [address, setAddressState] = useState<string>(initialValue);

  // Load from sessionStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = sessionStorage.getItem("towneye_shared_address");
      if (stored) {
        setAddressState(stored);
      }
    }
  }, []);

  // Sync to sessionStorage on change
  const setAddress = (newAddress: string) => {
    setAddressState(newAddress);
    if (typeof window !== "undefined") {
      sessionStorage.setItem("towneye_shared_address", newAddress);
    }
  };

  return [address, setAddress] as const;
}
