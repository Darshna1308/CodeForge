import type { TestVerdict, Verdict } from "./types";

export const VERDICT_LABEL: Record<Verdict | TestVerdict, string> = {
  ACCEPTED: "Accepted",
  WRONG_ANSWER: "Wrong Answer",
  COMPILATION_ERROR: "Compilation Error",
  RUNTIME_ERROR: "Runtime Error",
  TIME_LIMIT_EXCEEDED: "Time Limit Exceeded",
  MEMORY_LIMIT_EXCEEDED: "Memory Limit Exceeded",
  OUTPUT_LIMIT_EXCEEDED: "Output Limit Exceeded",
  EXECUTED: "Executed",
  SKIPPED: "Skipped",
};

export const VERDICT_SHORT: Record<Verdict | TestVerdict, string> = {
  ACCEPTED: "AC", WRONG_ANSWER: "WA", COMPILATION_ERROR: "CE", RUNTIME_ERROR: "RE",
  TIME_LIMIT_EXCEEDED: "TLE", MEMORY_LIMIT_EXCEEDED: "MLE", OUTPUT_LIMIT_EXCEEDED: "OLE", EXECUTED: "OK", SKIPPED: "—",
};

export function verdictTone(v: string | null | undefined): "ok" | "bad" | "warn" | "neutral" {
  if (!v) return "neutral";
  if (v === "ACCEPTED" || v === "EXECUTED") return "ok";
  if (v === "SKIPPED") return "neutral";
  if (v === "TIME_LIMIT_EXCEEDED" || v === "MEMORY_LIMIT_EXCEEDED" || v === "OUTPUT_LIMIT_EXCEEDED") return "warn";
  return "bad";
}

export const TONE_TEXT = { ok: "text-accent", bad: "text-red", warn: "text-amber", neutral: "text-muted" } as const;

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${v}ms`;
}

export function kb(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v >= 1024 ? `${(v / 1024).toFixed(1)} MB` : `${v} KB`;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
