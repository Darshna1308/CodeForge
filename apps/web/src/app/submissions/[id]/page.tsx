"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { VerdictBadge } from "@/components/Badges";
import { ExecutionVisualizer } from "@/components/ExecutionVisualizer";
import { PageHeader, Panel } from "@/components/Shell";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { kb, ms } from "@/lib/format";
import { useSubmissionStream } from "@/lib/useSubmissionStream";
import type { SubmissionDetail } from "@/lib/types";

import { ResultPanel } from "../../problems/[slug]/ResultPanel";

export default function SubmissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: raw } = use(params);
  const id = Number(raw);
  const { user, loading } = useAuth();
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api<SubmissionDetail>(`/submissions/${id}`).then(setDetail).catch((e: ApiError) => setError(e.message));
  }, [id, user]);

  const pipeline = useSubmissionStream(user && Number.isFinite(id) ? id : null, (d) => d && setDetail(d));

  if (!loading && !user) {
    return <main className="mx-auto max-w-[1600px] px-4 py-8 font-mono text-[13px] text-muted"><Link href={`/login?next=/submissions/${id}`} className="text-accent">log in</Link> to view this submission.</main>;
  }
  if (error) return <main className="mx-auto max-w-[1600px] px-4 py-8 font-mono text-[13px] text-red">{error}</main>;
  if (!detail) return <main className="px-4 py-20 text-center font-mono text-sm text-dim">loading<span className="animate-blink">_</span></main>;

  return (
    <main className="mx-auto max-w-[1600px] px-4 py-8">
      <PageHeader path={`inspect ${detail.display_id}`} title={detail.problem_title}>
        <div className="flex items-center gap-4 font-mono text-[12px]">
          <VerdictBadge verdict={detail.verdict} status={detail.status} size="lg" />
          <Link href={`/problems/${detail.problem_slug}`} className="text-muted hover:text-fg">open problem →</Link>
        </div>
      </PageHeader>

      <div className="mt-5 grid grid-cols-2 gap-px border border-line bg-line font-mono text-[12px] md:grid-cols-6">
        {[
          ["language", detail.language], ["mode", detail.mode.toLowerCase()], ["tests", detail.tests_total !== null ? `${detail.tests_passed}/${detail.tests_total}` : "—"],
          ["peak cpu", ms(detail.runtime_ms)], ["peak memory", kb(detail.memory_kb)], ["compile", ms(detail.compile_ms)],
        ].map(([k, v]) => (
          <div key={k} className="bg-panel px-3 py-2"><div className="label">{k}</div><div className="mt-0.5 text-fg">{v}</div></div>
        ))}
      </div>

      <div className="mt-4 h-[320px]"><ExecutionVisualizer id={id} state={pipeline} /></div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Panel title="results"><ResultPanel detail={detail} /></Panel>
        <div className="space-y-4">
          <Panel title="state machine transitions" right={<span className="font-mono text-[10px] text-dim">submission_transitions</span>}>
            <ol className="space-y-1 font-mono text-[12px]">
              {detail.transitions?.map((t, i) => (
                <li key={i} className="grid grid-cols-[6.5rem_1fr_auto] gap-2">
                  <span className="text-dim">{new Date(t.at).toISOString().slice(11, 23)}</span>
                  <span><span className="text-dim">{t.from_status ?? "∅"} →</span> <span className="text-fg">{t.to_status}</span></span>
                  <span className="text-dim">{t.actor}{t.attempt ? ` #${t.attempt}` : ""}</span>
                </li>
              ))}
            </ol>
          </Panel>
          <Panel title="execution attempts" right={<span className="font-mono text-[10px] text-dim">execution_attempts</span>}>
            <ul className="space-y-1.5 font-mono text-[12px]">
              {detail.attempts.map((a) => (
                <li key={a.attempt_no} className="grid grid-cols-[2rem_1fr_auto] gap-2">
                  <span className="text-dim">#{a.attempt_no}</span>
                  <span className="text-muted">{a.worker_id} · queue {ms(a.queue_wait_ms)} · sandbox {ms(a.sandbox_start_ms)} · total {ms(a.total_ms)}{a.error ? <span className="text-red"> · {a.error}</span> : null}</span>
                  <span className={a.outcome === "SUCCEEDED" ? "text-accent" : a.outcome === "RUNNING" ? "text-blue" : "text-amber"}>{a.outcome.toLowerCase()}</span>
                </li>
              ))}
              {detail.attempts.length === 0 && <li className="text-dim">not claimed yet</li>}
            </ul>
          </Panel>
          {detail.source_code && (
            <Panel title="source">
              <pre className="scrollbar-thin max-h-[420px] overflow-auto font-mono text-[12px] leading-5 text-muted">{detail.source_code}</pre>
            </Panel>
          )}
        </div>
      </div>
    </main>
  );
}
