# What x32scene can do

The whole toolkit on one page, organized by the job in front of you. Every command is
`x32scene <name>`; most take `--json` for machine output. Edit commands **always write a
new file** and refuse to overwrite an input, so your saved scenes are never touched — the
way to change a real scene is to write a copy, load-test it, and adopt it.

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
| `header FILE` | any file's header decoded: scene safes, snippet filters, a preset's slot, kind and sections |
| `show FILE.shw` | a show index: each cue and what it recalls, each scene's safes, each snippet's filters |
| `vocab routing\|taps\|sources` | the words the console accepts, for typing edits |

## Compare and track

| Command | Answers |
|---|---|
| `diff A B` | what changed, path by path; `--by-strip` groups by strip and names the fields that moved |
| `history PATH…` | one path's timeline across a dated scene library |
| `audit DIR` | structural invariants across a whole library, and where the record patch changed |
| `live-diff SCENE` | the running desk against a file |

## Edit one thing

Every edit takes a strip (a channel number or a path like `/bus/01`), mirrors to the
partner of a stereo-linked pair unless told `--no-link`, and reports exactly what it wrote.

| Command | Sets |
|---|---|
| `rename`, `set-fader`, `set-mute`, `set-pan` | a strip's name, fader, mute, pan |
| `set-eq STRIP BAND`, `set-lowcut`, `set-comp`, `set-gate` | one EQ band, the low cut, the compressor, the gate, by parameter |
| `set-fx SLOT` | an effect's type (parameters reset to the desk's own defaults), source, and parameters by name, formatted like the desk's token |
| `set-input CH` | a channel's input source by name (`"aes50-a 3"`, `"card 7"`) |
| `set-output BANK N` | an output's source (`"bus 12"`, `"direct out ch 5"`), tap point and polarity |
| `set-routing KEY` | a routing bank's blocks by label, checked against the console's vocabulary; `switch REC\|PLAY` |
| `port-iem` | one scene's output routing onto another |

## Carry things between scenes

| Command | Does |
|---|---|
| `transplant SRC DST` | copies chosen lines from one scene into another and touches nothing else: `--bus N` a whole monitor mix (the bus strip and every send into it, both sides of a pair), `--path GLOB` any lines, `--ch N --scope S` a channel's sections with the head amp re-mapped |
| `extract-preset` / `apply-preset` | a channel's sections as a `.chn`, loaded onto any channel of any scene |
| `extract-fx` / `apply-fx` | an effect slot as a `.efx`, loaded into any slot |
| `extract-routing` / `apply-routing` | the routing banks as a `.rou`, loaded whole or per bank |

## Change the desk without loading a whole scene

A **snippet** is recalled in place: only the lines it carries change. `snippet` writes one
three ways:

- `snippet A B -o OUT.snp` — the delta between two scenes.
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
snippet. Start from [`config/example-plan.json`](../config/example-plan.json).

`show-build -o DIR --name NAME --scene … --snippet … --cue "1 Opener scene=0 snippet=1"`
writes a show — the index plus its companion files — in the shape X32-Edit imports.

## Check a scene before a gig

| Command | Checks |
|---|---|
| `preflight SCENE --config rig.json [--stage stage.json]` | the scene against the documented rig: outputs, monitor skeleton, routing, links, send taps and presence, groups; `FAIL` exits 1 |
| `ports --stage` | the jack, device and wearer each output feeds, from the [stage sidecar](stage-sidecar.md) |
| `audit DIR` | a library's structural invariants |

## The live desk (read-only)

| Command | Reads |
|---|---|
| `pull REFERENCE -o OUT.scn` | the running desk's state into a scene file, so every command above works on the live desk |
| `desk` | who the desk is, what it is doing (selected strip, solo, USB recorder, expansion card), the preferences that matter for a show, and every occupied scene, snippet, cue and preset slot with its header decoded |
| `meters [inputs\|buses\|outputs\|sends\|fx\|monitor\|recorder]` | each slot's peak over a short window, in dBFS, named from a scene |

Nothing here writes to the desk. Pushing changes over the network is deliberately not a
feature: a file you load is a deliberate act with a confirm step, a push is not.

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
