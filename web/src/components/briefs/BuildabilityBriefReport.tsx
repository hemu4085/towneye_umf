"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  XCircle,
} from "lucide-react";
import type { BuildabilityPayload } from "@/lib/api";

function fmtMoney(value?: number | null) {
  if (value == null) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

function fmtSqft(value?: number | null) {
  if (value == null) return "—";
  return `${Math.round(value).toLocaleString()} sf`;
}

function SectionTitle({ num, title }: { num: string; title: string }) {
  return (
    <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 print:text-gray-700 border-b border-gray-800 pb-2 print:border-gray-300">
      {num} · {title}
    </h4>
  );
}

function WraparoundStatus({ status, detail }: { status: string; detail: string }) {
  if (status === "clear") {
    return <span className="text-green-400 text-xs">✅ {detail}</span>;
  }
  if (status === "caution") {
    return <span className="text-amber-400 text-xs">⚠ {detail}</span>;
  }
  return <span className="text-red-400 text-xs">⚠ {detail}</span>;
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

type Props = {
  data: BuildabilityPayload;
  generatedSeconds?: number | null;
};

export default function BuildabilityBriefReport({ data, generatedSeconds }: Props) {
  const verdict = verdictStyles(data.headline_verdict_class);
  const prop = data.property;
  const parcel = data.parcel;

  const snapshotRows: { label: string; value: string }[] = [
    { label: "Address", value: data.address || "—" },
  ];
  if (prop?.owner_name) snapshotRows.push({ label: "Owner", value: prop.owner_name });
  snapshotRows.push({ label: "Parcel ID", value: data.parcel_id });
  if (data.map_block_lot) {
    snapshotRows.push({ label: "Map–Block–Lot", value: String(data.map_block_lot) });
  }
  if (prop?.book_page) snapshotRows.push({ label: "Deed reference", value: prop.book_page });
  if (prop?.year_built) {
    snapshotRows.push({
      label: "Year built",
      value: prop.building_type
        ? `${prop.year_built} (${prop.building_type})`
        : String(prop.year_built),
    });
  }
  if (prop?.luc_description) {
    snapshotRows.push({
      label: "Use code (current)",
      value: `${prop.luc || ""} — ${prop.luc_description}`.trim(),
    });
  }
  if (prop?.finished_area_sqft) {
    snapshotRows.push({
      label: "Existing GFA",
      value: `${fmtSqft(prop.finished_area_sqft)} assessor (total finished area)`,
    });
  }
  if (prop?.beds != null || prop?.baths != null) {
    snapshotRows.push({
      label: "Bedrooms / bathrooms",
      value: `${prop.beds ?? "—"} BR / ${prop.baths ?? "—"} baths`,
    });
  }
  if (prop?.last_sale_date) {
    snapshotRows.push({
      label: "Last sale",
      value: `${fmtMoney(prop.last_sale_price)} (${prop.last_sale_date})`,
    });
  }
  if (prop?.assessed_value != null) {
    snapshotRows.push({ label: "Assessed value", value: fmtMoney(prop.assessed_value) });
  }
  const lotParts: string[] = [];
  if (prop?.lot_size_sqft) lotParts.push(`${fmtSqft(prop.lot_size_sqft)} assessor (regulatory)`);
  if (parcel?.area_sqft) lotParts.push(`${fmtSqft(parcel.area_sqft)} GIS polygon`);
  snapshotRows.push({ label: "Lot size", value: lotParts.join(" · ") || "—" });
  if (parcel?.lot_shape) snapshotRows.push({ label: "Lot shape", value: parcel.lot_shape });
  if (parcel?.longest_edge_ft) {
    snapshotRows.push({
      label: "Approx. longest edge",
      value: `${parcel.longest_edge_ft.toFixed(1)} ft`,
    });
  }
  if (parcel?.centroid_lat != null && parcel?.centroid_lon != null) {
    snapshotRows.push({
      label: "Centroid (WGS-84)",
      value: `${parcel.centroid_lat.toFixed(7)} N, ${parcel.centroid_lon.toFixed(7)} W`,
    });
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl print:border-gray-300 print:shadow-none">
      {/* Header card */}
      <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex flex-wrap justify-between items-start gap-4">
        <div className="min-w-0">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Parcel Buildability Brief</p>
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
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm text-gray-400 print:text-gray-600 mb-1">Opportunity Score</div>
          <div className="text-3xl font-bold text-purple-400 print:text-purple-700">
            {data.opportunity_score ?? "—"}
            <span className="text-lg text-gray-500">/10</span>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-10">
        {/* §1 Executive Summary */}
        <section>
          <SectionTitle num="1" title="Executive Summary" />
          {data.headline_verdict_text && (
            <div className={`flex gap-3 p-4 rounded-xl border mb-4 ${verdict.box}`}>
              {verdict.icon}
              <p className="text-sm leading-relaxed">{data.headline_verdict_text}</p>
            </div>
          )}
          {data.overlay_narrative && (
            <p className="text-sm text-gray-300 leading-relaxed mb-3 print:text-gray-800">
              {data.overlay_narrative}
            </p>
          )}
          {data.adu_law_note && (
            <p className="text-sm text-gray-400 leading-relaxed mb-3 print:text-gray-800">
              <span className="font-medium text-gray-300 print:text-gray-700">Statewide ADU law:</span>{" "}
              {data.adu_law_note.replace(/^Statewide ADU law[^:]*:\s*/i, "")}
            </p>
          )}
          {data.executive_sources && (
            <p className="text-xs text-gray-600 italic print:text-gray-500">{data.executive_sources}</p>
          )}
        </section>

        {/* §2 Parcel Snapshot */}
        <section>
          <SectionTitle num="2" title="Parcel Snapshot" />
          <KvTable rows={snapshotRows} />
          {!data.has_property_record && (
            <p className="text-xs text-gray-500 mt-3 print:text-gray-600">
              No assessor record found in property.parquet for this parcel. Owner / deed / GFA fields
              may be omitted; re-running the property ingestor will fill them automatically.
            </p>
          )}
          <p className="text-xs text-gray-600 italic mt-3 print:text-gray-500">
            Sources: Town tax assessor (property.parquet); Town parcels-with-CAMA FeatureServer
            (parcel.parquet); centroid + edge metrics from GIS polygon.
          </p>
        </section>

        {/* §3 Zoning Stack */}
        <section>
          <SectionTitle num="3" title="Zoning Stack & Dimensional Compliance" />

          {!!data.base_zones?.length && (
            <div className="mb-6">
              <h5 className="text-xs font-semibold text-gray-500 mb-2">3.1 — Base zoning</h5>
              {data.base_zones.map((z) => (
                <div key={z.code} className="mb-3">
                  <KvTable
                    rows={[
                      {
                        label: "Zone code",
                        value: z.rule?.description
                          ? `${z.code} — ${z.rule.description}`
                          : z.code || "—",
                      },
                      { label: "Source", value: `${z.layer || "—"} — point-in-polygon at centroid` },
                      ...(z.rule?.allowed_uses?.length
                        ? [{ label: "Permitted uses", value: z.rule.allowed_uses.join(", ") }]
                        : []),
                    ]}
                  />
                </div>
              ))}
            </div>
          )}

          {!!data.overlay_zones?.length ? (
            <div className="mb-6">
              <h5 className="text-xs font-semibold text-gray-500 mb-2">3.2 — Overlay zoning</h5>
              {data.overlay_zones.map((z) => (
                <div key={z.code || z.label} className="mb-3">
                  <KvTable
                    rows={[
                      {
                        label: "Overlay",
                        value: z.label && z.code && z.label !== z.code
                          ? `${z.code} — ${z.label}`
                          : z.code || z.label || "—",
                      },
                      { label: "Source", value: `${z.layer || "—"} — point-in-polygon at centroid` },
                      ...(z.rule?.allowed_uses?.length
                        ? [{ label: "Permitted uses", value: z.rule.allowed_uses.join(", ") }]
                        : []),
                    ]}
                  />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500 mb-4">No overlay districts intersect this parcel.</p>
          )}

          {data.dimensional_comparison && (
            <div>
              <h5 className="text-xs font-semibold text-gray-500 mb-2">
                3.{data.overlay_zones?.length ? "3" : "2"} — Side-by-side dimensional comparison
              </h5>
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
                            {val === "qualifies" ? (
                              <span className="text-green-400">✓ qualifies</span>
                            ) : val === "non-conforming" ? (
                              <span className="text-red-400">⚠ non-conforming</span>
                            ) : val === "not specified" ? (
                              <span className="text-amber-400">⚠ not specified</span>
                            ) : (
                              val
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

        {/* §4 Buildable Envelope Math */}
        <section>
          <SectionTitle num="4" title="Buildable Envelope — Math" />
          {data.envelope_calcs?.length ? (
            <div className="space-y-4">
              {data.envelope_calcs.map((calc, idx) => (
                <div key={calc.label}>
                  <h5 className="text-xs font-semibold text-gray-400 mb-2">
                    4.{idx + 1} — Under {calc.label}
                  </h5>
                  <div className="bg-gray-950 border-l-4 border-blue-600 rounded-r-lg p-4 font-mono text-xs text-gray-300 leading-relaxed print:bg-gray-50 print:text-gray-800 print:border-blue-400">
                    <p className="mb-2 text-gray-400 print:text-gray-600">{calc.rationale}</p>
                    {calc.lines.map((line) => (
                      <div key={line}>{line}</div>
                    ))}
                  </div>
                  {calc.notes && (
                    <p className="text-xs text-gray-500 mt-2 print:text-gray-600">{calc.notes}</p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">No envelope math available for this parcel.</p>
          )}
        </section>

        {/* §5 Development Options Matrix */}
        <section>
          <SectionTitle num="5" title="Development Options Matrix" />
          <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300">
            <table className="w-full text-sm min-w-[960px]">
              <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                <tr>
                  <th className="px-3 py-2 text-left">#</th>
                  <th className="px-3 py-2 text-left">Option</th>
                  <th className="px-3 py-2 text-left">Path</th>
                  <th className="px-3 py-2 text-left">Process</th>
                  <th className="px-3 py-2 text-left">Lot qualifies?</th>
                  <th className="px-3 py-2 text-left">Indicative scale</th>
                  <th className="px-3 py-2 text-left">Time to permit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 print:divide-gray-200">
                {(data.development_options || []).map((opt, i) => (
                  <tr key={i} className="bg-gray-900/50 print:bg-white">
                    <td className="px-3 py-2 text-gray-500">{opt.num}</td>
                    <td className="px-3 py-2 font-medium text-gray-300 print:text-gray-700">{opt.option}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{opt.path}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{opt.process}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{opt.lot_qualifies ?? "—"}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{opt.scale ?? "—"}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{opt.time_to_permit ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.development_options_footnote && (
            <p className="text-xs text-gray-500 mt-3 leading-relaxed print:text-gray-600">
              {data.development_options_footnote}
            </p>
          )}
          <p className="text-xs text-gray-600 mt-3 italic print:text-gray-500">
            Sources: Arlington Zoning Bylaw §5.4 (R2 permitted uses), §5.8 (NMF overlay); MA Affordable
            Homes Act 2024 (c. 150/2024).
          </p>
        </section>

        {/* §6 Wraparound Constraints */}
        <section>
          <SectionTitle
            num="6"
            title={data.wraparound_section_title || "Wraparound Constraints"}
          />
          <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300 mb-4">
            <table className="w-full text-sm min-w-[640px]">
              <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                <tr>
                  <th className="px-3 py-2 text-left">Constraint</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 print:divide-gray-200">
                {(data.wraparound || []).map((w) => (
                  <tr key={w.label} className="bg-gray-900/50 print:bg-white">
                    <td className="px-3 py-2 font-medium text-gray-300 print:text-gray-700">{w.label}</td>
                    <td className="px-3 py-2">
                      <WraparoundStatus status={w.status} detail={w.detail} />
                    </td>
                    <td className="px-3 py-2 text-gray-500 text-xs">{w.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.wraparound_summary && (
            <p className="text-sm text-gray-400 leading-relaxed print:text-gray-800">
              {data.wraparound_summary}
            </p>
          )}
        </section>

        {/* §7 Process Pathway */}
        <section>
          <SectionTitle num="7" title="Process Pathway — Indicative Timeline" />
          <p className="text-xs text-gray-500 mb-3 print:text-gray-600">
            Site Plan (overlay election) vs ZBA vs ISD. Durations are estimates unless marked Gold.
          </p>
          <div className="overflow-hidden rounded-lg border border-gray-800 print:border-gray-300">
            <table className="w-full text-sm">
              <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                <tr>
                  <th className="px-3 py-2 text-left">Stage</th>
                  <th className="px-3 py-2 text-left">Body</th>
                  <th className="px-3 py-2 text-left">Path</th>
                  <th className="px-3 py-2 text-left">Est. duration</th>
                  <th className="px-3 py-2 text-left">Basis</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 print:divide-gray-200">
                {(data.process_pathway || []).map((row) => (
                  <tr key={row.stage} className="bg-gray-900/50 print:bg-white">
                    <td className="px-3 py-2 font-medium text-gray-300 print:text-gray-700">{row.stage}</td>
                    <td className="px-3 py-2 text-gray-400">{row.body}</td>
                    <td className="px-3 py-2 text-gray-500 text-xs font-mono">{row.path_type || "—"}</td>
                    <td className="px-3 py-2 text-gray-400">{row.duration}</td>
                    <td className="px-3 py-2 text-xs">
                      {row.duration_basis === "gold" ? (
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
          {data.process_pathway_footnote && (
            <p className="text-xs text-gray-500 mt-3 leading-relaxed print:text-gray-600">
              {data.process_pathway_footnote}
            </p>
          )}
        </section>

        {/* §8 Open Items */}
        <section>
          <SectionTitle num="8" title="Open Items — To Be Verified Before Commitment" />
          <ol className="list-decimal list-inside space-y-3 text-sm text-gray-300 leading-relaxed print:text-gray-800">
            {(data.open_items || []).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ol>
        </section>

        {/* Value-add insights (from deal scoring) */}
        {!!data.insights?.length && (
          <section>
            <SectionTitle num="—" title="Value-Add Insights" />
            <div className="bg-purple-900/10 border border-purple-500/20 rounded-xl p-4 print:bg-purple-50">
              <ul className="space-y-2">
                {data.insights.map((insight, idx) => (
                  <li key={idx} className="flex items-start text-sm text-gray-200 print:text-gray-800">
                    <ChevronRight className="h-5 w-5 mr-2 text-purple-500 shrink-0 mt-0.5" />
                    {insight}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}

        {/* §9 Methodology */}
        <section>
          <SectionTitle num="9" title="Methodology & Sources" />
          <h5 className="text-xs font-semibold text-gray-500 mb-2">9.1 Data acquisition</h5>
          <ul className="list-disc list-inside text-sm text-gray-400 space-y-1 mb-4 print:text-gray-700">
            <li>
              <span className="font-medium text-gray-300 print:text-gray-700">Parcel geometry:</span>{" "}
              parcel.parquet (Tier 2a) — town Parcels-with-CAMA FeatureServer.
            </li>
            <li>
              <span className="font-medium text-gray-300 print:text-gray-700">Zoning rules:</span>{" "}
              zoning.parquet (Tier 1 bylaw ingestor).
            </li>
            <li>
              <span className="font-medium text-gray-300 print:text-gray-700">Overlay polygons:</span>{" "}
              zoning-overlay.parquet (Tier 2b).
            </li>
            <li>
              <span className="font-medium text-gray-300 print:text-gray-700">Wraparound constraints:</span>{" "}
              OverlayResolver against MACRIS, historic, environmental, noncompliance Gold parquets.
            </li>
            {data.has_property_record && (
              <li>
                <span className="font-medium text-gray-300 print:text-gray-700">Assessor record:</span>{" "}
                property.parquet.
              </li>
            )}
          </ul>
          <h5 className="text-xs font-semibold text-gray-500 mb-2">9.2 Spatial method</h5>
          <p className="text-xs text-gray-500 mb-4 print:text-gray-600">
            Point-in-polygon and polyline-distance queries use Shapely 2.x with WGS-84 coordinates.
            Distances reported in feet via haversine (sub-1% drift at municipal scale).
          </p>
          <h5 className="text-xs font-semibold text-gray-500 mb-2">9.3 Disclaimer</h5>
          <p className="text-xs text-gray-500 print:text-gray-600">
            This brief is prepared for informational purposes only. It is not legal advice, not a
            licensed appraisal, and not a substitute for a stamped survey or an opinion from the
            town&apos;s Inspectional Services. Verify all conclusions against the consolidated bylaw
            and a licensed land-use attorney before any binding commitment.
          </p>
        </section>
      </div>
    </div>
  );
}
