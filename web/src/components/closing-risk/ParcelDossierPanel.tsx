"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import { fetchParcelDossier, type ParcelDossier } from "@/lib/api";

type Props = {
  townSlug: string;
  parcelId: string;
  address: string;
  onClose?: () => void;
};

type PermitRow = Record<string, unknown>;
type ViolationRow = {
  source?: string;
  violation_type?: string;
  status?: string;
  opened?: string;
  detail?: string;
  detail_full?: string;
  detail_url?: string | null;
  external_id?: string | null;
  link_kind?: string | null;
  link_label?: string | null;
  search_hint?: string | null;
};

type DetailState =
  | { kind: "permit"; row: PermitRow }
  | { kind: "violation"; row: ViolationRow }
  | null;

function statusClass(status: string) {
  const s = status.toUpperCase();
  if (["OPEN", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "INSPECTIONS"].some((x) => s.includes(x))) {
    return "text-red-400 bg-red-500/10 border-red-500/30";
  }
  if (s.includes("CLOSED")) return "text-emerald-400 bg-emerald-500/10 border-emerald-500/30";
  return "text-gray-400 bg-gray-800 border-gray-700";
}

function fmtMoney(value: unknown) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return null;
  return `$${Math.round(n).toLocaleString()}`;
}

function CopyButton({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false);
  if (!text || text === "—") return null;
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          /* ignore */
        }
      }}
      className="flex items-center justify-center gap-2 w-full text-sm text-gray-200 border border-gray-600 hover:border-gray-400 rounded-lg py-2"
    >
      <Copy className="h-3.5 w-3.5" />
      {copied ? "Copied" : label}
    </button>
  );
}

