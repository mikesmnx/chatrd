from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .database import Database
from .models import AuthenticationRequired, ValidationError
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

    async def _monitor_start(self, _payload: dict[str, Any]) -> dict[str, Any]:
        if not self.database.list_sources():
            raise ValidationError("Choose at least one source chat")
        settings = self.database.get_settings()
        if not any(rule.enabled for rule in self.database.list_rules()) and not settings[
            "ai_enabled"
        ]:
            raise ValidationError("Create at least one enabled rule or enable AI matching")
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
