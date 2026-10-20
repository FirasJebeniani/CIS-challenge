"""MQTT v5 client factory shared by the L1a publisher and the L1b subscriber."""

from __future__ import annotations

import ssl
import threading

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from core.config import MqttConfig

CBOR_CONTENT_TYPE = "application/cbor"


class MqttConnectError(ConnectionError):
    pass


def make_client(config: MqttConfig, client_id: str) -> mqtt.Client:
    """MQTT v5 client; with TLS configured it presents the client certificate
    certs/clients/<client_id>.crt (mutual TLS, CN = MQTT username)."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv5,
    )
    if config.tls is not None:
        certfile, keyfile = config.tls.client_cert(client_id)
        client.tls_set(
            ca_certs=str(config.tls.ca_cert),
            certfile=str(certfile),
            keyfile=str(keyfile),
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
    return client


def connect(client: mqtt.Client, config: MqttConfig, timeout: float = 10.0) -> None:
    """Connect, start the network loop and wait for CONNACK."""
    done = threading.Event()
    result: dict[str, object] = {}

    def on_connect(client, userdata, flags, reason_code, properties):
        result["reason"] = reason_code
        done.set()

    previous = client.on_connect
    client.on_connect = on_connect
    client.connect(config.host, config.port, keepalive=config.keepalive)
    client.loop_start()
    if not done.wait(timeout):
        client.loop_stop()
        raise MqttConnectError(f"no CONNACK from {config.host}:{config.port} after {timeout}s")
    client.on_connect = previous
    reason = result["reason"]
    if reason.is_failure:
        client.loop_stop()
        raise MqttConnectError(f"broker refused connection: {reason}")


def cbor_publish_properties() -> Properties:
    props = Properties(PacketTypes.PUBLISH)
    props.ContentType = CBOR_CONTENT_TYPE
    return props
