from __future__ import annotations

import json

import pytest

from core.provenance import codec
from core.provenance.keys import (
    generate_sensor_keys,
    load_private_key,
    load_public_key,
    private_key_path,
    public_key_path,
    raw_public_bytes,
    registry_path,
)
from core.provenance.signer import Signer
from tests.conftest import raw


def test_generated_keys_sign_and_verify(tmp_path):
    public_key = generate_sensor_keys(tmp_path, "sensor_01")
    signer = Signer.from_key_file("sensor_01", private_key_path(tmp_path, "sensor_01"))
    reading = signer.sign(raw())
    load_public_key(public_key_path(tmp_path, "sensor_01")).verify(
        reading.signature, codec.signing_bytes(codec.payload_of(reading))
    )
    assert raw_public_bytes(signer.public_key) == raw_public_bytes(public_key)


def test_registry_lists_public_keys(tmp_path):
    keys = {sid: generate_sensor_keys(tmp_path, sid) for sid in ("sensor_01", "sensor_02", "sensor_03")}
    registry = json.loads(registry_path(tmp_path).read_text())["sensors"]
    assert set(registry) == set(keys)
    for sid, key in keys.items():
        assert registry[sid]["public_key"] == raw_public_bytes(key).hex()
        assert registry[sid]["algorithm"] == "Ed25519"
    assert len({e["public_key"] for e in registry.values()}) == 3  # one key pair per sensor


def test_registry_never_contains_private_material(tmp_path):
    generate_sensor_keys(tmp_path, "sensor_01")
    assert "PRIVATE" not in registry_path(tmp_path).read_text()
    assert not any(p.suffix == ".key" for p in (tmp_path / "public").iterdir())


def test_existing_key_is_not_overwritten(tmp_path):
    generate_sensor_keys(tmp_path, "sensor_01")
    with pytest.raises(FileExistsError):
        generate_sensor_keys(tmp_path, "sensor_01")


def test_passphrase_protected_key(tmp_path):
    generate_sensor_keys(tmp_path, "sensor_01", passphrase="s3cret")
    path = private_key_path(tmp_path, "sensor_01")
    assert b"ENCRYPTED" in path.read_bytes()
    load_private_key(path, passphrase="s3cret")
    with pytest.raises((TypeError, ValueError)):
        load_private_key(path, passphrase="")
