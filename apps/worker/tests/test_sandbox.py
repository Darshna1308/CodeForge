"""Executes real programs in real sandbox containers."""

import pytest

from codeforge_core.config import get_settings
from codeforge_core.languages import CPP, PYTHON
from codeforge_worker.sandbox import SandboxSession, docker_run_argv, stdout_limit

from worker_helpers import requires_docker

pytestmark = [requires_docker, pytest.mark.docker]


def run(lang, src, inputs, tl=1000, mem=64):
    with SandboxSession(get_settings(), lang, 0, 0, mem) as sbx:
        comp = sbx.compile(src, tl)
        if not comp.ok:
            return comp, []
        return comp, [sbx.run(i, inp, tl) for i, inp in enumerate(inputs)]


def test_hardening_flags_present():
    argv = docker_run_argv(get_settings(), "img", "n", 256)
    joined = " ".join(argv)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--pids-limit", "--memory-swap"):
        assert flag in joined
    assert "-v" not in argv and "--privileged" not in argv and "/var/run/docker.sock" not in joined


def test_output_limit_scales_with_expected():
    s = get_settings()
    assert stdout_limit(s, None) == s.sandbox_stdout_limit_bytes
    assert stdout_limit(s, 10) == s.sandbox_stdout_limit_bytes
    assert stdout_limit(s, 3_000_000) == 6_004_096


def test_python_accepted_output_and_rusage():
    _, (r,) = run(PYTHON, "a, b = map(int, input().split())\nprint(a + b)\n", ["2 40\n"])
    assert r["status"] == "OK" and r["stdout"] == "42\n" and r["exit_code"] == 0
    assert 0 < r["max_rss_kb"] < 40_000  # the program's own RSS, not the runner's


def test_cpp_compile_error_reported():
    comp, _ = run(CPP, "int main() { return undefined_symbol; }", [])
    assert not comp.ok and "undefined_symbol" in comp.output


def test_infinite_loops_time_out():
    _, (r,) = run(CPP, "int main(){ while(true){} }", [""])
    assert r["status"] == "TLE"
    _, (r,) = run(PYTHON, "while True: pass\n", [""])
    assert r["status"] == "TLE" and r["wall_ms"] < 4000


def test_runtime_errors():
    _, (r,) = run(CPP, "int main(){ volatile int *p = 0; *p = 1; }", [""])
    assert r["status"] == "RE" and r["signal"] == 11
    _, (r,) = run(PYTHON, "raise SystemExit(3)\n", [""])
    assert r["status"] == "RE" and r["exit_code"] == 3


def test_memory_limit():
    _, (r,) = run(PYTHON, "x = bytearray(200 * 1024 * 1024)\n", [""], mem=64)
    assert r["status"] == "MLE"
    _, (r,) = run(CPP, "#include <vector>\nint main(){ std::vector<char> v(300u<<20, 1); return v[7] - 1; }", [""], mem=64)
    assert r["status"] == "MLE"


def test_output_flood_is_killed():
    _, (r,) = run(PYTHON, "while True:\n    print('x' * 8192)\n", [""])
    assert r["status"] == "OLE" and r["stdout_truncated"]


def test_sandbox_is_unprivileged_offline_and_readonly():
    src = (
        "import os, socket\n"
        "print(os.getuid(), os.getgid())\n"
        "try:\n    os.kill(1, 9); print('KILLED_PID1')\nexcept PermissionError: print('kill-denied')\n"
        "try:\n    socket.create_connection(('1.1.1.1', 80), timeout=2); print('NET')\nexcept OSError: print('no-net')\n"
        "try:\n    open('/etc/pwn', 'w'); print('WROTE')\nexcept OSError: print('ro-fs')\n"
        "print(os.path.exists('/var/run/docker.sock'))\n"
    )
    _, (r,) = run(PYTHON, src, [""])
    assert r["stdout"].split("\n")[:5] == ["65534 65534", "kill-denied", "no-net", "ro-fs", "False"]


def test_fork_bomb_is_contained():
    _, (r,) = run(CPP, "#include <unistd.h>\nint main(){ while(1) fork(); }", [""])
    assert r["status"] in ("TLE", "RE")


def test_multiple_tests_share_one_sandbox():
    _, results = run(PYTHON, "print(int(input()) * 2)\n", ["1\n", "2\n", "3\n"])
    assert [r["stdout"] for r in results] == ["2\n", "4\n", "6\n"]
