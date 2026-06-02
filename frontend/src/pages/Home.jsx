import { useCallback, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import AddressInput from '../components/AddressInput';
import ApiStatusBar from '../components/ApiStatusBar';
import FlowSteps from '../components/FlowSteps';
import ReportGrid from '../components/ReportGrid';
import UserTypeSelector from '../components/UserTypeSelector';
import { checkApiHealth, fetchReportAvailability, generateReport, resolveParcel } from '../api';
import { DEMO_PROPERTY } from '../demoProperty';

const DEFAULT_REQUEST_EMAIL = 'hemuit4085@gmail.com';

function parcelFromSuggestion(item) {
  if (!item?.parcel_id) return null;
  return {
    address: item.address,
    parcel_id: item.parcel_id,
    town_slug: item.town_slug,
    town_name: item.town_name,
    lat: item.lat ?? null,
    lng: item.lng ?? null,
  };
}

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
  const [apiOnline, setApiOnline] = useState(false);
  const [apiChecking, setApiChecking] = useState(true);

  const refreshApiHealth = useCallback(async () => {
    setApiChecking(true);
    const ok = await checkApiHealth();
    setApiOnline(ok);
    setApiChecking(false);
    return ok;
  }, []);

  useEffect(() => {
    if (location.state?.address) setAddress(location.state.address);
    if (location.state?.userType) setUserType(location.state.userType);
  }, [location.state]);

  useEffect(() => {
    refreshApiHealth();
  }, [refreshApiHealth]);

  function handleSuggestReady() {
    setApiOnline(true);
    setApiChecking(false);
  }

  function handleSelectSuggestion(item) {
    const p = parcelFromSuggestion(item);
    if (p) setParcel(p);
  }

  function loadDemoProperty() {
    setAddress(DEMO_PROPERTY.address);
    setParcel({
      address: DEMO_PROPERTY.address,
      parcel_id: DEMO_PROPERTY.parcel_id,
      town_slug: DEMO_PROPERTY.town_slug,
      town_name: DEMO_PROPERTY.town_name,
      lat: DEMO_PROPERTY.lat,
      lng: DEMO_PROPERTY.lng,
    });
    setError('');
    if (!userType) setUserType('agent');
  }

  useEffect(() => {
    const trimmed = address.trim();
    if (!userType || trimmed.length < 5) {
      if (trimmed.length < 5) {
        setAvailability(null);
        setAvailabilityLoading(false);
      }
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
        setApiOnline(true);
      } catch (err) {
        setAvailability(null);
        setError(err.message);
      } finally {
        setAvailabilityLoading(false);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [address, userType]);

  async function handleReportClick(report) {
    const status = availability?.[report.id];
    if (status && status.available === false) return;

    if (!address.trim()) {
      setError('Enter a property address or use the demo property button.');
      return;
    }
    if (!userType) {
      setError('Select your role to choose a report.');
      return;
    }

    setError('');
    setLoadingReportId(report.id);
    try {
      if (!apiOnline) {
        await refreshApiHealth();
      }
      const resolved =
        parcel ||
        (await resolveParcel(address.trim()));
      setParcel(resolved);
      const payload = {
        address: resolved.address,
        parcel_id: resolved.parcel_id,
        town_slug: resolved.town_slug,
        lat: resolved.lat,
        lng: resolved.lng,
      };
      const reportPrefetch = generateReport(report.endpoint, payload);
      navigate(`/report/${report.id}`, {
        state: {
          report,
          parcel: resolved,
          userType,
          address: address.trim(),
          reportPrefetch,
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
          <AddressInput
            value={address}
            onChange={setAddress}
            onSuggestReady={handleSuggestReady}
            onSelectSuggestion={handleSelectSuggestion}
            suggestEnabled
          />

          <button
            type="button"
            onClick={loadDemoProperty}
            className="mt-3 text-sm text-gold border border-gold/40 rounded-full px-4 py-2
                       hover:bg-gold/10 transition-colors"
          >
            Load demo property — 29 Walnut St, Arlington
          </button>

          <ApiStatusBar online={apiOnline} checking={apiChecking} onRetry={refreshApiHealth} />

          <UserTypeSelector value={userType} onChange={setUserType} />

          {userType && (
            <div className="w-full mt-2">
              <h2 className="font-display text-lg text-cream text-center mt-6">
                Choose a report to generate
              </h2>
              {parcel && (
                <p className="text-center text-xs text-graytown mt-2">
                  Parcel {parcel.parcel_id} ready
                </p>
              )}
              <ReportGrid
                userType={userType}
                loadingId={loadingReportId}
                onGenerate={handleReportClick}
                availability={availability}
                availabilityLoading={availabilityLoading}
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
