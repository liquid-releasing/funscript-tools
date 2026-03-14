# funscript-tools

Convert `.funscript` position timelines into restim estim control signals.

Built on [edger477's processing engine](https://github.com/edger477/funscript-tools) —
all algorithm credit to edger477.

---

## What it does

One `.funscript` in → ten restim-ready output files out.

Each output controls a distinct dimension of sensation: where it moves (alpha/beta),
how fast (frequency), how strong (volume), and what kind of pulse (width/rise time).

## Get started

```bash
# See what's in your file
python cli.py info my_scene.funscript

# Preview your settings before processing
python cli.py preview electrode-path --algorithm circular
python cli.py preview frequency-blend --ramp-ratio 5

# Process with defaults
python cli.py process my_scene.funscript

# See what was generated
python cli.py list-outputs . my_scene
```

## Docs

- **[User Guide](USER_GUIDE.md)** — what each setting does in plain language, creative decision guide, toolchain patterns
- **[CLI Reference](CLI_REFERENCE.md)** — every command and flag
- **[Examples](examples/README.md)** — runnable bash and Python examples
- **[Design](DESIGN.md)** — architecture, adapter pattern, deployment targets
