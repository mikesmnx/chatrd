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
    assert "Release details #urgent" in result["copy_preview_html"]
    assert "<b>Совпадение:</b> release, #urgent" in result["copy_preview_html"]
    assert other_source_rule.id not in {
        rule["id"] for rule in result["evaluated_rules"]
    }
    assert application.database.processing_counts() == {}
    assert gateway.sent == []
    assert gateway.forwarded == []
    application.database.close()


async def test_testing_evaluate_includes_ai_rules_and_forwarded_applicability(
    tmp_path, monkeypatch
) -> None:
    application = WorkerApplication(tmp_path)
    application.database.replace_peers(
        [
            TelegramPeer(-1001, "supergroup", "Source One", None, True),
            TelegramPeer(42, "user", "Saved Messages", None, True),
        ]
    )
    application.database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    application.database.update_settings({"destination_peer_id": 42})
    application.database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )
    forwarded_rule = application.database.create_ai_rule(
        prompt="Match risks",
        action_prompt="Summarize the risk",
        apply_to="forwarded",
    )
    all_rule = application.database.create_ai_rule(
        prompt="Match celebrations",
        action_prompt="Write a congratulation",
        apply_to="all",
    )
    disabled_rule = application.database.create_ai_rule(
        prompt="Disabled", action_prompt="Do nothing", apply_to="all"
    )
    application.database.update_ai_rule(disabled_rule.id, {"enabled": False})
    calls: list[str] = []

    async def fake_classify(_client, text, settings):
        assert text == "Release risk"
        calls.append(settings["ollama_prompt"])
        return settings["ollama_prompt"] == "Match risks"

    monkeypatch.setattr(OllamaClient, "classify", fake_classify)

    async def fake_act(_client, text, action_prompt, _settings):
        assert text == "Release risk"
        return f"Action result: {action_prompt}"

    monkeypatch.setattr(OllamaClient, "act", fake_act)

    forwarded = await application.dispatch(
        "testing.evaluate",
        {
            "source_peer_id": -1001,
            "message": "Release risk",
            "is_forwarded": True,
        },
    )
    assert forwarded["matched"] is True
    assert forwarded["message_is_forwarded"] is True
    assert [rule["id"] for rule in forwarded["evaluated_ai_rules"]] == [
        forwarded_rule.id,
        all_rule.id,
    ]
    assert [rule["matched"] for rule in forwarded["evaluated_ai_rules"]] == [
        True,
        False,
    ]
    assert forwarded["evaluated_ai_rules"][0]["action_result"] == (
        "Action result: Summarize the risk"
    )
    assert "Release risk" in forwarded["copy_preview_html"]
    assert "Action result: Summarize the risk" in forwarded["copy_preview_html"]
    assert "<b>Совпадение:</b> release, ИИ" in forwarded["copy_preview_html"]

    calls.clear()
    regular = await application.dispatch(
        "testing.evaluate",
        {
            "source_peer_id": -1001,
            "message": "Release risk",
            "is_forwarded": False,
        },
    )
    assert [rule["applicable"] for rule in regular["evaluated_ai_rules"]] == [
        False,
        True,
    ]
    assert calls == ["Match celebrations"]
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
    assert result["copy_preview_html"] is None
    assert result["evaluated_rules"][0]["matched"] is False

    with pytest.raises(ValidationError, match="configured source"):
        await application.dispatch(
            "testing.evaluate", {"source_peer_id": -9999, "message": "release"}
        )
    with pytest.raises(ValidationError, match="Test message is required"):
        await application.dispatch(
            "testing.evaluate", {"source_peer_id": -1001, "message": "   "}
        )
    with pytest.raises(ValidationError, match="forwarded state"):
        await application.dispatch(
            "testing.evaluate",
            {
                "source_peer_id": -1001,
                "message": "release",
                "is_forwarded": "yes",
            },
        )
    application.database.close()
