"""Unit tests for the demo's pure text helpers (the demo itself only prints; it makes no decisions)."""
from demo.run import failing_lines, short, split_verification

SUMMARY = ("INVARIANTS FAILING\nok   requests_vs_saved: requests=10 missing=0\n"
           "FAIL payment_success: 30 of 80 checkouts failed\nFAIL replica_checksum: copied=a replica=b")


def test_failing_lines_keeps_only_the_fail_lines():
    assert failing_lines(SUMMARY) == ["payment_success: 30 of 80 checkouts failed", "replica_checksum: copied=a replica=b"]
    assert failing_lines("ALL INVARIANTS OK\nok   a: x") == []


def test_split_verification_separates_result_status_and_failures():
    text = 'action result: {"rolled_back": true}\nverification after 5s:\n' + SUMMARY
    result, status, bad = split_verification(text)
    assert result == '{"rolled_back": true}'
    assert status == "INVARIANTS FAILING" or status.startswith("INVARIANTS")
    assert len(bad) == 2


def test_split_verification_without_a_verification_block():
    result, status, bad = split_verification('action result: {"requeued": 1}')
    assert status is None and bad == [] and "requeued" in result


def test_short_collapses_whitespace_and_truncates():
    assert short("a   b\nc") == "a b c"
    assert short("x" * 200, 20).endswith("...") and len(short("x" * 200, 20)) == 20
