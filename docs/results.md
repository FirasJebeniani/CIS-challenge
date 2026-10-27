# Results

Generated numbers for the Phase 1 report. Detection/leakage/false-alarm tables are added
once the detector and scoring land; the efficiency section below is final.

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
