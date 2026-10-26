import Link from "next/link";

import { LiveStats } from "./landing/LiveStats";
import { PipelineHero } from "./landing/PipelineHero";

const MECHANISMS = [
  { k: "isolation", t: "Ephemeral sandbox per job", d: "--network none · read-only rootfs · cap-drop ALL · pids/memory/cpu cgroups · uid 65534" },
  { k: "queue", t: "Redis Streams consumer group", d: "XADD → XREADGROUP → XACK; crashed consumers' messages reclaimed with XAUTOCLAIM" },
  { k: "exactly-once effect", t: "Row-locked state machine", d: "QUEUED → PROCESSING succeeds for one worker; duplicate deliveries become no-ops" },
  { k: "fencing", t: "Lease + attempt token", d: "every write checks (worker_id, attempt); a stalled worker can never overwrite a retry" },
  { k: "realtime", t: "Server-Sent Events", d: "per-submission event stream with Last-Event-ID replay; DB polling fallback" },
  { k: "observability", t: "Structured logs + Prometheus", d: "request_id · submission_id · worker_id · attempt on every line; /metrics on API and workers" },
];

export default function Landing() {
  return (
    <main className="mx-auto max-w-[1600px] px-4">
      <section className="grid gap-10 border-b border-line py-14 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:py-20">
        <div className="flex flex-col justify-center">
          <div className="font-mono text-[12px] text-dim">
            <span className="text-accent">$</span> codeforge judge --distributed --sandboxed
          </div>
          <h1 className="mt-5 text-[clamp(2.2rem,4.3vw,3.9rem)] leading-[1.02] font-semibold tracking-[-0.035em] text-fg">
            Your code doesn&apos;t just run.
            <br />
            <span className="text-accent text-glow">It survives the judge.</span>
          </h1>
          <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-muted">
            CodeForge is an online judge built like infrastructure. Submissions are persisted, queued on Redis Streams,
            claimed by a pool of workers, compiled and executed inside throwaway Docker sandboxes with hard resource limits,
            and judged against hidden tests — with every step streamed back to your browser as it happens.
          </p>
          <div className="mt-8 flex flex-wrap gap-3 font-mono text-[13px]">
            <Link href="/problems" className="glow-accent bg-accent px-4 py-2 font-medium text-bg transition-transform hover:-translate-y-px">
              open problem set →
            </Link>
            <Link href="/architecture" className="border border-line-strong px-4 py-2 text-fg transition-colors hover:border-muted">
              read the architecture
            </Link>
            <Link href="/dashboard" className="px-2 py-2 text-muted transition-colors hover:text-fg">
              system dashboard
            </Link>
          </div>
        </div>
        <PipelineHero />
      </section>

      <LiveStats />

      <section className="py-14">
        <div className="mb-6 flex items-end justify-between">
          <h2 className="font-mono text-[12px] uppercase tracking-[0.18em] text-muted">what actually happens when you press submit</h2>
          <Link href="/architecture" className="font-mono text-[12px] text-dim hover:text-fg">/architecture →</Link>
        </div>
        <div className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {MECHANISMS.map((m) => (
            <div key={m.k} className="group bg-panel p-5 transition-colors hover:bg-panel-2">
              <div className="label group-hover:text-accent">{m.k}</div>
              <div className="mt-2 text-[15px] font-medium text-fg">{m.t}</div>
              <p className="mt-2 font-mono text-[12px] leading-relaxed text-muted">{m.d}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="flex flex-wrap justify-between gap-4 border-t border-line py-6 font-mono text-[11px] text-dim">
        <span>codeforge · fastapi · postgres · redis streams · docker · next.js</span>
        <span>educational execution engine — see SECURITY.md for the threat model</span>
      </footer>
    </main>
  );
}
