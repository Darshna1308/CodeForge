import Link from "next/link";

import { PageHeader } from "@/components/Shell";

import { ArchitectureDiagram } from "./ArchitectureDiagram";

const SECTIONS: { id: string; q: string; a: string[]; code?: string }[] = [
  {
    id: "redis", q: "Why does Redis exist here?",
    a: [
      "It is the system's nervous system, with five distinct jobs: the job queue (Redis Streams + a consumer group), the per-submission event log that feeds SSE, the cache-aside layer for problem data, atomic token-bucket rate limiting (Lua), and the worker liveness registry (keys with a 15s TTL).",
      "PostgreSQL stays the source of truth. Everything in Redis is either reconstructible (cache, events) or recoverable from the database (the queue — the sweeper re-publishes stuck rows).",
    ],
    code: "XADD cf:q:submit * submission_id 1927\nXREADGROUP GROUP judges worker-3/0 COUNT 1 BLOCK 2000 STREAMS cf:q:submit >\nXACK cf:q:submit judges 1793018469621-0",
  },
  {
    id: "async", q: "Why is execution asynchronous?",
    a: [
      "Compiling and running untrusted code takes hundreds of milliseconds to seconds and must never share a process with the API. POST /submissions validates, persists, enqueues and returns 202 with an id in a few milliseconds; workers pull jobs at their own pace.",
      "The queue absorbs bursts (backpressure instead of timeouts), lets workers scale independently of the API, and lets a job outlive the HTTP request that created it — including a worker crash.",
    ],
  },
  {
    id: "isolation", q: "How does isolation work?",
    a: [
      "Every job gets a fresh container from the sandbox image: no network namespace beyond loopback, read-only root filesystem, a 64 MB tmpfs at /sandbox, all capabilities dropped except the three the supervisor needs to drop privileges, no-new-privileges, an IPC namespace of its own, and cgroup limits on memory, CPU and PIDs.",
      "Inside, a trusted supervisor (runner.py) starts the compiler and the program as uid 65534 via a small C launcher. The program cannot signal or read the supervisor, and the expected outputs never enter the container at all — judging happens in the worker.",
      "Docker is not a perfect boundary for hostile multi-tenant code (shared kernel). See docs/SECURITY.md for the threat model and what a production system would add (gVisor/Firecracker, seccomp allow-lists, a Docker socket proxy).",
    ],
    code: "docker run --rm -i --network none --read-only \\\n  --tmpfs /sandbox:rw,exec,nosuid,size=64m --cap-drop ALL \\\n  --cap-add SETUID --cap-add SETGID --cap-add KILL \\\n  --security-opt no-new-privileges --pids-limit 64 \\\n  --memory 512m --memory-swap 512m --cpus 1 --init codeforge-sandbox",
  },
  {
    id: "limits", q: "How are resource limits enforced?",
    a: [
      "Per test: RLIMIT_CPU (CPU seconds; SIGXCPU then SIGKILL), RLIMIT_AS (memory limit + runtime headroom), RLIMIT_FSIZE, RLIMIT_NOFILE, no core dumps, plus a wall-clock deadline of 2×TL+1s enforced by the supervisor, which kills the whole process group.",
      "Output is drained with non-blocking reads and capped (1 MiB or 2× the expected answer): a print loop is killed the moment it crosses the cap. Peak memory comes from wait4() rusage of the program itself. The container's cgroup limits are the backstop if any of this is bypassed.",
    ],
  },
  {
    id: "duplicates", q: "How are duplicate jobs handled?",
    a: [
      "Streams give at-least-once delivery, so duplicates are expected, not exceptional. The claim is a state-machine transition QUEUED → PROCESSING executed under a row lock: exactly one worker wins; every other delivery sees a non-QUEUED row, counts a duplicate, and acknowledges without doing work.",
      "On the API side, POST /submissions accepts an Idempotency-Key; a partial unique index on (user_id, idempotency_key) makes concurrent retries return the original submission instead of creating a second one.",
    ],
  },
  {
    id: "scaling", q: "How does scaling workers work?",
    a: [
      "Workers are stateless consumers in one consumer group. Adding capacity is `docker compose up --scale worker=4` (or raising WORKER_CONCURRENCY): Redis distributes new messages across consumers, and each worker registers a heartbeat so the dashboard shows the live pool.",
      "Interactive Run jobs live on a separate stream with priority over judged submissions, with an anti-starvation rule so a flood of runs cannot stall submissions.",
    ],
  },
  {
    id: "crash", q: "What happens when a worker crashes?",
    a: [
      "Two independent recovery paths. Queue level: the message stays in the consumer group's pending list; after the visibility timeout another worker takes it over with XAUTOCLAIM (poison messages are dead-lettered after 5 deliveries).",
      "Database level: each claim sets a lease (lease_expires_at) that the worker renews after every test. A leader-elected sweeper re-queues submissions whose lease expired (or fails them after 3 attempts). The attempt number is a fencing token: if the 'dead' worker was only slow, its late writes are rejected because (worker_id, attempt) no longer match.",
    ],
  },
];

