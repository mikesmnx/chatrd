from __future__ import annotations

import sys
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from chatrd_worker.database import Database  # noqa: E402
from chatrd_worker.models import TelegramPeer  # noqa: E402


@pytest.fixture
def database(tmp_path: Path) -> Database:
    instance = Database(tmp_path / "chatrd.db")
    instance.replace_peers(
        [
            TelegramPeer(-1001, "supergroup", "Source One", "source_one", True),
            TelegramPeer(-1002, "supergroup", "Source Two", None, True),
            TelegramPeer(42, "user", "Saved Messages", None, True),
        ]
    )
    instance.update_settings({"destination_peer_id": 42})
    yield instance
    instance.close()

