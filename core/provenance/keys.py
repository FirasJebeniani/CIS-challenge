"""Ed25519 key files.

Layout (default ``keys/``):
    keys/private/<sensor_id>.key   PKCS#8 PEM, field side only, never committed
    keys/public/<sensor_id>.pub    SubjectPublicKeyInfo PEM
    keys/public/registry.json      sensor_id -> public key, read by the L1b
                                   key registry
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PASSPHRASE_ENV = "CIS_KEY_PASSPHRASE"


def private_key_path(keys_dir: Path, sensor_id: str) -> Path:
    return keys_dir / "private" / f"{sensor_id}.key"


def public_key_path(keys_dir: Path, sensor_id: str) -> Path:
    return keys_dir / "public" / f"{sensor_id}.pub"


def registry_path(keys_dir: Path) -> Path:
    return keys_dir / "public" / "registry.json"


def _passphrase(passphrase: str | None) -> bytes | None:
    value = passphrase if passphrase is not None else os.environ.get(PASSPHRASE_ENV)
    return value.encode("utf-8") if value else None


def save_private_key(path: Path, key: Ed25519PrivateKey, passphrase: str | None = None) -> None:
    secret = _passphrase(passphrase)
    encryption = (
        serialization.BestAvailableEncryption(secret)
        if secret
        else serialization.NoEncryption()
    )
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL: never silently overwrite a key; 0o600 is honoured on POSIX only
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)


def load_private_key(path: Path, passphrase: str | None = None) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), _passphrase(passphrase))
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{path} is not an Ed25519 private key")
    return key


def save_public_key(path: Path, key: Ed25519PublicKey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"{path} is not an Ed25519 public key")
    return key


def raw_public_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def register_public_key(keys_dir: Path, sensor_id: str, key: Ed25519PublicKey) -> None:
    """Add/replace a sensor's entry in keys/public/registry.json."""
    path = registry_path(keys_dir)
    registry = json.loads(path.read_text("utf-8")) if path.exists() else {"sensors": {}}
    registry["sensors"][sensor_id] = {
        "algorithm": "Ed25519",
        "public_key": raw_public_bytes(key).hex(),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", "utf-8")


def generate_sensor_keys(
    keys_dir: Path, sensor_id: str, passphrase: str | None = None
) -> Ed25519PublicKey:
    """Create the key pair of one sensor and publish its public key."""
    private_key = Ed25519PrivateKey.generate()
    save_private_key(private_key_path(keys_dir, sensor_id), private_key, passphrase)
    public_key = private_key.public_key()
    save_public_key(public_key_path(keys_dir, sensor_id), public_key)
    register_public_key(keys_dir, sensor_id, public_key)
    return public_key
