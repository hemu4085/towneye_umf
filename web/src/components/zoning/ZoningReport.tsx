"use client";

import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Sparkles,
  ShieldAlert,
  Info,
} from "lucide-react";
import type { ZoningPayload, ZoningRegulatorySignal } from "@/lib/api";

function fmtSqft(value?: number | null) {
  if (value == null) return "—";
  return `${Math.round(value).toLocaleString()} sf`;
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

function ComparisonCell({ val }: { val: string }) {
  if (val === "qualifies") return <span className="text-green-400">✓ qualifies</span>;
  if (val === "non-conforming") return <span className="text-red-400">⚠ non-conforming</span>;
  if (val === "not specified") return <span className="text-amber-400">⚠ not specified</span>;
  return <>{val}</>;
}

function verdictStyles(verdictClass?: string) {
  if (verdictClass === "v-green") {
    return {
      box: "bg-green-950/40 border-green-700/50 text-green-200",
      icon: <CheckCircle2 className="text-green-500 w-5 h-5 shrink-0" />,
    };
  }
  if (verdictClass === "v-red") {
    return {
      box: "bg-red-950/40 border-red-700/50 text-red-200",
      icon: <XCircle className="text-red-500 w-5 h-5 shrink-0" />,
    };
  }
  return {
    box: "bg-amber-950/40 border-amber-700/50 text-amber-200",
    icon: <AlertTriangle className="text-amber-500 w-5 h-5 shrink-0" />,
  };
}

function SignalIcon({ severity }: { severity: string }) {
  if (severity === "opportunity") return <Sparkles className="h-4 w-4 text-purple-400 shrink-0 mt-0.5" />;
  if (severity === "warning") return <ShieldAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />;
  return <Info className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />;
}

function RegulatorySignalRow({ sig }: { sig: ZoningRegulatorySignal }) {
  const border =
    sig.severity === "opportunity"
      ? "border-purple-500/30 bg-purple-500/5"
      : sig.severity === "warning"
        ? "border-amber-500/30 bg-amber-500/5"
        : "border-gray-700 bg-gray-950/40";
  return (
    <div className={`flex gap-3 p-3 rounded-lg border ${border}`}>
      <SignalIcon severity={sig.severity} />
      <div>
        <div className="text-xs font-medium text-gray-300 mb-0.5">{sig.signal}</div>
        <p className="text-sm text-gray-400 leading-relaxed">{sig.detail}</p>
      </div>
    </div>
  );
}

type Props = {
  data: ZoningPayload;
  generatedSeconds?: number | null;
};

export default function ZoningReport({ data, generatedSeconds }: Props) {
  const verdict = verdictStyles(data.headline_verdict_class);
  const district =
    data.zoning_district ||
    [data.primary_zone_code, data.primary_overlay_code].filter(Boolean).join(" + ") ||
    "—";

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl print:border-gray-300 print:shadow-none">
      <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex flex-wrap justify-between items-start gap-4">
        <div className="min-w-0">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Zoning Intelligence Report
          </p>
          <h3 className="text-xl font-bold text-white print:text-black mb-2">{data.address}</h3>
          <p className="text-xs text-gray-500">
            {data.report_date && <span>Prepared on {data.report_date}</span>}
            <span className="mx-2">·</span>
            <span className="font-mono">Parcel {data.parcel_id}</span>
            {generatedSeconds != null && (
              <>
                <span className="mx-2">·</span>
                <span>Generated in {generatedSeconds.toFixed(1)}s</span>
              </>
            )}
          </p>
          {(data.lot_size_sqft || data.existing_gfa_sqft || data.assessor_use_code) && (
            <p className="text-xs text-gray-600 mt-2">
              {data.lot_size_sqft != null && <span>Lot {fmtSqft(data.lot_size_sqft)}</span>}
              {data.existing_gfa_sqft != null && (
                <span className="mx-2">· Existing GFA {fmtSqft(data.existing_gfa_sqft)}</span>
              )}
              {data.assessor_use_code && (
                <span className="mx-2">· Use {data.assessor_use_code}</span>
              )}
            </p>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm text-gray-400 print:text-gray-600 mb-1">
            Zoning capacity score
          </div>
          <div className="text-3xl font-bold text-purple-400 print:text-purple-700">
            {data.zoning_opportunity_score ?? "—"}
            <span className="text-lg text-gray-500">/10</span>
          </div>
          <div className="text-sm font-medium text-blue-400 mt-2 print:text-blue-700">{district}</div>
          {data.has_mbta_communities_overlay && (
            <div className="text-xs text-purple-400 mt-1 border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 rounded inline-block">
              MBTA §3A / NMF overlay
            </div>
          )}
        </div>
      </div>

      <div className="p-6 space-y-10">
        {data.headline_verdict_text && (
          <section>
            <div className={`flex gap-3 p-4 rounded-xl border ${verdict.box}`}>
              {verdict.icon}
              <p className="text-sm leading-relaxed">{data.headline_verdict_text}</p>
            </div>
          </section>
        )}

        {data.overlay_election && (
          <section>
            <SectionTitle title="Overlay election (base vs overlay — do not stack)" />
            <div className="p-4 rounded-xl border border-purple-500/30 bg-purple-950/20 space-y-3">
              <p className="text-sm text-gray-300">
                <span className="font-medium text-purple-300">Recommended regime for memo:</span>{" "}
                {data.overlay_election.recommended_regime}
                {data.overlay_election.alternative_regime && (
                  <span className="text-gray-500">
                    {" "}
                    (alternative: {data.overlay_election.alternative_regime} base)
                  </span>
                )}
              </p>
              {(data.overlay_election.does_not_stack || data.overlay_election.election_type) && (
                <p className="text-sm text-amber-200/90 leading-relaxed border border-amber-500/20 bg-amber-950/20 rounded-lg px-3 py-2">
                  {data.overlay_election.election_type ||
                    "Project-by-project election — base and overlay regimes do not stack."}
                </p>
              )}
              <p className="text-sm text-gray-400 leading-relaxed">
                {data.overlay_election.rationale}
              </p>
              {data.overlay_election.legal_basis && (
                <p className="text-xs text-gray-500 font-mono leading-relaxed">
                  Citation: {data.overlay_election.legal_basis}
                </p>
              )}
              {data.overlay_election.memo_text && (
                <p className="text-xs text-gray-500 leading-relaxed border-t border-gray-800 pt-3 italic print:text-gray-600">
                  {data.overlay_election.memo_text}
                </p>
              )}
            </div>
          </section>
        )}

        {!!data.regulatory_signals?.length && (
          <section>
            <SectionTitle title="Regulatory signals" />
            <p className="text-xs text-gray-500 mb-3">
              Parcel-specific zoning friction and upside — not available from generic zone lookup tools.
            </p>
            <div className="space-y-2">
              {data.regulatory_signals.map((sig) => (
                <RegulatorySignalRow key={sig.signal} sig={sig} />
              ))}
            </div>
          </section>
        )}

        {!!data.zoning_insights?.length && (
          <section>
            <SectionTitle title="Key insights" />
            <ul className="space-y-2 text-sm text-gray-300 list-disc list-inside print:text-gray-800">
              {data.zoning_insights.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )}

        {data.overlay_narrative && (
          <section>
            <SectionTitle title="Overlay context" />
            <p className="text-sm text-gray-300 leading-relaxed print:text-gray-800">
              {data.overlay_narrative}
            </p>
          </section>
        )}

        <section>
          <SectionTitle title="Zoning stack (GIS-resolved)" />
          {!!data.base_zones?.length &&
            data.base_zones.map((z) => (
              <div key={z.code} className="mb-4">
                <h5 className="text-xs font-semibold text-gray-500 mb-2">Base — {z.code}</h5>
                <KvTable
                  rows={[
                    {
                      label: "District",
                      value: z.gis?.district_name
                        ? `${z.code} — ${z.gis.district_name}`
                        : z.rule?.description
                          ? `${z.code} — ${z.rule.description}`
                          : z.code || "—",
                    },
                    { label: "GIS layer", value: `${z.layer || "—"} · point-in-polygon at centroid` },
                    ...(z.gis?.adoption_reference
                      ? [{ label: "Adoption / amendment", value: z.gis.adoption_reference }]
                      : []),
                    ...(z.gis?.gis_notes ? [{ label: "GIS notes", value: z.gis.gis_notes }] : []),
                  ]}
                />
              </div>
            ))}
          {!!data.overlay_zones?.length ? (
            data.overlay_zones.map((z) => (
              <div key={z.code || z.label} className="mb-4">
                <h5 className="text-xs font-semibold text-gray-500 mb-2">Overlay — {z.code}</h5>
                <KvTable
                  rows={[
                    {
                      label: "Overlay district",
                      value: z.gis?.district_name || z.label || z.code || "—",
                    },
                    { label: "GIS layer", value: `${z.layer || "—"} · point-in-polygon at centroid` },
                    ...(z.gis?.adoption_reference
                      ? [{ label: "Town Meeting / adoption", value: z.gis.adoption_reference }]
                      : []),
                    ...(z.gis?.gis_notes ? [{ label: "Adoption history", value: z.gis.gis_notes }] : []),
                    ...(z.rule?.notes ? [{ label: "Bylaw note", value: z.rule.notes }] : []),
                  ]}
                />
              </div>
            ))
          ) : (
            <p className="text-xs text-gray-500">No overlay districts intersect this parcel.</p>
          )}
        </section>

        {!!data.envelopes?.length && (
          <section>
            <SectionTitle title="Buildable envelope by regime" />
            <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300">
              <table className="w-full text-sm text-left min-w-[640px]">
                <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                  <tr>
                    <th className="px-3 py-2 font-medium">Regime</th>
                    <th className="px-3 py-2 font-medium">Max GFA</th>
                    <th className="px-3 py-2 font-medium">Existing</th>
                    <th className="px-3 py-2 font-medium">Expansion</th>
                    <th className="px-3 py-2 font-medium">Lot qualifies?</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 bg-gray-900 print:divide-gray-200 print:bg-white">
                  {data.envelopes.map((env) => (
                    <tr key={env.zone_code || env.label}>
                      <td className="px-3 py-2 font-medium text-gray-300 print:text-gray-700">
                        {env.label}
                        {env.is_overlay && (
                          <span className="ml-1 text-xs text-purple-400">overlay</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-gray-400">
                        {env.max_gfa_sqft != null ? fmtSqft(env.max_gfa_sqft) : "—"}
                      </td>
                      <td className="px-3 py-2 text-gray-400">
                        {env.existing_gfa_sqft != null ? fmtSqft(env.existing_gfa_sqft) : "—"}
                      </td>
                      <td className="px-3 py-2 text-gray-400">
                        {env.expansion_room_sqft != null && env.expansion_room_sqft > 0
                          ? `+${fmtSqft(env.expansion_room_sqft)}`
                          : "—"}
                      </td>
                      <td className="px-3 py-2">
                        {env.qualifies === true && (
                          <span className="text-green-400 text-xs">✓ qualifies</span>
                        )}
                        {env.qualifies === false && (
                          <span className="text-red-400 text-xs">⚠ non-conforming</span>
                        )}
                        {env.qualifies == null && <span className="text-gray-500 text-xs">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.envelopes.map((env) => (
              <p key={`r-${env.label}`} className="text-xs text-gray-600 mt-2 font-mono">
                {env.label}: {env.rationale}
              </p>
            ))}
          </section>
        )}

        {!!data.development_paths?.length && (
          <section>
            <SectionTitle title="Development paths (zoning-filtered)" />
            <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300">
              <table className="w-full text-sm min-w-[720px]">
                <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Option</th>
                    <th className="px-3 py-2 text-left font-medium">Legal path</th>
                    <th className="px-3 py-2 text-left font-medium">Process</th>
                    <th className="px-3 py-2 text-left font-medium">Indicative scale</th>
                    <th className="px-3 py-2 text-left font-medium">Timeline</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 print:divide-gray-200">
                  {data.development_paths.map((row) => (
                    <tr key={row.option} className="bg-gray-900/50 print:bg-white">
                      <td className="px-3 py-2 font-medium text-gray-300 print:text-gray-700">
                        {row.option}
                      </td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.path}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.process}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.scale}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.time_to_permit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.development_paths_footnote && (
              <p className="text-xs text-gray-500 mt-3 leading-relaxed">{data.development_paths_footnote}</p>
            )}
          </section>
        )}

        {!!data.allowable_uses?.length && (
          <section>
            <SectionTitle title="Permitted uses" />
            <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300">
              <table className="w-full text-sm text-left min-w-[480px]">
                <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                  <tr>
                    <th className="px-3 py-2 font-medium">Use</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Zone</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 bg-gray-900 print:divide-gray-200 print:bg-white">
                  {data.allowable_uses.map((row) => (
                    <tr key={`${row.use}-${row.zone_code}`}>
                      <td className="px-3 py-2 text-gray-300">{row.use}</td>
                      <td className="px-3 py-2 text-gray-400">{row.status}</td>
                      <td className="px-3 py-2 text-gray-400 font-mono text-xs">{row.zone_code}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {data.dimensional_comparison && (
          <section>
            <SectionTitle title="Base vs overlay dimensional comparison" />
            <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300">
              <table className="w-full text-sm text-left min-w-[480px]">
                <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                  <tr>
                    <th className="px-3 py-2 font-medium">Standard</th>
                    {data.dimensional_comparison.columns.map((col) => (
                      <th key={col} className="px-3 py-2 font-medium">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 bg-gray-900 print:divide-gray-200 print:bg-white">
                  {data.dimensional_comparison.rows.map((row) => (
                    <tr key={row.standard}>
                      <td className="px-3 py-2 font-medium text-gray-300 print:text-gray-700">
                        {row.standard}
                      </td>
                      {row.values.map((val, i) => (
                        <td key={i} className="px-3 py-2 text-gray-400 print:text-gray-800">
                          <ComparisonCell val={val} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!!data.dimensional_controls?.length && (
          <section>
            <SectionTitle title="Primary regime dimensional controls" />
            <KvTable
              rows={data.dimensional_controls.map((row) => ({
                label: row.metric,
                value: `${row.limit} · ${row.current}`,
              }))}
            />
          </section>
        )}

        {!!data.zoning_constraints?.length && (
          <section>
            <SectionTitle title="Constraints affecting zoning approvals" />
            <div className="space-y-2">
              {data.zoning_constraints.map((c) => (
                <div
                  key={c.label}
                  className={`flex flex-col gap-1 p-3 rounded-lg border text-sm ${
                    c.status === "clear"
                      ? "border-gray-800 bg-gray-950/40"
                      : "border-amber-500/30 bg-amber-500/5"
                  }`}
                >
                  <div className="flex justify-between items-start gap-4">
                    <span className="font-medium text-gray-300">{c.label}</span>
                    <span
                      className={`text-xs text-right max-w-[60%] ${
                        c.status === "clear" ? "text-green-400" : "text-amber-400"
                      }`}
                    >
                      {c.detail}
                    </span>
                  </div>
                  {c.source && (
                    <p className="text-[11px] text-gray-600 font-mono print:text-gray-500">
                      Cite: {c.source}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {!!data.process_pathway?.length && (
          <section>
            <SectionTitle title="Entitlement process pathway" />
            <p className="text-xs text-gray-500 mb-3">
              Distinguishes Site Plan (overlay election), ZBA (variance / special permit), and ISD
              building permit. Durations labeled estimate unless marked Gold.
            </p>
            <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300">
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Stage</th>
                    <th className="px-3 py-2 text-left font-medium">Body</th>
                    <th className="px-3 py-2 text-left font-medium">Path</th>
                    <th className="px-3 py-2 text-left font-medium">Duration</th>
                    <th className="px-3 py-2 text-left font-medium">Basis</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 print:divide-gray-200">
                  {data.process_pathway.map((stage) => (
                    <tr key={stage.stage} className="bg-gray-900/50 print:bg-white">
                      <td className="px-3 py-2 text-gray-300 text-xs">{stage.stage}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{stage.body}</td>
                      <td className="px-3 py-2 text-gray-500 text-xs font-mono">
                        {stage.path_type || "—"}
                      </td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{stage.duration}</td>
                      <td className="px-3 py-2 text-xs">
                        {stage.duration_basis === "gold" ? (
                          <span className="text-green-400">Gold fact</span>
                        ) : (
                          <span className="text-amber-400">Estimate</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(data.process_pathway_footnote || data.board_dockets_status?.detail) && (
              <p className="text-xs text-gray-500 mt-3 leading-relaxed">
                {data.process_pathway_footnote || data.board_dockets_status?.detail}
              </p>
            )}
          </section>
        )}

        {data.board_dockets_status?.status === "missing" && (
          <section>
            <div className="flex gap-3 p-4 rounded-xl border border-amber-500/30 bg-amber-950/20">
              <AlertTriangle className="text-amber-500 w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-amber-200 mb-1">
                  Board dockets not in Gold
                </p>
                <p className="text-xs text-gray-400 leading-relaxed">
                  {data.board_dockets_status.detail}
                </p>
              </div>
            </div>
          </section>
        )}

        {!!data.open_items?.length && (
          <section>
            <SectionTitle title="Open items before commitment (attorney checklist)" />
            <ul className="space-y-2 text-sm text-gray-400 list-disc list-inside print:text-gray-700">
              {data.open_items.map((item) => (
                <li key={item} className="leading-relaxed">
                  {item}
                </li>
              ))}
            </ul>
          </section>
        )}

        {data.sources && (
          <p className="text-xs text-gray-600 italic print:text-gray-500 border-t border-gray-800 pt-6">
            {data.sources}
          </p>
        )}
      </div>
    </div>
  );
}
