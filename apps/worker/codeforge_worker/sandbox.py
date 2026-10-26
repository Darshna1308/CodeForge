"""Worker-side driver for one ephemeral sandbox container.

The worker talks to the Docker daemon only through the ``docker`` CLI with an
argv array (no shell, no string interpolation). The container gets the
submission's source and test *inputs* over its stdin; expected outputs stay in
the worker. See infrastructure/sandbox/runner.py for the other side of the
protocol and docs/SECURITY.md for the threat model.
"""

import json
import logging
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass

from codeforge_core.config import Settings
from codeforge_core.languages import LanguageAdapter

log = logging.getLogger(__name__)

SANDBOX_LABEL = "codeforge.sandbox"


class SandboxError(Exception):
    """Infrastructure failure (container could not start, protocol broke, hung)."""


@dataclass
class CompileResult:
    ok: bool
    ms: int
    output: str
    skipped: bool


def stdout_limit(settings: Settings, expected_size: int | None) -> int:
    """Output limit: the configured floor (1 MiB), or twice the expected answer if larger.

    A fixed cap would wrongly reject correct programs whose answers are big
    (e.g. 10^5 shortest-path distances), while 2x expected still stops floods.
    """
    floor = settings.sandbox_stdout_limit_bytes
    return floor if expected_size is None else max(floor, 2 * expected_size + 4096)


def docker_run_argv(settings: Settings, image: str, name: str, memory_limit_mb: int) -> list[str]:
    container_mb = max(settings.sandbox_container_memory_floor_mb, memory_limit_mb + 256)
    return [
        settings.sandbox_docker_binary, "run",
        "--rm", "-i",
        "--name", name,
        "--label", f"{SANDBOX_LABEL}=1",
        "--network", "none",                      # no network stack beyond loopback
        "--read-only",                            # immutable root filesystem
        "--tmpfs", f"/sandbox:rw,exec,nosuid,nodev,size={settings.sandbox_tmpfs_mb}m,mode=1777",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--cap-drop", "ALL",                      # runner keeps only what it needs to drop privileges
        "--cap-add", "SETUID", "--cap-add", "SETGID", "--cap-add", "KILL",
        "--security-opt", "no-new-privileges",
        "--memory", f"{container_mb}m",
        "--memory-swap", f"{container_mb}m",      # no swap: memory limit is real
        "--pids-limit", str(settings.sandbox_pids_limit),
        "--cpus", str(settings.sandbox_cpus),
        "--ipc", "none",
        "--init",                                 # reap orphans left by the program
        "--log-driver", "none",                   # protocol traffic is not logged by the daemon
        "--hostname", "sandbox",
        image,
    ]


