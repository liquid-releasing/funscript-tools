"""
cli.py — Adapter layer for funscript-tools.

This is the ONLY file that imports from the upstream processing engine.
All other code (UI, tests, API) imports from here only.

Processing engine by edger477: https://github.com/edger477/funscript-tools
All algorithm credit belongs to edger477 and contributors.

Usage (command line):
    python cli.py process path/to/file.funscript
    python cli.py process path/to/file.funscript --output-dir /some/dir
    python cli.py info path/to/file.funscript
    python cli.py list-outputs path/to/dir stem_name

Usage (Python):
    from cli import load_file, process, get_default_config
    from cli import preview_electrode_path, preview_frequency_blend, preview_pulse_shape
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Optional

import numpy as np

# ── Upstream imports (isolated here) ─────────────────────────────────────────
# Everything upstream lives behind this boundary.

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))


def _upstream_load(path: Path):
    """Load a funscript via the upstream Funscript class."""
    from funscript import Funscript  # upstream
    return Funscript.from_file(path)


def _upstream_process(input_path: Path, config: dict, on_progress=None) -> bool:
    """Run the upstream RestimProcessor pipeline."""
    from processor import RestimProcessor  # upstream
    proc = RestimProcessor(config)
    return proc.process(str(input_path), on_progress)


def _upstream_default_config() -> dict:
    """Return upstream default config."""
    from config import DEFAULT_CONFIG  # upstream
    import copy
    return copy.deepcopy(DEFAULT_CONFIG)


def _upstream_preview_path(algorithm: str, min_distance: float,
                            speed_threshold: float, n_points: int):
    """Generate a 2D electrode path using a synthetic sine input."""
    from funscript import Funscript  # upstream
    from processing.speed_processing import convert_to_speed  # upstream
    from processing.funscript_1d_to_2d import generate_alpha_beta_from_main  # upstream

    # Synthetic sinusoidal funscript (2 seconds, representative motion)
    t = np.linspace(0, 2.0, n_points)
    y = (np.sin(2 * np.pi * 1.5 * t) + 1) / 2  # 0-1 range, 1.5 Hz
    synth = Funscript(t.tolist(), y.tolist())

    speed = convert_to_speed(synth, window_size=5, interpolation_interval=0.05)

    alpha, beta = generate_alpha_beta_from_main(
        synth, speed,
        points_per_second=25,
        algorithm=algorithm,
        min_distance_from_center=min_distance,
        speed_threshold_percent=speed_threshold,
    )
    return alpha.y, beta.y  # Both are 0-1 floats


# ── Public API ────────────────────────────────────────────────────────────────

ALGORITHMS = {
    "circular":        "Circular (0°–180°)",
    "top-right-left":  "Top-Right-Bottom-Left (0°–270°)",
    "top-left-right":  "Top-Left-Bottom-Right (0°–90°)",
    "restim-original": "Restim Original (0°–360°)",
}

ALGORITHM_DESCRIPTIONS = {
    "circular":        "Smooth semi-circle. Balanced, works well for most content.",
    "top-right-left":  "Wider arc. More variation, stronger contrast between strokes.",
    "top-left-right":  "Narrower arc. Subtle, good for slower content.",
    "restim-original": "Full circle with random direction changes. Most unpredictable.",
}


def load_file(path: str) -> dict:
    """
    Load a .funscript file and return metadata + waveform data.

    Returns:
        {
            name: str,
            path: str,
            actions: int,
            duration_s: float,
            duration_fmt: str,    # "MM:SS"
            pos_min: float,       # 0–100
            pos_max: float,       # 0–100
            x: list[float],       # time in seconds
            y: list[float],       # position 0–100
        }
    Raises:
        ValueError if the file cannot be loaded.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"File not found: {path}")
    if p.suffix.lower() != ".funscript":
        raise ValueError(f"Expected a .funscript file, got: {p.suffix}")

    try:
        fs = _upstream_load(p)
    except Exception as e:
        raise ValueError(f"Failed to read {p.name}: {e}") from e

    x = [float(v) for v in fs.x]
    y = [float(v) * 100 for v in fs.y]  # Convert 0-1 → 0-100
    duration = x[-1] if x else 0.0
    m, s = int(duration // 60), int(duration % 60)

    return {
        "name": p.name,
        "path": str(p),
        "actions": len(x),
        "duration_s": duration,
        "duration_fmt": f"{m:02d}:{s:02d}",
        "pos_min": round(min(y), 1) if y else 0.0,
        "pos_max": round(max(y), 1) if y else 0.0,
        "x": x,
        "y": y,
    }


def get_default_config() -> dict:
    """Return the default processing configuration."""
    return _upstream_default_config()


def process(path: str, config: dict, on_progress: Optional[Callable] = None) -> dict:
    """
    Run the full processing pipeline on a .funscript file.

    on_progress: optional callback(percent: int, message: str)

    Returns:
        {
            success: bool,
            error: str | None,
            outputs: list[{ suffix: str, path: str, size_bytes: int }]
        }
    """
    p = Path(path)

    try:
        success = _upstream_process(p, config, on_progress)
    except Exception as e:
        return {"success": False, "error": str(e), "outputs": []}

    if not success:
        return {"success": False, "error": "Processing failed — check logs.", "outputs": []}

    # Determine output directory
    custom = config.get("advanced", {}).get("custom_output_directory", "").strip()
    out_dir = Path(custom) if custom else p.parent

    outputs = list_outputs(str(out_dir), p.stem)
    return {"success": True, "error": None, "outputs": outputs}


def list_outputs(directory: str, stem: str) -> list[dict]:
    """
    Find all generated output files for a given stem in a directory.

    Returns:
        list of { suffix: str, path: str, size_bytes: int }
    """
    d = Path(directory)
    if not d.exists():
        return []

    results = []
    for p in sorted(d.glob(f"{stem}.*.funscript")):
        suffix = p.name[len(stem) + 1: -len(".funscript")]
        results.append({
            "suffix": suffix,
            "path": str(p),
            "size_bytes": p.stat().st_size,
        })
    return results


# ── Preview functions (no file I/O, safe to call on every slider move) ────────

def preview_electrode_path(
    algorithm: str = "circular",
    min_distance_from_center: float = 0.1,
    speed_threshold_percent: float = 50.0,
    points: int = 200,
) -> dict:
    """
    Return the 2D electrode path shape for visualization.

    Uses a synthetic sinusoidal input so shape depends only on the algorithm
    and parameters — no real funscript needed.

    Returns:
        {
            alpha: list[float],   # x-axis values 0–1
            beta:  list[float],   # y-axis values 0–1
            label: str,           # algorithm display name
            description: str,     # plain-language description
        }
    """
    try:
        alpha_y, beta_y = _upstream_preview_path(
            algorithm,
            min_distance_from_center,
            speed_threshold_percent,
            points,
        )
        return {
            "alpha": [float(v) for v in alpha_y],
            "beta":  [float(v) for v in beta_y],
            "label": ALGORITHMS.get(algorithm, algorithm),
            "description": ALGORITHM_DESCRIPTIONS.get(algorithm, ""),
        }
    except Exception as e:
        # Return a fallback circle so the UI never crashes
        t = np.linspace(0, np.pi, points)
        return {
            "alpha": (0.5 + 0.4 * np.cos(t)).tolist(),
            "beta":  (0.5 + 0.4 * np.sin(t)).tolist(),
            "label": ALGORITHMS.get(algorithm, algorithm),
            "description": f"Preview unavailable: {e}",
        }


def preview_frequency_blend(
    frequency_ramp_combine_ratio: float = 2.0,
    pulse_frequency_combine_ratio: float = 3.0,
) -> dict:
    """
    Return plain-language description of the frequency blend settings.

    The combine ratio R means: (R-1)/R of the first source + 1/R of the second.

    Returns:
        {
            frequency_ramp_pct:   float,  # % from ramp (slow build)
            frequency_speed_pct:  float,  # % from speed (action intensity)
            pulse_speed_pct:      float,  # % from speed in pulse freq
            pulse_alpha_pct:      float,  # % from alpha in pulse freq
            frequency_label:      str,    # "70% slow build + 30% scene energy"
            pulse_label:          str,
            overall_label:        str,    # summary sentence
        }
    """
    def split(ratio):
        r = max(1.0, float(ratio))
        left = round((r - 1) / r * 100, 1)
        right = round(100 - left, 1)
        return left, right

    ramp_pct, speed_pct = split(frequency_ramp_combine_ratio)
    pulse_speed_pct, pulse_alpha_pct = split(pulse_frequency_combine_ratio)

    freq_label = f"{ramp_pct:.0f}% slow build + {speed_pct:.0f}% scene energy"
    pulse_label = f"{pulse_speed_pct:.0f}% scene energy + {pulse_alpha_pct:.0f}% spatial position"

    if ramp_pct >= 60:
        character = "gradual, builds slowly"
    elif speed_pct >= 60:
        character = "reactive, follows action closely"
    else:
        character = "balanced — responsive with a slow build"

    return {
        "frequency_ramp_pct":  ramp_pct,
        "frequency_speed_pct": speed_pct,
        "pulse_speed_pct":     pulse_speed_pct,
        "pulse_alpha_pct":     pulse_alpha_pct,
        "frequency_label":     freq_label,
        "pulse_label":         pulse_label,
        "overall_label":       f"Frequency feel: {character}",
    }


def preview_pulse_shape(
    width_min: float = 0.1,
    width_max: float = 0.45,
    rise_min: float = 0.0,
    rise_max: float = 0.80,
) -> dict:
    """
    Return a representative pulse silhouette for visualization.

    Generates a trapezoidal pulse at the midpoint of the configured ranges,
    showing the relationship between width and rise time.

    Returns:
        {
            x: list[float],   # normalized time 0–1
            y: list[float],   # normalized amplitude 0–1
            width: float,     # midpoint width used
            rise:  float,     # midpoint rise time used
            label: str,       # plain-language description
            sharpness: str,   # "sharp" / "medium" / "soft"
        }
    """
    width = (width_min + width_max) / 2
    rise = (rise_min + rise_max) / 2

    # Build trapezoidal pulse: rise → hold → fall
    # Normalized to 0-1 time window
    rise_frac = min(rise, width / 2)   # Can't rise longer than half the pulse
    hold_frac = width - 2 * rise_frac
    fall_frac = rise_frac
    gap_frac = 1.0 - width

    x = [0.0,
         rise_frac,
         rise_frac + hold_frac,
         rise_frac + hold_frac + fall_frac,
         rise_frac + hold_frac + fall_frac + gap_frac]
    y = [0.0, 1.0, 1.0, 0.0, 0.0]

    if rise < 0.1:
        sharpness = "sharp — immediate onset"
    elif rise < 0.4:
        sharpness = "medium — smooth ramp"
    else:
        sharpness = "soft — gentle build"

    width_desc = "narrow" if width < 0.2 else ("wide" if width > 0.35 else "medium")
    label = f"Pulse: {width_desc} width, {sharpness}"

    return {
        "x": x,
        "y": y,
        "width": round(width, 3),
        "rise": round(rise, 3),
        "label": label,
        "sharpness": sharpness.split(" — ")[0],
    }


def preview_output(
    source: dict,
    config: dict,
    output_type: str = "alpha",
) -> dict:
    """
    Run a lightweight partial pipeline to preview one output type.

    Faster than full process() — skips file I/O, returns array data only.
    Best effort: falls back gracefully if the output type isn't computable.

    Returns:
        {
            original_x: list[float],
            original_y: list[float],   # 0–100
            output_x:   list[float],
            output_y:   list[float],   # 0–100
            label:      str,
            available:  bool,
        }
    """
    base = {
        "original_x": source.get("x", []),
        "original_y": source.get("y", []),
        "output_x": [],
        "output_y": [],
        "label": output_type,
        "available": False,
    }

    try:
        from funscript import Funscript  # upstream
        from processing.speed_processing import convert_to_speed  # upstream

        x = np.array(source["x"])
        y = np.array(source["y"]) / 100.0  # back to 0-1
        main_fs = Funscript(x.tolist(), y.tolist())

        ab_cfg = config.get("alpha_beta_generation", {})
        speed_fs = convert_to_speed(
            main_fs,
            config["general"]["speed_window_size"],
            config["speed"]["interpolation_interval"],
        )

        if output_type in ("alpha", "beta"):
            from processing.funscript_1d_to_2d import generate_alpha_beta_from_main  # upstream
            alpha, beta = generate_alpha_beta_from_main(
                main_fs, speed_fs,
                points_per_second=ab_cfg.get("points_per_second", 25),
                algorithm=ab_cfg.get("algorithm", "circular"),
                min_distance_from_center=ab_cfg.get("min_distance_from_center", 0.1),
                speed_threshold_percent=ab_cfg.get("speed_threshold_percent", 50),
            )
            out = alpha if output_type == "alpha" else beta

        elif output_type == "speed":
            out = speed_fs

        elif output_type == "frequency":
            from processing.combining import combine_funscripts  # upstream
            from processing.special_generators import make_volume_ramp  # upstream
            ramp = make_volume_ramp(main_fs, config.get("volume", {}).get("ramp_percent_per_hour", 15))
            out = combine_funscripts(ramp, speed_fs, config["frequency"]["frequency_ramp_combine_ratio"])

        elif output_type == "volume":
            from processing.combining import combine_funscripts  # upstream
            from processing.special_generators import make_volume_ramp  # upstream
            ramp = make_volume_ramp(main_fs, config.get("volume", {}).get("ramp_percent_per_hour", 15))
            out = combine_funscripts(
                ramp, speed_fs,
                config["volume"]["volume_ramp_combine_ratio"],
                config["general"]["rest_level"],
                config["general"]["ramp_up_duration_after_rest"],
            )

        else:
            base["label"] = f"{output_type} (preview not available — run Process)"
            return base

        base["output_x"] = [float(v) for v in out.x]
        base["output_y"] = [float(v) * 100 for v in out.y]
        base["available"] = True
        base["label"] = output_type

    except Exception as e:
        base["label"] = f"{output_type} (preview error: {e})"

    return base


# ── Command-line interface ─────────────────────────────────────────────────────

def _cmd_info(args):
    try:
        info = load_file(args.file)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"File:     {info['name']}")
    print(f"Actions:  {info['actions']}")
    print(f"Duration: {info['duration_fmt']}")
    print(f"Range:    {info['pos_min']:.0f} – {info['pos_max']:.0f}")


