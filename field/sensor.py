"""Field sensors (in-situ side, before the L1a signer).

A sensor only measures: it returns RawReading objects. Sequence numbers and
the hash chain are added by the signer, which acts as the trust anchor.

    python -m field.sensor --sensor-id sensor_01 --interval 2
"""

from __future__ import annotations

import argparse
import random
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from typing import Protocol

from core.contracts import RawReading


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Sensor(Protocol):
    sensor_id: str

    def read(self) -> RawReading:
        """Next measurement. Raises StopIteration when the source is exhausted."""
        ...


class SimulatedTemperatureSensor:
    """Uniform random temperature in [low, high] °C."""

    unit = "C"

    def __init__(
        self,
        sensor_id: str,
        low: float = 20.0,
        high: float = 30.0,
        rng: random.Random | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if low >= high:
            raise ValueError("low must be < high")
        self.sensor_id = sensor_id
        self.low = low
        self.high = high
        self._rng = rng or random.Random()
        self._clock = clock

    def read(self) -> RawReading:
        return RawReading(
            sensor_id=self.sensor_id,
            timestamp=self._clock(),
            value=round(self._rng.uniform(self.low, self.high), 2),
            unit=self.unit,
        )


class DatasetSensor:
    """Plays back (timestamp, value) records of a real dataset as a sensor.

    Original timestamps and values are kept as-is; mapping a dataset's
    columns/units to these records is the job of the dataset adapter.
    """

    def __init__(
        self, sensor_id: str, records: Iterable[tuple[datetime, float | None]], unit: str
    ) -> None:
        self.sensor_id = sensor_id
        self.unit = unit
        self._records: Iterator[tuple[datetime, float | None]] = iter(records)

    def read(self) -> RawReading:
        timestamp, value = next(self._records)
        return RawReading(sensor_id=self.sensor_id, timestamp=timestamp, value=value, unit=self.unit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated temperature sensor")
    parser.add_argument("--sensor-id", default="sensor_01")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between readings")
    parser.add_argument("--count", type=int, default=0, help="stop after N readings (0 = forever)")
    args = parser.parse_args()

    sensor = SimulatedTemperatureSensor(args.sensor_id)
    print(f"SENSOR RUNNING: {sensor.sensor_id} every {args.interval}s (Ctrl+C to stop)")
    n = 0
    try:
        while args.count == 0 or n < args.count:
            reading = sensor.read()
            print(f"{reading.timestamp.isoformat()}  {reading.sensor_id}  {reading.value:.2f} {reading.unit}")
            n += 1
            if args.count == 0 or n < args.count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
