# What x32scene can do

The whole toolkit on one page, organized by the job in front of you. Every command is
`x32scene <name>`; most take `--json` for machine output. Edit commands **always write a
new file**, refuse to overwrite an input, and refuse an output that already exists unless
you pass `--force`, so your saved scenes are never touched — the way to change a real scene
is to write a copy, load-test it, and adopt it. Reading a file whose shape does not match
its kind warns on stderr without refusing the file.

The file kinds it handles, all byte-faithful (`Scene.parse(text).dump() == text`):

| Kind | What | Read | Write |
|---|---|---|---|
| `.scn` | a whole console | yes | yes — every edit command, `band-setup`, `transplant` |
| `.snp` | a snippet: lines the desk recalls *in place*, everything else untouched | yes | yes — `snippet`, `band-setup --snippet` |
| `.chn` | one channel strip, per section | yes | yes — `extract-preset` / `apply-preset` |
| `.efx` | one effect slot | yes | yes — `extract-fx` / `apply-fx` |
| `.rou` | the input routing banks | yes | yes — `extract-routing` / `apply-routing` |
| `.shw` | a show: cues that recall scenes and snippets | yes | yes — `show-build` |

[format.md](format.md) documents every line of every kind; [console-behavior.md](console-behavior.md)
what the desk does with them.

---

## Table of contents

