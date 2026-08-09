from chatrd_worker.idempotency import delivery_random_id


def test_id_is_deterministic_nonzero_signed_64_bit() -> None:
    values = {
        "account_id": 1,
        "destination_peer_id": -1004,
        "source_peer_id": -1009,
        "source_message_id": 44,
    }
    first = delivery_random_id(**values)
    assert first == delivery_random_id(**values)
    assert first != 0
    assert -(2**63) <= first < 2**63


def test_domain_inputs_change_id() -> None:
    baseline = delivery_random_id(
        account_id=1,
        destination_peer_id=2,
        source_peer_id=3,
        source_message_id=4,
    )
    changed = delivery_random_id(
        account_id=1,
        destination_peer_id=2,
        source_peer_id=3,
        source_message_id=5,
    )
    assert baseline != changed
    assert delivery_random_id(
        account_id=1,
        destination_peer_id=2,
        source_peer_id=3,
        source_message_id=4,
        purpose="ai-action",
    ) != baseline
