import { useEffect, useState } from 'react';
import { askPropertyQuestion } from '../api';
import { loadChatMessages, storeChatMessages } from '../utils/chatStorage';

const STARTERS = [
  'Can I add an ADU?',
  'What is the zoning verdict?',
  'Can I add a garage?',
  'Any flood or historic constraints?',
];

function formatAnswer(text) {
  return (text || '').replace(/\*\*/g, '');
}

export default function PropertyChat({ parcel, disabled }) {
  const parcelId = parcel?.parcel_id ?? null;
  const [messages, setMessages] = useState(() => loadChatMessages(parcelId));
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setMessages(loadChatMessages(parcelId));
    setError('');
  }, [parcelId]);

  useEffect(() => {
    storeChatMessages(parcelId, messages);
  }, [parcelId, messages]);

  const parcelReady = Boolean(parcelId);
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
        {
          role: 'assistant',
          content: formatAnswer(data.answer),
          source: data.source,
        },
      ]);
    } catch (err) {
      setError(
        err?.message ||
          'Could not reach property Q&A. Wait a moment and try again, or generate a Buildability Brief.',
      );
    } finally {
      setLoading(false);
    }
  }

  const cardClass = `text-left card transition-all h-full flex flex-col ${
    parcelReady ? 'ring-2 ring-gold bg-gold/10 hover:border-gold' : 'hover:border-gold/60'
  } ${disabled ? 'opacity-60' : ''}`;

  return (
    <div className={cardClass}>
      <div className="flex justify-between items-start gap-2">
        <span className="text-2xl" aria-hidden>
          💬
        </span>
        <span className="text-xs px-2 py-0.5 rounded-full font-semibold shrink-0 bg-gold text-navy">
          Must-have
        </span>
      </div>

      <h3 className="font-display text-lg text-cream mt-2">Ask about this property</h3>
      <p className="text-sm text-graytown mt-1">
        {parcelReady
          ? 'Answers use live zoning, assessor, and constraint data for this parcel — not generic search.'
          : 'Pick an address from the dropdown (or Quick demo) to unlock Q&A.'}
      </p>
      <p className="text-xs text-gold mt-3">Grounded in TownEye Gold data</p>

      <div className="flex flex-wrap gap-1.5 mt-3">
        {STARTERS.map((s) => (
          <button
            key={s}
            type="button"
            disabled={inputDisabled}
            onClick={() => sendQuestion(s)}
            className="text-xs px-2 py-0.5 rounded-full border border-gold/40 text-gold hover:bg-gold/10
                       disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>

      {messages.length > 0 && (
        <ul className="mt-3 max-h-48 overflow-y-auto space-y-2 text-sm flex-1 min-h-0">
          {messages.map((m, i) => (
            <li
              key={`${m.role}-${i}`}
              className={`p-2 rounded-lg text-xs ${
                m.role === 'user' ? 'bg-navy-light' : 'bg-gold/10 text-cream'
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
        className="mt-auto pt-3 flex gap-2"
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
          placeholder={parcelReady ? 'e.g. Can I add a garage?' : 'Select a parcel first'}
          className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-navy-light border border-gold/40 text-cream text-sm
                     focus:outline-none focus:border-gold"
        />
        <button
          type="submit"
          disabled={inputDisabled || !input.trim()}
          className="btn-gold shrink-0 text-sm px-4 py-2"
        >
          {loading ? '…' : 'Ask'}
        </button>
      </form>

      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
    </div>
  );
}
