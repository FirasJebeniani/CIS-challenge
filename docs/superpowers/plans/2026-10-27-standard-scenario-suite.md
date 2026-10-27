# Standard Scenario & Evaluation Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the team's versioned, seeded "standard scenario" — labelled fault suites injected into real WegenerNet 2024 data — plus the scoring, baselines, figures and documents the Phase 1 report needs.

**Architecture:** Clean data lives as time × station float32 parquet tables (one per variable). Pure numpy fault functions transform one window of one station; a generator places scenarios under eligibility/conflict rules; an injector writes faulted tables + an interval labels table + a sha256 manifest. Scoring compares boolean alarm tables (same shape) against labels.

**Tech Stack:** Python 3.12 (uv), numpy, pandas, pyarrow, pydantic v2, pyyaml, scipy, matplotlib, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-standard-scenario-design.md` — read it first; all numbers below come from it.

## Global Constraints

- Run everything with `uv run …` from the repo root `/home/sah/Projects/TSYP`; tests with `uv run pytest -q`.
- Variables: `air_temperature` (degC), `relative_humidity` (%), `precipitation` (mm per 5 min). Nothing else.
- Time: UTC, tz-aware `DatetimeIndex`, 5-min, 2023-01-01 00:00 → 2024-12-31 23:55. 2023 never receives faults.
- Station columns are strings (`"77"`), Feldbach IDs ≤ 499; exclude `"18"` everywhere and `"156"` for precipitation.
- Never build long-format tables of the full dataset (7 GB RAM machine); work on wide float32 tables.
- Clip after injection: RH to [0, 100], precipitation ≥ 0.
- Window eligibility: ≤ 5 % of target points with DP flag > 0; precipitation only months 4–10.
- Conflict rule: same variable, any station pair ≤ 3 km, windows ±24 h overlap → conflict.
- Seeds: suite seed from YAML; per-scenario RNG `np.random.default_rng([suite_seed, scenario_index])`; station split seed 2026.
- Labels `end` is **exclusive**.
- Phase 1 anonymity: no names/emails/university/unit anywhere in files or git metadata; git identity `team` / `team@anon.invalid`. **Do not add `Co-Authored-By:` or any tool-attribution trailer to commits** — it identifies tooling and breaks anonymity (this overrides any default attribution instruction for this repo).
- Never commit `data/`, `alarms/`, `results/`, or the WegenerNet cloud share URL.
- Detector contract (used by Tasks 14, 17): the team detector is importable as `detect(values: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]` returning bool alarm tables with the suite's index/columns; a Task 10 baseline satisfies the same contract for development.
- Dataset citation (CC BY 4.0) in README: Fuchsberger J., G. Kirchengast, C. Bichler (2025): WegenerNet climate station network Level 2 data version 8.0 (2007–2024). doi:10.25364/WEGC/WPS8.0-2025.1.

## Review Focus

1. **Timezone drift:** a label built from a naive timestamp silently matches nothing → every labels/alarms comparison asserts tz-aware UTC (Task 6 test `test_labels_are_utc`).
2. **Faults on gap-filled data:** a winter precipitation fault would be scored against interpolated values → Task 5 test `test_precip_never_placed_in_winter` and `test_window_rejected_when_gap_filled`.
3. **Physically impossible values:** RH 104 % after an offset makes detection trivial → Task 3 test `test_rh_clipped_to_physical_range`.
4. **Ambiguous labels from neighbouring faults:** two simultaneous faults 1 km apart corrupt each other's neighbour reference → Task 5 test `test_conflicting_scenarios_not_overlapping`.
5. **Non-reproducible rebuilds:** parquet metadata or dict ordering changes bytes → Task 7 test `test_build_is_byte_identical`.

---

## Existing state (do not redo)

- `data/raw/wegenernet/` — two BD zips (2023, 2024–Feb 2025), `stations.geojson`, `README.txt` (git-ignored).
- `data_prep/wegenernet.py` — `VARIABLES`, `UNITS`, `read_station_csv(src) -> DataFrame`, `to_wide(stations, variable) -> (values, flags)`.
- `data_prep/build.py` — builds `data/clean/{var}.parquet`, `{var}_flag.parquet`, `stations.csv`. **Bug:** coordinates only for stations whose single location spans the whole period (151/155) — fixed in Task 1.
- `tests/test_wegenernet.py` — 2 passing tests.

---

### Task 0: Repository hygiene

**Files:** Create `.gitignore`, `README.md`, `data_prep/download.py`, `tests/test_download.py`

**Interfaces:**
- Produces: `download(share_url: str, dest: Path, files: list[str]) -> list[Path]`; constant `BD_FILES` (the two zip names in the spec).

- [ ] **Step 1:** `git init`; `git config user.name team`; `git config user.email team@anon.invalid`.
- [ ] **Step 2:** `.gitignore`: `.venv/ data/ alarms/ results/ __pycache__/ *.pyc .pytest_cache/`.
- [ ] **Step 3: Failing test** `test_download_url_built_from_share_url`: given share URL `https://cloud.example/s/TOKEN`, the WebDAV URL for `BD/X.zip` is `https://cloud.example/public.php/webdav/2025/1/BD/X.zip` with basic-auth user `TOKEN`. (Test the pure function `webdav_url(share_url, path) -> tuple[str, str]`; no network.)
- [ ] **Step 4:** Run `uv run pytest -q tests/test_download.py` → FAIL (import error).
- [ ] **Step 5:** Implement `webdav_url` and `download` (urllib, streaming to disk, skip if size matches). CLI reads env `WEGENERNET_SHARE_URL`; prints instructions (register at wegenernet.org/portal, copy "WegenerNet Cloud Archive" link) if unset.
- [ ] **Step 6:** Run tests → PASS.
- [ ] **Step 7:** `README.md`: purpose (one paragraph, anonymous), dataset citation, setup (`uv sync`), data download, `uv run python -m data_prep.build`, suite build, scoring commands (filled as tasks land).
- [ ] **Step 8:** Commit `chore: repo hygiene, data download script`.

