from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from core.contracts import (
    FeatureWindow,
    ProvenanceStatus,
    RawReading,
    SignedReading,
    VerifiedReading,
)
from tests.conftest import T0


def signed(**overrides) -> SignedReading:
    fields = dict(
        sensor_id="sensor_01", seq=0, timestamp=T0, value=25.5, unit="C",
        prev_hash=b"\x00" * 32, signature=b"\x01" * 64,
    )
    fields.update(overrides)
    return SignedReading(**fields)


def test_signed_reading_valid():
    reading = signed()
    assert reading.seq == 0 and reading.unit == "C"


def test_timestamp_normalised_to_utc():
    plus_one = timezone(timedelta(hours=1))
    reading = signed(timestamp=datetime(2026, 1, 1, 13, 0, tzinfo=plus_one))
    assert reading.timestamp == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert reading.timestamp.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"timestamp": datetime(2026, 1, 1, 12, 0)},  # naive datetime
        {"value": math.nan},
        {"value": math.inf},
        {"seq": -1},
        {"seq": "3"},  # strict: no str -> int coercion
        {"prev_hash": b"\x00" * 31},
        {"signature": b"\x00" * 63},
        {"sensor_id": "bad id!"},
        {"unit": ""},
    ],
)
def test_signed_reading_rejects_invalid(overrides):
    with pytest.raises(ValidationError):
        signed(**overrides)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        signed(extra="x")


def test_contracts_are_immutable():
    reading = signed()
    with pytest.raises(ValidationError):
        reading.value = 99.0


def test_missing_value_is_allowed():
    assert RawReading(sensor_id="s1", timestamp=T0, value=None, unit="C").value is None


def test_verified_reading_authenticity():
    ok = VerifiedReading(reading=signed(), status=ProvenanceStatus.VALID, received_at=T0)
    bad = VerifiedReading(reading=signed(), status=ProvenanceStatus.BAD_SIGNATURE, received_at=T0)
    assert ok.is_authentic and not bad.is_authentic


def test_feature_window_json_roundtrip():
    window = FeatureWindow(
        sensor_id="sensor_01", ts=T0, raw_value=25.5, clean_value=25.5,
        rolling_features={"mean_5": 25.1}, provenance_status=ProvenanceStatus.VALID,
    )
    assert FeatureWindow.model_validate_json(window.model_dump_json()) == window


def test_signed_reading_json_debug_uses_hex():
    reading = signed()
    text = reading.model_dump_json()
    assert "00" * 32 in text
    assert SignedReading.model_validate_json(text) == reading
