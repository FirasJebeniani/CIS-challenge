from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.provenance import codec
from core.provenance.signer import Signer
from tests.conftest import T0, raw


def verify(public_key, reading) -> None:
    public_key.verify(reading.signature, codec.signing_bytes(codec.payload_of(reading)))


def sign_series(signer: Signer, n: int):
    return [signer.sign(raw(value=20.0 + i, ts=T0 + timedelta(seconds=2 * i))) for i in range(n)]


def test_signature_verifies_with_public_key(signer):
    verify(signer.public_key, signer.sign(raw()))


def test_tampered_value_breaks_signature(signer):
    reading = signer.sign(raw(value=25.5))
    tampered = reading.model_copy(update={"value": 30.5})
    with pytest.raises(InvalidSignature):
        verify(signer.public_key, tampered)


@pytest.mark.parametrize(
    "update",
    [{"seq": 7}, {"timestamp": T0 + timedelta(hours=1)}, {"unit": "F"}, {"sensor_id": "sensor_02"}, {"prev_hash": b"\x00" * 32}],
)
def test_any_signed_field_change_breaks_signature(signer, update):
    reading = signer.sign(raw())
    with pytest.raises(InvalidSignature):
        verify(signer.public_key, reading.model_copy(update=update))


def test_other_key_does_not_verify(signer):
    reading = signer.sign(raw())
    with pytest.raises(InvalidSignature):
        verify(Ed25519PrivateKey.generate().public_key(), reading)


def test_signer_refuses_other_sensor(signer):
    with pytest.raises(ValueError):
        signer.sign(raw(sensor_id="sensor_02"))


def test_sequence_is_monotonic(signer):
    assert [r.seq for r in sign_series(signer, 5)] == [0, 1, 2, 3, 4]


def test_hash_chain_links_records(signer):
    readings = sign_series(signer, 5)
    assert readings[0].prev_hash == codec.genesis_hash("sensor_01")
    for previous, current in zip(readings, readings[1:]):
        assert current.prev_hash == codec.record_hash(previous)
    assert signer.chain_head == codec.record_hash(readings[-1])


def test_modifying_old_record_breaks_chain_continuity(signer):
    readings = sign_series(signer, 3)
    rewritten = readings[0].model_copy(update={"value": 99.0})
    assert readings[1].prev_hash != codec.record_hash(rewritten)


def test_sensors_have_independent_chains():
    s1 = Signer("sensor_01", Ed25519PrivateKey.generate())
    s2 = Signer("sensor_02", Ed25519PrivateKey.generate())
    r1, r2 = s1.sign(raw("sensor_01")), s2.sign(raw("sensor_02"))
    s1.sign(raw("sensor_01"))
    assert r1.seq == r2.seq == 0
    assert r1.prev_hash != r2.prev_hash
    assert s1.next_seq == 2 and s2.next_seq == 1


def test_state_persists_across_restart(tmp_path, private_key):
    state = tmp_path / "sensor_01.json"
    first = Signer("sensor_01", private_key, state_path=state)
    before = sign_series(first, 3)

    restarted = Signer("sensor_01", private_key, state_path=state)
    after = restarted.sign(raw())
    assert after.seq == 3
    assert after.prev_hash == codec.record_hash(before[-1])


def test_state_file_of_other_sensor_is_rejected(tmp_path, private_key):
    state = tmp_path / "state.json"
    Signer("sensor_01", private_key, state_path=state).sign(raw())
    with pytest.raises(ValueError):
        Signer("sensor_02", private_key, state_path=state)
