import { useEffect, useState } from 'react';
import { fetchAddressIndex } from '../api';

/**
 * Load Arlington address index once — enables instant local autocomplete.
 */
export function useAddressIndex() {
  const [entries, setEntries] = useState(null);
  const [townName, setTownName] = useState('Arlington');
  const [townSlug, setTownSlug] = useState('arlington-ma');
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchAddressIndex();
        if (cancelled) return;
        const town = data?.towns?.[0];
        if (town?.entries?.length) {
          setEntries(
            town.entries.map((e) => ({
              address: e.address,
              parcel_id: e.parcel_id,
              town_slug: town.town_slug,
            })),
          );
          setTownName(town.town_name || 'Arlington');
          setTownSlug(town.town_slug || 'arlington-ma');
          setReady(true);
        }
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load address index');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { entries, townName, townSlug, ready, error };
}
