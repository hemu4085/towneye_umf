import { useEffect, useRef, useState } from 'react';
import { suggestAddresses } from '../api';

export default function AddressInput({ value, onChange, onSubmit, disabled }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);
  const rootRef = useRef(null);
  const listId = 'address-suggestions';

  useEffect(() => {
    const q = value.trim();
    if (q.length < 3) {
      setSuggestions([]);
      setOpen(false);
      setActiveIndex(-1);
      return undefined;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const results = await suggestAddresses(q);
        setSuggestions(results);
        setOpen(results.length > 0);
        setActiveIndex(-1);
      } catch {
        setSuggestions([]);
        setOpen(false);
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [value]);

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
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Enter any Massachusetts property address..."
          className="w-full px-5 py-4 rounded-xl bg-navy-light border-2 border-gold/40
                     text-cream text-lg placeholder:text-graytown
                     focus:outline-none focus:border-gold"
        />

        {loading && value.trim().length >= 3 && (
          <span className="absolute right-4 top-1/2 -translate-y-1/2 text-xs text-graytown">
            Searching…
          </span>
        )}

        {open && suggestions.length > 0 && (
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
          </ul>
        )}
      </div>
    </form>
  );
}
