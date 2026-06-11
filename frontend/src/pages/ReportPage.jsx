import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import DealRadarCriteriaPanel from '../components/DealRadarCriteriaPanel';
import ClosingRiskCriteriaPanel from '../components/ClosingRiskCriteriaPanel';
import FlowSteps from '../components/FlowSteps';
import LoadingState from '../components/LoadingState';
import ReportViewer from '../components/ReportViewer';
import { useParcel } from '../context/ParcelContext';
import { generateReport } from '../api';
import { consumeReportPrefetch } from '../reportPrefetch';
import { reportRequiresParcel } from '../reportCatalog';
import { absoluteUrl, copyToClipboard } from '../utils/share';

export default function ReportPage() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [shareNotice, setShareNotice] = useState('');
  const [appliedCriteria, setAppliedCriteria] = useState(null);

  const { parcel: storedParcel, setParcel } = useParcel();
  const report = state?.report;
  const townContext = state?.townContext;
  const parcel = state?.parcel || storedParcel;
  const preparedFor = state?.preparedFor;
  const reportCacheKey = state?.reportCacheKey;
  const townScoped = report && !reportRequiresParcel(report.id);
  const isDealRadar = report?.id === 'deal-radar';
  const isClosingRiskRadar = report?.id === 'closing-risk-radar';

  useEffect(() => {
    if (state?.parcel?.parcel_id) {
      setParcel(state.parcel);
    }
  }, [state?.parcel, setParcel]);

  const buildPayload = useCallback(
    (criteria) => {
      const ctx = townScoped
        ? (townContext || {
            town_slug: parcel?.town_slug,
            town_name: parcel?.town_name,
            address: parcel?.address,
            parcel_id: parcel?.parcel_id,
            lat: parcel?.lat,
            lng: parcel?.lng,
          })
        : parcel;

      const payload = {
        town_slug: ctx?.town_slug || parcel?.town_slug,
        prepared_for: preparedFor || undefined,
        address: ctx?.address || parcel?.address,
        lat: ctx?.lat ?? parcel?.lat,
        lng: ctx?.lng ?? parcel?.lng,
      };
      const highlightId = ctx?.parcel_id || parcel?.parcel_id;
      if (highlightId) payload.parcel_id = highlightId;
      if (criteria && Object.keys(criteria).length > 0) {
        payload.criteria = criteria;
      }
      return payload;
    },
    [townScoped, townContext, parcel, preparedFor],
  );

  const loadReport = useCallback(
    (criteria, usePrefetch = false) => {
      if (!report) {
        navigate('/');
        return undefined;
      }
      if (!townScoped && !parcel) {
        navigate('/');
        return undefined;
      }

      const payload = buildPayload(criteria);
      if (!payload.town_slug) {
        navigate('/');
        return undefined;
      }

      setLoading(true);
      setError('');

      const prefetched =
        usePrefetch && reportCacheKey ? consumeReportPrefetch(reportCacheKey) : null;
      const load = prefetched ?? generateReport(report.endpoint, payload);

      return load
        .then((data) => {
          setResult(data);
          if (data?.data?.criteria) {
            setAppliedCriteria(data.data.criteria);
          }
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    },
    [report, parcel, townScoped, buildPayload, reportCacheKey, navigate],
  );

  useEffect(() => {
    if (!report) {
      navigate('/');
      return;
    }
    if (!townScoped && !parcel) {
      navigate('/');
      return;
    }

    const payload = buildPayload(null);
    if (!payload.town_slug) {
      navigate('/');
      return;
    }

    setLoading(true);
    setError('');

    const prefetched = reportCacheKey ? consumeReportPrefetch(reportCacheKey) : null;
    const load = prefetched ?? generateReport(report.endpoint, payload);

    load
      .then((data) => {
        setResult(data);
        if (data?.data?.criteria) {
          setAppliedCriteria(data.data.criteria);
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
    // Initial load only — regenerations go through handleApplyCriteria.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.id, reportCacheKey]);

  async function handleShare() {
    if (!result?.download_url) {
      setShareNotice('PDF download is optional in the demo — the brief preview above is the full report.');
      return;
    }
    const url = absoluteUrl(result.download_url);
    const ok = await copyToClipboard(url);
    setShareNotice(ok ? 'PDF link copied to clipboard.' : 'Could not copy link. Try Download PDF.');
  }

  function handleApplyCriteria(criteria) {
    loadReport(criteria, false);
  }

  function handleResetCriteria() {
    setAppliedCriteria(null);
    loadReport(null, false);
  }

  if (!report) return null;

  const subtitle = townScoped
    ? `${townContext?.town_name || 'Town'}, MA — town-wide scan${
        townContext?.parcel_id ? ' (parcel highlighted)' : ''
      }`
    : parcel?.address;

  const townSlug = townContext?.town_slug || parcel?.town_slug;

  return (
    <div className="min-h-screen w-full px-4 sm:px-8 lg:px-12 xl:px-16 py-8 relative">
      <a href="/" className="absolute top-6 right-6 sm:top-8 sm:right-8 inline-block">
        <img src="/logo.png" alt="TownEye Logo" className="h-8 sm:h-10 w-auto opacity-80 hover:opacity-100 transition-opacity" />
      </a>
      <FlowSteps current="report" />

      <Link
        to="/"
        state={{
          address: state?.address || parcel?.address,
          userType: state?.userType,
          parcel,
        }}
        className="text-gold text-sm hover:underline"
      >
        ← Back to reports
      </Link>

      <h1 className="font-display text-2xl text-gold mt-4">
        {report.icon} {report.name}
      </h1>
      <p className="text-graytown">{subtitle}</p>

      {isDealRadar && townSlug && (
        <DealRadarCriteriaPanel
          townSlug={townSlug}
          appliedCriteria={appliedCriteria}
          loading={loading}
          onApply={handleApplyCriteria}
          onReset={handleResetCriteria}
        />
      )}

      {isClosingRiskRadar && townSlug && (
        <ClosingRiskCriteriaPanel
          townSlug={townSlug}
          appliedCriteria={appliedCriteria}
          loading={loading}
          onApply={handleApplyCriteria}
          onReset={handleResetCriteria}
        />
      )}

      {loading && <LoadingState reportName={report.name} />}

      {error && (
        <div className="mt-6 p-4 rounded-lg bg-red-950/40 border border-red-800/50">
          <p className="text-red-300">{error}</p>
          <p className="text-sm text-graytown mt-2">
            {townScoped ? (
              <>
                {isClosingRiskRadar ? (
                  <>
                    Closing Risk Radar scans permits and overlay flags town-wide — wait up to 45
                    seconds on a cold API and retry.
                  </>
                ) : (
                  <>
                    Deal Radar scans the pilot town from Gold data — wait 30 seconds on a cold API
                    and retry.
                  </>
                )}
              </>
            ) : (
              <>
                Try <strong>Quick demo — 5-7 Belknap St</strong>, select <strong>Developer</strong>,
                then retry Buildability or Pro Forma.
              </>
            )}
          </p>
        </div>
      )}

      {result && !loading && (
        <ReportViewer
          html={result.html}
          downloadUrl={result.download_url}
          onShare={handleShare}
          shareNotice={shareNotice}
        />
      )}

    </div>
  );
}
