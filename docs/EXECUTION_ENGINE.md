# Execution engine

## Lifecycle state machine

Defined once in `packages/core/codeforge_core/state_machine.py` and enforced by
`repository.transition()` for every status change in the system.

```
CREATED ─► QUEUED ─► PROCESSING ─┬─► COMPILING ─┬─► RUNNING ─► JUDGING ─► COMPLETED
              ▲                  └──────────────┼─► RUNNING          (verdict set)
              │                                 └─► COMPLETED  (compilation error)
              └──── lease expired (sweeper) ◄── any in-progress state

Any non-terminal state ─► INTERNAL_ERROR (attempts exhausted / unrecoverable)
CREATED | QUEUED       ─► CANCELLED      (user cancelled before a worker claimed it)
```

**Status vs verdict.** The prompt-style list of "failure states" (`COMPILE_ERROR`,
`TIME_LIMIT_EXCEEDED`, …) mixes two concepts. CodeForge keeps them orthogonal:
`status` is *where the job is* in the pipeline, `verdict` is *what the judge
decided*. A program that times out ran to completion as far as the pipeline is
concerned (`COMPLETED`), with verdict `TIME_LIMIT_EXCEEDED`. Only infrastructure
problems produce `INTERNAL_ERROR`. A database CHECK constraint
(`ck_submissions_verdict_iff_completed`) guarantees `verdict IS NOT NULL ⇔ status = COMPLETED`.

Verdicts: `ACCEPTED`, `WRONG_ANSWER`, `COMPILATION_ERROR`, `RUNTIME_ERROR`,
`TIME_LIMIT_EXCEEDED`, `MEMORY_LIMIT_EXCEEDED`, `OUTPUT_LIMIT_EXCEEDED`, and
`EXECUTED` (Run Code with custom input — nothing to compare against).

`transition()` takes a row lock (`SELECT … FOR UPDATE`), validates the move against
the table, the caller's `expected_from` set and the optional fencing token
`(worker_id, attempt)`, then writes the update and an audit row in
`submission_transitions`. It returns `None` when the move is not (or no longer) legal,
which callers treat as "someone else won".

## Language adapters

`packages/core/codeforge_core/languages.py`:

| Field | Python | C++17 |
|---|---|---|
| source file | `main.py` | `main.cpp` |
| compile argv | — | `g++ -std=gnu++17 -O2 -pipe -o /sandbox/main /sandbox/main.cpp` |
| run argv | `python3 -I -B /sandbox/main.py` | `/sandbox/main` |
| address-space headroom | +96 MB (interpreter) | +32 MB |
| image | `codeforge-sandbox:latest` | same |

Adding a language = an adapter entry + toolchain in the sandbox image + a row in the
`languages` table (migration). Commands are argv arrays executed with `execv`; no shell.

## Sandbox protocol

The worker starts one container per job attempt and speaks line-delimited JSON over
the container's stdin/stdout (`apps/worker/codeforge_worker/sandbox.py` ↔
`infrastructure/sandbox/runner.py`):

```
runner → {"type":"ready"}                         # handshake; time to here = sandbox start latency
worker → {"op":"init","language":{…},"source":"…","limits":{…}}
runner → {"type":"compiled","ok":true,"ms":412,"output":""}
worker → {"op":"run","id":1,"input":"…","stdout_limit_bytes":1048576}
runner → {"type":"result","id":1,"status":"OK","exit_code":0,"signal":null,
          "cpu_ms":18,"wall_ms":24,"max_rss_kb":9804,"stdout":"…","stderr":"…", …}
worker → {"op":"exit"}
```

Only test **inputs** cross into the sandbox. Expected outputs stay in the worker, which
judges each result as it arrives. This is what makes "stop at the first failing test"
possible without leaking answers.

## Per-execution limits (inside the sandbox)

Programs are started by `cf-launch` (static C binary) which forks, drops to uid/gid
65534 with no supplementary groups, sets rlimits and `execv`s the program:

| Limit | Value |
|---|---|
| `RLIMIT_CPU` | ⌈TL⌉ s soft (SIGXCPU), +1 s hard (SIGKILL) |
| `RLIMIT_AS` | memory limit + language headroom |
| `RLIMIT_STACK` | memory limit (deep recursion allowed within the memory budget) |
| `RLIMIT_FSIZE` | 16 MB |
| `RLIMIT_NOFILE` | 64 |
| `RLIMIT_CORE` | 0 |
| wall clock | 2·TL + 1 s, then SIGKILL to the whole process group |
| stdout | max(1 MiB, 2 × expected output size + 4 KiB); killed when crossed |
| stderr | 8 KiB (truncated, not fatal) |

Compilation runs under the same launcher (as uid 65534) with a 15 s CPU/wall budget.

**Why `cf-launch`?** Linux keeps a process's peak-RSS high-water mark across
`fork`+`exec`. Forked directly from the Python runner, every program would report at
least the runner's ~12 MB. Forking from a tiny static binary makes `ru_maxrss` reflect
the program (measured: ~3.5 MB for a trivial C++ program, ~9.8 MB for Python).

## Classification (runner) and judging (worker)

Runner status per test, in priority order:

1. stdout cap crossed → `OLE`
2. wall-clock kill, CPU time > TL, or SIGXCPU → `TLE`
3. peak RSS > memory limit, or a crash whose stderr shows an allocation failure
   (`MemoryError`, `std::bad_alloc`) → `MLE`
4. non-zero exit or signal → `RE`
5. otherwise `OK`

The worker maps `OK` to `ACCEPTED`/`WRONG_ANSWER` by comparing output against the
expected answer, or `EXECUTED` for custom input.

### Output normalisation policy (`apps/worker/codeforge_worker/judge.py`)

1. Decode UTF-8 (invalid bytes replaced).
2. CRLF and CR → LF.
3. Strip trailing spaces/tabs on every line.
4. Drop trailing empty lines.

Everything else must match exactly: leading whitespace, inner spacing, case. No
floating-point tolerance (no seeded problem needs it).

### Aggregation

Tests run in ordinal order (samples first, then hidden). In SUBMIT mode the first
non-accepted test decides the verdict and the remaining tests are recorded as
`SKIPPED`. RUN mode runs every sample (or the single custom input).

Reported `runtime_ms` is the maximum CPU time over executed tests; `memory_kb` is the
maximum peak RSS.

## What is stored and exposed

| Data | SUBMIT, hidden test | SUBMIT, sample test | RUN mode |
|---|---|---|---|
| verdict, cpu/wall ms, memory, exit code, signal | ✓ | ✓ | ✓ |
| stdout / stderr | **never** | ✓ | ✓ |
| input / expected output in API responses | **never** | ✓ (already public) | ✓ (samples or the user's own input) |

Hidden-test stderr is deliberately not stored: a program could print its input to
stderr and exfiltrate hidden tests.

## Honest limitations

* Memory accounting uses `RLIMIT_AS` + peak RSS rather than a per-test cgroup; the
  container cgroup (≥512 MB) is the hard backstop. A Python program that is killed by
  the container OOM killer would surface as a runtime error.
* Tests of one submission share a container (and its `/sandbox` tmpfs), so a program
  can leave files for later tests of the same submission. Nothing persists across
  submissions.
* CPU time is measured per process tree via `wait4`; multi-threaded programs are
  charged for all threads (as most judges do).
