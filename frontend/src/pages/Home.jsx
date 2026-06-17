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
  fetchTownReportAvailability,
  generateReport,
  getApiHealth,
  resolveParcel,
} from '../api';
import { useAddressIndex } from '../hooks/useAddressIndex';
import { DEMO_PROPERTY } from '../demoProperty';
import { reportCacheKey, startReportPrefetch } from '../reportPrefetch';
import { reportRequiresParcel } from '../reportCatalog';
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

function townLabel(slug, fallbackName) {
  if (fallbackName) return fallbackName;
  const prefix = (slug || '').split('-')[0] || 'town';
  return `${prefix.charAt(0).toUpperCase()}${prefix.slice(1)}`;
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
  const [pilotTownSlug, setPilotTownSlug] = useState(DEMO_PROPERTY.town_slug);
  const [pilotTownName, setPilotTownName] = useState(DEMO_PROPERTY.town_name);
  const {
    entries: addressEntries,
    townName,
    ready: indexReady,
    loading: indexLoading,
    error: indexError,
  } = useAddressIndex();
  const pilotTownShort = townName || pilotTownName || pilotTown.split(',')[0]?.trim() || 'town';

  const refreshApiHealth = useCallback(async () => {
    setApiChecking(true);
    try {
      const data = await getApiHealth();
      const ok = data?.status === 'ok';
      setApiOnline(ok);
      if (data?.towns?.[0]) {
        const slug = data.towns[0];
        setPilotTownSlug(slug);
        const name = slug.split('-')[0];
        const label = `${name.charAt(0).toUpperCase()}${name.slice(1)}`;
        setPilotTownName(label);
        setPilotTown(`${label} MA`);
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

  useEffect(() => {
    if (!userType || !pilotTownSlug) return undefined;

    const timer = setTimeout(async () => {
      setAvailabilityLoading(true);
      try {
        const townData = await fetchTownReportAvailability(pilotTownSlug);
        let merged = { ...(townData.reports || {}) };
        if (townData.report_request_email) setRequestEmail(townData.report_request_email);
        setApiOnline(true);

        const trimmed = address.trim();
        if (trimmed.length >= 3 && parcel?.parcel_id) {
          const parcelData = await fetchReportAvailability(resolvePayload(trimmed, parcel));
          merged = { ...merged, ...(parcelData.reports || {}) };
          if (parcelData.parcel) setParcel(parcelData.parcel);
          if (parcelData.report_request_email) setRequestEmail(parcelData.report_request_email);
        }
        setAvailability(merged);
      } catch {
        /* parcel reports still resolve on click */
      } finally {
        setAvailabilityLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [address, userType, parcel?.parcel_id, parcel?.town_slug, pilotTownSlug, setParcel]);

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

  async function generateTownReport(report) {
    if (!userType) {
      setError('Select your role to run a town-wide scan.');
      return;
    }
    setError('');
    setLoadingReportId(report.id);
    try {
      if (!apiOnline) await refreshApiHealth();

      const townSlug = pilotTownSlug || DEMO_PROPERTY.town_slug;
      const townNameLabel = pilotTownName || townLabel(townSlug);
      const highlightParcelId = parcel?.parcel_id || undefined;
      const townContext = {
        town_slug: townSlug,
        town_name: townNameLabel,
        parcel_id: highlightParcelId,
        address: highlightParcelId ? parcel.address : `${townNameLabel}, MA`,
        lat: parcel?.lat,
        lng: parcel?.lng,
      };

      const payload = {
        town_slug: townSlug,
        parcel_id: highlightParcelId,
        address: townContext.address,
        lat: townContext.lat,
        lng: townContext.lng,
      };
      const cacheKey = reportCacheKey(report.id, highlightParcelId, townSlug);
      startReportPrefetch(cacheKey, generateReport(report.endpoint, payload));
      navigate(`/report/${report.id}`, {
        state: {
          report,
          townContext,
          parcel: highlightParcelId ? parcel : null,
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

  async function handleReportClick(report) {
    const status = availability?.[report.id];
    if (status && status.available === false) return;

    if (!reportRequiresParcel(report.id)) {
      await generateTownReport(report);
      return;
    }

    if (!address.trim()) {
      setError(`Enter a property address in ${pilotTownShort}, or use the demo button.`);
      return;
    }
    if (!userType) {
      setError('Select your role (Developer, Attorney, etc.) to choose a report.');
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
      const cacheKey = reportCacheKey(report.id, resolved.parcel_id, resolved.town_slug);
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
  const showDeveloperDealRadarHint = userType === 'developer';
  const showAttorneyClosingRiskHint = userType === 'attorney';

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-200">
      <header className="px-6 py-12 text-center relative border-b border-slate-800 bg-slate-900/50 backdrop-blur-md">
        <a href="/" className="absolute top-6 left-6 sm:top-8 sm:left-8 inline-flex items-center gap-2 group">
          <div className="w-8 h-8 rounded bg-brand-500/20 border border-brand-500/50 flex items-center justify-center">
            <div className="w-4 h-4 bg-brand-400 rounded-sm" />
          </div>
          <span className="font-sans font-semibold text-lg tracking-wide text-white group-hover:text-brand-400 transition-colors">TownEye</span>
        </a>
        <h1 className="font-sans font-bold text-4xl md:text-5xl text-white tracking-tight">Municipal Intelligence Engine</h1>
        <p className="text-slate-400 mt-4 text-lg max-w-2xl mx-auto font-light">
          Institutional-grade feasibility, underwriting, and risk analysis for real estate developers and lenders.
        </p>
        <p className="text-xs font-mono text-brand-400/80 mt-6 uppercase tracking-widest bg-brand-500/10 inline-block px-3 py-1 rounded-full border border-brand-500/20">
          Pilot Active: {pilotTown}
        </p>
      </header>

      <main className="flex-1 flex flex-col items-center px-6 py-12 bg-slate-950 relative overflow-hidden">
        {/* Subtle grid background */}
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCI+PGRlZnM+PHBhdHRlcm4gaWQ9ImdyaWQiIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHBhdGggZD0iTSAwIDQwIEwgNDAgNDAgTCA0MCAwIiBmaWxsPSJub25lIiBzdHJva2U9InJnYmEoMjU1LDI1NSwyNTUsMC4wMykiIHN0cm9rZS13aWR0aD0iMSIvPjwvcGF0dGVybj48L2RlZnM+PHJlY3Qgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgZmlsbD0idXJsKCNncmlkKSIvPjwvc3ZnPg==')] pointer-events-none" />
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
                Suggestions appear <strong className="text-cream">as you type</strong> — pick one for
                parcel reports, or skip for <strong className="text-cream">town-wide scans</strong>.
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
            className="mt-4 text-xs font-mono text-slate-400 border border-slate-700/50 rounded px-3 py-1.5 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            Load Demo Address (5-7 Belknap St)
          </button>

          <ApiStatusBar online={apiOnline} checking={apiChecking} onRetry={refreshApiHealth} />

          <UserTypeSelector value={userType} onChange={setUserType} />

          {showDeveloperDealRadarHint && (
            <div className="w-full max-w-2xl mt-6 p-4 rounded-lg border border-gold/30 bg-gold/5 text-center">
              <p className="text-cream text-sm leading-relaxed">
                <strong>Deal Radar</strong> scans all of {pilotTownShort} — no address required.
                Pick an address only if you want that parcel highlighted in the ranked list.
              </p>
              <p className="text-xs text-gold/90 mt-2">
                Parcel reports (Buildability, Pro Forma, Risk) still need an address from the dropdown.
              </p>
            </div>
          )}

          {showAttorneyClosingRiskHint && (
            <div className="w-full max-w-2xl mt-6 p-4 rounded-lg border border-gold/30 bg-gold/5 text-center">
              <p className="text-cream text-sm leading-relaxed">
                <strong>Closing Risk Radar</strong> scans all of {pilotTownShort} for open/expired
                permits, flood SFHA, wetlands, and historic flags — no address required.
              </p>
              <p className="text-xs text-gold/90 mt-2">
                Pick an address to highlight a parcel, or run Buildability / Risk on a specific property.
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
                  Town-wide scans are ready for {pilotTownShort}. Select an address for parcel-level reports.
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
    </div>
  );
}
