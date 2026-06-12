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
  indexLoading = false,
  indexFailed = false,
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

  const hasLocalIndex = Boolean(addressEntries?.length);

  const runLocalSuggest = useCallback(
    (raw) => {
      const q = raw.trim();
      if (!q || !addressEntries?.length) return [];

      return filterLocalSuggestions(addressEntries, q, pilotTownHint, 8);
    },
    [addressEntries, pilotTownHint],
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

      if (indexLoading) {
        setLoading(true);
        setSuggestError('');
        setSuggestions([]);
        setOpen(false);
        return;
      }

      if (hasLocalIndex) {
        try {
          const local = runLocalSuggest(q);
          setSuggestions(local);
          setOpen(local.length > 0);
          setActiveIndex(-1);
          setLoading(false);
          setSuggestError(local.length ? '' : 'No matches — try another street or number');
          if (local.length) onSuggestReady?.();
        } catch {
          setSuggestError('Address suggestions unavailable — try again');
          setLoading(false);
        }
        return;
      }

      if (!indexFailed) {
        setLoading(true);
        setSuggestError('');
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
      hasLocalIndex,
      indexLoading,
      indexFailed,
      addressEntries,
      runLocalSuggest,
      onSuggestReady,
      pilotTownHint,
    ],
  );

  useEffect(() => {
    runSuggest(value);
  }, [value, runSuggest, indexReady, addressEntries, indexLoading, indexFailed]);

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

  const showIndexLoading = indexLoading && value.trim().length > 0;
  const showServerLoading = loading && !hasLocalIndex && !indexLoading && value.trim().length > 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit?.();
      }}
      className="w-full max-w-2xl mx-auto"
    >
      <div ref={rootRef} className="relative">
        <div className="relative flex items-center">
          <svg className="w-5 h-5 absolute left-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
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
            placeholder="Search by Street Address or APN (e.g. 5-7 Belknap St)"
            className={`w-full pl-12 pr-5 py-4 rounded-xl bg-slate-900/80 border text-white text-lg font-mono placeholder:text-slate-500 placeholder:font-sans focus:outline-none transition-all shadow-lg backdrop-blur-sm
                       ${open ? 'border-brand-500/50 shadow-[0_0_20px_rgba(59,130,246,0.1)]' : 'border-slate-800 focus:border-slate-600'}`}
          />
        </div>

        {showIndexLoading && (
          <p className="mt-2 text-center text-xs text-graytown">Loading address list…</p>
        )}

        {showServerLoading && (
          <p className="mt-2 text-center text-xs text-graytown">Searching addresses…</p>
        )}

        {suggestError && !showIndexLoading && !showServerLoading && value.trim() && (
          <p className="mt-2 text-center text-xs text-amber-300">{suggestError}</p>
        )}

        {open && suggestions.length > 0 && (
          <ul
            id={listId}
            role="listbox"
            className="absolute z-20 left-0 right-0 mt-2 max-h-64 overflow-y-auto
                       rounded-xl border border-slate-800 bg-slate-900 shadow-2xl backdrop-blur-md"
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
                  className={`w-full text-left px-4 py-3 text-[15px] font-mono transition-colors flex items-center justify-between group ${
                    index === activeIndex ? 'bg-brand-500/10 text-brand-300' : 'text-slate-300 hover:bg-slate-800/50 hover:text-white'
                  }`}
                >
                  <span>{item.address}</span>
                  <span className={`text-xs ${index === activeIndex ? 'text-brand-500/50' : 'text-slate-600 group-hover:text-slate-500'}`}>APN {item.parcel_id}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </form>
  );
}
