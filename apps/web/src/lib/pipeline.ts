/**
 * Pure reducer that turns the backend's SSE events into the execution
 * visualizer's state. Every number shown comes from an event payload or the
 * DB snapshot; nothing is estimated or animated into existence client-side.
 */
import type { PipelineEvent, SubmissionDetail, SubmissionStatus, TestVerdict, Verdict } from "./types";

export type StageState = "idle" | "active" | "done" | "fail" | "skipped";
export type StageKey = "queue" | "claim" | "sandbox" | "compile" | "run" | "judge" | "verdict";

export const STAGES: { key: StageKey; label: string }[] = [
  { key: "queue", label: "Queue" },
  { key: "claim", label: "Claim" },
  { key: "sandbox", label: "Isolate" },
  { key: "compile", label: "Compile" },
  { key: "run", label: "Execute" },
  { key: "judge", label: "Judge" },
  { key: "verdict", label: "Verdict" },
];

export interface TestLine {
  index: number;
  verdict: TestVerdict;
  cpu_ms: number | null;
  wall_ms: number | null;
  memory_kb: number | null;
  sample: boolean;
}

export interface LogLine {
  key: string;
  text: string;
  detail?: string;
  tone: "ok" | "bad" | "warn" | "info" | "dim";
}

export interface PipelineState {
  status: SubmissionStatus | null;
  verdict: Verdict | null;
  stages: Record<StageKey, StageState>;
  workerId: string | null;
  attempt: number | null;
  queueWaitMs: number | null;
  sandboxMs: number | null;
  compileMs: number | null;
  totalTests: number | null;
  tests: TestLine[];
  runtimeMs: number | null;
  memoryKb: number | null;
  totalMs: number | null;
  passed: number | null;
  log: LogLine[];
  done: boolean;
  error: string | null;
}

const idleStages = (): Record<StageKey, StageState> =>
  ({ queue: "idle", claim: "idle", sandbox: "idle", compile: "idle", run: "idle", judge: "idle", verdict: "idle" });

export const initialPipeline = (): PipelineState => ({
  status: null, verdict: null, stages: idleStages(), workerId: null, attempt: null, queueWaitMs: null,
  sandboxMs: null, compileMs: null, totalTests: null, tests: [], runtimeMs: null, memoryKb: null,
  totalMs: null, passed: null, log: [], done: false, error: null,
});

const TERMINAL: SubmissionStatus[] = ["COMPLETED", "INTERNAL_ERROR", "CANCELLED"];
const n = (v: unknown): number | null => (typeof v === "number" ? v : null);

function push(s: PipelineState, line: LogLine): LogLine[] {
  return s.log.some((l) => l.key === line.key) ? s.log : [...s.log, line];
}

function stagesFromStatus(status: SubmissionStatus, verdict: Verdict | null, compiled: boolean | null): Record<StageKey, StageState> {
  const st = idleStages();
  const order: StageKey[] = ["queue", "claim", "sandbox", "compile", "run", "judge", "verdict"];
  const upto = (k: StageKey, last: StageState) => {
    for (const key of order) {
      if (key === k) { st[key] = last; break; }
      st[key] = "done";
    }
  };
  switch (status) {
    case "CREATED": case "QUEUED": upto("queue", "active"); break;
    case "PROCESSING": upto("sandbox", "active"); break;
    case "COMPILING": upto("compile", "active"); break;
    case "RUNNING": upto("run", "active"); break;
    case "JUDGING": upto("judge", "active"); break;
    case "COMPLETED":
      for (const k of order) st[k] = "done";
      if (verdict === "COMPILATION_ERROR") { st.compile = "fail"; st.run = "skipped"; st.judge = "skipped"; }
      if (compiled === false && verdict !== "COMPILATION_ERROR") st.compile = "skipped";
      st.verdict = verdict === "ACCEPTED" || verdict === "EXECUTED" ? "done" : "fail";
      break;
    case "INTERNAL_ERROR": upto("verdict", "fail"); break;
    case "CANCELLED": upto("queue", "fail"); break;
  }
  return st;
}

export function fromSnapshot(s: PipelineState, d: Pick<SubmissionDetail, "status" | "verdict" | "results" | "compile_ms" | "runtime_ms" | "memory_kb" | "tests_passed" | "tests_total" | "worker_id" | "attempt" | "attempts" | "error_message">): PipelineState {
  const lastAttempt = d.attempts?.[d.attempts.length - 1];
  const tests = s.tests.length
    ? s.tests
    : (d.results ?? []).map((r) => ({
        index: r.ordinal, verdict: r.verdict, cpu_ms: r.cpu_ms, wall_ms: r.wall_ms, memory_kb: r.memory_kb, sample: r.is_sample,
      }));
  const merged: PipelineState = {
    ...s,
    status: d.status,
    verdict: d.verdict,
    stages: stagesFromStatus(d.status, d.verdict, d.compile_ms !== null ? true : null),
    workerId: s.workerId ?? d.worker_id,
    attempt: s.attempt ?? (d.attempt || null),
    queueWaitMs: s.queueWaitMs ?? lastAttempt?.queue_wait_ms ?? null,
    sandboxMs: s.sandboxMs ?? lastAttempt?.sandbox_start_ms ?? null,
    compileMs: s.compileMs ?? d.compile_ms,
    totalTests: s.totalTests ?? d.tests_total,
    tests,
    runtimeMs: d.runtime_ms ?? s.runtimeMs,
    memoryKb: d.memory_kb ?? s.memoryKb,
    totalMs: s.totalMs ?? lastAttempt?.total_ms ?? null,
    passed: d.tests_passed ?? s.passed,
    done: TERMINAL.includes(d.status),
    error: d.status === "INTERNAL_ERROR" ? d.error_message : s.error,
  };
  if (d.compile_ms === null && d.status === "COMPLETED") merged.stages.compile = "skipped";
  return merged;
}

