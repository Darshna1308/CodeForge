"""Output comparison and verdict aggregation.

Normalisation policy (documented in docs/EXECUTION_ENGINE.md):
  1. Decode as UTF-8 (invalid bytes replaced).
  2. Normalise line endings: CRLF and CR -> LF.
  3. Strip trailing whitespace (spaces/tabs) from every line.
  4. Drop trailing empty lines at the end of the output.
Everything else, including leading whitespace, inner spacing and letter case,
must match exactly. This tolerates the usual "extra newline / trailing space"
noise without accepting genuinely different answers.
"""

from codeforge_core.enums import TestVerdict, Verdict

RUNNER_STATUS_TO_VERDICT = {
    "TLE": TestVerdict.TIME_LIMIT_EXCEEDED,
    "MLE": TestVerdict.MEMORY_LIMIT_EXCEEDED,
    "OLE": TestVerdict.OUTPUT_LIMIT_EXCEEDED,
    "RE": TestVerdict.RUNTIME_ERROR,
}

TEST_TO_SUBMISSION_VERDICT = {
    TestVerdict.ACCEPTED: Verdict.ACCEPTED,
    TestVerdict.WRONG_ANSWER: Verdict.WRONG_ANSWER,
    TestVerdict.RUNTIME_ERROR: Verdict.RUNTIME_ERROR,
    TestVerdict.TIME_LIMIT_EXCEEDED: Verdict.TIME_LIMIT_EXCEEDED,
    TestVerdict.MEMORY_LIMIT_EXCEEDED: Verdict.MEMORY_LIMIT_EXCEEDED,
    TestVerdict.OUTPUT_LIMIT_EXCEEDED: Verdict.OUTPUT_LIMIT_EXCEEDED,
    TestVerdict.EXECUTED: Verdict.EXECUTED,
}


def normalize(output: str) -> str:
    lines = output.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip(" \t") for line in lines]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def outputs_match(actual: str, expected: str) -> bool:
    return normalize(actual) == normalize(expected)


def judge_test(runner_result: dict, expected: str | None) -> TestVerdict:
    status = runner_result["status"]
    if status != "OK":
        return RUNNER_STATUS_TO_VERDICT.get(status, TestVerdict.RUNTIME_ERROR)
    if expected is None:  # custom input: nothing to compare against
        return TestVerdict.EXECUTED
    return TestVerdict.ACCEPTED if outputs_match(runner_result.get("stdout", ""), expected) else TestVerdict.WRONG_ANSWER


def aggregate(test_verdicts: list[TestVerdict]) -> Verdict:
    """Submission verdict = first non-passing test's verdict (tests run in order)."""
    for v in test_verdicts:
        if v not in (TestVerdict.ACCEPTED, TestVerdict.EXECUTED, TestVerdict.SKIPPED):
            return TEST_TO_SUBMISSION_VERDICT[v]
    if test_verdicts and all(v == TestVerdict.EXECUTED for v in test_verdicts):
        return Verdict.EXECUTED
    return Verdict.ACCEPTED
