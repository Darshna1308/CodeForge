# Security model

CodeForge executes **untrusted code**. This document states what is protected, how,
and — just as importantly — what is *not*.

> CodeForge is an educational / portfolio execution engine. Docker containers share
> the host kernel and are **not** a sufficient boundary for hostile, multi-tenant
> Internet workloads. Do not expose this deployment to arbitrary users without the
> additional measures listed under "Production hardening".

## Trust boundaries

```
 untrusted ┃ program + compiler (uid 65534) inside the sandbox container
───────────╋──────────────────────────────────────────────────────────────
  trusted  ┃ runner.py / cf-launch (container root with 3 capabilities)
           ┃ worker (controls Docker via the socket) · API · Postgres · Redis
```

* The **API never executes user code**; it only stores it and enqueues an id.
* The **worker is privileged** (it holds the Docker socket) and never evaluates user
  input as code. It passes source text and test inputs to the sandbox as JSON data.
* The **sandbox container** receives no credentials, no Docker socket, no host bind
  mounts and no network.

## Container hardening (`apps/worker/codeforge_worker/sandbox.py`)

| Control | Setting | Mitigates |
|---|---|---|
| Network | `--network none` | data exfiltration, scanning, callbacks |
| Root filesystem | `--read-only`; writable tmpfs only at `/sandbox` (64 MB, `nosuid,nodev`) and `/tmp` (16 MB, `noexec`) | persistence, tampering with toolchains |
| Capabilities | `--cap-drop ALL --cap-add SETUID --cap-add SETGID --cap-add KILL` | privilege use inside the container |
| Privilege escalation | `--security-opt no-new-privileges` | setuid binaries |
| Processes | `--pids-limit 64` | fork bombs |
| Memory | `--memory = --memory-swap = max(512 MB, limit + 256 MB)` | host memory exhaustion (no swap) |
| CPU | `--cpus 1` | noisy neighbour |
| IPC | `--ipc none` | shared-memory side channels with the host |
| Init | `--init` | zombie accumulation |
| Logging | `--log-driver none` | disk exhaustion via container logs |
| Lifetime | `--rm`, per-job wall deadline (150 s), forced `docker rm -f` on timeout, labelled janitor for leftovers | resource leaks |
| Seccomp/AppArmor | Docker defaults | dangerous syscalls |

## Inside the container

* `runner.py` (trusted supervisor) runs as container-root holding only SETUID,
  SETGID and KILL. It needs them to start the compiler and the program as
  **uid/gid 65534 with no supplementary groups** (via `cf-launch`) and to kill the
  program's process group.
* After the uid switch the program has **no capabilities**. It cannot signal the
  supervisor, ptrace it, or open its `/proc/<pid>/fd/*` — so it cannot read or forge
  the protocol channel. Verified by `test_sandbox_is_unprivileged_offline_and_readonly`.
* **Expected outputs never enter the sandbox.** Even a full compromise of the
  container cannot read hidden answers; judging happens in the worker.
* rlimits per execution: CPU, address space, stack, file size, open files, no core
  dumps; wall-clock deadline; stdout/stderr caps enforced while draining pipes.
* No shell anywhere: compile and run commands are fixed argv arrays from the language
  adapter, passed to `execv`. Source code is written to a file by the supervisor; it
  is never interpolated into a command line. No `eval`/`exec` of submissions.

## Application security

| Area | Implementation |
|---|---|
| Passwords | Argon2id (`argon2-cffi`), never stored or logged in plaintext; login does a dummy verify for unknown users to reduce username-enumeration timing |
| Sessions | HS256 JWT with `exp`, `iat`, `jti`, `iss`; 12 h default TTL; secret from `JWT_SECRET` (API refuses the dev default outside `ENVIRONMENT=development`) |
| Cookie | `httpOnly`, `SameSite=Lax`, `Secure` configurable; Bearer header also accepted |
| Logout | `jti` denylisted in Redis until the token's own expiry |
| CSRF | SameSite=Lax cookie + JSON bodies (cross-site forms cannot send `application/json` without a CORS preflight, which the allow-list rejects) |
| CORS | Explicit origin allow-list (`CORS_ORIGINS`), credentials only for listed origins |
| Authorization | Submissions readable only by owner (or admin); other users get 404, not 403, to avoid id enumeration; cache invalidation requires ADMIN |
| Input validation | Pydantic schemas; source and custom input ≤ 64 KB (also DB CHECK constraints); NUL bytes rejected; language allow-list; Idempotency-Key format check |
| Rate limiting | Redis token buckets: submit (per user), run (per user), auth (per IP); 429 + `Retry-After` |
| Hidden tests | Never selected by public endpoints; never cached; hidden-test stdout/stderr never stored |
| Secrets | Environment variables only; `.env` is git-ignored; `.env.example` holds placeholders |
| Logs | No source code, test data, passwords or tokens in logs |
| Markdown | Problem statements are rendered by a tiny React renderer — no `dangerouslySetInnerHTML` |
| Open redirect | Login `?next=` only follows same-site relative paths |

### Deliberate fail-open choices

* **Rate limiter** fails open if Redis is down: it protects capacity, it is not an
  authentication control.
* **Token revocation check** fails open if Redis is down: otherwise a Redis outage
  logs out every user. Tokens remain signed and time-limited. A high-security
  deployment should flip this to fail-closed.

## Known limitations

1. **Shared kernel.** A kernel exploit reachable through the default seccomp profile
   escapes the container. Docker isolation is defence-in-depth, not a guarantee.
2. **Docker socket on the worker.** Anyone who compromises the worker process controls
   the host's Docker daemon (effectively root). The worker never executes user input,
   but this is the most sensitive component.
3. **Image size.** The sandbox uses the full `python:3.12` image (it ships GCC); a
   smaller image would reduce attack surface.
4. **Shared `/sandbox` across tests of one submission.** A program can leave files for
   its own later tests (not for other users).
5. **Container root inside the sandbox** holds 3 capabilities for the supervisor; the
   untrusted program does not.
6. **Memory accounting** per test uses rlimits + peak RSS; the container cgroup is the
   hard limit.

## Production hardening (not implemented)

* Run sandboxes under **gVisor (runsc)**, **Kata Containers** or **Firecracker**
  microVMs instead of runc.
* A custom **seccomp allow-list** per language; AppArmor/SELinux profiles.
* **User namespaces** (`userns-remap`/rootless Docker) so container root ≠ host root.
* Replace the raw socket with a **Docker socket proxy** that only permits
  `containers/create|start|attach|kill|delete` for the sandbox image, or a dedicated
  execution service on separate, disposable hosts.
* Per-test cgroups (e.g. `isolate`/nsjail) for exact memory/time accounting.
* Refresh tokens + short access tokens; TLS everywhere; secret manager.
