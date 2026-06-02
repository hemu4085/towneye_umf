import { useCallback, useEffect, useRef, useState } from 'react';
import { suggestAddresses, warmSuggestCache } from '../api';

function minQueryLength(query) {
  const q = query.trim();
  if (q.length >= 3) return 3;
  if (q.length >= 2 && /\d/.test(q)) return 2;
  return 3;
}

function filterSuggestions(results, query) {
  const tokens = query.trim().toUpperCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return results;
  return results.filter((item) => {
    const addr = item.address.toUpperCase();
    return tokens.every((t) => addr.includes(t));
  });
}

function pickFromCache(cache, query) {
  const q = query.trim();
  if (cache.has(q)) return cache.get(q);

  let best = null;
  for (const [key, results] of cache) {
    if (q.startsWith(key) && key.length >= 2) {
      if (!best || key.length > best.key.length) {
        best = { key, results };
      }
    }
  }
  if (!best) return null;
  return filterSuggestions(best.results, q);
}

export default function AddressInput({ value, onChange, onSubmit, disabled, suggestEnabled = true }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [fetching, setFetching] = useState(false);

  const rootRef = useRef(null);
  const abortRef = useRef(null);
  const cacheRef = useRef(new Map());
  const seqRef = useRef(0);
  const listId = 'address-suggestions';

  useEffect(() => {
    if (suggestEnabled) warmSuggestCache();
  }, [suggestEnabled]);

  useEffect(() => {
    const q = value.trim();
    const minLen = minQueryLength(q);

    if (!suggestEnabled || q.length < minLen) {
      setSuggestions([]);
      setOpen(false);
      setActiveIndex(-1);
      setFetching(false);
      abortRef.current?.abort();
      return undefined;
    }

    const instant = pickFromCache(cacheRef.current, q);
    if (instant?.length) {
      setSuggestions(instant);
      setOpen(true);
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const seq = ++seqRef.current;
    setFetching(!instant?.length);

    (async () => {
      try {
        const results = await suggestAddresses(q, 8, controller.signal);
        if (controller.signal.aborted || seq !== seqRef.current) return;
        cacheRef.current.set(q, results);
        setSuggestions(results);
        setOpen(results.length > 0);
        setActiveIndex(-1);
      } catch {
        if (controller.signal.aborted || seq !== seqRef.current) return;
      } finally {
        if (!controller.signal.aborted && seq === seqRef.current) {
          setFetching(false);
        }
      }
    })();

    return () => controller.abort();
  }, [value, suggestEnabled]);

  useEffect(() => {
    function handleClickOutside(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
        setActiveIndex(-1);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const pickSuggestion = useCallback(
    (item) => {
      onChange(item.address);
      setOpen(false);
      setActiveIndex(-1);
    },
    [onChange],
  );

  function handleKeyDown(event) {
    if (!open || suggestions.length === 0) {
      if (event.key === 'Enter') {
        event.preventDefault();
        onSubmit?.();
      }
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((i) => (i + 1) % suggestions.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (activeIndex >= 0) pickSuggestion(suggestions[activeIndex]);
      else onSubmit?.();
    } else if (event.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  const showPanel = open && suggestions.length > 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit?.();
      }}
      className="w-full max-w-2xl mx-auto"
    >
      <div ref={rootRef} className="relative">
        <input
          type="text"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Start typing an address…"
          className="w-full px-5 py-4 pr-11 rounded-xl bg-navy-light border-2 border-gold/40
                     text-cream text-lg placeholder:text-graytown/80
                     focus:outline-none focus:border-gold transition-colors"
        />

        {fetching && suggestEnabled && (
          <span
            className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full
                       border-2 border-gold/30 border-t-gold animate-spin pointer-events-none"
            aria-hidden="true"
          />
        )}

        {showPanel && (
          <ul
            id={listId}
            role="listbox"
            className="absolute z-20 left-0 right-0 mt-1 max-h-64 overflow-y-auto
                       rounded-lg border border-gold/20 bg-navy-light shadow-2xl"
          >
            {suggestions.map((item, index) => (
              <li key={`${item.parcel_id}-${item.address}`} role="option" aria-selected={index === activeIndex}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pickSuggestion(item)}
                  className={`w-full text-left px-4 py-2.5 text-[15px] transition-colors ${
                    index === activeIndex ? 'bg-gold/15 text-cream' : 'text-cream/95 hover:bg-white/5'
                  }`}
                >
                  {item.address}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </form>
  );
}
