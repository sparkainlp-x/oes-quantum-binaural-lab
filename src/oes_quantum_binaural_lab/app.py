"""Orchestrate independent simulation lanes through the classical event bus."""
from __future__ import annotations

from dataclasses import dataclass
import time
import tracemalloc

from .audio import AudioSettings, run_stereo_calibration
from .bus import EventBus
from .control import build_control_ledger, publish_metric_summary
from .quantum import run_quantum_sandbox


@dataclass(frozen=True)
class LabConfig:
    pair_count: int = 512
    calibration_shots_per_state: int = 64
    sweep_shots_per_pair: tuple[int, ...] = (4, 8, 16)
    seed: int = 1731
    audio: AudioSettings = AudioSettings()


def run_lab(config: LabConfig | None = None) -> dict:
    config = config or LabConfig()
    started = time.perf_counter()
    tracemalloc.start()

    # Each simulator returns its own report to the coordinator. Only scalar
    # reported metrics are published to the shared bus; OES/control reads those
    # timestamped records back from the bus and never receives a lane object.
    quantum_report = run_quantum_sandbox(
        pair_count=config.pair_count,
        calibration_shots_per_state=config.calibration_shots_per_state,
        sweep_shots_per_pair=config.sweep_shots_per_pair,
        seed=config.seed,
    )
    audio_report = run_stereo_calibration(config.audio, seed=config.seed + 701)
    bus = EventBus()

    last = quantum_report["sweep"][-1]
    q_metrics = {
        "pair_count": quantum_report["model"]["pair_count"],
        "qubit_count": quantum_report["model"]["qubit_count"],
        "calibration_shots_total": quantum_report["readout_calibration"]["calibration_shots_total"],
        "held_out_eval_shots_total": last["bell_pair_evaluation_shots_total"],
        "bell_chsh_corrected": last["bell"]["chsh_corrected"],
        "bell_chsh_corrected_ci_low": last["bell"]["chsh_corrected_ci95_conditional_on_calibration"][0],
        "bell_chsh_corrected_ci_high": last["bell"]["chsh_corrected_ci95_conditional_on_calibration"][1],
        "separable_chsh_corrected": last["separable_control"]["chsh_corrected"],
        "superposition_p0": last["superposition"]["probability_zero_estimate"],
    }
    a_recovery = audio_report["recovery"]
    a_metrics = {
        "left_level_error": a_recovery["left_level_error"],
        "right_level_error": a_recovery["right_level_error"],
        "left_phase_error_deg": a_recovery["left_phase_error_deg"],
        "right_phase_error_deg": a_recovery["right_phase_error_deg"],
        "delay_error_samples": a_recovery["delay_error_samples"],
        "crosstalk_abs_error": a_recovery["crosstalk_abs_error"],
        "clipped_fraction": a_recovery["clipped_fraction"],
    }
    publish_metric_summary(bus, "quantum_sandbox", q_metrics)
    publish_metric_summary(bus, "stereo_binaural", a_metrics)
    oes_report = build_control_ledger(bus, capacity=1024)
    elapsed = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    all_events = bus.read()
    return {
        "title": "Classical metrics ledger / Bell-correlation Monte Carlo / digital stereo loopback — local prototype",
        "architecture": {
            "modules": [
                {"lane": "oes_control", "description": "classical metrics ledger: 1,024 scalar slots; not an OES detector; no quantum channels"},
                {"lane": "quantum_sandbox", "description": "Bell-correlation Monte Carlo model; no quantum state/circuit evolution; classical toy simulation"},
                {"lane": "stereo_binaural", "description": "digital stereo loopback; synthetic in-memory calibration; no audio device"},
            ],
            "join": "timestamped classical scalar event bus only",
            "membrane_term": "metaphor only; audio sonification does not entangle sound with qubits",
            "observer_term": "measurement/readout only; no consciousness interpretation",
            "classical_toy_simulation": True,
            "quantum_advantage_claimed": False,
            "hardware_claimed": False,
        },
        "quantum_sandbox": quantum_report,
        "stereo_binaural": audio_report,
        "oes_control": oes_report,
        "resource_use": {
            "elapsed_seconds": elapsed,
            "python_tracemalloc_peak_bytes": peak_bytes,
            "event_count": len(all_events),
            "simulation_only": True,
            "hardware_results": False,
        },
        "event_bus": {
            "timestamped": True,
            "lane_event_counts": {lane: sum(1 for event in all_events if event.lane == lane) for lane in ("oes_control", "quantum_sandbox", "stereo_binaural")},
            "only_scalar_payloads": True,
            "cross_lane_payloads_are_metrics_only": True,
        },
    }
