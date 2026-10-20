"""Generate a local CA and the TLS certificates for Mosquitto (mutual TLS).

    python -m tools.generate_certs                   # server, gateway, every configured sensor
    python -m tools.generate_certs --clients sensor_04

Written to certs/ (git-ignored):
    ca.crt / ca.key                CA that signs everything below
    server.crt / server.key        broker identity (SAN localhost, 127.0.0.1)
    clients/<name>.crt / .key      one client identity per sensor + "gateway";
                                   the broker uses the CN as MQTT username (ACL)
Existing files are kept, so new clients can be added without breaking others.
"""

from __future__ import annotations

import argparse
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

GATEWAY_CLIENT = "gateway"
VALIDITY_DAYS = 825


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _write(path: Path, key: ec.EllipticCurvePrivateKey, cert: x509.Certificate) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.with_suffix(".crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _builder(subject: x509.Name, issuer: x509.Name, public_key, days: int) -> x509.CertificateBuilder:
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    )


def load_or_create_ca(certs_dir: Path, days: int = VALIDITY_DAYS):
    crt, key_path = certs_dir / "ca.crt", certs_dir / "ca.key"
    if crt.exists() and key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), None)
        return key, x509.load_pem_x509_certificate(crt.read_bytes())
    key = ec.generate_private_key(ec.SECP256R1())
    name = _name("CIS-Challenge Local CA")
    cert = (
        _builder(name, name, key.public_key(), days)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    _write(certs_dir / "ca", key, cert)
    return key, cert


def issue(
    ca_key,
    ca_cert: x509.Certificate,
    out_path: Path,
    common_name: str,
    server: bool,
    hostnames: tuple[str, ...] = (),
    ips: tuple[str, ...] = (),
    days: int = VALIDITY_DAYS,
) -> None:
    """Issue a server or client certificate signed by the CA (skipped if present)."""
    if out_path.with_suffix(".crt").exists():
        return
    key = ec.generate_private_key(ec.SECP256R1())
    usage = ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH
    builder = (
        _builder(_name(common_name), ca_cert.subject, key.public_key(), days)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()),
            critical=False,
        )
    )
    if server:
        alt_names = [x509.DNSName(h) for h in hostnames]
        alt_names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
        builder = builder.add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
    _write(out_path, key, builder.sign(ca_key, hashes.SHA256()))


def generate_all(
    certs_dir: Path,
    clients: list[str],
    hostnames: tuple[str, ...] = ("localhost",),
    ips: tuple[str, ...] = ("127.0.0.1",),
) -> None:
    ca_key, ca_cert = load_or_create_ca(certs_dir)
    issue(ca_key, ca_cert, certs_dir / "server", "cis-broker", True, hostnames, ips)
    for client in clients:
        issue(ca_key, ca_cert, certs_dir / "clients" / client, client, False)


def main() -> None:
    from core.config import REPO_ROOT, load_config

    config = load_config()
    default_clients = [GATEWAY_CLIENT] + [s.id for s in config.sensors]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--certs-dir", type=Path, default=REPO_ROOT / "certs")
    parser.add_argument("--clients", nargs="+", default=default_clients)
    args = parser.parse_args()

    generate_all(args.certs_dir, args.clients)
    print(f"TLS certificates ready in {args.certs_dir} (clients: {', '.join(args.clients)})")


if __name__ == "__main__":
    main()
