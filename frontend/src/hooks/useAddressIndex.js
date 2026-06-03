import { useEffect, useState } from 'react';
import { fetchAddressIndex } from '../api';

const STATIC_INDEX_URL = '/address-index/arlington-ma.json';

function townFromPayload(data) {
  if (data?.towns?.[0]?.entries?.length) return data.towns[0];
  if (data?.entries?.length) {
    return {
      town_slug: data.town_slug || 'arlington-ma',
      town_name: 'Arlington',
      entries: data.entries,
    };
  }
  return null;
}

function applyTown(town, setters) {
  const { setEntries, setTownName, setTownSlug, setReady, setError } = setters;
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
  setError(null);
}

/**
 * Load Arlington address index — static JSON first (Vercel CDN), then API fallback.
 */
export function useAddressIndex() {
  const [entries, setEntries] = useState(null);
  const [townName, setTownName] = useState('Arlington');
  const [townSlug, setTownSlug] = useState('arlington-ma');
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const setters = { setEntries, setTownName, setTownSlug, setReady, setError };

    (async () => {
      setLoading(true);
      setError(null);

      try {
        const staticRes = await fetch(STATIC_INDEX_URL, { cache: 'force-cache' });
        if (staticRes.ok) {
          const data = await staticRes.json();
          const town = townFromPayload(data);
          if (town && !cancelled) {
            applyTown(town, setters);
            setLoading(false);
            return;
          }
        }
      } catch {
        /* try API */
      }

      try {
        const data = await fetchAddressIndex();
        if (cancelled) return;
        const town = townFromPayload(data);
        if (town) {
          applyTown(town, setters);
        } else {
          setError('Address index empty');
        }
      } catch (e) {
        if (!cancelled) {
          setError(e?.message || 'Could not load address index');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return { entries, townName, townSlug, ready, loading, error };
}
