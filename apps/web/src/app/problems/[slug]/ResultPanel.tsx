import { VerdictBadge } from "@/components/Badges";
import { kb, ms, TONE_TEXT, VERDICT_SHORT, verdictTone } from "@/lib/format";
import type { SubmissionDetail } from "@/lib/types";

function Block({ label, text, tone = "text-fg" }: { label: string; text: string | null | undefined; tone?: string }) {
  if (text === null || text === undefined) return null;
  return (
    <div className="min-w-0">
      <div className="mb-1 font-mono text-[10px] text-dim">{label}</div>
      <pre className={`scrollbar-thin max-h-40 overflow-auto border border-line bg-panel-2 p-2 font-mono text-[12px] ${tone}`}>{text || <span className="text-dim">(empty)</span>}</pre>
    </div>
  );
}

/** Final verdict + per-test details. Hidden tests show verdict/time/memory only. */
export function ResultPanel({ detail }: { detail: SubmissionDetail }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <VerdictBadge verdict={detail.verdict} status={detail.status} size="lg" />
        {detail.tests_total !== null && <span className="font-mono text-[12px] text-muted">{detail.tests_passed}/{detail.tests_total} tests</span>}
        {detail.attempt > 1 && <span className="font-mono text-[11px] text-amber">recovered after {detail.attempt - 1} retry</span>}
      </div>
      {detail.error_message && detail.status === "INTERNAL_ERROR" && <Block label="internal error" text={detail.error_message} tone="text-red" />}
      {detail.compile_output && <Block label="compiler output" text={detail.compile_output} tone="text-red" />}
      <ul className="space-y-2">
        {detail.results.map((r) => {
          const tone = verdictTone(r.verdict);
          const showsData = r.input !== null && r.input !== undefined;
          return (
            <li key={r.ordinal} className="border border-line">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line bg-panel px-2 py-1.5 font-mono text-[12px]">
                <span className="text-dim">test {r.ordinal}{r.is_sample ? " · sample" : detail.mode === "RUN" ? " · custom" : " · hidden"}</span>
                <span className={TONE_TEXT[tone]}>{VERDICT_SHORT[r.verdict]} <span className="text-[11px]">{r.verdict.toLowerCase().replaceAll("_", " ")}</span></span>
                <span className="text-muted">cpu {ms(r.cpu_ms)}</span>
                <span className="text-muted">wall {ms(r.wall_ms)}</span>
                <span className="text-dim">mem {kb(r.memory_kb)}</span>
                {r.signal ? <span className="text-red">signal {r.signal}</span> : r.exit_code ? <span className="text-red">exit {r.exit_code}</span> : null}
              </div>
              {showsData || r.stdout !== null ? (
                <div className="grid gap-2 p-2 md:grid-cols-3">
                  <Block label="stdin" text={r.input} />
                  <Block label="expected" text={r.expected_output} tone="text-accent" />
                  <Block label="stdout" text={r.stdout} tone={tone === "ok" ? "text-fg" : "text-amber"} />
                  {r.stderr ? <div className="md:col-span-3"><Block label="stderr" text={r.stderr} tone="text-red" /></div> : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
