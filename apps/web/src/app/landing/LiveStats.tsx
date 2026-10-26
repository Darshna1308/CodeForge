"use client";

import { useEffect, useState } from "react";

import { Stat } from "@/components/Shell";
import { api } from "@/lib/api";

interface Overview {
  problems: number; users: number; submissions: number; executions: number; accepted: number;
  acceptance_rate: number | null; median_runtime_ms: number | null; active_workers: number | null; languages: string[];
}

/** Numbers read from this deployment's database and Redis; "—" when unavailable, never invented. */
export function LiveStats() {
  const [d, setD] = useState<Overview | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    api<Overview>("/stats/overview").then(setD).catch(() => setErr(true));
  }, []);
  const v = (x: number | null | undefined, suffix = "") => (x === null || x === undefined ? "—" : `${x}${suffix}`);
  return (
    <section className="py-8">
      <div className="mb-3 flex items-center gap-2 font-mono text-[11px] text-dim">
        <span className={`h-1.5 w-1.5 rounded-full ${err ? "bg-red" : d ? "bg-accent animate-pulse-dot" : "bg-dim"}`} />
        {err ? "live stats unavailable (api unreachable)" : "live from this deployment"}
      </div>
      <div className="grid grid-cols-2 gap-px border border-line bg-line md:grid-cols-3 lg:grid-cols-6">
        <Stat label="problems" value={v(d?.problems)} hint={d ? d.languages.join(" · ") : undefined} />
        <Stat label="judged submissions" value={v(d?.submissions)} hint={d ? `${d.executions} total executions` : undefined} />
        <Stat label="accepted" value={v(d?.accepted)} tone="accent" />
        <Stat label="acceptance rate" value={v(d?.acceptance_rate, "%")} />
        <Stat label="median runtime" value={v(d?.median_runtime_ms, "ms")} hint="cpu time, all executions" />
        <Stat label="workers online" value={v(d?.active_workers)} tone={d?.active_workers ? "accent" : "amber"} hint="live heartbeats" />
      </div>
    </section>
  );
}
