#!/usr/bin/env python3
"""Convenience launcher for source-tree use."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
from oes_quantum_binaural_lab.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
