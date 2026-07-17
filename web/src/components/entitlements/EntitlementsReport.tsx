"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Info,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import type { EntitlementsPayload, ZoningRegulatorySignal } from "@/lib/api";

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
  if (severity === "opportunity") return <Info className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />;
  if (severity === "warning") return <ShieldAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />;
  return <Info className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />;
}

function SignalRow({ sig }: { sig: ZoningRegulatorySignal }) {
  const border =
    sig.severity === "warning"
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
  data: EntitlementsPayload;
  generatedSeconds?: number | null;
};

export default function EntitlementsReport({ data, generatedSeconds }: Props) {
  const verdict = verdictStyles(data.headline_verdict_class);
  const docketStatus = data.board_dockets_status?.status;
  /** Only highlight when Gold actually found dockets on this parcel. */
  const hasMatchedDockets = docketStatus === "found" && !!data.dockets?.length;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl print:border-gray-300 print:shadow-none">
      <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex flex-wrap justify-between items-start gap-4">
        <div className="min-w-0">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Entitlements &amp; Risk Brief
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
          <p className="text-xs text-gray-600 mt-2">
            {data.lot_size_sqft != null && <span>Lot {fmtSqft(data.lot_size_sqft)}</span>}
            {data.existing_gfa_sqft != null && (
              <span className="mx-2">· Existing GFA {fmtSqft(data.existing_gfa_sqft)}</span>
            )}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-medium text-blue-400 print:text-blue-700">
            {data.zoning_district || "—"}
          </div>
          {data.has_mbta_communities_overlay && (
            <div className="text-xs text-purple-400 mt-1 border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 rounded inline-block">
              MBTA §3A / NMF
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
            <SectionTitle title="Overlay election (regimes do not stack)" />
            <div className="p-4 rounded-xl border border-purple-500/30 bg-purple-950/20 space-y-2">
              <p className="text-sm text-gray-300">
                <span className="font-medium text-purple-300">Recommended:</span>{" "}
                {data.overlay_election.recommended_regime}
                {data.overlay_election.alternative_regime && (
                  <span className="text-gray-500">
                    {" "}
                    (alt: {data.overlay_election.alternative_regime})
                  </span>
                )}
              </p>
              <p className="text-sm text-amber-200/90">
                {data.overlay_election.election_type}
              </p>
              <p className="text-sm text-gray-400 leading-relaxed">
                {data.overlay_election.rationale}
              </p>
              {data.overlay_election.legal_basis && (
                <p className="text-xs text-gray-500 font-mono">
                  Citation: {data.overlay_election.legal_basis}
                </p>
              )}
            </div>
          </section>
        )}

        {!!data.risk_signals?.length && (
          <section>
            <SectionTitle title="Entitlement risk signals" />
            <div className="space-y-2">
              {data.risk_signals.map((sig) => (
                <SignalRow key={`${sig.signal}-${sig.detail.slice(0, 24)}`} sig={sig} />
              ))}
            </div>
          </section>
        )}

        {!!data.process_pathway?.length && (
          <section>
            <SectionTitle title="Entitlement process pathway" />
            <p className="text-xs text-gray-500 mb-3">
              Site Plan (overlay) vs ZBA vs ISD. Durations labeled Estimate unless Gold.
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
            {data.process_pathway_footnote && (
              <p className="text-xs text-gray-500 mt-3 leading-relaxed">
                {data.process_pathway_footnote}
              </p>
            )}
          </section>
        )}

        {!!data.development_paths?.length && (
          <section>
            <SectionTitle title="Zoning-filtered development paths" />
            <div className="overflow-x-auto rounded-lg border border-gray-800 print:border-gray-300">
              <table className="w-full text-sm min-w-[720px]">
                <thead className="text-xs text-gray-400 bg-gray-950 print:bg-gray-100">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Option</th>
                    <th className="px-3 py-2 text-left font-medium">Legal path</th>
                    <th className="px-3 py-2 text-left font-medium">Process</th>
                    <th className="px-3 py-2 text-left font-medium">Scale</th>
                    <th className="px-3 py-2 text-left font-medium">Timeline</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 print:divide-gray-200">
                  {data.development_paths.map((row) => (
                    <tr key={row.option} className="bg-gray-900/50 print:bg-white">
                      <td className="px-3 py-2 font-medium text-gray-300 text-xs">{row.option}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.path}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.process}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.scale}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{row.time_to_permit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!!data.zoning_constraints?.length && (
          <section>
            <SectionTitle title="Constraints affecting approvals" />
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
                    <p className="text-[11px] text-gray-600 font-mono">Cite: {c.source}</p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <SectionTitle title="Board docket history" />
          {hasMatchedDockets ? (
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-400 bg-gray-950">
                  <tr>
                    <th className="px-3 py-2 text-left">Board</th>
                    <th className="px-3 py-2 text-left">Docket</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Summary</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {data.dockets!.map((d, i) => (
                    <tr key={`${d.docket || d.board}-${i}`}>
                      <td className="px-3 py-2 text-gray-300 text-xs">{d.board}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs font-mono">
                        {d.docket || "—"}
                      </td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{d.status}</td>
                      <td className="px-3 py-2 text-gray-400 text-xs">{d.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-500 leading-relaxed">
              No ZBA / Planning / ARB / Conservation docket rows are available for this parcel in
              the current Gold release. Confirm active filings with the Town Clerk if needed.
            </p>
          )}
        </section>

        {!!data.open_items?.length && (
          <section>
            <SectionTitle title="Open items before commitment" />
            <ul className="space-y-2 text-sm text-gray-400 list-disc list-inside">
              {data.open_items.map((item) => (
                <li key={item} className="leading-relaxed">
                  {item}
                </li>
              ))}
            </ul>
          </section>
        )}

        {data.sources && (
          <p className="text-xs text-gray-600 italic border-t border-gray-800 pt-6">{data.sources}</p>
        )}
      </div>
    </div>
  );
}
