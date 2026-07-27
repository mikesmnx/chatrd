from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from .models import MatchResult, Rule, RuleType, ValidationError


def normalize_text(value: str, *, case_sensitive: bool) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return normalized if case_sensitive else normalized.casefold()


def validate_rule(rule_type: RuleType, pattern: str, whole_word: bool = False) -> str:
    pattern = unicodedata.normalize("NFC", pattern.strip())
    if not pattern:
        raise ValidationError("Rule pattern cannot be empty")
    if len(pattern) > 256:
        raise ValidationError("Rule pattern cannot exceed 256 characters")
    if rule_type is RuleType.HASHTAG:
        pattern = pattern[1:] if pattern.startswith("#") else pattern
        if not pattern or not all(_is_word_character(char) for char in pattern):
            raise ValidationError("A hashtag may contain only letters, numbers, and underscores")
        return f"#{pattern}"
    if whole_word and rule_type is not RuleType.KEYWORD:
        raise ValidationError("Whole-word matching is available only for keyword rules")
    return pattern


def match_message(text: str | None, rules: Iterable[Rule]) -> MatchResult:
    if not text:
        return MatchResult(())

    matched: list[Rule] = []
    for rule in rules:
        if not rule.enabled:
            continue
        pattern = validate_rule(rule.type, rule.pattern, rule.whole_word)
        haystack = normalize_text(text, case_sensitive=rule.case_sensitive)
        needle = normalize_text(pattern, case_sensitive=rule.case_sensitive)

        if rule.type is RuleType.HASHTAG:
            is_match = _contains_token(haystack, needle, hashtag=True)
        elif rule.type is RuleType.KEYWORD and rule.whole_word:
            is_match = _contains_token(haystack, needle, hashtag=False)
        else:
            is_match = needle in haystack

        if is_match:
            matched.append(rule)

    return MatchResult(tuple(matched))


def _contains_token(haystack: str, needle: str, *, hashtag: bool) -> bool:
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index > 0 else None
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else None

        before_ok = before is None or not _is_word_character(before)
        if hashtag and before == "#":
            before_ok = False
        after_ok = after is None or not _is_word_character(after)
        if before_ok and after_ok:
            return True
        start = index + 1


def _is_word_character(value: str) -> bool:
    return value == "_" or value.isalnum()

