from __future__ import annotations

import asyncio

from chatrd_worker.monitor import Monitor
from chatrd_worker.processor import MessageProcessor
from fakes import FakeGateway
from test_processor import envelope


async def test_now_mode_initializes_high_water_without_old_delivery(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )
    gateway = FakeGateway()
    gateway.messages[-1001] = [envelope(1), envelope(2)]
    monitor = Monitor(
        database,
        gateway,
        MessageProcessor(database, gateway, account_id=7),
    )
    result = await monitor.start()
    assert result["state"] == "monitoring"
    assert database.get_cursor(-1001) == 2
    assert gateway.sent == []


async def test_latest_count_processes_oldest_to_newest(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="latest_count",
        initial_scan_value=2,
    )
    database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )
    gateway = FakeGateway()
    gateway.messages[-1001] = [envelope(1), envelope(2), envelope(3)]
    monitor = Monitor(
        database,
        gateway,
        MessageProcessor(database, gateway, account_id=7),
    )
    await monitor.start()
    assert len(gateway.sent) == 2
    assert database.processing_row(-1001, 1) is None
    assert database.get_cursor(-1001) == 3


async def test_live_source_is_processed_and_unmonitored_source_is_ignored(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )
    gateway = FakeGateway()
    monitor = Monitor(
        database,
        gateway,
        MessageProcessor(database, gateway, account_id=7),
    )
    await monitor.start()
    await gateway.emit(envelope(10))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(gateway.sent) == 1
    await monitor.pause()
    await gateway.emit(envelope(11))
    await asyncio.sleep(0)
    assert len(gateway.sent) == 1


async def test_live_events_buffer_during_catchup_then_drain_in_order(database) -> None:
    database.upsert_source(
        peer_id=-1001,
        enabled=True,
        initial_scan_mode="now",
        initial_scan_value=None,
    )
    database.create_rule(
        source_peer_id=None, rule_type="keyword", pattern="release"
    )
    gateway = FakeGateway()
    monitor = Monitor(
        database,
        gateway,
        MessageProcessor(database, gateway, account_id=7),
    )
    database.update_settings({"paused": False})
    monitor.state = "catching_up"
    await monitor._on_live_message(envelope(12))
    await monitor._on_live_message(envelope(11))
    await monitor._on_live_message(envelope(12))
    assert gateway.sent == []
    await monitor._drain_buffer(-1001)
    assert len(gateway.sent) == 2
    assert database.get_cursor(-1001) == 12
