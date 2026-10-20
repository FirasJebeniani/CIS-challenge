from __future__ import annotations

from datetime import datetime, timezone

import cbor2
import pytest

from core.provenance import codec
from tests.conftest import T0, raw


def test_epoch_microseconds_roundtrip():
    for ts in (T0, datetime(1970, 1, 1, tzinfo=timezone.utc), datetime(2099, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)):
        assert codec.from_epoch_us(codec.to_epoch_us(ts)) == ts


def test_cbor_roundtrip_is_identical(signer):
    reading = signer.sign(raw())
    data = codec.encode(reading)
    assert codec.decode(data) == reading
    assert codec.encode(codec.decode(data)) == data


def test_canonical_encoding_is_deterministic(signer):
    reading = signer.sign(raw())
    payload = codec.payload_of(reading)
    shuffled = dict(reversed(list(payload.items())))
    assert codec.signing_bytes(payload) == codec.signing_bytes(shuffled)


def test_int_and_float_values_sign_identically():
    common = ("sensor_01", 0, T0)
    a = codec.signed_payload(*common, 25, "C", b"\x00" * 32)
    b = codec.signed_payload(*common, 25.0, "C", b"\x00" * 32)
    assert codec.signing_bytes(a) == codec.signing_bytes(b)


def test_genesis_differs_per_sensor():
    assert codec.genesis_hash("sensor_01") != codec.genesis_hash("sensor_02")
    assert len(codec.genesis_hash("sensor_01")) == 32


def test_cbor_is_smaller_than_json(signer):
    reading = signer.sign(raw())
    assert len(codec.encode(reading)) < len(reading.model_dump_json())


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xff\x00garbage",
        cbor2.dumps([1, 2, 3]),
        cbor2.dumps({"sensor_id": "sensor_01"}),
        b"\x00" * (codec.MAX_WIRE_SIZE + 1),
    ],
)
def test_decode_rejects_malformed(data):
    with pytest.raises(codec.DecodeError):
        codec.decode(data)


def _wire(signer, **changes):
    wire = cbor2.loads(codec.encode(signer.sign(raw())))
    wire.update(changes)
    return cbor2.dumps(wire)


def test_decode_rejects_extra_field(signer):
    with pytest.raises(codec.DecodeError):
        codec.decode(_wire(signer, extra=1))


@pytest.mark.parametrize(
    "changes",
    [
        {"timestamp_us": "2026-01-01"},
        {"timestamp_us": 1.5},
        {"seq": "1"},
        {"prev_hash": b"short"},
        {"signature": "not-bytes"},
        {"value": "25.5"},
    ],
)
def test_decode_rejects_wrong_types(signer, changes):
    with pytest.raises(codec.DecodeError):
        codec.decode(_wire(signer, **changes))
