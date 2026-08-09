from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .database import Database
from .formatter import format_copy
from .matcher import match_message
from .models import (
    AuthenticationRequired,
    MessageEnvelope,
    Rule,
    RuleType,
    ValidationError,
)
from .monitor import Monitor
from .ollama import OllamaClient
from .processor import EventCallback, MessageProcessor, _no_event
from .telethon_gateway import TelethonGateway


class WorkerApplication:
    def __init__(self, data_dir: str | Path, *, emit: EventCallback = _no_event):
        self.data_dir = Path(data_dir)
        self.database = Database(self.data_dir / "chatrd.db")
        self.emit = emit
        self.gateway: TelethonGateway | None = None
        self.monitor: Monitor | None = None
        self._pending_api_id: int | None = None
        self._pending_api_hash: str | None = None

    async def dispatch(self, method: str, payload: dict[str, Any]) -> Any:
        handlers = {
            "system.ping": self._ping,
            "system.snapshot": self._snapshot,
            "system.shutdown": self._shutdown,
            "auth.status": self._auth_status,
            "auth.restore": self._auth_restore,
            "auth.start": self._auth_start,
            "auth.submitCode": self._auth_submit_code,
            "auth.submitPassword": self._auth_submit_password,
            "auth.logout": self._auth_logout,
            "chats.list": self._chats_list,
            "settings.get": self._settings_get,
            "settings.update": self._settings_update,
            "ollama.chat": self._ollama_chat,
            "sources.list": self._sources_list,
            "sources.upsert": self._sources_upsert,
            "sources.remove": self._sources_remove,
            "rules.list": self._rules_list,
            "rules.create": self._rules_create,
            "rules.update": self._rules_update,
            "rules.delete": self._rules_delete,
            "aiRules.list": self._ai_rules_list,
            "aiRules.create": self._ai_rules_create,
            "aiRules.update": self._ai_rules_update,
            "aiRules.delete": self._ai_rules_delete,
            "testing.evaluate": self._testing_evaluate,
            "monitor.start": self._monitor_start,
            "monitor.pause": self._monitor_pause,
            "monitor.status": self._monitor_status,
            "processing.skip": self._processing_skip,
            "processing.retry": self._processing_retry,
        }
        handler = handlers.get(method)
        if handler is None:
            raise ValidationError(f"Unknown worker method: {method}")
        return await handler(payload)

    async def _ping(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"version": __version__, "protocol_version": 1}

    async def _snapshot(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "authenticated": await self._is_authenticated(),
            "settings": self.database.get_settings(),
            "sources": [source.to_dict() for source in self.database.list_sources()],
            "rules": [rule.to_dict() for rule in self.database.list_rules()],
            "ai_rules": [rule.to_dict() for rule in self.database.list_ai_rules()],
            "monitor": self.monitor.snapshot() if self.monitor else {
                "state": "paused",
                "counts": self.database.processing_counts(),
            },
        }

    async def _shutdown(self, _payload: dict[str, Any]) -> dict[str, bool]:
        if self.monitor:
            await self.monitor.shutdown()
        if self.gateway:
            await self.gateway.disconnect()
        self.database.close()
        return {"ok": True}

    async def _auth_status(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"authenticated": await self._is_authenticated()}

    async def _auth_restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_id = _positive_int(payload.get("api_id"), "API ID")
        api_hash = _required_string(payload.get("api_hash"), "API hash")
        session = _required_string(payload.get("session"), "Session")
        await self._replace_gateway(api_id, api_hash, session)
        if not await self.gateway.is_authorized():  # type: ignore[union-attr]
            raise AuthenticationRequired("Telegram session has expired")
        await self._build_monitor()
        return {"authenticated": True}

    async def _auth_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_id = _positive_int(payload.get("api_id"), "API ID")
        api_hash = _required_string(payload.get("api_hash"), "API hash")
        phone = _required_string(payload.get("phone"), "Phone number")
        self._pending_api_id = api_id
        self._pending_api_hash = api_hash
        await self._replace_gateway(api_id, api_hash)
        await self.gateway.request_code(phone)  # type: ignore[union-attr]
        return {"status": "code_required"}

    async def _auth_submit_code(self, payload: dict[str, Any]) -> dict[str, Any]:
        gateway = self._require_gateway()
        status = await gateway.submit_code(_required_string(payload.get("code"), "Login code"))
        if status == "password_required":
            return {"status": status}
        await self._build_monitor()
        return self._authorized_payload()

    async def _auth_submit_password(self, payload: dict[str, Any]) -> dict[str, Any]:
        gateway = self._require_gateway()
        await gateway.submit_password(_required_string(payload.get("password"), "Password"))
        await self._build_monitor()
        return self._authorized_payload()

    async def _auth_logout(self, _payload: dict[str, Any]) -> dict[str, bool]:
        if self.monitor:
            await self.monitor.shutdown()
        remotely_revoked = False
        if self.gateway:
            try:
                await self.gateway.logout()
                remotely_revoked = True
            except Exception:
                # Local logout must still succeed when Telegram is unreachable.
                remotely_revoked = False
            finally:
                await self.gateway.disconnect()
        self.gateway = None
        self.monitor = None
        return {"ok": True, "remotely_revoked": remotely_revoked}

    async def _chats_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        gateway = self._require_authenticated_gateway()
        peers = await gateway.list_peers()
        self.database.replace_peers(peers)
        return self.database.list_peers()

    async def _settings_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return self.database.get_settings()

    async def _settings_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = payload.get("values")
        if not isinstance(values, dict):
            raise ValidationError("Settings values are required")
        destination = values.get("destination_peer_id")
        if destination is not None:
            destination = int(destination)
            sources = {source.peer_id for source in self.database.list_sources()}
            if destination in sources:
                raise ValidationError("Destination chat cannot also be a source")
            peer = next(
                (item for item in self.database.list_peers() if item["peer_id"] == destination),
                None,
            )
            if peer is None or not peer["can_write"]:
                raise ValidationError("Destination must be an available writable chat")
            values["destination_peer_id"] = destination
        return self.database.update_settings(values)

    async def _ollama_chat(self, payload: dict[str, Any]) -> dict[str, str]:
        message = payload.get("message")
        if not isinstance(message, str):
            raise ValidationError("Ollama test message is required")
        return await OllamaClient().chat(message, self.database.get_settings())

    async def _sources_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [source.to_dict() for source in self.database.list_sources()]

    async def _sources_upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self.database.upsert_source(
            peer_id=int(payload["peer_id"]),
            enabled=bool(payload.get("enabled", True)),
            initial_scan_mode=str(payload.get("initial_scan_mode", "now")),
            initial_scan_value=(
                int(payload["initial_scan_value"])
                if payload.get("initial_scan_value") is not None
                else None
            ),
        )
        return source.to_dict()

    async def _sources_remove(self, payload: dict[str, Any]) -> dict[str, bool]:
        self.database.remove_source(int(payload["peer_id"]))
        return {"ok": True}

    async def _rules_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        source = payload.get("source_peer_id")
        rules = self.database.list_rules(int(source) if source is not None else None)
        return [rule.to_dict() for rule in rules]

    async def _rules_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule = self.database.create_rule(
            source_peer_id=(
                int(payload["source_peer_id"])
                if payload.get("source_peer_id") is not None
                else None
            ),
            rule_type=str(payload["type"]),
            pattern=str(payload["pattern"]),
            case_sensitive=bool(payload.get("case_sensitive", False)),
            whole_word=bool(payload.get("whole_word", False)),
        )
        return rule.to_dict()

    async def _rules_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule_id = str(payload.get("id", ""))
        values = payload.get("values")
        if not rule_id or not isinstance(values, dict):
            raise ValidationError("Rule ID and values are required")
        return self.database.update_rule(rule_id, values).to_dict()

    async def _rules_delete(self, payload: dict[str, Any]) -> dict[str, bool]:
        self.database.delete_rule(str(payload["id"]))
        return {"ok": True}

    async def _ai_rules_list(self, _payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [rule.to_dict() for rule in self.database.list_ai_rules()]

    async def _ai_rules_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule = self.database.create_ai_rule(
            prompt=payload.get("prompt"),
            action_prompt=payload.get("action_prompt"),
            apply_to=payload.get("apply_to", "forwarded"),
        )
        return rule.to_dict()

    async def _ai_rules_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule_id = str(payload.get("id", ""))
        values = payload.get("values")
        if not rule_id or not isinstance(values, dict):
            raise ValidationError("AI rule ID and values are required")
        return self.database.update_ai_rule(rule_id, values).to_dict()

    async def _ai_rules_delete(self, payload: dict[str, Any]) -> dict[str, bool]:
        self.database.delete_ai_rule(str(payload["id"]))
        return {"ok": True}

    async def _testing_evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_peer_id = _positive_or_negative_int(
            payload.get("source_peer_id"), "Source chat"
        )
        source = next(
            (
                item
                for item in self.database.list_sources()
                if item.peer_id == source_peer_id
            ),
            None,
        )
        if source is None:
            raise ValidationError("Choose a configured source chat")

        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValidationError("Test message is required")
        if len(message) > 8_000:
            raise ValidationError("Test message cannot exceed 8,000 characters")
        is_forwarded = payload.get("is_forwarded", False)
        if not isinstance(is_forwarded, bool):
            raise ValidationError("Test forwarded state must be true or false")

        rules = [
            rule for rule in self.database.list_rules(source_peer_id) if rule.enabled
        ]
        result = match_message(message, rules)
        matched_rule_ids = {rule.id for rule in result.matched_rules}
        settings = self.database.get_settings()
        evaluated_ai_rules: list[dict[str, Any]] = []
        ai_matched = False
        for ai_rule in self.database.list_ai_rules():
            if not ai_rule.enabled:
                continue
            applicable = ai_rule.apply_to.value == "all" or is_forwarded
            matched = False
            action_result = None
            if applicable:
                matched = await OllamaClient().classify(
                    message, {**settings, "ollama_prompt": ai_rule.prompt}
                )
                if matched and ai_rule.action_prompt:
                    action_result = await OllamaClient().act(
                        message, ai_rule.action_prompt, settings
                    )
            ai_matched = ai_matched or matched
            evaluated_ai_rules.append(
                {
                    **ai_rule.to_dict(),
                    "applicable": applicable,
                    "matched": matched,
                    "action_result": action_result,
                }
            )
        matched = result.matched or ai_matched
        destination_configured = settings["destination_peer_id"] is not None
        would_send = matched and source.enabled and destination_configured
        matched_ai_rules = [rule for rule in evaluated_ai_rules if rule["matched"]]
        preview_rules = result.matched_rules + tuple(
            Rule(
                id=rule["id"],
                source_peer_id=None,
                type=RuleType.PHRASE,
                pattern="ИИ",
            )
            for rule in matched_ai_rules
        )
        preview_addition = "\n\n".join(
            rule["action_result"]
            for rule in matched_ai_rules
            if rule["action_result"]
        ) or None

        copy_preview_html = None
        if matched and settings["delivery_mode"] == "copy":
            preview_message = MessageEnvelope(
                source_peer_id=source_peer_id,
                source_message_id=0,
                source_timestamp=datetime.now(UTC),
                source_name=source.display_name,
                text=message,
                is_forwarded=is_forwarded,
            )
            copy_preview_html = format_copy(
                preview_message,
                preview_rules,
                additional_content=preview_addition,
            ).text

        if not matched:
            reason = "no_match"
        elif not source.enabled:
            reason = "source_disabled"
        elif not destination_configured:
            reason = "destination_missing"
        else:
            reason = "matched_rules"

        return {
            "source_peer_id": source_peer_id,
            "source_enabled": source.enabled,
            "message_is_forwarded": is_forwarded,
            "destination_peer_id": settings["destination_peer_id"],
            "delivery_mode": settings["delivery_mode"],
            "matched": matched,
            "would_send": would_send,
            "copy_preview_html": copy_preview_html,
            "reason": reason,
            "evaluated_rules": [
                {**rule.to_dict(), "matched": rule.id in matched_rule_ids}
                for rule in rules
            ],
            "evaluated_ai_rules": evaluated_ai_rules,
        }

    async def _monitor_start(self, _payload: dict[str, Any]) -> dict[str, Any]:
        if not self.database.list_sources():
            raise ValidationError("Choose at least one source chat")
        has_literal_rule = any(rule.enabled for rule in self.database.list_rules())
        has_ai_rule = any(rule.enabled for rule in self.database.list_ai_rules())
        if not has_literal_rule and not has_ai_rule:
            raise ValidationError("Create at least one enabled rule")
        monitor = await self._require_monitor()
        return await monitor.start()

    async def _monitor_pause(self, _payload: dict[str, Any]) -> dict[str, Any]:
        monitor = await self._require_monitor()
        return await monitor.pause()

    async def _monitor_status(self, _payload: dict[str, Any]) -> dict[str, Any]:
        if self.monitor:
            return self.monitor.snapshot()
        return {"state": "paused", "counts": self.database.processing_counts()}

    async def _processing_skip(self, payload: dict[str, Any]) -> dict[str, bool]:
        self.database.skip_failure(
            int(payload["source_peer_id"]), int(payload["source_message_id"])
        )
        return {"ok": True}

    async def _processing_retry(self, payload: dict[str, Any]) -> dict[str, bool]:
        self.database.retry_failure(
            int(payload["source_peer_id"]), int(payload["source_message_id"])
        )
        return {"ok": True}

    async def _replace_gateway(
        self, api_id: int, api_hash: str, session: str | None = None
    ) -> None:
        if self.gateway:
            await self.gateway.disconnect()
        self.gateway = TelethonGateway(api_id, api_hash, session)
        await self.gateway.connect()
        self.monitor = None

    async def _build_monitor(self) -> None:
        gateway = self._require_authenticated_gateway()
        account_id = await gateway.account_id()
        processor = MessageProcessor(
            self.database, gateway, account_id=account_id, emit=self.emit
        )
        self.monitor = Monitor(
            self.database, gateway, processor, emit=self.emit
        )

    async def _require_monitor(self) -> Monitor:
        if self.monitor is None:
            await self._build_monitor()
        return self.monitor  # type: ignore[return-value]

    def _authorized_payload(self) -> dict[str, Any]:
        gateway = self._require_gateway()
        return {
            "status": "authorized",
            "authenticated": True,
            "_sensitive_session": gateway.export_session(),
            "_sensitive_api_id": self._pending_api_id,
            "_sensitive_api_hash": self._pending_api_hash,
        }

    async def _is_authenticated(self) -> bool:
        return bool(self.gateway and await self.gateway.is_authorized())

    def _require_gateway(self) -> TelethonGateway:
        if self.gateway is None:
            raise AuthenticationRequired("Start Telegram sign-in first")
        return self.gateway

    def _require_authenticated_gateway(self) -> TelethonGateway:
        gateway = self._require_gateway()
        return gateway


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} is required")
    return value.strip()


def _positive_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{label} must be a number") from error
    if parsed <= 0:
        raise ValidationError(f"{label} must be positive")
    return parsed


def _positive_or_negative_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{label} must be a number") from error
    if parsed == 0:
        raise ValidationError(f"{label} cannot be zero")
    return parsed
