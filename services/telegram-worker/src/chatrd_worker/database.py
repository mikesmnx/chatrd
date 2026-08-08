from __future__ import annotations

import json
import math
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .matcher import validate_rule
from .models import ProcessingOutcome, Rule, RuleType, Source, TelegramPeer, ValidationError

SCHEMA_VERSION = 1

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_peers (
    peer_id INTEGER PRIMARY KEY,
    peer_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    username TEXT,
    can_write INTEGER NOT NULL DEFAULT 0,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitored_sources (
    peer_id INTEGER PRIMARY KEY REFERENCES telegram_peers(peer_id),
    enabled INTEGER NOT NULL DEFAULT 1,
    initial_scan_mode TEXT NOT NULL DEFAULT 'now'
        CHECK(initial_scan_mode IN ('now', 'latest_count', 'recent_window')),
    initial_scan_value INTEGER,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    source_peer_id INTEGER REFERENCES monitored_sources(peer_id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK(type IN ('keyword', 'phrase', 'hashtag')),
    pattern TEXT NOT NULL,
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    whole_word INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_cursors (
    source_peer_id INTEGER PRIMARY KEY REFERENCES monitored_sources(peer_id) ON DELETE CASCADE,
    last_terminal_message_id INTEGER NOT NULL,
    initialized_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_processing (
    source_peer_id INTEGER NOT NULL,
    source_message_id INTEGER NOT NULL,
    source_timestamp TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN (
        'pending', 'no_match', 'sent', 'permanently_failed', 'skipped'
    )),
    matched_rule_ids_json TEXT NOT NULL DEFAULT '[]',
    delivery_random_id INTEGER,
    destination_peer_id INTEGER,
    destination_message_id INTEGER,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(source_peer_id, source_message_id)
);

CREATE INDEX IF NOT EXISTS idx_processing_outcome
    ON message_processing(outcome, updated_at);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "destination_peer_id": None,
    "delivery_mode": "copy",
    "paused": True,
    "ai_enabled": False,
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_model": "gpt-oss:20b",
    "ollama_prompt": "",
    "ollama_timeout_seconds": 120,
    "ollama_temperature": 0.0,
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._lock = threading.RLock()
        self.migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def migrate(self) -> None:
        with self.transaction() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )

    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._connection.execute("SELECT key, value_json FROM app_settings").fetchall()
        values = DEFAULT_SETTINGS.copy()
        values.update({row["key"]: json.loads(row["value_json"]) for row in rows})
        return values

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        allowed = set(DEFAULT_SETTINGS)
        unknown = set(values) - allowed
        if unknown:
            raise ValidationError(f"Unknown setting: {sorted(unknown)[0]}")
        if "delivery_mode" in values and values["delivery_mode"] not in {"copy", "forward"}:
            raise ValidationError("Delivery mode must be copy or forward")
        if "ai_enabled" in values and not isinstance(values["ai_enabled"], bool):
            raise ValidationError("AI enabled must be true or false")
        if "ollama_base_url" in values:
            if not isinstance(values["ollama_base_url"], str):
                raise ValidationError("Ollama URL must be a valid HTTP or HTTPS server URL")
            base_url = values["ollama_base_url"].strip().rstrip("/")
            parsed = urlparse(base_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or len(base_url) > 2048
            ):
                raise ValidationError("Ollama URL must be a valid HTTP or HTTPS server URL")
            values["ollama_base_url"] = base_url
        if "ollama_model" in values:
            if not isinstance(values["ollama_model"], str):
                raise ValidationError("Ollama model is required and cannot exceed 128 characters")
            model = values["ollama_model"].strip()
            if not model or len(model) > 128:
                raise ValidationError("Ollama model is required and cannot exceed 128 characters")
            values["ollama_model"] = model
        if "ollama_prompt" in values:
            if not isinstance(values["ollama_prompt"], str):
                raise ValidationError("Ollama instructions must be text")
            prompt = values["ollama_prompt"].strip()
            if len(prompt) > 4000:
                raise ValidationError("Ollama instructions cannot exceed 4,000 characters")
            values["ollama_prompt"] = prompt
        if "ollama_timeout_seconds" in values:
            try:
                if isinstance(values["ollama_timeout_seconds"], bool):
                    raise ValueError
                timeout = int(values["ollama_timeout_seconds"])
            except (TypeError, ValueError) as error:
                raise ValidationError("Ollama timeout must be a number") from error
            if timeout < 5 or timeout > 600:
                raise ValidationError("Ollama timeout must be between 5 and 600 seconds")
            values["ollama_timeout_seconds"] = timeout
        if "ollama_temperature" in values:
            try:
                if isinstance(values["ollama_temperature"], bool):
                    raise ValueError
                temperature = float(values["ollama_temperature"])
            except (TypeError, ValueError) as error:
                raise ValidationError("Ollama temperature must be a number") from error
            if not math.isfinite(temperature) or temperature < 0 or temperature > 2:
                raise ValidationError("Ollama temperature must be between 0 and 2")
            values["ollama_temperature"] = temperature
        if "destination_peer_id" in values and values["destination_peer_id"] is not None:
            destination = int(values["destination_peer_id"])
            with self._lock:
                source = self._connection.execute(
                    "SELECT 1 FROM monitored_sources WHERE peer_id=?", (destination,)
                ).fetchone()
                peer = self._connection.execute(
                    "SELECT can_write FROM telegram_peers WHERE peer_id=?", (destination,)
                ).fetchone()
            if source is not None:
                raise ValidationError("Destination chat cannot also be a source")
            if peer is None or not bool(peer["can_write"]):
                raise ValidationError("Destination must be an available writable chat")
            values["destination_peer_id"] = destination
        resulting = self.get_settings()
        resulting.update(values)
        if resulting["ai_enabled"] and not resulting["ollama_prompt"]:
            raise ValidationError("Ollama instructions are required when AI matching is enabled")
        now = utc_now()
        with self.transaction() as connection:
            for key, value in values.items():
                connection.execute(
                    """
                    INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                        updated_at=excluded.updated_at
                    """,
                    (key, json.dumps(value), now),
                )
        return self.get_settings()

    def replace_peers(self, peers: Iterable[TelegramPeer]) -> None:
        now = utc_now()
        with self.transaction() as connection:
            for peer in peers:
                connection.execute(
                    """
                    INSERT INTO telegram_peers(
                        peer_id, peer_type, display_name, username, can_write, refreshed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(peer_id) DO UPDATE SET
                        peer_type=excluded.peer_type,
                        display_name=excluded.display_name,
                        username=excluded.username,
                        can_write=excluded.can_write,
                        refreshed_at=excluded.refreshed_at
                    """,
                    (
                        peer.peer_id,
                        peer.peer_type,
                        peer.display_name,
                        peer.username,
                        int(peer.can_write),
                        now,
                    ),
                )

    def list_peers(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT peer_id, peer_type, display_name, username, can_write
                FROM telegram_peers ORDER BY display_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            {
                "peer_id": row["peer_id"],
                "peer_type": row["peer_type"],
                "display_name": row["display_name"],
                "username": row["username"],
                "can_write": bool(row["can_write"]),
            }
            for row in rows
        ]

    def upsert_source(
        self,
        *,
        peer_id: int,
        enabled: bool,
        initial_scan_mode: str,
        initial_scan_value: int | None,
    ) -> Source:
        if initial_scan_mode not in {"now", "latest_count", "recent_window"}:
            raise ValidationError("Invalid initial scan mode")
        if initial_scan_mode != "now" and (
            initial_scan_value is None or initial_scan_value < 1 or initial_scan_value > 10_000
        ):
            raise ValidationError("Initial scan value must be between 1 and 10,000")
        if initial_scan_mode == "now":
            initial_scan_value = None
        now = utc_now()
        with self.transaction() as connection:
            peer = connection.execute(
                "SELECT peer_id FROM telegram_peers WHERE peer_id=?", (peer_id,)
            ).fetchone()
            if peer is None:
                raise ValidationError("Selected source chat is not available")
            destination = self.get_settings()["destination_peer_id"]
            if destination == peer_id:
                raise ValidationError("Destination chat cannot also be a source")
            connection.execute(
                """
                INSERT INTO monitored_sources(
                    peer_id, enabled, initial_scan_mode, initial_scan_value, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(peer_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    initial_scan_mode=excluded.initial_scan_mode,
                    initial_scan_value=excluded.initial_scan_value,
                    updated_at=excluded.updated_at
                """,
                (peer_id, int(enabled), initial_scan_mode, initial_scan_value, now, now),
            )
        return next(source for source in self.list_sources() if source.peer_id == peer_id)

    def remove_source(self, peer_id: int) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM monitored_sources WHERE peer_id=?", (peer_id,))

    def list_sources(self) -> list[Source]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT s.peer_id, p.display_name, s.enabled, s.initial_scan_mode,
                       s.initial_scan_value, s.error_code, c.last_terminal_message_id
                FROM monitored_sources s
                JOIN telegram_peers p ON p.peer_id=s.peer_id
                LEFT JOIN source_cursors c ON c.source_peer_id=s.peer_id
                ORDER BY p.display_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            Source(
                peer_id=row["peer_id"],
                display_name=row["display_name"],
                enabled=bool(row["enabled"]),
                initial_scan_mode=row["initial_scan_mode"],
                initial_scan_value=row["initial_scan_value"],
                last_terminal_message_id=row["last_terminal_message_id"],
                error_code=row["error_code"],
            )
            for row in rows
        ]

    def create_rule(
        self,
        *,
        source_peer_id: int | None,
        rule_type: str,
        pattern: str,
        case_sensitive: bool = False,
        whole_word: bool = False,
    ) -> Rule:
        try:
            parsed_type = RuleType(rule_type)
        except ValueError as error:
            raise ValidationError("Invalid rule type") from error
        normalized = validate_rule(parsed_type, pattern, whole_word)
        rule = Rule(
            id=str(uuid.uuid4()),
            source_peer_id=source_peer_id,
            type=parsed_type,
            pattern=normalized,
            case_sensitive=case_sensitive,
            whole_word=whole_word,
        )
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO rules(
                    id, source_peer_id, type, pattern, case_sensitive, whole_word,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    rule.id,
                    rule.source_peer_id,
                    rule.type.value,
                    rule.pattern,
                    int(rule.case_sensitive),
                    int(rule.whole_word),
                    now,
                    now,
                ),
            )
        return rule

    def update_rule(self, rule_id: str, values: dict[str, Any]) -> Rule:
        current = self.get_rule(rule_id)
        if current is None:
            raise ValidationError("Rule not found")
        rule_type = RuleType(values.get("type", current.type.value))
        whole_word = bool(values.get("whole_word", current.whole_word))
        pattern = validate_rule(rule_type, values.get("pattern", current.pattern), whole_word)
        source_peer_id = values.get("source_peer_id", current.source_peer_id)
        updated = Rule(
            id=current.id,
            source_peer_id=source_peer_id,
            type=rule_type,
            pattern=pattern,
            case_sensitive=bool(values.get("case_sensitive", current.case_sensitive)),
            whole_word=whole_word,
            enabled=bool(values.get("enabled", current.enabled)),
        )
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE rules SET source_peer_id=?, type=?, pattern=?, case_sensitive=?,
                    whole_word=?, enabled=?, updated_at=? WHERE id=?
                """,
                (
                    updated.source_peer_id,
                    updated.type.value,
                    updated.pattern,
                    int(updated.case_sensitive),
                    int(updated.whole_word),
                    int(updated.enabled),
                    utc_now(),
                    updated.id,
                ),
            )
        return updated

    def delete_rule(self, rule_id: str) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM rules WHERE id=?", (rule_id,))

    def get_rule(self, rule_id: str) -> Rule | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
        return self._row_to_rule(row) if row else None

    def list_rules(self, source_peer_id: int | None = None) -> list[Rule]:
        query = "SELECT * FROM rules"
        parameters: tuple[Any, ...] = ()
        if source_peer_id is not None:
            query += " WHERE source_peer_id IS NULL OR source_peer_id=?"
            parameters = (source_peer_id,)
        query += " ORDER BY created_at, id"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._row_to_rule(row) for row in rows]

    def get_cursor(self, source_peer_id: int) -> int | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT last_terminal_message_id FROM source_cursors WHERE source_peer_id=?",
                (source_peer_id,),
            ).fetchone()
        return row["last_terminal_message_id"] if row else None

    def initialize_cursor(self, source_peer_id: int, message_id: int) -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO source_cursors(
                    source_peer_id, last_terminal_message_id, initialized_at, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (source_peer_id, message_id, now, now),
            )

    def processing_row(self, source_peer_id: int, source_message_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM message_processing
                WHERE source_peer_id=? AND source_message_id=?
                """,
                (source_peer_id, source_message_id),
            ).fetchone()
        return dict(row) if row else None

    def record_no_match(
        self, source_peer_id: int, source_message_id: int, source_timestamp: str
    ) -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO message_processing(
                    source_peer_id, source_message_id, source_timestamp, outcome,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'no_match', ?, ?)
                """,
                (source_peer_id, source_message_id, source_timestamp, now, now),
            )
            self._advance_cursor(connection, source_peer_id, source_message_id, now)

    def begin_pending(
        self,
        *,
        source_peer_id: int,
        source_message_id: int,
        source_timestamp: str,
        matched_rule_ids: list[str],
        random_id: int,
        destination_peer_id: int,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO message_processing(
                    source_peer_id, source_message_id, source_timestamp, outcome,
                    matched_rule_ids_json, delivery_random_id, destination_peer_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                ON CONFLICT(source_peer_id, source_message_id) DO NOTHING
                """,
                (
                    source_peer_id,
                    source_message_id,
                    source_timestamp,
                    json.dumps(matched_rule_ids),
                    random_id,
                    destination_peer_id,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM message_processing
                WHERE source_peer_id=? AND source_message_id=?
                """,
                (source_peer_id, source_message_id),
            ).fetchone()
        return dict(row)

    def increment_attempt(self, source_peer_id: int, source_message_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE message_processing SET attempt_count=attempt_count+1, updated_at=?
                WHERE source_peer_id=? AND source_message_id=?
                """,
                (utc_now(), source_peer_id, source_message_id),
            )

    def record_sent(
        self, source_peer_id: int, source_message_id: int, destination_message_id: int
    ) -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE message_processing
                SET outcome='sent', destination_message_id=?, error_code=NULL, updated_at=?
                WHERE source_peer_id=? AND source_message_id=?
                """,
                (destination_message_id, now, source_peer_id, source_message_id),
            )
            self._advance_cursor(connection, source_peer_id, source_message_id, now)

    def record_failure(
        self, source_peer_id: int, source_message_id: int, error_code: str
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE message_processing
                SET outcome='permanently_failed', error_code=?, updated_at=?
                WHERE source_peer_id=? AND source_message_id=?
                """,
                (error_code, utc_now(), source_peer_id, source_message_id),
            )

    def retry_failure(self, source_peer_id: int, source_message_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE message_processing SET outcome='pending', error_code=NULL, updated_at=?
                WHERE source_peer_id=? AND source_message_id=? AND outcome='permanently_failed'
                """,
                (utc_now(), source_peer_id, source_message_id),
            )

    def skip_failure(self, source_peer_id: int, source_message_id: int) -> None:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE message_processing SET outcome='skipped', updated_at=?
                WHERE source_peer_id=? AND source_message_id=?
                    AND outcome='permanently_failed'
                """,
                (now, source_peer_id, source_message_id),
            )
            self._advance_cursor(connection, source_peer_id, source_message_id, now)

    def processing_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT outcome, COUNT(*) AS count FROM message_processing GROUP BY outcome"
            ).fetchall()
        return {row["outcome"]: row["count"] for row in rows}

    @staticmethod
    def _advance_cursor(
        connection: sqlite3.Connection, source_peer_id: int, source_message_id: int, now: str
    ) -> None:
        connection.execute(
            """
            INSERT INTO source_cursors(
                source_peer_id, last_terminal_message_id, initialized_at, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(source_peer_id) DO UPDATE SET
                last_terminal_message_id=excluded.last_terminal_message_id,
                updated_at=excluded.updated_at
            WHERE excluded.last_terminal_message_id > source_cursors.last_terminal_message_id
            """,
            (source_peer_id, source_message_id, now, now),
        )

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> Rule:
        return Rule(
            id=row["id"],
            source_peer_id=row["source_peer_id"],
            type=RuleType(row["type"]),
            pattern=row["pattern"],
            case_sensitive=bool(row["case_sensitive"]),
            whole_word=bool(row["whole_word"]),
            enabled=bool(row["enabled"]),
        )
