import math
import unittest

from oes_quantum_binaural_lab.quantum import (
    CHSH_SETTINGS,
    calibrate_readout,
    collect_evaluation_counts,
    correct_distribution,
    correlation,
    estimate_plus_state,
    ideal_bell_distribution,
    ideal_separable_distribution,
    run_quantum_sandbox,
    summarize_family,
    _raw_e_ci,
)


class QuantumLaneTests(unittest.TestCase):
    def test_probabilities_are_normalized(self):
        for a, b in CHSH_SETTINGS:
            self.assertAlmostEqual(sum(ideal_bell_distribution(a, b)), 1.0)
            self.assertAlmostEqual(sum(ideal_separable_distribution(a, b)), 1.0)
        plus = estimate_plus_state(1000, seed=42)
        lo, hi = plus["probability_zero_ci95_wilson"]
        self.assertTrue(lo <= plus["probability_zero_estimate"] <= hi)
        self.assertAlmostEqual(plus["ideal_probability_zero"], 0.5)

    def test_ideal_bell_pair_correlations_and_protocol_value(self):
        es = [correlation(ideal_bell_distribution(a, b)) for a, b in CHSH_SETTINGS]
        self.assertAlmostEqual(es[0], math.sqrt(0.5), places=12)
        self.assertAlmostEqual(es[1], math.sqrt(0.5), places=12)
        self.assertAlmostEqual(es[2], math.sqrt(0.5), places=12)
        self.assertAlmostEqual(es[3], -math.sqrt(0.5), places=12)
        self.assertAlmostEqual(es[0] + es[1] + es[2] - es[3], 2 * math.sqrt(2), places=12)

    def test_separable_control_does_not_exceed_chsh_bound(self):
        es = [correlation(ideal_separable_distribution(a, b)) for a, b in CHSH_SETTINGS]
        chsh = es[0] + es[1] + es[2] - es[3]
        self.assertLessEqual(abs(chsh), 2.0 + 1e-12)

    def test_corrected_distribution_is_nonnegative_and_sums_to_one(self):
        identity = tuple(tuple(1.0 if row == col else 0.0 for col in range(4)) for row in range(4))
        projected = correct_distribution((-0.2, 0.4, 0.5, 0.3), identity)
        self.assertTrue(all(value >= 0.0 for value in projected))
        self.assertAlmostEqual(sum(projected), 1.0, places=14)

    def test_corrected_distribution_preserves_valid_simplex_input(self):
        identity = tuple(tuple(1.0 if row == col else 0.0 for col in range(4)) for row in range(4))
        valid = (0.1, 0.2, 0.3, 0.4)
        projected = correct_distribution(valid, identity)
        for actual, expected in zip(projected, valid):
            self.assertAlmostEqual(actual, expected, places=14)

    def test_correction_uses_euclidean_projection_not_clip_and_renormalize(self):
        identity = tuple(tuple(1.0 if row == col else 0.0 for col in range(4)) for row in range(4))
        estimate = (-1.0, 0.5, 0.5, 1.0)
        projected = correct_distribution(estimate, identity)
        expected = (0.0, 1.0 / 6.0, 1.0 / 6.0, 2.0 / 3.0)
        clipped_and_renormalized = (0.0, 0.25, 0.25, 0.5)
        for actual, target in zip(projected, expected):
            self.assertAlmostEqual(actual, target, places=14)
        self.assertNotEqual(projected, clipped_and_renormalized)

    def test_pairwise_calibration_and_separate_evaluation_correct_readout(self):
        cal = calibrate_readout(pair_count=1, shots_per_prepared_state=4096, seed=9)
        self.assertEqual(cal.total_calibration_shots, 4 * 4096)
        self.assertEqual(len(cal.true_pair_matrices), 1)
        self.assertEqual(len(cal.pair_matrices), 1)
        self.assertEqual(len(cal.estimated_matrix), 4)
        self.assertTrue(all(abs(sum(row) - 1.0) < 1e-12 for row in cal.estimated_matrix))
        self.assertTrue(all(0 <= lo <= hi <= 1 for row in cal.ci95 for lo, hi in row))
        # Evaluation must use the hidden true matrices; correction uses estimates only.
        eval_counts = collect_evaluation_counts(cal.true_pair_matrices, "bell", (0.0, 0.0), 20_000, seed=55)
        n = sum(eval_counts)
        raw = correlation([c / n for c in eval_counts])
        corrected = correlation(correct_distribution([c / n for c in eval_counts], cal.estimated_matrix))
        self.assertEqual(n, 20_000)
        self.assertLess(abs(corrected - 1.0), abs(raw - 1.0))
        self.assertEqual(cal.total_calibration_shots, 16_384)

    def test_shot_estimates_vary_and_interval_tightens(self):
        small_estimates = [estimate_plus_state(64, seed=s)["zero_count"] for s in range(12, 24)]
        large = estimate_plus_state(8192, seed=14)
        self.assertGreater(len(set(small_estimates)), 1)
        sample = estimate_plus_state(64, seed=12)
        small_width = sample["probability_zero_ci95_wilson"][1] - sample["probability_zero_ci95_wilson"][0]
        large_width = large["probability_zero_ci95_wilson"][1] - large["probability_zero_ci95_wilson"][0]
        self.assertLess(large_width, small_width)
        self.assertLess(abs(large["probability_zero_estimate"] - 0.5), 0.04)

    def test_bounded_sweep_reports_held_out_counts_and_claim_labels(self):
        result = run_quantum_sandbox(pair_count=8, calibration_shots_per_state=8, sweep_shots_per_pair=(1, 2), seed=17)
        self.assertEqual(result["model"]["qubit_count"], 16)
        self.assertIn("not one globally entangled", result["model"]["structure"])
        self.assertFalse(result["readout_calibration"]["cross_pair_correlated_readout_modeled"])
        self.assertTrue(result["readout_calibration"]["evaluation_shots_separate_and_held_out"])
        self.assertEqual(len(result["sweep"]), 2)
        self.assertIn("not a loophole-free Bell test", result["sweep"][-1]["bell"]["chsh_label"])
        self.assertGreater(result["sweep"][-1]["bell_pair_evaluation_shots_total"], 0)

    def test_h_then_z_control_separates_plus_from_mixture(self):
        result = estimate_plus_state(4096, seed=99)
        control = result["h_then_z_control"]
        self.assertEqual(control["ideal_plus_one_count"], 0)
        self.assertEqual(control["ideal_plus_probability_one_estimate"], 0.0)
        self.assertLess(abs(control["mixture_probability_one_estimate"] - 0.5), 0.05)
        # Bare Z arm remains a balanced-outcome sampler (~50/50).
        self.assertLess(abs(result["probability_zero_estimate"] - 0.5), 0.05)

    def test_calibration_independence_repeated_seeds_as_cal_shots_vary(self):
        # Hidden true matrices must drive evaluation; estimates alone are for correction.
        # As calibration shots increase, mean |corrected - ideal| should drop across seeds.
        shot_levels = (8, 64, 512)
        mean_errors = []
        for shots in shot_levels:
            errors = []
            for seed in range(20, 28):
                cal = calibrate_readout(pair_count=4, shots_per_prepared_state=shots, seed=seed)
                self.assertEqual(len(cal.true_pair_matrices), 4)
                # Low-shot estimates should generally differ from the hidden truth.
                if shots == 8:
                    self.assertNotEqual(cal.pair_matrices[0], cal.true_pair_matrices[0])
                counts = collect_evaluation_counts(
                    cal.true_pair_matrices, "bell", (0.0, 0.0), 4_000, seed=seed + 1000
                )
                n = sum(counts)
                corrected = correlation(
                    correct_distribution([c / n for c in counts], cal.estimated_matrix)
                )
                errors.append(abs(corrected - 1.0))
            mean_errors.append(sum(errors) / len(errors))
        self.assertLess(mean_errors[-1], mean_errors[0])
        self.assertLess(mean_errors[-1], 0.05)

    def test_chsh_interval_aggregates_unbounded_standard_errors(self):
        # Low-shot component CIs clip to [-1, 1]; recovering SE from clipped widths
        # underestimates the aggregate CHSH interval. Use unbounded SEs instead.
        low_shot_counts = [(1, 1, 0, 0)] * 4  # n=2, E≈0, margin > 1 so CI clips
        identity = tuple(tuple(1.0 if r == c else 0.0 for c in range(4)) for r in range(4))
        summary = summarize_family(low_shot_counts, identity)
        # Unbounded SE per component from the same counts:
        _, clipped_ci, se = _raw_e_ci(low_shot_counts[0])
        self.assertAlmostEqual(clipped_ci[0], -1.0)
        self.assertAlmostEqual(clipped_ci[1], 1.0)
        clipped_recovered_se = (clipped_ci[1] - clipped_ci[0]) / (2 * 1.959963984540054)
        self.assertGreater(se, clipped_recovered_se)
        chsh_half_width = (
            summary["chsh_raw_ci95"][1] - summary["chsh_raw_ci95"][0]
        ) / 2
        expected_unbounded = 1.959963984540054 * (4 * se * se) ** 0.5
        self.assertAlmostEqual(chsh_half_width, expected_unbounded, places=12)
        # Clipped aggregation would have been narrower:
        clipped_aggregate = 1.959963984540054 * (4 * clipped_recovered_se ** 2) ** 0.5
        self.assertGreater(chsh_half_width, clipped_aggregate)
        self.assertIn("approximate simulator check", summary["chsh_label"])



if __name__ == "__main__":
    unittest.main()
