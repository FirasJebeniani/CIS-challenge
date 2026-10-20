"""L1a field node: sensor -> signer (Ed25519 + hash chain) -> CBOR -> MQTT v5/TLS.

Each sensor has its own key pair, counter, hash chain and MQTT client
identity, and publishes on cis/v1/readings/<sensor_id>.

    python -m field.node                          # every sensor in config/system.yaml
    python -m field.node --sensors sensor_01 --count 5
    python -m field.node --dry-run                # no broker: print signed readings as JSON
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from core.config import SystemConfig, load_config
from core.contracts import SignedReading
from core.provenance import codec
from core.provenance.keys import private_key_path
from core.provenance.signer import Signer
from field.sensor import Sensor, SimulatedTemperatureSensor


@dataclass
class SensorNode:
    """One field sensor with its signer and MQTT topic."""

    sensor: Sensor
    signer: Signer
    topic: str

    @property
    def sensor_id(self) -> str:
        return self.sensor.sensor_id

    def produce(self) -> tuple[SignedReading, bytes]:
        signed = self.signer.sign(self.sensor.read())
        return signed, codec.encode(signed)


def build_nodes(config: SystemConfig, sensor_ids: list[str] | None, persist_state: bool = True) -> list[SensorNode]:
    selected = [s for s in config.sensors if sensor_ids is None or s.id in sensor_ids]
    unknown = set(sensor_ids or ()) - {s.id for s in selected}
    if unknown:
        raise SystemExit(f"sensors not in config: {', '.join(sorted(unknown))}")
    nodes = []
    for s in selected:
        if s.kind != "temperature":
            raise SystemExit(f"{s.id}: sensor kind '{s.kind}' is not simulated yet")
        key_path = private_key_path(config.keys_dir, s.id)
        if not key_path.exists():
            raise SystemExit(f"{s.id}: no private key at {key_path}; run: python -m tools.generate_keys")
        state_path = config.state_dir / f"{s.id}.json" if persist_state else None
        nodes.append(
            SensorNode(
                sensor=SimulatedTemperatureSensor(s.id, s.low, s.high),
                signer=Signer.from_key_file(s.id, key_path, state_path=state_path),
                topic=config.mqtt.topic_for(s.id),
            )
        )
    return nodes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sensors", nargs="+", help="subset of sensor ids (default: all)")
    parser.add_argument("--count", type=int, default=0, help="rounds to run (0 = forever)")
    parser.add_argument("--interval", type=float, help="seconds between rounds (default: config)")
    parser.add_argument("--dry-run", action="store_true", help="sign and print, do not publish")
    args = parser.parse_args()

    config = load_config()
    interval = args.interval if args.interval is not None else config.interval_s
    nodes = build_nodes(config, args.sensors, persist_state=not args.dry_run)

    clients = {}
    if not args.dry_run:
        from adapters.mqtt_common import MqttConnectError, cbor_publish_properties, connect, make_client

        try:
            for node in nodes:
                clients[node.sensor_id] = make_client(config.mqtt, node.sensor_id)
                connect(clients[node.sensor_id], config.mqtt)
        except (MqttConnectError, OSError) as exc:
            sys.exit(f"MQTT connection failed: {exc}")
        tls = "TLS" if config.mqtt.tls else "PLAIN TCP"
        print(f"MQTT {tls} CONNECTED to {config.mqtt.host}:{config.mqtt.port}")
        properties = cbor_publish_properties()

    print(f"MULTI-SENSOR RUNNING: {', '.join(n.sensor_id for n in nodes)} every {interval}s")
    rounds = 0
    try:
        while args.count == 0 or rounds < args.count:
            for node in nodes:
                signed, payload = node.produce()
                if args.dry_run:
                    print(signed.model_dump_json())
                    continue
                info = clients[node.sensor_id].publish(
                    node.topic, payload, qos=config.mqtt.qos, properties=properties
                )
                info.wait_for_publish(timeout=5)
                print(
                    f"CBOR MESSAGE PUBLISHED  {node.sensor_id} seq={signed.seq} "
                    f"value={signed.value} {signed.unit} ({len(payload)} B) -> {node.topic}"
                )
            rounds += 1
            if args.count == 0 or rounds < args.count:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        for client in clients.values():
            client.disconnect()
            client.loop_stop()


if __name__ == "__main__":
    main()