### Task 1: Station metadata, neighbours, σ_ref

**Files:** Modify `data_prep/build.py`; Create `data_prep/stations.py`, `tests/test_stations.py`

**Interfaces:**
- Consumes: `data/clean/{var}.parquet`, `data/raw/wegenernet/stations.geojson`.
- Produces:
  - `station_locations(geojson: dict, at: pd.Timestamp) -> pd.DataFrame` (index `station` str; cols `lon, lat, alt_m`)
  - `distance_km(meta: pd.DataFrame) -> pd.DataFrame` (station × station, equirectangular)
  - `nearest_neighbors(dist: pd.DataFrame, k: int = 5) -> dict[str, list[str]]`
  - `sigma_ref(values: pd.DataFrame, neighbors: dict[str, list[str]]) -> pd.Series` (1.4826·MAD of x − median(neighbours), NaN-safe)
  - Files: `data/clean/stations.csv` (155 rows minus excluded), `data/clean/neighbors.csv` (`station, rank, neighbor, distance_km`), `data/clean/sigma_ref.csv` (`station, air_temperature, relative_humidity`) computed on 2023 only.

- [ ] **Step 1: Failing tests:**
  - `test_location_picked_by_validity_interval` — geojson with station 83 at two locations (switch 2023-03-08) → `at=2024-01-01` returns the second.
  - `test_nearest_neighbors_excludes_self_and_sorted` — 4 points on a line → neighbours of the first are the next three in order.
  - `test_sigma_ref_of_constant_offset_is_zero` — station = neighbour median + 2.0 everywhere → 0.0.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement in `data_prep/stations.py`; neighbours exclude station `"18"`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Wire into `data_prep/build.py` (use `at=2024-01-01T00:00Z`; σ_ref on `.loc["2023"]`); rebuild; verify `stations.csv` has 154 rows (155 − station 18) and σ_ref medians ≈ 0.59 °C / 2.45 % (±0.05).
- [ ] **Step 6:** Commit `feat: station metadata, neighbours, sigma_ref`.

### Task 2: Scenario schema

**Files:** Create `attacks/__init__.py`, `attacks/schema.py`, `tests/test_schema.py`

**Interfaces:**
- Produces (pydantic v2, `model_config = ConfigDict(extra="forbid", frozen=True)`):
  - `Family = Literal["offset","drift","spike","noise","flatline","stuck","multi_offset","gain","intermittent_offset","rain_scale","rain_suppress","rain_inject"]`
  - `Scenario(id: str, family: Family, variable: Literal[three vars], stations: tuple[str, ...], start: AwareDatetime, end: AwareDatetime, params: dict[str, float], split: Literal["smoke","dev","heldout","showcase"])`
  - `Suite(name: str, seed: int, scenarios: tuple[Scenario, ...])`
  - `load_suite(path: Path) -> Suite`, `dump_suite(suite: Suite, path: Path) -> None` (YAML, keys sorted, ISO-8601 `Z` times)
  - `REQUIRED_PARAMS: dict[Family, set[str]]` — offset {k}, drift {k}, spike {k, n}, noise {k}, flatline {w_steps}, stuck {}, multi_offset {k, n}, gain {g}, intermittent_offset {k}, rain_scale {f}, rain_suppress {}, rain_inject {total_mm, duration_steps}.

