"""Unit tests for Control Advisor's pure input-parsing helpers — the logic
most prone to silently misreading a user's answer, which is exactly what this
tool is meant to avoid."""
import cli


# --- _parse_draft_count --------------------------------------------------

def test_parse_draft_count_bare_number():
    assert cli._parse_draft_count("3", 10) == 3


def test_parse_draft_count_embedded_number():
    assert cli._parse_draft_count("draft 5 please", 10) == 5


def test_parse_draft_count_clamps_to_max():
    assert cli._parse_draft_count("99", 10) == 10


def test_parse_draft_count_all_phrasing():
    assert cli._parse_draft_count("all of them", 10) == 10


def test_parse_draft_count_none_phrasing():
    assert cli._parse_draft_count("none", 10) == 0


def test_parse_draft_count_empty_defaults_to_zero():
    assert cli._parse_draft_count("", 10) == 0


def test_parse_draft_count_ambiguous_returns_none():
    # Genuinely ambiguous input must return None so the caller re-prompts
    # instead of silently guessing 0.
    assert cli._parse_draft_count("write for the ones that matter", 10) is None


# --- _sanitize_folder_name ----------------------------------------------

def test_sanitize_strips_illegal_characters():
    assert cli._sanitize_folder_name('Acme: Corp/Inc*') == "Acme CorpInc"


def test_sanitize_trims_trailing_dots():
    assert cli._sanitize_folder_name("Acme...") == "Acme"


def test_sanitize_empty_falls_back_to_default():
    assert cli._sanitize_folder_name("   ") == "Unnamed Organization"
