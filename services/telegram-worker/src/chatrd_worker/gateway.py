from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from .models import DeliveryResult, FormattedMessage, MessageEnvelope, TelegramPeer

MessageHandler = Callable[[MessageEnvelope], Awaitable[None]]


class TelegramGateway(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def is_authorized(self) -> bool: ...

    async def account_id(self) -> int: ...

    async def request_code(self, phone: str) -> None: ...

    async def submit_code(self, code: str) -> str: ...

    async def submit_password(self, password: str) -> None: ...

    def export_session(self) -> str: ...

    async def logout(self) -> None: ...

    async def list_peers(self) -> list[TelegramPeer]: ...

    async def high_water(self, peer_id: int) -> int: ...

    async def history_after(
        self, peer_id: int, message_id: int, *, high_water: int | None = None
    ) -> list[MessageEnvelope]: ...

    async def latest(self, peer_id: int, count: int) -> list[MessageEnvelope]: ...

    async def since(self, peer_id: int, window: timedelta) -> list[MessageEnvelope]: ...

    async def set_message_handler(self, handler: MessageHandler) -> None: ...

    async def send_copy(
        self, destination_peer_id: int, message: FormattedMessage, random_id: int
    ) -> DeliveryResult: ...

    async def forward(
        self,
        destination_peer_id: int,
        source_peer_id: int,
        source_message_id: int,
        random_id: int,
    ) -> DeliveryResult: ...


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