function DetailDrawer({
  detail,
  onClose,
  activityUrl,
  isdUrl,
}: {
  detail: NonNullable<DetailState>;
  onClose: () => void;
  activityUrl?: string;
  isdUrl?: string;
}) {
  const title =
    detail.kind === "permit"
      ? `Permit ${String(detail.row.permit_number || "record")}`
      : detail.row.violation_type || "Violation record";

  const linkKind = String(detail.row.link_kind || "");
  const externalUrl = String(detail.row.detail_url || "");
  const isDeepLink = linkKind === "record" || linkKind === "location";
  const isManual = linkKind === "manual" || (detail.kind === "permit" && !isDeepLink && !externalUrl);
  const isScf = detail.kind === "violation" && detail.row.source === "311-seeclickfix";

  const externalLabel =
    detail.kind === "permit"
      ? String(detail.row.link_label || "Open this permit in OpenGov")
      : isScf
        ? String(detail.row.link_label || "Open in SeeClickFix")
        : String(detail.row.link_label || "Open source record");

  const linkHint =
    linkKind === "location"
      ? "Opens the OpenGov property page for this address (all permits / activity)."
      : linkKind === "record"
        ? "Opens this specific OpenGov record."
        : null;

  const permitNumber =
    detail.kind === "permit" ? String(detail.row.permit_number || "").trim() : "";
  const street =
    detail.kind === "permit"
      ? String(detail.row.address || "").split(",")[0].trim()
      : "";
  const searchHint = String(detail.row.search_hint || "").trim();

  const fields: { label: string; value: string }[] =
    detail.kind === "permit"
      ? [
          { label: "Permit #", value: String(detail.row.permit_number ?? "—") },
          { label: "Type", value: String(detail.row.permit_type ?? "—") },
          { label: "Status", value: String(detail.row.status ?? "—") },
          { label: "Applied", value: String(detail.row.application_date ?? "—") },
          { label: "Approved", value: String(detail.row.approval_date ?? "—") },
          {
            label: "Estimated value",
            value: fmtMoney(detail.row.estimated_value) || "—",
          },
          { label: "Address", value: String(detail.row.address ?? "—") },
          { label: "Applicant / owner", value: String(detail.row.owner_name ?? "—") },
          { label: "Inspector", value: String(detail.row.inspector ?? "—") },
          { label: "Work type", value: String(detail.row.work_type ?? "—") },
          { label: "Description", value: String(detail.row.description ?? "—") },
        ]
      : [
          { label: "Type", value: String(detail.row.violation_type ?? "—") },
          { label: "Status", value: String(detail.row.status ?? "—") },
          { label: "Opened", value: String(detail.row.opened ?? "—") },
          { label: "Source", value: String(detail.row.source ?? "—") },
          { label: "Case / ID", value: String(detail.row.external_id ?? "—") },
          {
            label: "Detail",
            value: String(detail.row.detail_full || detail.row.detail || "—"),
          },
        ];

  return (
    <div className="absolute inset-0 z-20 flex justify-end bg-black/40">
      <div className="w-full max-w-md h-full bg-gray-900 border-l border-gray-700 shadow-2xl flex flex-col">
        <div className="px-4 py-3 border-b border-gray-800 flex items-start justify-between gap-3 shrink-0">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
              {detail.kind === "permit" ? "Permit detail" : "Violation detail"}
            </p>
            <h3 className="text-sm font-semibold text-white leading-snug">{title}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white shrink-0"
            aria-label="Close detail"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
          {fields.map((f) => (
            <div key={f.label}>
              <dt className="text-[11px] text-gray-500 uppercase tracking-wider mb-0.5">
                {f.label}
              </dt>
              <dd className="text-sm text-gray-200 whitespace-pre-wrap break-words">{f.value}</dd>
            </div>
          ))}
        </div>

        <div className="px-4 py-3 border-t border-gray-800 shrink-0 space-y-2">
          {isDeepLink && externalUrl ? (
            <>
              <a
                href={externalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-lg py-2.5 no-underline"
              >
                <ExternalLink className="h-4 w-4" />
                {externalLabel}
              </a>
              {linkHint && (
                <p className="text-[11px] text-gray-500 text-center leading-relaxed">{linkHint}</p>
              )}
            </>
          ) : isScf && externalUrl ? (
            <a
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 w-full text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-lg py-2.5 no-underline"
            >
              <ExternalLink className="h-4 w-4" />
              {externalLabel}
            </a>
          ) : isManual ? (
            <>
              <p className="text-[11px] text-amber-200/80 text-center leading-relaxed">
                Arlington OpenGov does not expose public lookup by permit # or address (portal
                home and search URLs do not work). Details above are from Towneye Gold.
              </p>
              {permitNumber && <CopyButton label={`Copy permit # ${permitNumber}`} text={permitNumber} />}
              {street && <CopyButton label={`Copy address ${street}`} text={street} />}
              {!permitNumber && !street && searchHint && (
                <CopyButton label="Copy search text" text={searchHint} />
              )}
              {activityUrl && (
                <a
                  href={activityUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 w-full text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 rounded-lg py-2.5 no-underline"
                >
                  <ExternalLink className="h-4 w-4" />
                  Town permit activity spreadsheets
                </a>
              )}
              {isdUrl && (
                <a
                  href={isdUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 w-full text-sm text-gray-200 border border-gray-600 hover:border-gray-400 rounded-lg py-2 no-underline"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  ISD department page
                </a>
              )}
              <p className="text-[11px] text-gray-500 text-center leading-relaxed">
                Use the Excel lists on the activity page (Ctrl+F by address / permit #), or call
                ISD with the copied permit number.
              </p>
            </>
          ) : (
            <p className="text-xs text-gray-500 text-center">
              No public record link available for this item in Gold.
            </p>
          )}
          <button
            type="button"
            onClick={onClose}
            className="w-full text-sm text-gray-400 hover:text-white py-2 rounded-lg border border-gray-700"
          >
            Back to list
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ParcelDossierPanel({ townSlug, parcelId, address, onClose }: Props) {
  const [dossier, setDossier] = useState<ParcelDossier | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"permits" | "violations">("permits");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<DetailState>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setDetail(null);
    try {
      const data = await fetchParcelDossier({ town_slug: townSlug, parcel_id: parcelId, address });
      setDossier(data);
      if (data.permits.open_count > 0) setTab("permits");
      else if (data.violations.open_count > 0) setTab("violations");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load parcel records");
    } finally {
      setLoading(false);
    }
  }, [townSlug, parcelId, address]);

  useEffect(() => {
    load();
  }, [load]);

  const q = query.trim().toLowerCase();

  const permits = useMemo(() => {
    const rows = (dossier?.permits.permits || []) as PermitRow[];
    if (!q) return rows;
    return rows.filter((r) =>
      [r.permit_number, r.permit_type, r.status, r.description, r.address]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [dossier, q]);

  const violations = useMemo(() => {
    const rows = (dossier?.violations.rows || []) as ViolationRow[];
    if (!q) return rows;
    return rows.filter((r) =>
      [r.violation_type, r.status, r.detail, r.detail_full, r.source, r.opened]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [dossier, q]);

  const isdUrl = dossier?.isd_url || dossier?.violations.isd_url || "";
  const activityUrl = dossier?.permits_activity_url || "";

  return (
    <div className="relative flex flex-col h-full bg-gray-950 text-gray-100">
      <div className="px-5 py-4 border-b border-gray-800 shrink-0 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-red-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <ShieldAlert className="h-4 w-4" />
            Parcel dossier
          </div>
          <h2 className="text-lg font-bold text-white truncate">{address}</h2>
          <p className="text-xs text-gray-500 mt-0.5">Parcel {parcelId}</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white shrink-0"
            aria-label="Close dossier"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {loading && (
        <div className="flex-1 flex items-center justify-center text-blue-400 text-sm">
          <Loader2 className="h-5 w-5 animate-spin mr-2" />
          Loading ISD permits & violation records…
        </div>
      )}

      {error && !loading && (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <p className="text-red-400 text-sm mb-3">{error}</p>
          <button
            type="button"
            onClick={load}
            className="text-sm px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg hover:text-white"
          >
            Retry
          </button>
        </div>
      )}

      {dossier && !loading && (
        <>
          <div className="px-5 py-3 border-b border-gray-800 shrink-0 flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search permits, violations, trash, ISD…"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            {activityUrl && (
              <a
                href={activityUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center text-xs text-blue-400 hover:text-blue-300 no-underline"
              >
                <ExternalLink className="h-3.5 w-3.5 mr-1" />
                Permit activity (Excel)
              </a>
            )}
            {isdUrl && (
              <a
                href={isdUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center text-xs text-gray-500 hover:text-gray-300 no-underline"
              >
                ISD dept page
              </a>
            )}
          </div>

          <div className="px-5 pt-3 flex gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setTab("permits")}
              className={`text-sm px-3 py-1.5 rounded-lg border ${
                tab === "permits"
                  ? "bg-blue-600/20 border-blue-500/50 text-blue-300"
                  : "border-gray-700 text-gray-400"
              }`}
            >
              Permits ({dossier.permits.total_count})
              {dossier.permits.open_count > 0 && (
                <span className="ml-1 text-red-400">{dossier.permits.open_count} open</span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setTab("violations")}
              className={`text-sm px-3 py-1.5 rounded-lg border ${
                tab === "violations"
                  ? "bg-red-600/20 border-red-500/50 text-red-300"
                  : "border-gray-700 text-gray-400"
              }`}
            >
              Violations & 311 ({dossier.violations.rows.length})
              {dossier.violations.open_count > 0 && (
                <span className="ml-1 text-red-400">{dossier.violations.open_count} open</span>
              )}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-5 min-h-0">
            {tab === "permits" && (
              <>
                <p className="text-xs text-gray-500 mb-3">
                  Click a permit for full Towneye Gold details. Arlington OpenGov does not support
                  public paste lookup; use town Excel activity lists or call ISD to verify.
                </p>
                {permits.length === 0 ? (
                  <p className="text-gray-500 text-sm text-center py-12">
                    {q ? "No permits match your search." : "No building permits on file for this parcel."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                          <th className="pb-2 pr-3">Permit #</th>
                          <th className="pb-2 pr-3">Type</th>
                          <th className="pb-2 pr-3">Status</th>
                          <th className="pb-2 pr-3">Applied</th>
                          <th className="pb-2 pr-3">Description</th>
                          <th className="pb-2"> </th>
                        </tr>
                      </thead>
                      <tbody>
                        {permits.map((p, i) => (
                          <tr
                            key={`${p.permit_number}-${i}`}
                            onClick={() => setDetail({ kind: "permit", row: p })}
                            className="border-b border-gray-800/80 hover:bg-gray-900/80 cursor-pointer"
                          >
                            <td className="py-2.5 pr-3 font-mono text-xs text-blue-400 underline-offset-2 hover:underline">
                              {String(p.permit_number ?? "") || "—"}
                            </td>
                            <td className="py-2.5 pr-3 text-gray-300">{String(p.permit_type ?? "") || "—"}</td>
                            <td className="py-2.5 pr-3">
                              <span className={`text-xs px-2 py-0.5 rounded border ${statusClass(String(p.status || ""))}`}>
                                {String(p.status ?? "") || "—"}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-gray-400 text-xs">{String(p.application_date ?? "") || "—"}</td>
                            <td className="py-2.5 pr-3 text-gray-400 text-xs max-w-xs truncate">
                              {String(p.description || "—")}
                            </td>
                            <td className="py-2.5 text-xs text-blue-400 whitespace-nowrap">
                              {p.link_kind === "record"
                                ? "Open permit →"
                                : p.link_kind === "location"
                                  ? "Open property →"
                                  : "View details →"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}

            {tab === "violations" && (
              <>
                <p className="text-xs text-gray-500 mb-3 flex items-center gap-1">
                  <FileText className="h-3.5 w-3.5" />
                  {dossier.violations.note} Click a row for full detail and source link.
                </p>
                {violations.length === 0 ? (
                  <p className="text-gray-500 text-sm text-center py-12">
                    {q ? "No violations match your search." : "No code violations or 311 records for this parcel."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                          <th className="pb-2 pr-3">Type</th>
                          <th className="pb-2 pr-3">Status</th>
                          <th className="pb-2 pr-3">Opened</th>
                          <th className="pb-2 pr-3">Source</th>
                          <th className="pb-2 pr-3">Detail</th>
                          <th className="pb-2"> </th>
                        </tr>
                      </thead>
                      <tbody>
                        {violations.map((v, i) => (
                          <tr
                            key={`${v.violation_type}-${i}`}
                            onClick={() => setDetail({ kind: "violation", row: v })}
                            className="border-b border-gray-800/80 hover:bg-gray-900/80 cursor-pointer"
                          >
                            <td className="py-2.5 pr-3 text-blue-400 underline-offset-2 hover:underline">
                              {v.violation_type || "—"}
                            </td>
                            <td className="py-2.5 pr-3">
                              <span className={`text-xs px-2 py-0.5 rounded border ${statusClass(String(v.status || ""))}`}>
                                {v.status || "—"}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-gray-400 text-xs">{v.opened || "—"}</td>
                            <td className="py-2.5 pr-3 text-gray-500 text-xs">{v.source || "—"}</td>
                            <td className="py-2.5 pr-3 text-gray-400 text-xs max-w-sm truncate">
                              {v.detail || "—"}
                            </td>
                            <td className="py-2.5 text-xs text-blue-400 whitespace-nowrap">
                              {v.source === "311-seeclickfix" && v.detail_url
                                ? "Open source →"
                                : v.link_kind === "record" || v.link_kind === "location"
                                  ? "Open in OpenGov →"
                                  : "View details →"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}

      {detail && (
        <DetailDrawer
          detail={detail}
          onClose={() => setDetail(null)}
          activityUrl={activityUrl}
          isdUrl={isdUrl}
        />
      )}
    </div>
  );
}
