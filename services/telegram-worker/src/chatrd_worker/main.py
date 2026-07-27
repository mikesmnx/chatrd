from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from .application import WorkerApplication
from .models import WorkerError

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 1_048_576


class ProtocolServer:
    def __init__(self, data_dir: Path):
        self._write_lock = asyncio.Lock()
        self.application = WorkerApplication(data_dir, emit=self.emit)
        self._stopping = False

    async def run(self) -> None:
        while not self._stopping:
            line = await asyncio.to_thread(sys.stdin.buffer.readline)
            if not line:
                break
            if len(line) > MAX_FRAME_BYTES:
                await self._write(
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "type": "error",
                        "id": None,
                        "error": {
                            "code": "frame_too_large",
                            "message": "Worker request exceeded the size limit",
                        },
                    }
                )
                continue
            try:
                frame = json.loads(line)
                await self._handle(frame)
            except json.JSONDecodeError:
                await self._write(
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "type": "error",
                        "id": None,
                        "error": {
                            "code": "invalid_json",
                            "message": "Worker request was not valid JSON",
                        },
                    }
                )

    async def emit(self, name: str, payload: dict[str, Any]) -> None:
        await self._write(
            {
                "protocolVersion": PROTOCOL_VERSION,
                "type": "event",
                "event": name,
                "payload": payload,
            }
        )

    async def _handle(self, frame: dict[str, Any]) -> None:
        request_id = frame.get("id")
        if frame.get("protocolVersion") != PROTOCOL_VERSION:
            await self._error(request_id, "protocol_mismatch", "Incompatible worker protocol")
            return
        if frame.get("type") != "request" or not isinstance(frame.get("method"), str):
            await self._error(request_id, "invalid_request", "Invalid worker request")
            return
        payload = frame.get("payload", {})
        if not isinstance(payload, dict):
            await self._error(request_id, "invalid_request", "Payload must be an object")
            return
        try:
            result = await self.application.dispatch(frame["method"], payload)
            await self._write(
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "type": "response",
                    "id": request_id,
                    "result": result,
                }
            )
            if frame["method"] == "system.shutdown":
                self._stopping = True
        except WorkerError as error:
            await self._error(request_id, error.code, error.safe_message)
        except Exception:
            logging.exception("Unhandled worker request failure")
            await self._error(
                request_id,
                "internal_error",
                "The local worker could not complete the request",
            )

    async def _error(self, request_id: Any, code: str, message: str) -> None:
        await self._write(
            {
                "protocolVersion": PROTOCOL_VERSION,
                "type": "error",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        )

    async def _write(self, frame: dict[str, Any]) -> None:
        encoded = encode_frame(frame)
        async with self._write_lock:
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()


def encode_frame(frame: dict[str, Any]) -> bytes:
    encoded = json.dumps(frame, separators=(",", ":"), ensure_ascii=False)
    return (encoded + "\n").encode("utf-8")


async def async_main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    data_dir = Path(os.environ.get("CHATRD_DATA_DIR", ".chatrd-data")).resolve()
    server = ProtocolServer(data_dir)
    await server.run()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
