from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from .database import Database
from .gateway import TelegramGateway
from .models import FloodWaitError, MessageEnvelope, Source, TransientTelegramError
from .processor import EventCallback, MessageProcessor, _no_event


class Monitor:
    def __init__(
        self,
        database: Database,
        gateway: TelegramGateway,
        processor: MessageProcessor,
        *,
        emit: EventCallback = _no_event,
    ):
        self.database = database
        self.gateway = gateway
        self.processor = processor
        self.emit = emit
        self.state = "paused"
        self._tasks: set[asyncio.Task[Any]] = set()
        self._handler_registered = False
        self._live_buffer: dict[int, list[MessageEnvelope]] = {}
        self._max_buffered_per_source = 10_000

    async def start(self) -> dict[str, Any]:
        if self.state in {"catching_up", "monitoring"}:
            return self.snapshot()
        self.database.update_settings({"paused": False})
        self.state = "catching_up"
        await self.emit("monitor.status", self.snapshot())
        if not self._handler_registered:
            await self.gateway.set_message_handler(self._on_live_message)
            self._handler_registered = True

        sources = [source for source in self.database.list_sources() if source.enabled]
        for source in sources:
            await self._catch_up(source)
            await self._drain_buffer(source.peer_id)
        self.state = "monitoring"
        await self.emit("monitor.status", self.snapshot())
        return self.snapshot()

    async def pause(self) -> dict[str, Any]:
        self.database.update_settings({"paused": True})
        self.state = "paused"
        await self.emit("monitor.status", self.snapshot())
        return self.snapshot()

    async def shutdown(self) -> None:
        await self.pause()
        pending = tuple(self._tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "counts": self.database.processing_counts(),
            "sources": [source.to_dict() for source in self.database.list_sources()],
        }

    async def _catch_up(self, source: Source) -> None:
        cursor = self.database.get_cursor(source.peer_id)
        high_water = await self.gateway.high_water(source.peer_id)
        if cursor is None:
            if source.initial_scan_mode == "now":
                self.database.initialize_cursor(source.peer_id, high_water)
                await self.emit(
                    "source.progress",
                    {"source_peer_id": source.peer_id, "processed": 0, "complete": True},
                )
                return
            if source.initial_scan_mode == "latest_count":
                messages = await self.gateway.latest(
                    source.peer_id, int(source.initial_scan_value or 1)
                )
            else:
                messages = await self.gateway.since(
                    source.peer_id, timedelta(hours=int(source.initial_scan_value or 1))
                )
            if messages:
                self.database.initialize_cursor(
                    source.peer_id, messages[0].source_message_id - 1
                )
        else:
            messages = await self.gateway.history_after(
                source.peer_id, cursor, high_water=high_water
            )

        for index, message in enumerate(messages, start=1):
            await self._process_with_retry(message)
            await self.emit(
                "source.progress",
                {
                    "source_peer_id": source.peer_id,
                    "processed": index,
                    "total": len(messages),
                    "complete": index == len(messages),
                },
            )
        if not messages:
            self.database.initialize_cursor(source.peer_id, high_water)

    async def _on_live_message(self, message: MessageEnvelope) -> None:
        if self.database.get_settings()["paused"]:
            return
        source_ids = {
            source.peer_id for source in self.database.list_sources() if source.enabled
        }
        if message.source_peer_id not in source_ids:
            return
        if self.state == "catching_up":
            buffered = self._live_buffer.setdefault(message.source_peer_id, [])
            if len(buffered) >= self._max_buffered_per_source:
                await self.emit(
                    "source.error",
                    {
                        "source_peer_id": message.source_peer_id,
                        "error_code": "live_buffer_full",
                    },
                )
                return
            buffered.append(message)
            return
        task = asyncio.create_task(self._process_with_retry(message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _drain_buffer(self, source_peer_id: int) -> None:
        buffered = self._live_buffer.pop(source_peer_id, [])
        unique = {
            message.source_message_id: message
            for message in buffered
            if message.source_message_id > (self.database.get_cursor(source_peer_id) or 0)
        }
        for message_id in sorted(unique):
            await self._process_with_retry(unique[message_id])

    async def _process_with_retry(self, message: MessageEnvelope) -> None:
        attempt = 0
        while not self.database.get_settings()["paused"]:
            try:
                await self.processor.process(message)
                return
            except FloodWaitError as error:
                await self.emit(
                    "monitor.waiting",
                    {
                        "source_peer_id": message.source_peer_id,
                        "seconds": error.seconds,
                    },
                )
                await asyncio.sleep(error.seconds)
            except TransientTelegramError:
                attempt += 1
                delay = min(60, 2**min(attempt, 6))
                await self.emit(
                    "monitor.retrying",
                    {"source_peer_id": message.source_peer_id, "seconds": delay},
                )
                await asyncio.sleep(delay)
