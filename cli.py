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


def _geometric_preview_path(algorithm: str, min_distance: float, n_points: int):
    """
    Return a clean geometric representation of what each algorithm's path looks like.

    The upstream algorithms converge on synthetic input. This draws the template
    shape directly — which is what users need to understand the algorithm choice.

    Center of electrode space is (0.5, 0.5). Radius scales with min_distance.
    """
    cx, cy = 0.5, 0.5
    r = (0.9 - min_distance) / 2  # radius: shrinks as min_distance grows
    r = max(0.05, min(r, 0.45))

    if algorithm == "circular":
        # Semi-circle: sweeps 0° → 180° (right side to left, arcing upward)
        angles = np.linspace(0, np.pi, n_points)
        alpha = cx + r * np.cos(angles)
        beta  = cy + r * np.sin(angles)

    elif algorithm == "top-right-left":
        # Wide arc: sweeps 0° → 270° (right → top → left → bottom)
        angles = np.linspace(0, 1.5 * np.pi, n_points)
        alpha = cx + r * np.cos(angles)
        beta  = cy + r * np.sin(angles)

    elif algorithm == "top-left-right":
        # Narrow arc: sweeps 0° → 90° (right → top only — subtle quarter circle)
        angles = np.linspace(0, 0.5 * np.pi, n_points)
        alpha = cx + r * np.cos(angles)
        beta  = cy + r * np.sin(angles)

    elif algorithm == "restim-original":
        # Full circle with random direction reversals — shows unpredictability
        rng = np.random.default_rng(42)  # fixed seed so preview is consistent
        angles = np.zeros(n_points)
        direction = 1
        step = 2 * np.pi / (n_points / 3)
        for i in range(1, n_points):
            if rng.random() < 0.12:   # ~12% chance of reversal per step
                direction *= -1
            angles[i] = angles[i-1] + direction * step
        alpha = cx + r * np.cos(angles)
        beta  = cy + r * np.sin(angles)

    else:
        # Fallback: circle
        angles = np.linspace(0, np.pi, n_points)
        alpha = cx + r * np.cos(angles)
        beta  = cy + r * np.sin(angles)

    return alpha.tolist(), beta.tolist()


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


# ── Presets ───────────────────────────────────────────────────────────────────

_USER_PRESETS_PATH = Path.home() / ".config" / "funscript-tools" / "presets.json"

