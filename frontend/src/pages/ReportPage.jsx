import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import DealRadarCriteriaPanel from '../components/DealRadarCriteriaPanel';
import ClosingRiskCriteriaPanel from '../components/ClosingRiskCriteriaPanel';
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
  }, [report?.id, reportCacheKey]);

  async function handleShare() {
    if (!result?.download_url) {
      setShareNotice('PDF download is optional in the demo — the brief preview above is the full report.');
      return;
    }
    const url = absoluteUrl(result.download_url);
    const ok = await copyToClipboard(url);
    setShareNotice(ok ? 'PDF link copied to clipboard.' : 'Could not copy link.');
    setTimeout(() => setShareNotice(''), 3000);
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
    <div className="w-full flex flex-col h-[calc(100vh-64px)]">
      {/* Report Header Bar */}
      <div className="flex-none bg-slate-900 border-b border-slate-800 px-8 py-4 flex items-center justify-between z-10">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Link
              to="/dashboard"
              state={{
                address: state?.address || parcel?.address,
                userType: state?.userType,
                parcel,
              }}
              className="text-slate-400 hover:text-white transition-colors text-sm font-medium"
            >
              ← Back to Engine
            </Link>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-3">
            <span className="text-3xl leading-none">{report.icon}</span> 
            {report.name}
          </h1>
          <p className="text-slate-400 text-sm mt-1">{subtitle}</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6 relative">
        <div className="max-w-6xl mx-auto">
          {isDealRadar && townSlug && (
            <div className="mb-6">
              <DealRadarCriteriaPanel
                townSlug={townSlug}
                appliedCriteria={appliedCriteria}
                loading={loading}
                onApply={handleApplyCriteria}
                onReset={handleResetCriteria}
              />
            </div>
          )}

          {isClosingRiskRadar && townSlug && (
            <div className="mb-6">
              <ClosingRiskCriteriaPanel
                townSlug={townSlug}
                appliedCriteria={appliedCriteria}
                loading={loading}
                onApply={handleApplyCriteria}
                onReset={handleResetCriteria}
              />
            </div>
          )}

          {loading && (
            <div className="flex flex-col items-center justify-center p-12 glass-panel mt-4">
              <div className="w-8 h-8 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mb-4"></div>
              <p className="text-brand-400 font-mono text-sm uppercase tracking-wider animate-pulse">Running {report.name} Analysis...</p>
            </div>
          )}

          {error && (
            <div className="mt-6 p-6 rounded-xl bg-red-500/10 border border-red-500/20 backdrop-blur-sm">
              <p className="text-red-400 font-medium mb-2">Analysis Failed</p>
              <p className="text-red-300 text-sm">{error}</p>
              <p className="text-sm text-slate-400 mt-4">
                {townScoped ? 'Please wait 30-45 seconds on a cold API and retry the operation.' : 'Please try selecting a different address or user type.'}
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
      </div>
    </div>
  );
}
