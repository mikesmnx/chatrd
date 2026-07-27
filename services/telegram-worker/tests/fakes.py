from __future__ import annotations

from datetime import timedelta

from chatrd_worker.gateway import MessageHandler
from chatrd_worker.models import (
    DeliveryResult,
    FormattedMessage,
    MessageEnvelope,
    TelegramPeer,
)


class FakeGateway:
    def __init__(self):
        self.authorized = True
        self.account = 7
        self.messages: dict[int, list[MessageEnvelope]] = {}
        self.handler: MessageHandler | None = None
        self.sent: list[tuple[int, FormattedMessage, int]] = []
        self.forwarded: list[tuple[int, int, int, int]] = []
        self.next_error: Exception | None = None
        self.logout_error: Exception | None = None

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def is_authorized(self) -> bool:
        return self.authorized

    async def account_id(self) -> int:
        return self.account

    async def request_code(self, phone: str) -> None:
        return None

    async def submit_code(self, code: str) -> str:
        return "authorized"

    async def submit_password(self, password: str) -> None:
        return None

    def export_session(self) -> str:
        return "not-a-real-session"

    async def logout(self) -> None:
        if self.logout_error:
            raise self.logout_error
        self.authorized = False

    async def list_peers(self) -> list[TelegramPeer]:
        return []

    async def high_water(self, peer_id: int) -> int:
        items = self.messages.get(peer_id, [])
        return max((item.source_message_id for item in items), default=0)

    async def history_after(
        self, peer_id: int, message_id: int, *, high_water: int | None = None
    ) -> list[MessageEnvelope]:
        return [
            item
            for item in self.messages.get(peer_id, [])
            if item.source_message_id > message_id
            and (high_water is None or item.source_message_id <= high_water)
        ]

    async def latest(self, peer_id: int, count: int) -> list[MessageEnvelope]:
        return self.messages.get(peer_id, [])[-count:]

    async def since(self, peer_id: int, window: timedelta) -> list[MessageEnvelope]:
        return self.messages.get(peer_id, [])

    async def set_message_handler(self, handler: MessageHandler) -> None:
        self.handler = handler

    async def send_copy(
        self, destination_peer_id: int, message: FormattedMessage, random_id: int
    ) -> DeliveryResult:
        if self.next_error:
            error, self.next_error = self.next_error, None
            raise error
        self.sent.append((destination_peer_id, message, random_id))
        return DeliveryResult(1000 + len(self.sent))

    async def forward(
        self,
        destination_peer_id: int,
        source_peer_id: int,
        source_message_id: int,
        random_id: int,
    ) -> DeliveryResult:
        if self.next_error:
            error, self.next_error = self.next_error, None
            raise error
        self.forwarded.append(
            (destination_peer_id, source_peer_id, source_message_id, random_id)
        )
        return DeliveryResult(2000 + len(self.forwarded))

    async def emit(self, message: MessageEnvelope) -> None:
        assert self.handler is not None
        await self.handler(message)
