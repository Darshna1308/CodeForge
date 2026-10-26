"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";

import { HBars, HourlyBars } from "@/components/Charts";
import { PageHeader, Panel, Stat } from "@/components/Shell";
import { api, ApiError } from "@/lib/api";
import { ago, ms } from "@/lib/format";

interface Worker { worker_id: string; host: string; concurrency: number; busy: number; handled: number; started_at: number; last_seen: number }
interface SystemStats {
  live: {
    available: boolean;
    queue?: { run: { backlog: number; in_flight: number }; submit: { backlog: number; in_flight: number }; dead: { total: number } };
    workers?: Worker[];
    counters?: { jobs_completed: number; jobs_failed: number; duplicate_deliveries: number; redelivered: number };
  };
  db: {
    status_counts: Record<string, number>; in_progress: number; verdicts: Record<string, number>; attempt_outcomes: Record<string, number>;
    latency_24h: { jobs: number; avg_total_ms: number | null; avg_queue_wait_ms: number | null; avg_sandbox_start_ms: number | null; avg_compile_ms: number | null; p95_total_ms: number | null };
    submissions_per_hour: { hour: string; total: number; accepted: number }[];
    recent_jobs: { submission_id: number; display_id: string; attempt: number; worker_id: string; outcome: string; total_ms: number | null; queue_wait_ms: number | null; started_at: string; verdict: string | null; language: string }[];
  };
  generated_at: string;
}

const VERDICT_COLOR: Record<string, string> = {
  ACCEPTED: "bg-accent", EXECUTED: "bg-accent/50", WRONG_ANSWER: "bg-red", RUNTIME_ERROR: "bg-red/70", COMPILATION_ERROR: "bg-violet",
  TIME_LIMIT_EXCEEDED: "bg-amber", MEMORY_LIMIT_EXCEEDED: "bg-amber/70", OUTPUT_LIMIT_EXCEEDED: "bg-amber/50",
};

