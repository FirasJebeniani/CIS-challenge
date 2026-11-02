# Results

Generated numbers for the Phase 1 report. Detection/leakage/false-alarm tables are added
once the detector and scoring land; the efficiency section below is final.

## Suite calibration (reference baseline on the dev suite)

The `baseline_combined` reference detector (range/step/constancy rules OR 5-NN consistency)
is a floor, not the team detector. On the real `dev` suite its offset recall rises monotonically
with fault size, confirming the exam is graded, not all-or-nothing:

| offset size (k·σ_ref) | 0.5 | 1 | 2 | 3 | 5 |
|---|---|---|---|---|---|
| recall | 0.31 | 0.31 | 0.38 | 0.50 | 0.81 |

Small faults (k ≤ 1) mostly evade (recall < 0.5, as the design targets); large faults (k = 5)
are mostly caught (0.81). The team detector should exceed 0.9 at k = 5 — the ~0.19 the floor
misses is the headroom it must win. Per-family recall for the floor (dev): drift 0.83,
multi_offset 0.89, stuck 0.75, noise 0.64, spike 0.53, flatline 0.08 (flatline hides variance,
so a rules/neighbour floor is weak — a spectral/temporal detector is needed).

False-alarm rate of the floor on fault-free 2024 (`clean2024`): air temperature ~4.5 alarms
per station-day (0.61 episodes), precipitation ~0.02. Humidity is noisier (the 5-NN rule at
z = 4 fires on real day/night valley differences); the team detector should bring this down —
lower false-alarm rate is the competition's second tie-breaker.

## Cross-source check & the network-wide bias (remote-sensing angle)

A `network_bias` fault shifts every station together. Neighbour consistency is **structurally
blind** to it: when all stations (and therefore all of each station's neighbours) move by the
same amount, every station still agrees with its neighbours. The `crosssource` suite is this
attack (whole network, k = 2 and 3 σ_ref, held out).

The controlled demonstration (unit tests `test_neighbor_baseline_misses_network_bias`,
`test_crosssource_baseline_catches_network_bias`): under a uniform network shift, the neighbour
baseline alarms on < 2 % of cells (its background noise — it does not detect the shift), while
the cross-source check against an independent reference alarms on ~100 % of cells.

Honest limitation worth stating in the report: with **in-situ station data alone**, a coordinated
whole-network bias is not separable from a genuine regional weather event — any internal
reference (even a held-out station cluster) moves with the attack. Separating them **requires an
independent source**: ERA5-Land reanalysis or satellite land-surface temperature. `data_prep/reference.py`
fetches ERA5 when a CDS key is configured and the `crosssource_baseline` detector consumes it;
without a key it documents the requirement. This is precisely why the challenge asks all three
chapters to combine — the remote-sensing input is not optional for this attack class. (The
network spans only ~1–4 ERA5 cells, so the external reference is a network-wide check, not a
per-station one — which the temporal/spatial detectors already cover.)

## Escape magnitude (evasion) — reference baseline

`eval/escape.py` sweeps each family's size and reports the largest the detector still misses.
Against the `baseline_combined` reference (one showcase window per family), the escape magnitudes are:
offset 3·σ_ref, noise 2·σ_ref, cycle_shaped 2·σ_ref, network_bias 2·σ_ref, rain_scale ×3, rain_inject 3 mm·scale.
Every other family was caught at the smallest probed size (NaN = no residual escape, or no size parameter).
Read this as the reference floor's blind spots; the team detector should push these boundaries lower,
and the same command run against it gives the honest "below this, residual risk" line for the report.

## Efficiency & security overhead

Measured on a 16-core laptop, Python 3.12, `cryptography` 50.0.2 (Ed25519), n = 10 000 records.
This is the Layer-1 provenance cost — the "security overhead" the brief asks for.

| Metric | Value |
|---|---|
| Ed25519 sign throughput (incl. hash chaining) | ~34,900 records/s |
| Ed25519 verify throughput (incl. chain-link check) | ~11,300 records/s |
| Added bytes per record (sig 64 + seq 8 + prev_hash 32) | 104 B |
| Wire record size (payload 16 B + overhead) | 120 B |
| Verify failures on untampered stream | 0 |
| Tampered (bit-flipped) records rejected | 100 / 100 |

Interpretation: verifying every reading from all 154 stations (one reading per 5 min = 0.51
readings/s network-wide) uses a negligible fraction of one core; provenance is not a
bottleneck on a laptop. Detector latency, peak memory, and per-family detection/leakage
numbers follow once the detector is wired through `eval.overhead` and `eval.run`.
