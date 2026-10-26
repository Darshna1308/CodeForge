"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { VerdictBadge } from "@/components/Badges";
import { PageHeader } from "@/components/Shell";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, kb, ms } from "@/lib/format";
import type { Page, SubmissionSummary } from "@/lib/types";

export default function SubmissionsPage() {
  const { user, loading } = useAuth();
  const [page, setPage] = useState(1);
  const [includeRuns, setIncludeRuns] = useState(false);
  const [data, setData] = useState<Page<SubmissionSummary> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    const load = () =>
      api<Page<SubmissionSummary>>(`/submissions?page=${page}&page_size=25&include_runs=${includeRuns}`)
        .then(setData)
        .catch((e: ApiError) => setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [user, page, includeRuns]);

  if (!loading && !user) {
    return (
      <main className="mx-auto max-w-[1600px] px-4 py-8">
        <PageHeader path="cat ~/.submissions" title="Submissions" />
        <p className="mt-6 font-mono text-[13px] text-muted"><Link href="/login?next=/submissions" className="text-accent">log in</Link> to see your submission history.</p>
      </main>
    );
  }
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <main className="mx-auto max-w-[1600px] px-4 py-8">
      <PageHeader path="cat ~/.submissions" title="Submission history">
        <label className="flex items-center gap-2 font-mono text-[12px] text-muted">
          <input type="checkbox" checked={includeRuns} onChange={(e) => { setPage(1); setIncludeRuns(e.target.checked); }} className="accent-[var(--color-accent)]" />
          include “run code” executions
        </label>
      </PageHeader>
      {error && <p className="mt-4 font-mono text-[12px] text-red">{error}</p>}
      <div className="mt-5 overflow-x-auto border border-line">
        <table className="w-full min-w-[820px] border-collapse font-mono text-[12.5px]">
          <thead>
            <tr className="border-b border-line bg-panel text-left">
              {["id", "problem", "verdict", "lang", "mode", "tests", "cpu", "memory", "attempt", "submitted"].map((h) => (
                <th key={h} className="label px-3 py-2 font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.items.map((s) => (
              <tr key={s.id} className="border-b border-line/70 last:border-0 hover:bg-panel-2">
                <td className="px-3 py-2"><Link href={`/submissions/${s.id}`} className="text-muted hover:text-accent">{s.display_id}</Link></td>
                <td className="px-3 py-2"><Link href={`/problems/${s.problem_slug}`} className="font-sans text-[13.5px] text-fg hover:text-accent">{s.problem_title}</Link></td>
                <td className="px-3 py-2"><VerdictBadge verdict={s.verdict} status={s.status} /></td>
                <td className="px-3 py-2 text-muted">{s.language}</td>
                <td className="px-3 py-2 text-dim">{s.mode.toLowerCase()}</td>
                <td className="px-3 py-2 text-muted">{s.tests_total !== null ? `${s.tests_passed}/${s.tests_total}` : "—"}</td>
                <td className="px-3 py-2 text-muted">{ms(s.runtime_ms)}</td>
                <td className="px-3 py-2 text-dim">{kb(s.memory_kb)}</td>
                <td className={`px-3 py-2 ${s.attempt > 1 ? "text-amber" : "text-dim"}`}>{s.attempt}</td>
                <td className="px-3 py-2 text-dim" title={s.created_at}>{ago(s.created_at)}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && <tr><td colSpan={10} className="px-3 py-8 text-center text-dim">nothing here yet — <Link className="text-accent" href="/problems">solve something</Link></td></tr>}
          </tbody>
        </table>
      </div>
      {data && pages > 1 && (
        <div className="mt-3 flex items-center gap-3 font-mono text-[12px] text-muted">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="disabled:opacity-30 hover:text-fg">← prev</button>
          <span>page {page} / {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="disabled:opacity-30 hover:text-fg">next →</button>
          <span className="text-dim">{data.total} total</span>
        </div>
      )}
    </main>
  );
}
