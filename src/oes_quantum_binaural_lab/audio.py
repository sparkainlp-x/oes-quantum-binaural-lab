"""Digital stereo loopback: synthetic in-memory multitone calibration lane.

Classical digital simulation only. This intentionally does not access an audio
device or play sound. It synthesizes multitone signals in memory and measures
the known digital settings after a simulated loopback with delay, leakage,
noise, and clipping. Not analog hardware calibration.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import random
from typing import Sequence


@dataclass(frozen=True)
class AudioSettings:
    sample_rate_hz: int = 48_000
    frames: int = 4096
    left_level: float = 0.62
    right_level: float = 0.48
    left_phase_rad: float = 0.08
    right_phase_rad: float = -0.22
    right_delay_samples: int = 3
    crosstalk: float = 0.035
    noise_std: float = 0.001
    clip_threshold: float = 0.95

    def validate(self) -> None:
        if self.sample_rate_hz < 8000 or self.frames < 1024:
            raise ValueError("sample rate must be >=8000 Hz and frames >=1024")
        if not 0.0 <= self.left_level <= 4.0 or not 0.0 <= self.right_level <= 4.0:
            raise ValueError("levels must be in 0..4")
        if abs(self.left_phase_rad) > 2 * math.pi or abs(self.right_phase_rad) > 2 * math.pi:
            raise ValueError("phase must be within +/-2pi radians")
        if abs(self.right_delay_samples) > 64:
            raise ValueError("delay must be within +/-64 samples")
        max_safe = max_unambiguous_delay_samples(self.frames, RIGHT_BINS)
        if abs(self.right_delay_samples) > max_safe:
            raise ValueError(
                f"unsafe frame/delay combination: |delay|={abs(self.right_delay_samples)} samples "
                f"with frames={self.frames} aliases phase unwrapping for bins {RIGHT_BINS}; "
                f"max unambiguous |delay| is {max_safe} samples"
            )
        if not 0.0 <= self.crosstalk <= 0.5 or not 0.0 <= self.noise_std <= 0.1:
            raise ValueError("crosstalk must be 0..0.5 and noise standard deviation 0..0.1")
        if not 0.05 <= self.clip_threshold <= 1.0:
            raise ValueError("clip threshold must be in 0.05..1.0")


LEFT_BINS = (11, 23, 37)
RIGHT_BINS = (17, 31, 47)


def max_unambiguous_delay_samples(frames: int, bins: Sequence[int] = RIGHT_BINS) -> int:
    """Largest |delay| whose consecutive-bin phase steps stay within (-π, π].

    Phase-unwrapping delay estimation aliases when |delay| * 2π * Δk / frames
    exceeds π for any consecutive analysis-bin spacing Δk.
    """
    if frames < 2 or len(bins) < 2:
        return 0
    spacings = [bins[i + 1] - bins[i] for i in range(len(bins) - 1)]
    max_spacing = max(abs(s) for s in spacings)
    if max_spacing <= 0:
        return 0
    return frames // (2 * max_spacing)


def _tone_coefficients(signal: Sequence[float], bin_number: int) -> tuple[float, float, float]:
    n = len(signal)
    c_sin = c_cos = 0.0
    for i, sample in enumerate(signal):
        phase = 2.0 * math.pi * bin_number * i / n
        c_sin += sample * math.sin(phase)
        c_cos += sample * math.cos(phase)
    c_sin *= 2.0 / n
    c_cos *= 2.0 / n
    amplitude = math.hypot(c_sin, c_cos)
    phase = math.atan2(c_cos, c_sin)
    return amplitude, phase, c_sin


def _unwrap(phases: Sequence[float]) -> list[float]:
    if not phases:
        return []
    output = [phases[0]]
    for phase in phases[1:]:
        value = phase
        while value - output[-1] > math.pi:
            value -= 2 * math.pi
        while value - output[-1] < -math.pi:
            value += 2 * math.pi
        output.append(value)
    return output


def _linear_fit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    return slope, ybar - slope * xbar


def _wrap_phase(value: float) -> float:
    return (value + math.pi) % (2 * math.pi) - math.pi


def run_stereo_calibration(settings: AudioSettings | None = None, seed: int = 9281) -> dict:
    settings = settings or AudioSettings()
    settings.validate()
    n = settings.frames
    rng = random.Random(seed)
    left_raw: list[float] = []
    right_raw: list[float] = []
    for i in range(n):
        left = sum(math.sin(2 * math.pi * k * i / n + settings.left_phase_rad) for k in LEFT_BINS) / len(LEFT_BINS)
        right_index = i - settings.right_delay_samples
        right = sum(
            math.sin(2 * math.pi * k * right_index / n + settings.right_phase_rad)
            for k in RIGHT_BINS
        ) / len(RIGHT_BINS)
        source_l = settings.left_level * left
        source_r = settings.right_level * right
        left_raw.append(source_l + settings.crosstalk * source_r + rng.gauss(0.0, settings.noise_std))
        right_raw.append(source_r + settings.crosstalk * source_l + rng.gauss(0.0, settings.noise_std))

    clipped_l = [max(-settings.clip_threshold, min(settings.clip_threshold, x)) for x in left_raw]
    clipped_r = [max(-settings.clip_threshold, min(settings.clip_threshold, x)) for x in right_raw]
    clipped_count = sum(abs(x) > settings.clip_threshold for x in left_raw + right_raw)

    left_coeffs = [_tone_coefficients(clipped_l, k) for k in LEFT_BINS]
    right_coeffs = [_tone_coefficients(clipped_r, k) for k in RIGHT_BINS]
    left_leak_coeffs = [_tone_coefficients(clipped_l, k)[0] for k in RIGHT_BINS]
    right_leak_coeffs = [_tone_coefficients(clipped_r, k)[0] for k in LEFT_BINS]
    estimated_left = sum(a for a, _, _ in left_coeffs) / len(left_coeffs) * len(LEFT_BINS)
    estimated_right = sum(a for a, _, _ in right_coeffs) / len(right_coeffs) * len(RIGHT_BINS)

    left_phases = _unwrap([p for _, p, _ in left_coeffs])
    right_phases = _unwrap([p for _, p, _ in right_coeffs])
    left_phase_est = sum(left_phases) / len(left_phases)
    omega = [2 * math.pi * k / n for k in RIGHT_BINS]
    delay_slope, right_phase_est = _linear_fit(omega, right_phases)
    estimated_delay = -delay_slope

    # Crosstalk for a direction needs a non-zero reference on the source channel.
    ref_right = estimated_right / len(RIGHT_BINS)
    ref_left = estimated_left / len(LEFT_BINS)
    if settings.right_level == 0.0 or ref_right <= 0.0:
        leakage_lr = None
    else:
        leakage_lr = sum(left_leak_coeffs) / len(left_leak_coeffs) / ref_right
    if settings.left_level == 0.0 or ref_left <= 0.0:
        leakage_rl = None
    else:
        leakage_rl = sum(right_leak_coeffs) / len(right_leak_coeffs) / ref_left
    if leakage_lr is None or leakage_rl is None:
        estimated_leakage = None
        crosstalk_abs_error = None
    else:
        estimated_leakage = (leakage_lr + leakage_rl) / 2
        crosstalk_abs_error = abs(estimated_leakage - settings.crosstalk)

    level_l_error = estimated_left - settings.left_level
    level_r_error = estimated_right - settings.right_level
    phase_l_error = _wrap_phase(left_phase_est - settings.left_phase_rad)
    phase_r_error = _wrap_phase(right_phase_est - settings.right_phase_rad)
    delay_error = estimated_delay - settings.right_delay_samples
    return {
        "scope": "digital stereo loopback (synthetic in-memory); no audio interface, DAC, ADC, or physical measurement used",
        "playback": "disabled; samples remain in memory",
        "settings": asdict(settings),
        "recovery": {
            "estimated_left_level": estimated_left,
            "estimated_right_level": estimated_right,
            "left_level_error": level_l_error,
            "right_level_error": level_r_error,
            "left_phase_error_rad": phase_l_error,
            "left_phase_error_deg": math.degrees(phase_l_error),
            "right_phase_error_rad": phase_r_error,
            "right_phase_error_deg": math.degrees(phase_r_error),
            "estimated_right_delay_samples": estimated_delay,
            "delay_error_samples": delay_error,
            "delay_error_microseconds": delay_error * 1_000_000 / settings.sample_rate_hz,
            "estimated_crosstalk_left_from_right": leakage_lr,
            "estimated_crosstalk_right_from_left": leakage_rl,
            "estimated_crosstalk": estimated_leakage,
            "crosstalk_abs_error": crosstalk_abs_error,
            "clipped_sample_count_across_channels": clipped_count,
            "clipped_fraction": clipped_count / (2 * n),
            "peak_before_clipping": max(max(abs(x) for x in left_raw), max(abs(x) for x in right_raw)),
        },
        "limitations": [
            "digital stereo loopback only; not analog hardware calibration",
            "physical calibration requires a specified audio interface and measured physical loopback",
            "clipping flags are measured against the configured digital ceiling",
            "crosstalk for a direction is unavailable (null) when that direction's reference channel level is zero",
        ],
    }
