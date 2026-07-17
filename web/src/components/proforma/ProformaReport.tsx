"use client";

import { Fragment } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Shield,
  Target,
} from "lucide-react";
import type { ProformaPayload } from "@/lib/api";

function fmtMoney(value?: number | null) {
  if (value == null) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

function fmtSqft(value?: number | null) {
  if (value == null) return "—";
  return `${Math.round(value).toLocaleString()} sf`;
}

function fmtPct(value?: number | null) {
  if (value == null) return "—";
  return `${value.toFixed(1)}%`;
}

function stripHtml(text: string) {
  return text.replace(/<[^>]+>/g, "");
}

function SectionTitle({ title }: { title: string }) {
  return (
    <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 print:text-gray-700 border-b border-gray-800 pb-2 print:border-gray-300">
      {title}
    </h4>
  );
}

function KvTable({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-800 print:border-gray-300">
      <table className="w-full text-sm">
        <tbody className="divide-y divide-gray-800 print:divide-gray-200">
          {rows.map((row) => (
            <tr key={row.label} className="bg-gray-950/50 print:bg-white">
              <td className="px-4 py-2.5 font-medium text-gray-300 w-[36%] align-top print:text-gray-700">
                {row.label}
              </td>
              <td className="px-4 py-2.5 text-gray-400 print:text-gray-800">{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function investorVerdictStyles(rating?: string) {
  if (rating === "pursue") {
    return {
      box: "bg-emerald-950/50 border-emerald-600/50 text-emerald-100",
      badge: "bg-emerald-600 text-white",
      icon: <CheckCircle2 className="text-emerald-400 w-6 h-6 shrink-0" />,
    };
  }
  if (rating === "pass") {
    return {
      box: "bg-red-950/50 border-red-700/50 text-red-100",
      badge: "bg-red-600 text-white",
      icon: <XCircle className="text-red-400 w-6 h-6 shrink-0" />,
    };
  }
  return {
    box: "bg-amber-950/50 border-amber-600/50 text-amber-100",
    badge: "bg-amber-600 text-white",
    icon: <AlertTriangle className="text-amber-400 w-6 h-6 shrink-0" />,
  };
}

function roiColor(roi: number) {
  if (roi >= 15) return "text-emerald-400";
  if (roi >= 0) return "text-amber-400";
  return "text-red-400";
}

function sensitivityCellColor(roi: number) {
  if (roi >= 15) return "bg-emerald-500/20 text-emerald-300";
  if (roi >= 5) return "bg-blue-500/15 text-blue-300";
  if (roi >= 0) return "bg-amber-500/15 text-amber-300";
  return "bg-red-500/15 text-red-300";
}

type Props = {
  data: ProformaPayload;
  generatedSeconds?: number | null;
};

export default function ProformaReport({ data, generatedSeconds }: Props) {
  const exhibit = data.investor_exhibit;
  const verdict = data.investor_verdict;
  const vstyles = investorVerdictStyles(verdict?.rating);
  const snap = data.site_snapshot || {};
  const market = data.market || {};
  const exitPricing = data.exit_pricing || market.exit_pricing || {};
  const comps = data.comps;
  const scenarios = data.scenarios || [];
  const primaryName = data.primary_scenario;
  const primary = scenarios.find((s) => s.name === primaryName) || scenarios[0];
  const sensitivity = data.return_sensitivity || data.irr_grid;
  const overlay = data.overlay_economics;

  const zoningStack = [snap.primary_zone || data.primary_zone, snap.primary_overlay || data.primary_overlay]
    .filter(Boolean)
    .join(" + ");

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl print:border-gray-300 print:shadow-none">
      {/* Investor vow moment — one-page exhibit */}
      <div className="p-6 md:p-8 border-b border-gray-800 bg-gradient-to-br from-gray-900 via-gray-900 to-blue-950/30">
        <div className="flex flex-wrap justify-between items-start gap-6 mb-6">
          <div className="min-w-0">
            <p className="text-xs text-blue-400 uppercase tracking-widest mb-2 font-semibold">
              Investor Feasibility Exhibit
            </p>
            <h3 className="text-2xl font-bold text-white print:text-black mb-1">
              {exhibit?.address || snap.address}
            </h3>
            <p className="text-xs text-gray-500">
              {data.prepared_on && <span>Prepared {data.prepared_on}</span>}
              <span className="mx-2">·</span>
              <span className="font-mono">Parcel {data.parcel_id}</span>
              {generatedSeconds != null && (
                <>
                  <span className="mx-2">·</span>
                  <span>{generatedSeconds.toFixed(1)}s</span>
                </>
              )}
            </p>
            {zoningStack && <p className="text-sm text-blue-300/90 mt-2 font-medium">{zoningStack}</p>}
          </div>
          <div className={`flex items-start gap-3 p-4 rounded-xl border max-w-md ${vstyles.box}`}>
            {vstyles.icon}
            <div>
              <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full ${vstyles.badge}`}>
                {verdict?.rating || "screen"}
              </span>
              <p className="text-sm font-semibold mt-2 leading-snug">
                {verdict?.label || exhibit?.investor_verdict_label}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <MetricCard
            label="Equity multiple"
            value={exhibit?.equity_multiple != null ? `${exhibit.equity_multiple.toFixed(2)}×` : "—"}
            accent="emerald"
          />
          <MetricCard
            label="Equity IRR"
            value={fmtPct(exhibit?.equity_irr_pct)}
            accent="blue"
          />
          <MetricCard label="Equity check" value={fmtMoney(exhibit?.equity_required)} accent="purple" />
          <MetricCard
            label="Equity profit"
            value={fmtMoney(exhibit?.equity_profit)}
            accent={(exhibit?.equity_profit ?? 0) >= 0 ? "emerald" : "red"}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="bg-gray-950/60 rounded-lg border border-gray-800 p-3">
            <div className="text-gray-500 text-xs mb-1">Recommended regime</div>
            <div className="text-white font-semibold">{exhibit?.recommended_regime || "—"}</div>
            <div className="text-gray-400 text-xs mt-1">
              {exhibit?.units ?? "—"} units · {fmtSqft(exhibit?.total_gfa)}
            </div>
          </div>
          <div className="bg-gray-950/60 rounded-lg border border-gray-800 p-3">
            <div className="text-gray-500 text-xs mb-1">Exit pricing</div>
            <div className="text-white font-semibold">{fmtMoney(exhibit?.exit_sale_psf)}/sf</div>
            <div className="text-gray-500 text-xs mt-1 line-clamp-2">
              {exhibit?.exit_pricing_method || exitPricing.method}
            </div>
          </div>
          <div className="bg-gray-950/60 rounded-lg border border-gray-800 p-3">
            <div className="text-gray-500 text-xs mb-1">Land basis</div>
            <div className="text-white font-semibold">{fmtMoney(exhibit?.land_basis)}</div>
            <div className="text-gray-500 text-xs mt-1">{exhibit?.land_basis_source}</div>
          </div>
        </div>

        {(exhibit?.investor_thesis || data.executive_summary) && (
          <p className="text-sm text-gray-300 leading-relaxed mt-5 border-t border-gray-800/80 pt-4">
            {exhibit?.investor_thesis || data.executive_summary}
          </p>
        )}

        {overlay && overlay.profit_delta != null && overlay.profit_delta !== 0 && (
          <div className="mt-4 flex items-center gap-2 text-sm text-purple-300 bg-purple-950/30 border border-purple-800/40 rounded-lg px-4 py-2">
            <Target className="h-4 w-4 shrink-0" />
            Overlay election adds {fmtMoney(overlay.profit_delta)} profit vs {overlay.base_scenario}
            {overlay.equity_multiple_delta != null && (
              <span className="text-purple-400/80">
                {" "}
                (+{overlay.equity_multiple_delta.toFixed(2)}× equity)
              </span>
            )}
          </div>
        )}
      </div>

      <div className="p-6 space-y-10">
        <section>
          <SectionTitle title="Exit Pricing & Comparable Sales" />
          <KvTable
            rows={[
              {
                label: "Modeled exit $/sf",
                value: `${fmtMoney(exitPricing.sale_psf_used || market.indicative_sale_psf)}/sf GFA`,
              },
              { label: "Pricing method", value: exitPricing.method || "—" },
              {
                label: "CAMA comp median (resale)",
                value: exitPricing.comp_median_resale_psf
                  ? `${fmtMoney(exitPricing.comp_median_resale_psf)}/sf`
                  : "—",
              },
              {
                label: "Comp-adjusted new construction",
                value: exitPricing.comp_adjusted_new_psf
                  ? `${fmtMoney(exitPricing.comp_adjusted_new_psf)}/sf`
                  : "—",
              },
              {
                label: "Zip MLS trend $/sf",
                value: exitPricing.zip_price_per_sqft
                  ? `${fmtMoney(exitPricing.zip_price_per_sqft)}/sf`
                  : market.price_per_sqft
                    ? `${fmtMoney(market.price_per_sqft)}/sf`
                    : "—",
              },
              {
                label: "Town median sale",
                value: fmtMoney(market.median_sale_price),
              },
              {
                label: "New-construction premium applied",
                value:
                  exitPricing.new_construction_premium_pct != null
                    ? `${Math.round(exitPricing.new_construction_premium_pct * 100)}% over resale comps`
                    : "40% (default)",
              },
            ]}
          />
          {comps?.rows && comps.rows.length > 0 ? (
            <div className="mt-4 overflow-x-auto rounded-lg border border-gray-800">
              <p className="text-xs text-gray-500 px-4 py-2 border-b border-gray-800 bg-gray-950/40">
                {comps.note} · Median {fmtMoney(comps.median_ppsf)}/sf
              </p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-gray-500 bg-gray-950/60">
                    <th className="px-4 py-2">Address</th>
                    <th className="px-4 py-2 text-right">Distance</th>
                    <th className="px-4 py-2 text-right">Sale</th>
                    <th className="px-4 py-2">Date</th>
                    <th className="px-4 py-2 text-right">$/sf</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {comps.rows.map((c) => (
                    <tr key={c.parcel_id || c.address} className="bg-gray-950/30">
                      <td className="px-4 py-2 text-gray-300">{c.address}</td>
                      <td className="px-4 py-2 text-right text-gray-500 tabular-nums">
                        {c.distance_ft != null ? `${Math.round(c.distance_ft).toLocaleString()} ft` : "—"}
                      </td>
                      <td className="px-4 py-2 text-right text-gray-400 tabular-nums">
                        {fmtMoney(c.sale_price)}
                      </td>
                      <td className="px-4 py-2 text-gray-500 text-xs">{c.sale_date}</td>
                      <td className="px-4 py-2 text-right text-emerald-400/90 tabular-nums">
                        {c.price_per_sf != null ? `${fmtMoney(c.price_per_sf)}/sf` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-amber-500/90 mt-3 italic">
              No CAMA comparable sales in radius — exit uses zip trend and town config. Confirm with broker
              comps before IC.
            </p>
          )}
        </section>

        {!!scenarios.length && (
          <section>
            <SectionTitle title="Regime Economics — Base vs Overlay" />
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-xs sm:text-sm min-w-[1000px]">
                <thead>
                  <tr className="bg-gray-800/60 text-left text-xs uppercase tracking-wider text-gray-400">
                    <th className="px-3 py-2.5">Scenario</th>
                    <th className="px-3 py-2.5 text-right">Units</th>
                    <th className="px-3 py-2.5 text-right">GFA</th>
                    <th className="px-3 py-2.5 text-right">Total cost</th>
                    <th className="px-3 py-2.5 text-right">Sale</th>
                    <th className="px-3 py-2.5 text-right">Profit</th>
                    <th className="px-3 py-2.5 text-right">ROI</th>
                    <th className="px-3 py-2.5 text-right">Equity</th>
                    <th className="px-3 py-2.5 text-right">Eq. mult.</th>
                    <th className="px-3 py-2.5 text-right">Eq. IRR</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {scenarios.map((s) => {
                    const isPrimary = s.name === primaryName;
                    const eq = s.equity_returns;
                    return (
                      <Fragment key={s.name}>
                        <tr className={isPrimary ? "bg-blue-950/30" : "bg-gray-950/40"}>
                          <td className="px-3 py-2.5 text-gray-300">
                            {s.name}
                            {isPrimary && (
                              <span className="ml-2 text-[9px] uppercase bg-blue-600 text-white px-1.5 py-0.5 rounded-full">
                                IC path
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-gray-400">{s.units}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-gray-400">
                            {s.total_gfa.toLocaleString()}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-gray-400">
                            {fmtMoney(s.total_cost)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-emerald-400">
                            {fmtMoney(s.sale_price)}
                          </td>
                          <td
                            className={`px-3 py-2.5 text-right tabular-nums ${(s.profit ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}
                          >
                            {fmtMoney(s.profit)}
                          </td>
                          <td className={`px-3 py-2.5 text-right font-medium tabular-nums ${roiColor(s.roi_pct)}`}>
                            {fmtPct(s.roi_pct)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-purple-300">
                            {fmtMoney(eq?.equity_required)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-purple-300 font-semibold">
                            {eq?.equity_multiple != null ? `${eq.equity_multiple.toFixed(2)}×` : "—"}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-purple-300">
                            {fmtPct(eq?.equity_irr_pct)}
                          </td>
                        </tr>
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!!sensitivity?.rows?.length && (
          <section>
            <SectionTitle title={`Return Sensitivity — ${primaryName || "Primary"}`} />
            <p className="text-xs text-gray-500 mb-3">
              Project ROI % under land ±10% and hard ±10% (exit $/sf held constant).
            </p>
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-800/60 text-xs uppercase text-gray-400">
                    <th className="px-4 py-2.5">Hard cost →</th>
                    {(sensitivity.columns || []).map((col) => (
                      <th key={col} className="px-4 py-2.5 text-center">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(sensitivity.rows || []).map((row) => (
                    <tr key={row.label} className="bg-gray-950/40">
                      <td className="px-4 py-2.5 text-gray-300 font-medium">{row.label}</td>
                      {(row.cells || []).map((cell, i) => (
                        <td
                          key={`${row.label}-${i}`}
                          className={`px-4 py-2.5 text-center font-semibold tabular-nums ${sensitivityCellColor(cell)}`}
                        >
                          {cell}%
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!!exhibit?.key_risks?.length && (
          <section>
            <SectionTitle title="Key Risks" />
            <ul className="space-y-2">
              {exhibit.key_risks.map((risk) => (
                <li key={risk} className="flex gap-2 text-sm text-gray-400">
                  <Shield className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                  {risk}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <SectionTitle title="Site Context" />
          <KvTable
            rows={[
              { label: "Owner", value: snap.owner || "—" },
              { label: "Assessed value", value: fmtMoney(snap.assessed_value ?? data.assessed_value) },
              {
                label: "Last sale",
                value:
                  snap.last_sale_price != null
                    ? `${fmtMoney(snap.last_sale_price)}${snap.last_sale_date ? ` (${snap.last_sale_date})` : ""}`
                    : "—",
              },
              { label: "Lot size", value: fmtSqft(snap.lot_sqft_regulatory ?? snap.lot_sqft_gis ?? data.lot_sqft) },
              { label: "Zoning", value: zoningStack || "—" },
            ]}
          />
        </section>

        {!!data.assumptions?.length && (
          <section>
            <SectionTitle title="Assumptions & Sources" />
            <ul className="space-y-2 text-sm text-gray-400">
              {data.assumptions.map((a, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-gray-600">·</span>
                  <span dangerouslySetInnerHTML={{ __html: stripHtml(a) }} />
                </li>
              ))}
            </ul>
            {!!data.data_sources?.length && (
              <p className="text-xs text-gray-600 mt-4">Sources: {data.data_sources.join(", ")}</p>
            )}
          </section>
        )}

        <p className="text-xs text-gray-600 border-t border-gray-800 pt-4 leading-relaxed">
          Indicative investor screening — not an appraisal, securities offering, or lending commitment.
          Confirm exit pricing with broker/appraiser comps, land with purchase contract, and costs with GC
          bids before investment committee or capital deployment. Zoning math in Buildability Brief.
        </p>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: "emerald" | "blue" | "purple" | "red";
}) {
  const ring = {
    emerald: "border-emerald-500/30 bg-emerald-500/5",
    blue: "border-blue-500/30 bg-blue-500/5",
    purple: "border-purple-500/30 bg-purple-500/5",
    red: "border-red-500/30 bg-red-500/5",
  }[accent];
  const text = {
    emerald: "text-emerald-400",
    blue: "text-blue-400",
    purple: "text-purple-400",
    red: "text-red-400",
  }[accent];
  return (
    <div className={`rounded-xl border p-4 ${ring}`}>
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${text}`}>{value}</div>
    </div>
  );
}

export function proformaToCsv(data: ProformaPayload): string {
  const lines: string[] = [];
  const exhibit = data.investor_exhibit;
  const snap = data.site_snapshot || {};

  lines.push("--- INVESTOR EXHIBIT ---");
  lines.push(`Verdict,${exhibit?.investor_verdict || ""}`);
  lines.push(`Equity Multiple,${exhibit?.equity_multiple ?? ""}`);
  lines.push(`Equity IRR,${exhibit?.equity_irr_pct ?? ""}`);
  lines.push(`Equity Required,${exhibit?.equity_required ?? ""}`);
  lines.push(`Exit $/sf,${exhibit?.exit_sale_psf ?? ""}`);
  lines.push("");

  lines.push("--- SITE ---");
  lines.push(`Address,${snap.address || ""}`);
  lines.push(`Parcel ID,${data.parcel_id}`);
  lines.push("");

  lines.push("--- SCENARIOS ---");
  const scenarios = data.scenarios || [];
  if (scenarios.length) {
    lines.push(
      "Scenario,Units,GFA,Total Cost,Sale,Profit,ROI %,Equity Required,Equity Multiple,Equity IRR %",
    );
    for (const s of scenarios) {
      const eq = s.equity_returns || {};
      lines.push(
        [
          s.name,
          s.units,
          s.total_gfa,
          s.total_cost,
          s.sale_price,
          s.profit,
          s.roi_pct,
          eq.equity_required ?? "",
          eq.equity_multiple ?? "",
          eq.equity_irr_pct ?? "",
        ].join(","),
      );
    }
  }
  lines.push("");

  lines.push("--- ASSUMPTIONS ---");
  for (const a of data.assumptions || []) {
    lines.push(stripHtml(a));
  }

  return lines.join("\n");
}
