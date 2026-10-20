"""L1a signer: runs next to the sensor (emulated secure element).

For every RawReading it assigns the next sequence number (monotonic counter),
links the record to the previous one (prev_hash = hash chain) and signs it
with the sensor's Ed25519 private key.

The counter and the chain head can be persisted so that a restart continues
the chain instead of restarting at seq 0 (which L1b would flag as a replay).
The state is saved *before* the signed reading is returned: after a crash a
sequence number may be skipped (seen as a gap) but is never reused.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from core.contracts import RawReading, SignedReading
from core.provenance import codec
from core.provenance.keys import load_private_key


class Signer:
    def __init__(
        self,
        sensor_id: str,
        private_key: Ed25519PrivateKey,
        state_path: Path | None = None,
    ) -> None:
        self.sensor_id = sensor_id
        self._key = private_key
        self._state_path = state_path
        self._lock = threading.Lock()
        self._next_seq = 0
        self._prev_hash = codec.genesis_hash(sensor_id)
        if state_path is not None and state_path.exists():
            self._load_state(state_path)

    @classmethod
    def from_key_file(
        cls,
        sensor_id: str,
        key_path: Path,
        passphrase: str | None = None,
        state_path: Path | None = None,
    ) -> Signer:
        return cls(sensor_id, load_private_key(key_path, passphrase), state_path)

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._key.public_key()

    @property
    def next_seq(self) -> int:
        return self._next_seq

    @property
    def chain_head(self) -> bytes:
        """prev_hash that the next signed reading will carry."""
        return self._prev_hash

    def sign(self, raw: RawReading) -> SignedReading:
        if raw.sensor_id != self.sensor_id:
            raise ValueError(f"signer of {self.sensor_id} cannot sign for {raw.sensor_id}")
        with self._lock:
            payload = codec.signed_payload(
                raw.sensor_id, self._next_seq, raw.timestamp, raw.value, raw.unit, self._prev_hash
            )
            reading = SignedReading(
                sensor_id=raw.sensor_id,
                seq=self._next_seq,
                timestamp=raw.timestamp,
                value=payload["value"],
                unit=raw.unit,
                prev_hash=self._prev_hash,
                signature=self._key.sign(codec.signing_bytes(payload)),
            )
            self._next_seq += 1
            self._prev_hash = codec.record_hash(reading)
            self._save_state()
            return reading

    def _load_state(self, path: Path) -> None:
        state = json.loads(path.read_text("utf-8"))
        if state["sensor_id"] != self.sensor_id:
            raise ValueError(f"{path} holds the state of {state['sensor_id']}")
        self._next_seq = int(state["next_seq"])
        self._prev_hash = bytes.fromhex(state["prev_hash"])

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        state = {
            "sensor_id": self.sensor_id,
            "next_seq": self._next_seq,
            "prev_hash": self._prev_hash.hex(),
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_name(self._state_path.name + ".tmp")
        tmp.write_text(json.dumps(state), "utf-8")
        os.replace(tmp, self._state_path)  # atomic: never a half-written state
