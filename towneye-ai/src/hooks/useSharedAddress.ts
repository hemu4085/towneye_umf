"use client";

import { useState, useEffect } from "react";

export function useSharedAddress(initialValue: string = "") {
  const [address, setAddressState] = useState<string>(initialValue);

  // Load from sessionStorage on mount and listen to global changes
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = sessionStorage.getItem("towneye_shared_address");
      if (stored) {
        setAddressState(stored);
      }

      // Listen for updates from other components
      const handleSync = (e: Event) => {
        const customEvent = e as CustomEvent;
        setAddressState(customEvent.detail);
      };

      window.addEventListener("towneye_address_changed", handleSync);
      return () => window.removeEventListener("towneye_address_changed", handleSync);
    }
  }, []);

  // Sync to sessionStorage and emit event to other components
  const setAddress = (newAddress: string) => {
    setAddressState(newAddress);
    if (typeof window !== "undefined") {
      sessionStorage.setItem("towneye_shared_address", newAddress);
      window.dispatchEvent(new CustomEvent("towneye_address_changed", { detail: newAddress }));
    }
  };

  return [address, setAddress] as const;
}
