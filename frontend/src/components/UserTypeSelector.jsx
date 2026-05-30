import { USER_TYPES } from '../reportCatalog';

export default function UserTypeSelector({ value, onChange }) {
  return (
    <div className="flex flex-wrap justify-center gap-2 mt-6">
      {USER_TYPES.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onChange(t.id)}
          className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
            value === t.id
              ? 'bg-gold text-navy'
              : 'bg-navy-light border border-gold/30 text-cream hover:border-gold'
          }`}
          aria-pressed={value === t.id}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
