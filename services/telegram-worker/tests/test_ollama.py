from __future__ import annotations

import io
import json
from urllib.error import URLError

import pytest

from chatrd_worker.models import OllamaUnavailableError, ValidationError
from chatrd_worker.ollama import OllamaClient


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def settings() -> dict:
    return {
        "ollama_base_url": "http://127.0.0.1:11434",
        "ollama_model": "gpt-oss:20b",
        "ollama_prompt": "Отбирай сообщения о релизах.",
        "ollama_timeout_seconds": 30,
        "ollama_temperature": 0.0,
    }


async def test_structured_classification_request(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        return Response(b'{"message":{"content":"{\\"match\\":true}"}}')

    monkeypatch.setattr("chatrd_worker.ollama.urlopen", fake_urlopen)

    assert await OllamaClient().classify("release candidate", settings()) is True
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["timeout"] == 30
    assert captured["body"]["model"] == "gpt-oss:20b"
    assert captured["body"]["stream"] is False
    assert captured["body"]["think"] is False
    assert captured["body"]["format"]["properties"]["match"] == {"type": "boolean"}
    assert "release candidate" in captured["body"]["messages"][1]["content"]


async def test_chat_returns_the_models_answer(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, **_kwargs):
        captured["body"] = json.loads(request.data)
        return Response(b'{"message":{"content":"Hello from Ollama"}}')

    monkeypatch.setattr("chatrd_worker.ollama.urlopen", fake_urlopen)
    assert await OllamaClient().chat("Hello", settings()) == {
        "model": "gpt-oss:20b",
        "message": "Hello from Ollama",
    }
    assert captured["body"]["messages"] == [{"role": "user", "content": "Hello"}]
    assert "format" not in captured["body"]


@pytest.mark.parametrize("message", ["", "   ", "x" * 8001])
async def test_chat_validates_test_message(message: str) -> None:
    with pytest.raises(ValidationError, match="Ollama test message"):
        await OllamaClient().chat(message, settings())


async def test_chat_rejects_an_empty_model_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        "chatrd_worker.ollama.urlopen",
        lambda *_args, **_kwargs: Response(b'{"message":{"content":""}}'),
    )
    with pytest.raises(OllamaUnavailableError, match="valid chat response"):
        await OllamaClient().chat("Hello", settings())


@pytest.mark.parametrize(
    "failure",
    [
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
        lambda *_args, **_kwargs: Response(b'{"message":{"content":"not json"}}'),
    ],
)
async def test_ollama_failures_are_redacted(monkeypatch, failure) -> None:
    monkeypatch.setattr("chatrd_worker.ollama.urlopen", failure)
    with pytest.raises(OllamaUnavailableError, match="Ollama did not return"):
        await OllamaClient().classify("private message text", settings())
