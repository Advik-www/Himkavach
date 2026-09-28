"""Test verification for sample-day plot generation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from experiments.phase2a.generate_sample_plots import generate_all_sample_plots


def test_sample_plots_generated_and_valid():
    """Verify that all Phase 2A validation plots exist and are non-empty PNG files."""
    out_dir = Path("experiments/phase2a")
    winter_img = out_dir / "winter_day.png"
    summer_img = out_dir / "summer_day.png"
    comp_img = out_dir / "sample_days_comparison.png"

    # Ensure files exist (generate if not already present)
    if not (winter_img.exists() and summer_img.exists() and comp_img.exists()):
        generate_all_sample_plots()

    for path in [winter_img, summer_img, comp_img]:
        assert path.exists(), f"Missing expected plot: {path}"
        # File should be a non-trivial PNG (> 50 KB)
        size = path.stat().st_size
        assert size > 50000, f"Plot file {path} suspiciously small: {size} bytes"

        # Verify PNG header magic bytes
        with open(path, "rb") as f:
            header = f.read(8)
            assert header == b"\x89PNG\r\n\x1a\n", f"Invalid PNG magic bytes in {path}"
