from __future__ import annotations

import hashlib


def delivery_random_id(
    *,
    account_id: int,
    destination_peer_id: int,
    source_peer_id: int,
    source_message_id: int,
    purpose: str = "delivery",
) -> int:
    prefix = "chatrd:delivery:v1" if purpose == "delivery" else f"chatrd:{purpose}:v1"
    material = (
        f"{prefix}|{account_id}|{destination_peer_id}|{source_peer_id}|{source_message_id}"
    ).encode("ascii")
    unsigned = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    signed = unsigned if unsigned < 2**63 else unsigned - 2**64
    return signed or 1
