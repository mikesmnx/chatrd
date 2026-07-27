from __future__ import annotations

import json

from chatrd_worker.main import MAX_FRAME_BYTES, PROTOCOL_VERSION, encode_frame


def test_protocol_constants_are_stable() -> None:
    assert PROTOCOL_VERSION == 1
    assert MAX_FRAME_BYTES == 1_048_576


def test_request_fixture_is_json_serializable() -> None:
    request = {
        "protocolVersion": 1,
        "type": "request",
        "id": "test-1",
        "method": "system.ping",
        "payload": {},
    }
    assert json.loads(json.dumps(request)) == request


def test_protocol_frames_are_always_utf8_even_with_emoji() -> None:
    frame = {
        "protocolVersion": 1,
        "type": "response",
        "id": "unicode",
        "result": [{"display_name": "Team 😎 — Αθήνα"}],
    }
    encoded = encode_frame(frame)
    assert encoded.endswith(b"\n")
    assert json.loads(encoded.decode("utf-8"))["result"][0]["display_name"] == "Team 😎 — Αθήνα"
