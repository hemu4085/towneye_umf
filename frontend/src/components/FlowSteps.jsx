const STEPS = [
  { id: 'address', label: 'Address & role' },
  { id: 'pick', label: 'Pick report' },
  { id: 'report', label: 'HTML + PDF' },
];

export default function FlowSteps({ current }) {
  const idx = STEPS.findIndex((s) => s.id === current);

  return (
    <nav aria-label="Portal progress" className="w-full max-w-3xl mx-auto mb-8">
      <ol className="flex flex-wrap justify-center gap-2 md:gap-0 md:justify-between">
        {STEPS.map((step, i) => {
          const done = i < idx;
          const active = i === idx;
          return (
            <li
              key={step.id}
              className={`flex items-center text-xs md:text-sm ${
                active ? 'text-gold font-semibold' : done ? 'text-cream' : 'text-graytown'
              }`}
            >
              <span
                className={`inline-flex items-center justify-center w-6 h-6 rounded-full mr-1.5 text-xs font-bold shrink-0 ${
                  active
                    ? 'bg-gold text-navy'
                    : done
                      ? 'bg-gold/30 text-gold'
                      : 'bg-navy-light border border-gold/20'
                }`}
              >
                {done ? '✓' : i + 1}
              </span>
              <span className="hidden sm:inline">{step.label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
