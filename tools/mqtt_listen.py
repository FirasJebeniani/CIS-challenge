"""Debug subscriber: prints the decoded readings received through the broker.

    python -m tools.mqtt_listen

Connects with the "gateway" client certificate and only decodes CBOR; it
does NOT verify signatures (that is the L1b verifier's job).
"""

from __future__ import annotations

import sys
import time

from adapters.mqtt_common import MqttConnectError, connect, make_client
from core.config import load_config
from core.provenance import codec
from tools.generate_certs import GATEWAY_CLIENT


def main() -> None:
    config = load_config()
    client = make_client(config.mqtt, GATEWAY_CLIENT)

    def on_message(client, userdata, message):
        try:
            reading = codec.decode(message.payload)
        except codec.DecodeError as exc:
            print(f"[{message.topic}] undecodable message: {exc}")
            return
        print(f"[{message.topic}] {reading.model_dump_json()}")

    client.on_message = on_message
    try:
        connect(client, config.mqtt)
    except (MqttConnectError, OSError) as exc:
        sys.exit(f"MQTT connection failed: {exc}")
    client.subscribe(f"{config.mqtt.topic_prefix}/#", qos=config.mqtt.qos)
    print(f"Listening on {config.mqtt.topic_prefix}/# (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
