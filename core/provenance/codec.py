"""Canonical encoding of signed readings, shared by the L1a signer and the L1b
verifier so that both sides rebuild exactly the same signed bytes.

Signed bytes   = SIGNING_CONTEXT || CBOR_canonical({sensor_id, seq,
                 timestamp_us, value, unit, prev_hash})
Record hash    = SHA-256(signed bytes || signature)   -> next record's prev_hash
Genesis hash   = SHA-256(GENESIS_CONTEXT || sensor_id) -> prev_hash of seq 0
Wire format    = CBOR_canonical(signed fields + signature), sent over MQTT

CBOR canonical encoding (RFC 8949 §4.2) gives one byte string per value
(sorted map keys, shortest integer/float forms). Timestamps are integer
microseconds since the Unix epoch, so no string formatting is involved.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import cbor2
from pydantic import ValidationError

from core.contracts import SignedReading

SIGNING_CONTEXT = b"CIS-L1a/v1\x00"
GENESIS_CONTEXT = b"CIS-L1a/genesis/v1\x00"
MAX_WIRE_SIZE = 1024  # a signed reading is ~150 bytes; reject anything far larger

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_SIGNED_FIELDS = frozenset({"sensor_id", "seq", "timestamp_us", "value", "unit", "prev_hash"})
_WIRE_FIELDS = _SIGNED_FIELDS | {"signature"}


class DecodeError(ValueError):
    """The bytes received are not a well-formed signed reading."""


def to_epoch_us(ts: datetime) -> int:
    delta = ts - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def from_epoch_us(us: int) -> datetime:
    return _EPOCH + timedelta(microseconds=us)


def signed_payload(
    sensor_id: str,
    seq: int,
    timestamp: datetime,
    value: float | None,
    unit: str,
    prev_hash: bytes,
) -> dict[str, Any]:
    """The fields covered by the signature, in wire representation."""
    return {
        "sensor_id": sensor_id,
        "seq": seq,
        "timestamp_us": to_epoch_us(timestamp),
        # always a CBOR float, so 25 and 25.0 sign identically
        "value": None if value is None else float(value),
        "unit": unit,
        "prev_hash": bytes(prev_hash),
    }


def payload_of(reading: SignedReading) -> dict[str, Any]:
    return signed_payload(
        reading.sensor_id,
        reading.seq,
        reading.timestamp,
        reading.value,
        reading.unit,
        reading.prev_hash,
    )


def signing_bytes(payload: dict[str, Any]) -> bytes:
    return SIGNING_CONTEXT + cbor2.dumps(payload, canonical=True)


def record_hash(reading: SignedReading) -> bytes:
    """Hash of the whole signed record; becomes the next record's prev_hash."""
    return hashlib.sha256(signing_bytes(payload_of(reading)) + reading.signature).digest()


def genesis_hash(sensor_id: str) -> bytes:
    """prev_hash of a sensor's first record (seq 0)."""
    return hashlib.sha256(GENESIS_CONTEXT + sensor_id.encode("utf-8")).digest()


def encode(reading: SignedReading) -> bytes:
    """SignedReading -> CBOR bytes for MQTT."""
    wire = payload_of(reading)
    wire["signature"] = reading.signature
    return cbor2.dumps(wire, canonical=True)


def decode(data: bytes) -> SignedReading:
    """CBOR bytes from MQTT -> SignedReading. Raises DecodeError, never returns
    a partially filled object. Does NOT verify the signature (that is L1b)."""
    if len(data) > MAX_WIRE_SIZE:
        raise DecodeError(f"message too large ({len(data)} bytes)")
    try:
        wire = cbor2.loads(data)
    except Exception as exc:  # cbor2 raises several error types on bad input
        raise DecodeError(f"invalid CBOR: {exc}") from exc
    if not isinstance(wire, dict):
        raise DecodeError("CBOR payload is not a map")
    if set(wire) != _WIRE_FIELDS:
        missing = sorted(_WIRE_FIELDS - set(wire))
        extra = sorted(map(str, set(wire) - _WIRE_FIELDS))
        raise DecodeError(f"bad fields (missing={missing}, unexpected={extra})")
    ts = wire["timestamp_us"]
    if type(ts) is not int:
        raise DecodeError("timestamp_us must be an integer")
    try:
        return SignedReading(
            sensor_id=wire["sensor_id"],
            seq=wire["seq"],
            timestamp=from_epoch_us(ts),
            value=wire["value"],
            unit=wire["unit"],
            prev_hash=wire["prev_hash"],
            signature=wire["signature"],
        )
    except (ValidationError, OverflowError) as exc:
        raise DecodeError(f"invalid reading: {exc}") from exc
