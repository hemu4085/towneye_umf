import { useState } from 'react';
import { askPropertyQuestion } from '../api';

const STARTERS = [
  'Can I add an ADU?',
  'What is by-right?',
  'What is the zoning verdict?',
  'Any flood or historic constraints?',
];

export default function PropertyChat({ parcel, disabled }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const parcelReady = Boolean(parcel?.parcel_id);
  const inputDisabled = disabled || loading || !parcelReady;

  async function sendQuestion(text) {
    const q = text.trim();
    if (!q || inputDisabled) return;

    setError('');
    setLoading(true);
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: 'user', content: q }]);
    setInput('');

    try {
      const data = await askPropertyQuestion({
        address: parcel.address,
        parcel_id: parcel.parcel_id,
        town_slug: parcel.town_slug,
        question: q,
        history,
      });
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer, source: data.source },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-2xl mx-auto card border border-gold/30">
      <h3 className="font-display text-lg text-gold">Ask about this property</h3>
      {parcelReady ? (
        <p className="text-xs text-graytown mt-1">
          {parcel.address} — answers use TownEye zoning, assessor &amp; constraint data for this parcel.
        </p>
      ) : (
        <p className="text-xs text-amber-300/90 mt-1">
          Pick an address from the dropdown (or use Quick demo) to unlock Q&amp;A for that parcel.
        </p>
      )}

      <div className="flex flex-wrap gap-2 mt-3">
        {STARTERS.map((s) => (
          <button
            key={s}
            type="button"
            disabled={inputDisabled}
            onClick={() => sendQuestion(s)}
            className="text-xs px-3 py-1 rounded-full border border-gold/40 text-gold hover:bg-gold/10
                       disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>

      {messages.length > 0 && (
        <ul className="mt-4 max-h-64 overflow-y-auto space-y-3 text-sm">
          {messages.map((m, i) => (
            <li
              key={`${m.role}-${i}`}
              className={`p-3 rounded-lg ${
                m.role === 'user' ? 'bg-navy-light ml-8' : 'bg-gold/10 mr-4 text-cream'
              }`}
            >
              {m.role === 'user' ? (
                <span className="text-gold font-medium">You: </span>
              ) : (
                <span className="text-gold font-medium">TownEye: </span>
              )}
              <span className="whitespace-pre-wrap">{m.content}</span>
            </li>
          ))}
        </ul>
      )}

      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          sendQuestion(input);
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={inputDisabled}
          placeholder={
            parcelReady ? 'e.g. Can I build a second story?' : 'Select a parcel from the address dropdown first'
          }
          className="flex-1 px-4 py-2 rounded-lg bg-navy-light border border-gold/40 text-cream
                     focus:outline-none focus:border-gold"
        />
        <button
          type="submit"
          disabled={inputDisabled || !input.trim()}
          className="btn-gold shrink-0"
        >
          {loading ? '…' : 'Ask'}
        </button>
      </form>

      {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
    </div>
  );
}
