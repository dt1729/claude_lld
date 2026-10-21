"""Behaviour of the controlled-language subset used for diagram labels and captions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ste import Violation, check_caption, check_label, is_technical_name, report


def rules(violations: list[Violation]) -> list[str]:
    return [v.rule for v in violations]


# --- labels ---------------------------------------------------------------------------------


def test_an_approved_verb_passes() -> None:
    assert check_label("raises") == []


def test_a_verb_outside_the_list_is_refused() -> None:
    assert "verb is not approved" in rules(check_label("triggers"))


def test_two_words_on_one_arrow_are_refused() -> None:
    assert "one verb per edge" in rules(check_label("may import"))


def test_an_empty_label_is_refused() -> None:
    assert "empty" in rules(check_label("  "))


# --- technical names ---------------------------------------------------------------------------


def test_camel_case_is_a_technical_name() -> None:
    assert is_technical_name("InvalidSideError")


def test_snake_case_is_a_technical_name() -> None:
    assert is_technical_name("side_m")


def test_a_dotted_path_is_a_technical_name() -> None:
    assert is_technical_name("shapes.square")


def test_a_plain_word_is_not() -> None:
    assert not is_technical_name("module")


# --- captions ------------------------------------------------------------------------------------


def test_a_caption_in_the_subset_passes() -> None:
    assert check_caption("Each arrow shows a module and a module it imports.") == []


def test_a_technical_name_passes_through_a_caption() -> None:
    assert check_caption("Each arrow shows InvalidSideError and its base.") == []


def test_passive_voice_is_refused() -> None:
    assert "passive voice" in rules(check_caption("The name is matched as text."))


def test_a_gerund_used_as_a_noun_is_refused() -> None:
    assert "gerund used as a noun" in rules(check_caption("The arrow shows the parsing."))


def test_an_approved_technical_gerund_passes() -> None:
    """logging is a technical noun here, not a verb form."""
    assert check_caption("Each module shows its logging.") == []


def test_a_long_sentence_is_refused() -> None:
    long = "Each arrow " + "and each box " * 10 + "shows a module."
    assert any("longer than" in r for r in rules(check_caption(long)))


def test_an_unapproved_word_is_refused() -> None:
    assert "word is not in the approved set" in rules(check_caption("The arrow depicts a module."))


# --- reporting -------------------------------------------------------------------------------------


def test_a_clean_report_says_so() -> None:
    assert report([]) == "every label and caption stays in the approved subset"


def test_a_report_carries_the_fix() -> None:
    assert "use one of" in report(check_label("triggers"))
