# ADR 0006 — Accepting the limits of Docker-based sandboxing

**Status:** accepted (with documented risk)

## Context
Containers share the host kernel. Isolation depends on namespaces, cgroups, seccomp
and capabilities being correctly configured *and* the kernel being free of reachable
bugs.

## Decision
CodeForge treats Docker isolation as appropriate for an educational/portfolio judge
and documents — in the README and SECURITY.md — that it is **not** sufficient for
hostile multi-tenant workloads. We do not claim otherwise anywhere.

## Consequences / what production would require
* A stronger boundary: gVisor (`runsc`), Kata Containers or Firecracker microVMs.
* Language-specific seccomp allow-lists; user-namespace remapping.
* A restricted Docker API proxy (or a dedicated execution service on disposable
  hosts) instead of mounting the raw socket into the worker.
* Per-test cgroups (nsjail/isolate) for exact memory and time accounting.
