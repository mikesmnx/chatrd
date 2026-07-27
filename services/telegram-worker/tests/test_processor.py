from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chatrd_worker.models import (
    MessageEnvelope,
    PermanentTelegramError,
    TransientTelegramError,
)
from chatrd_worker.processor import MessageProcessor
from fakes import FakeGateway


def envelope(message_id: int, text: str = "release #decision") -> MessageEnvelope:
    return MessageEnvelope(
        source_peer_id=-1001,
        source_message_id=message_id,
        source_timestamp=datetime(2026, 7, 25, tzinfo=UTC),
        source_name="Source One",
        text=text,
        author_name="Alex",
        source_username="source_one",
        source_peer_type="supergroup",
    )


@pytest.fixture
def configured(database):
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )
    database.create_rule(
        source_peer_id=-1001, rule_type="hashtag", pattern="#decision"
    )
    return database


async def test_multiple_matches_send_once_and_advance_cursor(configured) -> None:
    gateway = FakeGateway()
    processor = MessageProcessor(configured, gateway, account_id=7)
    assert await processor.process(envelope(1)) == "sent"
    assert len(gateway.sent) == 1
    assert configured.get_cursor(-1001) == 1
    assert len(configured.processing_row(-1001, 1)["matched_rule_ids_json"]) > 2


async def test_no_match_is_terminal_without_send(configured) -> None:
    gateway = FakeGateway()
    processor = MessageProcessor(configured, gateway, account_id=7)
    assert await processor.process(envelope(2, "nothing relevant")) == "no_match"
    assert gateway.sent == []
    assert configured.get_cursor(-1001) == 2


async def test_repeated_terminal_message_is_deduplicated(configured) -> None:
    gateway = FakeGateway()
    processor = MessageProcessor(configured, gateway, account_id=7)
    await processor.process(envelope(3))
    await processor.process(envelope(3))
    assert len(gateway.sent) == 1


async def test_transient_failure_keeps_pending_and_retry_reuses_random_id(configured) -> None:
    gateway = FakeGateway()
    gateway.next_error = TransientTelegramError("offline")
    processor = MessageProcessor(configured, gateway, account_id=7)
    with pytest.raises(TransientTelegramError):
        await processor.process(envelope(4))
    pending = configured.processing_row(-1001, 4)
    assert pending["outcome"] == "pending"
    original_id = pending["delivery_random_id"]
    assert await processor.process(envelope(4)) == "sent"
    assert gateway.sent[0][2] == original_id


async def test_permanent_failure_blocks_until_explicit_action(configured) -> None:
    gateway = FakeGateway()
    gateway.next_error = PermanentTelegramError("forbidden")
    processor = MessageProcessor(configured, gateway, account_id=7)
    assert await processor.process(envelope(5)) == "permanently_failed"
    assert configured.get_cursor(-1001) is None
    assert await processor.process(envelope(5)) == "permanently_failed"
    configured.skip_failure(-1001, 5)
    assert configured.get_cursor(-1001) == 5


async def test_native_forward_mode(configured) -> None:
    configured.update_settings({"delivery_mode": "forward"})
    gateway = FakeGateway()
    processor = MessageProcessor(configured, gateway, account_id=7)
    assert await processor.process(envelope(6)) == "sent"
    assert gateway.sent == []
    assert gateway.forwarded[0][:3] == (42, -1001, 6)

