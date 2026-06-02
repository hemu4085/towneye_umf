import { useCallback, useEffect, useRef, useState } from 'react';
import { suggestAddresses } from '../api';

const DEBOUNCE_MS = 50;

function minQueryLength(query) {
  const q = query.trim();
  if (q.length >= 3) return 3;
  if (q.length >= 2 && /\d/.test(q)) return 2;
  return 3;
}

export default function AddressInput({
  value,
  onChange,
  onSubmit,
  disabled,
  suggestEnabled = true,
  onSuggestReady,
  onSelectSuggestion,
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [suggestError, setSuggestError] = useState('');

  const rootRef = useRef(null);
  const debounceRef = useRef(null);
  const requestRef = useRef(0);
  const listId = 'address-suggestions';

  const fetchSuggestions = useCallback(
    (raw) => {
      if (!suggestEnabled) return;

      const q = raw.trim();
      const minLen = minQueryLength(q);

      clearTimeout(debounceRef.current);

      if (q.length < minLen) {
        setSuggestions([]);
        setOpen(false);
        setSuggestError('');
        return;
      }

      debounceRef.current = setTimeout(async () => {
        const reqId = ++requestRef.current;
        setLoading(true);
        setSuggestError('');
        try {
          const results = await suggestAddresses(q, 8);
          if (reqId !== requestRef.current) return;
          setSuggestions(results);
          setOpen(results.length > 0);
          setActiveIndex(-1);
          if (results.length > 0) {
            onSuggestReady?.();
          } else {
            setSuggestError('No matches — include town (e.g. Arlington MA) or try the demo button below.');
          }
        } catch (err) {
          if (reqId !== requestRef.current) return;
          setSuggestions([]);
          setOpen(false);
          setSuggestError(err?.message || 'Address search failed. Wait a moment and try again.');
        } finally {
          if (reqId === requestRef.current) setLoading(false);
        }
      }, DEBOUNCE_MS);
    },
    [suggestEnabled, onSuggestReady],
  );

  useEffect(() => {
    fetchSuggestions(value);
  }, [value, fetchSuggestions]);

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
    fetchSuggestions(next);
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
      else onSubmit?.();
    } else if (event.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

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
          type="search"
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
          onInput={handleInputChange}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
            else if (value.trim().length >= minQueryLength(value)) fetchSuggestions(value);
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="e.g. 29 walnut, Arlington MA — pick from dropdown"
          className={`w-full px-5 py-4 rounded-xl bg-navy-light border-2 text-cream text-lg
                     placeholder:text-graytown/80 focus:outline-none focus:border-gold
                     ${loading ? 'border-gold/70' : 'border-gold/40'}`}
        />

        {loading && value.trim().length >= minQueryLength(value) && (
          <p className="mt-2 text-center text-xs text-gold animate-pulse">Searching addresses…</p>
        )}

        {suggestError && !loading && (
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
