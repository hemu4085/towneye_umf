"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import { fetchDealRadarConfig } from "@/lib/api";
import RangeField from "@/components/forms/RangeField";

const SORT_LABELS: Record<string, string> = {
  score: "Score",
  expansion: "Expansion room",
  assessed_value: "Assessed value",
  tenure: "Owner tenure",
};

function formFromCriteria(criteria: Record<string, unknown> | null | undefined) {
  const c = criteria || {};
  return {
    preset: String(c.preset || ""),
    min_owner_tenure_years: c.min_owner_tenure_years ?? "",
    max_utilization_pct: c.max_utilization_pct ?? "",
    min_expansion_room_sqft: c.min_expansion_room_sqft ?? "",
    min_existing_gfa_sqft: c.min_existing_gfa_sqft ?? "",
    max_existing_gfa_sqft: c.max_existing_gfa_sqft ?? "",
    min_max_gfa_sqft: c.min_max_gfa_sqft ?? "",
    max_max_gfa_sqft: c.max_max_gfa_sqft ?? "",
    min_assessed_value: c.min_assessed_value ?? "",
    max_assessed_value: c.max_assessed_value ?? "",
    min_lot_sqft: c.min_lot_sqft ?? "",
    max_lot_sqft: c.max_lot_sqft ?? "",
    include_zone_codes: [...((c.include_zone_codes as string[]) || [])],
    require_no_open_permit: c.require_no_open_permit !== false,
    top_n: c.top_n ?? "",
    sort_by: String(c.sort_by || "score"),
  };
}

