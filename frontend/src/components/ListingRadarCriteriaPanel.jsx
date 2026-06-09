import { useEffect, useMemo, useState } from 'react';
import { fetchListingRadarConfig } from '../api';

const SORT_LABELS = {
  score: 'Score',
  tenure: 'Owner tenure',
  assessed_value: 'Assessed value',
  utilization: 'Utilization',
};

function formFromCriteria(criteria) {
  const c = criteria || {};
  return {
    preset: c.preset || '',
    min_owner_tenure_years: c.min_owner_tenure_years ?? '',
    max_owner_tenure_years: c.max_owner_tenure_years ?? '',
    min_utilization_pct: c.min_utilization_pct ?? '',
    max_utilization_pct: c.max_utilization_pct ?? '',
    min_existing_gfa_sqft: c.min_existing_gfa_sqft ?? '',
    min_assessed_value: c.min_assessed_value ?? '',
    max_assessed_value: c.max_assessed_value ?? '',
    min_lot_sqft: c.min_lot_sqft ?? '',
    max_lot_sqft: c.max_lot_sqft ?? '',
    include_zone_codes: [...(c.include_zone_codes || [])],
    require_no_open_permit: c.require_no_open_permit !== false,
    top_n: c.top_n ?? '',
    sort_by: c.sort_by || 'score',
  };
}

function numOrNull(value) {
  if (value === '' || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function buildListingRadarCriteriaPayload(form) {
  const payload = {};
  if (form.preset) payload.preset = form.preset;

  const numericFields = [
    'min_owner_tenure_years',
    'max_owner_tenure_years',
    'min_utilization_pct',
    'max_utilization_pct',
    'min_existing_gfa_sqft',
    'min_assessed_value',
    'max_assessed_value',
    'min_lot_sqft',
    'max_lot_sqft',
    'top_n',
  ];

  for (const key of numericFields) {
    const val = numOrNull(form[key]);
    if (val !== null) payload[key] = val;
  }

  if (form.include_zone_codes?.length) {
    payload.include_zone_codes = form.include_zone_codes;
  }

  payload.require_no_open_permit = Boolean(form.require_no_open_permit);

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

export default function ListingRadarCriteriaPanel({
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
    fetchListingRadarConfig(townSlug)
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
  const sortOptions = config?.sort_options || ['score'];

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
    onApply(buildListingRadarCriteriaPayload(form));
  }

  return (
    <section className="card mt-6">
      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <div>
          <h2 className="font-display text-lg text-gold">Listing criteria</h2>
          <p className="text-sm text-graytown mt-1">
            Adjust filters for town-wide listing opportunity ranking.
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
                    {name.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <NumberField
              label="Min owner tenure (years)"
              value={form.min_owner_tenure_years}
              min={limits.min_owner_tenure_years?.[0]}
              max={limits.min_owner_tenure_years?.[1]}
              onChange={(v) => patchForm({ min_owner_tenure_years: v })}
            />
            <NumberField
              label="Max owner tenure (years)"
              value={form.max_owner_tenure_years}
              min={limits.max_owner_tenure_years?.[0]}
              max={limits.max_owner_tenure_years?.[1]}
              onChange={(v) => patchForm({ max_owner_tenure_years: v })}
            />
            <NumberField
              label="Min utilization (%)"
              hint="Listing story — not fully built out"
              value={form.min_utilization_pct}
              min={0}
              max={100}
              onChange={(v) => patchForm({ min_utilization_pct: v })}
            />
            <NumberField
              label="Max utilization (%)"
              value={form.max_utilization_pct}
              min={0}
              max={100}
              onChange={(v) => patchForm({ max_utilization_pct: v })}
            />
            <NumberField
              label="Min existing GFA (sq ft)"
              value={form.min_existing_gfa_sqft}
              min={limits.min_existing_gfa_sqft?.[0]}
              max={limits.min_existing_gfa_sqft?.[1]}
              onChange={(v) => patchForm({ min_existing_gfa_sqft: v })}
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
              min={limits.min_assessed_value?.[0]}
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

          <label className="flex items-center gap-2 text-sm text-cream cursor-pointer">
            <input
              type="checkbox"
              className="rounded border-gold/40"
              checked={form.require_no_open_permit}
              onChange={(e) => patchForm({ require_no_open_permit: e.target.checked })}
            />
            Require no open building permit
          </label>

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
