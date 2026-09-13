# Using x32scene from Python

The library behind the CLI. Every command in [cli.md](cli.md) is a thin presentation layer
over these calls, so anything the CLI does is available in a script — and a few things that
are only sensible in code, like applying one transform across a directory of scenes.

This page is the map, not an inventory. Read the module's own docstrings for exact
signatures; they are the reference, and they do not go stale.

---

## Table of contents

- [The layers](#the-layers)
- [Scene and Line](#scene-and-line)
- [The one invariant](#the-one-invariant)
- [Services](#services)
- [Orchestrators](#orchestrators)
- [What the library does not do](#what-the-library-does-not-do)
- [Worked examples](#worked-examples)
- [Adding a new operation](#adding-a-new-operation)

## The layers

| Layer | Import | What lives there |
|---|---|---|
| Model | `from x32scene import Scene, Line` | parse, address, edit and dump a file |
| Tables | `x32scene.tables`, `x32scene.tables_fx` | the console's enumerations and token formats |
| Services | `x32scene.services.<name>` | one concern each: transforms, routing, presets, fx, iem, diff, snippets, preflight, osc … |
| Orchestrators | `x32scene.orchestrators.band_swap` | multi-step workflows: plan → apply → verify → save |

Import from the layer you need. `x32scene.cli` and the `_views*` modules are the CLI's own
presentation and exception boundary — do not import them; they print and raise for a
terminal.

**The library never logs and never prints.** It raises `ValueError` / `KeyError` for a bad
value or a missing path and leaves the decision to the caller. Logging and the pf-core
exception boundary are adopted at the CLI only.

## Scene and Line

```python
from x32scene import Scene

sc = Scene.load("scene.scn")        # or Scene.parse(text)
line = sc.get("/ch/01/mix")         # Line | None — the path is the index
line.args                           # ['ON', '+6.5', 'ON', '+0', 'OFF', '-oo']
line.set_arg(1, "-3.0")             # marks the line dirty; only dirty lines are rebuilt
sc.save("out.scn")                  # atomic write, LF endings
```

`Scene.find(prefix)` returns every line whose path starts with a **prefix** — `"/headamp/"`,
`"/ch/01/"`. It is not a glob; a trailing `*` matches nothing. `Line.dirty` says whether a
line has been changed — `band_swap` counts them to report how much a plan moved.

Address a line by its **exact path**. `/outputs/main/01` and `/outputs/main/01/delay` share
a prefix, and a startswith match over `/ch/01/mix` also catches all sixteen of its sends.

## The one invariant

`Scene.parse(text).dump() == text`

Every line is stored verbatim and rebuilt only when a transform changes it. That is what
makes an edit provable: the output differs from its source by exactly the intended lines,
and `diff` shows it. Any change that breaks round-trip on a real file is a bug regardless
of what else it fixes.

Two things round-trip does **not** prove, both of which have bitten:

- **Field-count shape.** A five-field even-bus send line round-trips and diffs clean while
  being a line no console ever wrote. So does a three-field `rec` output. See
  [format.md](format.md#bus-sends--and-the-oddeven-field-count-invariant).
- **Semantic correctness.** Only the console proves that. See
  [console-behavior.md](console-behavior.md).

## Services

One concern per module. The ones a script reaches for first:

| Module | Does |
|---|---|
| `transforms` | names, faders, mutes, pan, head amps, output taps |
| `stagebox` | channels moved onto AES50 stage-box inputs, head amps travelling with them |
| `channelfx` | EQ bands, low cut, compressor, gate — the per-strip processing |
| `routing`, `routing_edit` | resolve a channel to its jack, the outputs a bus feeds; set inputs, outputs and routing banks |
| `iem` | monitor mixes: one send, a whole mix copied, pair-aware targets |
| `buslink` | link or unlink a stereo bus pair as the desk does: `set_bus_link(sc, bus, on) -> BusLinkEdit`; `relinked_pairs(a, b, paths)` for the pairs whose link differs that `paths` carry a line of |
| `transplant` | carry chosen lines from one scene into another |
| `presets` | `.chn` extract/apply, with the head-amp index remapped |
| `preset_library` | a folder of `.chn` against a scene: `check_library(sc, dir) -> list[PresetCheck]`; `extract_library(sc) -> (presets, unnamed, shared)` for one preset per named channel, skipping every channel on a shared file name |
| `fx` | effect types, sources and parameters by name |
| `snippets` | build a `.snp` from a delta, with the header masks derived from the body |
| `diff` | `diff(a, b) -> list[Change]` |
| `preflight`, `stage` | check a scene against a config and a sidecar |
| `preflight_regen` | the config a scene satisfies: `regenerate(sc, source, generated) -> dict`; `dumps(doc)` is the stable file text |
| `osc`, `desk`, `meters` | the read-only live layer |
| `watch` | changes on the running desk as they happen: `subscribe(transport)` before pulling `start` returns a `Subscription` to pass as `pull_scene_like(..., between=)`, which renews `/xremote` and keeps what the desk pushes meanwhile; `Watch(reference, start).run(transport, backlog=sub.backlog)` yields each `Changed`, dated by the push that reported it; `flush(transport)` reads back what an interrupted run left waiting; `summary()` is the net change of the paths that answered and the paths left `unanswered`; transport and clock are injectable |

Two conventions run through all of them:

- **A strip is `int | str`.** A channel number, or a path — `"/bus/01"`, `"/main/st"`,
  `"/dca/3"`. `transforms.strip_path` does the conversion.
- **`linked=` controls mirroring.** `None` (the default) mirrors to the partner of a
  stereo-linked pair when the console would; `False` edits one side only. A name and a
  pan are never mirrored and take no such argument.

## Orchestrators

`band_swap` is the only one. It applies a [plan](band-plan.md) and refuses to write
anything outside it:

```python
from x32scene.orchestrators.band_swap import load_plan, run

report = run("template.scn", load_plan("plan.json"), "out.scn")
report["lines_changed"]
```

`run` validates, applies, verifies against the template and saves — raising rather than
writing a scene the plan did not describe. To inspect before saving, call `apply_plan` and
`verify` yourself.

## What the library does not do

- **It does not refuse to overwrite.** `Scene.save(path)` writes where you point it. The
  input/output guards are the CLI's (`_cli_files.refuse_overwrite`), so a script that edits
  a real scene library must not point `save` at its source.
- **It does not push to the desk.** The OSC layer reads; writing over the network is
  deliberately not a feature.
- **It does not validate a file on load.** `services.validate` computes the shape findings
  (`findings`, `kind_of`), but only the CLI's checked readers call it and print them — a
  script gets them by asking. `preflight` and `audit` are the semantic checks, and they are
  likewise services you call explicitly.

## Worked examples

Re-point a whole input set to a second stage box, gain and phantom travelling with it:

```python
from x32scene import Scene
from x32scene.services import stagebox

sc = Scene.load("scene.scn")
for m in stagebox.move_to_stagebox(sc, [(1, 1), (2, 2), (3, 3)], port="B"):
    print(m.ch, m.old_source, "->", m.new_source, m.headamp, m.carried)
sc.save("out.scn")
```

Every move is checked before a line changes: a refused move raises `ValueError`, or
`KeyError` for a channel the scene has no line for, and leaves the scene as it was.
`transforms.move_inputs_to_stagebox(sc, {1: 1}, port="A")` is the same move taking a
dict and returning the count.

Carry one player's monitor mix into the next band's scene, and prove nothing else moved:

```python
from x32scene import Scene
from x32scene.services import transplant
from x32scene.services.diff import diff

src, dst = Scene.load("friday.scn"), Scene.load("saturday.scn")
changed = transplant.transplant(src, dst, buses=[9])
assert {c.path for c in diff(Scene.load("saturday.scn"), dst)} == set(changed)
dst.save("out.scn")
```

Sweep a library and report one parameter:

```python
import glob
from x32scene import Scene

for path in sorted(glob.glob("scenes/*.scn")):
    line = Scene.load(path).get("/headamp/003")
    print(path, line.args if line else "—")
```

## Adding a new operation

1. Put it in the `services/` module that owns that concern — a new module only for a new
   concern. Multi-step workflows go in `orchestrators/`.
2. Take and return plain values; raise `ValueError`/`KeyError`. No logging, no printing, no
   `sys.exit`.
3. Write the token in the console's own format and check it against `tables`. A value that
   is in range but wrong-format is silently rejected by the desk
   ([console-behavior.md](console-behavior.md#a-bad-token-aborts-the-rest-of-the-line)).
4. Mirror to a stereo-linked partner where the console would, and take `linked=` to opt out.
5. Add a test against `tests/fixtures/`, including round-trip.
6. Expose it in `cli.py` / `_cli_edits.py` if it should be a command, and add it to
   [cli.md](cli.md).
