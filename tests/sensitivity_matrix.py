"""Sensitivity matrix — brute-force slider validation.

For each eTransform × each parameter × each step value × each fixture:
  - Run process() with one parameter varied from baseline
  - Measure delta in alpha, beta, pulse_frequency outputs (L2 norm)
  - Record to CSV

Usage:
    python tests/sensitivity_matrix.py
    python tests/sensitivity_matrix.py --out results/sensitivity.csv
    python tests/sensitivity_matrix.py --steps 8 --fixtures tests/fixtures/

Results feed into tests/sensitivity_analysis.ipynb for EDA.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# Ensure project root is importable
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from cli import BUILTIN_PRESETS, get_default_config, get_preset, load_file, process

# ---------------------------------------------------------------------------
# Parameters to vary — (config_path, min, max, n_steps)
# config_path is dot-notation into the config dict
# ---------------------------------------------------------------------------

PARAMETERS = [
    # Alpha/beta generation
    ("alpha_beta_generation.min_distance_from_center",  0.05, 0.60, 10),
    ("alpha_beta_generation.points_per_second",         10,   50,    6),
    ("alpha_beta_generation.speed_threshold_percent",   20,   80,    6),
    # Frequency
    ("frequency.frequency_ramp_combine_ratio",          0.5,  10.0, 10),
    ("frequency.pulse_frequency_combine_ratio",         0.5,  10.0,  8),
    ("frequency.pulse_freq_min",                        0.1,   0.7,  7),
    ("frequency.pulse_freq_max",                        0.5,   1.0,  6),
    # Pulse
    ("pulse.pulse_width_min",                           0.0,   0.5,  6),
    ("pulse.pulse_width_max",                           0.2,   0.9,  8),
    ("pulse.pulse_rise_min",                            0.0,   0.5,  6),
    ("pulse.pulse_rise_max",                            0.1,   1.0,  8),
    ("pulse.pulse_rise_combine_ratio",                  1.0,   5.0,  5),
]

# Output channels we measure delta on
MEASURE_CHANNELS = ("alpha", "beta", "pulse_frequency")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_nested(d: dict, dot_path: str, value) -> dict:
    """Return a deep copy of d with dot_path set to value."""
    result = copy.deepcopy(d)
    keys = dot_path.split(".")
    node = result
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return result


def _load_channel(path: Path) -> np.ndarray:
    """Load a funscript output and return y values as float32 array."""
    data = load_file(str(path))
    return np.asarray(data["y"], dtype=np.float32)


def _run_and_measure(input_path: str, config: dict, baseline_channels: dict) -> dict[str, float]:
    """Process with config, return delta per channel vs baseline."""
    result = process(input_path, config=config)
    outputs = result.get("outputs", {})
    deltas = {}
    for ch in MEASURE_CHANNELS:
        if ch in outputs and ch in baseline_channels:
            arr = _load_channel(Path(outputs[ch]))
            baseline = baseline_channels[ch]
            # Trim to same length in case of rounding
            n = min(len(arr), len(baseline))
            deltas[ch] = float(np.linalg.norm(arr[:n] - baseline[:n]))
        else:
            deltas[ch] = 0.0
    return deltas


def _get_baseline(input_path: str, config: dict) -> dict[str, np.ndarray]:
    """Run once to get baseline channel arrays."""
    result = process(input_path, config=config)
    outputs = result.get("outputs", {})
    channels = {}
    for ch in MEASURE_CHANNELS:
        if ch in outputs:
            channels[ch] = _load_channel(Path(outputs[ch]))
    return channels


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(fixtures: list[Path], out_path: Path, n_steps_override: int | None = None):
    rows = []
    total_steps = sum(n_steps_override or n for _, _, _, n in PARAMETERS)
    total_runs = len(BUILTIN_PRESETS) * len(fixtures) * total_steps
    run_count = 0
    t0 = time.time()

    print("=" * 70)
    print("SENSITIVITY MATRIX — what does each slider actually do?")
    print("=" * 70)
    print(f"Plan: {len(BUILTIN_PRESETS)} eTransforms × {len(fixtures)} fixtures × "
          f"{len(PARAMETERS)} parameters × ~{total_steps // len(PARAMETERS)} steps each")
    print(f"Total runs: ~{total_runs}")
    print(f"Output: {out_path}")
    print()
    print("How to read the output:")
    print("  delta_alpha/beta/pulse = L2 norm of (varied output − baseline output)")
    print("  delta_mean = average across all three channels")
    print("  High delta = this parameter moves the needle")
    print("  Zero delta = this parameter does nothing for this eTransform")
    print("=" * 70)

    for preset_idx, preset_name in enumerate(BUILTIN_PRESETS, 1):
        base_config = get_preset(preset_name)
        print(f"\n{'─'*60}")
        print(f"eTransform {preset_idx}/{len(BUILTIN_PRESETS)}: {preset_name}")
        print(f"  Character: {BUILTIN_PRESETS[preset_name]['description']}")
        print(f"{'─'*60}")

        for fixture in fixtures:
            input_path = str(fixture)
            print(f"\n  Fixture: {fixture.name}")
            print(f"  Step 1: Running baseline (no changes) to get reference output...")
            baseline = _get_baseline(input_path, base_config)
            channels_found = list(baseline.keys())
            print(f"  Baseline done. Measuring channels: {channels_found}")
            print(f"  Step 2: Varying each parameter across its range...")
            print()

            for param_idx, (dot_path, p_min, p_max, n_steps) in enumerate(PARAMETERS, 1):
                steps = n_steps_override or n_steps
                values = np.linspace(p_min, p_max, steps)
                param_short = dot_path.split(".")[-1]
                print(f"  [{param_idx:2d}/{len(PARAMETERS)}] {param_short:<35} "
                      f"range [{p_min}→{p_max}] in {steps} steps", flush=True)

                step_deltas = []
                for val in values:
                    config = _set_nested(base_config, dot_path, float(val))
                    try:
                        deltas = _run_and_measure(input_path, config, baseline)
                    except Exception as e:
                        print(f"       ERROR at value={val:.3f}: {e}")
                        deltas = {ch: 0.0 for ch in MEASURE_CHANNELS}

                    step_deltas.append(deltas.get("delta_mean", 0.0)
                                       if "delta_mean" in deltas
                                       else np.mean([deltas.get(ch, 0.0) for ch in MEASURE_CHANNELS]))

                    row = {
                        "etransform": preset_name,
                        "parameter": dot_path,
                        "value": round(float(val), 4),
                        "fixture": fixture.name,
                        "delta_alpha": round(deltas.get("alpha", 0.0), 4),
                        "delta_beta": round(deltas.get("beta", 0.0), 4),
                        "delta_pulse": round(deltas.get("pulse_frequency", 0.0), 4),
                        "delta_mean": round(
                            np.mean([deltas.get(ch, 0.0) for ch in MEASURE_CHANNELS]), 4
                        ),
                    }
                    rows.append(row)
                    run_count += 1

                    elapsed = time.time() - t0
                    rate = run_count / elapsed if elapsed > 0 else 0
                    run_count += 1
                    rows.append(row)

                # Per-parameter summary after all steps
                max_delta = max(step_deltas) if step_deltas else 0.0
                verdict = (
                    "SIGNIFICANT ✓" if max_delta > 50
                    else "moderate" if max_delta > 10
                    else "low" if max_delta > 1
                    else "DEAD — no effect"
                )
                elapsed = time.time() - t0
                rate = run_count / elapsed if elapsed > 0 else 0
                print(f"       max delta={max_delta:.1f}  → {verdict}  "
                      f"[{run_count}/{total_runs} runs, {rate:.1f}/s]")

    print()
    print("=" * 70)
    print("ALL RUNS COMPLETE")
    print("=" * 70)

    # Write CSV
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["etransform", "parameter", "value", "fixture",
                  "delta_alpha", "delta_beta", "delta_pulse", "delta_mean"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. {run_count} runs in {time.time()-t0:.1f}s")
    print(f"Results: {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sensitivity matrix — brute-force slider validation")
    parser.add_argument("--out", default="tests/results/sensitivity.csv", help="Output CSV path")
    parser.add_argument("--steps", type=int, default=None, help="Override steps per parameter")
    parser.add_argument("--fixtures", default="tests/fixtures", help="Fixtures directory")
    parser.add_argument("--fixture", nargs="*", help="Specific fixture file(s)")
    args = parser.parse_args()

    fixtures_dir = Path(args.fixtures)
    if args.fixture:
        fixtures = [Path(f) for f in args.fixture]
    else:
        fixtures = sorted(fixtures_dir.glob("*.funscript"))

    if not fixtures:
        print(f"No fixtures found in {fixtures_dir}")
        sys.exit(1)

    run(fixtures, Path(args.out), args.steps)
