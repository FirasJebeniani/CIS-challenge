from __future__ import annotations

import random
from datetime import timedelta, timezone

import pytest

from field.sensor import DatasetSensor, SimulatedTemperatureSensor
from tests.conftest import T0


def test_simulated_values_in_range_and_utc():
    sensor = SimulatedTemperatureSensor("sensor_01", rng=random.Random(0))
    for _ in range(200):
        reading = sensor.read()
        assert 20.0 <= reading.value <= 30.0
        assert reading.unit == "C"
        assert reading.sensor_id == "sensor_01"
        assert reading.timestamp.tzinfo == timezone.utc


def test_seeded_simulation_is_reproducible():
    a = SimulatedTemperatureSensor("s", rng=random.Random(42), clock=lambda: T0)
    b = SimulatedTemperatureSensor("s", rng=random.Random(42), clock=lambda: T0)
    assert [a.read() for _ in range(10)] == [b.read() for _ in range(10)]


def test_invalid_range_rejected():
    with pytest.raises(ValueError):
        SimulatedTemperatureSensor("s", low=30, high=20)


def test_dataset_sensor_keeps_original_records():
    records = [(T0 + timedelta(minutes=i), v) for i, v in enumerate([12.5, None, 13.0])]
    sensor = DatasetSensor("station_7", records, unit="C")
    out = [sensor.read() for _ in records]
    assert [(r.timestamp, r.value) for r in out] == records
    with pytest.raises(StopIteration):
        sensor.read()
