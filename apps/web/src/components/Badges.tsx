import { TONE_TEXT, VERDICT_LABEL, verdictTone } from "@/lib/format";
import type { Difficulty, SubmissionStatus, TestVerdict, Verdict } from "@/lib/types";

const DIFF: Record<Difficulty, string> = { EASY: "text-accent", MEDIUM: "text-amber", HARD: "text-red" };

export function DifficultyTag({ d }: { d: Difficulty }) {
  return <span className={`font-mono text-[11px] uppercase tracking-wider ${DIFF[d]}`}>{d.toLowerCase()}</span>;
}

export function VerdictBadge({ verdict, status, size = "sm" }: { verdict: Verdict | TestVerdict | null; status?: SubmissionStatus; size?: "sm" | "lg" }) {
  if (!verdict) {
    const pending = status && !["COMPLETED", "INTERNAL_ERROR", "CANCELLED"].includes(status);
    return (
      <span className={`inline-flex items-center gap-1.5 font-mono ${size === "lg" ? "text-base" : "text-[12px]"} ${status === "INTERNAL_ERROR" ? "text-red" : "text-muted"}`}>
        {pending && <span className="h-1.5 w-1.5 rounded-full bg-blue animate-pulse-dot" />}
        {status ? status.toLowerCase().replace("_", " ") : "—"}
      </span>
    );
  }
  const tone = verdictTone(verdict);
  return (
    <span className={`font-mono font-medium ${size === "lg" ? "text-lg" : "text-[12px]"} ${TONE_TEXT[tone]}`}>
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="border border-line-strong bg-panel-2 px-1 py-px font-mono text-[10px] text-muted">{children}</kbd>;
}
