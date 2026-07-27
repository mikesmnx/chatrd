from __future__ import annotations

from datetime import UTC, datetime

from chatrd_worker.formatter import TELEGRAM_TEXT_LIMIT, format_copy, source_message_link
from chatrd_worker.models import MessageEnvelope, Rule, RuleType


def message(**values) -> MessageEnvelope:
    defaults = {
        "source_peer_id": -1001234,
        "source_message_id": 77,
        "source_timestamp": datetime(2026, 7, 25, 11, 35, tzinfo=UTC),
        "source_name": "Project <Alpha>",
        "text": "Use <b>literal</b> & safe",
        "author_name": "Alex & Sam",
        "source_username": "projectalpha",
        "source_peer_type": "supergroup",
    }
    defaults.update(values)
    return MessageEnvelope(**defaults)


def test_format_copy_escapes_content_and_includes_link() -> None:
    output = format_copy(
        message(),
        (Rule("r", None, RuleType.PHRASE, "production release"),),
        local_timezone=UTC,
    ).text
    assert "Project &lt;Alpha&gt;" in output
    assert "Alex &amp; Sam" in output
    assert "Use &lt;b&gt;literal&lt;/b&gt; &amp; safe" in output
    assert 'href="https://t.me/projectalpha/77"' in output
    assert "#production_release" in output


def test_private_supergroup_link_and_unavailable_private_link() -> None:
    private = message(source_username=None)
    assert source_message_link(private) == "https://t.me/c/1234/77"
    assert source_message_link(
        message(source_peer_id=99, source_username=None, source_peer_type="user")
    ) is None


def test_long_content_is_truncated_within_limit_without_broken_escape() -> None:
    output = format_copy(
        message(text="<" * 10_000),
        (Rule("r", None, RuleType.HASHTAG, "#decision"),),
        local_timezone=UTC,
    ).text
    assert len(output) <= TELEGRAM_TEXT_LIMIT
    assert "[текст сокращён]" in output
    assert output.count("&lt;") > 100


def test_missing_author_and_link_are_safe() -> None:
    output = format_copy(
        message(author_name=None, source_username=None, source_peer_type="group"),
        (Rule("r", None, RuleType.KEYWORD, "release"),),
        local_timezone=UTC,
    ).text
    assert "Не указан" in output
    assert "Открыть исходное сообщение" not in output
