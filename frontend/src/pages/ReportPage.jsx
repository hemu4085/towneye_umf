import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import FlowSteps from '../components/FlowSteps';
import LoadingState from '../components/LoadingState';
import ReportViewer from '../components/ReportViewer';
import { useParcel } from '../context/ParcelContext';
import { generateReport } from '../api';
import { consumeReportPrefetch } from '../reportPrefetch';
import { absoluteUrl, copyToClipboard } from '../utils/share';

export default function ReportPage() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [shareNotice, setShareNotice] = useState('');

  const { parcel: storedParcel, setParcel } = useParcel();
  const report = state?.report;
  const parcel = state?.parcel || storedParcel;
  const preparedFor = state?.preparedFor;
  const reportCacheKey = state?.reportCacheKey;

  useEffect(() => {
    if (state?.parcel?.parcel_id) {
      setParcel(state.parcel);
    }
  }, [state?.parcel, setParcel]);

  useEffect(() => {
    if (!report || !parcel) {
      navigate('/');
      return;
    }

    const payload = {
      address: parcel.address,
      parcel_id: parcel.parcel_id,
      town_slug: parcel.town_slug,
      prepared_for: preparedFor || undefined,
      lat: parcel.lat,
      lng: parcel.lng,
    };

    const prefetched = reportCacheKey ? consumeReportPrefetch(reportCacheKey) : null;
    const load = prefetched ?? generateReport(report.endpoint, payload);

    load
      .then((data) => setResult(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [report, parcel, preparedFor, reportCacheKey, navigate]);

  async function handleShare() {
    if (!result?.download_url) {
      setShareNotice('PDF download is optional in the demo — the brief preview above is the full report.');
      return;
    }
    const url = absoluteUrl(result.download_url);
    const ok = await copyToClipboard(url);
    setShareNotice(ok ? 'PDF link copied to clipboard.' : 'Could not copy link. Try Download PDF.');
  }

  if (!report) return null;

  return (
    <div className="min-h-screen w-full px-4 sm:px-8 lg:px-12 xl:px-16 py-8">
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
      <p className="text-graytown">{parcel?.address}</p>

      {loading && <LoadingState reportName={report.name} />}

      {error && (
        <div className="mt-6 p-4 rounded-lg bg-red-950/40 border border-red-800/50">
          <p className="text-red-300">{error}</p>
          <p className="text-sm text-graytown mt-2">
            Try <strong>Load demo property</strong> on the home page, then Buildability Brief again.
            If the API was cold, wait 30 seconds and retry.
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
