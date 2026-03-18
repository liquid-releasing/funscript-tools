# Funscript Tools — Estim Tone Engine

One funscript in. Ten estim outputs out. Tone baked in.

A GUI and CLI for converting a single `.funscript` file into a complete set of restim-ready output files, with named estim tones that control how sensation moves and builds.

---

## The Idea

A funscript describes position over time — the stroke. Restim needs more: where the sensation is, how it moves, how intense it gets, how the pulse feels.

This tool takes the stroke and derives all of it. You pick a **tone** — a movement personality — and it generates alpha, beta, pulse frequency, and seven other output files tuned to that tone.

---

## eTransforms — Six Tones

| Tone | What it means |
|---|---|
| **Gentle** | Soft, slow-building. Narrow arc, soft pulse onset. Good for intimate or slow content. |
| **Reactive** | Sharp, tracks action closely. Wide arc, instant response. Good for fast, intense content. |
| **Scene Builder** | Builds gradually over the scene. Circular arc, slow ramp. Rewards patience. |
| **Unpredictable** | Random direction changes, varied tone. Keeps you guessing. |
| **Balanced** | Middle of everything. Good starting point for any content. |
| **Baseline** | Safe, unbiased output. No tone applied. Clean processing with sensible defaults. |

Pick a tone. See 1–2 sliders that matter for it. Tune if you want. Process.

---

## The Three Outputs That Matter

| File | What it is |
|---|---|
| `alpha.funscript` | Where — left/right electrode position |
| `beta.funscript` | Where — up/down electrode position |
| `pulse_frequency.funscript` | Intensity — tracks action speed |

Plus seven additional channels for specialist hardware (pulse_width, pulse_rise, E1–E4, prostate).

---

## Workflow

```
1. Drop a .funscript file
2. Pick an eTransform tone
3. Tune 1–2 sliders (optional)
4. Process — takes seconds
5. Review: original / master / alpha / beta / pulse_frequency / explorer
6. Export to project folder
```

The Review tab shows six panels simultaneously. Original on the left. Five outputs on the right. The Explorer panel lets you inspect any additional channel. All panels update automatically when you change settings.

---

## CLI

```bash
# Process with defaults
python cli.py process input.funscript

# List available eTransforms
python cli.py list-presets

# Process with a named character
python cli.py process input.funscript --preset Reactive

# Get config for a preset (JSON)
python cli.py get-preset "Scene Builder"

# Save current settings as a named preset
python cli.py save-preset "My Character" --from-config config.json
```

### Pipe-friendly JSON output

```bash
python cli.py process input.funscript --json | jq '.outputs'
```

---

## Installation

### Option 1: Pre-built executable

Download the latest release — no Python required.

### Option 2: From source

```bash
git clone https://github.com/liquid-releasing/funscript-tools.git
cd funscript-tools
pip install -r requirements.txt
python forge.py
```

**Requirements:** Python 3.8+, NumPy, Matplotlib. Tkinter included with Python on Windows/macOS. Optional: `pip install tkinterdnd2` for drag-and-drop.

---

## Project Bundle (Export)

All outputs go into a named project folder alongside the video:

```
my-scene/
  my-scene.mp4
  my-scene.funscript
  my-scene.alpha.funscript
  my-scene.beta.funscript
  my-scene.pulse_frequency.funscript
  ... (all outputs)
```

Drop the folder into restim. Done.

---

## Advanced — Full Control

Every parameter from the underlying processor is still accessible via **Advanced** in the UI, or as raw config in the CLI. The eTransforms are a starting point, not a cage.

Edger's full parameter set: algorithm, points per second, speed threshold, frequency ramp ratio, pulse frequency min/max, pulse width min/max, pulse rise min/max, and more.

---

## Test Fixtures

```
tests/fixtures/big_buck_bunny.raw.funscript     — original, unprocessed
tests/fixtures/big_buck_bunny.forged.funscript  — after FunScriptForge cleanup
```

Convention: `<name>.raw.funscript` / `<name>.forged.funscript`

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the adapter boundary design, the sensitivity matrix plan, and the agent loop spec.

**Adapter boundary:** `forge_window.py` imports only from `cli.py`. Zero upstream imports. The UI, the CLI, and FunScriptForge all call the same functions.

---

## Integration with FunScriptForge

funscript-tools is the second stage of the estim pipeline:

```
FunScriptForge Explorer  →  FunScriptForge  →  funscript-tools  →  restim
   (originate)               (edit/shape)       (estim character)   (play)
```

The same five tone names appear in FunScriptForge. Pick a tone once — it flows through the entire pipeline.

---

## Credits

Built on [edger477/funscript-tools](https://github.com/edger477/funscript-tools). The eTransforms system, guided UI, CLI preset API, and six-panel review are additions by [liquid-releasing](https://github.com/liquid-releasing).
