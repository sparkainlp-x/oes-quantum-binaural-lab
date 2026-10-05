# Default simulation summary

Generated from the documented default simulation on 2026-10-05 with review fixes applied (v0.1.0). The run used the fixed seed 1731, 512 independent simulated pairs, 64 calibration shots per prepared outcome per pair, and the default evaluation sweep of 4, 8, and 16 shots per pair per setting. The result below is from the final 16-shot sweep point (8,192 held-out Bell evaluation shots per setting; 32,768 total across four settings). Evaluation shots are generated from the **hidden true** per-pair readout matrices; only the calibration **estimates** are used for correction.

| Measure | Fresh default-run result |
|---|---:|
| Raw Bell CHSH | 2.525878906250 |
| Corrected Bell CHSH | 2.837728425669 |
| Conditional 95% interval | [2.799946701594, 2.875510149745] |
| Bound, 2√2 | 2.828427124746 |
| Does the interval overlap the bound? | Yes |

**CHSH is an approximate simulator-only protocol check**, not a physical Bell test, loophole-free result, or hardware evidence. The corrected point may slightly exceed `2√2` because of finite-sample noise and Euclidean simplex-projection effects; that is expected for this classical Monte Carlo toy, not a physical claim. The interval is an analytic normal approximation for the *unprojected* linear-deconvolution shot variance (aggregate of unbounded component standard errors), conditional on the pooled estimated calibration matrix; it neither models projection effects nor propagates calibration-matrix estimation uncertainty. Matrix-cell Wilson intervals are reported separately and do not validate corrected-interval coverage.

The full machine-readable output is in [`default-run-report.json`](default-run-report.json). To reproduce from the project root, run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 run_lab.py --json reports/default-run-report.json
```
