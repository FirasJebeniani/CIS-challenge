# Standard Scenario & Evaluation Suite (Track 2 — False-Data Injection)

A reproducible evaluation harness for an in-situ sensor false-data-injection detector.
It injects **labelled synthetic faults** into real, public weather-station data and scores a
detector's output: detection quality, how much false data still reaches the analyst, false
alarms, latency, and efficiency/overhead.

## Dataset

WegenerNet climate station network Level 2 data version 8.0 (2007–2024), Feldbach Region,
5-min resolution, UTC. Used here: air temperature, relative humidity, precipitation, 2023–2024.
Fuchsberger J., G. Kirchengast, C. Bichler (2025). doi:10.25364/WEGC/WPS8.0-2025.1. Licensed CC BY 4.0.

## Setup

```bash
uv sync
# register (free) at https://wegenernet.org/portal, then Data download -> Cloud access,
# copy the "WegenerNet Cloud Archive" link:
export WEGENERNET_SHARE_URL="https://cloud.uni-graz.at/s/XXXXXXXX"
uv run python -m data_prep.download      # ~430 MB -> data/raw/wegenernet/
uv run python -m data_prep.build         # -> data/clean/
```

`data/clean/` holds, per variable, a `time × station` table of values, a matching table of the
provider's gap-fill flags, plus `stations.csv`, `neighbors.csv`, `sigma_ref.csv`, and diurnal
climatologies. `sigma_ref` is each station's normal disagreement with its 5 nearest neighbours —
fault sizes are expressed in multiples of it.

## Build suites and score a detector

```bash
uv run python -m attacks.build_suites            # -> data/suites/<name>/
uv run python -m eval.run --suite dev --alarms alarms/<run>/dev
```

A detector exposes `detect(values) -> alarms` (boolean `time × station` tables, same shape as the
suite). See `docs/evaluation_protocol.md` for the full method and `docs/attack_catalogue.md` for the
fault families.

## Docs

- `docs/superpowers/specs/2026-10-27-standard-scenario-design.md` — design
- `docs/superpowers/plans/2026-10-27-standard-scenario-suite.md` — implementation plan
