# Architecture Decisions

This document records the key architectural decisions made during the design of
FunScriptForge and funscript-tools, and the reasoning behind them.

---

## Decision 1: OSS Fork Adapter Pattern

**Decision:** All open-source integrations follow a strict fork → `cli.py` → UI pattern.
The UI never imports upstream classes directly.

**Why:** When upstream changes internals, you fix one file (`cli.py`). The UI never
breaks. When porting to a new deployment target (desktop → SaaS), only the rendering
layer changes — the adapter is identical.

**How it works:**
```
upstream repo          cli.py (adapter)        UI layer
──────────────         ────────────────         ─────────────────────────
processor.py  ──────►  process()         ──────► forge_window.py (dev)
funscript.py           load_file()               Streamlit tab (desktop)
config.py              get_default_config()      API endpoint (SaaS)
```

**Consequence:** Every OSS integration we add follows this pattern. `cli.py` is the
contract. Stable function signatures, plain return types (dict, list, numpy array),
no upstream objects ever cross the boundary.

---

## Decision 2: Three Deployment Targets, One Adapter

**Decision:** The same `cli.py` serves local CLI use, the tkinter dev harness,
Streamlit desktop (PyInstaller), and SaaS — without modification.

**Why:** We ship to Windows, Mac, Linux desktop and a cloud SaaS. Writing four
versions of the same logic is unsustainable. The adapter isolates all differences
in a thin rendering layer.

| Target | Layer | How it runs |
|--------|-------|-------------|
| CLI / automation | `argparse` in `cli.py` | `python cli.py process ...` |
| Dev/test | tkinter (`forge_window.py`) | `python forge.py` |
| Desktop | Streamlit in FunScriptForge | PyInstaller + local Streamlit |
| SaaS | Streamlit in FunScriptForge | Cloud-deployed Streamlit |

**Consequence:** The tkinter standalone is a development harness only — fast
iteration without Streamlit overhead. Once the UX is proven there, the Streamlit
tab calls identical `cli.py` functions.

---

## Decision 3: Project State as JSON (Design for Agents)

**Decision:** Project state is a single `.forge-project.json` file.
Schema is designed for both human use and agent orchestration simultaneously.

**Why JSON, not a database:**
- Portable — lives next to the source files, easy to inspect, easy to back up
- No install dependency
- Upgrades to a database later without changing the schema — a JSON file
  is a degenerate case of a record in a job queue

**Why designed for agents now:**
We recognized during design that the 4-tab workflow UI is not just a UI for humans.
It is a human-in-the-loop interface — the surface where an agent hands off a decision
to a human, the human approves, and the pipeline continues. Building the project
schema to support agent reasoning now costs one field (`agent_notes`) and makes
the upgrade to agentic automation trivial later.

**The four capabilities agents add:**
1. **Handoff notification** — run automated steps, surface to human only when judgment is needed
2. **Configuration recommendation** — analyze source material, suggest settings, explain why
3. **Evaluation loops** — run → score → adjust → rerun until output meets criteria, then notify
4. **Audit trail and explanation** — `agent_notes` records every non-default decision so humans learn the domain

**Key schema fields that enable agents:**

| Field | Human use | Agent use |
|-------|-----------|-----------|
| `next_action` | Resume: open the right tab | Continue: know whether to run or wait |
| `agent_notes` | Read why settings were chosen | Write reasoning for human review |
| `evaluation.checks` | See pass/fail quality summary | Decide whether to retry or escalate |
| `human_review.required` | Know when approval is needed | Know when to pause the loop |
| `resource.url` | — | Call remote API instead of local CLI |

**Upgrade path:**
- Today: `resource.path` → local CLI
- SaaS: `resource.url` → REST API call
- Enterprise: `step.job_id` → remote job queue, `next_action.type: "await_job"`
- The schema handles all three without breaking existing projects

---

## Decision 4: Preview Functions for Live UI

**Decision:** `cli.py` exposes `preview_*` functions that return pure data
(no file I/O) for every configurable parameter group.

