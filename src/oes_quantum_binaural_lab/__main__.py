"""CLI entry point: python -m oes_quantum_binaural_lab"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .app import LabConfig, run_lab
from .audio import AudioSettings
from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline OES / quantum / binaural simulation prototype")
    parser.add_argument("--serve", action="store_true", help="start the loopback-only browser dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="server host (loopback only)")
    parser.add_argument("--port", type=int, default=8765, help="local dashboard port")
    parser.add_argument("--pairs", type=int, default=512, help="independent Bell-pair systems, 1..512")
    parser.add_argument("--cal-shots-per-state", type=int, default=64, help="known-preparation calibration shots per outcome, per pair")
    parser.add_argument("--sweep", default="4,8,16", help="comma-separated evaluation shots per pair per setting, each 1..128")
    parser.add_argument("--seed", type=int, default=1731, help="deterministic simulation seed")
    parser.add_argument("--json", dest="json_path", help="also write the full report to this path")
    parser.add_argument("--left-level", type=float, default=0.62)
    parser.add_argument("--right-level", type=float, default=0.48)
    parser.add_argument("--left-phase", type=float, default=0.08, help="radians")
    parser.add_argument("--right-phase", type=float, default=-0.22, help="radians")
    parser.add_argument("--delay-samples", type=int, default=3)
    parser.add_argument("--crosstalk", type=float, default=0.035)
    parser.add_argument("--noise", type=float, default=0.001)
    parser.add_argument("--clip-threshold", type=float, default=0.95)
    args = parser.parse_args()
    if args.serve:
        serve(args.host, args.port)
        return
    try:
        sweep = tuple(int(x.strip()) for x in args.sweep.split(",") if x.strip())
        config = LabConfig(
            pair_count=args.pairs,
            calibration_shots_per_state=args.cal_shots_per_state,
            sweep_shots_per_pair=sweep,
            seed=args.seed,
            audio=AudioSettings(
                left_level=args.left_level,
                right_level=args.right_level,
                left_phase_rad=args.left_phase,
                right_phase_rad=args.right_phase,
                right_delay_samples=args.delay_samples,
                crosstalk=args.crosstalk,
                noise_std=args.noise,
                clip_threshold=args.clip_threshold,
            ),
        )
        report = run_lab(config)
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Full report written to {path}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
