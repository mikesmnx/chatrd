from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .database import Database
from .formatter import format_copy
from .gateway import TelegramGateway
from .idempotency import delivery_random_id
from .matcher import match_message
from .models import (
    FloodWaitError,
    MessageEnvelope,
    PermanentTelegramError,
    TERMINAL_OUTCOMES,
    TransientTelegramError,
    ValidationError,
)

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


async def _no_event(_name: str, _payload: dict[str, Any]) -> None:
    return None


class MessageProcessor:
    def __init__(
        self,
        database: Database,
        gateway: TelegramGateway,
        *,
        account_id: int,
        emit: EventCallback = _no_event,
    ):
        self.database = database
        self.gateway = gateway
        self.account_id = account_id
        self.emit = emit
        self._source_locks: dict[int, asyncio.Lock] = {}

    async def process(self, message: MessageEnvelope) -> str:
        lock = self._source_locks.setdefault(message.source_peer_id, asyncio.Lock())
        async with lock:
            existing = self.database.processing_row(
                message.source_peer_id, message.source_message_id
            )
            if existing and existing["outcome"] in TERMINAL_OUTCOMES:
                return existing["outcome"]
            if existing and existing["outcome"] == "permanently_failed":
                return existing["outcome"]

            rules = self.database.list_rules(message.source_peer_id)
            match = match_message(message.text, rules)
            if not match.matched and existing is None:
                self.database.record_no_match(
                    message.source_peer_id,
                    message.source_message_id,
                    message.source_timestamp.isoformat(),
                )
                await self.emit(
                    "message.processed",
                    {"source_peer_id": message.source_peer_id, "outcome": "no_match"},
                )
                return "no_match"

            settings = self.database.get_settings()
            destination = settings["destination_peer_id"]
            if destination is None:
                raise ValidationError("Choose a destination chat before monitoring")

            if existing is None:
                random_id = delivery_random_id(
                    account_id=self.account_id,
                    destination_peer_id=int(destination),
                    source_peer_id=message.source_peer_id,
                    source_message_id=message.source_message_id,
                )
                existing = self.database.begin_pending(
                    source_peer_id=message.source_peer_id,
                    source_message_id=message.source_message_id,
                    source_timestamp=message.source_timestamp.isoformat(),
                    matched_rule_ids=[rule.id for rule in match.matched_rules],
                    random_id=random_id,
                    destination_peer_id=int(destination),
                )

            random_id = int(existing["delivery_random_id"])
            self.database.increment_attempt(message.source_peer_id, message.source_message_id)
            try:
                if settings["delivery_mode"] == "forward":
                    result = await self.gateway.forward(
                        int(destination),
                        message.source_peer_id,
                        message.source_message_id,
                        random_id,
                    )
                else:
                    formatted = format_copy(message, match.matched_rules)
                    result = await self.gateway.send_copy(int(destination), formatted, random_id)
            except FloodWaitError:
                raise
            except TransientTelegramError:
                raise
            except PermanentTelegramError as error:
                self.database.record_failure(
                    message.source_peer_id, message.source_message_id, error.code
                )
                await self.emit(
                    "message.failed",
                    {
                        "source_peer_id": message.source_peer_id,
                        "source_message_id": message.source_message_id,
                        "error_code": error.code,
                    },
                )
                return "permanently_failed"

            self.database.record_sent(
                message.source_peer_id,
                message.source_message_id,
                result.destination_message_id,
            )
            await self.emit(
                "message.processed",
                {"source_peer_id": message.source_peer_id, "outcome": "sent"},
            )
            return "sent"