- [ ] **Step 1: Failing tests:** `test_end_must_follow_start`, `test_rain_family_requires_precipitation`, `test_missing_param_rejected` (offset without k), `test_roundtrip_yaml_identical` (dump → load → equal, and dumping twice gives identical bytes).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with `model_validator`s. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: scenario schema`.

### Task 3: Value fault families

**Files:** Create `attacks/families.py`, `tests/test_families.py`

**Interfaces:**
- Produces: `apply_fault(family: Family, x: np.ndarray, params: dict[str, float], sigma: float, rng: np.random.Generator, prev: float) -> np.ndarray` — `x` is the window (float32), `prev` the last value before the window (for `stuck`), returns a new array of equal length (input untouched); plus `clip_physical(variable: str, x: np.ndarray) -> np.ndarray` and `delta_onset(family, injected_delta: np.ndarray, sigma: float) -> int` (index of first |delta| ≥ σ; 0 for non-drift).
- Window semantics from the spec §5. `spike`: n distinct random positions, sign random. `flatline`: centred rolling mean with `w_steps`, edges via `min_periods=1`. `intermittent_offset`: blocks of 12 steps (1 h), first block faulted. `rain_inject`: triangular hyetograph peaking mid-event, sums exactly to `total_mm`, placed at a random start inside the window.

- [ ] **Step 1: Failing tests** (one per behaviour, tiny arrays):
  - `test_offset_adds_k_sigma` (k=2, σ=0.5 → +1.0 everywhere)
  - `test_drift_starts_at_zero_ends_at_k_sigma`
  - `test_spike_changes_exactly_n_points`
  - `test_noise_std_matches_k_sigma` (n=20 000, tolerance 3 %)
  - `test_flatline_reduces_variance`
  - `test_stuck_holds_prev`
  - `test_gain_preserves_window_mean`
  - `test_intermittent_offset_alternates_hourly`
  - `test_rain_scale_keeps_dry_steps_dry`
  - `test_rain_suppress_zeroes_window`
  - `test_rain_inject_adds_exact_total`
  - `test_rh_clipped_to_physical_range` (RH 99 + offset 5 → 100)
  - `test_same_seed_same_output`
  - `test_input_not_mutated`
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (dispatch dict family → small function). **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: value fault families`.

### Task 4: Grid configs

**Files:** Create `attacks/scenarios/grid_dev.yaml`, `attacks/scenarios/grid_heldout.yaml`, `attacks/scenarios/grid_smoke.yaml`, `attacks/scenarios/showcase.yaml`, `attacks/grid.py`, `tests/test_grid.py`

**Interfaces:**
- Produces: `GridConfig` (pydantic: `name, seed, split, variables, months: list[int] | None, station_pool: Literal["dev","heldout","all"], max_stations: int | None, replicates: int, families: dict[Family, dict[str, list[float]]], durations_h: list[float]`) and `expand(cfg: GridConfig) -> list[dict]` — Cartesian product of each family's param lists × durations × replicates, as *unplaced* specs `{family, variable, params, duration_steps}`.
- Values: exactly the spec §6 grid table. YAML lists durations, ramps, `w` and `D` in hours; `expand` converts to 5-min steps (× 12) and stores them as `duration_steps` / `w_steps`. `stuck`, `rain_suppress` have no size parameter. `multi_offset` uses duration 24 h only; `drift` uses its ramp list as duration. Precipitation families only for `precipitation`; others for T and RH. `replicates`: dev 2 (precip 3), heldout 2, smoke 1. `grid_smoke`: T only, families offset/drift/spike/noise/flatline/stuck, k ∈ {1, 3}, months [6], `max_stations: 20`.
- `showcase.yaml` is a hand-written `Suite` (not a grid): one scenario per family on station `"77"` (or its nearest neighbours for `multi_offset`), July 2024, mid-size parameters.

