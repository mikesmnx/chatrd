from __future__ import annotations

from chatrd_worker.application import WorkerApplication
import pytest

from chatrd_worker.models import TelegramPeer, TransientTelegramError, ValidationError
from chatrd_worker.ollama import OllamaClient
from fakes import FakeGateway


async def test_offline_logout_still_clears_local_gateway(tmp_path) -> None:
    application = WorkerApplication(tmp_path)
    gateway = FakeGateway()
    gateway.logout_error = TransientTelegramError("offline")
    application.gateway = gateway  # type: ignore[assignment]

    result = await application.dispatch("auth.logout", {})

    assert result == {"ok": True, "remotely_revoked": False}
    assert application.gateway is None
    application.database.close()


async def test_online_logout_reports_revocation(tmp_path) -> None:
    application = WorkerApplication(tmp_path)
    gateway = FakeGateway()
    application.gateway = gateway  # type: ignore[assignment]

    result = await application.dispatch("auth.logout", {})

    assert result == {"ok": True, "remotely_revoked": True}
    assert gateway.authorized is False
    application.database.close()


async def test_ollama_chat_returns_the_model_answer(tmp_path, monkeypatch) -> None:
    application = WorkerApplication(tmp_path)

    async def fake_chat(_client, message, settings):
        assert message == "Hello"
        assert settings["ollama_model"] == "gpt-oss:20b"
        return {"model": "gpt-oss:20b", "message": "Hi there"}

    monkeypatch.setattr(OllamaClient, "chat", fake_chat)
    assert await application.dispatch("ollama.chat", {"message": "Hello"}) == {
        "model": "gpt-oss:20b",
        "message": "Hi there",
    }
    with pytest.raises(ValidationError, match="test message is required"):
        await application.dispatch("ollama.chat", {"message": None})
    application.database.close()


async def test_testing_evaluate_uses_only_applicable_enabled_rules(tmp_path) -> None:
    application = WorkerApplication(tmp_path)
    application.database.replace_peers(
        [
            TelegramPeer(-1001, "supergroup", "Source One", None, True),
            TelegramPeer(-1002, "supergroup", "Source Two", None, True),
            TelegramPeer(42, "user", "Saved Messages", None, True),
        ]
    )
    application.database.update_settings(
        {
            "destination_peer_id": 42,
            "ai_enabled": True,
            "ollama_prompt": "This must not run during literal-rule testing.",
        }
    )
    for peer_id in (-1001, -1002):
        application.database.upsert_source(
            peer_id=peer_id,
            enabled=True,
            initial_scan_mode="now",
            initial_scan_value=None,
        )

    global_rule = application.database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )
    local_rule = application.database.create_rule(
        source_peer_id=-1001, rule_type="hashtag", pattern="urgent"
    )
    other_source_rule = application.database.create_rule(
        source_peer_id=-1002, rule_type="phrase", pattern="other source"
    )
    disabled_rule = application.database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="disabled"
    )
    application.database.update_rule(disabled_rule.id, {"enabled": False})
    gateway = FakeGateway()
    application.gateway = gateway  # type: ignore[assignment]

    result = await application.dispatch(
        "testing.evaluate",
        {
            "source_peer_id": -1001,
            "message": "Release details #urgent, disabled and other source",
        },
    )

    assert result["would_send"] is True
    assert result["reason"] == "matched_rules"
    assert [rule["id"] for rule in result["evaluated_rules"]] == [
        global_rule.id,
        local_rule.id,
    ]
    assert all(rule["matched"] for rule in result["evaluated_rules"])
    assert other_source_rule.id not in {
        rule["id"] for rule in result["evaluated_rules"]
    }
    assert application.database.processing_counts() == {}
    assert gateway.sent == []
    assert gateway.forwarded == []
    application.database.close()


async def test_testing_evaluate_reports_no_match_and_validates_input(tmp_path) -> None:
    application = WorkerApplication(tmp_path)
    application.database.replace_peers(
        [TelegramPeer(-1001, "supergroup", "Source One", None, True)]
    )
    application.database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    application.database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )

    result = await application.dispatch(
        "testing.evaluate", {"source_peer_id": -1001, "message": "Nothing relevant"}
    )
    assert result["matched"] is False
    assert result["would_send"] is False
    assert result["reason"] == "no_match"
    assert result["evaluated_rules"][0]["matched"] is False

    with pytest.raises(ValidationError, match="configured source"):
        await application.dispatch(
            "testing.evaluate", {"source_peer_id": -9999, "message": "release"}
        )
    with pytest.raises(ValidationError, match="Test message is required"):
        await application.dispatch(
            "testing.evaluate", {"source_peer_id": -1001, "message": "   "}
        )
    application.database.close()
