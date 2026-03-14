# Workflow Assessment — funscript-tools UI

> This document captures what the original UI by edger477 is asking the user to decide,
> and how we're organizing those decisions in the Funscript Forge workflow wrapper.
>
> All processing algorithms and transforms are the work of edger477 and contributors:
> https://github.com/edger477/funscript-tools

---

## What the original UI asks the user to answer

The controls fall into two groups: **creative decisions** that shape how the output feels,
and **config** that you set once and leave alone.

---

### Creative Controls — what changes how it feels

#### Motion Axis (the 2D path on the electrode)
- **Algorithm** — which geometric path to trace:
  - Top-Right-Bottom-Left (0°–270°)
  - Circular (0°–180°)
  - Top-Left-Bottom-Right (0°–90°)
  - Restim original (0°–360°)
  - Tear-shaped (prostate)
- **Points per second** — how smoothly the path is interpolated (1–100)
- **Min distance from center** — how "wide" the motion range is (0.1–0.9)
- **Speed threshold %** — what percentile of speed triggers maximum radius (0–100%)
- **Direction change probability** — randomness in direction flips (restim-original only)
- **Phase-shifted copies** — generate a delayed second channel for stereo stimulation

#### Frequency (pulse rate)
- **Ramp vs Speed blend** — how much is slow build vs action intensity
  - `frequency_ramp_combine_ratio` — primary frequency (ramp + speed blend)
  - `pulse_frequency_combine_ratio` — pulse frequency (speed + alpha blend)
- **Pulse frequency min/max** — output range mapping (0.0–1.0)

#### Pulse shape (how each pulse feels)
- **Width min/max** — limits on pulse width, mapped from inverted main signal
- **Width blend** — Speed vs limited-main combine ratio
- **Rise time min/max** — limits on pulse rise time
- **Rise time blend** — Ramp-inverted vs Speed-inverted combine ratio

#### E1–E4 curves (4P mode only)
- Per-axis enable/disable
- Custom curve editor: maps input position (0–100) → output response (0–100)
- Phase-shifted copies for each axis

---

### Config — set once and leave

| Setting | What it does |
|---------|-------------|
| Rest level | Signal level during silence/stillness |
| Ramp-up duration | Seconds to recover from rest (0 = instant) |
| Speed window size | Smoothing window for speed calculation (seconds) |
| Accel window size | Smoothing window for acceleration |
| Interpolation interval | Time between interpolated points (seconds) |
| Volume combine ratio | Ramp vs Speed blend for amplitude |
| Normalize volume | Whether to normalize the volume output |
| Prostate multiplier | Volume scaling for prostate channel |
| Generate prostate files | Whether to produce prostate outputs |
| Generate 3P / 4P | Which motion axis mode(s) to produce |
| Output mode | Local (next to source) or Central (fixed folder) |
| Overwrite / backup | What to do with existing outputs |
| Inversion outputs | Whether to generate inverted variants |

---

## How Funscript Forge organizes this

```
Tab 1: Input
  Load file → see original waveform → understand what you're working with

Tab 2: Configure
  Left side:
    [Creative]  — the knobs that change how it feels (algorithm, frequency blend, pulse shape)
    [Settings]  — the full parameter set for advanced users
  Right side:
    Before: original waveform
    After:  preview of selected output type (updates after Process)
  → Process button

Tab 3: Review
  Left: checklist of all generated outputs (check to include in export)
  Right: click any output → see before/after comparison plot

Tab 4: Export
  Choose output directory → export selected files
  Completion: Open Folder | New Project  (no modal popups on success)
```

---

## Key insight for the UI

The "creative" controls are what a user iterates on — they process, look at the before/after,
adjust the algorithm or blend ratio, process again. The "config" is infrastructure.

By surfacing the creative controls prominently and showing before/after visualization,
the user can develop an intuition for what each parameter does without needing to understand
the underlying math.
