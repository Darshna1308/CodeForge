# ADR 0005 — Ephemeral Docker containers as the sandbox

**Status:** accepted

## Context
Submitted programs are untrusted. The project must run with `docker compose up` on a
developer laptop (Linux, macOS, Windows/WSL), without kernel modules or a hypervisor.

## Decision
One fresh container per job attempt from a dedicated sandbox image, created by the
worker through the Docker CLI with: no network, read-only rootfs, tmpfs work dir,
`cap-drop ALL` (+SETUID/SETGID/KILL for the supervisor), `no-new-privileges`, memory/
CPU/PIDs cgroup limits, `--init`, `--rm`. Inside, a trusted supervisor runs the
compiler and program as uid 65534 under rlimits via a small C launcher, and only test
inputs enter the container.

## Consequences
* Strong defence-in-depth with zero host setup; easy to reason about and to test
  (`apps/worker/tests/test_sandbox.py` asserts the restrictions from inside).
* ~300–400 ms start-up per job (amortised across all tests of a submission by reusing
  one container per attempt).
* The worker needs the Docker socket and is therefore a privileged component.
* See ADR 0006 for what Docker does *not* give us.