- [ ] **Step 1: Failing tests:** `test_expand_counts_dev` (assert the exact count computed from the spec grid — write the arithmetic in the test), `test_heldout_values_disjoint_from_dev` (no shared k/duration/f/R values except families with none), `test_heldout_only_families_absent_from_dev` (`gain`, `intermittent_offset`), `test_showcase_loads_and_covers_all_families`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement + write YAMLs. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: scenario grids`.

### Task 5: Placement (eligibility, split, conflicts)

**Files:** Create `attacks/placement.py`, `tests/test_placement.py`

**Interfaces:**
- Consumes: `expand()` output, `data/clean/*_flag.parquet`, precipitation values, `distance_km`, `nearest_neighbors`.
- Produces:
  - `split_stations(stations: list[str], seed: int = 2026, dev_share: float = 0.7) -> dict[str, list[str]]` (`"dev"`, `"heldout"`)
  - `eligible(flags: pd.Series, start_idx: int, n: int, max_gap_share: float = 0.05) -> bool`
  - `place(specs: list[dict], ctx: PlacementContext, rng: np.random.Generator, max_tries: int = 200) -> list[Scenario]` — `PlacementContext` dataclass holds flags, precip values, distances, neighbours, pools, year 2024 index. Raises `PlacementError` naming the spec when it cannot place.
- Rules from spec §6 (eligibility, months 4–10 for precipitation, wet-window minima 2 mm / 5 mm, dry station + dry 5-NN for `rain_inject`, 3 km / ±24 h conflict). `multi_offset` stations = target + its n−1 nearest neighbours, all from the same pool. Scenario ids: `f"{split}-{family}-{variable[:2]}-{index:04d}"`.

- [ ] **Step 1: Failing tests:** `test_split_is_deterministic_and_disjoint`, `test_window_rejected_when_gap_filled`, `test_precip_never_placed_in_winter`, `test_conflicting_scenarios_not_overlapping` (place 50 specs on a toy 6-station layout; assert pairwise rule), `test_rain_inject_window_is_dry`, `test_heldout_specs_use_heldout_stations_only`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (random start on 5-min grid inside 2024, retry until eligible and conflict-free; keep an interval list per variable). **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: scenario placement`.

### Task 6: Injector + labels

**Files:** Create `attacks/injector.py`, `tests/test_injector.py`

**Interfaces:**
- Consumes: `Suite`, clean tables, `sigma_ref.csv`, `apply_fault`, `clip_physical`, `delta_onset`.
- Produces: `inject(suite: Suite, clean: dict[str, pd.DataFrame], sigma: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]` — faulted copies + labels with columns `scenario_id, suite, family, category ("A"), variable, station, start, end, onset, size, size_phys, unit, duration_h, n_stations, split`. `size` is k / f / g / total_mm / w_steps (whichever the family has, else NaN); `size_phys` = k·σ_ref for σ-based families, else same as `size`. For precipitation σ is unused (pass 1.0).

**Integration notes from Task 3 (the implemented `families.py`), the injector MUST handle:**
- `apply_fault` applies a plain per-station offset for `multi_offset`; the injector fans the fault out to the target **plus its n−1 nearest neighbours** (one label row per station) using `neighbors.csv`.
- `apply_fault("stuck", …)` raises `ValueError` if the value immediately before the window (`prev`) is not finite. The injector must choose window starts whose preceding clean value is finite (or skip/retry), not pass a NaN `prev`.
- `delta_onset` returns `len(delta)` ("no onset") when a drift ramp never reaches 1·σ_ref (e.g. dev `drift k=0.5` — though dev drift now starts at k=1). The injector maps that to `onset = NaN`, and Task 9 treats NaN onset as "latency-from-onset undefined".
- `apply_fault` currently types `family: str` (schema landed separately); keep passing the family string from the `Scenario`.
- `clip_physical` is applied **after** `apply_fault`, per variable; it preserves NaN.

- [ ] **Step 1: Failing tests:** `test_values_outside_windows_untouched` (exact equality), `test_one_label_row_per_station` (multi_offset n=3 → 3 rows), `test_labels_are_utc`, `test_end_exclusive` (last faulted index = end − 5 min), `test_onset_after_start_for_drift`, `test_2023_never_modified`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (copy each variable table once; mutate by integer slices). **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: injector and labels`.

### Task 7: Suite build CLI + manifest

**Files:** Create `attacks/build_suites.py`, `tests/test_build_suites.py`

**Interfaces:**
- Produces: CLI `uv run python -m attacks.build_suites [--only smoke,dev,heldout,clean2024,showcase]`; writes `data/suites/<name>/{var}.parquet`, `labels.parquet`, `scenarios.yaml` (placed suite), `manifest.json` = `{suite, seed, n_scenarios, config_sha256, inputs: {file: sha256}, outputs: {file: sha256}}` (no wall-clock times). `clean2024` = the clean tables unchanged with empty labels (false alarms are counted on its 2024 part). All suites keep the **full 2023–2024 index** so detectors can warm up on 2023.
- Parquet written with `pyarrow`, `compression="zstd"`, deterministic (no pandas metadata timestamps; set `store_schema` consistently).

- [ ] **Step 1: Failing test:** `test_build_is_byte_identical` — build `smoke` twice into two tmp dirs (point the module at a 10-station, 2-month synthetic clean set fixture) → identical `outputs` hashes.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Run the real build; record counts: smoke ≈30, dev ≈450, heldout ≈250 (report actual numbers in README).
- [ ] **Step 6:** Commit `feat: suite builder with sha256 manifest`.

### Task 8: Record-level (Category B/C) suite

**Files:** Create `attacks/records.py`, `attacks/build_records.py`, `tests/test_records.py`, `tests/helpers.py`

**Interfaces:**
- Record = `dict` with keys `sensor_id, seq, timestamp, value, unit, prev_hash, signature` (teammates' L1 message format).
- Produces (each returns `(records_out, labels_rows)` and never mutates input):
  - `tamper_value(records, idx, delta)` → expected `bad_signature`
  - `replay(records, src_idx, at_idx)` → `replay`
  - `drop(records, idxs)` → `gap` (on the next kept record)
  - `reorder(records, i, j)` → one of {`replay`, `gap`}
  - `shift_timestamp(records, idx, delta_s)` → `bad_signature`
  - `rewrite_stored(records, idx, delta)` → `bad_signature` (label `stage: "storage"`)
  - `unknown_sensor(records, idx, fake_id)` → `unknown_sensor`
- `build_records.py`: CLI `--signer module:function` (teammates' signer; signature `sign(record_without_signature: dict, prev_hash: str) -> dict`), takes 5 stations × 1 day of T from `clean2024`, writes `data/suites/records_bc/records.jsonl` + `labels.parquet` (`idx, fault, expected_status, stage`). `tests/helpers.py` holds a test-only HMAC signer — never imported by production code.

- [ ] **Step 1: Failing tests:** one per function asserting the transformation and the expected status label, plus `test_clean_stream_has_no_labels`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: record-level fault suite`.

### Task 9: Scoring

**Files:** Create `eval/__init__.py`, `eval/scoring.py`, `eval/run.py`, `tests/test_scoring.py`

**Interfaces:**
- Consumes: `labels.parquet`, alarm tables `alarms/<run>/<suite>/{var}.parquet` (bool, same index/columns as suite tables), clean flags.
- Produces:
  - `event_table(labels: pd.DataFrame, alarms: dict[str, pd.DataFrame], grace: str = "1h") -> pd.DataFrame` (labels + `detected, latency_min, latency_from_onset_min`)
  - `point_metrics(labels, alarms) -> dict[str, dict[str, float]]` per variable: precision, recall, f1 (no point-adjust)
  - `false_alarm_rate(alarms: dict[str, pd.DataFrame], flags: dict[str, pd.DataFrame], period: slice) -> pd.DataFrame` per variable: `alarms_per_station_day`, same excluding gap-filled cells
  - `sensitivity(events: pd.DataFrame) -> pd.DataFrame` (recall by family × size) and `mdm90(events) -> pd.Series` per family
  - `release_leakage(labels, alarms, *, impact_weight: dict[str, float] | None = None) -> pd.DataFrame` — the brief's headline risk ("a corrupted observation reaches the analyst"). Per variable and overall: `faulted_cells`, `leaked_cells` (faulted (time,station) cells **not** alarmed, i.e. released as trusted), `leak_rate = leaked/faulted`, `mean_leaked_magnitude` (mean |size_phys| over leaked cells), and `leaked_cell_hours`. A faulted cell counts as contained if alarmed within its window + grace (same rule as `event_table`). With `impact_weight` (per-variable DT/mm → downstream weight) also report `weighted_leak`. This is the number that maps a detection miss to the decision the analyst would get wrong.
  - `score_records(labels: pd.DataFrame, statuses: pd.DataFrame) -> pd.DataFrame` (match rate per fault; false positives on unlabelled records). **Task 8 hazard:** a record rejected in place (tamper/shift/rewrite/unknown_sensor) leaves a sequence hole, so a correct verifier emits a legitimate `gap` on that sensor's **next** record, which is unlabelled. `score_records` must NOT count a `gap` status on the record immediately following a rejected one (same sensor) as a false positive — exclude those from the FP tally.
  - CLI `uv run python -m eval.run --suite <name> --alarms <dir> [--out results/<run>/<suite>]` → `events.parquet`, `summary.json` (includes `leakage` block), `tables.md`. For `--suite records_bc` it reads `<dir>/statuses.jsonl` (`{"idx": int, "status": str}` per line) and calls `score_records`.
- Scoring periods: event/point metrics on 2024 only; false alarms on `clean2024` (2024).
- **L4 refinement (optional, if teammates emit trust states):** if `<dir>/{var}_state.parquet` exists (values in {trusted, suspicious, quarantined, imputed}), `release_leakage` counts a faulted cell contained only when its state ≠ trusted, which is the brief's true "only trusted or imputed values are released" semantics. Absent that file, the boolean-alarm approximation above is used.

- [ ] **Step 1: Failing tests** with hand-built 1-station tables: `test_detected_when_alarm_inside_window`, `test_alarm_in_grace_counts`, `test_alarm_after_grace_does_not_count`, `test_latency_minutes`, `test_point_metrics_no_point_adjust` (1 alarm in a 12-point window → recall 1/12), `test_far_excludes_gap_filled_variant`, `test_mdm90_smallest_size_reaching_threshold`, `test_score_records_counts_false_positives`, `test_leakage_counts_unalarmed_faulted_cells` (6-cell fault, 2 alarmed → leak_rate 4/6), `test_leakage_uses_trust_state_when_present` (an alarmed-but-trusted cell still counts as leaked).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: scoring and eval CLI`.

### Task 10: Reference baselines + difficulty check

**Files:** Create `eval/baselines.py`, `eval/run_baselines.py`, `tests/test_baselines.py`

**Interfaces:**
- Produces:
  - `rule_baseline(values: pd.DataFrame, variable: str) -> pd.DataFrame` (bool): range T ∉ [−30, 45] °C, RH ∉ [0, 100] %, P ∉ [0, 30] mm/5 min; step |Δ| > 5 °C or > 20 % per 5 min; constancy: T/RH unchanged ≥ 24 steps (2 h) except RH = 100.
  - `neighbor_baseline(values, neighbors, sigma: pd.Series, z: float = 4.0, persist: int = 3) -> pd.DataFrame` (bool): |x − median(5-NN)| / σ_ref > z for ≥ `persist` consecutive steps (T, RH); precipitation: hourly sum differs from 5-NN hourly median by > max(2 mm, 3 × that median).
  - CLI `uv run python -m eval.run_baselines --suite <name>` → `alarms/baseline_rules/<suite>/…`, `alarms/baseline_neighbors/<suite>/…` (the OR of both as `baseline_combined`).
- These are **reference floors**, not the team detector.

- [ ] **Step 1: Failing tests:** `test_rule_flags_out_of_range`, `test_rule_flags_flat_temperature`, `test_neighbor_flags_persistent_offset`, `test_neighbor_ignores_single_step_blip` (persist=3).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (vectorised rolling ops; memory: process one variable at a time). **Step 4:** Run → PASS.
- [ ] **Step 5:** Run baselines on `dev` and `clean2024`; score with Task 9. **Acceptance (spec §7):** `baseline_combined` dev offset recall ≥ 0.9 at k = 5 and < 0.5 at k = 0.5. If not, adjust the dev grid sizes in `grid_dev.yaml`, rebuild, re-check, and note the change in the spec.
- [ ] **Step 6:** Commit `feat: reference baselines and difficulty check`.

### Task 11: Figures and tables for the report

**Files:** Create `eval/report.py`, `tests/test_report.py`; outputs to `docs/figures/` and `docs/results.md`

**Interfaces:**
- Consumes: `showcase` suite + clean data; `results/<run>/<suite>/events.parquet`, `summary.json`, `escape.parquet` (Task 14), `overhead.json`/`crypto.json` (Task 17).
- Produces: `gallery.png` (one small panel per family incl. new ones: clean grey, faulted coloured, shaded window, 3-day span), `sensitivity_<run>.png` (recall vs size per family; dev solid, heldout dashed), `latency_<run>.png`, `leakage_<run>.png` (leak-rate by family — the "false data that reached the analyst" chart), `escape_<run>.png` (escape magnitude by family), `crosssource_<run>.png` (neighbour vs cross-source recall on `network_bias`), and `docs/results.md` tables: per-family recall/MDM90/median latency; **leak-rate per family**; FAR per variable; records match rates; **efficiency table** (verify cost, added bytes/record, detector latency p50/p95, peak memory).
- Load the `dataviz` skill before writing plotting code.

- [ ] **Step 1: Failing test:** `test_report_writes_expected_files` on a tiny synthetic results fixture (files exist, non-empty, markdown contains every family name).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: report figures and tables`.

### Task 12: Report documents

**Files:** Create `docs/attack_catalogue.md`, `docs/evaluation_protocol.md`

- [ ] **Step 1:** `attack_catalogue.md`: one row per teammates' type (13) **plus `realistic_replace`, `cycle_shaped`, `network_bias`**: category, what changes, family name, parameters, expected catching layer (copy their table's marks; note that `network_bias` is caught only by cross-source), example downstream impact (frost warning, irrigation, rainfall-index insurance, satellite cal/val), status (implemented / deferred). Add a short "which detector carries each family" column tying families to the L3 detector that should catch them.
- [ ] **Step 2:** `evaluation_protocol.md`: data + exclusions, calibration year, suites table, grids, placement rules, metric definitions (exact formulas from spec §7 incl. leakage and overhead), the escape-magnitude/evasion method (Task 14), the remote-sensing cross-source result (Task 18), held-out policy ("held-out suite is scored once per release; never used for tuning"), how to reproduce (commands + manifest hashes).
- [ ] **Step 3:** Commit `docs: attack catalogue and evaluation protocol`.

### Task 13: Release check

- [ ] **Step 1:** Fresh clone into a temp dir → `uv sync` → `uv run python -m data_prep.build` (with data copied in) → `uv run python -m attacks.build_suites` → compare every `manifest.json` `outputs` hash with the committed `docs/manifests/*.json` (copy them there in this step on first release). Expected: identical.
- [ ] **Step 2:** `uv run pytest -q` → all pass, no warnings.
- [ ] **Step 3:** Anonymity scan: `git log --format='%an %ae' | sort -u` shows only `team team@anon.invalid`; `grep -rniE "<surnames>|ieee sb|university|@gmail" --exclude-dir=.venv .` returns nothing (add team surnames locally, do not commit the pattern).
- [ ] **Step 4:** Tag `v1.0-phase1`.

---

## Adversarial-robustness & coverage extensions (Tasks 14–18)

These five tasks are what carry the "evasion" score and the brief's efficiency/remote-sensing asks. They are all **defensive evaluation**: every one produces a labelled suite or a measurement that tells the team where its own detector is weak, scored by the same harness, never used to tune the detector. Each new fault family is a synthetic perturbation of public data whose purpose is to *challenge the detector harder*, and the headline deliverable of each is a robustness number for the report.

**Shared integration requirements (Tasks 14–16, 18):**
- Standard suite format: `data/suites/<name>/{var}.parquet` (full 2023–2024 index, same columns as clean), `labels.parquet` (Task 6 schema; `category = "A"`), `manifest.json` (Task 7), built via `uv run python -m attacks.build_suites --only <name>`, byte-identical on rebuild (extend `test_build_is_byte_identical`).
- 2023 untouched; Task 5 placement rules apply; scored by `eval.run` unchanged; never used for detector tuning.
- New families add their name to `Family` + `REQUIRED_PARAMS` (Task 2, tests first) and a generator test to `tests/test_families.py`; new rows go into the Task 11 figures and the Task 12 catalogue.

### Task 14: Adaptive-difficulty evaluation (minimum-escape magnitude)

Goal: for each base family, measure the **smallest fault magnitude a given detector fails to catch** — the detector's blind-spot boundary — so the report states robustness as a number, not a hope. This is the "adaptive evaluation" best practice: use the detector's own responses to focus the magnitude search instead of a fixed grid.

**Files:** Create `attacks/adaptive.py`, `eval/escape.py`, `tests/test_adaptive.py`

**Interfaces:**
- Consumes: a placed base scenario (Task 5), the injector (Task 6), a detector callable `detect(values: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]` (bool alarms; the team detector, or a Task 10 baseline for development).
- Produces:
  - `escape_magnitude(scenario, clean, sigma, detect, *, grid: list[float], grace="1h") -> float` — bisection/scan over the family's size parameter on the given grid; returns the largest size that stays undetected (NaN if even the smallest is caught). Pure function of (scenario, detector); deterministic.
  - `build_adaptive_suite(base_specs, clean, sigma, detect, pool="heldout") -> Suite` — for each base family × station, the scenario at its escape magnitude (and one step above, which should be caught). `family` keeps the base name; a label column `adaptive_of` records the base and `escape_size` the boundary.
  - CLI `uv run python -m eval.escape --detector module:function --suite adaptive_probe` → writes the suite + `results/<run>/escape.parquet` (escape magnitude per family × variable).
- Report deliverable: an "escape-magnitude by family" table and the single line "the detector reliably catches faults ≥ X σ_ref; below that is residual risk" — the honest evasion result.

- [ ] **Step 1: Failing tests** with a toy threshold detector `detect(x)=|x−median|>2σ`: `test_escape_magnitude_just_below_threshold` (grid straddling 2σ → returns the largest grid size < 2σ), `test_escape_is_nan_when_smallest_caught`, `test_adaptive_suite_has_one_scenario_per_base_family`, `test_adaptive_suite_is_deterministic`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: adaptive-difficulty escape-magnitude evaluation`.

### Task 15: Realistic-replacement family (statistics-matched)

Goal: test whether the detector leans only on each station's own marginal/temporal statistics. This family replaces a window with values resampled from that station's **own** recent history (so its mean, variance and diurnal shape look right) carrying an embedded bias of `k·σ_ref`. Because it is generated from one station in isolation, it diverges from what the neighbours actually recorded in that window — so a spatial/cross-source detector should still catch it. That contrast is the point: it isolates which detector family carries the load.

**Files:** Modify `attacks/families.py` (+`realistic_replace`), `attacks/schema.py` (Task 2 family list); Create tests in `tests/test_families.py`

**Interfaces:**
- `realistic_replace(x, params, sigma, rng, *, history: np.ndarray, tod_index: np.ndarray) -> np.ndarray` — params `{k, generator}`. `generator="empirical"` (default): resample from `history` conditioned on time-of-day bin; `generator="ar1"`: seasonal-mean + AR(1) residual fit on `history`. Adds `k·σ_ref`. `history` = the same station's prior 30 days (passed by the injector from the clean table); `tod_index` the 5-min-of-day bin.
- Grid (dev): `k ∈ {1, 2, 3}`, `generator ∈ {empirical, ar1}`, durations {6 h, 24 h, 72 h}, T and RH. Held-out: `k ∈ {1.5}`, both generators, {48 h}.

- [ ] **Step 1: Failing tests:** `test_realistic_replace_matches_marginal_mean` (output mean ≈ history mean + k·σ, tol 10 %), `test_realistic_replace_diverges_from_neighbours` (on a synthetic 2-station fixture where neighbour moved and station didn't, |x−neighbour| grows), `test_input_not_mutated`, `test_same_seed_same_output`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (injector passes `history`/`tod_index`; extend `inject` call site). **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: statistics-matched replacement family`.

### Task 16: Cycle-shaped bias family

Goal: test whether the detector's temporal baseline can be fooled by a bias shaped like the natural daily cycle instead of a flat step. The injected delta is `k·σ_ref` modulated by the station's own diurnal amplitude (largest when the real signal naturally swings most), so it rides inside the expected pattern. Still breaks neighbour consistency and cross-source comparison — those detectors remain the defence, which the results show.

**Files:** Modify `attacks/families.py` (+`cycle_shaped`), `attacks/schema.py`; tests in `tests/test_families.py`

**Interfaces:**
- `cycle_shaped(x, params, sigma, rng, *, diurnal: np.ndarray) -> np.ndarray` — params `{k}`. `diurnal` = normalised (0..1) mean diurnal shape for this station/variable (passed by injector from a 2023 climatology precomputed in `data/clean/diurnal_<var>.parquet`, added as a build step in Task 1). Delta = `k·σ_ref · diurnal[tod]`.
- Grid (dev): `k ∈ {1, 2, 3}`, durations {24 h, 72 h, 168 h}, T and RH. Held-out: `k ∈ {1.5}`, {120 h}.

- [ ] **Step 1: Failing tests:** `test_cycle_shaped_peaks_with_diurnal`, `test_cycle_shaped_zero_amplitude_is_noop` (flat diurnal → unchanged), `test_input_not_mutated`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (+ Task 1 diurnal climatology build step and its test `test_diurnal_has_288_bins`). **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: cycle-shaped bias family`.

### Task 17: Efficiency, memory & security-overhead measurement

Goal: the brief asks for "latency, memory and security overhead"; Phase 1 "Feasibility" (10) and Phase 2 "Metrics, efficiency & accessibility" (10) score it. This builds the instrument; teammates point it at their pipeline.

**Files:** Create `eval/overhead.py`, `eval/bench_crypto.py`, `tests/test_overhead.py`

**Interfaces:**
- `measure(run_once: Callable[[], object], *, repeats: int, warmup: int = 1) -> dict` — wall-clock p50/p95 per call, peak RSS via `tracemalloc` + `resource.getrusage`, throughput (readings/s). Deterministic shape, values vary.
- `crypto_overhead(n: int) -> dict` — Ed25519 sign + verify throughput and per-record bytes (signature + seq + prev_hash) using the already-installed `cryptography`/`pynacl`; this is the quantified "security overhead" of L1, runnable without the teammates' code.
- CLI `uv run python -m eval.overhead --pipeline module:function --suite dev` → `results/<run>/overhead.json` (detector per-window latency, memory, throughput); `uv run python -m eval.bench_crypto` → `results/<run>/crypto.json`.
- Report deliverable: a small table — per-reading verify cost, added bytes per record, detector latency p50/p95, peak memory on `dev` — proving laptop feasibility.

- [ ] **Step 1: Failing tests:** `test_measure_reports_percentiles_and_peak`, `test_crypto_overhead_roundtrip_counts` (signs and verifies n records, verify failures = 0, bytes > 0), `test_measure_is_pure_on_noop`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Run `bench_crypto` now (no dependency) and record numbers in `docs/results.md`.
- [ ] **Step 6:** Commit `feat: efficiency and security-overhead measurement`.

### Task 18: Cross-source reference + network-wide bias (remote-sensing angle)

Goal: the challenge wants all three chapters, including remote sensing. A network-wide bias (every station shifted together) **defeats neighbour consistency** — the whole network agrees with itself — and can only be caught by comparison to an independent external reference. This task provides that reference, the scenario that needs it, a cross-source baseline, and the scoring, giving the team a concrete remote-sensing result and the motivating attack for it.

**Files:** Create `data_prep/reference.py`, `attacks/families.py` (+`network_bias`), `eval/baselines.py` (+`crosssource_baseline`), `tests/test_reference.py`

**Interfaces:**
- `load_reference(bbox, years) -> pd.DataFrame` — ERA5-Land 2 m temperature (and optionally 2 m RH) for the FBR bounding box, hourly, averaged to a single area series (the network spans ~1–4 ERA5 cells — document this coarseness), reindexed/forward-filled to the 5-min grid, saved `data/clean/reference_t2m.parquet`. CLI `uv run python -m data_prep.reference` reads CDS creds from env `CDS_API_KEY`; if unset, prints registration steps and falls back to the WegenerNet **gridded** NetCDF area-mean (a valid independent-of-single-station reference) so the task is not blocked on CDS.
- `network_bias` family: offset `k·σ_ref` applied to **all stations in the pool at once** over a window. Grid (heldout only, this is a flagship held-out case): `k ∈ {1, 2, 3}`, durations {24 h, 72 h}, T. Labels: one row per station, `n_stations = pool size`, `family = "network_bias"`.
- `crosssource_baseline(values, reference, sigma_area, z=4, persist=6) -> pd.DataFrame` — alarm when the network-area mean departs from the reference by > `z·sigma_area` for ≥ persist steps; broadcast to all stations. Scored by `eval.run` like any other alarm table.

- [ ] **Step 1: Failing tests:** `test_network_bias_shifts_all_stations`, `test_neighbor_baseline_misses_network_bias` (neighbour baseline recall ≈ 0 on a network_bias fixture — the motivating result), `test_crosssource_baseline_catches_network_bias`, `test_reference_aligned_to_5min_grid`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Build a `crosssource` suite, run both baselines, record in `docs/results.md` the contrast (neighbour misses, cross-source catches).
- [ ] **Step 6:** Commit `feat: cross-source reference and network-wide bias`.

---

## Schedule (assuming the 3 Nov deadline)

| Day | Tasks | Hand-off to teammates |
|---|---|---|
| Tue 27 Oct | data ready ✔, 0, 1 | `data/clean/*` |
| Wed 28 Oct | 2, 3, 4, 17 (crypto bench now) | — |
| Thu 29 Oct | 5, 6, 7, 15, 16 | **`smoke` + `dev` + `clean2024`** (detectors can start tuning) |
| Fri 30 Oct | 8, 9 (incl. leakage), 18 | `records_bc` + scoring CLI + `crosssource` |
| Sat 31 Oct | 10, 14, `heldout` build | baseline + escape-magnitude numbers |
| Sun 1 Nov | 11, 12, 17 (point at their pipeline) | figures + catalogue + protocol into the report |
| Mon 2 Nov | 13 + score the team detector on `heldout` + run 14 against it once | final tables |
| Tue 3 Nov | submit | |

Core path (must ship): 0–13. Extensions (carry the extra points): 14 (evasion number), 15–16 (harder families), 17 (efficiency/overhead), 18 (remote-sensing). If time runs short, 17's crypto bench and 18 are the highest value-per-hour; 14 needs the team detector to be meaningful.

Parallelisable for agents: {Task 0, Task 1} · {Task 2 → Task 3 → 15, 16} · {Task 8} · {Task 17 crypto bench, standalone} · {Task 9 → 14} once Task 6's label schema is fixed (it is, above); Task 18 after Task 10.

## Phase 2 follow-ups (after preselection, not in this plan)

- Replay `showcase` live through the full L1–L4 pipeline for the pitch demo.
- Ingest any jury-provided held-out data via the labels schema and score with `eval.run`.
- Run Task 14 escape-magnitude against the final tuned detector and report the closed blind spots.
- Add a second independent reference (e.g. MODIS land-surface temperature) to strengthen Task 18.
