"""Language adapters.

A language is pure configuration: the sandbox runner receives these fields and
executes argv arrays verbatim (no shell). Adding a language means adding an
entry here, installing its toolchain in the sandbox image, and inserting a row
in the ``languages`` table (migration) so submissions can reference it.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageAdapter:
    key: str
    display_name: str
    version: str
    source_filename: str
    compile_argv: tuple[str, ...] | None
    run_argv: tuple[str, ...]
    sandbox_image: str | None = None  # None -> settings.sandbox_image
    # Extra address space granted on top of the problem's memory limit, to
    # cover the runtime itself (interpreter, shared libraries). The verdict
    # still uses measured peak RSS against the *problem* limit.
    address_space_overhead_mb: int = 0
    monaco_language: str = "plaintext"
    template: str = ""
    env: dict[str, str] = field(default_factory=dict)

    def to_runner_spec(self) -> dict:
        return {
            "key": self.key,
            "source_filename": self.source_filename,
            "compile_argv": list(self.compile_argv) if self.compile_argv else None,
            "run_argv": list(self.run_argv),
            "address_space_overhead_mb": self.address_space_overhead_mb,
            "env": dict(self.env),
        }


PYTHON = LanguageAdapter(
    key="python",
    display_name="Python",
    version="3.12",
    source_filename="main.py",
    compile_argv=None,
    # -I: isolated mode (ignore env vars / user site), -B: no .pyc writes
    run_argv=("/usr/local/bin/python3", "-I", "-B", "/sandbox/main.py"),
    address_space_overhead_mb=96,
    monaco_language="python",
    template=(
        "import sys\n\n\n"
        "def main() -> None:\n"
        "    data = sys.stdin.read().split()\n"
        "    # write your solution here\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    ),
)

CPP = LanguageAdapter(
    key="cpp",
    display_name="C++17",
    version="GCC 14 · -O2",
    source_filename="main.cpp",
    compile_argv=("/usr/bin/g++", "-std=gnu++17", "-O2", "-pipe", "-o", "/sandbox/main", "/sandbox/main.cpp"),
    run_argv=("/sandbox/main",),
    address_space_overhead_mb=32,
    monaco_language="cpp",
    template=(
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    ios::sync_with_stdio(false);\n"
        "    cin.tie(nullptr);\n"
        "    // write your solution here\n"
        "    return 0;\n"
        "}\n"
    ),
)

LANGUAGES: dict[str, LanguageAdapter] = {lang.key: lang for lang in (PYTHON, CPP)}


def get_language(key: str) -> LanguageAdapter:
    try:
        return LANGUAGES[key]
    except KeyError as exc:
        raise KeyError(f"unsupported language: {key}") from exc
