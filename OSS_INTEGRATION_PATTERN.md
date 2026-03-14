# OSS Integration Pattern

> This document describes the standard pattern used across the liquid-releasing
> project suite for integrating open-source tools. It lives here as a worked
> example and should be copied into FunScriptForge as the canonical reference.

---

## The Problem

Open-source projects change. When you build a UI directly on top of someone
else's classes and config structures, every upstream update is a potential
breaking change scattered across your entire codebase.

## The Solution: Fork → Adapter → UI

```
upstream repo                    your fork
─────────────────────────────    ──────────────────────────────────────────
processor.py                     cli.py              forge_window.py
funscript.py      ────────────►  (your adapter)  ►  (UI / FunScriptForge tab)
config.py                        stable API
```

`cli.py` is the **adapter** — it translates between the upstream API and a
stable contract that your UI binds to. When upstream changes, you fix `cli.py`.
The UI never changes.

---

## Steps to add a new OSS integration

### 1. Fork and clone

```bash
gh repo fork <upstream-url> --clone=false
git clone https://github.com/liquid-releasing/<repo>.git
cd <repo>
git remote add upstream <original-url>
git remote -v  # verify both origin and upstream
```

### 2. Build `cli.py` — your adapter

Design the stable functions *you* want to expose before writing any UI:

```python
# cli.py — the only file the UI ever imports from

def load_file(path: str) -> dict:
    """Load source file. Returns simple dict, never an upstream object."""
    ...

def get_default_config() -> dict:
    """Return default config as a plain dict."""
    ...

def process(path: str, config: dict, on_progress=None) -> list[dict]:
    """Run the pipeline. Returns list of {suffix, path} dicts."""
    ...

def list_outputs(directory: str, stem: str) -> list[dict]:
    """Find generated output files. Returns list of {suffix, path} dicts."""
    ...
```

Rules for `cli.py`:
- **Only file the UI imports from** — never import upstream classes in the UI
- **Returns simple types** — `dict`, `list`, `str`, `Path` — never upstream objects
- **Owns the config structure** — wrap/translate upstream config internally
- **One file** — all upstream interaction in one place

### 3. Build the UI on top of `cli.py`

```python
# ui/forge_window.py
from cli import load_file, process, get_default_config   # ✓ only this

# Never:
# from processor import RestimProcessor                  # ✗
# from funscript import Funscript                        # ✗
```

### 4. Pull upstream updates

```bash
git fetch upstream
git merge upstream/main
```

If it breaks: the error is in `cli.py`. Fix the translation there. UI untouched.

### 5. Add to FunScriptForge as a tab

Because the UI calls `cli.py` — not upstream internals — porting to FunScriptForge
means:
1. Copy `cli.py` into the FunScriptForge module
2. Replace `forge_window.py` with a `ttk.Frame`-based tab
3. The tab calls the same `cli.py` functions unchanged

---

## Worked Example: funscript-tools

| File | Role |
|------|------|
| `processor.py` | edger477's processing engine — **never imported by UI** |
| `cli.py` | *(to be built)* adapter exposing `load_file`, `process`, `get_default_config` |
| `ui/forge_window.py` | 4-tab workflow UI — imports `cli.py` only |
| `forge.py` | Entry point |

Upstream repo: https://github.com/edger477/funscript-tools
Our fork: https://github.com/liquid-releasing/funscript-tools

---

## Why this matters for the whole suite

Every tool in the liquid-releasing ecosystem that wraps OSS follows this pattern:

```
funscript-tools  →  cli.py  →  FunScriptForge tab
[next tool]      →  cli.py  →  FunScriptForge tab
[next tool]      →  cli.py  →  FunScriptForge tab
```

FunScriptForge becomes the unified UI. Each `cli.py` is an independently
versioned, independently testable adapter. The UI is just tabs.