# Built-in presets — curated starting points, not exhaustive configurations.
# Each preset overrides only the creative settings; infrastructure (volume,
# rest level, output mode) stays at defaults unless explicitly set.
BUILTIN_PRESETS: dict[str, dict] = {
    "Gentle": {
        "description": "Soft, slow-building. Good for intimate or slow content.",
        "config": {
            "alpha_beta_generation": {
                "algorithm": "top-left-right",
                "min_distance_from_center": 0.12,
                "points_per_second": 20,
                "speed_threshold_percent": 40,
            },
            "frequency": {
                "frequency_ramp_combine_ratio": 8.0,
                "pulse_frequency_combine_ratio": 6.0,
                "pulse_freq_min": 0.25,
                "pulse_freq_max": 0.70,
            },
            "pulse": {
                "pulse_width_min": 0.30,
                "pulse_width_max": 0.60,
                "pulse_rise_min": 0.50,
                "pulse_rise_max": 0.90,
            },
        },
        "sliders": [
            {
                "cv": "cv_min_dist",
                "label": "Softness",
                "hint": "How far sensation moves from center. Low = barely perceptible flutter. High = wider, more present.",
                "from_": 0.05, "to_": 0.35,
                "min_label": "whisper", "max_label": "noticeable",
            },
            {
                "cv": "cv_pr_max",
                "label": "Onset gentleness",
                "hint": "How softly each pulse starts. High = feather-light onset. Low = cleaner, more defined edge.",
                "from_": 0.40, "to_": 1.0,
                "min_label": "defined", "max_label": "feather",
            },
        ],
    },
    "Reactive": {
        "description": "Sharp, tracks action closely. Good for fast, intense content.",
        "config": {
            "alpha_beta_generation": {
                "algorithm": "top-right-left",
                "min_distance_from_center": 0.18,
                "points_per_second": 30,
                "speed_threshold_percent": 60,
            },
            "frequency": {
                "frequency_ramp_combine_ratio": 2.0,
                "pulse_frequency_combine_ratio": 2.0,
                "pulse_freq_min": 0.50,
                "pulse_freq_max": 0.95,
            },
            "pulse": {
                "pulse_width_min": 0.05,
                "pulse_width_max": 0.25,
                "pulse_rise_min": 0.00,
                "pulse_rise_max": 0.20,
            },
        },
        "sliders": [
            {
                "cv": "cv_freq_ramp_ratio",
                "label": "Reactivity",
                "hint": "How tightly sensation tracks each stroke. Low = instant response. High = adds a slight lag.",
                "from_": 1.0, "to_": 4.0,
                "min_label": "instant", "max_label": "slight lag",
            },
            {
                "cv": "cv_pf_max",
                "label": "Peak intensity",
                "hint": "Maximum pulse rate at peak action. Higher = more intense at climax.",
                "from_": 0.60, "to_": 1.0,
                "min_label": "moderate peak", "max_label": "maximum",
            },
        ],
    },
    "Scene Builder": {
        "description": "Builds gradually over the scene. Works well for longer content with a slow arc.",
        "config": {
            "alpha_beta_generation": {
                "algorithm": "circular",
                "min_distance_from_center": 0.15,
                "points_per_second": 25,
                "speed_threshold_percent": 50,
            },
            "frequency": {
                "frequency_ramp_combine_ratio": 7.0,
                "pulse_frequency_combine_ratio": 5.0,
                "pulse_freq_min": 0.30,
                "pulse_freq_max": 0.85,
            },
            "pulse": {
                "pulse_width_min": 0.15,
                "pulse_width_max": 0.45,
                "pulse_rise_min": 0.20,
                "pulse_rise_max": 0.70,
            },
        },
        "sliders": [
            {
                "cv": "cv_freq_ramp_ratio",
                "label": "Build speed",
                "hint": "How slowly the scene builds. High = very gradual — ignores short spikes, follows the overall arc.",
                "from_": 4.0, "to_": 10.0,
                "min_label": "builds quickly", "max_label": "very slow arc",
            },
            {
                "cv": "cv_min_dist",
                "label": "Arc width",
                "hint": "How wide the circular sweep is. Low = tight circle. High = broad sweep at the peak.",
                "from_": 0.05, "to_": 0.45,
                "min_label": "tight", "max_label": "broad",
            },
        ],
    },
    "Unpredictable": {
        "description": "Random direction changes, varied character. Good for surprise content.",
        "config": {
            "alpha_beta_generation": {
                "algorithm": "restim-original",
                "min_distance_from_center": 0.20,
                "points_per_second": 28,
                "speed_threshold_percent": 55,
            },
            "frequency": {
                "frequency_ramp_combine_ratio": 4.0,
                "pulse_frequency_combine_ratio": 3.0,
                "pulse_freq_min": 0.35,
                "pulse_freq_max": 0.90,
            },
            "pulse": {
                "pulse_width_min": 0.10,
                "pulse_width_max": 0.50,
                "pulse_rise_min": 0.00,
                "pulse_rise_max": 0.60,
            },
        },
        "sliders": [
            {
                "cv": "cv_min_dist",
                "label": "Wildness",
                "hint": "How far the random movement reaches. Low = subtle chaos. High = full-range unpredictability.",
                "from_": 0.10, "to_": 0.50,
                "min_label": "subtle chaos", "max_label": "full range",
            },
            {
                "cv": "cv_pulse_freq_ratio",
                "label": "Pulse variety",
                "hint": "How much the pulse rate varies. Low = speed-driven changes. High = position adds more variation.",
                "from_": 1.0, "to_": 8.0,
                "min_label": "speed only", "max_label": "highly varied",
            },
        ],
    },
    "Balanced": {
        "description": "Middle of everything. A good starting point for any content.",
        "config": {
            "alpha_beta_generation": {
                "algorithm": "circular",
                "min_distance_from_center": 0.15,
                "points_per_second": 25,
                "speed_threshold_percent": 50,
            },
            "frequency": {
                "frequency_ramp_combine_ratio": 5.0,
                "pulse_frequency_combine_ratio": 3.0,
                "pulse_freq_min": 0.40,
                "pulse_freq_max": 0.95,
            },
            "pulse": {
                "pulse_width_min": 0.10,
                "pulse_width_max": 0.45,
                "pulse_rise_min": 0.00,
                "pulse_rise_max": 0.80,
            },
        },
        "sliders": [
            {
                "cv": "cv_min_dist",
                "label": "Sweep width",
                "hint": "How wide the sensation arc is. Low = centered and focused. High = sweeps edge to edge.",
                "from_": 0.05, "to_": 0.50,
                "min_label": "focused", "max_label": "edge to edge",
            },
            {
                "cv": "cv_freq_ramp_ratio",
                "label": "Reactive vs. gradual",
                "hint": "The balance between tracking strokes and building slowly. Low = follows action. High = ignores spikes.",
                "from_": 1.0, "to_": 8.0,
                "min_label": "follows action", "max_label": "slow build",
            },
        ],
    },
}


