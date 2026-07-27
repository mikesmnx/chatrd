from __future__ import annotations

from chatrd_worker.application import WorkerApplication
from chatrd_worker.models import TransientTelegramError
from fakes import FakeGateway


async def test_offline_logout_still_clears_local_gateway(tmp_path) -> None:
    application = WorkerApplication(tmp_path)
    gateway = FakeGateway()
    gateway.logout_error = TransientTelegramError("offline")
    application.gateway = gateway  # type: ignore[assignment]

    result = await application.dispatch("auth.logout", {})

    assert result == {"ok": True, "remotely_revoked": False}
    assert application.gateway is None
    application.database.close()


async def test_online_logout_reports_revocation(tmp_path) -> None:
    application = WorkerApplication(tmp_path)
    gateway = FakeGateway()
    application.gateway = gateway  # type: ignore[assignment]

    result = await application.dispatch("auth.logout", {})

    assert result == {"ok": True, "remotely_revoked": True}
    assert gateway.authorized is False
    application.database.close()

