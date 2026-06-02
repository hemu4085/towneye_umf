import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import AddressInput from '../components/AddressInput';
import FlowSteps from '../components/FlowSteps';
import ReportGrid from '../components/ReportGrid';
import UserTypeSelector from '../components/UserTypeSelector';
import { checkApiHealth, fetchReportAvailability, resolveParcel } from '../api';

const DEFAULT_REQUEST_EMAIL = 'hemuit4085@gmail.com';

export default function Home() {
  const navigate = useNavigate();
  const location = useLocation();
  const [address, setAddress] = useState(location.state?.address || '');
  const [userType, setUserType] = useState(location.state?.userType || null);
  const [error, setError] = useState('');
  const [loadingReportId, setLoadingReportId] = useState(null);
  const [parcel, setParcel] = useState(null);
  const [availability, setAvailability] = useState(null);
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [requestEmail, setRequestEmail] = useState(DEFAULT_REQUEST_EMAIL);
  const [apiOnline, setApiOnline] = useState(true);
  const [apiChecking, setApiChecking] = useState(true);

  useEffect(() => {
    if (location.state?.address) setAddress(location.state.address);
    if (location.state?.userType) setUserType(location.state.userType);
  }, [location.state]);

  useEffect(() => {
    let cancelled = false;
    const stopChecking = setTimeout(() => {
      if (!cancelled) setApiChecking(false);
    }, 6000);

    (async () => {
      const ok = await checkApiHealth();
      if (!cancelled) {
        setApiOnline(ok);
        setApiChecking(false);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(stopChecking);
    };
  }, []);

  useEffect(() => {
    const trimmed = address.trim();
    if (!userType || trimmed.length < 5 || !apiOnline) {
      setParcel(null);
      setAvailability(null);
      setAvailabilityLoading(false);
      return undefined;
    }

    const timer = setTimeout(async () => {
      setAvailabilityLoading(true);
      try {
        const data = await fetchReportAvailability(trimmed);
        setParcel(data.parcel);
        setAvailability(data.reports);
        if (data.report_request_email) setRequestEmail(data.report_request_email);
        setError('');
      } catch (err) {
        setParcel(null);
        setAvailability(null);
        setError(err.message);
      } finally {
        setAvailabilityLoading(false);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [address, userType, apiOnline]);

  async function handleReportClick(report) {
    const status = availability?.[report.id];
    if (status && status.available === false) return;

    if (!address.trim()) {
      setError('Enter a property address.');
      return;
    }
    if (!userType) {
      setError('Select your role to choose a report.');
      return;
    }
    if (!apiOnline) {
      setError('Report API is waking up. Wait a few seconds and try again.');
      return;
    }

    setError('');
    setLoadingReportId(report.id);
    try {
      const resolved = parcel || (await resolveParcel(address.trim()));
      navigate(`/report/${report.id}`, {
        state: {
          report,
          parcel: resolved,
          userType,
          address: address.trim(),
        },
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingReportId(null);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="px-6 py-8 text-center border-b border-gold/20">
        <h1 className="font-display text-4xl md:text-5xl text-gold tracking-wide">TownEye</h1>
        <p className="text-graytown mt-2 text-lg">
          AI-Powered Real Estate Intelligence for Massachusetts
        </p>
      </header>

      <main className="flex-1 flex flex-col items-center px-6 py-12">
        <FlowSteps current={userType ? 'pick' : 'address'} />

        <div className="w-full max-w-6xl mx-auto flex flex-col items-center">
          {apiChecking && (
            <p className="w-full max-w-2xl mb-4 text-center text-sm text-graytown">
              Connecting to report services…
            </p>
          )}
          {!apiChecking && apiOnline === false && (
            <div className="w-full max-w-2xl mb-6 px-4 py-3 rounded-lg border border-gold/40 bg-gold/10 text-sm text-cream text-center">
              Report API is slow to respond (common on free hosting). Address search may still work —
              wait a few seconds and try again.
            </div>
          )}

          <AddressInput
            value={address}
            onChange={setAddress}
            suggestEnabled
          />
          <UserTypeSelector value={userType} onChange={setUserType} />

          {userType && (
            <div className="w-full mt-2">
              <h2 className="font-display text-lg text-cream text-center mt-6">
                Choose a report to generate
              </h2>
              <ReportGrid
                userType={userType}
                loadingId={loadingReportId}
                onGenerate={handleReportClick}
                availability={availability}
                availabilityLoading={availabilityLoading && apiOnline === true}
                address={address.trim()}
                parcel={parcel}
                requestEmail={requestEmail}
                apiOnline={apiOnline}
              />
            </div>
          )}

          {error && <p className="text-red-400 mt-4 text-center max-w-xl">{error}</p>}
        </div>
      </main>
    </div>
  );
}
