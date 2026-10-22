# Local key storage

Phase 2's local demo provisions identities under the ignored `local/` directory.
`generate_keys.py` can separately create encrypted sensor keys here. All files
except this README are ignored by Git. Sensor keys use encrypted PKCS8; TLS
service keys use restrictive file permissions. Never publish private keys or
TLS credentials. Git exclusions alone are not key protection. Runtime registry
loading, revocation and rotation remain Phase 3.
