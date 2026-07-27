from __future__ import annotations

import pytest

from chatrd_worker.matcher import match_message, normalize_text, validate_rule
from chatrd_worker.models import Rule, RuleType, ValidationError


def rule(
    pattern: str,
    *,
    kind: RuleType = RuleType.KEYWORD,
    case_sensitive: bool = False,
    whole_word: bool = False,
    enabled: bool = True,
) -> Rule:
    return Rule("r1", None, kind, pattern, case_sensitive, whole_word, enabled)


@pytest.mark.parametrize(
    ("text", "configured", "kind", "whole_word", "expected"),
    [
        ("Production ISSUE found", "production issue", RuleType.KEYWORD, False, True),
        ("concatenate", "cat", RuleType.KEYWORD, True, False),
        ("a cat!", "cat", RuleType.KEYWORD, True, True),
        ("#Action now", "action", RuleType.HASHTAG, False, True),
        ("#actionable", "#action", RuleType.HASHTAG, False, False),
        ("say hello, world", "hello, world", RuleType.PHRASE, False, True),
        ("добрый ДЕНЬ", "Добрый день", RuleType.PHRASE, False, True),
        ("x_foo", "foo", RuleType.KEYWORD, True, False),
        ("🔥#todo.", "todo", RuleType.HASHTAG, False, True),
    ],
)
def test_matching_semantics(
    text: str, configured: str, kind: RuleType, whole_word: bool, expected: bool
) -> None:
    result = match_message(text, [rule(configured, kind=kind, whole_word=whole_word)])
    assert result.matched is expected


def test_nfc_and_casefold_are_used() -> None:
    composed = "Café STRASSE"
    decomposed = "Cafe\u0301 straße"
    assert normalize_text(composed, case_sensitive=False) == normalize_text(
        decomposed, case_sensitive=False
    )


def test_case_sensitive_rule_and_disabled_rule() -> None:
    assert not match_message("Action", [rule("action", case_sensitive=True)]).matched
    assert not match_message("action", [rule("action", enabled=False)]).matched


def test_returns_all_matches_in_input_order() -> None:
    rules = [
        Rule("first", None, RuleType.KEYWORD, "release"),
        Rule("second", None, RuleType.HASHTAG, "#decision"),
    ]
    result = match_message("Release #decision", rules)
    assert [item.id for item in result.matched_rules] == ["first", "second"]


@pytest.mark.parametrize(
    ("kind", "pattern", "whole_word"),
    [
        (RuleType.KEYWORD, "   ", False),
        (RuleType.HASHTAG, "#has space", False),
        (RuleType.PHRASE, "okay", True),
        (RuleType.KEYWORD, "x" * 257, False),
    ],
)
def test_invalid_rules(kind: RuleType, pattern: str, whole_word: bool) -> None:
    with pytest.raises(ValidationError):
        validate_rule(kind, pattern, whole_word)


def test_empty_message_never_matches() -> None:
    assert not match_message(None, [rule("anything")]).matched
    assert not match_message("", [rule("anything")]).matched

