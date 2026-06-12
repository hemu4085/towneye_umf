import { USER_TYPES } from '../reportCatalog';

export default function UserTypeSelector({ value, onChange }) {
  return (
    <div className="w-full max-w-2xl mt-8">
      <label className="block text-xs font-mono text-slate-400 mb-3 text-center uppercase tracking-wider">Select Persona Profile</label>
      <div className="flex flex-wrap justify-center gap-3">
        {USER_TYPES.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 border ${
              value === t.id
                ? 'bg-brand-500/10 border-brand-500 text-brand-300 shadow-[0_0_15px_rgba(59,130,246,0.15)]'
                : 'bg-slate-900/50 border-slate-700/50 text-slate-400 hover:border-slate-600 hover:text-slate-200'
            }`}
            aria-pressed={value === t.id}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
