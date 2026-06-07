import { useCallback, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import AddressInput from '../components/AddressInput';
import ApiStatusBar from '../components/ApiStatusBar';
import FlowSteps from '../components/FlowSteps';
import ReportGrid from '../components/ReportGrid';
import UserTypeSelector from '../components/UserTypeSelector';
import { useParcel } from '../context/ParcelContext';
import {
  fetchReportAvailability,
  generateReport,
  getApiHealth,
  resolveParcel,
} from '../api';
import { useAddressIndex } from '../hooks/useAddressIndex';
import { DEMO_PROPERTY } from '../demoProperty';
import { reportCacheKey, startReportPrefetch } from '../reportPrefetch';
import { addressesMatch } from '../utils/address';

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

function resolvePayload(address, parcel) {
  return {
    address: parcel?.address || address,
    parcel_id: parcel?.parcel_id,
    town_slug: parcel?.town_slug,
  };
}

export default function Home() {
  const navigate = useNavigate();
  const location = useLocation();
  const [address, setAddress] = useState(location.state?.address || '');
  const [userType, setUserType] = useState(location.state?.userType || null);
  const [error, setError] = useState('');
  const [loadingReportId, setLoadingReportId] = useState(null);
  const { parcel, setParcel } = useParcel();
  const [availability, setAvailability] = useState(null);
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [requestEmail, setRequestEmail] = useState(DEFAULT_REQUEST_EMAIL);
  const [apiOnline, setApiOnline] = useState(false);
  const [apiChecking, setApiChecking] = useState(true);
  const [pilotTown, setPilotTown] = useState('Arlington MA');
  const {
    entries: addressEntries,
    townName,
    ready: indexReady,
    loading: indexLoading,
    error: indexError,
  } = useAddressIndex();
  const pilotTownShort = townName || pilotTown.split(',')[0]?.trim() || 'town';

  const refreshApiHealth = useCallback(async () => {
    setApiChecking(true);
    try {
      const data = await getApiHealth();
      const ok = data?.status === 'ok';
      setApiOnline(ok);
      if (data?.towns?.[0]) {
        const slug = data.towns[0];
        const name = slug.split('-')[0];
        setPilotTown(`${name.charAt(0).toUpperCase()}${name.slice(1)} MA`);
      }
      return ok;
    } catch {
      setApiOnline(false);
      return false;
    } finally {
      setApiChecking(false);
    }
  }, []);

  useEffect(() => {
    if (location.state?.address) setAddress(location.state.address);
    if (location.state?.userType) setUserType(location.state.userType);
    if (location.state?.parcel?.parcel_id) {
      setParcel(location.state.parcel);
      if (!location.state?.address) {
        setAddress(location.state.parcel.address);
      }
    }
  }, [location.state, setParcel]);

  useEffect(() => {
    refreshApiHealth();
  }, [refreshApiHealth]);

  function handleAddressChange(value) {
    setAddress(value);
    if (parcel?.parcel_id && value.trim() && !addressesMatch(value, parcel.address)) {
      setParcel(null);
      setAvailability(null);
    }
  }

  function handleSuggestReady() {
    setApiOnline(true);
    setApiChecking(false);
  }

  function handleSelectSuggestion(item) {
    const p = parcelFromSuggestion(item);
    if (p) {
      setParcel(p);
      if (item.address) setAddress(item.address);
      setError('');
    }
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
    if (!userType) setUserType('developer');
  }

  useEffect(() => {
    const trimmed = address.trim();
    if (!userType || trimmed.length < 3 || !parcel?.parcel_id) {
      return undefined;
    }

    const timer = setTimeout(async () => {
      setAvailabilityLoading(true);
      try {
        const data = await fetchReportAvailability(resolvePayload(trimmed, parcel));
        setAvailability(data.reports);
        if (data.parcel) setParcel(data.parcel);
        if (data.report_request_email) setRequestEmail(data.report_request_email);
        setApiOnline(true);
      } catch {
        /* clicks still work — resolve happens on report generation */
      } finally {
        setAvailabilityLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [address, userType, parcel?.parcel_id, parcel?.town_slug]);

  async function handleReportClick(report) {
    const status = availability?.[report.id];
    if (status && status.available === false) return;

    if (!address.trim()) {
      setError(`Enter a property address in ${pilotTownShort}, or use the demo button.`);
      return;
    }
    if (!userType) {
      setError('Select your role (RE Agent or Developer) to choose a report.');
      return;
    }

    setError('');
    setLoadingReportId(report.id);
    try {
      if (!apiOnline) await refreshApiHealth();

      let resolved = parcel?.parcel_id ? parcel : null;
      if (!resolved) {
        resolved = await resolveParcel({
          address: address.trim(),
          parcel_id: parcel?.parcel_id,
          town_slug: parcel?.town_slug,
        });
      } else {
        resolved = await resolveParcel(resolvePayload(address.trim(), resolved));
      }
      setParcel(resolved);

      const payload = {
        address: resolved.address,
        parcel_id: resolved.parcel_id,
        town_slug: resolved.town_slug,
        lat: resolved.lat,
        lng: resolved.lng,
      };
      const cacheKey = reportCacheKey(report.id, resolved.parcel_id);
      startReportPrefetch(cacheKey, generateReport(report.endpoint, payload));
      navigate(`/report/${report.id}`, {
        state: {
          report,
          parcel: resolved,
          userType,
          address: address.trim(),
          reportCacheKey: cacheKey,
        },
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingReportId(null);
    }
  }

  const parcelReady = Boolean(parcel?.parcel_id);

  return (
    <>
      <header className="px-6 py-8 text-center border-b border-gold/20">
        <h1 className="font-display text-4xl md:text-5xl text-gold tracking-wide">TownEye</h1>
        <p className="text-graytown mt-2 text-lg">
          AI-Powered Real Estate Intelligence for Massachusetts
        </p>
        <p className="text-sm text-gold/80 mt-1">Pilot: {pilotTown} — any address in town</p>
      </header>

      <main className="flex-1 flex flex-col items-center px-6 py-12">
        <FlowSteps current={userType ? 'pick' : 'address'} />

        <div className="w-full max-w-6xl mx-auto flex flex-col items-center">
          <AddressInput
            value={address}
            onChange={handleAddressChange}
            onSuggestReady={handleSuggestReady}
            onSelectSuggestion={handleSelectSuggestion}
            pilotTownHint={pilotTown}
            addressEntries={addressEntries}
            indexReady={indexReady}
            indexLoading={indexLoading}
            indexFailed={Boolean(indexError)}
            suggestEnabled
          />

          <p className="text-center text-xs text-graytown mt-2 max-w-lg">
            {indexReady ? (
              <>
                Suggestions appear <strong className="text-cream">as you type</strong> — pick one, then
                choose your role and report.
              </>
            ) : (
              <>Loading {pilotTownShort} address list…</>
            )}
          </p>
          {indexError && (
            <p className="text-center text-xs text-amber-300 mt-1">{indexError}</p>
          )}

          <button
            type="button"
            onClick={loadDemoProperty}
            className="mt-3 text-sm text-gold border border-gold/40 rounded-full px-4 py-2
                       hover:bg-gold/10 transition-colors"
          >
            Quick demo — 5-7 Belknap St
          </button>

          <ApiStatusBar online={apiOnline} checking={apiChecking} onRetry={refreshApiHealth} />

          <UserTypeSelector value={userType} onChange={setUserType} />

          {userType === 'developer' && (
            <div className="w-full max-w-2xl mt-6 p-4 rounded-lg border border-gold/30 bg-gold/5 text-center">
              <p className="text-cream text-sm leading-relaxed">
                Instant buildability + pro forma for any {pilotTownShort} lot — zoning stack,
                overlay analysis, and indicative development economics before you option or design.
              </p>
              <p className="text-xs text-gold/90 mt-2">
                Start with <strong>Buildability Brief</strong>, then <strong>Development Pro Forma</strong>.
              </p>
            </div>
          )}

          {userType && (
            <div className="w-full mt-2">
              <h2 className="font-display text-lg text-cream text-center mt-6">
                Choose a report to generate
              </h2>
              {parcelReady ? (
                <p className="text-center text-xs text-green-400/90 mt-2">
                  Live parcel {parcel.parcel_id} — {parcel.address}
                </p>
              ) : (
                <p className="text-center text-xs text-amber-300/90 mt-2">
                  Select an address from the dropdown to lock the parcel
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

          {error && <p className="text-red-400 mt-4 text-center max-w-xl pb-4">{error}</p>}
        </div>
      </main>
    </>
  );
}
