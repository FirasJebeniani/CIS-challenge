"""Loads config/system.yaml. Relative paths are resolved from the repo root."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "system.yaml"


def _from_repo_root(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


RepoPath = Annotated[Path, AfterValidator(_from_repo_root)]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TlsConfig(_Section):
    ca_cert: RepoPath
    client_certs_dir: RepoPath  # <client_id>.crt / <client_id>.key (mutual TLS)

    def client_cert(self, client_id: str) -> tuple[Path, Path]:
        return (
            self.client_certs_dir / f"{client_id}.crt",
            self.client_certs_dir / f"{client_id}.key",
        )


class MqttConfig(_Section):
    host: str = "localhost"
    port: int = 8883
    topic_prefix: str = "cis/v1/readings"
    qos: int = Field(default=1, ge=0, le=2)
    keepalive: int = 60
    tls: TlsConfig | None = None  # None = plain TCP, local debugging only

    def topic_for(self, sensor_id: str) -> str:
        return f"{self.topic_prefix}/{sensor_id}"


class SensorConfig(_Section):
    id: str
    kind: str = "temperature"
    low: float = 20.0
    high: float = 30.0


class SystemConfig(_Section):
    mqtt: MqttConfig = MqttConfig()
    sensors: list[SensorConfig]
    interval_s: float = 2.0
    keys_dir: RepoPath = Path("keys")
    state_dir: RepoPath = Path("state")  # signer counters / chain heads


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> SystemConfig:
    with open(path, encoding="utf-8") as fh:
        return SystemConfig.model_validate(yaml.safe_load(fh))
