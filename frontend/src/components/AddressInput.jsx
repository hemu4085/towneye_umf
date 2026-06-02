import { useEffect, useRef, useState } from 'react';
import { suggestAddresses } from '../api';

/** Fire suggest quickly while typing (ms). */
const DEBOUNCE_MS = 120;

function minQueryLength(query) {
  const q = query.trim();
  if (q.length >= 3) return 3;
  if (q.length >= 2 && /\d/.test(q)) return 2;
  return 3;
}

export default function AddressInput({ value, onChange, onSubmit, disabled, suggestEnabled = true }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const rootRef = useRef(null);
  const abortRef = useRef(null);
  const listId = 'address-suggestions';

  useEffect(() => {
    const q = value.trim();
    const minLen = minQueryLength(q);

    if (!suggestEnabled || q.length < minLen) {
      setSuggestions([]);
      setOpen(false);
      setActiveIndex(-1);
      setLoading(false);
      return undefined;
    }

    setOpen(true);
    setLoading(true);

    const timer = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const results = await suggestAddresses(q, 8, controller.signal);
        if (controller.signal.aborted) return;
        setSuggestions(results);
        setOpen(results.length > 0);
        setActiveIndex(-1);
      } catch {
        if (controller.signal.aborted) return;
        setSuggestions((prev) => prev);
        setOpen((prev) => prev);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
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

  function pickSuggestion(item) {
    onChange(item.address);
    setOpen(false);
    setActiveIndex(-1);
  }

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
      if (activeIndex >= 0) {
        pickSuggestion(suggestions[activeIndex]);
      } else {
        onSubmit?.();
      }
    } else if (event.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  const showPanel = open && (suggestions.length > 0 || loading);

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
            if (value.trim().length >= minQueryLength(value) && (suggestions.length > 0 || loading)) {
              setOpen(true);
            }
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="e.g. 29 Walnut St, Arlington MA"
          className="w-full px-5 py-4 rounded-xl bg-navy-light border-2 border-gold/40
                     text-cream text-lg placeholder:text-graytown
                     focus:outline-none focus:border-gold"
        />

        {suggestEnabled && loading && value.trim().length >= minQueryLength(value) && (
          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-xs text-graytown pointer-events-none">
            Searching…
          </span>
        )}

        {showPanel && (
          <ul
            id={listId}
            role="listbox"
            className="absolute z-20 left-0 right-0 mt-2 max-h-72 overflow-y-auto
                       rounded-xl border border-gold/30 bg-navy-light shadow-xl"
          >
            {suggestions.map((item, index) => (
              <li key={`${item.parcel_id}-${item.address}`} role="option" aria-selected={index === activeIndex}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pickSuggestion(item)}
                  className={`w-full text-left px-4 py-3 transition-colors ${
                    index === activeIndex
                      ? 'bg-gold/20 text-cream'
                      : 'text-cream hover:bg-gold/10'
                  }`}
                >
                  <span className="block">{item.address}</span>
                  <span className="block text-xs text-graytown mt-0.5">
                    Parcel {item.parcel_id}
                  </span>
                </button>
              </li>
            ))}
            {loading && suggestions.length === 0 && (
              <li className="px-4 py-3 text-sm text-graytown">Finding addresses…</li>
            )}
          </ul>
        )}
      </div>
    </form>
  );
}
