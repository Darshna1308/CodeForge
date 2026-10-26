"use client";

import { kb, ms, TONE_TEXT, VERDICT_SHORT, verdictTone } from "@/lib/format";
import { STAGES, type PipelineState, type StageState } from "@/lib/pipeline";

const STAGE_STYLE: Record<StageState, string> = {
  idle: "border-line text-dim",
  active: "border-blue/70 text-blue",
  done: "border-accent/50 text-accent",
  fail: "border-red/60 text-red",
  skipped: "border-line text-dim line-through",
};

function StageRail({ stages }: { stages: PipelineState["stages"] }) {
  return (
    <ol className="grid grid-cols-7 gap-px border-b border-line bg-line">
      {STAGES.map((s, i) => {
        const st = stages[s.key];
        return (
          <li key={s.key} className="relative bg-panel px-2 py-2.5" title={`${s.label}: ${st}`}>
            <div className={`flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider ${STAGE_STYLE[st].split(" ").slice(1).join(" ")}`}>
              <span className={`grid h-3.5 w-3.5 shrink-0 place-items-center border text-[8px] ${STAGE_STYLE[st]} ${st === "active" ? "animate-pulse-dot" : ""}`}>
                {st === "done" ? "✓" : st === "fail" ? "×" : String(i + 1)}
              </span>
              <span className="truncate">{s.label}</span>
            </div>
            {st === "active" && <span className="absolute inset-x-0 bottom-0 h-px bg-blue" />}
            {st === "done" && <span className="absolute inset-x-0 bottom-0 h-px bg-accent/40" />}
            {st === "fail" && <span className="absolute inset-x-0 bottom-0 h-px bg-red" />}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Live view of one submission travelling through the judge. Every timing is
 * a value the worker measured and sent over SSE (or the DB snapshot).
 */
export function ExecutionVisualizer({ id, state, compact = false }: { id: number | null; state: PipelineState; compact?: boolean }) {
  const pending = state.totalTests !== null ? Math.max(0, state.totalTests - state.tests.length) : 0;
  const tone = verdictTone(state.verdict);
  return (
    <section className="flex min-h-0 flex-col border border-line bg-panel" aria-live="polite">
      <header className="flex items-center justify-between border-b border-line px-3 py-2">
        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span className="text-dim">SUBMISSION</span>
          <span className="text-fg">#{id !== null ? `CF-${id}` : "—"}</span>
          {state.workerId && <span className="hidden text-dim sm:inline">via <span className="text-muted">{state.workerId}</span></span>}
        </div>
        <div className="font-mono text-[11px]">
          {state.done ? (
            <span className={TONE_TEXT[state.status === "INTERNAL_ERROR" ? "bad" : tone]}>{state.status === "COMPLETED" ? state.verdict : state.status}</span>
          ) : state.status ? (
            <span className="text-blue">{state.status}<span className="animate-blink">_</span></span>
          ) : (
            <span className="text-dim">connecting…</span>
          )}
        </div>
      </header>
      <StageRail stages={state.stages} />
      <div className={`grid min-h-0 flex-1 ${compact ? "grid-cols-1" : "md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"}`}>
        <ol className="scrollbar-thin min-h-0 space-y-0.5 overflow-auto p-3 font-mono text-[12px] leading-5">
          {state.log.map((l) => (
            <li key={l.key} className="animate-fade-up">
              <span className="text-dim">› </span>
              <span className={{ ok: "text-accent", bad: "text-red", warn: "text-amber", info: "text-fg", dim: "text-dim" }[l.tone]}>{l.text}</span>
              {l.detail && <span className="text-dim"> · {l.detail}</span>}
            </li>
          ))}
          {state.tests.length > 0 && (
            <li className="animate-fade-up">
              <span className="text-dim">› </span>
              <span className="text-fg">TESTS</span>
              <span className="text-dim"> · {state.tests.filter((t) => t.verdict === "ACCEPTED" || t.verdict === "EXECUTED").length}/{state.totalTests ?? "?"} passed</span>
            </li>
          )}
          {state.done && state.status === "COMPLETED" && (
            <li className="pt-1 text-muted">
              TOTAL {ms(state.totalMs)} · peak cpu {ms(state.runtimeMs)} · peak mem {kb(state.memoryKb)}
            </li>
          )}
          {state.error && <li className="text-red">{state.error}</li>}
          {!state.done && <li className="text-dim"><span className="animate-blink">▍</span></li>}
        </ol>
        <div className="scrollbar-thin min-h-0 overflow-auto border-t border-line p-3 md:border-t-0 md:border-l">
          <div className="label mb-2">test cases</div>
          <ul className="space-y-px font-mono text-[12px]">
            {state.tests.map((t) => {
              const tt = verdictTone(t.verdict);
              return (
                <li key={t.index} className="grid animate-fade-up grid-cols-[3.5rem_2.5rem_1fr_1fr] items-center gap-2 px-1 py-0.5 hover:bg-panel-2">
                  <span className="text-dim">#{String(t.index).padStart(2, "0")}{t.sample ? <span className="text-blue">ˢ</span> : ""}</span>
                  <span className={TONE_TEXT[tt]}>{t.verdict === "ACCEPTED" ? "✓" : VERDICT_SHORT[t.verdict]}</span>
                  <span className="text-muted">{ms(t.cpu_ms)}</span>
                  <span className="text-dim">{kb(t.memory_kb)}</span>
                </li>
              );
            })}
            {Array.from({ length: state.done ? 0 : Math.min(pending, 40) }).map((_, i) => (
              <li key={`p${i}`} className="grid grid-cols-[3.5rem_2.5rem_1fr_1fr] gap-2 px-1 py-0.5 text-dim/60">
                <span>#{String(state.tests.length + i + 1).padStart(2, "0")}</span><span>·</span><span>—</span><span />
              </li>
            ))}
          </ul>
          {state.tests.length === 0 && state.done && (
            <p className="font-mono text-[12px] text-dim">no tests executed</p>
          )}
        </div>
      </div>
    </section>
  );
}
