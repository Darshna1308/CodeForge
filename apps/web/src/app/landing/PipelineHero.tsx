"use client";

import { useEffect, useState } from "react";

const STEPS = [
  { name: "SUBMIT", cmd: "POST /submissions", note: "validate · persist row (CREATED) · Idempotency-Key" },
  { name: "QUEUE", cmd: "XADD cf:q:submit", note: "row → QUEUED · 202 Accepted returned immediately" },
  { name: "ISOLATE", cmd: "docker run --network none --read-only", note: "cap-drop ALL · pids 64 · memory cgroup · tmpfs /sandbox" },
  { name: "COMPILE", cmd: "g++ -std=gnu++17 -O2", note: "as uid 65534 · 15s budget · diagnostics captured" },
  { name: "EXECUTE", cmd: "cf-launch → execve(argv)", note: "RLIMIT_CPU · RLIMIT_AS · wall clock · output cap" },
  { name: "JUDGE", cmd: "normalize ⟶ compare", note: "per-test verdicts · first failure stops · fenced commit" },
];

/** Illustrative animation of the pipeline stages (not live data; live numbers are below). */
export function PipelineHero() {
  const [active, setActive] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setActive((a) => (a + 1) % (STEPS.length + 2)), 900);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="relative border border-line bg-panel/80">
      <div className="flex items-center justify-between border-b border-line px-3 py-2 font-mono text-[11px]">
        <span className="text-dim">pipeline.trace</span>
        <span className="text-dim">illustrative</span>
      </div>
      <ol className="relative p-2">
        <span className="absolute top-6 bottom-6 left-[27px] w-px bg-line" aria-hidden />
        {STEPS.map((s, i) => {
          const state = i < active ? "done" : i === active ? "active" : "idle";
          return (
            <li key={s.name} className={`relative grid grid-cols-[38px_1fr] items-start gap-2 px-1 py-2.5 transition-colors duration-300 ${state === "active" ? "bg-panel-2" : ""}`}>
              <span className={`relative z-10 mx-auto mt-0.5 grid h-[18px] w-[18px] place-items-center border font-mono text-[9px] transition-colors duration-300 ${
                state === "done" ? "border-accent/60 bg-bg text-accent" : state === "active" ? "border-blue bg-bg text-blue" : "border-line-strong bg-bg text-dim"}`}>
                {state === "done" ? "✓" : i + 1}
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className={`font-mono text-[12px] font-semibold tracking-[0.14em] ${state === "idle" ? "text-dim" : "text-fg"}`}>{s.name}</span>
                  <code className={`truncate font-mono text-[12px] ${state === "active" ? "text-blue" : state === "done" ? "text-accent/80" : "text-dim"}`}>{s.cmd}</code>
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-dim">{s.note}</div>
              </div>
            </li>
          );
        })}
        <li className="grid grid-cols-[38px_1fr] items-center gap-2 px-1 py-3">
          <span className={`relative z-10 mx-auto h-[18px] w-[18px] border transition-colors duration-300 ${active >= STEPS.length ? "border-accent bg-accent" : "border-line-strong bg-bg"}`} />
          <span className={`font-mono text-[13px] font-semibold tracking-[0.14em] transition-colors duration-300 ${active >= STEPS.length ? "text-accent text-glow" : "text-dim"}`}>
            ACCEPTED
          </span>
        </li>
      </ol>
    </div>
  );
}
