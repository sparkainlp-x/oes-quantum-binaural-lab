"""Bell-correlation Monte Carlo model: independent pair samplers, not a QPU.

Classical toy simulation only. No dense 2**1024 state vector, no quantum state
or circuit evolution, and no quantum advantage. Each of at most 512 pairs is
sampled from a stipulated four-outcome correlation law with a simulated 4x4
readout assignment matrix. Outputs are Monte Carlo statistics of this sandbox.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, isfinite, pi, sin, sqrt
import random
from statistics import NormalDist
from typing import Sequence

OUTCOMES = ((0, 0), (0, 1), (1, 0), (1, 1))
OUTCOME_SIGNS = (1.0, -1.0, -1.0, 1.0)
CHSH_SETTINGS = ((0.0, pi / 8), (0.0, -pi / 8), (pi / 4, pi / 8), (pi / 4, -pi / 8))


@dataclass(frozen=True)
class ReadoutCalibration:
    true_pair_matrices: tuple[tuple[tuple[float, ...], ...], ...]
    pair_matrices: tuple[tuple[tuple[float, ...], ...], ...]
    estimated_matrix: tuple[tuple[float, ...], ...]
    pooled_counts: tuple[tuple[int, ...], ...]
    ci95: tuple[tuple[tuple[float, float], ...], ...]
    shots_per_prepared_state_per_pair: int
    total_calibration_shots: int


def ideal_bell_distribution(angle_a: float, angle_b: float) -> tuple[float, ...]:
    """Joint probabilities for the toy |Phi+> pair under analyzer settings.

    E = cos(2(a-b)); bits map to +/-1. This is a protocol-level simulator,
    not a claim about a physical apparatus.
    """
    corr = cos(2.0 * (angle_a - angle_b))
    return tuple((1.0 + OUTCOME_SIGNS[i] * corr) / 4.0 for i in range(4))


def ideal_separable_distribution(angle_a: float, angle_b: float) -> tuple[float, ...]:
    """Product-state |00> control with independent local measurement outcomes."""
    ea, eb = cos(2.0 * angle_a), cos(2.0 * angle_b)
    result = []
    for a, b in OUTCOMES:
        sa, sb = (1.0 if a == 0 else -1.0), (1.0 if b == 0 else -1.0)
        result.append((1.0 + sa * ea) * (1.0 + sb * eb) / 4.0)
    return tuple(result)


def correlation(probabilities: Sequence[float]) -> float:
    if len(probabilities) != 4:
        raise ValueError("a pair distribution must have four outcomes")
    return sum(p * s for p, s in zip(probabilities, OUTCOME_SIGNS))


def _pair_assignment_matrix(pair_id: int) -> tuple[tuple[float, ...], ...]:
    """Simulated pair-local assignment matrix with small pair-to-pair drift."""
    base = (
        (0.940, 0.025, 0.025, 0.010),
        (0.025, 0.930, 0.015, 0.030),
        (0.025, 0.015, 0.930, 0.030),
        (0.010, 0.030, 0.030, 0.930),
    )
    delta = ((pair_id % 7) - 3) * 0.0005
    rows: list[tuple[float, ...]] = []
    for row_idx, row in enumerate(base):
        adjusted = list(row)
        adjusted[row_idx] += delta
        donor = max((j for j in range(4) if j != row_idx), key=lambda j: adjusted[j])
        adjusted[donor] -= delta
        rows.append(tuple(adjusted))
    return tuple(rows)


def _draw_index(probabilities: Sequence[float], rng: random.Random) -> int:
    r = rng.random()
    cumulative = 0.0
    for i, p in enumerate(probabilities):
        cumulative += p
        if r < cumulative or i == len(probabilities) - 1:
            return i
    raise AssertionError("unreachable")


def _wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    radius = z * sqrt((p * (1 - p) / n) + (z * z / (4 * n * n))) / denom
    return (max(0.0, center - radius), min(1.0, center + radius))


def calibrate_readout(pair_count: int = 512, shots_per_prepared_state: int = 64, seed: int = 1731) -> ReadoutCalibration:
    """Estimate each pair's 4x4 matrix from known 00, 01, 10, 11 preparations.

    Hidden true per-pair matrices are retained for independent evaluation draws.
    Calibration samples come from a dedicated RNG stream and are not reused in
    evaluation. Only the estimated (and pooled) matrices are used for correction.
    """
    if not 1 <= pair_count <= 512:
        raise ValueError("pair_count must be in 1..512")
    if not 8 <= shots_per_prepared_state <= 4096:
        raise ValueError("shots_per_prepared_state must be in 8..4096")
    rng = random.Random(seed)
    true_matrices = tuple(_pair_assignment_matrix(i) for i in range(pair_count))
    pair_estimates: list[tuple[tuple[float, ...], ...]] = []
    pooled = [[0 for _ in range(4)] for _ in range(4)]
    for matrix in true_matrices:
        local = [[0 for _ in range(4)] for _ in range(4)]
        for true_idx in range(4):
            for _ in range(shots_per_prepared_state):
                observed_idx = _draw_index(matrix[true_idx], rng)
                local[true_idx][observed_idx] += 1
                pooled[true_idx][observed_idx] += 1
        pair_estimates.append(tuple(tuple(v / shots_per_prepared_state for v in row) for row in local))
    row_n = pair_count * shots_per_prepared_state
    estimated = tuple(tuple(c / row_n for c in row) for row in pooled)
    ci = tuple(
        tuple(_wilson_interval(pooled[i][j], row_n) for j in range(4))
        for i in range(4)
    )
    return ReadoutCalibration(
        true_pair_matrices=true_matrices,
        pair_matrices=tuple(pair_estimates),
        estimated_matrix=estimated,
        pooled_counts=tuple(tuple(row) for row in pooled),
        ci95=ci,
        shots_per_prepared_state_per_pair=shots_per_prepared_state,
        total_calibration_shots=pair_count * 4 * shots_per_prepared_state,
    )


def _solve_linear(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    """Small 4x4 Gaussian elimination with partial pivoting."""
    n = len(rhs)
    a = [list(matrix[i]) + [float(rhs[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-10:
            raise ValueError("readout matrix is singular or ill-conditioned")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [v / scale for v in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            a[row] = [a[row][j] - factor * a[col][j] for j in range(n + 1)]
    return [a[i][n] for i in range(n)]


def _inverse(matrix: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    cols = [_solve_linear(matrix, [1.0 if r == c else 0.0 for r in range(4)]) for c in range(4)]
    return tuple(tuple(cols[c][r] for c in range(4)) for r in range(4))


def _project_onto_simplex(values: Sequence[float]) -> tuple[float, ...]:
    """Return the Euclidean projection of a real vector onto the probability simplex.

    The sorting/threshold method finds the unique minimizer of
    ``||p - values||_2`` subject to ``p_i >= 0`` and ``sum(p) == 1``.
    """
    if not values:
        raise ValueError("cannot project an empty vector onto the simplex")
    vector = tuple(float(value) for value in values)
    if any(not isfinite(value) for value in vector):
        raise ValueError("simplex projection requires finite values")

    ordered = sorted(vector, reverse=True)
    cumulative = 0.0
    rho = 0
    threshold = 0.0
    for index, value in enumerate(ordered, start=1):
        cumulative += value
        candidate = (cumulative - 1.0) / index
        if value > candidate:
            rho = index
            threshold = candidate
    if rho == 0:  # For a non-empty finite vector, the largest value always qualifies.
        raise ArithmeticError("failed to determine simplex projection threshold")
    return tuple(max(value - threshold, 0.0) for value in vector)


def correct_distribution(observed: Sequence[float], assignment: Sequence[Sequence[float]]) -> tuple[float, ...]:
    """Deconvolve ``q = p M`` and Euclidean-project the estimate onto the simplex.

    The projection is the unique nearest probability vector in Euclidean distance;
    it is not equivalent to clipping negative entries and renormalizing. Because
    the projection is nonlinear near the simplex boundary, this constrained
    finite-sample estimator is not generally unbiased.
    """
    if len(observed) != 4 or len(assignment) != 4 or any(len(row) != 4 for row in assignment):
        raise ValueError("expected a four-outcome vector and 4x4 assignment matrix")
    transposed = tuple(tuple(assignment[r][c] for r in range(4)) for c in range(4))
    estimate = _solve_linear(transposed, observed)
    return _project_onto_simplex(estimate)


def _sample_counts(probabilities: Sequence[float], n: int, rng: random.Random) -> list[int]:
    counts = [0, 0, 0, 0]
    for _ in range(n):
        counts[_draw_index(probabilities, rng)] += 1
    return counts


def collect_evaluation_counts(
    pair_matrices: Sequence[Sequence[Sequence[float]]],
    family: str,
    setting: tuple[float, float],
    shots_per_pair: int,
    seed: int,
) -> tuple[int, int, int, int]:
    """Collect held-out measurement shots, independent of calibration draws."""
    if family not in {"bell", "separable"}:
        raise ValueError("family must be bell or separable")
    if shots_per_pair < 1:
        raise ValueError("shots_per_pair must be positive")
    rng = random.Random(seed)
    a, b = setting
    ideal = ideal_bell_distribution(a, b) if family == "bell" else ideal_separable_distribution(a, b)
    counts = [0, 0, 0, 0]
    for matrix in pair_matrices:
        for _ in range(shots_per_pair):
            true_idx = _draw_index(ideal, rng)
            observed_idx = _draw_index(matrix[true_idx], rng)
            counts[observed_idx] += 1
    return tuple(counts)


def _multinomial_e(probabilities: Sequence[float], n: int, rng: random.Random) -> float:
    counts = _sample_counts(probabilities, n, rng)
    return correlation([c / n for c in counts])


def _corrected_e_ci(counts: Sequence[int], assignment: Sequence[Sequence[float]]) -> tuple[float, tuple[float, float], float]:
    n = sum(counts)
    observed = [c / n for c in counts]
    corrected = correct_distribution(observed, assignment)
    e = correlation(corrected)
    inv = _inverse(assignment)
    h = [sum(inv[r][c] * OUTCOME_SIGNS[c] for c in range(4)) for r in range(4)]
    mean_h = sum(observed[i] * h[i] for i in range(4))
    variance = sum(observed[i] * (h[i] - mean_h) ** 2 for i in range(4)) / n
    se = sqrt(max(0.0, variance))
    margin = 1.959963984540054 * se
    return e, (max(-1.0, e - margin), min(1.0, e + margin)), se


def _raw_e_ci(counts: Sequence[int]) -> tuple[float, tuple[float, float], float]:
    n = sum(counts)
    probs = [c / n for c in counts]
    e = correlation(probs)
    variance = max(0.0, sum(p * (s - e) ** 2 for p, s in zip(probs, OUTCOME_SIGNS)) / n)
    se = sqrt(variance)
    margin = 1.959963984540054 * se
    return e, (max(-1.0, e - margin), min(1.0, e + margin)), se


def summarize_family(counts_by_setting: Sequence[Sequence[int]], assignment: Sequence[Sequence[float]]) -> dict:
    rows = []
    raw_s = corrected_s = ideal_s = 0.0
    raw_var = corrected_var = 0.0
    signs = (1.0, 1.0, 1.0, -1.0)
    for idx, (angles, counts) in enumerate(zip(CHSH_SETTINGS, counts_by_setting)):
        raw_e, raw_ci, raw_se = _raw_e_ci(counts)
        corrected_e, corrected_ci, corrected_se = _corrected_e_ci(counts, assignment)
        ideal_dist = ideal_bell_distribution(*angles) if idx >= 0 else (0.25,) * 4
        # For the separable family the caller replaces ideal_e below.
        ideal_e = correlation(ideal_dist)
        rows.append({
            "setting": f"A{0 if idx < 2 else 1}B{0 if idx % 2 == 0 else 1}",
            "angle_a_rad": angles[0],
            "angle_b_rad": angles[1],
            "shots": sum(counts),
            "correlation_raw": raw_e,
            "correlation_raw_ci95": list(raw_ci),
            "correlation_corrected": corrected_e,
            "correlation_corrected_ci95_conditional_on_calibration": list(corrected_ci),
            "correlation_ideal": ideal_e,
        })
        raw_s += signs[idx] * raw_e
        corrected_s += signs[idx] * corrected_e
        ideal_s += signs[idx] * ideal_e
        # Aggregate unbounded component standard errors; do not recover SE from
        # correlation intervals that were clipped to [-1, 1].
        raw_var += raw_se ** 2
        corrected_var += corrected_se ** 2
    raw_margin = 1.959963984540054 * sqrt(raw_var)
    corrected_margin = 1.959963984540054 * sqrt(corrected_var)
    return {
        "settings": rows,
        "chsh_ideal_simulated": ideal_s,
        "chsh_raw": raw_s,
        "chsh_raw_ci95": [raw_s - raw_margin, raw_s + raw_margin],
        "chsh_corrected": corrected_s,
        "chsh_corrected_ci95_conditional_on_calibration": [corrected_s - corrected_margin, corrected_s + corrected_margin],
        "chsh_label": (
            "approximate simulator check only; not a loophole-free Bell test or hardware evidence. "
            "Corrected CHSH may exceed 2√2 from finite-sample noise and simplex-projection effects"
        ),
    }


def run_quantum_sandbox(
    pair_count: int = 512,
    calibration_shots_per_state: int = 64,
    sweep_shots_per_pair: Sequence[int] = (4, 8, 16),
    seed: int = 1731,
) -> dict:
    if not 1 <= pair_count <= 512:
        raise ValueError("pair_count must be in 1..512")
    sweep = sorted(set(int(n) for n in sweep_shots_per_pair))
    if not sweep or sweep[0] < 1 or sweep[-1] > 128:
        raise ValueError("sweep values must be in 1..128 shots per pair per setting")
    calibration = calibrate_readout(pair_count, calibration_shots_per_state, seed=seed + 101)
    results = []
    for shot_index, per_pair in enumerate(sweep):
        bell_counts = []
        sep_counts = []
        for setting_index, setting in enumerate(CHSH_SETTINGS):
            base = seed + 100_000 + shot_index * 10_000 + setting_index * 1_000
            bell_counts.append(collect_evaluation_counts(calibration.true_pair_matrices, "bell", setting, per_pair, base + 11))
            sep_counts.append(collect_evaluation_counts(calibration.true_pair_matrices, "separable", setting, per_pair, base + 29))
        bell_result = summarize_family(bell_counts, calibration.estimated_matrix)
        separable_result = summarize_family(sep_counts, calibration.estimated_matrix)
        # Swap the generic ideal values for the actual product-state expectations.
        for row, angles in zip(separable_result["settings"], CHSH_SETTINGS):
            row["correlation_ideal"] = correlation(ideal_separable_distribution(*angles))
        sep_signs = (1.0, 1.0, 1.0, -1.0)
        separable_result["chsh_ideal_simulated"] = sum(
            sep_signs[i] * correlation(ideal_separable_distribution(*angles))
            for i, angles in enumerate(CHSH_SETTINGS)
        )
        results.append({
            "shots_per_pair_per_setting": per_pair,
            "bell_pair_evaluation_shots_per_setting": pair_count * per_pair,
            "bell_pair_evaluation_shots_total": pair_count * per_pair * len(CHSH_SETTINGS),
            "separable_control_evaluation_shots_total": pair_count * per_pair * len(CHSH_SETTINGS),
            "superposition": estimate_plus_state(pair_count * per_pair, seed + 500_000 + shot_index),
            "bell": bell_result,
            "separable_control": separable_result,
        })
    matrix_intervals = []
    for r in range(4):
        matrix_intervals.append([
            {"estimate": calibration.estimated_matrix[r][c], "ci95_wilson": list(calibration.ci95[r][c])}
            for c in range(4)
        ])
    return {
        "model": {
            "pair_count": pair_count,
            "qubit_count": pair_count * 2,
            "structure": f"{pair_count} independent Bell-correlation Monte Carlo pair samplers; not one globally entangled {pair_count * 2}-qubit state; no quantum state/circuit evolution",
            "representation": "compact 4-outcome probability distributions per pair; classical Monte Carlo only; no dense global state vector",
            "observer_definition": "observer means measurement/readout in this simulator; it does not mean consciousness",
            "superposition_definition": "|+> is one balanced single-qubit state; increasing shots improves probability estimates, not the amount of superposition",
            "quantum_advantage_claimed": False,
            "classical_toy_simulation": True,
        },
        "readout_calibration": {
            "matrix_type": "one 4x4 pair-outcome assignment matrix per modeled pair; rows are known prepared outcomes 00,01,10,11; columns are recorded outcomes 00,01,10,11",
            "within_pair_crosstalk_included": True,
            "cross_pair_correlated_readout_modeled": False,
            "calibration_method": "repeated known-basis pair preparations; each pair matrix estimated from its own calibration-shot set; evaluation shots are generated from the hidden true matrices and corrected with estimates only",
            "evaluation_uses_hidden_true_matrices": True,
            "correction_uses_estimates_only": True,
            "calibration_shots_per_prepared_state_per_pair": calibration.shots_per_prepared_state_per_pair,
            "known_prepared_states_per_pair": 4,
            "pair_matrices_calibrated": pair_count,
            "calibration_shots_total": calibration.total_calibration_shots,
            "evaluation_shots_separate_and_held_out": True,
            "correction_matrix_for_aggregate_metrics": "pooled estimate across pair-specific calibration counts",
            "matrix_estimates_with_95pct_wilson_intervals": matrix_intervals,
            "corrected_metric_ci_note": "95% corrected metric intervals use an analytic normal approximation for the unprojected linear-deconvolution shot variance, conditional on the pooled estimated matrix. Point estimates are Euclidean-projected onto the probability simplex; intervals do not model projection effects or propagate matrix-estimation uncertainty. Matrix-cell Wilson intervals report calibration uncertainty separately, but do not validate corrected-interval coverage.",
        },
        "sweep": results,
        "limits": {
            "max_pairs": 512,
            "max_qubits": 1024,
            "max_shots_per_pair_per_setting": 128,
            "calibration_shots_max_per_prepared_state_per_pair": 4096,
            "cross_pair_crosstalk": "not modeled",
            "global_entanglement": "not modeled",
            "hardware": "software simulation only; no quantum hardware connection",
        },
    }


def estimate_plus_state(shots: int, seed: int = 811) -> dict:
    """Z-basis sampling of |+> plus an H-then-Z coherence control.

    A bare Z-basis measurement of |+> cannot distinguish a coherent equal
    superposition from an incoherent 50/50 mixture. The H-then-Z control can:
    ideal |+> maps under H to |0| (P(1)=0), while the mixture stays 50/50.
    """
    if shots < 1:
        raise ValueError("shots must be positive")
    rng = random.Random(seed)
    zeroes = sum(1 for _ in range(shots) if rng.random() < 0.5)
    lo, hi = _wilson_interval(zeroes, shots)
    # Ideal |+>: H|+> = |0|, so every Z outcome is 0.
    ideal_ones = 0
    # Incoherent 50/50 mixture after H: still 50/50 in Z.
    mix_rng = random.Random(seed + 17)
    mixture_ones = sum(1 for _ in range(shots) if mix_rng.random() < 0.5)
    mix_lo, mix_hi = _wilson_interval(shots - mixture_ones, shots)
    ideal_lo, ideal_hi = _wilson_interval(shots - ideal_ones, shots)
    return {
        "state": "|+> = (|0> + |1>)/sqrt(2)",
        "shots": shots,
        "zero_count": zeroes,
        "probability_zero_estimate": zeroes / shots,
        "probability_zero_ci95_wilson": [lo, hi],
        "ideal_probability_zero": 0.5,
        "z_basis_note": "Z-only outcomes are 50/50 for both coherent |+> and an incoherent 50/50 mixture; this arm is a balanced-outcome sampler",
        "h_then_z_control": {
            "description": "Apply H then measure Z. Ideal |+> yields P(1)=0; incoherent 50/50 mixture stays ~50/50.",
            "ideal_plus_one_count": ideal_ones,
            "ideal_plus_probability_one_estimate": ideal_ones / shots,
            "ideal_plus_probability_one_ci95_wilson": [ideal_lo, ideal_hi],
            "ideal_plus_probability_one_target": 0.0,
            "mixture_one_count": mixture_ones,
            "mixture_probability_one_estimate": mixture_ones / shots,
            "mixture_probability_one_ci95_wilson": [mix_lo, mix_hi],
            "mixture_probability_one_target": 0.5,
        },
    }
