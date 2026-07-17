"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import { fetchClosingRiskRadarConfig } from "@/lib/api";
import RangeField from "@/components/forms/RangeField";

const SORT_LABELS: Record<string, string> = {
  risk_score: "Risk score",
  open_permit_count: "Open permits",
  assessed_value: "Assessed value",
  tenure: "Owner tenure",
};

function formField(value: unknown, fallback: string | number = ""): string | number {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") return value;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function formFromCriteria(criteria: Record<string, unknown> | null | undefined) {
  const c = criteria || {};
  return {
    preset: String(c.preset || ""),
    min_risk_signals: formField(c.min_risk_signals, 1),
    min_open_permit_count: formField(c.min_open_permit_count),
    include_open_permit: c.include_open_permit !== false,
    include_expired_permit: c.include_expired_permit !== false,
    include_flood_effective: c.include_flood_effective !== false,
    include_flood_preliminary: Boolean(c.include_flood_preliminary),
    require_flood_sfha_only: Boolean(c.require_flood_sfha_only),
    include_wetland: c.include_wetland !== false,
    include_historic: c.include_historic !== false,
    min_assessed_value: formField(c.min_assessed_value),
    max_assessed_value: formField(c.max_assessed_value),
    include_zone_codes: [...((c.include_zone_codes as string[]) || [])],
    top_n: formField(c.top_n),
    sort_by: String(c.sort_by || "risk_score"),
  };
}

function numOrNull(value: unknown) {
  if (value === "" || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function buildClosingRiskCriteriaPayload(form: ReturnType<typeof formFromCriteria>) {
  const payload: Record<string, unknown> = {};
  if (form.preset) payload.preset = form.preset;

  for (const key of [
    "min_risk_signals",
    "min_open_permit_count",
    "min_assessed_value",
    "max_assessed_value",
    "top_n",
  ] as const) {
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

  if (form.include_zone_codes.length) {
    payload.include_zone_codes = form.include_zone_codes;
  }
  if (form.sort_by) payload.sort_by = form.sort_by;
  return payload;
}

type Props = {
  townSlug: string;
  appliedCriteria: Record<string, unknown> | null;
  loading: boolean;
  /** When true, panel fills parent height and scrolls internally. */
  fillHeight?: boolean;
  onOpenChange?: (open: boolean) => void;
  onApply: (criteria: Record<string, unknown>) => void;
  onReset: () => void;
};

export default function ClosingRiskCriteriaPanel({
  townSlug,
  appliedCriteria,
  loading,
  fillHeight = false,
  onOpenChange,
  onApply,
  onReset,
}: Props) {
  const [open, setOpen] = useState(true);

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    onOpenChange?.(next);
  }
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [configError, setConfigError] = useState("");
  const [form, setForm] = useState(() => formFromCriteria(null));

  useEffect(() => {
    setConfigError("");
    fetchClosingRiskRadarConfig(townSlug)
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
  const sortOptions = (config?.sort_options as string[]) || ["risk_score"];

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

  return (
    <div
      className={`bg-gray-900/95 flex flex-col min-h-0 ${
        fillHeight ? "h-full" : "border-b border-gray-800 shrink-0"
      }`}
    >
      <button
        type="button"
        onClick={toggleOpen}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-gray-800/50 transition-colors shrink-0"
      >
        <div className="min-w-0">
          <span className="text-sm font-semibold text-white block">Parameters</span>
          {matchSummary && (
            <span className="text-xs text-gray-500 truncate block">{matchSummary}</span>
          )}
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-gray-400 shrink-0" /> : <ChevronDown className="h-4 w-4 text-gray-400 shrink-0" />}
      </button>

      {configError && (
        <p className="px-3 pb-2 text-xs text-red-400 shrink-0">Could not load config: {configError}</p>
      )}

      {open && (
        <div
          className={`px-3 pb-3 space-y-3 border-t border-gray-800/80 overflow-y-auto overscroll-contain ${
            fillHeight ? "flex-1 min-h-0" : "max-h-[40vh]"
          }`}
        >
          {presets.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-3">
              {presets.map((name) => (
                <button
                  key={name}
                  type="button"
                  disabled={loading}
                  className={`text-xs px-3 py-1.5 rounded-lg border capitalize ${
                    form.preset === name || appliedCriteria?.preset === name
                      ? "border-red-500/60 bg-red-500/10 text-red-200"
                      : "border-gray-700 text-gray-300 hover:border-red-500/40 hover:text-white"
                  }`}
                  onClick={() => applyPreset(name)}
                >
                  {name.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 gap-2.5 pt-2">
            <RangeField
              label="Min risk signals"
              hint="How many flag types must match"
              value={form.min_risk_signals}
              min={lim("min_risk_signals", [1, 8])[0]}
              max={lim("min_risk_signals", [1, 8])[1]}
              onChange={(v) => patchForm({ min_risk_signals: Number(v) || 1 })}
            />
            <RangeField
              label="Min open permits"
              value={form.min_open_permit_count}
              min={lim("min_open_permit_count", [0, 10])[0]}
              max={lim("min_open_permit_count", [0, 10])[1]}
              onChange={(v) => patchForm({ min_open_permit_count: v })}
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

          <div>
            <p className="text-xs text-gray-400 mb-2">Risk signal types</p>
            <div className="grid grid-cols-1 gap-2">
              {[
                ["include_open_permit", "Open building permits"],
                ["include_expired_permit", "Expired permits"],
                ["include_flood_effective", "FEMA flood (effective)"],
                ["include_flood_preliminary", "FEMA flood (preliminary)"],
                ["require_flood_sfha_only", "SFHA only for flood flag"],
                ["include_wetland", "Wetland overlay"],
                ["include_historic", "Historic resource / district"],
              ].map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-xs text-gray-300">
                  <input
                    type="checkbox"
                    checked={Boolean(form[key as keyof typeof form])}
                    onChange={(e) => patchForm({ [key]: e.target.checked } as Partial<ReturnType<typeof formFromCriteria>>)}
                  />
                  {label}
                </label>
              ))}
            </div>
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
                          ? "bg-red-600 border-red-500 text-white"
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

        </div>
      )}

      {open && (
        <div className="flex gap-2 px-3 py-2 border-t border-gray-800 shrink-0 bg-gray-900">
          <button
            type="button"
            disabled={loading || !config}
            onClick={() => onApply(buildClosingRiskCriteriaPayload(form))}
            className="flex-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-medium py-2 rounded-lg"
          >
            {loading ? "Scanning…" : "Apply"}
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={loading}
            className="px-2.5 py-2 border border-gray-700 rounded-lg text-gray-400 hover:text-white"
            title="Reset filters"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
