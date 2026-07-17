"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BookOpen,
  Copy,
  ExternalLink,
  Filter,
  Loader2,
  Scale,
  Search,
  ArrowRight,
} from "lucide-react";
import {
  searchPrecedents,
  type PrecedentResult,
  type PrecedentSearchResponse,
} from "@/lib/api";
import { useSharedParcel } from "@/hooks/useSharedParcel";

function decisionClass(decision?: string) {
  const d = (decision || "").toUpperCase();
  if (d.includes("APPROVED") || d.includes("ON_FILE")) {
    return "text-emerald-300 bg-emerald-500/10 border-emerald-500/30";
  }
  if (d.includes("DENIED") || d.includes("WITHDRAWN")) {
    return "text-red-300 bg-red-500/10 border-red-500/30";
  }
  if (d.includes("CONTINUED") || d.includes("VERIFY") || d.includes("HEARING")) {
    return "text-amber-200 bg-amber-500/10 border-amber-500/30";
  }
  if (d.includes("RESEARCH")) {
    return "text-blue-300 bg-blue-500/10 border-blue-500/30";
  }
  return "text-gray-300 bg-gray-800 border-gray-700";
}

function sourceBadge(kind?: string) {
  if (kind === "gold_civic_minutes") return "Gold minutes";
  if (kind === "agenda_index") return "Agenda index";
  if (kind === "research_note") return "Research note";
  if (kind === "pilot_research") return "Pilot research";
  return kind || "Source";
}

function CopyCite({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1600);
        } catch {
          /* ignore */
        }
      }}
      className="inline-flex items-center gap-1.5 text-xs text-gray-300 border border-gray-600 hover:border-gray-400 rounded-lg px-2.5 py-1.5"
    >
      <Copy className="h-3.5 w-3.5" />
      {copied ? "Copied" : "Copy for memo"}
    </button>
  );
}

