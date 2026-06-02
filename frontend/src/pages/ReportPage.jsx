import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import FlowSteps from '../components/FlowSteps';
import LoadingState from '../components/LoadingState';
import ReportViewer from '../components/ReportViewer';
import { generateReport } from '../api';
import { absoluteUrl, copyToClipboard } from '../utils/share';

export default function ReportPage() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [shareNotice, setShareNotice] = useState('');

  const report = state?.report;
  const parcel = state?.parcel;
  const preparedFor = state?.preparedFor;

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

    (async () => {
      try {
        const data = await generateReport(report.endpoint, payload);
        setResult(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [report, parcel, preparedFor, navigate]);

  async function handleShare() {
    if (!result?.download_url) {
      setShareNotice('PDF is not ready to share yet.');
      return;
    }
    const url = absoluteUrl(result.download_url);
    const ok = await copyToClipboard(url);
    setShareNotice(ok ? 'PDF link copied to clipboard.' : 'Could not copy link. Try Download PDF.');
  }

  if (!report) return null;

  return (
    <div className="min-h-screen px-4 py-8 max-w-5xl mx-auto">
      <FlowSteps current="report" />

      <Link
        to="/"
        state={{ address: state?.address || parcel?.address, userType: state?.userType }}
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
            Demo tip: pick <strong>29 Walnut St</strong>, role <strong>RE Agent</strong>, then{' '}
            <strong>Buildability Brief</strong>. If this is your first visit today, wait ~30s and
            try again while Render wakes up.
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
