import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { applyEvent, initialPipeline } from "@/lib/pipeline";

import { VerdictBadge } from "./Badges";
import { ExecutionVisualizer } from "./ExecutionVisualizer";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("renders the supported subset and never injects HTML", () => {
    const { container } = render(<Markdown text={"Use `a[i]` and **bold**.\n\n- one\n- <img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("code")?.textContent).toBe("a[i]");
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("VerdictBadge", () => {
  it("shows a pending status before a verdict exists", () => {
    render(<VerdictBadge verdict={null} status="RUNNING" />);
    expect(screen.getByText("running")).toBeTruthy();
  });
  it("labels verdicts", () => {
    render(<VerdictBadge verdict="TIME_LIMIT_EXCEEDED" />);
    expect(screen.getByText("Time Limit Exceeded")).toBeTruthy();
  });
});

describe("ExecutionVisualizer", () => {
  it("renders streamed tests with measured timings", () => {
    let s = initialPipeline();
    s = applyEvent(s, { type: "claimed", worker_id: "worker-x", attempt: 1, queue_wait_ms: 4, tests: 2 });
    s = applyEvent(s, { type: "test", index: 1, verdict: "ACCEPTED", cpu_ms: 21, wall_ms: 22, memory_kb: 3500, sample: true });
    render(<ExecutionVisualizer id={1927} state={s} />);
    expect(screen.getByText("#CF-1927")).toBeTruthy();
    expect(screen.getByText("21ms")).toBeTruthy();
    expect(screen.getByText("WORKER-X CLAIMED JOB")).toBeTruthy();
  });
});
