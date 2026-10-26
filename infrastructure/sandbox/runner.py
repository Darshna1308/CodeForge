#!/usr/bin/env python3
"""CodeForge sandbox runner — the trusted supervisor inside each sandbox container.

It speaks a line-delimited JSON protocol with the worker over the container's
stdin/stdout, and launches the *untrusted* program as a separate process:

    worker -> {"op": "init", "language": {...}, "source": "...", "limits": {...}}
    runner -> {"type": "compiled", "ok": true, "ms": 412, "output": "..."}   (or ok=false)
    worker -> {"op": "run", "id": 1, "input": "..."}
    runner -> {"type": "result", "id": 1, "status": "OK", "cpu_ms": 18, ...}
    worker -> {"op": "exit"}

Design points:

* The runner starts as root *inside the container* but the container keeps
  only CAP_SETUID, CAP_SETGID and CAP_KILL. Untrusted code and the compiler
  run as uid/gid 65534 (nobody) with no supplementary groups, so they lose
  every capability on exec and cannot ptrace, signal, or read the file
  descriptors of the runner (which carry the protocol channel). The container
  also sets no-new-privileges, so setuid binaries cannot regain anything.
* Expected outputs never enter the sandbox. The runner only reports what the
  program printed; judging happens in the worker. A program therefore cannot
  read hidden answers even if it fully compromises the runner.
* Limits per execution: RLIMIT_CPU (CPU seconds), RLIMIT_AS (address space),
  RLIMIT_FSIZE, RLIMIT_NOFILE, RLIMIT_CORE=0, plus a wall-clock deadline and
  stdout/stderr caps enforced here while draining the pipes. Container-level
  limits (cgroup memory, pids, cpus, network=none, read-only rootfs) are the
  backstop if any of these are bypassed.
* No shell is ever involved: argv arrays come from the language adapter and
  are passed to execve directly.
* Programs are started through ``cf-launch`` (launcher.c), a tiny static
  binary that drops privileges, applies the rlimits and reports the program's
  own rusage. Forking from it (instead of from this Python process) keeps the
  peak-RSS measurement honest; see the comment at the top of launcher.c.
"""

import json
import os
import selectors
import signal
import subprocess
import sys
import time

SANDBOX_DIR = "/sandbox"
NOBODY = 65534
LAUNCHER = "/opt/runner/cf-launch"
CHILD_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
MEMORY_ERROR_MARKERS = ("MemoryError", "std::bad_alloc", "Cannot allocate memory", "out of memory")

_out = sys.stdout


def send(obj: dict) -> None:
    _out.write(json.dumps(obj, separators=(",", ":")) + "\n")
    _out.flush()


def execute(
    argv: list[str],
    stdin_data: bytes,
    *,
    cpu_limit_s: float | None,
    wall_limit_s: float,
    address_space: int | None,
    stack: int | None,
    stdout_cap: int,
    stderr_cap: int,
    extra_env: dict | None = None,
) -> dict:
    env = {**CHILD_ENV, **(extra_env or {})}
    acct_r, acct_w = os.pipe()
    launch = [
        LAUNCHER,
        str(acct_w),
        str(NOBODY),
        str(NOBODY),
        str(max(1, int(cpu_limit_s + 0.999)) if cpu_limit_s else 0),
        str(address_space or 0),
        str(stack or 0),
        "--",
        *argv,
    ]
    started = time.monotonic()
    proc = subprocess.Popen(
        launch,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=SANDBOX_DIR,
        env=env,
        process_group=0,  # own process group so we can kill everything it forks
        close_fds=True,
        pass_fds=(acct_w,),
    )
    os.close(acct_w)
    pgid = proc.pid
    deadline = started + wall_limit_s

    out_fd, err_fd = proc.stdout.fileno(), proc.stderr.fileno()
    sel = selectors.DefaultSelector()
    for f in (proc.stdin, proc.stdout, proc.stderr):
        os.set_blocking(f.fileno(), False)
    buffers = {out_fd: bytearray(), err_fd: bytearray()}
    caps = {out_fd: stdout_cap, err_fd: stderr_cap}
    truncated = {out_fd: False, err_fd: False}
    sel.register(proc.stdout, selectors.EVENT_READ)
    sel.register(proc.stderr, selectors.EVENT_READ)
    pending_in = memoryview(stdin_data)
    if pending_in:
        sel.register(proc.stdin, selectors.EVENT_WRITE)
    else:
        proc.stdin.close()

    wall_killed = False
    output_exceeded = False

    def kill_group() -> None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    while sel.get_map():
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            wall_killed = True
            kill_group()
            break
        for key, _ in sel.select(timeout):
            f = key.fileobj
            if f is proc.stdin:
                try:
                    n = os.write(f.fileno(), pending_in[:65536])
                    pending_in = pending_in[n:]
                except (BrokenPipeError, OSError):
                    pending_in = pending_in[:0]
                if not pending_in:
                    sel.unregister(f)
                    f.close()
                continue
            fd = f.fileno()
            chunk = os.read(fd, 65536)
            if not chunk:
                sel.unregister(f)
                continue
            room = caps[fd] - len(buffers[fd])
            if len(chunk) > room:
                buffers[fd] += chunk[: max(room, 0)]
                truncated[fd] = True
                if fd == out_fd:
                    # Output flood: stop the program now instead of draining forever.
                    output_exceeded = True
                    kill_group()
                    for k in list(sel.get_map().values()):
                        sel.unregister(k.fileobj)
                    break
            else:
                buffers[fd] += chunk

    sel.close()
    for f in (proc.stdin, proc.stdout, proc.stderr):
        try:
            f.close()
        except OSError:
            pass

    # Reap with wait4 to get *this child's* resource usage (CPU time, peak RSS).
    while True:
        pid, wstatus, usage = os.wait4(proc.pid, os.WNOHANG)
        if pid:
            break
        if time.monotonic() >= deadline:
            wall_killed = True
            kill_group()
            pid, wstatus, usage = os.wait4(proc.pid, 0)
            break
        time.sleep(0.002)
    proc.returncode = 0  # reaped manually; stop Popen from trying again
    kill_group()  # stray background processes left behind by the program
    wall_ms = int((time.monotonic() - started) * 1000)

    with os.fdopen(acct_r, "r") as acct:
        line = acct.read().split()
    if len(line) == 5:
        code, sig, user_us, sys_us, maxrss = (int(x) for x in line)
        exit_code = code if code >= 0 else None
        sig = sig or None
        cpu_ms = (user_us + sys_us) // 1000
        max_rss_kb = maxrss
    else:
        # Launcher was killed (wall-clock deadline) before it could report.
        exit_code, sig, cpu_ms, max_rss_kb = None, signal.SIGKILL, None, None
    return {
        "exit_code": exit_code,
        "signal": sig,
        "cpu_ms": cpu_ms,
        "wall_ms": wall_ms,
        "max_rss_kb": max_rss_kb,
        "wall_killed": wall_killed,
        "output_exceeded": output_exceeded,
        "_stdout": bytes(buffers[out_fd]),
        "_stderr": bytes(buffers[err_fd]),
        "stdout_truncated": truncated[out_fd],
        "stderr_truncated": truncated[err_fd],
    }


