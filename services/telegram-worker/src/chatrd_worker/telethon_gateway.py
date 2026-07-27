from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from telethon import TelegramClient, events, functions, types, utils
from telethon.extensions import html
from telethon.errors import (
    AuthKeyError,
    ChatForwardsRestrictedError,
    FloodWaitError as TelethonFloodWait,
    RPCError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from .gateway import MessageHandler, ensure_utc
from .models import (
    AuthenticationRequired,
    DeliveryResult,
    FloodWaitError,
    FormattedMessage,
    MessageEnvelope,
    PermanentTelegramError,
    TelegramPeer,
    TransientTelegramError,
)


class TelethonGateway:
    def __init__(self, api_id: int, api_hash: str, session: str | None = None):
        self._api_id = api_id
        self._api_hash = api_hash
        self._client = TelegramClient(StringSession(session or ""), api_id, api_hash)
        self._phone: str | None = None
        self._phone_code_hash: str | None = None
        self._handler: MessageHandler | None = None
        self._event_callback: Any = None

    async def connect(self) -> None:
        await self._translate(self._client.connect())

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def is_authorized(self) -> bool:
        return bool(await self._translate(self._client.is_user_authorized()))

    async def account_id(self) -> int:
        me = await self._translate(self._client.get_me())
        if me is None:
            raise AuthenticationRequired("Telegram sign-in is required")
        return int(me.id)

    async def request_code(self, phone: str) -> None:
        self._phone = phone
        result = await self._translate(self._client.send_code_request(phone))
        self._phone_code_hash = result.phone_code_hash

    async def submit_code(self, code: str) -> str:
        if not self._phone or not self._phone_code_hash:
            raise AuthenticationRequired("Request a Telegram login code first")
        try:
            await self._client.sign_in(
                phone=self._phone,
                code=code,
                phone_code_hash=self._phone_code_hash,
            )
        except SessionPasswordNeededError:
            return "password_required"
        except Exception as error:
            raise self._map_error(error) from error
        return "authorized"

    async def submit_password(self, password: str) -> None:
        await self._translate(self._client.sign_in(password=password))

    def export_session(self) -> str:
        return StringSession.save(self._client.session)

    async def logout(self) -> None:
        await self._translate(self._client.log_out())

    async def list_peers(self) -> list[TelegramPeer]:
        peers: list[TelegramPeer] = []
        try:
            async for dialog in self._client.iter_dialogs():
                entity = dialog.entity
                peer_id = int(utils.get_peer_id(entity))
                peer_type = _peer_type(entity)
                username = getattr(entity, "username", None)
                can_write = _can_write(entity, dialog.is_user)
                peers.append(
                    TelegramPeer(
                        peer_id=peer_id,
                        peer_type=peer_type,
                        display_name=dialog.name or "Чат без названия",
                        username=username,
                        can_write=can_write,
                    )
                )
        except Exception as error:
            raise self._map_error(error) from error
        return peers

    async def high_water(self, peer_id: int) -> int:
        messages = await self._translate(self._client.get_messages(peer_id, limit=1))
        return int(messages[0].id) if messages else 0

    async def history_after(
        self, peer_id: int, message_id: int, *, high_water: int | None = None
    ) -> list[MessageEnvelope]:
        result: list[MessageEnvelope] = []
        try:
            async for message in self._client.iter_messages(
                peer_id, min_id=message_id, reverse=True
            ):
                if high_water is not None and message.id > high_water:
                    break
                result.append(await self._to_envelope(peer_id, message))
        except Exception as error:
            raise self._map_error(error) from error
        return result

    async def latest(self, peer_id: int, count: int) -> list[MessageEnvelope]:
        messages = await self._translate(self._client.get_messages(peer_id, limit=count))
        envelopes = [await self._to_envelope(peer_id, message) for message in messages]
        return sorted(envelopes, key=lambda item: item.source_message_id)

    async def since(self, peer_id: int, window: timedelta) -> list[MessageEnvelope]:
        cutoff = datetime.now(UTC) - window
        result: list[MessageEnvelope] = []
        try:
            async for message in self._client.iter_messages(peer_id):
                if ensure_utc(message.date) < cutoff:
                    break
                result.append(await self._to_envelope(peer_id, message))
        except Exception as error:
            raise self._map_error(error) from error
        return sorted(result, key=lambda item: item.source_message_id)

    async def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler
        if self._event_callback is not None:
            return

        async def callback(event: events.NewMessage.Event) -> None:
            if self._handler is None:
                return
            peer_id = int(event.chat_id)
            envelope = await self._to_envelope(peer_id, event.message)
            await self._handler(envelope)

        self._event_callback = callback
        self._client.add_event_handler(callback, events.NewMessage())

    async def send_copy(
        self, destination_peer_id: int, message: FormattedMessage, random_id: int
    ) -> DeliveryResult:
        try:
            peer = await self._client.get_input_entity(destination_peer_id)
            plain_text, entities = html.parse(message.text)
            result = await self._client(
                functions.messages.SendMessageRequest(
                    peer=peer,
                    message=plain_text,
                    entities=entities,
                    random_id=random_id,
                    no_webpage=True,
                )
            )
            return DeliveryResult(_destination_message_id(result, random_id))
        except Exception as error:
            raise self._map_error(error) from error

    async def forward(
        self,
        destination_peer_id: int,
        source_peer_id: int,
        source_message_id: int,
        random_id: int,
    ) -> DeliveryResult:
        try:
            source = await self._client.get_input_entity(source_peer_id)
            destination = await self._client.get_input_entity(destination_peer_id)
            result = await self._client(
                functions.messages.ForwardMessagesRequest(
                    from_peer=source,
                    id=[source_message_id],
                    random_id=[random_id],
                    to_peer=destination,
                )
            )
            return DeliveryResult(_destination_message_id(result, random_id))
        except Exception as error:
            raise self._map_error(error) from error

    async def _to_envelope(self, peer_id: int, message: Any) -> MessageEnvelope:
        chat = await message.get_chat()
        sender = await message.get_sender()
        text = message.message or None
        return MessageEnvelope(
            source_peer_id=peer_id,
            source_message_id=int(message.id),
            source_timestamp=ensure_utc(message.date),
            source_name=utils.get_display_name(chat) or "Чат без названия",
            text=text,
            author_name=utils.get_display_name(sender) if sender else None,
            source_username=getattr(chat, "username", None),
            source_peer_type=_peer_type(chat),
        )

    async def _translate(self, awaitable: Any) -> Any:
        try:
            return await awaitable
        except Exception as error:
            raise self._map_error(error) from error

    @staticmethod
    def _map_error(error: Exception) -> Exception:
        if isinstance(error, TelethonFloodWait):
            return FloodWaitError(int(error.seconds))
        if isinstance(error, (AuthKeyError,)):
            return AuthenticationRequired("Telegram authorization is invalid or expired")
        if isinstance(error, ChatForwardsRestrictedError):
            return PermanentTelegramError("Telegram does not allow forwarding this message")
        if isinstance(error, RPCError):
            code = getattr(error, "code", 0)
            if code >= 500 or code == 420:
                return TransientTelegramError("Telegram is temporarily unavailable")
            return PermanentTelegramError("Telegram rejected the requested operation")
        if isinstance(error, (ConnectionError, TimeoutError, OSError)):
            return TransientTelegramError("Telegram connection is unavailable")
        return error


def _peer_type(entity: Any) -> str:
    if isinstance(entity, types.Channel):
        return "supergroup" if entity.megagroup else "channel"
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.User):
        return "user"
    return "unknown"


def _can_write(entity: Any, is_user: bool = False) -> bool:
    if is_user:
        return not bool(getattr(entity, "bot", False))
    if isinstance(entity, types.Channel) and entity.broadcast:
        rights = getattr(entity, "admin_rights", None)
        return bool(rights and (rights.post_messages or rights.edit_messages))
    return not bool(getattr(entity, "left", False))


def _destination_message_id(result: Any, random_id: int) -> int:
    updates = getattr(result, "updates", [])
    for update in updates:
        if isinstance(update, types.UpdateMessageID) and int(update.random_id) == random_id:
            return int(update.id)
    for update in updates:
        message = getattr(update, "message", None)
        if message is not None and getattr(message, "out", False):
            return int(message.id)
    direct_id = getattr(result, "id", None)
    if direct_id is not None:
        return int(direct_id)
    raise TransientTelegramError("Telegram accepted the send but confirmation is pending")
