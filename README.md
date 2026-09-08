# x32scene

[![PyPI](https://img.shields.io/pypi/v/x32scene)](https://pypi.org/project/x32scene/)

Create X32 / M32 console files on the fly. Build, update, modify, transfer settings using AI via Python.

# Why x32scene

The X32 is a wildly capable mixer. Almost anything can be routed anywhere between hardware
inputs and outputs. With that capability comes a lot of complexity and a steep learning
curve, and developing a great scene is a lot of work: the right EQs, frequency-keyed gate
settings, the aux setup for each player's in-ears, the routing to the stage boxes. Copying
any of it by hand, one control at a time, is slow and easy to get wrong. **x32scene**
exposes commands that do that work on the scene file and save a new scene that loads
onto the desk.

Some of the things it does that are hard to do any other way:

- **Move a whole set of inputs to a second stage box.** Each channel's source is re-pointed
  through the routing banks and its head-amp gain and phantom travel with it, because
  the X32 stores gain by physical input, not by channel; the move is all-or-nothing, with
  every target input range-checked first.
- **Carry one player's in-ear mix into the next band's scene.** A monitor mix is a bus
  strip plus every sender's send into it, both sides of a stereo pair; `transplant` moves
  exactly those lines and nothing else, and `snippet --bus` writes the same mix as a
  snippet the desk recalls mid-changeover while every other aux stays put. Loaded on a
  console, a full pull afterwards differed from the starting scene in only that pair's
  lines.
- **Set an effect by parameter name.** Every one of the 61 effect types is mapped
  parameter by parameter, so "plate in FX 4, decay 2.1, damping 8 kHz" is one command,
  written in the desk's own token format; a type change starts from the parameter line
  the desk itself writes.
- **Describe a whole night in one file.** A JSON plan — names, head amps, EQ, dynamics,
  monitor mixes, effects, routing, outputs — applied to a known-good template, every
  value checked against the console's vocabulary, and the result refused if it changed
  anything the plan did not name.
- **Know what actually changed.** `diff --by-strip` says "channel 23, send to bus 9,
  level −14.0 → −11.0", and `history` follows one parameter across every scene you have
  saved.

## What it is

An X32 stores its state as plain text, one parameter per line: input patching, head amps,
every monitor mix, effects, routing. The console and its editor edit that state one
control at a time. x32scene works on the files instead. It parses every kind the console
reads and writes, keeps each file byte for byte (`Scene.parse(text).dump() == text`), and
applies edits so that the result differs from its source by exactly the intended lines —
which `x32scene diff` shows. Edit commands never overwrite the file they read, and will not
land on a file that already exists unless you pass `--force`; the changed file is loaded on
the console by you.

The live layer is read-only: `pull` captures the running desk as a scene file so every
command works on the live console, `desk` reports its identity, status and memory slots,
`meters` reports levels. Pushing changes to the desk over the network is not a feature.

Most read commands have a `--json` form, the vocabularies the console accepts are listed by
commands, and the reference docs state which facts were observed on hardware and which
were read from a manual, so the tool can be driven by an AI agent as well as by hand.

## What it handles

| File | What it is | Read | Write |
|---|---|---|---|
| `.scn` | a whole console | yes | every edit command, `band-setup`, `transplant` |
| `.snp` | a snippet — lines the desk recalls *in place*, everything else untouched | yes | `snippet` |
| `.chn` | one channel strip, per section | yes | `extract-preset` / `apply-preset` |
| `.efx` | one effect slot | yes | `extract-fx` / `apply-fx` |
| `.rou` | the input routing banks | yes | `extract-routing` / `apply-routing` |
| `.shw` | a show: cues that recall scenes and snippets | yes | `show-build` |

[docs/capabilities.md](https://github.com/phierceweb/x32scene/blob/main/docs/capabilities.md)
lists every command by the job it does.

## What the operations are

**Reading.** Channel sources resolved through the routing banks and user patch, every
output's feed and tap point, the mix buses and their stereo pairs, one monitor mix or all
of them as a matrix, the USB record map, the FX rack with parameters by name, DCA and
mute groups, the desk-wide settings (monitor, talkback, oscillator, recorder, user-assign
buttons) in words, and a markdown report of the whole scene.

**Comparing.** `diff` between two files, by path or grouped by strip with the moved
fields named; `history` of one parameter across a dated library; `audit` of a library's
structural invariants; `live-diff` of the desk against a file.

**Editing.** Strip settings (name, fader, mute, pan, EQ, low cut, compressor, gate), FX
slots by parameter name, a channel's input source, an output's feed, the routing banks.
Values are written in the console's own token formats, checked against its vocabularies,
and mirrored to a stereo-linked partner unless told not to.

**Carrying between scenes.** `transplant` copies chosen lines from one scene into another
and touches nothing else: a whole monitor mix (the bus strip and every send into it), any
path pattern, or a channel's sections with the head amp re-mapped. Presets do the same
one strip, slot or bank at a time.

**Snippets.** The delta between two scenes, edits applied in memory, or one monitor mix
whole, written with the filter masks the desk reads derived from the body. Loaded on a
console, a snippet of one bus pair changed that pair's lines and no others; the details are
in the console-behaviour doc.

**Plans and shows.** `band-setup` applies one JSON plan (names, head amps, processing,
monitor mixes, effects, routing, outputs) to a template, validates every value first, and
refuses to write if the result strays outside the paths the plan named. `show-build`
writes a show index with cues and its companion files in the shape X32-Edit imports.

**Checks.** `preflight` compares a scene against a documented rig — outputs, monitor
skeleton, routing, stereo links, send taps, groups — and a stage sidecar recording which
jack and which person each output feeds. Exit 1 on a failure.

## What the desk does with a file

A file that round-trips and diffs clean can still not do what was intended once the
console loads it. The docs record what was learned by loading files on hardware and
reading the state back: the token formats a bad value silently aborts a line on, the
frequencies and effect parameters the desk snaps to its own grid, how stereo-linked pairs
reconcile on recall, and the difference between the desk's USB import and X32-Edit's Load
(which pushes a file's lines from the computer). See
[docs/console-behavior.md](https://github.com/phierceweb/x32scene/blob/main/docs/console-behavior.md)
and its load-test loop before trusting a generated file at a gig.

## Scope

- Files and a read-only view of the desk. No network writes to the console.
- Round-trip and diff prove a file is structurally correct and changed only where
  intended; the console is the only proof it is semantically correct.
- Snippets and presets loaded from a USB stick go through the desk's own recall and
  header masks; X32-Edit's Load pushes the lines instead. Both were used in testing; the
  USB route was not observed directly.
- Pre-1.0: pin to a tagged release.

## How it relates to other tools

| Tool | What it is | How x32scene relates |
|---|---|---|
| X32-Edit, Mixing Station | Editors for the live console | They change the desk one control at a time. x32scene works on the files those editors save and load, and shows what changed between two of them |
| Patrick-Gilles Maillot's X32 utilities and protocol document | The reference for the console's OSC dialect, and command-line tools that copy, save and drive it | x32scene's OSC layer implements the read side of that dialect; its enumerations were checked against a console and the document's corrections are noted where the desk disagreed |
| OSC libraries (python-osc and the like) | Generic OSC transport | x32scene carries its own small X32 dialect encoder, because the console's node queries and meter blobs are not plain OSC |
| A scene library in git | Version control of `.scn` files | x32scene adds a diff in the console's terms and edits that keep every other byte in place |

## Install

```bash
pip install x32scene
```

Python 3.12 or newer, one dependency ([pf-core](https://pypi.org/project/pf-core/)).
Releases are tagged; `main` is the development line. Release notes:
[CHANGELOG.md](https://github.com/phierceweb/x32scene/blob/main/CHANGELOG.md).

## Commands

```bash
x32scene info | inputs | ports | buses | iem | iem-matrix | record-map | fx | dca | console | report   scene.scn
x32scene header FILE                       # any file's header decoded
x32scene show show.shw                     # a show index
x32scene diff a.scn b.scn [--by-strip]     # what changed
x32scene history PATH… --dir DIR           # one parameter across a library
x32scene set-eq | set-comp | set-gate | set-lowcut | set-fader | set-mute | set-pan | rename   scene.scn STRIP … -o out.scn
x32scene set-fx | set-input | set-output | set-routing   scene.scn … -o out.scn
x32scene transplant src.scn dst.scn -o out.scn --bus 1 --path /headamp/000 --ch 3 --scope eq
x32scene snippet a.scn b.scn -o delta.snp | a.scn -o mix.snp --bus 9 | a.scn -o eq.snp --edit "set-eq 5 2 --gain 3"
x32scene band-setup template.scn plan.json -o out.scn [--snippet out.snp]
x32scene show-build -o DIR --name Night --scene a.scn --snippet x.snp --cue "1 Opener scene=0"
x32scene preflight scene.scn --config rig.json [--stage stage.json]
x32scene pull reference.scn -o live.scn | live-diff scene.scn | desk | meters   # --ip or X32SCENE_IP
```

Every command, flag and environment variable:
[docs/cli.md](https://github.com/phierceweb/x32scene/blob/main/docs/cli.md). Example
inputs: [`config/example-preflight.json`](https://github.com/phierceweb/x32scene/blob/main/config/example-preflight.json),
[`config/example-plan.json`](https://github.com/phierceweb/x32scene/blob/main/config/example-plan.json),
[`config/example-stage.json`](https://github.com/phierceweb/x32scene/blob/main/config/example-stage.json).

## Use it from Python

```python
from x32scene import Scene
from x32scene.services import transforms as T, transplant

sc = Scene.load("scene.scn")
T.rename_channel(sc, 1, "Kick In")
T.set_headamp(sc, "local", 1, gain_db=30.0, phantom=False)
sc.save("out.scn")

other = Scene.load("friday.scn")
transplant.transplant(sc, other, buses=[9])      # this scene's bus-9 mix into the other
```

The band-setup workflow is one call and raises rather than write anything outside the plan:

```python
from x32scene.orchestrators.band_swap import load_plan, run

report = run("template.scn", load_plan("plan.json"), "out.scn")
```

## Working from a checkout

```bash
git clone https://github.com/phierceweb/x32scene && cd x32scene
bin/run setup          # venv, editable install
bin/run pytest         # the suite
bin/run lint           # ruff + the pf-core structural gate
bin/run x32scene …     # the CLI, with .env loaded
```

`X32SCENE_CORPUS=~/path/to/scenes bin/run pytest tests/test_roundtrip.py` runs the
round-trip test over your own library.

## Docs

[docs/README.md](https://github.com/phierceweb/x32scene/blob/main/docs/README.md) is the
index, maintained beside the docs.

- [capabilities.md](https://github.com/phierceweb/x32scene/blob/main/docs/capabilities.md) — everything x32scene does, by job, and what it deliberately does not do
- [cli.md](https://github.com/phierceweb/x32scene/blob/main/docs/cli.md) — every command, flag and environment variable
- [format.md](https://github.com/phierceweb/x32scene/blob/main/docs/format.md) — every file kind and every line, field by field; the enumerations; what is verified against hardware and what is inferred
- [console-behavior.md](https://github.com/phierceweb/x32scene/blob/main/docs/console-behavior.md) — what the desk does when it loads a file, and how a file reaches the desk
- [routing.md](https://github.com/phierceweb/x32scene/blob/main/docs/routing.md) — the two-layer routing model, resolving a channel to its jack, the record map
- [stage-sidecar.md](https://github.com/phierceweb/x32scene/blob/main/docs/stage-sidecar.md) — recording which jack and which person each output feeds, and what `preflight` checks against it

## Built on pf-core

x32scene is built on [pf-core](https://github.com/phierceweb/pf-core)
([PyPI](https://pypi.org/project/pf-core/)), a Python foundation for LLM-facing
applications. x32scene uses its atomic-write utilities, structured logging, exception
boundary and config-from-env, and its structural gate, which fails the build when a file
outgrows its line budget.

For other phierceweb projects, see [github.com/phierceweb](https://github.com/phierceweb).

## Contributing

[CONTRIBUTING.md](https://github.com/phierceweb/x32scene/blob/main/CONTRIBUTING.md): never
break the round-trip, run `bin/run lint` and the suite, and a real scene file that does not
round-trip is the most useful bug report — with the console model and firmware, not the file.

## Security

[SECURITY.md](https://github.com/phierceweb/x32scene/blob/main/SECURITY.md). x32scene
sends nothing off the local network, stores no credentials, and its live layer only reads
the desk.

## License

MIT — see [LICENSE](https://github.com/phierceweb/x32scene/blob/main/LICENSE).

Not affiliated with, endorsed by, or sponsored by Music Tribe. BEHRINGER, X32, and M32 are
trademarks of Music Tribe Global Brands Ltd. See
[TRADEMARKS.md](https://github.com/phierceweb/x32scene/blob/main/TRADEMARKS.md).
