"use client";

import { Clock, AlertTriangle } from "lucide-react";
import type { PermitTimelinePayload, PermitTimelineKeyPermit } from "@/lib/api";

function fmtDays(value?: number | null) {
  if (value == null) return "—";
  return `${Math.round(value)} days`;
}

function fmtRange(row: PermitTimelineKeyPermit) {
  const low = row.estimated_days_low;
  const mid = row.median_days ?? row.estimated_days_mid;
  const high = row.estimated_days_high;
  if (low == null && mid == null && high == null) return "—";
  if (low != null && high != null) {
    const midS = mid != null ? Math.round(mid) : "—";
    return `${Math.round(low)}–${Math.round(high)} days (mid ${midS})`;
  }
  return fmtDays(mid);
}

function confidenceClass(conf?: string) {
  if (conf === "high") return "text-emerald-400";
  if (conf === "medium") return "text-blue-400";
  return "text-amber-400";
}

function statusClass(status?: string) {
  if (!status) return "text-gray-400";
  if (["APPROVED", "CLOSED", "INSPECTIONS"].includes(status)) return "text-emerald-400";
  if (["SUBMITTED", "UNDER_REVIEW"].includes(status)) return "text-amber-400";
  return "text-red-400";
}

function SectionTitle({ title }: { title: string }) {
  return (
    <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 print:text-gray-700 border-b border-gray-800 pb-2 print:border-gray-300">
      {title}
    </h4>
  );
}

type Props = {
  data: PermitTimelinePayload;
  generatedSeconds?: number | null;
};