export function applyEvent(s: PipelineState, e: PipelineEvent): PipelineState {
  switch (e.type) {
    case "queued":
      return { ...s, status: s.status ?? "QUEUED", stages: { ...s.stages, queue: "active" },
        log: push(s, { key: "queued", text: "QUEUED", detail: e.recovered ? "republished by sweeper" : "job appended to stream", tone: "info" }) };
    case "claimed": {
      const attempt = n(e.attempt);
      const retry = attempt !== null && attempt > 1;
      return {
        ...s, status: "PROCESSING", workerId: String(e.worker_id ?? ""), attempt, queueWaitMs: n(e.queue_wait_ms),
        totalTests: n(e.tests), tests: retry ? [] : s.tests,
        stages: { ...s.stages, queue: "done", claim: "done", sandbox: "active" },
        log: push(s, { key: `claimed-${attempt}`, text: `${String(e.worker_id).toUpperCase()} CLAIMED JOB`,
          detail: `attempt ${attempt} · waited ${n(e.queue_wait_ms) ?? "?"}ms in queue`, tone: retry ? "warn" : "info" }),
      };
    }
    case "sandbox_ready":
      return { ...s, sandboxMs: n(e.ms), stages: { ...s.stages, sandbox: "done" },
        log: push(s, { key: `sandbox-${s.attempt}`, text: "SANDBOX CREATED", detail: `${n(e.ms)}ms · net=none · ro-rootfs · caps dropped`, tone: "info" }) };
    case "compiling":
      return { ...s, status: "COMPILING", stages: { ...s.stages, compile: "active" } };
    case "compiled": {
      const ok = Boolean(e.ok);
      return { ...s, compileMs: n(e.ms), stages: { ...s.stages, compile: ok ? "done" : "fail" },
        log: push(s, { key: `compiled-${s.attempt}`, text: ok ? "COMPILATION" : "COMPILATION FAILED", detail: `${n(e.ms)}ms`, tone: ok ? "ok" : "bad" }) };
    }
    case "running":
      return { ...s, status: "RUNNING", totalTests: n(e.tests) ?? s.totalTests,
        stages: { ...s.stages, compile: s.stages.compile === "done" ? "done" : "skipped", run: "active" } };
    case "test": {
      const line: TestLine = {
        index: Number(e.index), verdict: e.verdict as TestVerdict, cpu_ms: n(e.cpu_ms), wall_ms: n(e.wall_ms),
        memory_kb: n(e.memory_kb), sample: Boolean(e.sample),
      };
      const tests = [...s.tests.filter((t) => t.index !== line.index), line].sort((a, b) => a.index - b.index);
      return { ...s, tests };
    }
    case "judging":
      return { ...s, status: "JUDGING", stages: { ...s.stages, run: "done", judge: "active" } };
    case "completed": {
      const verdict = e.verdict as Verdict;
      const good = verdict === "ACCEPTED" || verdict === "EXECUTED";
      return {
        ...s, status: "COMPLETED", verdict, runtimeMs: n(e.runtime_ms), memoryKb: n(e.memory_kb), totalMs: n(e.total_ms),
        passed: n(e.passed), totalTests: n(e.total) ?? s.totalTests, done: true,
        stages: { ...s.stages, run: verdict === "COMPILATION_ERROR" ? "skipped" : "done",
          judge: verdict === "COMPILATION_ERROR" ? "skipped" : "done", verdict: good ? "done" : "fail" },
        log: push(s, { key: "completed", text: verdict.replaceAll("_", " "), detail: `total ${n(e.total_ms)}ms`, tone: good ? "ok" : "bad" }),
      };
    }
    case "retrying":
      return { ...s, status: "QUEUED", stages: { ...idleStages(), queue: "active" },
        log: push(s, { key: `retry-${e.attempt}`, text: "RETRYING", detail: String(e.reason ?? ""), tone: "warn" }) };
    case "internal_error":
      return { ...s, status: "INTERNAL_ERROR", done: true, error: String(e.reason ?? "internal error"),
        stages: { ...s.stages, verdict: "fail" }, log: push(s, { key: "internal", text: "INTERNAL ERROR", detail: String(e.reason ?? ""), tone: "bad" }) };
    case "cancelled":
      return { ...s, status: "CANCELLED", done: true, log: push(s, { key: "cancelled", text: "CANCELLED", tone: "dim" }) };
    default:
      return s;
  }
}
