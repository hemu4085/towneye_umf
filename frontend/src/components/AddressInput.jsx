import { useCallback, useEffect, useRef, useState } from 'react';
import { suggestAddresses } from '../api';
import { filterLocalSuggestions } from '../utils/localSuggest';
import { normalizePilotSearchQuery } from '../utils/address';

const SERVER_DEBOUNCE_MS = 280;

export default function AddressInput({
  value,
  onChange,
  onSubmit,
  disabled,
  suggestEnabled = true,
  onSuggestReady,
  onSelectSuggestion,
  pilotTownHint = 'Arlington MA',
  addressEntries = null,
  indexReady = false,
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [suggestError, setSuggestError] = useState('');

  const rootRef = useRef(null);
  const serverDebounceRef = useRef(null);
  const requestRef = useRef(0);
  const listId = 'address-suggestions';

  const townName = pilotTownHint.split(',')[0]?.trim() || 'Arlington';

  const runLocalSuggest = useCallback(
    (raw) => {
      const q = raw.trim();
      if (!q || !addressEntries?.length) return [];

      return filterLocalSuggestions(addressEntries, q, townName, 8);
    },
    [addressEntries, townName],
  );

  const runSuggest = useCallback(
    (raw) => {
      if (!suggestEnabled) return;

      const q = raw.trim();
      clearTimeout(serverDebounceRef.current);

      if (!q) {
        setSuggestions([]);
        setOpen(false);
        setSuggestError('');
        setLoading(false);
        return;
      }

      if (indexReady && addressEntries?.length) {
        const local = runLocalSuggest(q);
        setSuggestions(local);
        setOpen(local.length > 0);
        setActiveIndex(-1);
        setLoading(false);
        setSuggestError(local.length ? '' : 'No matches — try another street or number');
        if (local.length) onSuggestReady?.();
        return;
      }

      setLoading(true);
      setSuggestError('');
      serverDebounceRef.current = setTimeout(async () => {
        const reqId = ++requestRef.current;
        try {
          const searchQ = normalizePilotSearchQuery(q, pilotTownHint);
          const results = await suggestAddresses(searchQ, 8);
          if (reqId !== requestRef.current) return;
          setSuggestions(results);
          setOpen(results.length > 0);
          setActiveIndex(-1);
          if (results.length) onSuggestReady?.();
          else setSuggestError('No matches — pick from list or use demo button');
        } catch (err) {
          if (reqId !== requestRef.current) return;
          setSuggestions([]);
          setOpen(false);
          setSuggestError(err?.message || 'Address search failed');
        } finally {
          if (reqId === requestRef.current) setLoading(false);
        }
      }, SERVER_DEBOUNCE_MS);
    },
    [
      suggestEnabled,
      indexReady,
      addressEntries,
      runLocalSuggest,
      onSuggestReady,
      pilotTownHint,
    ],
  );

  useEffect(() => {
    runSuggest(value);
  }, [value, runSuggest, indexReady, addressEntries]);

  useEffect(() => {
    function handleClickOutside(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
        setActiveIndex(-1);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, []);

  function handleInputChange(e) {
    const next = e.target.value;
    onChange(next);
  }

  function pickSuggestion(item) {
    onChange(item.address);
    onSelectSuggestion?.(item);
    setOpen(false);
    setActiveIndex(-1);
    setSuggestError('');
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
      if (activeIndex >= 0) pickSuggestion(suggestions[activeIndex]);
      else if (suggestions[0]) pickSuggestion(suggestions[0]);
      else onSubmit?.();
    } else if (event.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  const showServerLoading = loading && !indexReady && value.trim().length > 0;

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
          enterKeyHint="search"
          role="combobox"
          aria-expanded={open && suggestions.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          value={value}
          onChange={handleInputChange}
          onFocus={() => {
            if (value.trim()) runSuggest(value);
            if (suggestions.length > 0) setOpen(true);
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Start typing — e.g. 29 wal"
          className={`w-full px-5 py-4 rounded-xl bg-navy-light border-2 text-cream text-lg
                     placeholder:text-graytown/80 focus:outline-none focus:border-gold
                     ${open ? 'border-gold/70' : 'border-gold/40'}`}
        />

        {showServerLoading && (
          <p className="mt-2 text-center text-xs text-graytown">Loading address list…</p>
        )}

        {suggestError && !showServerLoading && value.trim() && (
          <p className="mt-2 text-center text-xs text-amber-300">{suggestError}</p>
        )}

        {open && suggestions.length > 0 && (
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
                  onTouchEnd={(e) => {
                    e.preventDefault();
                    pickSuggestion(item);
                  }}
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