function numOrNull(value: unknown) {
  if (value === "" || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function buildCriteriaPayload(form: ReturnType<typeof formFromCriteria>) {
  const payload: Record<string, unknown> = {};
  if (form.preset) payload.preset = form.preset;

  for (const key of [
    "min_owner_tenure_years",
    "max_utilization_pct",
    "min_expansion_room_sqft",
    "min_existing_gfa_sqft",
    "max_existing_gfa_sqft",
    "min_max_gfa_sqft",
    "max_max_gfa_sqft",
    "min_assessed_value",
    "max_assessed_value",
    "min_lot_sqft",
    "max_lot_sqft",
    "top_n",
  ] as const) {
    const val = numOrNull(form[key]);
    if (val !== null) payload[key] = val;
  }

  if (form.include_zone_codes.length) {
    payload.include_zone_codes = form.include_zone_codes;
  }
  payload.require_no_open_permit = Boolean(form.require_no_open_permit);
  if (form.sort_by) payload.sort_by = form.sort_by;
  return payload;
}

type Props = {
  townSlug: string;
  appliedCriteria: Record<string, unknown> | null;
  loading: boolean;
  onApply: (criteria: Record<string, unknown>) => void;
  onReset: () => void;
  layout?: "sidebar" | "sheet";
};

export default function DealRadarCriteriaPanel({
  townSlug,
  appliedCriteria,
  loading,
  onApply,
  onReset,
  layout = "sidebar",
}: Props) {
  const isSheet = layout === "sheet";
  const [open, setOpen] = useState(isSheet ? true : false);
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [configError, setConfigError] = useState("");
  const [form, setForm] = useState(() => formFromCriteria(null));

  useEffect(() => {
    setConfigError("");
    fetchDealRadarConfig(townSlug)
      .then((data) => setConfig(data as Record<string, unknown>))
      .catch((err) => setConfigError(err instanceof Error ? err.message : "Config failed"));
  }, [townSlug]);

  useEffect(() => {
    const source = appliedCriteria || (config?.defaults as Record<string, unknown>) || null;
    if (source) setForm(formFromCriteria(source));
  }, [appliedCriteria, config?.defaults]);

  const limits = (config?.limits || {}) as Record<string, [number, number]>;
  const zones = (config?.zones as string[]) || [];
  const presets = (config?.presets as string[]) || [];
  const sortOptions = (config?.sort_options as string[]) || ["score"];

  const matchSummary = useMemo(() => {
    if (!appliedCriteria) return null;
    return appliedCriteria.preset
      ? `Preset: ${appliedCriteria.preset}`
      : "Custom criteria applied";
  }, [appliedCriteria]);

  function patchForm(updates: Partial<ReturnType<typeof formFromCriteria>>) {
    setForm((prev) => ({ ...prev, ...updates, preset: "" }));
  }

  function toggleZone(code: string) {
    setForm((prev) => {
      const set = new Set(prev.include_zone_codes);
      if (set.has(code)) set.delete(code);
      else set.add(code);
      return { ...prev, include_zone_codes: [...set].sort(), preset: "" };
    });
  }

  function applyPreset(name: string) {
    setForm((prev) => ({ ...prev, preset: name }));
    onApply({ preset: name });
  }

  const lim = (key: string, fallback: [number, number]) =>
    limits[key] || fallback;

  const formBody = (
    <div className={`space-y-4 ${isSheet ? "px-4 py-4" : "px-4 pb-4 border-t border-gray-800/80 max-h-[55vh] overflow-y-auto"}`}>
          {presets.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-3">
              {presets.map((name) => (
                <button
                  key={name}
                  type="button"
                  disabled={loading}
                  className={`text-xs px-3 py-1.5 rounded-lg border capitalize ${
                    form.preset === name || appliedCriteria?.preset === name
                      ? "border-amber-500/60 bg-amber-500/10 text-amber-200"
                      : "border-gray-700 text-gray-300 hover:border-blue-500/50 hover:text-white"
                  }`}
                  onClick={() => applyPreset(name)}
                >
                  {name.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <RangeField
              label="Min owner tenure (years)"
              value={form.min_owner_tenure_years}
              min={lim("min_owner_tenure_years", [0, 50])[0]}
              max={lim("min_owner_tenure_years", [0, 50])[1]}
              onChange={(v) => patchForm({ min_owner_tenure_years: v })}
            />
            <RangeField
              label="Max utilization (%)"
              hint="Existing GFA vs indicative max GFA"
              value={form.max_utilization_pct}
              min={0}
              max={100}
              onChange={(v) => patchForm({ max_utilization_pct: v })}
            />
            <RangeField
              label="Min expansion room (sq ft)"
              value={form.min_expansion_room_sqft}
              min={lim("min_expansion_room_sqft", [0, 50000])[0]}
              max={lim("min_expansion_room_sqft", [0, 50000])[1]}
              step={100}
              onChange={(v) => patchForm({ min_expansion_room_sqft: v })}
            />
            <RangeField
              label="Min existing GFA (sq ft)"
              value={form.min_existing_gfa_sqft}
              min={lim("min_existing_gfa_sqft", [0, 20000])[0]}
              max={lim("min_existing_gfa_sqft", [0, 20000])[1]}
              step={100}
              onChange={(v) => patchForm({ min_existing_gfa_sqft: v })}
            />
            <RangeField
              label="Max existing GFA (sq ft)"
              value={form.max_existing_gfa_sqft}
              min={lim("max_existing_gfa_sqft", [0, 20000])[0]}
              max={lim("max_existing_gfa_sqft", [0, 20000])[1]}
              step={100}
              onChange={(v) => patchForm({ max_existing_gfa_sqft: v })}
            />
            <RangeField
              label="Min indicative max GFA (sq ft)"
              value={form.min_max_gfa_sqft}
              min={lim("min_max_gfa_sqft", [0, 50000])[0]}
              max={lim("min_max_gfa_sqft", [0, 50000])[1]}
              step={100}
              onChange={(v) => patchForm({ min_max_gfa_sqft: v })}
            />
            <RangeField
              label="Max indicative max GFA (sq ft)"
              value={form.max_max_gfa_sqft}
              min={lim("max_max_gfa_sqft", [0, 50000])[0]}
              max={lim("max_max_gfa_sqft", [0, 50000])[1]}
              step={100}
              onChange={(v) => patchForm({ max_max_gfa_sqft: v })}
            />
            <RangeField
              label="Min assessed value ($)"
              value={form.min_assessed_value}
              min={lim("min_assessed_value", [0, 5000000])[0]}
              max={lim("min_assessed_value", [0, 5000000])[1]}
              step={10000}
              onChange={(v) => patchForm({ min_assessed_value: v })}
            />
            <RangeField
              label="Max assessed value ($)"
              value={form.max_assessed_value}
              min={lim("max_assessed_value", [0, 5000000])[0]}
              max={lim("max_assessed_value", [0, 5000000])[1]}
              step={10000}
              onChange={(v) => patchForm({ max_assessed_value: v })}
            />
            <RangeField
              label="Min lot size (sq ft)"
              value={form.min_lot_sqft}
              min={lim("min_lot_sqft", [0, 50000])[0]}
              max={lim("min_lot_sqft", [0, 50000])[1]}
              step={100}
              onChange={(v) => patchForm({ min_lot_sqft: v })}
            />
            <RangeField
              label="Max lot size (sq ft)"
              value={form.max_lot_sqft}
              min={lim("max_lot_sqft", [0, 50000])[0]}
              max={lim("max_lot_sqft", [0, 50000])[1]}
              step={100}
              onChange={(v) => patchForm({ max_lot_sqft: v })}
            />
            <RangeField
              label="Top results"
              value={form.top_n}
              min={lim("top_n", [5, 200])[0]}
              max={lim("top_n", [5, 200])[1]}
              onChange={(v) => patchForm({ top_n: v })}
            />
            <label className="text-xs text-gray-400 block">
              Sort by
              <select
                className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white"
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
              <p className="text-xs text-gray-400 mb-2">
                Include zones <span className="text-gray-600">(none = all)</span>
              </p>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                {zones.map((code) => {
                  const active = form.include_zone_codes.includes(code);
                  return (
                    <button
                      key={code}
                      type="button"
                      disabled={loading}
                      onClick={() => toggleZone(code)}
                      className={`text-xs px-2 py-0.5 rounded-full border ${
                        active
                          ? "bg-blue-600 border-blue-500 text-white"
                          : "border-gray-700 text-gray-400 hover:border-gray-500"
                      }`}
                    >
                      {code}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-xs text-gray-300">
            <input
              type="checkbox"
              checked={form.require_no_open_permit}
              onChange={(e) => patchForm({ require_no_open_permit: e.target.checked })}
            />
            Require no open building permit
          </label>

          <div className={`flex gap-2 pt-1 ${isSheet ? "sticky bottom-0 bg-gray-950 pb-4 pt-3 border-t border-gray-800" : "sticky bottom-0 bg-gray-900/95 pb-1"}`}>
            <button
              type="button"
              disabled={loading || !config}
              onClick={() => onApply(buildCriteriaPayload(form))}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold py-3 rounded-xl"
            >
              {loading ? "Scanning…" : "Show results"}
            </button>
            <button
              type="button"
              onClick={onReset}
              disabled={loading}
              className="px-4 py-3 border border-gray-700 rounded-xl text-gray-400 hover:text-white"
              title="Reset filters"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
          </div>
    </div>
  );

  if (isSheet) {
    return (
      <>
        {configError && (
          <p className="px-4 pt-2 text-xs text-red-400">Could not load config: {configError}</p>
        )}
        {formBody}
      </>
    );
  }

  return (
    <div className="border-b border-gray-800 bg-gray-900/95 shrink-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-800/50 transition-colors"
      >
        <div>
          <span className="text-sm font-semibold text-white block">Screening criteria</span>
          {matchSummary && (
            <span className="text-xs text-gray-500">{matchSummary}</span>
          )}
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
      </button>

      {configError && (
        <p className="px-4 pb-2 text-xs text-red-400">Could not load config: {configError}</p>
      )}

      {open && formBody}
    </div>
  );
}