function ResultCard({ row }: { row: PrecedentResult }) {
  return (
    <article className="rounded-xl border border-gray-800 bg-gray-900/80 p-4 space-y-3 hover:border-gray-700 transition-colors">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-white font-mono">
              {row.docket || "—"}
            </h3>
            <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${decisionClass(row.decision)}`}>
              {row.decision || "—"}
            </span>
            <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border border-gray-700 text-gray-400">
              {sourceBadge(row.source_kind)}
            </span>
          </div>
          <p className="text-sm text-gray-200">{row.address || "—"}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {row.board}
            {row.hearing_date ? ` · ${row.hearing_date}` : ""}
            {row.neighborhood ? ` · ${row.neighborhood}` : ""}
          </p>
        </div>
        {row.relevance_score != null && row.relevance_score > 0 && (
          <div className="text-right shrink-0">
            <p className="text-[10px] uppercase tracking-wider text-gray-500">Relevance</p>
            <p className="text-sm text-blue-300 font-medium">{row.relevance_score}</p>
            <p className="text-[11px] text-gray-500 max-w-[140px]">{row.relevance_reason}</p>
          </div>
        )}
      </div>

      {(row.relief_types?.length || 0) > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {row.relief_types!.map((r) => (
            <span
              key={r}
              className="text-[11px] px-2 py-0.5 rounded border border-blue-500/30 text-blue-300 bg-blue-500/5"
            >
              {r.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      {row.summary && (
        <p className="text-sm text-gray-300 leading-relaxed">{row.summary}</p>
      )}

      {(row.zbl_sections?.length || 0) > 0 && (
        <p className="text-xs text-gray-500 font-mono">
          Cite sections: {row.zbl_sections!.join(" · ")}
        </p>
      )}

      {row.memo_tip && (
        <p className="text-xs text-amber-200/80 leading-relaxed border-l-2 border-amber-500/40 pl-3">
          {row.memo_tip}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        {row.citation && <CopyCite text={row.citation} />}
        {row.source_url && (
          <a
            href={row.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 no-underline"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Official source
          </a>
        )}
        {!row.cite_ready && (
          <span className="text-[11px] text-gray-500">Verify before citing</span>
        )}
      </div>
    </article>
  );
}

export default function PrecedentsPage() {
  const [parcel] = useSharedParcel();
  const townSlug = parcel?.town_slug || "arlington-ma";
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [board, setBoard] = useState("all");
  const [relief, setRelief] = useState("all");
  const [decision, setDecision] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState<PrecedentSearchResponse | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 280);
    return () => window.clearTimeout(t);
  }, [query]);

  const runSearch = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await searchPrecedents({
        town_slug: townSlug,
        q: debouncedQuery.trim() || undefined,
        board: board === "all" ? undefined : board,
        relief: relief === "all" ? undefined : relief,
        decision: decision === "all" ? undefined : decision,
        parcel_id: parcel?.parcel_id || undefined,
        address: parcel?.address || undefined,
        limit: 50,
      });
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [townSlug, debouncedQuery, board, relief, decision, parcel?.parcel_id, parcel?.address]);

  useEffect(() => {
    runSearch();
  }, [runSearch]);

  const facets = data?.facets;
  const results = data?.results || [];

  const stats = useMemo(() => {
    if (!data) return null;
    return [
      { label: "Indexed", value: data.total_indexed },
      { label: "Showing", value: data.result_count },
      { label: "Agenda corpus", value: data.corpus_count },
      { label: "Gold minutes", value: data.gold_minutes_count },
    ];
  }, [data]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-gray-950 text-gray-100">
      <div className="px-6 py-5 border-b border-gray-800 shrink-0">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-3xl">
            <h1 className="text-2xl font-bold text-white mb-2">Precedent Search</h1>
            <p className="text-gray-400 text-sm leading-relaxed">
              Zoning Attorney research surface — find nearby ZBA, Redevelopment Board, and
              Conservation matters, copy memo-ready locators, and jump to official town sources.
            </p>
            {parcel?.address && (
              <p className="text-xs text-blue-300/90 mt-2">
                Scoped to {parcel.address}
                {parcel.parcel_id ? (
                  <span className="text-gray-500 font-mono"> · {parcel.parcel_id}</span>
                ) : null}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/zoning"
              className="inline-flex items-center gap-1.5 text-xs text-gray-300 border border-gray-700 rounded-lg px-3 py-2 no-underline hover:border-gray-500"
            >
              <Scale className="h-3.5 w-3.5" />
              Zoning
            </Link>
            <Link
              href="/civic-entitlements"
              className="inline-flex items-center gap-1.5 text-xs text-gray-300 border border-gray-700 rounded-lg px-3 py-2 no-underline hover:border-gray-500"
            >
              Entitlements
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
          <div className="space-y-4 min-w-0">
            <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4 space-y-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search docket, street, relief type, board…"
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg pl-9 pr-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                <Filter className="h-3.5 w-3.5 text-gray-500" />
                <select
                  value={board}
                  onChange={(e) => setBoard(e.target.value)}
                  className="bg-gray-950 border border-gray-700 rounded-lg text-xs text-gray-200 px-2 py-1.5"
                >
                  <option value="all">All boards</option>
                  {(facets?.boards || []).map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
                <select
                  value={relief}
                  onChange={(e) => setRelief(e.target.value)}
                  className="bg-gray-950 border border-gray-700 rounded-lg text-xs text-gray-200 px-2 py-1.5"
                >
                  <option value="all">All relief types</option>
                  {(facets?.relief_types || []).map((r) => (
                    <option key={r} value={r}>
                      {r.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
                <select
                  value={decision}
                  onChange={(e) => setDecision(e.target.value)}
                  className="bg-gray-950 border border-gray-700 rounded-lg text-xs text-gray-200 px-2 py-1.5"
                >
                  <option value="all">All statuses</option>
                  {(facets?.decisions || []).map((d) => (
                    <option key={d} value={d}>
                      {d.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
              {stats && (
                <div className="flex flex-wrap gap-3 pt-1">
                  {stats.map((s) => (
                    <div key={s.label} className="text-xs text-gray-500">
                      <span className="text-gray-300 font-medium">{s.value}</span> {s.label}
                    </div>
                  ))}
                  {data?.data_tier && (
                    <div className="text-xs text-gray-500">
                      Tier <span className="text-blue-300 font-mono">{data.data_tier}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {data?.disclaimer && (
              <div className="flex gap-3 p-3 rounded-xl border border-amber-500/30 bg-amber-950/20">
                <AlertTriangle className="text-amber-500 w-4 h-4 shrink-0 mt-0.5" />
                <p className="text-xs text-amber-100/90 leading-relaxed">{data.disclaimer}</p>
              </div>
            )}

            {loading && (
              <div className="flex items-center justify-center py-16 text-blue-400 text-sm">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                Searching board precedents…
              </div>
            )}

            {error && !loading && (
              <div className="rounded-xl border border-red-500/30 bg-red-950/20 p-4 text-sm text-red-300">
                {error}
              </div>
            )}

            {!loading && !error && results.length === 0 && (
              <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-10 text-center">
                <BookOpen className="h-8 w-8 text-gray-600 mx-auto mb-3" />
                <p className="text-sm text-gray-300 mb-1">No matching precedents</p>
                <p className="text-xs text-gray-500 max-w-md mx-auto">
                  Clear filters or open an official ZBA agenda source from the right rail.
                </p>
              </div>
            )}

            {!loading && results.length > 0 && (
              <div className="space-y-3">
                {results.map((row) => (
                  <ResultCard key={row.id} row={row} />
                ))}
              </div>
            )}
          </div>

          <aside className="space-y-4 lg:sticky lg:top-6 self-start">
            <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
                Official sources
              </h2>
              <ul className="space-y-3">
                {(data?.official_sources || []).map((src) => (
                  <li key={src.url}>
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-400 hover:text-blue-300 no-underline inline-flex items-start gap-1.5"
                    >
                      <ExternalLink className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                      <span>
                        {src.label}
                        {src.note && (
                          <span className="block text-[11px] text-gray-500 font-normal mt-0.5">
                            {src.note}
                          </span>
                        )}
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            {(data?.research_tips?.length || 0) > 0 && (
              <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
                  Research tips
                </h2>
                <ul className="space-y-2">
                  {data!.research_tips.map((tip) => (
                    <li key={tip} className="text-xs text-gray-400 leading-relaxed pl-3 border-l border-gray-700">
                      {tip}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4 text-xs text-gray-500 leading-relaxed">
              Bundle note: live civic-minutes Gold ingest upgrades this index automatically.
              Until then, agenda-index rows + official links keep research moving without
              fabricated holdings.
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
