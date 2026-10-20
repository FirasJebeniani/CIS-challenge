"""Generate one Ed25519 key pair per sensor.

    python -m tools.generate_keys                       # sensors from config/system.yaml
    python -m tools.generate_keys --sensors sensor_04

Private keys go to keys/private/ (git-ignored). Set CIS_KEY_PASSPHRASE to
encrypt them at rest; the node then needs the same variable to load them.
Public keys go to keys/public/ and keys/public/registry.json for L1b.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.config import load_config
from core.provenance.keys import generate_sensor_keys, private_key_path, raw_public_bytes


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sensors", nargs="+", default=[s.id for s in config.sensors])
    parser.add_argument("--keys-dir", type=Path, default=config.keys_dir)
    args = parser.parse_args()

    for sensor_id in args.sensors:
        if private_key_path(args.keys_dir, sensor_id).exists():
            print(f"{sensor_id}: key already exists, skipped (delete it to rotate)")
            continue
        public_key = generate_sensor_keys(args.keys_dir, sensor_id)
        print(f"{sensor_id}: public key {raw_public_bytes(public_key).hex()}")
    print("KEYS GENERATED")


if __name__ == "__main__":
    main()