class SandboxSession:
    """Context manager: starts a container, exchanges protocol messages, always cleans up."""

    def __init__(self, settings: Settings, language: LanguageAdapter, submission_id: int, attempt: int, memory_limit_mb: int):
        self.settings = settings
        self.language = language
        self.memory_limit_mb = memory_limit_mb
        self.name = f"cf-sbx-{submission_id}-{attempt}-{uuid.uuid4().hex[:6]}"
        self.image = language.sandbox_image or settings.sandbox_image
        self.proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self.startup_ms: int | None = None
        self._deadline = time.monotonic() + settings.sandbox_job_timeout_s

    # -- lifecycle -----------------------------------------------------------------
    def __enter__(self) -> "SandboxSession":
        argv = docker_run_argv(self.settings, self.image, self.name, self.memory_limit_mb)
        t0 = time.monotonic()
        try:
            self.proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
            )
        except OSError as exc:
            raise SandboxError(f"failed to launch docker: {exc}") from exc
        threading.Thread(target=self._pump, daemon=True, name=f"pump-{self.name}").start()
        ready = self._read(timeout=30)
        if ready.get("type") != "ready":
            raise SandboxError(f"unexpected sandbox handshake: {ready.get('type')}")
        self.startup_ms = int((time.monotonic() - t0) * 1000)
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.poll() is None:
                try:
                    self._send({"op": "exit"})
                except SandboxError:
                    pass
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.kill()
        finally:
            for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                try:
                    f and f.close()
                except OSError:
                    pass

    def kill(self) -> None:
        """Force-remove the container (used on timeouts / protocol failures)."""
        subprocess.run(
            [self.settings.sandbox_docker_binary, "rm", "-f", self.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False,
        )
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    # -- protocol ------------------------------------------------------------------
    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        for raw in self.proc.stdout:
            self._lines.put(raw.decode("utf-8", "replace"))
        self._lines.put(None)

    def _send(self, msg: dict) -> None:
        assert self.proc and self.proc.stdin
        try:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise SandboxError(f"sandbox stdin closed: {exc}") from exc

    def _read(self, timeout: float) -> dict:
        timeout = min(timeout, max(0.1, self._deadline - time.monotonic()))
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.kill()
            raise SandboxError(f"sandbox did not respond within {timeout:.1f}s")
        if line is None:
            err = b""
            if self.proc and self.proc.stderr:
                try:
                    err = self.proc.stderr.read(2000) or b""
                except OSError:
                    pass
            raise SandboxError(f"sandbox exited unexpectedly: {err.decode('utf-8', 'replace').strip()[:500]}")
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            self.kill()
            raise SandboxError("malformed message from sandbox") from exc
        if msg.get("type") == "error":
            raise SandboxError(f"runner error: {msg.get('error')}")
        return msg

    def compile(self, source: str, time_limit_ms: int) -> CompileResult:
        self._send(
            {
                "op": "init",
                "language": self.language.to_runner_spec(),
                "source": source,
                "limits": {
                    "time_limit_ms": time_limit_ms,
                    "memory_limit_mb": self.memory_limit_mb,
                    "compile_timeout_s": self.settings.sandbox_compile_timeout_s,
                    "stdout_limit_bytes": self.settings.sandbox_stdout_limit_bytes,
                    "stderr_limit_bytes": self.settings.sandbox_stderr_limit_bytes,
                },
            }
        )
        msg = self._read(timeout=self.settings.sandbox_compile_timeout_s + 10)
        if msg.get("type") != "compiled":
            raise SandboxError(f"expected compiled, got {msg.get('type')}")
        return CompileResult(ok=bool(msg["ok"]), ms=int(msg.get("ms", 0)), output=msg.get("output", ""), skipped=bool(msg.get("skipped")))

    def run(self, test_id: int, stdin: str, time_limit_ms: int, expected_size: int | None = None) -> dict:
        self._send({"op": "run", "id": test_id, "input": stdin, "stdout_limit_bytes": stdout_limit(self.settings, expected_size)})
        # Runner enforces 2*TL+1s wall time itself; allow slack for container scheduling.
        msg = self._read(timeout=time_limit_ms / 1000 * 2 + 10)
        if msg.get("type") != "result" or msg.get("id") != test_id:
            raise SandboxError("out-of-order sandbox response")
        return msg


def reap_stale_containers(settings: Settings, older_than_s: int = 300) -> int:
    """Remove sandbox containers left behind by a crashed worker (labelled, older than N s)."""
    try:
        out = subprocess.run(
            [settings.sandbox_docker_binary, "ps", "-a", "--filter", f"label={SANDBOX_LABEL}=1",
             "--format", "{{.ID}} {{.CreatedAt}}"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("sandbox reaper could not list containers", extra={"error": str(exc)})
        return 0
    removed = 0
    now = time.time()
    for line in out.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        cid, created = parts
        try:
            ts = time.mktime(time.strptime(created[:19], "%Y-%m-%d %H:%M:%S")) - time.timezone
        except ValueError:
            continue
        if now - ts > older_than_s:
            subprocess.run([settings.sandbox_docker_binary, "rm", "-f", cid], capture_output=True, timeout=20, check=False)
            removed += 1
    if removed:
        log.info("reaped stale sandbox containers", extra={"count": removed})
    return removed
