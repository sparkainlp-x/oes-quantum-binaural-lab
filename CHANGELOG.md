# Changelog

All notable changes to this project. Everything here is a SYNTHETIC classical toy simulation.

## 0.1.0 (2026-10-05)

First tagged release (`v0.1.0`). The Zenodo DOI is added to the README and `CITATION.cff` after Zenodo archives the release; the tag is not moved.

### Added

- Three separate classical lanes joined only by a scalar event bus: a classical metrics ledger (1,024 scalar slots), a Bell-correlation Monte Carlo model (512 independent pairwise samplers; no quantum state or circuit evolution) and digital stereo loopback (in-memory multitone; no audio device).
- Pair-local 4x4 readout assignment matrices, with calibration shots kept separate from evaluation shots, and a bounded linear correction projected onto the probability simplex.
- `|+>` superposition sampler with an H-then-Z coherence control.
- Optional loopback-only local dashboard.
- Bundled default-run reports (seed 1731).

### Review fixes included in 0.1.0

- Calibration independence, the H-then-Z control, unclipped CHSH interval aggregation, audio aliasing and zero-level crosstalk guards, event-bus string limits, accurate lane naming, regenerated reports.

### Known limitations

- CHSH is an approximate simulator check only; the corrected point can exceed 2*sqrt(2) through finite-sample and projection effects, which is a simulator artifact.
- Intervals do not account for projection effects or matrix-estimation uncertainty.
- Cross-pair correlated readout is not simulated; analog audio calibration is not included.
- No quantum hardware, QEC, quantum advantage or consciousness claim.