export default function Dashboard() {
  const [s, setS] = useState<SystemStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<number>(0);

  useEffect(() => {
    const load = () => api<SystemStats>("/stats/system").then((d) => { setS(d); setError(null); setUpdated(Date.now()); }).catch((e: ApiError) => setError(e.message));
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const live = s?.live;
  const q = live?.queue;
  const n = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v);
  return (
    <main className="mx-auto max-w-[1600px] px-4 py-8">
      <PageHeader path="watch -n3 codeforge status" title="System dashboard">
        <div className="flex items-center gap-2 font-mono text-[11px] text-dim">
          <span className={`h-1.5 w-1.5 rounded-full ${error ? "bg-red" : "bg-accent animate-pulse-dot"}`} />
          {error ? error : updated ? `refreshed ${ago(new Date(updated).toISOString())} · polling every 3s` : "connecting"}
          <a href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/metrics`} className="ml-3 text-muted hover:text-fg">/metrics ↗</a>
        </div>
      </PageHeader>

      {live && !live.available && (
        <p className="mt-4 border border-amber/40 bg-amber/5 px-3 py-2 font-mono text-[12px] text-amber">Redis is unreachable: live queue and worker data unavailable. Database aggregates below are still real.</p>
      )}

      <div className="mt-5 grid grid-cols-2 gap-px border border-line bg-line md:grid-cols-4 xl:grid-cols-8">
        <Stat label="queue · submit" value={n(q?.submit.backlog)} hint={q ? `${q.submit.in_flight} in flight` : "unavailable"} />
        <Stat label="queue · run" value={n(q?.run.backlog)} hint={q ? `${q.run.in_flight} in flight` : "unavailable"} />
        <Stat label="active workers" value={n(live?.workers?.length)} tone={live?.workers?.length ? "accent" : "amber"}
          hint={live?.workers ? `${live.workers.reduce((a, w) => a + w.busy, 0)}/${live.workers.reduce((a, w) => a + w.concurrency, 0)} slots busy` : undefined} />
        <Stat label="jobs completed" value={n(live?.counters?.jobs_completed)} tone="accent" hint="worker counter" />
        <Stat label="jobs failed" value={n(live?.counters?.jobs_failed)} tone={live?.counters?.jobs_failed ? "red" : "fg"} hint="infra failures, retried" />
        <Stat label="dead-lettered" value={n(q?.dead.total)} tone={q?.dead.total ? "red" : "fg"} />
        <Stat label="avg job latency" value={ms(s?.db.latency_24h.avg_total_ms !== null && s?.db.latency_24h.avg_total_ms !== undefined ? Math.round(s.db.latency_24h.avg_total_ms) : null)}
          hint={`p95 ${ms(s?.db.latency_24h.p95_total_ms != null ? Math.round(s.db.latency_24h.p95_total_ms) : null)} · 24h`} />
        <Stat label="avg queue wait" value={ms(s?.db.latency_24h.avg_queue_wait_ms != null ? Math.round(s.db.latency_24h.avg_queue_wait_ms) : null)}
          hint={`sandbox start ${ms(s?.db.latency_24h.avg_sandbox_start_ms != null ? Math.round(s.db.latency_24h.avg_sandbox_start_ms) : null)}`} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Panel title="submissions per hour · last 24h" right={<span className="font-mono text-[10px] text-dim"><span className="text-accent">■</span> accepted <span className="ml-2 text-line-strong">■</span> other</span>}>
          {s ? <HourlyBars data={s.db.submissions_per_hour} /> : <div className="h-36" />}
        </Panel>
        <Panel title="verdict distribution">
          <HBars rows={Object.entries(s?.db.verdicts ?? {}).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value }))}
            colorFor={(l) => VERDICT_COLOR[l] ?? "bg-muted"} />
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <div className="space-y-4">
          <Panel title="worker pool" right={<span className="font-mono text-[10px] text-dim">redis heartbeats · ttl 15s</span>}>
            <ul className="space-y-2 font-mono text-[12px]">
              {live?.workers?.map((w) => (
                <li key={w.worker_id} className="border border-line bg-panel-2 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-fg"><span className={`mr-2 inline-block h-1.5 w-1.5 rounded-full ${w.busy ? "bg-blue animate-pulse-dot" : "bg-accent"}`} />{w.worker_id}</span>
                    <span className="text-dim">seen {Math.max(0, Math.round(Date.now() / 1000 - w.last_seen))}s ago</span>
                  </div>
                  <div className="mt-1.5 flex items-center gap-2">
                    {Array.from({ length: w.concurrency }).map((_, i) => (
                      <span key={i} className={`h-2 flex-1 ${i < w.busy ? "bg-blue" : "bg-line-strong"}`} title={i < w.busy ? "busy" : "idle"} />
                    ))}
                  </div>
                  <div className="mt-1 text-[11px] text-dim">{w.busy}/{w.concurrency} busy · {w.handled} jobs handled · up {ago(new Date(w.started_at * 1000).toISOString()).replace(" ago", "")}</div>
                </li>
              ))}
              {live?.available && live.workers?.length === 0 && <li className="text-amber">no workers alive — jobs will wait in the queue</li>}
            </ul>
          </Panel>
          <Panel title="delivery semantics">
            <dl className="grid grid-cols-2 gap-y-1.5 font-mono text-[12px]">
              <dt className="text-muted">duplicate deliveries skipped</dt><dd className="text-right text-fg">{n(live?.counters?.duplicate_deliveries)}</dd>
              <dt className="text-muted">messages reclaimed (XAUTOCLAIM)</dt><dd className="text-right text-fg">{n(live?.counters?.redelivered)}</dd>
              {Object.entries(s?.db.attempt_outcomes ?? {}).map(([k, v]) => (
                <Fragment key={k}><dt className="text-muted">attempts {k.toLowerCase()}</dt><dd className="text-right text-fg">{v}</dd></Fragment>
              ))}
              <dt className="text-muted">submissions in progress</dt><dd className="text-right text-fg">{n(s?.db.in_progress)}</dd>
            </dl>
          </Panel>
        </div>
        <Panel title="recent jobs" right={<span className="font-mono text-[10px] text-dim">execution_attempts</span>}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] font-mono text-[12px]">
              <thead><tr className="text-left">{["job", "worker", "lang", "outcome", "verdict", "queue", "total", "when"].map((h) => <th key={h} className="label pb-2 font-normal">{h}</th>)}</tr></thead>
              <tbody>
                {s?.db.recent_jobs.map((j) => (
                  <tr key={`${j.submission_id}-${j.attempt}`} className="border-t border-line/60">
                    <td className="py-1.5"><Link href={`/submissions/${j.submission_id}`} className="text-muted hover:text-accent">{j.display_id}</Link>{j.attempt > 1 && <span className="text-amber"> #{j.attempt}</span>}</td>
                    <td className="text-dim">{j.worker_id}</td>
                    <td className="text-muted">{j.language}</td>
                    <td className={j.outcome === "SUCCEEDED" ? "text-accent" : j.outcome === "RUNNING" ? "text-blue" : "text-amber"}>{j.outcome.toLowerCase()}</td>
                    <td className="text-muted">{j.verdict?.toLowerCase().replaceAll("_", " ") ?? "—"}</td>
                    <td className="text-dim">{ms(j.queue_wait_ms)}</td>
                    <td className="text-fg">{ms(j.total_ms)}</td>
                    <td className="text-dim">{ago(j.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {s && s.db.recent_jobs.length === 0 && <p className="py-4 text-center font-mono text-[12px] text-dim">no jobs yet</p>}
          </div>
        </Panel>
      </div>
      <p className="mt-4 font-mono text-[11px] text-dim">All values are measured: queue depth via XINFO GROUPS, workers via heartbeat keys, latencies and verdicts from PostgreSQL. Missing data is shown as “—”.</p>
    </main>
  );
}