export default function PermitTimelineReport({ data, generatedSeconds }: Props) {
  const stats = data.summary_stats || {};
  const keyPermits = data.key_permits || [];
  const decisions = data.recent_decisions || [];
  const parcel = data.parcel_context;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl print:border-gray-300 print:shadow-none">
      <div className="p-6 border-b border-gray-800 bg-gray-800/30 flex flex-wrap justify-between items-start gap-4">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
            Permit Timeline Intelligence
          </p>
          <h3 className="text-xl font-bold text-white print:text-black mb-2">
            {data.town_name || data.town_slug}
          </h3>
          <p className="text-xs text-gray-500">
            {data.prepared_on && <span>Prepared {data.prepared_on}</span>}
            <span className="mx-2">·</span>
            <span>{stats.total_permits ?? 0} Gold permits</span>
            {generatedSeconds != null && (
              <>
                <span className="mx-2">·</span>
                <span>{generatedSeconds.toFixed(1)}s</span>
              </>
            )}
          </p>
        </div>
        <div className="text-right">
          <div className="text-sm text-gray-400">Open / ledger</div>
          <div className="text-2xl font-bold text-blue-400">
            {stats.open_permits ?? 0}
            <span className="text-lg text-gray-500">/{stats.total_permits ?? 0}</span>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-10">
        {data.pilot_message && (
          <p className="text-xs text-amber-400/90 italic flex gap-2 items-start">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            {data.pilot_message}
          </p>
        )}

        <section>
          <SectionTitle title="Town Velocity Snapshot" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Reno median" value={fmtDays(stats.avg_days_residential_reno)} />
            <StatCard label="New construction median" value={fmtDays(stats.avg_days_new_construction)} />
            <StatCard label="Commercial median" value={fmtDays(stats.avg_days_commercial)} />
            <StatCard
              label="ZBA estimate"
              value={fmtDays(stats.avg_days_zba_special_permit)}
              sub={stats.approval_rate_zba ? `${stats.approval_rate_zba} approve` : undefined}
            />
          </div>
          <p className="text-xs text-gray-500 mt-3">
            Fastest filing month: {stats.fastest_month || "—"} · Slowest: {stats.slowest_month || "—"}
          </p>
        </section>

        <section>
          <SectionTitle title="Key Permit Timeline Estimates" />
          <p className="text-xs text-gray-500 mb-3">
            Use for carry planning. ISD rows = Gold filed→issued. Board rows = labeled estimates
            (not in ISD ledger).
          </p>
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm min-w-[800px]">
              <thead>
                <tr className="bg-gray-800/60 text-left text-xs uppercase tracking-wider text-gray-400">
                  <th className="px-3 py-2.5">Permit / path</th>
                  <th className="px-3 py-2.5">Body</th>
                  <th className="px-3 py-2.5">Estimated duration</th>
                  <th className="px-3 py-2.5 text-right">Issued n</th>
                  <th className="px-3 py-2.5">Confidence</th>
                  <th className="px-3 py-2.5">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {keyPermits.map((row) => (
                  <tr key={row.permit_type} className="bg-gray-950/40">
                    <td className="px-3 py-2.5 text-gray-200 font-medium">
                      {row.label}
                      <div className="text-[10px] text-gray-600 font-mono">{row.permit_type}</div>
                    </td>
                    <td className="px-3 py-2.5 text-gray-400 text-xs">{row.approval_body}</td>
                    <td className="px-3 py-2.5 text-blue-300 tabular-nums font-medium">
                      {fmtRange(row)}
                    </td>
                    <td className="px-3 py-2.5 text-right text-gray-400 tabular-nums">
                      {row.issued_sample_size ?? 0}
                    </td>
                    <td className={`px-3 py-2.5 text-xs font-medium uppercase ${confidenceClass(row.confidence)}`}>
                      {row.confidence || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-gray-500 max-w-xs">{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <SectionTitle title="Recent Decisions (Gold ledger)" />
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="bg-gray-800/60 text-left text-xs uppercase tracking-wider text-gray-400">
                  <th className="px-3 py-2.5">Permit #</th>
                  <th className="px-3 py-2.5">Type</th>
                  <th className="px-3 py-2.5">Filed</th>
                  <th className="px-3 py-2.5">Issued</th>
                  <th className="px-3 py-2.5 text-right">Days</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">Address</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {decisions.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-6 text-center text-gray-500">
                      No permits in Gold
                    </td>
                  </tr>
                )}
                {decisions.map((d) => (
                  <tr key={d.permit_number || `${d.address}-${d.application_date}`} className="bg-gray-950/40">
                    <td className="px-3 py-2.5 font-mono text-xs text-gray-400">
                      {d.permit_number || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-gray-300 text-xs">
                      {d.permit_type_label || d.permit_type}
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 tabular-nums text-xs">
                      {d.application_date || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 tabular-nums text-xs">
                      {d.decision_date || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right text-white tabular-nums font-medium">
                      {d.calendar_days != null ? d.calendar_days : "—"}
                    </td>
                    <td className={`px-3 py-2.5 text-xs font-medium ${statusClass(d.outcome)}`}>
                      {d.outcome || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-gray-400 text-xs">{d.address}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {parcel && (
          <section>
            <SectionTitle
              title={`Parcel Path — ${parcel.address || parcel.parcel_id || "Selected"}`}
            />
            <p className="text-xs text-gray-500 mb-3">
              {parcel.parcel_permit_count ?? 0} permit(s) matched to this parcel in Gold.
            </p>
            <div className="overflow-x-auto rounded-lg border border-gray-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-800/60 text-left text-xs uppercase tracking-wider text-gray-400">
                    <th className="px-3 py-2.5">Path step</th>
                    <th className="px-3 py-2.5">Body</th>
                    <th className="px-3 py-2.5">Estimated duration</th>
                    <th className="px-3 py-2.5">Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {(parcel.suggested_path || []).map((s) => (
                    <tr key={s.step} className="bg-gray-950/40">
                      <td className="px-3 py-2.5 text-gray-200">
                        {s.step}
                        {s.optional && (
                          <span className="ml-2 text-[10px] uppercase text-amber-400">if required</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-gray-400 text-xs">{s.body}</td>
                      <td className="px-3 py-2.5 text-blue-300 tabular-nums">
                        {s.estimated_days_low != null && s.estimated_days_high != null
                          ? `${Math.round(s.estimated_days_low)}–${Math.round(s.estimated_days_high)} days`
                          : fmtDays(s.estimated_days_mid)}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-gray-500">{s.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!!data.data_sources?.length && (
          <p className="text-xs text-gray-600 border-t border-gray-800 pt-4">
            Sources: {data.data_sources.join(" · ")}
          </p>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-950/50 p-4">
      <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
        <Clock className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="text-lg font-bold text-white tabular-nums">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export function permitTimelineToCsv(data: PermitTimelinePayload): string {
  const lines: string[] = [];
  lines.push("--- KEY PERMIT TIMELINE ESTIMATES ---");
  lines.push(
    "Permit,Body,Est Low,Est Mid,Est High,Issued n,Confidence,Source,Note",
  );
  for (const r of data.key_permits || []) {
    lines.push(
      [
        `"${r.label}"`,
        `"${r.approval_body}"`,
        r.estimated_days_low ?? "",
        r.median_days ?? r.estimated_days_mid ?? "",
        r.estimated_days_high ?? "",
        r.issued_sample_size ?? "",
        r.confidence ?? "",
        r.source ?? "",
        `"${(r.note || "").replace(/"/g, '""')}"`,
      ].join(","),
    );
  }
  lines.push("");
  lines.push("--- RECENT DECISIONS ---");
  lines.push("Permit #,Type,Filed,Issued,Days,Status,Address");
  for (const d of data.recent_decisions || []) {
    lines.push(
      [
        d.permit_number ?? "",
        d.permit_type_label ?? d.permit_type ?? "",
        d.application_date ?? "",
        d.decision_date ?? "",
        d.calendar_days ?? "",
        d.outcome ?? "",
        `"${(d.address || "").replace(/"/g, '""')}"`,
      ].join(","),
    );
  }
  return lines.join("\n");
}
