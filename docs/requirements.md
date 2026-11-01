# Requirement and development tracking

Source documents supplied for this project are the two-page official challenge
PDF, the updated 40-step development plan and the earlier Layers 1/2 architecture.
The official PDF does not name the reference datasets or define the common
Track 2 attack/evasion scenario. No dataset schema is assumed.

## Official criteria

| Requirement or criterion | Phase 1 foundation | Remaining evidence |
| --- | --- | --- |
| Exactly one track | Track 2 documented | Team submission selection |
| Authentic public data and official reference datasets | Adapter boundary documented | Dataset URLs, licenses, actual columns, official standard scenario |
| Threat model and segment analysis | Initial threat model | Validate with actual deployments and official attack scope |
| Architecture and trust anchor | Modular scaffold and contracts | Deployment trust separation and hardware/remote anti-rollback evidence |
| Signal processing | Phase 4 normalization, alignment and feature algorithms tested | Official sources, deployment parameter calibration and L3 acceptance |
| AI/statistical detection | Provisional L3 input boundary | L3 implementation, training/evaluation split and detector results |
| Adversarial validation and response | Status/event types and threat scenarios | Held-out official scenario tests and L4 response integration |
| Detection quality and false alarms | No metrics claimed | Labeled standard evaluation and attack/evasion results |
| Latency, memory, security overhead | Actual synthetic local benchmark and resource reports | Native Windows results, deployment-scale and broker-resource measurements |
| Local affordable execution | Python environment and local tests | Full prototype and clean-machine demonstration |
| Documentation/reproducibility | README, hash-locked dependencies, test evidence | Later-phase documentation and official data instructions |
| Anonymous Phase 1 submission | Anonymous defaults and checklist | Final repository/history/artifact audit |

Phase 1 scoring from PDF page 2: threat model 15; architecture 15; processing 15;
detector design/evaluation 20; standard scenario/evasion 20; local feasibility 10;
clarity/reproducibility 5. Phase 1 contributes 30% of the final score and Phase 2
70%. No bonus points are awarded. Dataset use and evaluation readiness must
receive early attention alongside cryptography.

## Development progress after Phase 6 implementation

| Phase / steps | State at this delivery |
| --- | --- |
| 1 / 1 | Python/dependencies verified locally; user supplied Windows results confirm Python 3.14.0, Mosquitto 2.1.2, Git and VS Code |
| 1 / 2 | Scaffold, ignores, VS Code settings and Git preparation complete; no remote created |
| 1 / 3 | Provisional contracts and automated tests implemented; L3/L4 acceptance pending |
| 2 / 4 | Three independent temperature simulators implemented; actual CLI exercised against a broker |
| 2 / 5 | Encrypted Ed25519 keys, public registry description, exclusive provisioning and file protections implemented |
| 2 / 6-7 | Canonical CBOR signing and domain-separated hash chains implemented and tested |
| 2 / 8-9 | MQTT v5, mutual TLS, per-sensor ACLs and bounded canonical CBOR implemented; actual broker tests executed |
| 2 / 10 | Independent keys/sequences/chains, three-sensor live publication and restart continuity tested |
| 3 / 11-16 | Implemented: bounded live receiver, explicit registry/revocation/rotation, Ed25519 verification, persistent replay/time/chain policy, durable L4 routing; tested with real broker |
| 4 / 17-18 | Implemented/tested: all six semantic cases, C/F/K normalization, immutable raw evidence and duplicate handling |
| 4 / 19-21 | Implemented/tested: UTC alignment, variable sample rates, missingness, rolling/statistical/conditional spectral features and configured-neighbor comparisons |
| 4 / 22 | Generic reference interface, unit/time/location matching and availability checks implemented/tested; actual official datasets and source adapters pending |
| 4 / 23 | Existing FeatureWindow constructed and round-trip tested with provenance, raw/normalized values and feature availability |
| 5 / 24 | Implemented/tested: direct FeatureWindow callable handoff and stub; real L3 acceptance pending |
| 5 / 25 | Typed source-traceable dataset boundary; actual data adapters pending supplied sources |
| 5 / 26-29 | Implemented/tested: post-sign tamper, unknown sensor, replay, deletion/reordering, signed chain break |
| 5 / 30 | Eight configurable signed families and feature extraction tested; detector evaluation pending |
| 5 / 31-32 | Deterministic isolated replay and unit/integration tests, including real broker attack delivery |
| 6 / 33 | Implemented/tested: multi-series primitive/durable/L2 latency statistics and real MQTT timing |
| 6 / 34 | Implemented/tested: CPU/RSS/Python allocation observations, message sizes and controlled serialization/TLS comparisons |
| 6 / 35 | Implemented/tested: bounded retries, explicit recovery archive, concurrent-sensor soak with restart/gap/duplicate faults; extended deployment soak pending |
| 6 / 36 | Metrics formulas and strict evaluation-only input validated; real L3 predictions and approved labeled datasets pending |
| 7 / 37-40 | Pending |

The six semantic validator cases (Celsius, Fahrenheit, Kelvin, wrong types, nulls
and unknown units) are explicitly implemented in tests/test_validator.py. These
semantic tests supplement the original envelope contract tests.

## Unresolved inputs and decisions

1. Official reference dataset links and Track 2 common attack/evasion specification.
2. L3/L4 code or interface agreement, features, missingness, windows and routing.
3. Native Windows Phase 6 execution remains pending. User-supplied Phase 5 broker run: 360 passed, 1 skipped in 57.40s; attack demo also succeeded.
4. Conservative stream policy remains enforced. Phase 6 adds transport retries and explicit retained-byte recovery; automatic archival rotation, multi-hour soak and recovery beyond freshness limits remain operational work.
5. Geographic metadata, trusted neighbors and available external references.
6. Clarification of deadline conflict: page 1 says 8 November 2026; page 2 says
   first submission 3 November and preselection 8 November. Plan for the earlier
   date until organizers clarify. Competition phases differ from development phases.

Do not claim official compliance, detection performance or final compatibility
until the relevant evidence is available.