**Why:** Live parameter visualization requires calling the underlying math on
every slider move. File-writing operations are too slow for this. Preview functions
use the same math as the real processor but return numpy arrays directly —
safe to call 10 times per second from a UI event loop.

**Functions:** `preview_electrode_path()`, `preview_frequency_blend()`,
`preview_pulse_shape()`, `preview_output()`

**Consequence:** These same functions are what an agent uses to *evaluate options*
before committing to a full process run. The agent calls `preview_electrode_path()`
for each algorithm, scores the result, picks the best one — without writing any files.

---

## Decision 5: Value-Add Layer on Every OSS Fork

**Decision:** When we fork an OSS project, our contribution is always the same
six things — regardless of what the underlying tool does.

1. **Tests** — upstream often has none
2. **CLI** — structured interface with documented flags and `--help`
3. **API** — programmatic access for SaaS integration
4. **Docs** — MkDocs user documentation on GitHub Pages
5. **UI + Visualizations** — every parameter shows its effect visually in plain language
6. **Production packaging** — cross-platform builds, error handling, graceful completion

**Why this framing:** Users know what they want to feel, not what the math does.
Every parameter change should show its effect immediately. "70% scene energy" not
"frequency_ramp_combine_ratio: 3". The value-add is translation — between math and experience, between upstream internals and user decisions.

---

## Decision 6: Plugin Architecture for FunScriptForge

**Decision:** Each tool integration becomes a plugin (tab) in FunScriptForge.
FunScriptForge is the project host. Plugins are the steps.

**Why:** A content creation workflow involves many tools chained together.
The user shouldn't manage that chain manually — open tool A, take the output,
open tool B, etc. FunScriptForge manages the project state, shows the user
where they are in the pipeline, and surfaces each tool at the right moment.

**Plugin interface (same regardless of tool):**
- Local: call the tool's `cli.py` via subprocess or direct import
- SaaS: call the tool's REST API endpoint
- Both expose the same function signatures — the host doesn't care which transport is used

**Project lifecycle:**
```
New project
  └─ Step 1: funscript-tools   → awaiting_human (review outputs)
  └─ Step 2: [next tool]       → pending
  └─ Step 3: [next tool]       → pending

Human approves step 1
  └─ Step 2 runs automatically (or agent runs it)
  └─ Step 2 completes → awaiting_human (if review required)

Human approves step 2
  └─ Step 3 runs...
```

**Long-running jobs:** Some steps take minutes or hours (e.g., 4K video render).
`step.status = "running"` with no `completed` timestamp means in-flight.
The project file is the source of truth. The UI polls or subscribes.
The user closes the app, comes back later, opens the project — it's done.

---

## What we are building toward

The architecture described above is a foundation for agentic workflow automation:

```
project.forge-project.json   (state + agent memory)
         │
         ▼
    agent reads next_action
         │
    ┌────┴────────────────────────────────────────┐
    │ type: run_step                              │
    │   → call tool CLI/API                       │
    │   → evaluate output                         │
    │   → if failed: adjust config, retry         │
    │   → if passed: write agent_notes, continue  │
    └────┬────────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────────────┐
    │ type: await_human                           │
    │   → notify user                             │
    │   → surface project in FunScriptForge UI    │
    │   → human reviews, approves, adds notes     │
    │   → pipeline continues                      │
    └─────────────────────────────────────────────┘
```

This is not a future feature. The project schema supports it today.
The CLI tools support it today. The UI is already structured as a
human-in-the-loop interface. Adding an agent means wiring a loop around
what already exists.

---

## Repos and responsibilities

| Repo | Role |
|------|------|
| `funscript-tools` | CLI adapter + dev UI harness for edger477's restim processor |
| `funscriptforge` | Project host, plugin tabs, Streamlit UI, PyInstaller packaging |
| `funscriptforge-web` | Marketing site (static, Cloudflare Pages) |
| `wiki` | General estim getting-started content |

Upstream: `edger477/funscript-tools` — all processing algorithm credit to edger477.
