from __future__ import annotations

import sqlite3

import pytest

from chatrd_worker.database import Database
from chatrd_worker.models import RuleType, ValidationError


def test_defaults_and_setting_validation(database) -> None:
    assert database.get_settings()["delivery_mode"] == "copy"
    assert database.get_settings()["ollama_model"] == "gpt-oss:20b"
    assert database.get_settings()["ai_enabled"] is False
    database.update_settings({"delivery_mode": "forward", "paused": False})
    assert database.get_settings()["delivery_mode"] == "forward"
    with pytest.raises(ValidationError):
        database.update_settings({"unknown": True})


def test_ollama_settings_validation(database) -> None:
    updated = database.update_settings(
        {
            "ai_enabled": True,
            "ollama_base_url": "http://localhost:11434/",
            "ollama_model": "gpt-oss:20b",
            "ollama_prompt": "  Отбирай сообщения о релизах.  ",
            "ollama_timeout_seconds": "90",
            "ollama_temperature": "0.2",
        }
    )
    assert updated["ollama_base_url"] == "http://localhost:11434"
    assert updated["ollama_prompt"] == "Отбирай сообщения о релизах."
    assert updated["ollama_timeout_seconds"] == 90
    assert updated["ollama_temperature"] == 0.2


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"ai_enabled": "yes"}, "true or false"),
        ({"ollama_base_url": "file:///tmp/ollama"}, "HTTP or HTTPS"),
        ({"ollama_base_url": None}, "HTTP or HTTPS"),
        ({"ollama_base_url": "http://user:pass@localhost:11434"}, "HTTP or HTTPS"),
        ({"ollama_model": ""}, "model is required"),
        ({"ollama_model": None}, "model is required"),
        ({"ollama_prompt": "x" * 4001}, "4,000"),
        ({"ollama_prompt": None}, "must be text"),
        ({"ollama_timeout_seconds": "fast"}, "must be a number"),
        ({"ollama_timeout_seconds": 4}, "between 5 and 600"),
        ({"ollama_temperature": "warm"}, "must be a number"),
        ({"ollama_temperature": 2.1}, "between 0 and 2"),
        ({"ollama_temperature": float("nan")}, "between 0 and 2"),
    ],
)
def test_invalid_ollama_settings_are_rejected(database, values, message) -> None:
    with pytest.raises(ValidationError, match=message):
        database.update_settings(values)


def test_ai_matching_requires_instructions(database) -> None:
    with pytest.raises(ValidationError, match="instructions are required"):
        database.update_settings({"ai_enabled": True})


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


def test_ai_rule_crud_defaults_to_forwarded_messages(database) -> None:
    rule = database.create_ai_rule(
        prompt="  Отбирай сообщения о рисках.  ",
        action_prompt="  Сделай краткое резюме.  ",
    )
    assert rule.prompt == "Отбирай сообщения о рисках."
    assert rule.action_prompt == "Сделай краткое резюме."
    assert rule.apply_to.value == "forwarded"
    assert database.list_ai_rules() == [rule]

    updated = database.update_ai_rule(
        rule.id,
        {
            "prompt": "Отбирай релизы.",
            "action_prompt": "Переведи на русский.",
            "apply_to": "all",
            "enabled": False,
        },
    )
    assert updated.prompt == "Отбирай релизы."
    assert updated.action_prompt == "Переведи на русский."
    assert updated.apply_to.value == "all"
    assert updated.enabled is False

    database.delete_ai_rule(rule.id)
    assert database.get_ai_rule(rule.id) is None


def test_legacy_enabled_ai_prompt_migrates_to_all_messages_rule(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    legacy = Database(path)
    legacy.update_settings(
        {"ollama_prompt": "Legacy selection", "ai_enabled": True}
    )
    with legacy.transaction() as connection:
        connection.execute("DELETE FROM ai_rules")
        connection.execute("DELETE FROM schema_migrations WHERE version=2")
    legacy.close()

    migrated = Database(path)
    rules = migrated.list_ai_rules()
    assert [(rule.prompt, rule.apply_to.value) for rule in rules] == [
        ("Legacy selection", "all")
    ]
    assert rules[0].action_prompt == ""
    migrated.close()


def test_version_two_ai_rules_gain_action_prompt_column(tmp_path) -> None:
    path = tmp_path / "version-two.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        INSERT INTO schema_migrations(version, applied_at) VALUES (2, 'now');
        CREATE TABLE ai_rules (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            apply_to TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO ai_rules VALUES (
            'old-rule', 'Legacy filter', 'forwarded', 1, 'now', 'now'
        );
        """
    )
    connection.commit()
    connection.close()

    migrated = Database(path)
    assert migrated.get_ai_rule("old-rule").action_prompt == ""  # type: ignore[union-attr]
    migrated.close()


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"prompt": ""}, "cannot be empty"),
        ({"prompt": "x" * 4001}, "4,000"),
        ({"prompt": None}, "must be text"),
        ({"action_prompt": ""}, "action prompt cannot be empty"),
        ({"apply_to": "sometimes"}, "forwarded or all"),
        ({"enabled": "yes"}, "true or false"),
    ],
)
def test_invalid_ai_rules_are_rejected(database, values, message) -> None:
    if "prompt" in values:
        with pytest.raises(ValidationError, match=message):
            database.create_ai_rule(
                prompt=values["prompt"],
                action_prompt="Valid action",
                apply_to=values.get("apply_to", "forwarded"),
            )
        return

    rule = database.create_ai_rule(prompt="Valid prompt", action_prompt="Valid action")
    with pytest.raises(ValidationError, match=message):
        database.update_ai_rule(rule.id, values)


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
