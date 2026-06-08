import { useEffect, useMemo, useState } from 'react';
import { fetchClosingRiskRadarConfig } from '../api';

const SORT_LABELS = {
  risk_score: 'Risk score',
  open_permit_count: 'Open permits',
  assessed_value: 'Assessed value',
  tenure: 'Owner tenure',
};

function formFromCriteria(criteria) {
  const c = criteria || {};
  return {
    preset: c.preset || '',
    min_risk_signals: c.min_risk_signals ?? 1,
    min_open_permit_count: c.min_open_permit_count ?? '',
    include_open_permit: c.include_open_permit !== false,
    include_expired_permit: c.include_expired_permit !== false,
    include_flood_effective: c.include_flood_effective !== false,
    include_flood_preliminary: Boolean(c.include_flood_preliminary),
    require_flood_sfha_only: Boolean(c.require_flood_sfha_only),
    include_wetland: c.include_wetland !== false,
    include_historic: c.include_historic !== false,
    min_assessed_value: c.min_assessed_value ?? '',
    max_assessed_value: c.max_assessed_value ?? '',
    include_zone_codes: [...(c.include_zone_codes || [])],
    top_n: c.top_n ?? '',
    sort_by: c.sort_by || 'risk_score',
  };
}

function numOrNull(value) {
  if (value === '' || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function buildClosingRiskCriteriaPayload(form) {
  const payload = {};
  if (form.preset) payload.preset = form.preset;

  const numericFields = [
    'min_risk_signals',
    'min_open_permit_count',
    'min_assessed_value',
    'max_assessed_value',
    'top_n',
  ];
  for (const key of numericFields) {
    const val = numOrNull(form[key]);
    if (val !== null) payload[key] = val;
  }

  payload.include_open_permit = Boolean(form.include_open_permit);
  payload.include_expired_permit = Boolean(form.include_expired_permit);
  payload.include_flood_effective = Boolean(form.include_flood_effective);
  payload.include_flood_preliminary = Boolean(form.include_flood_preliminary);
  payload.require_flood_sfha_only = Boolean(form.require_flood_sfha_only);
  payload.include_wetland = Boolean(form.include_wetland);
  payload.include_historic = Boolean(form.include_historic);

  if (form.include_zone_codes?.length) {
    payload.include_zone_codes = form.include_zone_codes;
  }
  if (form.sort_by) payload.sort_by = form.sort_by;

  return payload;
}

function NumberField({ label, hint, value, onChange, min, max, step = 1 }) {
  return (
    <label className="block text-sm">
      <span className="text-cream">{label}</span>
      {hint && <span className="block text-xs text-graytown mt-0.5">{hint}</span>}
      <input
        type="number"
        className="mt-1 w-full rounded-lg bg-navy border border-gold/30 px-3 py-2 text-cream text-sm"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function ToggleField({ label, hint, checked, onChange }) {
  return (
    <label className="flex items-start gap-2 text-sm text-cream cursor-pointer">
      <input
        type="checkbox"
        className="rounded border-gold/40 mt-0.5"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        {label}
        {hint && <span className="block text-xs text-graytown">{hint}</span>}
      </span>
    </label>
  );
}

export default function ClosingRiskCriteriaPanel({
  townSlug,
  appliedCriteria,
  loading,
  onApply,
  onReset,
}) {
  const [open, setOpen] = useState(true);
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState('');
  const [form, setForm] = useState(() => formFromCriteria(null));

  useEffect(() => {
    let cancelled = false;
    setConfigError('');
    fetchClosingRiskRadarConfig(townSlug)
      .then((data) => {
        if (!cancelled) setConfig(data);
      })
      .catch((err) => {
        if (!cancelled) setConfigError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [townSlug]);

  useEffect(() => {
    const source = appliedCriteria || config?.defaults;
    if (source) setForm(formFromCriteria(source));
  }, [appliedCriteria, config?.defaults]);

  const limits = config?.limits || {};
  const zones = config?.zones || [];
  const presets = config?.presets || [];
  const sortOptions = config?.sort_options || ['risk_score'];

  const matchSummary = useMemo(() => {
    if (!appliedCriteria) return null;
    return appliedCriteria.preset
      ? `Preset: ${appliedCriteria.preset}`
      : 'Custom criteria applied';
  }, [appliedCriteria]);

  function patchForm(updates) {
    setForm((prev) => ({ ...prev, ...updates, preset: '' }));
  }

  function toggleZone(code) {
    setForm((prev) => {
      const set = new Set(prev.include_zone_codes);
      if (set.has(code)) set.delete(code);
      else set.add(code);
      return { ...prev, include_zone_codes: [...set].sort(), preset: '' };
    });
  }

  function applyPreset(name) {
    setForm((prev) => ({ ...prev, preset: name }));
    onApply({ preset: name });
  }

  function handleApply() {
    onApply(buildClosingRiskCriteriaPayload(form));
  }

  return (
    <section className="card mt-6">
      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <div>
          <h2 className="font-display text-lg text-gold">Screening criteria</h2>
          <p className="text-sm text-graytown mt-1">
            Filter town-wide closing risks — permits, flood, wetlands, historic.
            {matchSummary && (
              <span className="text-cream ml-1">({matchSummary})</span>
            )}
          </p>
        </div>
        <span className="text-gold text-sm shrink-0">{open ? 'Hide' : 'Show'}</span>
      </button>

      {configError && (
        <p className="text-sm text-red-300 mt-3">Could not load criteria config: {configError}</p>
      )}

      {open && (
        <div className="mt-5 space-y-6 border-t border-gold/20 pt-5">
          {presets.length > 0 && (
            <div>
              <p className="text-sm text-cream mb-2">Presets</p>
              <div className="flex flex-wrap gap-2">
                {presets.map((name) => (
                  <button
                    key={name}
                    type="button"
                    className={`btn-outline text-sm capitalize ${
                      form.preset === name || appliedCriteria?.preset === name
                        ? 'bg-gold/20 border-gold'
                        : ''
                    }`}
                    disabled={loading}
                    onClick={() => applyPreset(name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <NumberField
              label="Min risk signals"
              hint="How many flag types must match"
              value={form.min_risk_signals}
              min={limits.min_risk_signals?.[0]}
              max={limits.min_risk_signals?.[1]}
              onChange={(v) => patchForm({ min_risk_signals: v })}
            />
            <NumberField
              label="Min open permits"
              value={form.min_open_permit_count}
              min={limits.min_open_permit_count?.[0]}
              max={limits.min_open_permit_count?.[1]}
              onChange={(v) => patchForm({ min_open_permit_count: v })}
            />
            <NumberField
              label="Min assessed value ($)"
              value={form.min_assessed_value}
              min={limits.min_assessed_value?.[0]}
              max={limits.min_assessed_value?.[1]}
              step={1000}
              onChange={(v) => patchForm({ min_assessed_value: v })}
            />
            <NumberField
              label="Max assessed value ($)"
              value={form.max_assessed_value}
              min={limits.max_assessed_value?.[0]}
              max={limits.max_assessed_value?.[1]}
              step={1000}
              onChange={(v) => patchForm({ max_assessed_value: v })}
            />
            <NumberField
              label="Top results"
              value={form.top_n}
              min={limits.top_n?.[0]}
              max={limits.top_n?.[1]}
              onChange={(v) => patchForm({ top_n: v })}
            />
            <label className="block text-sm">
              <span className="text-cream">Sort by</span>
              <select
                className="mt-1 w-full rounded-lg bg-navy border border-gold/30 px-3 py-2 text-cream text-sm"
                value={form.sort_by}
                onChange={(e) => patchForm({ sort_by: e.target.value })}
              >
                {sortOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {SORT_LABELS[opt] || opt}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div>
            <p className="text-sm text-cream mb-3">Risk signal types</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <ToggleField
                label="Open building permits"
                checked={form.include_open_permit}
                onChange={(v) => patchForm({ include_open_permit: v })}
              />
              <ToggleField
                label="Expired permits"
                checked={form.include_expired_permit}
                onChange={(v) => patchForm({ include_expired_permit: v })}
              />
              <ToggleField
                label="FEMA flood (effective)"
                checked={form.include_flood_effective}
                onChange={(v) => patchForm({ include_flood_effective: v })}
              />
              <ToggleField
                label="FEMA flood (preliminary)"
                checked={form.include_flood_preliminary}
                onChange={(v) => patchForm({ include_flood_preliminary: v })}
              />
              <ToggleField
                label="SFHA only for flood flag"
                hint="When on, flood counts only in Special Flood Hazard Areas"
                checked={form.require_flood_sfha_only}
                onChange={(v) => patchForm({ require_flood_sfha_only: v })}
              />
              <ToggleField
                label="Wetland overlay"
                checked={form.include_wetland}
                onChange={(v) => patchForm({ include_wetland: v })}
              />
              <ToggleField
                label="Historic resource / district"
                checked={form.include_historic}
                onChange={(v) => patchForm({ include_historic: v })}
              />
            </div>
          </div>

          {zones.length > 0 && (
            <div>
              <p className="text-sm text-cream mb-2">
                Include zones <span className="text-graytown">(none selected = all zones)</span>
              </p>
              <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto">
                {zones.map((code) => {
                  const active = form.include_zone_codes.includes(code);
                  return (
                    <button
                      key={code}
                      type="button"
                      className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                        active
                          ? 'bg-gold text-navy border-gold font-semibold'
                          : 'border-gold/40 text-graytown hover:border-gold'
                      }`}
                      disabled={loading}
                      onClick={() => toggleZone(code)}
                    >
                      {code}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="button"
              className="btn-gold text-sm"
              disabled={loading || !config}
              onClick={handleApply}
            >
              {loading ? 'Regenerating…' : 'Apply & regenerate'}
            </button>
            <button
              type="button"
              className="btn-outline text-sm"
              disabled={loading}
              onClick={onReset}
            >
              Reset to defaults
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
