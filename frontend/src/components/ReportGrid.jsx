import { reportEngine, reportTier, reportsForUserType } from '../reportCatalog';
import { buildReportRequestMailto } from '../utils/reportRequest';

const TIER_BADGE = {
  must: { label: 'Primary', className: 'bg-brand-500 text-white shadow-[0_0_10px_rgba(59,130,246,0.5)]' },
  useful: { label: 'Secondary', className: 'bg-slate-800 border border-slate-700 text-slate-300' },
};

const ENGINE_BADGE = {
  deterministic: { label: 'Data-backed', className: 'border border-emerald-500/40 text-emerald-300' },
  hybrid: { label: 'Data + AI', className: 'border border-sky-500/40 text-sky-300' },
  llm: { label: 'AI-synthesized', className: 'border border-violet-500/40 text-violet-300' },
};

export default function ReportGrid({
  userType,
  onGenerate,
  loadingId,
  completed,
  availability,
  availabilityLoading,
  address,
  parcel,
  requestEmail,
  apiOnline,
}) {
  const visibleReports = reportsForUserType(userType);

  if (visibleReports.length === 0) {
    return (
      <p className="text-center text-graytown mt-6">No reports configured for this role.</p>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6 items-stretch">
      {visibleReports.map((r) => {
        const tier = reportTier(userType, r.id);
        const badge = tier ? TIER_BADGE[tier] : null;
        const engine = reportEngine(r.id);
        const engineBadge = ENGINE_BADGE[engine] || ENGINE_BADGE.deterministic;
        const isLoading = loadingId === r.id;
        const isDone = completed?.[r.id];
        const status = availability?.[r.id];
        const isUnavailable = apiOnline === true && status?.available === false;
        const isChecking = availabilityLoading && apiOnline === true && !status;

        const className = `text-left glass-panel transition-all p-5 relative overflow-hidden group ${
          isUnavailable
            ? 'opacity-70 border-slate-800/50 cursor-not-allowed'
            : 'hover:border-brand-500/50 hover:shadow-[0_0_20px_rgba(59,130,246,0.1)] cursor-pointer'
        } ${tier === 'must' && !isUnavailable ? 'ring-1 ring-brand-500 bg-brand-500/5' : ''} ${
          isLoading ? 'shimmer border-brand-500' : ''
        } ${loadingId && !isLoading ? 'opacity-50 grayscale-[50%]' : ''}`;

        const mailto = buildReportRequestMailto(r, address || '', requestEmail, parcel);

        const content = (
          <>
            <div className="flex justify-between items-start gap-2">
              <span className="text-2xl">{r.icon}</span>
              <div className="flex flex-col items-end gap-1 shrink-0">
                {badge && !isUnavailable && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-semibold ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                )}
                {!isUnavailable && (
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full ${engineBadge.className}`}
                  >
                    {engineBadge.label}
                  </span>
                )}
              </div>
            </div>
            <h3 className="font-sans font-semibold text-lg text-white mt-4 group-hover:text-brand-300 transition-colors">{r.name}</h3>
            <p className="text-sm text-slate-400 mt-2 leading-relaxed">{r.description}</p>
            <p className="text-xs font-mono text-brand-400/80 mt-4 uppercase tracking-wider">{r.time}</p>
            {isChecking && (
              <p className="text-sm text-slate-500 mt-3 flex items-center gap-2">
                <span className="w-3 h-3 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></span>
                Checking availability…
              </p>
            )}
            {isUnavailable && (
              <p className="text-sm text-slate-500 mt-3">
                Not Available.{' '}
                <a
                  href={mailto}
                  className="text-brand-400 hover:text-brand-300 underline underline-offset-2"
                  onClick={(e) => e.stopPropagation()}
                >
                  Request Override
                </a>
              </p>
            )}
            {isDone && !isUnavailable && (
              <p className="text-sm text-emerald-400 mt-3 font-medium flex items-center gap-1">✓ View Module</p>
            )}
            {isLoading && <p className="text-sm text-brand-400 mt-3 font-medium animate-pulse">Running Intelligence Engine…</p>}
          </>
        );

        if (isUnavailable) {
          return (
            <div key={r.id} className={className} aria-disabled="true">
              {content}
            </div>
          );
        }

        return (
          <button
            key={r.id}
            type="button"
            disabled={!!loadingId}
            onClick={() => onGenerate(r)}
            className={className}
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}
