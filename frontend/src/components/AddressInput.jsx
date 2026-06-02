import { useEffect, useRef, useState } from 'react';
import { suggestAddresses } from '../api';

const DEBOUNCE_MS = 150;

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
  const rootRef = useRef(null);
  const listId = 'address-suggestions';

  useEffect(() => {
    const q = value.trim();
    const minLen = minQueryLength(q);

    if (!suggestEnabled || q.length < minLen) {
      setSuggestions([]);
      setOpen(false);
      setActiveIndex(-1);
      return undefined;
    }

    const timer = setTimeout(async () => {
      try {
        const results = await suggestAddresses(q, 8);
        setSuggestions(results);
        setOpen(results.length > 0);
        setActiveIndex(-1);
      } catch {
        setSuggestions([]);
        setOpen(false);
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
          type="text"
          role="combobox"
          aria-expanded={open && suggestions.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Enter a property address"
          className="w-full px-5 py-4 rounded-xl bg-navy-light border-2 border-gold/40
                     text-cream text-lg placeholder:text-graytown/80
                     focus:outline-none focus:border-gold"
        />

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
