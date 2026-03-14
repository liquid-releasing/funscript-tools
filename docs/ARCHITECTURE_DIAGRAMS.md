# Architecture Diagrams

---

## System overview

```mermaid
graph TB
    subgraph USER["User"]
        H[Human]
    end

    subgraph FORGE["FunScriptForge (project host)"]
        UI[Streamlit UI\nproject tabs]
        PS[(project.forge-project.json\nstate + agent memory)]
        AG[Agent\norchestrator]
    end

    subgraph TOOLS["Tools (plugins)"]
        FT[funscript-tools\ncli.py]
        T2[next tool\ncli.py]
        T3[next tool\ncli.py]
    end

    subgraph DEPLOY["Deployment"]
        LOCAL[Local\nCLI subprocess]
        SAAS[SaaS\nREST API]
    end

    H -->|open project| UI
    UI -->|read/write| PS
    AG -->|read next_action| PS
    AG -->|write agent_notes, evaluation| PS
    AG -->|run step| FT
    AG -->|run step| T2
    AG -->|run step| T3
    FT -->|local| LOCAL
    FT -->|remote| SAAS
    PS -->|await_human| UI
    UI -->|human approves| PS
    AG -->|notify| H
```

---

## OSS fork adapter pattern

```mermaid
graph LR
    subgraph UPSTREAM["edger477/funscript-tools (upstream)"]
        P[processor.py]
        F[funscript.py]
        C[config.py]
    end

    subgraph FORK["liquid-releasing/funscript-tools (our fork)"]
        CLI[cli.py\nadapter]
        DEV[forge_window.py\ntkinter dev harness]
        ST[Streamlit tab\nFunScriptForge]
        API[REST API\nSaaS endpoint]
    end

    P --> CLI
    F --> CLI
    C --> CLI
    CLI --> DEV
    CLI --> ST
    CLI --> API

    style CLI fill:#4a4,color:#fff
    style UPSTREAM fill:#333,color:#aaa
```

`cli.py` is the only file that touches upstream internals.
When upstream changes, you fix `cli.py`. Everything else is untouched.

---

## Project state machine

```mermaid
stateDiagram-v2
    [*] --> pending : project created

    pending --> running : agent or user starts step
    running --> awaiting_human : step complete, review required
    running --> complete : step complete, no review needed
    running --> failed : step errored

    awaiting_human --> running : human approves → next step starts
    awaiting_human --> running : human requests rerun with new config

    failed --> running : agent retries with adjusted config
    failed --> awaiting_human : agent escalates to human

    complete --> [*]
```

---

## Agent loop

```mermaid
flowchart TD
    START([read project.forge-project.json]) --> CHECK{next_action.type}

    CHECK -->|run_step| RUN[call tool CLI or API\nwith step config]
    RUN --> EVAL[evaluate output\nrun named checks]

    EVAL --> PASS{evaluation.passed?}
    PASS -->|yes| WRITE[write agent_notes\nmark step complete]
    PASS -->|no, retries left| ADJUST[adjust config\nincrement retry count]
    ADJUST --> RUN

    PASS -->|no, retries exhausted| ESCALATE[set next_action = await_human\nwrite agent_notes explaining failure]

    WRITE --> NEXT{more steps?}
    NEXT -->|yes, next step automated| CHECK
    NEXT -->|yes, next step needs human| NOTIFY

    CHECK -->|await_human| NOTIFY[notify user\nsurface step in UI]
    NOTIFY --> WAIT([wait for human input])
    WAIT --> APPROVED{human_review.approved?}
    APPROVED -->|yes| CHECK
    APPROVED -->|no, rerun requested| ADJUST

    CHECK -->|complete| DONE([project complete\nnotify user])

    ESCALATE --> NOTIFY
```

---

## Multi-step pipeline (future state)

```mermaid
graph LR
    SRC[source\nfunscript] --> S1

    subgraph S1["Step 1 — funscript-tools"]
        direction TB
        S1A[cli.preview_*\nevaluate options]
        S1B[cli.process\nrun pipeline]
        S1C[human review\napprove outputs]
        S1A --> S1B --> S1C
    end

    subgraph S2["Step 2 — next tool"]
        direction TB
        S2A[preview]
        S2B[process]
        S2C[human review]
        S2A --> S2B --> S2C
    end

    subgraph S3["Step 3 — export / package"]
        direction TB
        S3A[assemble outputs]
        S3B[final approval]
        S3A --> S3B
    end

    S1 -->|outputs| S2
    S2 -->|outputs| S3
    S3 --> OUT[ready to use\nin restim / player]
```

Each step reads its inputs from the project file.
Outputs are written back to the project file before the next step starts.
A human approval gate can be placed after any step.
Long-running steps (video render, etc.) run async — the project file
holds `status: running` until they complete.

---

## Deployment targets

```mermaid
graph TD
    CLI_PY[cli.py\nadapter]

    CLI_PY --> A[python cli.py process ...\nscripts / CI pipelines]
    CLI_PY --> B[forge_window.py\ntkinter dev harness\npython forge.py]
    CLI_PY --> C[Streamlit tab\nFunScriptForge desktop\nPyInstaller bundle]
    CLI_PY --> D[Streamlit tab\nFunScriptForge SaaS\ncloud deploy]

    style CLI_PY fill:#4a4,color:#fff
```

Same adapter. Same function signatures. Different rendering layer.
```