def classify(res: dict, time_limit_ms: int, memory_limit_kb: int) -> str:
    """Map raw process facts to an execution status. Output correctness is judged by the worker."""
    stderr = res["_stderr"].decode("utf-8", "replace")
    if res["output_exceeded"]:
        return "OLE"
    if res["wall_killed"] or (res["cpu_ms"] or 0) > time_limit_ms or res["signal"] == signal.SIGXCPU:
        return "TLE"
    crashed = res["exit_code"] != 0
    if (res["max_rss_kb"] or 0) > memory_limit_kb:
        return "MLE"
    if crashed and any(m in stderr for m in MEMORY_ERROR_MARKERS):
        # Allocation refused by RLIMIT_AS: the program tried to exceed the limit.
        return "MLE"
    if crashed:
        return "RE"
    return "OK"


def main() -> int:
    send({"type": "ready", "pid": os.getpid(), "uid": os.getuid()})
    spec = None
    limits = None
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"type": "error", "error": "malformed protocol message"})
            return 2
        op = msg.get("op")
        if op == "init":
            spec = msg["language"]
            limits = msg["limits"]
            src_path = os.path.join(SANDBOX_DIR, os.path.basename(spec["source_filename"]))
            with open(src_path, "wb") as fh:
                fh.write(msg["source"].encode("utf-8"))
            os.chmod(src_path, 0o644)
            if spec.get("compile_argv"):
                res = execute(
                    spec["compile_argv"],
                    b"",
                    cpu_limit_s=limits["compile_timeout_s"],
                    wall_limit_s=limits["compile_timeout_s"],
                    address_space=None,
                    stack=None,
                    stdout_cap=16 * 1024,
                    stderr_cap=16 * 1024,
                )
                out = (res["_stdout"] + res["_stderr"]).decode("utf-8", "replace")
                ok = res["exit_code"] == 0 and not res["wall_killed"]
                if res["wall_killed"]:
                    out += "\n[compilation timed out]"
                send({"type": "compiled", "ok": ok, "ms": res["wall_ms"], "output": out[-16384:]})
            else:
                send({"type": "compiled", "ok": True, "ms": 0, "output": "", "skipped": True})
        elif op == "run":
            if spec is None:
                send({"type": "error", "error": "run before init"})
                return 2
            mem_bytes = limits["memory_limit_mb"] * 1024 * 1024
            res = execute(
                spec["run_argv"],
                msg.get("input", "").encode("utf-8"),
                cpu_limit_s=limits["time_limit_ms"] / 1000.0,
                wall_limit_s=limits["time_limit_ms"] / 1000.0 * 2 + 1.0,
                address_space=mem_bytes + spec.get("address_space_overhead_mb", 0) * 1024 * 1024,
                stack=mem_bytes,
                stdout_cap=int(msg.get("stdout_limit_bytes") or limits["stdout_limit_bytes"]),
                stderr_cap=limits["stderr_limit_bytes"],
                extra_env=spec.get("env"),
            )
            status = classify(res, limits["time_limit_ms"], limits["memory_limit_mb"] * 1024)
            send(
                {
                    "type": "result",
                    "id": msg.get("id"),
                    "status": status,
                    "exit_code": res["exit_code"],
                    "signal": res["signal"],
                    "cpu_ms": res["cpu_ms"],
                    "wall_ms": res["wall_ms"],
                    "max_rss_kb": res["max_rss_kb"],
                    "stdout": res["_stdout"].decode("utf-8", "replace"),
                    "stderr": res["_stderr"].decode("utf-8", "replace"),
                    "stdout_truncated": res["stdout_truncated"],
                    "stderr_truncated": res["stderr_truncated"],
                }
            )
        elif op == "exit":
            return 0
        else:
            send({"type": "error", "error": f"unknown op {op!r}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