export default function ArchitecturePage() {
  return (
    <main className="mx-auto max-w-[1600px] px-4 py-8">
      <PageHeader path="man codeforge" title="Architecture">
        <nav className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-dim">
          {SECTIONS.map((s) => <a key={s.id} href={`#${s.id}`} className="hover:text-fg">#{s.id}</a>)}
        </nav>
      </PageHeader>

      <section className="mt-6 border border-line bg-panel">
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <span className="label">request path · submit → verdict</span>
          <span className="font-mono text-[10px] text-dim">solid = data path · dashed = control/events</span>
        </div>
        <ArchitectureDiagram />
      </section>

      <section className="mt-6 grid gap-px border border-line bg-line lg:grid-cols-2">
        <div className="bg-panel p-5">
          <div className="label">submission state machine</div>
          <pre className="scrollbar-thin mt-3 overflow-x-auto font-mono text-[12px] leading-6 text-muted">{`CREATED ─► QUEUED ─► PROCESSING ─┬─► COMPILING ─┬─► RUNNING ─► JUDGING ─► COMPLETED
              ▲                   └──────────────┴─► RUNNING        (verdict)
              │                                  └─► COMPLETED  (compile error)
              └──── lease expired (sweeper) ◄──── any in-progress state

any non-terminal ─► INTERNAL_ERROR     CREATED | QUEUED ─► CANCELLED`}</pre>
          <p className="mt-3 text-[13px] leading-relaxed text-muted">
            Lifecycle <span className="font-mono text-fg">status</span> and judging <span className="font-mono text-fg">verdict</span> are separate columns; a CHECK constraint guarantees a verdict exists iff status is COMPLETED. Every transition is validated against one table in <span className="font-mono text-fg">codeforge_core/state_machine.py</span> and recorded in <span className="font-mono text-fg">submission_transitions</span>.
          </p>
        </div>
        <div className="bg-panel p-5">
          <div className="label">what a worker does with one message</div>
          <ol className="mt-3 space-y-1.5 font-mono text-[12px] text-muted">
            {[
              "XREADGROUP (run stream first, then both)",
              "BEGIN; SELECT … FOR UPDATE; QUEUED→PROCESSING, attempt+1, lease; COMMIT",
              "docker run … codeforge-sandbox  (handshake = sandbox start time)",
              "init: write source, compile as uid 65534  → COMPILING",
              "for each test: send input, receive stdout + rusage, judge, renew lease",
              "stop at first failing test (submit mode)  → JUDGING",
              "BEGIN; fenced JUDGING→COMPLETED + results + attempt row; COMMIT",
              "XACK · publish events · container removed (--rm)",
            ].map((step, i) => (
              <li key={i} className="grid grid-cols-[1.5rem_1fr]"><span className="text-accent">{i + 1}.</span><span>{step}</span></li>
            ))}
          </ol>
        </div>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {SECTIONS.map((s) => (
          <section key={s.id} id={s.id} className="scroll-mt-20 border-t border-line pt-5">
            <h2 className="text-lg font-semibold tracking-tight text-fg"><span className="mr-2 font-mono text-[12px] text-accent">#{s.id}</span>{s.q}</h2>
            {s.a.map((p, i) => <p key={i} className="mt-3 text-[14px] leading-relaxed text-muted">{p}</p>)}
            {s.code && <pre className="scrollbar-thin mt-3 overflow-x-auto border border-line bg-panel-2 p-3 font-mono text-[12px] leading-5 text-fg">{s.code}</pre>}
          </section>
        ))}
      </div>
      <p className="mt-10 font-mono text-[12px] text-dim">
        Deeper write-ups live in the repository: docs/ARCHITECTURE.md, docs/EXECUTION_ENGINE.md, docs/QUEUE_AND_CONCURRENCY.md, docs/SECURITY.md, docs/adr/. ·{" "}
        <Link href="/dashboard" className="text-muted hover:text-fg">see it running →</Link>
      </p>
    </main>
  );
}