def _cmd_process(args):
    config = get_default_config()

    if args.config:
        with open(args.config) as f:
            overrides = json.load(f)
        _deep_merge(config, overrides)

    if args.output_dir:
        config.setdefault("advanced", {})["custom_output_directory"] = args.output_dir

    def _progress(pct, msg):
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r[{bar}] {pct:3d}%  {msg:<50}", end="", flush=True)

    print(f"Processing: {args.file}")
    result = process(args.file, config, _progress)
    print()  # newline after progress bar

    if not result["success"]:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\nGenerated {len(result['outputs'])} file(s):")
    for out in result["outputs"]:
        size_kb = out["size_bytes"] / 1024
        print(f"  {out['suffix']:<30} {size_kb:.1f} KB  →  {out['path']}")


def _cmd_list_outputs(args):
    outputs = list_outputs(args.directory, args.stem)
    if not outputs:
        print(f"No outputs found for '{args.stem}' in {args.directory}")
        return
    for out in outputs:
        size_kb = out["size_bytes"] / 1024
        print(f"  {out['suffix']:<30} {size_kb:.1f} KB")


def _deep_merge(base: dict, override: dict):
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def main():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="funscript-tools CLI — built on edger477's processing engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # info
    p_info = sub.add_parser("info", help="Show info about a .funscript file")
    p_info.add_argument("file", help="Path to .funscript file")

    # process
    p_proc = sub.add_parser("process", help="Run the full processing pipeline")
    p_proc.add_argument("file", help="Path to .funscript file")
    p_proc.add_argument("--config", help="Path to config JSON file (overrides defaults)")
    p_proc.add_argument("--output-dir", help="Output directory (default: same as input)")

    # list-outputs
    p_list = sub.add_parser("list-outputs", help="List generated output files")
    p_list.add_argument("directory", help="Directory to search")
    p_list.add_argument("stem", help="Input filename stem (without extension)")

    args = parser.parse_args()

    if args.command == "info":
        _cmd_info(args)
    elif args.command == "process":
        _cmd_process(args)
    elif args.command == "list-outputs":
        _cmd_list_outputs(args)


if __name__ == "__main__":
    main()
