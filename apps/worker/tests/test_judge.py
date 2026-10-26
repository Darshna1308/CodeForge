import pytest

from codeforge_core.enums import TestVerdict as T, Verdict as V
from codeforge_worker.judge import aggregate, judge_test, normalize, outputs_match


@pytest.mark.parametrize("actual,expected,ok", [
    ("1 2\n", "1 2", True),            # trailing newline
    ("1 2   \n\n\n", "1 2\n", True),   # trailing spaces / blank lines
    ("1 2\r\n3\r\n", "1 2\n3\n", True),  # CRLF
    ("1  2\n", "1 2\n", False),        # inner spacing matters
    (" 1 2\n", "1 2\n", False),        # leading whitespace matters
    ("True\n", "true\n", False),       # case matters
    ("", "0\n", False),
])
def test_normalization_policy(actual, expected, ok):
    assert outputs_match(actual, expected) is ok


def test_normalize_is_idempotent():
    s = "a \r\nb\t\n\n"
    assert normalize(normalize(s)) == normalize(s) == "a\nb"


def test_runner_status_maps_before_comparison():
    assert judge_test({"status": "TLE", "stdout": "correct"}, "correct") == T.TIME_LIMIT_EXCEEDED
    assert judge_test({"status": "OK", "stdout": "5\n"}, "5") == T.ACCEPTED
    assert judge_test({"status": "OK", "stdout": "6\n"}, "5") == T.WRONG_ANSWER
    assert judge_test({"status": "OK", "stdout": "anything"}, None) == T.EXECUTED


def test_aggregate_takes_first_failure():
    assert aggregate([T.ACCEPTED, T.ACCEPTED]) == V.ACCEPTED
    assert aggregate([T.ACCEPTED, T.RUNTIME_ERROR, T.SKIPPED]) == V.RUNTIME_ERROR
    assert aggregate([T.WRONG_ANSWER, T.TIME_LIMIT_EXCEEDED]) == V.WRONG_ANSWER
    assert aggregate([T.EXECUTED]) == V.EXECUTED
