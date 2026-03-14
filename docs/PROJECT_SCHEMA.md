# Project Schema

A `.forge-project.json` file is the persistent state for a FunScriptForge project.
It serves two purposes simultaneously:

1. **Human resume** — open the project later and pick up exactly where you left off
2. **Agent memory** — the agent reads this file to know what's been done, what to run
   next, and why previous decisions were made

The schema is designed to be simple now and upgrade cleanly to a remote/enterprise
job queue later. The only difference between local and SaaS use is whether
`resource.path` or `resource.url` is populated.

---

## Top-level structure

```json
{
  "version": 1,
  "id": "a3f2c1d4-...",
  "name": "my_scene — restim",
  "created": "2026-03-14T10:30:00Z",
  "updated": "2026-03-14T11:15:00Z",
  "status": "awaiting_human",
  "next_action": {
    "type": "await_human",
    "step": 0,
    "message": "Review the frequency output before exporting."
  },
  "source": { ... },
  "steps": [ ... ]
}
```

### `status` enum

| Value | Meaning |
|-------|---------|
| `pending` | Not started |
| `running` | A step is actively executing |
| `awaiting_human` | Paused — needs a human decision before continuing |
| `complete` | All steps done, outputs ready |
| `failed` | A step failed; `error` field on that step explains why |

### `next_action`

The single most important field for an agent or a UI shell.
Always describes what should happen next — no need to walk the steps array to figure it out.

| `type` | Meaning |
|--------|---------|
| `run_step` | Agent or automation can proceed; run step at index `step` |
| `await_human` | Stop and surface to the user; `message` says what's needed |
| `complete` | Nothing left to do |

---

## Resource

Used for source files and output files. Path for local, URL for remote.
Never both required — populate whichever applies.

```json
{
  "name": "my_scene.funscript",
  "path": "/Users/bruce/scenes/my_scene.funscript",
  "url": null,
  "checksum": "sha256:a3f2..."
}
```

`checksum` is optional but lets the agent verify that files haven't changed
between sessions without re-reading them.

---

## Step

```json
{
  "index": 0,
  "tool": "funscript-tools",
  "tool_version": "0.2.0",
  "label": "Convert to restim signals",
  "status": "awaiting_human",
  "config": { ... },
  "inputs": [ { "name": "...", "path": "...", "url": null } ],
  "outputs": [ { "name": "...", "path": "...", "url": null } ],
  "started": "2026-03-14T11:00:00Z",
  "completed": "2026-03-14T11:02:14Z",
  "duration_s": 134,
  "agent_notes": "Chose top-right-left: source has wide amplitude variance across stroke range. Ramp ratio set to 3 — pacing is fast in second half.",
  "evaluation": {
    "passed": true,
    "score": 0.87,
    "checks": [
      { "name": "frequency_range",  "passed": true,  "value": "0.41–0.93", "threshold": "0.0–1.0" },
      { "name": "electrode_path",   "passed": true,  "value": "non-degenerate" },
      { "name": "volume_clipping",  "passed": false, "value": "peak: 1.02",  "threshold": "≤ 1.0",
        "note": "Minor clipping at 3 peaks. Acceptable for this content." }
    ]
  },
  "human_review": {
    "required": true,
    "approved": null,
    "approved_by": null,
    "notes": null,
    "timestamp": null
  },
  "error": null
}
```

### Step `status` enum

Same values as top-level status: `pending | running | awaiting_human | complete | failed | skipped`

### `agent_notes`

Free text. Written by the agent when it makes non-default decisions.
Displayed in the UI next to the step so the human understands why the
settings look the way they do. This is the field that makes the system
educational — users learn the domain by reading the agent's reasoning.

### `evaluation`

The agent's quality assessment after the step completes.
- `passed` — overall pass/fail
- `score` — 0.0–1.0 composite quality score (optional, tool-specific)
- `checks` — named checks the UI can render as a checklist

If evaluation fails a hard check, `next_action.type` should be `run_step`
(agent retries with adjusted config) before escalating to `await_human`.

