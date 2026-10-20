from __future__ import annotations

from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.contracts import RawReading
from core.provenance.signer import Signer

T0 = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)


def raw(sensor_id: str = "sensor_01", value: float | None = 25.5, ts: datetime = T0) -> RawReading:
    return RawReading(sensor_id=sensor_id, timestamp=ts, value=value, unit="C")


@pytest.fixture
def private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def signer(private_key) -> Signer:
    return Signer("sensor_01", private_key)
