# Forge UI Design — v1

## The flow (7 steps)

```
1. Drop funscript (or Browse)
2. Pick path shape — the circle/arc picker
3. Pick eTransform — 5 characters, 1–2 contextual sliders
4. Process (seconds)
5. Flip through alpha / beta / pulse_frequency previews
6. Export → project folder
7. Load in restim with video
```

---

## Configure panel layout

```
┌─ Path shape ──────────────────────────────────┐
│  [circular] [wide arc] [narrow arc] [original] │
│  Electrode path preview (live mini-plot)        │
│  Motion range slider                            │
└────────────────────────────────────────────────┘

┌─ eTransforms — Pick a character ──────────────┐
│  [Gentle] [Reactive] [Scene Builder]           │
│  [Unpredictable] [Balanced]                    │
│  ─────────────────────────────────────────────│
│  < 1–2 contextual sliders for selected >       │
│    e.g. Gentle: Softness + Onset gentleness    │
│  ▶ More settings...   (twisty, expands inline) │
│    < remaining sliders, collapsed by default > │
└────────────────────────────────────────────────┘

┌─ Advanced — Edger's full config ──────────────┐
│  [ button — takes over Configure tab ]         │
│  All parameter tabs visible                    │
│  [ Accept ] — returns to 3-panel preview       │
└────────────────────────────────────────────────┘
```

No scroll needed for the common case. Twisty expands inline. Advanced takes over the tab.

---

## Preview — the three channels

After processing, three panels with prev/next navigation:

```
[ ← ]  alpha — where (left/right)  [ → ]
       [ waveform ]

[ ← ]  beta — where (up/down)  [ → ]
       [ waveform ]

[ ← ]  pulse frequency — intensity  [ → ]
       [ waveform ]
```

Additional channels (pulse_width, pulse_rise, E1–E4, prostate) accessible but subordinate.

**What each looks like:**
- alpha / beta — position over time, transformed. Should look like original funscript but reshaped by the algorithm.
- pulse_frequency — intensity tracking. Follows stroke *speed*, not position. Spiky, reacts to action. Looks distinctly different from alpha/beta.

---

## eTransforms — the five characters

Currently applies globally. Per-section support coming when FunScriptForge phrase detection integrates.

| Name | Character | Contextual sliders |
|---|---|---|
| Gentle | Soft, slow-building. Intimate/slow content. | Softness, Onset gentleness |
| Reactive | Sharp, tracks action closely. Fast/intense. | Reactivity, Peak intensity |
| Scene Builder | Builds gradually. Long content, slow arc. | Build speed, Arc width |
| Unpredictable | Random direction changes. Surprise content. | Wildness, Pulse variety |
| Balanced | Middle of everything. Good starting point. | Sweep width, Reactive vs. gradual |

User-defined eTransforms save to `~/.config/funscript-tools/presets.json`.

**Design rule:** ~75% of parameters are locked per eTransform. Only the meaningful levers surface. Everything else is handled.

---

## Export — project bundle

```
my-scene/
  my-scene.mp4                 ← video (copied in)
  my-scene.funscript           ← original input
  my-scene.alpha.funscript
  my-scene.beta.funscript
  my-scene.pulse_frequency.funscript
  my-scene.pulse_width.funscript
  my-scene.pulse_rise.funscript
  ... (rest of outputs)
```

One folder. Drop into restim. No hunting for files.

---

## Channels

| Channel | What it is | Priority |
|---|---|---|
| alpha | Left-right electrode position | Primary |
| beta | Up-down electrode position | Primary |
| pulse_frequency | Pulse rate / intensity tracking | Primary |
| pulse_width | Fullness of each pulse | Additional |
| pulse_rise | Attack sharpness | Additional |
| E1–E4 | 4-pole electrode distribution | Additional |
| prostate_* | Prostate channel | Additional |

Alpha + beta + pulse_frequency = 80% of the experience. The rest is texture for specialist hardware.

---

## Audience

- **Enthusiast creator** — picks an eTransform, tunes 1–2 sliders, done in 30 seconds
- **Power user / twiddler** — opens the twisty, adjusts the full creative panel
- **Edger / expert** — Advanced button, all parameter tabs, full control

All three paths end at the same three preview panels and the same export.

---

## Backlog (priority order)

1. **Project bundle** — output folder with video + all funscripts, named after project
2. **Twisty / disclosure** — inline expand of remaining sliders in eTransforms panel
3. **Channel tour** — prev/next through all output channels with plain-English descriptions
4. **Validate eTransform slider choices** — empirical test: vary each slider, measure output delta, confirm the right 2 are surfaced per character
5. **Per-section eTransforms** — phrase timestamps from FunScriptForge feed into process_sections()
6. **process_sections() in cli.py** — section-based processing
7. **Forge editor** — video creation inside the tool
