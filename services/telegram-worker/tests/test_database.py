from __future__ import annotations

import sqlite3

import pytest

from chatrd_worker.models import RuleType, ValidationError


def test_defaults_and_setting_validation(database) -> None:
    assert database.get_settings()["delivery_mode"] == "copy"
    database.update_settings({"delivery_mode": "forward", "paused": False})
    assert database.get_settings()["delivery_mode"] == "forward"
    with pytest.raises(ValidationError):
        database.update_settings({"unknown": True})


def test_sources_and_destination_cannot_overlap(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    with pytest.raises(ValidationError):
        database.update_settings({"destination_peer_id": -1001})


def test_source_scan_bounds(database) -> None:
    with pytest.raises(ValidationError):
        database.upsert_source(
            peer_id=-1001,
            enabled=True,
            initial_scan_mode="latest_count",
            initial_scan_value=0,
        )
    source = database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="latest_count",
        initial_scan_value=25,
    )
    assert source.initial_scan_value == 25


def test_rule_crud_and_global_filtering(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    global_rule = database.create_rule(
        source_peer_id=None, rule_type="hashtag", pattern="decision"
    )
    local_rule = database.create_rule(
        source_peer_id=-1001,
        rule_type="keyword",
        pattern="release",
        whole_word=True,
    )
    assert [rule.id for rule in database.list_rules(-1001)] == [
        global_rule.id,
        local_rule.id,
    ]
    updated = database.update_rule(local_rule.id, {"enabled": False})
    assert updated.enabled is False
    database.delete_rule(local_rule.id)
    assert database.get_rule(local_rule.id) is None


def test_processing_uniqueness_and_cursor_transaction(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    database.record_no_match(-1001, 10, "2026-07-25T00:00:00+00:00")
    database.record_no_match(-1001, 10, "2026-07-25T00:00:00+00:00")
    assert database.processing_counts() == {"no_match": 1}
    assert database.get_cursor(-1001) == 10


def test_pending_send_reuses_persisted_id_and_finishes_atomically(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    first = database.begin_pending(
        source_peer_id=-1001,
        source_message_id=11,
        source_timestamp="2026-07-25T00:00:00+00:00",
        matched_rule_ids=["r1"],
        random_id=123,
        destination_peer_id=42,
    )
    second = database.begin_pending(
        source_peer_id=-1001,
        source_message_id=11,
        source_timestamp="2026-07-25T00:00:00+00:00",
        matched_rule_ids=["other"],
        random_id=999,
        destination_peer_id=42,
    )
    assert first["delivery_random_id"] == second["delivery_random_id"] == 123
    database.record_sent(-1001, 11, 501)
    assert database.processing_row(-1001, 11)["outcome"] == "sent"
    assert database.get_cursor(-1001) == 11


def test_foreign_keys_are_enabled(database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        database.create_rule(
            source_peer_id=-999,
            rule_type=RuleType.KEYWORD.value,
            pattern="missing",
        )

