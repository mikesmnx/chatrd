from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class RuleType(StrEnum):
    KEYWORD = "keyword"
    PHRASE = "phrase"
    HASHTAG = "hashtag"


class DeliveryMode(StrEnum):
    COPY = "copy"
    FORWARD = "forward"


class ProcessingOutcome(StrEnum):
    PENDING = "pending"
    NO_MATCH = "no_match"
    SENT = "sent"
    PERMANENTLY_FAILED = "permanently_failed"
    SKIPPED = "skipped"


TERMINAL_OUTCOMES = {
    ProcessingOutcome.NO_MATCH.value,
    ProcessingOutcome.SENT.value,
    ProcessingOutcome.SKIPPED.value,
}


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    source_peer_id: int | None
    type: RuleType
    pattern: str
    case_sensitive: bool = False
    whole_word: bool = False
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value
        return data


@dataclass(frozen=True, slots=True)
class Source:
    peer_id: int
    display_name: str
    enabled: bool = True
    initial_scan_mode: str = "now"
    initial_scan_value: int | None = None
    last_terminal_message_id: int | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TelegramPeer:
    peer_id: int
    peer_type: str
    display_name: str
    username: str | None = None
    can_write: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    source_peer_id: int
    source_message_id: int
    source_timestamp: datetime
    source_name: str
    text: str | None
    author_name: str | None = None
    source_username: str | None = None
    source_peer_type: str = "unknown"


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched_rules: tuple[Rule, ...]

    @property
    def matched(self) -> bool:
        return bool(self.matched_rules)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    destination_message_id: int


@dataclass(frozen=True, slots=True)
class FormattedMessage:
    text: str
    parse_mode: str = "html"


class WorkerError(Exception):
    code = "worker_error"
    transient = False

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.safe_message = message
        self.detail = detail


class ValidationError(WorkerError):
    code = "validation_error"


class AuthenticationRequired(WorkerError):
    code = "authentication_required"


class TransientTelegramError(WorkerError):
    code = "telegram_transient"
    transient = True


class OllamaUnavailableError(WorkerError):
    code = "ollama_unavailable"
    transient = True


class PermanentTelegramError(WorkerError):
    code = "telegram_permanent"


class FloodWaitError(TransientTelegramError):
    code = "telegram_flood_wait"

    def __init__(self, seconds: int):
        super().__init__(f"Telegram requested a {seconds}-second wait")
        self.seconds = seconds