- [Read a scene](#read-a-scene)
- [Compare and track](#compare-and-track)
- [Edit one thing](#edit-one-thing)
- [Carry things between scenes](#carry-things-between-scenes)
- [Change the desk without loading a whole scene](#change-the-desk-without-loading-a-whole-scene)
- [Describe a whole night](#describe-a-whole-night)
- [Check a scene before a gig](#check-a-scene-before-a-gig)
- [The live desk (read-only)](#the-live-desk-read-only)
- [Getting a file onto the desk](#getting-a-file-onto-the-desk)
- [What it does not do](#what-it-does-not-do)

## Read a scene

| Command | Answers |
|---|---|
| `info` | title, channel and bus names |
| `inputs` | each channel's physical source, resolved through the routing banks and user patch |
| `ports` | every output bank: what feeds each jack, its tap point, mirrors; `--config` marks physical vs virtual outputs, `--stage` adds the jack, device and wearer |
| `buses` | the 16 mix buses: stereo pairs, which feed an FX slot, PRE/POST tallies |
| `iem BUS` | one monitor mix: who is in it and at what level |
| `iem-matrix` | every monitor mix at once, senders down, buses across; `--compare` shows before>after against another scene |
| `record-map` | the USB card tracks a DAW receives, in order |
| `fx` | the FX rack: type, source, every parameter by name |
| `fx-types [CODE]` | every effect type the desk offers, where it may go, its parameters and default values |
| `dca` | DCA and mute-group membership |
| `console` | the desk-wide settings in words: monitor and solo modes, talkback and its destinations, oscillator, USB recorder, automix, DP48, output delays, iQ speakers, the three user-assign layers decoded |
| `explain` | all of the above in one readout, for troubleshooting |
| `report` | the scene as a markdown snapshot — the document a rig keeps by hand |
| `header FILE` | a file's header decoded: scene safes, snippet filters, a preset's slot, kind and sections. A `.chn` header is optional, and a file without one exits 1 |
| `show FILE.shw` | a show index: each cue and what it recalls, each scene's safes, each snippet's filters |
| `vocab routing\|taps\|sources` | the words the console accepts, for typing edits |

## Compare and track

| Command | Answers |
|---|---|
| `diff A B` | what changed, path by path; `--by-strip` groups by strip and names the fields that moved |
| `history PATH…` | one path's timeline across a dated scene library |
| `audit DIR` | structural invariants across a whole library, and where the record patch changed |
| `presets-diff DIR SCENE` | which channel presets in a folder no longer match the channel they are named for, path by path; exit 1 when one drifts or cannot be read |
| `live-diff SCENE` | the running desk against a file |

## Edit one thing

Every edit writes a new file and reports exactly what it wrote. The strip editors take a
strip — a channel number or a path like `/bus/01` — and mirror to the partner of a
stereo-linked pair unless told `--no-link`. `rename` and `set-pan` are the exceptions
among them: a linked pair's names and pans are individually meaningful, so they never
mirror and take no `--no-link`. The rest address a slot, a channel, an output, a bank or a second scene.

| Command | Sets |
|---|---|
| `rename`, `set-fader`, `set-mute`, `set-pan` | a strip's name, fader, mute, pan |
| `set-eq STRIP BAND`, `set-lowcut`, `set-comp`, `set-gate` | one EQ band, the low cut, the compressor, the gate, by parameter |
| `set-fx SLOT` | an effect's type (parameters reset to the desk's own defaults), source, and parameters by name, formatted like the desk's token |
| `set-input CH` | a channel's input source by name (`"aes50-a 3"`, `"card 7"`) |
| `move-inputs CH:IN… --to A\|B` | a set of channels onto stage-box inputs, each one's head-amp gain and phantom travelling with it (`--no-gain` leaves them); all-or-nothing, and refused when it would also re-source or re-gain a channel it did not name |
| `set-output BANK N` | an output's source (`"bus 12"`, `"direct out ch 5"`), tap point and polarity |
| `set-routing KEY` | a routing bank's blocks by label, checked against the console's vocabulary; `switch REC\|PLAY` |
| `set-bus-link BUS on\|off` | links or unlinks a stereo mix-bus pair the way the desk's link key does — on link the even bus takes the odd bus's sends and strip settings (not its name) and the matrix-send pans spread; on unlink only the link and pans move — and names the outputs either bus feeds |
| `port-iem` | one scene's output routing onto another |

## Carry things between scenes

| Command | Does |
|---|---|
| `transplant SRC DST` | copies chosen lines from one scene into another and touches nothing else: `--bus N` a whole monitor mix (the bus strip and every send into it, both sides of a pair), `--path GLOB` any lines, `--ch N --scope S` a channel's sections with the head amp re-mapped |
| `extract-preset` / `apply-preset` | a channel's sections as a `.chn`, loaded onto any channel of any scene; `extract-preset --all` writes one per named channel, regenerating a preset folder from a scene |
| `extract-fx` / `apply-fx` | an effect slot as a `.efx`, loaded into any slot |
| `extract-routing` / `apply-routing` | the routing banks as a `.rou`, loaded whole or per bank |

## Change the desk without loading a whole scene

A **snippet** is recalled in place: only the lines it carries change. `snippet` writes one
three ways:

- `snippet A B -o OUT.snp` — the delta between two scenes. One that links or unlinks a bus
  pair warns when it carries that pair's lines: a snippet cannot carry the link.
- `snippet A -o OUT.snp --edit "set-eq 5 2 --gain 3" --edit "set-fader 5 -3"` — edits
  applied in memory; only what moved is written, one filter per family touched.
- `snippet A -o OUT.snp --bus 9` — one monitor mix, whole, as it is in the scene. `--only
  GLOB` does the same for any path pattern; with two scenes both keep the delta. This is
  the "swap one band's aux for another's mid-changeover" move, and it was load-tested on a
  console: only that bus pair moved, every other aux stayed
  ([console-behavior.md](console-behavior.md#getting-a-file-onto-the-desk)).

The header's filter masks are derived from the body, so a fader edit is one line under one
filter, and a bus mix is the bus and its sends and nothing else.

## Describe a whole night

`band-setup TEMPLATE PLAN.json -o OUT.scn [--snippet OUT.snp]` applies one JSON plan:
title, channel names, presets, head amps, faders and mutes, per-channel low cut / EQ /
compressor / gate / pan / source, DCA membership, monitor-mix copies and send trims, FX
slots, routing banks, every output bank. Every value is validated against the console's
vocabulary before a line is written, and the result is verified to differ from the
template only in the paths the plan named. `--snippet` writes the same change as a
snippet. Every section, and the rules a plan must satisfy, are in
[band-plan.md](band-plan.md); start from [`config/example-plan.json`](../config/example-plan.json).

`show-build -o DIR --name NAME --scene … --snippet … --cue "1 Opener scene=0 snippet=1"`
writes a show — the index plus its companion files — in the shape X32-Edit imports.

## Check a scene before a gig

| Command | Checks |
|---|---|
| `preflight SCENE --config rig.json [--stage stage.json]` | the scene against the documented rig: outputs, monitor skeleton, routing, links, send taps and presence, groups; `FAIL` exits 1. The config's sections are in [preflight-config.md](preflight-config.md) |
| `preflight SCENE --regenerate rig.json` | nothing: writes the config SCENE satisfies — every section the scene holds, stable enough that `git diff` on a tracked copy shows what moved on the desk. The console's jack count is not in a scene, so `monitor.physical_outputs` and `require_reachable` are not written ([generating one](preflight-config.md#generating-one)) |
| `ports --stage` | the jack, device and wearer each output feeds, from the [stage sidecar](stage-sidecar.md) |
| `audit DIR` | a library's structural invariants |

## The live desk (read-only)

| Command | Reads |
|---|---|
| `pull REFERENCE -o OUT.scn` | the running desk's state into a scene file, so every command above works on the live desk |
| `desk` | who the desk is, what it is doing (selected strip, solo, USB recorder, expansion card), the preferences that matter for a show, and every occupied scene, snippet, cue and preset slot with its header decoded |
| `meters [inputs\|buses\|outputs\|sends\|fx\|monitor\|recorder]` | each slot's peak over a short window, in dBFS, named from a scene |
| `watch REFERENCE` | a timestamped log of every change made on the desk while it runs — by the surface or another client — each moved field named, then the net change against the start; `--snippet` saves that net change as a snippet |

Nothing here writes to the desk; `watch` only subscribes to its change reports
(`/xremote`). Pushing changes over the network is deliberately not a feature: a file you
load is a deliberate act with a confirm step, a push is not.

## Getting a file onto the desk

- A `.scn`, `.snp`, `.chn`, `.efx` or `.rou` on a USB stick loads from the desk's own
  Scenes, Library and Utility pages. That is the path that honours a snippet's header
  masks and a preset's recall scope on the desk itself.
- X32-Edit imports the same files and its **Load** buttons push them from the computer:
  see [console-behavior.md](console-behavior.md#getting-a-file-onto-the-desk).
- Either way: load-test, save the desk's state back, and `diff`. The desk snaps some
  values to its own grid; the diff shows exactly what it kept.

## What it does not do

- Push edits to the desk over OSC (shelved on purpose; the read side is complete).
- Write DP48 personal-monitor presets, or the MIDI fields of a cue (written as none).
- Name the graphic EQs' bands with certainty: they read as the standard ISO series and
  are refused for writing.
