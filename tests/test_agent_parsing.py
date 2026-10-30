"""Unit tests for how the agent cleans up model output (no API calls)."""
from agent.agent import categories, clean


def test_categories_accepts_a_normal_list():
    assert categories(["external_provider", "stuck_worker"]) == ["external_provider", "stuck_worker"]


def test_categories_accepts_the_list_sent_as_a_string():
    # the likely cause of the 'unknown' root causes seen in the first held-out run
    assert categories('["external_provider", "stuck_worker"]') == ["external_provider", "stuck_worker"]
    assert categories("['external_provider']") == ["external_provider"]
    assert categories("external_provider, stuck_worker") == ["external_provider", "stuck_worker"]


def test_categories_ignores_case_whitespace_duplicates_and_junk():
    assert categories([" Stuck_Worker ", "stuck_worker", "banana"]) == ["stuck_worker"]


def test_categories_falls_back_to_unknown():
    assert categories([]) == ["unknown"]
    assert categories(None) == ["unknown"]
    assert categories("nothing valid here") == ["unknown"]


def test_clean_cuts_stray_markup_and_truncates():
    assert clean("provider is down</root_cause_guess><parameter name='x'>junk") == "provider is down"
    assert clean("a < b is fine") == "a < b is fine"
    assert clean("x" * 400, 50).endswith("…") and len(clean("x" * 400, 50)) == 50
