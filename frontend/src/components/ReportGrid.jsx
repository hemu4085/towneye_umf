import PropertyChat from './PropertyChat';
import { reportTier, reportsForUserType } from '../reportCatalog';
import { buildReportRequestMailto } from '../utils/reportRequest';

const TIER_BADGE = {
  must: { label: 'Must-have', className: 'bg-gold text-navy' },
  useful: { label: 'Useful', className: 'bg-navy-light border border-gold/50 text-gold' },
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
  chatDisabled,
}) {
  const visibleReports = reportsForUserType(userType);

  if (visibleReports.length === 0) {
    return (
      <p className="text-center text-graytown mt-6">No reports configured for this role.</p>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6 items-stretch">
      <PropertyChat parcel={parcel} disabled={chatDisabled} />
      {visibleReports.map((r) => {
        const tier = reportTier(userType, r.id);
        const badge = tier ? TIER_BADGE[tier] : null;
        const isLoading = loadingId === r.id;
        const isDone = completed?.[r.id];
        const status = availability?.[r.id];
        const isUnavailable = apiOnline === true && status?.available === false;
        const isChecking = availabilityLoading && apiOnline === true && !status;

        const className = `text-left card transition-all ${
          isUnavailable
            ? 'opacity-70 border-graytown/30 cursor-not-allowed'
            : 'hover:border-gold cursor-pointer'
        } ${tier === 'must' && !isUnavailable ? 'ring-2 ring-gold bg-gold/10' : ''} ${
          isLoading ? 'shimmer' : ''
        } ${loadingId && !isLoading ? 'opacity-60' : ''}`;

        const mailto = buildReportRequestMailto(r, address || '', requestEmail, parcel);

        const content = (
          <>
            <div className="flex justify-between items-start gap-2">
              <span className="text-2xl">{r.icon}</span>
              {badge && !isUnavailable && (
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-semibold shrink-0 ${badge.className}`}
                >
                  {badge.label}
                </span>
              )}
            </div>
            <h3 className="font-display text-lg text-cream mt-2">{r.name}</h3>
            <p className="text-sm text-graytown mt-1">{r.description}</p>
            <p className="text-xs text-gold mt-3">{r.time}</p>
            {isChecking && (
              <p className="text-sm text-graytown mt-2">Checking availability…</p>
            )}
            {isUnavailable && (
              <p className="text-sm text-graytown mt-3">
                Not Available.{' '}
                <a
                  href={mailto}
                  className="text-gold underline hover:text-gold-light"
                  onClick={(e) => e.stopPropagation()}
                >
                  Request to generate it for you
                </a>
              </p>
            )}
            {isDone && !isUnavailable && (
              <p className="text-sm text-green-400 mt-2 font-medium">✓ View Report</p>
            )}
            {isLoading && <p className="text-sm text-gold mt-2">Generating…</p>}
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
