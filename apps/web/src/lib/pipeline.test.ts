import { describe, expect, it } from "vitest";

import { applyEvent, fromSnapshot, initialPipeline } from "./pipeline";
import type { PipelineEvent } from "./types";

const run = (events: PipelineEvent[]) => events.reduce(applyEvent, initialPipeline());

describe("pipeline reducer", () => {
  it("follows a compiled, accepted submission through every stage using backend numbers", () => {
    const s = run([
      { type: "queued" },
      { type: "claimed", worker_id: "worker-a", attempt: 1, queue_wait_ms: 12, tests: 2 },
      { type: "sandbox_ready", ms: 410 },
      { type: "compiling" },
      { type: "compiled", ok: true, ms: 143 },
      { type: "running", tests: 2 },
      { type: "test", index: 1, verdict: "ACCEPTED", cpu_ms: 21, wall_ms: 22, memory_kb: 3500, sample: true },
      { type: "test", index: 2, verdict: "ACCEPTED", cpu_ms: 18, wall_ms: 19, memory_kb: 3600, sample: false },
      { type: "judging" },
      { type: "completed", verdict: "ACCEPTED", runtime_ms: 21, memory_kb: 3600, passed: 2, total: 2, total_ms: 760 },
    ]);
    expect(s.done).toBe(true);
    expect(s.verdict).toBe("ACCEPTED");
    expect(Object.values(s.stages).every((x) => x === "done")).toBe(true);
    expect(s.compileMs).toBe(143);
    expect(s.sandboxMs).toBe(410);
    expect(s.totalMs).toBe(760);
    expect(s.tests.map((t) => t.cpu_ms)).toEqual([21, 18]);
    expect(s.log.map((l) => l.text)).toContain("WORKER-A CLAIMED JOB");
  });

  it("marks compile failure and skips execution stages", () => {
    const s = run([
      { type: "claimed", worker_id: "w", attempt: 1, queue_wait_ms: 1, tests: 5 },
      { type: "compiling" },
      { type: "compiled", ok: false, ms: 30 },
      { type: "completed", verdict: "COMPILATION_ERROR", passed: 0, total: 5, total_ms: 400 },
    ]);
    expect(s.stages.compile).toBe("fail");
    expect(s.stages.run).toBe("skipped");
    expect(s.stages.verdict).toBe("fail");
  });

  it("resets test progress when a retry is claimed", () => {
    let s = run([
      { type: "claimed", worker_id: "w1", attempt: 1, tests: 3 },
      { type: "test", index: 1, verdict: "ACCEPTED", cpu_ms: 5, wall_ms: 5, memory_kb: 1, sample: false },
      { type: "retrying", attempt: 1, reason: "worker lease expired" },
    ]);
    expect(s.status).toBe("QUEUED");
    s = applyEvent(s, { type: "claimed", worker_id: "w2", attempt: 2, tests: 3 });
    expect(s.tests).toHaveLength(0);
    expect(s.attempt).toBe(2);
    expect(s.log.some((l) => l.text === "RETRYING")).toBe(true);
  });

  it("ignores duplicate events (SSE replay after reconnect)", () => {
    const evt: PipelineEvent = { type: "test", index: 1, verdict: "ACCEPTED", cpu_ms: 5, wall_ms: 5, memory_kb: 1, sample: false };
    const s = run([{ type: "queued" }, { type: "queued" }, evt, evt]);
    expect(s.tests).toHaveLength(1);
    expect(s.log.filter((l) => l.key === "queued")).toHaveLength(1);
  });

  it("hydrates from a DB snapshot when events have expired", () => {
    const s = fromSnapshot(initialPipeline(), {
      status: "COMPLETED", verdict: "WRONG_ANSWER", compile_ms: null, runtime_ms: 40, memory_kb: 9000,
      tests_passed: 1, tests_total: 3, worker_id: "w", attempt: 1, error_message: null,
      attempts: [{ attempt_no: 1, worker_id: "w", outcome: "SUCCEEDED", started_at: "", finished_at: null, queue_wait_ms: 3, sandbox_start_ms: 300, compile_ms: null, total_ms: 900, error: null }],
      results: [
        { ordinal: 1, verdict: "ACCEPTED", is_sample: true, cpu_ms: 10, wall_ms: 11, memory_kb: 9000, exit_code: 0, signal: null },
        { ordinal: 2, verdict: "WRONG_ANSWER", is_sample: false, cpu_ms: 40, wall_ms: 41, memory_kb: 9000, exit_code: 0, signal: null },
        { ordinal: 3, verdict: "SKIPPED", is_sample: false, cpu_ms: null, wall_ms: null, memory_kb: null, exit_code: null, signal: null },
      ],
    });
    expect(s.done).toBe(true);
    expect(s.stages.compile).toBe("skipped");
    expect(s.stages.verdict).toBe("fail");
    expect(s.tests).toHaveLength(3);
    expect(s.totalMs).toBe(900);
  });
});
