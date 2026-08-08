from __future__ import annotations

from chatrd_worker.application import WorkerApplication
import pytest

from chatrd_worker.models import TransientTelegramError, ValidationError
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
