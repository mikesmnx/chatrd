from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .database import Database
from .formatter import format_ai_addition, format_copy
from .gateway import TelegramGateway
from .idempotency import delivery_random_id
from .matcher import match_message
from .models import (
    FloodWaitError,
    MatchResult,
    MessageEnvelope,
    PermanentTelegramError,
    Rule,
    RuleType,
    TERMINAL_OUTCOMES,
    TransientTelegramError,
    ValidationError,
)
from .ollama import OllamaClient

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class SemanticMatcher(Protocol):
    async def classify(self, text: str, settings: dict[str, Any]) -> bool: ...

    async def act(
        self, text: str, action_prompt: str, settings: dict[str, Any]
    ) -> str: ...


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
        semantic_matcher: SemanticMatcher | None = None,
    ):
        self.database = database
        self.gateway = gateway
        self.account_id = account_id
        self.emit = emit
        self.semantic_matcher = semantic_matcher or OllamaClient()
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
            settings = self.database.get_settings()
            ai_additions: list[str] = []
            ai_matched_rules: list[Rule] = []
            if message.text:
                applicable_ai_rules = (
                    rule
                    for rule in self.database.list_ai_rules()
                    if rule.enabled
                    and (rule.apply_to.value == "all" or message.is_forwarded)
                )
                for ai_rule in applicable_ai_rules:
                    rule_settings = {**settings, "ollama_prompt": ai_rule.prompt}
                    if await self.semantic_matcher.classify(message.text, rule_settings):
                        if ai_rule.action_prompt:
                            ai_additions.append(
                                await self.semantic_matcher.act(
                                    message.text, ai_rule.action_prompt, settings
                                )
                            )
                        ai_matched_rules.append(
                            Rule(
                                id=ai_rule.id,
                                source_peer_id=None,
                                type=RuleType.PHRASE,
                                pattern="ИИ",
                            )
                        )
                if ai_matched_rules:
                    match = MatchResult(
                        matched_rules=match.matched_rules + tuple(ai_matched_rules)
                    )
            ai_addition = "\n\n".join(ai_additions) or None
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
                    if ai_addition:
                        action_random_id = delivery_random_id(
                            account_id=self.account_id,
                            destination_peer_id=int(destination),
                            source_peer_id=message.source_peer_id,
                            source_message_id=message.source_message_id,
                            purpose="ai-action",
                        )
                        await self.gateway.send_copy(
                            int(destination),
                            format_ai_addition(ai_addition),
                            action_random_id,
                        )
                else:
                    formatted = format_copy(
                        message,
                        match.matched_rules,
                        additional_content=ai_addition,
                    )
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
