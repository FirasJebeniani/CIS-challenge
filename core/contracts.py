"""Data contracts shared by every layer (Pydantic v2).

These models are the *internal* format of the pipeline. Datasets and the MQTT
wire format are converted to/from these models by adapters and codecs; nothing
downstream should depend on a dataset's column names or on CBOR details.

Flow:  RawReading --(L1a signer)--> SignedReading --(MQTT/CBOR)-->
       VerifiedReading (L1b) --> FeatureWindow (L2) --> L3 / L4
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

HASH_SIZE = 32  # SHA-256
SIGNATURE_SIZE = 64  # Ed25519


def _to_utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc)


def _finite(value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError("value must be finite (use None for a missing measurement)")
    return value


SensorId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]
Measurement = Annotated[float | None, AfterValidator(_finite)]
Unit = Annotated[str, Field(min_length=1, max_length=16)]


class _Contract(BaseModel):
    # bytes fields (hashes, signatures) are shown as hex in JSON (debug output)
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, ser_json_bytes="hex", val_json_bytes="hex"
    )


class RawReading(_Contract):
    """One measurement as produced by a field sensor, before signing."""

    sensor_id: SensorId
    timestamp: UtcDatetime
    value: Measurement
    unit: Unit


class SignedReading(_Contract):
    """A reading signed by the L1a signer:
    {sensor_id, seq, timestamp, value, unit, prev_hash, signature}.

    ``prev_hash`` links the record to the previous record of the same sensor
    (hash chain); ``signature`` is Ed25519 over the canonical encoding defined
    in ``core.provenance.codec``.
    """

    sensor_id: SensorId
    seq: int = Field(ge=0)
    timestamp: UtcDatetime
    value: Measurement
    unit: Unit
    prev_hash: bytes = Field(min_length=HASH_SIZE, max_length=HASH_SIZE)
    signature: bytes = Field(min_length=SIGNATURE_SIZE, max_length=SIGNATURE_SIZE)


class ProvenanceStatus(str, Enum):
    """Verdict of the L1b verifier. Passed on to L4, not only used as a gate."""

    VALID = "valid"
    BAD_SIGNATURE = "bad_signature"
    UNKNOWN_SENSOR = "unknown_sensor"
    REPLAY = "replay"
    GAP = "gap"
    OUT_OF_WINDOW = "out_of_window"


class VerifiedReading(_Contract):
    """Output of L1b: the received reading plus its provenance verdict.

    Readings that fail verification are still emitted (with their status) so
    that L4 can account for them; L2 decides whether they are usable.
    """

    reading: SignedReading
    status: ProvenanceStatus
    received_at: UtcDatetime
    missing_before: int = Field(default=0, ge=0)  # seqs lost just before this one
    detail: str | None = None

    @property
    def is_authentic(self) -> bool:
        """Cryptographically authentic. Says nothing about physical truth."""
        return self.status in (ProvenanceStatus.VALID, ProvenanceStatus.GAP)


class FeatureWindow(_Contract):
    """Output of L2: one window per sensor per time step, input of L3."""

    sensor_id: SensorId
    ts: UtcDatetime
    raw_value: Measurement
    clean_value: Measurement
    rolling_features: dict[str, float] = Field(default_factory=dict)
    spatial_features: dict[str, float] = Field(default_factory=dict)
    neighbor_consensus: float | None = None
    seasonal_residual: float | None = None
    ref_data_features: dict[str, float] = Field(default_factory=dict)
    provenance_status: ProvenanceStatus
