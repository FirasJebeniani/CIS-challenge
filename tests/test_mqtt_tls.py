"""Integration: a real Mosquitto broker with mutual TLS, started on a free port.

Skipped when the mosquitto executable is not installed.
"""

from __future__ import annotations

import shutil
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adapters.mqtt_common import (
    CBOR_CONTENT_TYPE,
    MqttConnectError,
    cbor_publish_properties,
    connect,
    make_client,
)
from core.config import MqttConfig, TlsConfig
from core.provenance import codec
from core.provenance.signer import Signer
from tests.conftest import raw
from tools.generate_certs import generate_all

MOSQUITTO = shutil.which("mosquitto") or next(
    (p for p in [r"C:\Program Files\mosquitto\mosquitto.exe"] if Path(p).exists()), None
)
pytestmark = pytest.mark.skipif(MOSQUITTO is None, reason="mosquitto not installed")
REPO_ACL = Path(__file__).resolve().parent.parent / "config" / "mosquitto" / "acl.conf"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def broker(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("broker")
    certs = tmp / "certs"
    generate_all(certs, ["gateway", "sensor_01", "sensor_02"])
    port = _free_port()
    conf = tmp / "mosquitto.conf"
    conf.write_text(
        "\n".join(
            [
                f"listener {port} 127.0.0.1",
                f"cafile {(certs / 'ca.crt').as_posix()}",
                f"certfile {(certs / 'server.crt').as_posix()}",
                f"keyfile {(certs / 'server.key').as_posix()}",
                "tls_version tlsv1.2",
                "require_certificate true",
                "use_identity_as_username true",
                "allow_anonymous false",
                f"acl_file {REPO_ACL.as_posix()}",
            ]
        )
        + "\n"
    )
    log = open(tmp / "mosquitto.log", "wb")
    proc = subprocess.Popen([MOSQUITTO, "-c", str(conf), "-v"], stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail(f"mosquitto did not start, see {tmp / 'mosquitto.log'}")
    yield MqttConfig(
        host="127.0.0.1",
        port=port,
        tls=TlsConfig(ca_cert=certs / "ca.crt", client_certs_dir=certs / "clients"),
    )
    proc.terminate()
    proc.wait(timeout=10)
    log.close()


class Inbox:
    def __init__(self) -> None:
        self.messages = []
        self.event = threading.Event()

    def on_message(self, client, userdata, message):
        self.messages.append(message)
        self.event.set()


def _gateway(config: MqttConfig, inbox: Inbox):
    client = make_client(config, "gateway")
    client.on_message = inbox.on_message
    subscribed = threading.Event()
    client.on_subscribe = lambda *args: subscribed.set()
    connect(client, config)
    client.subscribe(f"{config.topic_prefix}/#", qos=1)
    assert subscribed.wait(5)
    return client


def _stop(*clients):
    for c in clients:
        c.disconnect()
        c.loop_stop()


def test_signed_cbor_reading_crosses_tls_broker(broker):
    inbox = Inbox()
    gateway = _gateway(broker, inbox)
    sensor = make_client(broker, "sensor_01")
    connect(sensor, broker)
    try:
        reading = Signer("sensor_01", Ed25519PrivateKey.generate()).sign(raw())
        info = sensor.publish(
            broker.topic_for("sensor_01"), codec.encode(reading), qos=1, properties=cbor_publish_properties()
        )
        info.wait_for_publish(timeout=5)
        assert inbox.event.wait(5), "gateway received nothing"
        message = inbox.messages[0]
        assert message.topic == "cis/v1/readings/sensor_01"
        assert message.properties.ContentType == CBOR_CONTENT_TYPE
        assert codec.decode(message.payload) == reading
    finally:
        _stop(sensor, gateway)


def test_sensor_cannot_publish_on_another_sensor_topic(broker):
    inbox = Inbox()
    gateway = _gateway(broker, inbox)
    intruder = make_client(broker, "sensor_02")
    connect(intruder, broker)
    try:
        reading = Signer("sensor_02", Ed25519PrivateKey.generate()).sign(raw("sensor_02"))
        intruder.publish(broker.topic_for("sensor_01"), codec.encode(reading), qos=1).wait_for_publish(timeout=5)
        assert not inbox.event.wait(1.5), "ACL let sensor_02 write on sensor_01's topic"
    finally:
        _stop(intruder, gateway)


def test_client_without_certificate_is_rejected(broker):
    import paho.mqtt.client as mqtt

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="anon", protocol=mqtt.MQTTv5
    )
    client.tls_set(ca_certs=str(broker.tls.ca_cert), tls_version=ssl.PROTOCOL_TLS_CLIENT)
    with pytest.raises((MqttConnectError, ssl.SSLError, OSError)):
        connect(client, broker, timeout=3)
    client.loop_stop()