def list_presets(user_presets_path: Optional[str] = None) -> dict[str, dict]:
    """
    Return all available presets — built-in and user-defined.

    User presets override built-ins with the same name.

    Returns:
        { name: { description, config, builtin: bool } }
    """
    result = {k: {**v, "builtin": True} for k, v in BUILTIN_PRESETS.items()}
    user = load_user_presets(user_presets_path)
    for name, preset in user.items():
        result[name] = {**preset, "builtin": False}
    return result


def get_preset(name: str, user_presets_path: Optional[str] = None) -> dict:
    """
    Get a preset by name. Returns the full config merged with defaults.

    Raises KeyError if not found.
    """
    all_presets = list_presets(user_presets_path)
    if name not in all_presets:
        raise KeyError(f"Preset '{name}' not found. Available: {list(all_presets)}")
    preset_config = all_presets[name]["config"]
    # Deep-merge preset over defaults so missing keys use defaults
    import copy
    config = get_default_config()
    for section, values in preset_config.items():
        if section in config:
            config[section].update(values)
        else:
            config[section] = copy.deepcopy(values)
    return config


def load_user_presets(path: Optional[str] = None) -> dict:
    """Load user-defined presets from disk. Returns {} if file doesn't exist."""
    p = Path(path) if path else _USER_PRESETS_PATH
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_preset(name: str, config: dict, description: str = "",
                path: Optional[str] = None) -> str:
    """
    Save a preset to the user presets file.

    Extracts only the creative settings from config (algorithm, frequency,
    pulse) — not infrastructure settings like volume or output mode.

    Returns the path where presets were saved.
    """
    p = Path(path) if path else _USER_PRESETS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)

    presets = load_user_presets(str(p))

    # Extract only creative settings
    creative_config = {}
    for section in ("alpha_beta_generation", "frequency", "pulse", "prostate_generation",
                    "positional_axes"):
        if section in config:
            creative_config[section] = config[section]

    presets[name] = {
        "description": description or f"User preset: {name}",
        "config": creative_config,
    }

    p.write_text(json.dumps(presets, indent=2), encoding="utf-8")
    return str(p)


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
        alpha_y, beta_y = _geometric_preview_path(
            algorithm,
            min_distance_from_center,
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

def _cmd_algorithms(args):
    for key, name in ALGORITHMS.items():
        desc = ALGORITHM_DESCRIPTIONS[key]
        print(f"  {key:<20} {name}")
        print(f"  {'':20} {desc}")
        print()


def _cmd_config_show(args):
    cfg = get_default_config()
    if args.section:
        if args.section not in cfg:
            print(f"Error: unknown section '{args.section}'. "
                  f"Available: {', '.join(cfg.keys())}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(cfg[args.section], indent=2))
    else:
        print(json.dumps(cfg, indent=2))


def _cmd_config_save(args):
    cfg = get_default_config()
    out = Path(args.output)
    if out.exists() and not args.force:
        print(f"Error: {out} already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)
    with open(out, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"Default config saved to: {out}")
    print(f"Edit it, then use:  python cli.py process <file> --config {out}")


def _cmd_preview_electrode(args):
    result = preview_electrode_path(
        algorithm=args.algorithm,
        min_distance_from_center=args.min_distance,
        speed_threshold_percent=args.speed_threshold,
        points=args.points,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Algorithm:    {result['label']}")
        print(f"Description:  {result['description']}")
        print(f"Points:       {len(result['alpha'])} alpha, {len(result['beta'])} beta")
        print(f"Alpha range:  {min(result['alpha']):.3f} – {max(result['alpha']):.3f}")
        print(f"Beta range:   {min(result['beta']):.3f} – {max(result['beta']):.3f}")


def _cmd_preview_frequency(args):
    result = preview_frequency_blend(
        frequency_ramp_combine_ratio=args.ramp_ratio,
        pulse_frequency_combine_ratio=args.pulse_ratio,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"  {result['overall_label']}")
        print(f"  Frequency:  {result['frequency_label']}")
        print(f"  Pulse:      {result['pulse_label']}")


def _cmd_preview_pulse(args):
    result = preview_pulse_shape(
        width_min=args.width_min,
        width_max=args.width_max,
        rise_min=args.rise_min,
        rise_max=args.rise_max,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"  {result['label']}")
        print(f"  Width (mid): {result['width']}")
        print(f"  Rise  (mid): {result['rise']}")
        print(f"  Sharpness:   {result['sharpness']}")


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
        description=(
            "funscript-tools CLI — convert .funscript files into restim-ready output sets.\n\n"
            "Processing engine by edger477: https://github.com/edger477/funscript-tools\n\n"
            "Quick start:\n"
            "  python cli.py process my_scene.funscript\n\n"
            "Tune settings:\n"
            "  python cli.py config save my_config.json\n"
            "  # edit my_config.json, then:\n"
            "  python cli.py process my_scene.funscript --config my_config.json\n\n"
            "Explore without processing:\n"
            "  python cli.py algorithms\n"
            "  python cli.py preview electrode-path --algorithm circular\n"
            "  python cli.py preview frequency-blend --ramp-ratio 4\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "For full documentation see DESIGN.md or examples/README.md\n"
            "Run any subcommand with --help for details:  python cli.py process --help"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    # ── info ─────────────────────────────────────────────────────────────────
    p_info = sub.add_parser(
        "info",
        help="Show metadata about a .funscript file",
        description="Load a .funscript file and display its metadata — action count, duration, and position range.",
        epilog="Example:\n  python cli.py info my_scene.funscript",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_info.add_argument("file", help="Path to the .funscript file")

    # ── process ──────────────────────────────────────────────────────────────
    p_proc = sub.add_parser(
        "process",
        help="Run the full processing pipeline on a .funscript file",
        description=(
            "Process a .funscript file through the full restim pipeline, generating all\n"
            "output files (alpha, beta, frequency, volume, pulse_width, etc.).\n\n"
            "Outputs are written next to the input file by default.\n"
            "Use --config to load a saved config (see: python cli.py config save).\n"
            "Use --output-dir to redirect outputs to a different folder."
        ),
        epilog=(
            "Examples:\n"
            "  python cli.py process my_scene.funscript\n"
            "  python cli.py process my_scene.funscript --output-dir ~/restim/\n"
            "  python cli.py process my_scene.funscript --config my_config.json\n"
            "  python cli.py process my_scene.funscript --config my_config.json --output-dir ~/restim/"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_proc.add_argument("file", help="Path to the .funscript file to process")
    p_proc.add_argument(
        "--config",
        metavar="FILE",
        help="JSON config file to use instead of defaults (see: python cli.py config save)"
    )
    p_proc.add_argument(
        "--output-dir",
        metavar="DIR",
        help="Directory for output files (default: same folder as input)"
    )

    # ── list-outputs ─────────────────────────────────────────────────────────
    p_list = sub.add_parser(
        "list-outputs",
        help="List generated output files for a given input stem",
        description=(
            "Find and list all generated .funscript output files for a given input\n"
            "filename stem (the filename without .funscript extension)."
        ),
        epilog=(
            "Examples:\n"
            "  python cli.py list-outputs . my_scene\n"
            "  python cli.py list-outputs ~/restim/ my_scene"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_list.add_argument("directory", help="Directory to search for output files")
    p_list.add_argument("stem", help="Input filename without extension (e.g. my_scene)")

    # ── algorithms ───────────────────────────────────────────────────────────
    sub.add_parser(
        "algorithms",
        help="List available 2D electrode path algorithms with descriptions",
        description=(
            "List all available algorithms for converting 1D funscript motion\n"
            "into a 2D electrode path, with plain-language descriptions.\n\n"
            "Use the algorithm key with:  python cli.py preview electrode-path --algorithm <key>\n"
            "Or set it in your config:    python cli.py config save my_config.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── config ───────────────────────────────────────────────────────────────
    p_cfg = sub.add_parser(
        "config",
        help="Show or save the default processing configuration",
        description=(
            "Inspect or export the default configuration.\n\n"
            "Workflow:\n"
            "  1. Save defaults to a file:   python cli.py config save my_config.json\n"
            "  2. Edit my_config.json in any text editor\n"
            "  3. Process with your config:  python cli.py process file.funscript --config my_config.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cfg_sub = p_cfg.add_subparsers(dest="config_command", required=True, metavar="subcommand")

    p_cfg_show = cfg_sub.add_parser(
        "show",
        help="Print the default configuration as JSON",
        description="Print the full default config, or a single section, as formatted JSON.",
        epilog=(
            "Examples:\n"
            "  python cli.py config show\n"
            "  python cli.py config show frequency\n"
            "  python cli.py config show pulse"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_cfg_show.add_argument(
        "section", nargs="?",
        help="Section to show: general, frequency, pulse, volume, alpha_beta_generation, "
             "prostate_generation, advanced, options, positional_axes, speed. Omit for full config."
    )

    p_cfg_save = cfg_sub.add_parser(
        "save",
        help="Save the default configuration to a JSON file for editing",
        description=(
            "Write the full default configuration to a JSON file.\n"
            "Edit the file to tune parameters, then use it with --config."
        ),
        epilog=(
            "Examples:\n"
            "  python cli.py config save my_config.json\n"
            "  python cli.py config save configs/gentle.json\n"
            "  python cli.py config save my_config.json --force  # overwrite existing"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_cfg_save.add_argument("output", help="Output file path (e.g. my_config.json)")
    p_cfg_save.add_argument("--force", action="store_true", help="Overwrite if file already exists")

    # ── preview ──────────────────────────────────────────────────────────────
    p_prev = sub.add_parser(
        "preview",
        help="Preview parameter effects without running the full pipeline",
        description=(
            "Fast parameter previews — no file I/O, no output files written.\n"
            "Use these to understand what a setting does before committing to a full process run.\n"
            "Add --json to pipe results to other tools."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    prev_sub = p_prev.add_subparsers(dest="preview_command", required=True, metavar="subcommand")

    p_elec = prev_sub.add_parser(
        "electrode-path",
        help="Show the 2D electrode path shape for an algorithm",
        description=(
            "Generate the 2D electrode path shape that a given algorithm produces.\n"
            "Uses a synthetic sine-wave input so the shape reflects the algorithm only.\n\n"
            "This is what the UI plots when you change the Algorithm dropdown.\n"
            "Run 'python cli.py algorithms' to see available algorithm keys."
        ),
        epilog=(
            "Examples:\n"
            "  python cli.py preview electrode-path\n"
            "  python cli.py preview electrode-path --algorithm circular\n"
            "  python cli.py preview electrode-path --algorithm top-right-left --min-distance 0.3\n"
            "  python cli.py preview electrode-path --json | python -m json.tool"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_elec.add_argument(
        "--algorithm", default="circular",
        choices=list(ALGORITHMS.keys()),
        help="Algorithm to preview (default: circular)"
    )
    p_elec.add_argument(
        "--min-distance", type=float, default=0.1,
        metavar="0.0-0.9",
        help="Min distance from center (default: 0.1)"
    )
    p_elec.add_argument(
        "--speed-threshold", type=float, default=50.0,
        metavar="0-100",
        help="Speed threshold percent (default: 50)"
    )
    p_elec.add_argument(
        "--points", type=int, default=200,
        help="Number of preview points (default: 200)"
    )
    p_elec.add_argument(
        "--json", action="store_true",
        help="Output raw JSON (for piping to other tools)"
    )

    p_freq = prev_sub.add_parser(
        "frequency-blend",
        help="Show plain-language description of frequency blend settings",
        description=(
            "Translate the frequency combine ratios into plain English.\n"
            "Shows what percentage of the output comes from the slow ramp vs scene energy,\n"
            "and gives an overall character description.\n\n"
            "The ramp ratio controls the primary frequency envelope.\n"
            "The pulse ratio controls how pulse frequency tracks action intensity."
        ),
        epilog=(
            "Examples:\n"
            "  python cli.py preview frequency-blend\n"
            "  python cli.py preview frequency-blend --ramp-ratio 4\n"
            "  python cli.py preview frequency-blend --ramp-ratio 1 --pulse-ratio 1\n"
            "  python cli.py preview frequency-blend --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_freq.add_argument(
        "--ramp-ratio", type=float, default=2.0,
        metavar="1-10",
        help="Frequency ramp combine ratio (default: 2.0)"
    )
    p_freq.add_argument(
        "--pulse-ratio", type=float, default=3.0,
        metavar="1-10",
        help="Pulse frequency combine ratio (default: 3.0)"
    )
    p_freq.add_argument("--json", action="store_true", help="Output raw JSON")

    p_pulse = prev_sub.add_parser(
        "pulse-shape",
        help="Show pulse silhouette for given width and rise time settings",
        description=(
            "Describe the shape of a representative pulse given width and rise time settings.\n\n"
            "Width controls how long each pulse lasts.\n"
            "Rise time controls how quickly it ramps up — low values are sharp, high values are soft.\n\n"
            "Both are expressed as 0.0–1.0 fractions. The preview uses the midpoint of each range."
        ),
        epilog=(
            "Examples:\n"
            "  python cli.py preview pulse-shape\n"
            "  python cli.py preview pulse-shape --width-min 0.1 --width-max 0.5\n"
            "  python cli.py preview pulse-shape --rise-min 0.0 --rise-max 0.1   # sharp\n"
            "  python cli.py preview pulse-shape --rise-min 0.5 --rise-max 0.9   # soft\n"
            "  python cli.py preview pulse-shape --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pulse.add_argument("--width-min", type=float, default=0.1, metavar="0.0-1.0")
    p_pulse.add_argument("--width-max", type=float, default=0.45, metavar="0.0-1.0")
    p_pulse.add_argument("--rise-min",  type=float, default=0.0,  metavar="0.0-1.0")
    p_pulse.add_argument("--rise-max",  type=float, default=0.80, metavar="0.0-1.0")
    p_pulse.add_argument("--json", action="store_true", help="Output raw JSON")

    # ── dispatch ─────────────────────────────────────────────────────────────
    args = parser.parse_args()

    if args.command == "info":
        _cmd_info(args)
    elif args.command == "process":
        _cmd_process(args)
    elif args.command == "list-outputs":
        _cmd_list_outputs(args)
    elif args.command == "algorithms":
        _cmd_algorithms(args)
    elif args.command == "config":
        if args.config_command == "show":
            _cmd_config_show(args)
        elif args.config_command == "save":
            _cmd_config_save(args)
    elif args.command == "preview":
        if args.preview_command == "electrode-path":
            _cmd_preview_electrode(args)
        elif args.preview_command == "frequency-blend":
            _cmd_preview_frequency(args)
        elif args.preview_command == "pulse-shape":
            _cmd_preview_pulse(args)


if __name__ == "__main__":
    main()