### `human_review`

Explicit gate. If `required: true` and `approved: null`, the pipeline stops.
- `approved_by` distinguishes human approval from agent auto-approval
  (some checks can be auto-approved if score is above threshold)

---

## Full example

```json
{
  "version": 1,
  "id": "a3f2c1d4-88b0-4e1a-9c2f-d5e6f7a8b9c0",
  "name": "my_scene — restim",
  "created": "2026-03-14T10:30:00Z",
  "updated": "2026-03-14T11:15:00Z",
  "status": "awaiting_human",
  "next_action": {
    "type": "await_human",
    "step": 0,
    "message": "Processing complete. Review the frequency and electrode path outputs before exporting."
  },
  "source": {
    "name": "my_scene.funscript",
    "path": "/Users/bruce/scenes/my_scene.funscript",
    "url": null,
    "checksum": null
  },
  "steps": [
    {
      "index": 0,
      "tool": "funscript-tools",
      "tool_version": "0.2.0",
      "label": "Convert to restim signals",
      "status": "awaiting_human",
      "config": {
        "alpha_beta_generation": {
          "algorithm": "top-right-left",
          "min_distance_from_center": 0.15
        },
        "frequency": {
          "frequency_ramp_combine_ratio": 3.0
        }
      },
      "inputs": [
        {
          "name": "my_scene.funscript",
          "path": "/Users/bruce/scenes/my_scene.funscript",
          "url": null
        }
      ],
      "outputs": [
        { "name": "my_scene.alpha.funscript",     "path": "/Users/bruce/scenes/my_scene.alpha.funscript",     "url": null },
        { "name": "my_scene.beta.funscript",      "path": "/Users/bruce/scenes/my_scene.beta.funscript",      "url": null },
        { "name": "my_scene.frequency.funscript", "path": "/Users/bruce/scenes/my_scene.frequency.funscript", "url": null }
      ],
      "started": "2026-03-14T11:00:00Z",
      "completed": "2026-03-14T11:02:14Z",
      "duration_s": 134,
      "agent_notes": "Chose top-right-left: source has wide amplitude variance across stroke range. Ramp ratio 3 — pacing is fast, keeping it reactive.",
      "evaluation": {
        "passed": true,
        "score": 0.87,
        "checks": [
          { "name": "frequency_range", "passed": true, "value": "0.41–0.93", "threshold": "0.0–1.0" },
          { "name": "electrode_path",  "passed": true, "value": "non-degenerate" },
          { "name": "volume_clipping", "passed": false, "value": "peak: 1.02", "threshold": "≤ 1.0",
            "note": "Minor clipping at 3 peaks. Acceptable for this content type." }
        ]
      },
      "human_review": {
        "required": true,
        "approved": null,
        "approved_by": null,
        "notes": null,
        "timestamp": null
      },
      "error": null
    }
  ]
}
```

---

## Upgrade path to SaaS / remote jobs

When a step runs remotely:
- `resource.url` is populated instead of `resource.path`
- `step.job_id` can be added (opaque ID from the remote job queue)
- `step.status = "running"` with no `completed` timestamp means the job
  is still in flight — poll or subscribe to find out when it's done
- `next_action.type = "await_job"` can be added as a new type when needed

The core schema doesn't change. The agent just checks `next_action.type`
and knows what to do.

---

## What this enables

| Capability | How |
|-----------|-----|
| Human resumes a session | Read `next_action` → open the right step in the UI |
| Agent continues a pipeline | Read `next_action.type == "run_step"` → call the tool CLI/API |
| Agent explains its decisions | Read `agent_notes` → display next to the step |
| UI shows quality summary | Read `evaluation.checks` → render as pass/fail checklist |
| Audit trail | Every decision, who approved it, and why is in the file |
| Long-running job support | `status: "running"` + no `completed` = in-flight |
| Future multi-tool pipeline | Add steps to the `steps` array — schema handles N tools |
