# Command reference

Every command, flag and environment variable. `x32scene <command> --help` prints the same
for one command. Edit commands always write a new file with `-o`: writing over an input is
refused outright, and an OUT that already exists is refused unless you pass `--force`. Every
writing command takes that flag, and `show-build` applies the same rule to each file it puts
in `-o DIR`, writing them all or none. `STRIP` is a channel number or a strip path (`/bus/01`, `/main/st`, `/dca/3`).
A word from a fixed list — `on|off`, a bank, a scope, a port, `REC|PLAY`, a tap point — is
accepted in either case; a word not on the list is refused quoting what was typed.

A file named on the command line that does not have the shape of its kind — a truncated
scene, an empty file, a header-only snippet, a `.chn` with no bare channel path or more than
one head amp — prints `x32scene: warning: …` on stderr and carries on. It is never an error: reading a damaged file to find out what survived is
exactly when you need to, and the warning goes to stderr so `--json` stays a clean pipe.
`audit` treats the same finding as a violation and exits 1; it and `history` sweep a
directory and report there instead.

A file's kind comes from its extension. For a name with none of `.scn`, `.snp`, `.chn`,
`.efx`, `.rou`, `.shw` (`gig.scn.bak`, `backup`), put `--kind KIND` before the command —
`x32scene --kind scn info gig.scn.bak` — and that file gets KIND's shape check; a file named
with one of the six keeps its own, so a preset beside it is still checked as a preset. The
same kind decides the `.scn`-only refusal of `swap-strips`, `move-strip` and
`reorder-strips` and the needs-a-scene refusal of `preflight --regenerate`. Without
`--kind`, such a file is only checked for being empty.

---

## Table of contents

- [Environment](#environment)
- [Reading a scene](#reading-a-scene)
- [Comparing](#comparing)
- [Editing one thing](#editing-one-thing)
- [Carrying between scenes](#carrying-between-scenes)
- [Snippets, plans and shows](#snippets-plans-and-shows)
- [Checks](#checks)
- [The live desk (read-only)](#the-live-desk-read-only)

## Environment

| Variable | Used by | Meaning |
|---|---|---|
| `X32SCENE_CONFIG` | `ports`, `report`, `preflight` | expected-config JSON ([preflight-config.md](preflight-config.md)); start from `config/example-preflight.json`. `preflight --regenerate` never reads it |
| `X32SCENE_CONSOLE` | `ports`, `report`, `preflight` | the console model, for how many main outputs have a rear jack ([console models](preflight-config.md#console-models)); `preflight --regenerate` reads it too |
| `X32SCENE_STAGE` | `ports`, `report`, `preflight` | stage sidecar JSON ([stage-sidecar.md](stage-sidecar.md)); start from `config/example-stage.json` |
| `X32SCENE_CORPUS` | `audit`, `history`, the round-trip test | directory of `.scn` files; the round-trip test also reads every `.snp`, `.chn`, `.efx`, `.rou` and `.shw` under it |
| `X32SCENE_REGEN_SCENE` | the rig-config drift test | a scene; with `X32SCENE_CONFIG`, the test regenerates a config from it and fails, printing the diff, when the two differ |
| `X32SCENE_IP` | `pull`, `live-diff`, `desk`, `meters`, `watch` | the console's address (UDP 10023) |
| `X32SCENE_TIMEOUT` | `pull`, `live-diff`, `desk`, `watch` | seconds to wait for each path's reply (default 0.5) |
| `LOG_FILE` | every command | a JSON-lines log of each invocation |

`bin/run` sources `.env`, so a checkout runs commands bare; `.env.example` lists the values.

## Reading a scene

| Command | Arguments | Flags |
|---|---|---|
| `info SCENE` | title, channel and bus names | `--json` |
| `inputs SCENE` | each channel's physical source through the routing banks and user patch | `--json` |
| `ports SCENE` | every output's source, tap point and mirrors | `--bank main\|aux\|p16\|aes\|rec\|all`, `--config` (labels physical vs virtual outputs from `monitor.physical_outputs`), `--console MODEL` (the same labels from the model's jack count; exit 1 when `--config` declares another count), `--stage` (jack, device, wearer), `--json` |
| `buses SCENE` | the 16 mix buses: pairs, FX sends, PRE/POST tallies (a linked pair's on its odd row) | `--json` (each bus with `linked` for its pair, `fx` null or `slot`, `type`, `name`, and `sends` per tap) |
| `iem SCENE BUS` | one monitor mix | `--json` |
| `iem-matrix SCENE` | every monitor mix, senders down, buses across | `--buses 1,3,9`, `--all` (silent strips too), `--compare OTHER` (before>after), `--json` |
| `record-map SCENE` | the USB card tracks a DAW receives | `--json` |
| `fx SCENE` | the FX rack, parameters by name | `--json` |
| `fx-types [CODE]` | every effect type, where it may go, its parameters with default tokens | `--json` |
| `dca SCENE` | DCA and mute-group membership | `--json` |
| `console SCENE` | monitor, talkback, oscillator, recorder, automix, DP48, delays, iQ, user assign | `--json` |
| `explain SCENE` | every readout at once | `--json` (`title`, then `inputs`, `buses`, `outputs` (every bank), `record_map`, `fx`, `groups`, each that command's own `--json` document) |
| `report SCENE` | the scene as markdown | `--config`, `--console MODEL` (as `ports`), `--stage` |
| `header FILE` | a file's header decoded; a channel preset whose header has no 16-bit flag mask shows no sections (`null` in `--json`), since every scope its body carries applies | `--json`; a file with no header line exits 1 — legal for a `.chn`, which may start straight at `/preamp` |
| `show FILE.shw` | a show index: cues, scenes, snippets | `--json`; `--check` exits 1, one line per finding, unless the file has a `show` line (an empty, header-only or non-show file fails), every cue's scene and snippet slot is in the index and every slot's `<show>.NNN.scn` / `.snp` companion beside the `.shw` exists, has its kind's shape and, for a snippet, the header its `snippet/NNN` line copies |
| `vocab routing\|taps\|sources [KEY]` | the tokens the console accepts; `routing` takes a bank key | `--json` |

## Comparing

| Command | Arguments | Flags |
|---|---|---|
| `diff A B` | what changed, path by path | `--by-strip` (grouped, fields named), `--json` |
| `history PATH…` | one path's timeline across a dated library | `--dir DIR`, `--json` |
| `audit [DIR]` | structural invariants across a library; exit 1 on violations | `--json` (`ok`, `load_errors`, `violations`, and each change down the chronology in `routing` and `record_patch`, every slot) |
| `presets-diff DIR SCENE` | each `.chn` regular file directly in DIR (a `._` AppleDouble sidecar, a folder, a pipe or a dangling link is skipped) against the channel it names: `MATCH`, `DRIFT` (each differing path, preset value -> scene value), `NO CHANNEL`, `AMBIGUOUS` (two channels share the name; never guessed) or `UNREADABLE`, then a count per verdict. A preset names its channel by its own `/config` scribble, else its file name, ignoring case and surrounding space; a file name also matches the name `extract-preset --all` would have written it from. A preset that cannot be read or parsed warns on stderr. Tokens are compared, not text, over the scopes an `apply-preset` would write (`--scope`, else a header's section flags); `/config`'s input-source field is not compared; a desk-written `/mix/fader`-style line is compared with that field of the scene's `/mix`; a `/headamp` line is compared by value against the channel's current head amp, and listed as not compared when its source has none. Exit 1 when any preset drifts or is `UNREADABLE`; `NO CHANNEL` and `AMBIGUOUS` leave the exit at 0 | `--scope` (repeatable), `--json` |

## Editing one thing

The six strip editors — `set-fader`, `set-mute`, `set-eq`, `set-lowcut`, `set-comp`,
`set-gate` — mirror to the partner of a stereo-linked pair unless `--no-link`. `rename`
and `set-pan` never mirror: a linked pair's names and pans are individually
meaningful. `set-fx`, `set-input`, `move-inputs`, `set-output`, `set-record` and `set-routing`
address a slot, a channel, an output, a record track or a bank rather than a strip, and take
no `--no-link`;
`set-bus-link` addresses a bus pair. `set-send-tap` addresses one strip's send to a bus pair and
mirrors to a stereo-linked strip unless `--no-link`. `swap-strips`, `move-strip` and `reorder-strips` move whole
channel strips.

| Command | Arguments | Flags |
|---|---|---|
| `rename SCENE STRIP NAME -o OUT` | | |
| `set-fader SCENE STRIP LEVEL -o OUT` | dB, or `oo` / `-oo` for −∞ | `--no-link` |
| `set-mute SCENE STRIP on\|off -o OUT` | `on` = muted | `--no-link` |
| `set-pan SCENE STRIP PAN -o OUT` | −100 (L) … +100 (R) | |
| `set-eq SCENE STRIP BAND -o OUT` | | `--type`, `--freq`, `--gain`, `--q`, `--no-link` |
| `set-lowcut SCENE STRIP -o OUT` | | `--on` / `--off`, `--freq`, `--no-link` |
| `set-comp SCENE STRIP -o OUT` | | `--thr`, `--ratio`, `--makeup`, `--attack`, `--release`, `--no-link` |
| `set-gate SCENE STRIP -o OUT` | | `--thr`, `--range`, `--attack`, `--release`, `--no-link` |
| `set-fx SCENE SLOT -o OUT` | | `--type CODE` (parameters reset to the desk's defaults), `--source L[,R]` (`INS`, `MIX1`…`MIX16`, `M/C`; slots 1–4), `--set NAME=VALUE` (repeatable) |
| `set-input SCENE CH SOURCE -o OUT` | `"local 5"`, `"aes50-a 3"`, `"aes50-b 12"`, `"card 7"`, `"aux 2"`, `off`, or 0–168 | |
| `move-inputs SCENE CH:IN… --to A\|B -o OUT` | each channel 1–32 onto stage-box input 1–48 of that AES50 port, through its user-in slot; head-amp gain and phantom travel with it. All-or-nothing, exit 1 with nothing written: refused are a channel listed twice, two channels onto one input, a channel that is direct-routed, OFF or on the aux bank, a user-in slot another channel or aux-in also reads, and (unless `--no-gain`) an input a channel or aux-in outside the batch still reads | `--to` (required, no default; either case), `--no-gain` (leave the new inputs' head amps as they are) |
| `set-output SCENE BANK N -o OUT` | bank `main\|aux\|p16\|aes\|rec` | `--src` (`"bus 12"`, `"main l"`, `"matrix 2"`, `"direct out ch 5"`, `off`, 0–76), `--pos` (`IN/LC` `<-EQ` `EQ->` `PRE` `POST`; the first four also as `+M`), `--invert on\|off` |
| `set-record SCENE TRACK SRC -o OUT` | USB card record TRACK 1–32 ← SRC, written into the `/config/userrout/out` slot the track's `/config/routing/CARD` block reads ([routing.md](routing.md#the-record-map)). SRC is a word `record-map` prints (`"Local input 5"`, `"Card 7"`, `"Output 9"`, `"P16 5"`, `"Aux Out 2"`, `"Monitor L"`, `"Talkback Int"`), the `set-input` words, `off`, or 0–208. Prints `track N: old -> new (user-out slot S)` and every other AES50, card or XLR channel that slot also feeds. Exit 1 with nothing written for a track outside 1–32, a track whose CARD block is not `UOUT…` (the block and its token are named), or an unknown source. Carried by `snippet --edit` | |
| `set-send-tap SCENE STRIP BUS TAP -o OUT` | the tap point of a strip's send to a mix bus. STRIP is a channel 1–32, `/auxin/NN` or `/fxrtn/NN`; BUS is 1–16; TAP is `IN/LC`, `<-EQ`, `EQ->`, `PRE`, `POST` or `GRP` in either case, written in that spelling. The tap lives on the odd bus's line of each pair ([format.md](format.md#bus-sends--and-the-oddeven-field-count-invariant)), so it sets both buses, and an even BUS writes its odd partner's line, said in the output. Prints every line written, old tap -> new. Exit 1 with nothing written for a strip that carries no sends, a bus outside 1–16, a send line missing or too short, or a scene missing the strip family's link line; exit 2 for an unknown TAP. Carried by `snippet --edit` | `--no-link` |
| `set-routing SCENE KEY BLOCK=TOKEN… -o OUT` | key `IN\|AES50A\|AES50B\|CARD\|OUT\|PLAY`, or `switch REC\|PLAY` | |
| `set-bus-link SCENE BUS on\|off -o OUT` | either bus of a pair, 1–16. `on` links it as the desk does: every sender's even-bus send takes the odd send's on and level, the even bus strip takes the odd strip's colour, key filter and matrix sends, and — per the scene's `/config/linkcfg` — its EQ (`eq`), dynamics and insert (`dyn`), groups and mix but pan (`fdrmute`); matrix-send pans spread to `-100`/`+100`, main pans only when both are centred ([console-behavior.md](console-behavior.md#linking-or-unlinking-a-pair)). `off` unlinks, centres the matrix-send pans, and centres main pans only from exactly `-100`/`+100`. Prints the outputs either bus feeds. Exit 1 with nothing written for a pair already in that state, a bus outside 1–16, or a scene missing `/config/buslink`, `/config/linkcfg` (`on` only) or a line the edit writes. `on`/`off` in either case. Refused by `snippet --edit`, exit 1 with nothing written: a snippet cannot carry `/config/buslink`, so it would load the reshaped sends and pans onto a pair still in its old link state | |
| `swap-strips SCENE A B -o OUT` | channels 1–32 trade places. Every `/ch/NN` line travels whole with its values unchanged — the input source too, so a moved channel keeps its jack and head amp — and each value outside the strips that names a channel by number follows it: a channel direct-out tap on any `/outputs` bank, the `/config/chlink` token of a linked pair moved whole, and a user-assign encoder (fader, pan, send) or button (mute, insert, a page jump to a channel, the factory `P0000` included) ([format.md](format.md#channel-references)). Prints each move, then each remapped reference as its path, field, and value before -> after. All-or-nothing, exit 1 with nothing written: a channel outside 1–32, a strip that stays put, a stereo-linked pair split or reversed, a gate or dynamics key source 1–32 naming a channel that moves (whether it names a channel or an input slot is not desk-verified), an automix group X or Y crossing channels 1–8, strips carrying different lines, a scene missing `/config/chlink` or a moved channel's `/config`, an input that is not a `.scn`. Refused by `snippet --edit`, exit 1 with nothing written: a snippet cannot carry `/config/chlink` or `/config/userctrl` | |
| `move-strip SCENE FROM --to TO -o OUT` | channel FROM lands on TO and the strips between shift one place toward FROM. The rewrites and refusals of `swap-strips`, so a linked pair in the way refuses the move | `--to` (required) |
| `reorder-strips SCENE FROM:TO… -o OUT` | a whole mapping at once: each FROM given once, and every TO also a FROM. The rewrites and refusals of `swap-strips` | |

## Carrying between scenes

| Command | Arguments | Flags |
|---|---|---|
| `transplant SRC DST -o OUT` | lines from SRC into DST, nothing else | `--bus N` (a whole monitor mix, pair-aware), `--path GLOB`, `--ch N`, `--scope` (with `--ch`), all repeatable |
| `extract-preset SCENE CH -o OUT.chn` | | `--scope` (repeatable; `ha scribble gate comp eq sends mainfader insert automix`), `--header` |
| `extract-preset SCENE --all -o DIR` | one `<scribble name>.chn` per channel 1–32 with a name, into DIR (created if missing); unnamed channels are listed as skipped, and so is every channel on a file name another channel also lands on (compared without case or Unicode normalization), named with that file name. `/ \ : * ? " < > \|` in a name, and a leading `.`, become `_`. The rest are written all or nothing, exit 1 with nothing written: a target that is a directory, a file name the filesystem refuses, or any target that already exists without `--force` — every one is named. With `--force`, a target the filesystem will not replace (a locked file) names that file, and every target already replaced gets its original back. A DIR the command created is removed again when nothing is written. Also exit 1 with nothing written when every named channel is skipped, or DIR is not a directory, lies under a file, or cannot be written | `--scope`, `--header`, `--force` |
| `apply-preset SCENE CH PRESET -o OUT` | exit 1 with nothing written for a preset with EQ bands 5-6: a bus, matrix or main preset, whose matrix sends would land on the channel's bus sends. Without `--scope`, a preset header's section flags pick the scopes ([format.md](format.md#channel-presets-chn)) and the summary names each scope the body carries but the header leaves out as skipped, and `/delay` when the config flag is off; a headerless preset applies every scope it carries | `--scope` |
| `extract-fx SCENE SLOT -o OUT.efx` | | `--name` |
| `apply-fx SCENE SLOT PRESET -o OUT` | | `--source` (take the preset's feed too) |
| `extract-routing SCENE -o OUT.rou` | | `--name` |
| `apply-routing SCENE PRESET -o OUT` | | `--bank` (repeatable) |
| `port-iem SRC DST -o OUT` | SRC's output routing onto DST | |

## Snippets, plans and shows

| Command | Arguments | Flags |
|---|---|---|
| `snippet A B -o OUT.snp` | the delta between two scenes. When A and B differ in a bus pair's `/config/buslink` token and the snippet carries a line of either bus (its strip, or a send to it), it is written with a warning on stderr: a snippet cannot carry the link | `--bus N`, `--only GLOB` (keep the delta to a mix or pattern), `--name` |
| `snippet A -o OUT.snp --edit "…"` | edits applied in memory; only what moved is written | `--edit` repeatable: any `set-*` but `set-bus-link`, `rename`, `apply-preset`, `set-fx`, `apply-fx`, `set-routing`, `set-input`, `set-output`, `apply-routing` without its scene and `-o` |
| `snippet A -o OUT.snp --bus N` | one monitor mix as it is (or `--only GLOB`) | |
| `band-setup TEMPLATE PLAN -o OUT` | apply a JSON plan ([band-plan.md](band-plan.md)), verify, save; exit 2 with nothing written on a plan error (a plan that is not a JSON object included). Prints the line and path count, each plan `record` track as `set-record` prints it (the other destinations its user-out slot feeds included), then every changed path grouped by strip as `diff --by-strip` does, a send the plan wrote only because the console mirrors a stereo-linked pair marked `(mirrored)` | `--snippet OUT.snp`, `--force` |
| `show-build -o DIR --name NAME` | a `.shw` index with companions | `--scene FILE` (repeatable), `--snippet FILE` (repeatable), `--cue "1 Opener scene=0 snippet=1 skip"` (repeatable) |

## Checks

| Command | Arguments | Flags |
|---|---|---|
| `preflight SCENE` | the scene against a documented rig; exit 1 on `FAIL`, and on `--force`, which only applies to `--regenerate` | `--config`, `--console MODEL` (fills `monitor.physical_outputs` for a config that declares none; exit 1 when the config declares another count), `--stage`, `--json` |
| `preflight SCENE --regenerate OUT.json` | write the expected-config SCENE satisfies instead of checking it: every section the scene holds, keys sorted, byte-identical for the same scene on the same day. Exit 1 with nothing written, before SCENE is read, for an OUT that is a directory or sits in no writable directory, even with `--force`; exit 1 with nothing written for an existing OUT without `--force`, OUT naming SCENE, an OUT named `.scn`, `.snp`, `.chn`, `.efx`, `.rou` or `.shw` even with `--force`, a `.snp`, `.chn`, `.efx`, `.rou` or `.shw` SCENE, a SCENE with no channel strips (a JSON file, a header-only scene), or `--config`, `--stage` or `--json` typed alongside; the `X32SCENE_CONFIG` and `X32SCENE_STAGE` defaults are ignored. `monitor.physical_outputs` and `require_reachable` are written only with a console model, from `--console` or `X32SCENE_CONSOLE`; exit 1 with nothing written for an unknown model ([preflight-config.md](preflight-config.md#generating-one)) | `--force`, `--console MODEL` |

## The live desk (read-only)

| Command | Arguments | Flags |
|---|---|---|
| `pull REFERENCE -o OUT.scn` | the desk's state, for the paths REFERENCE carries; a reply holding more than one line counts as unanswered | `--ip`, `--timeout`, `--force` |
| `live-diff SCENE` | the desk against a file | `--ip`, `--timeout`, `--json` (`changes` as `diff --json` gives them, and `unanswered`; the warning stays on stderr) |
| `desk` | identity, status, preferences, memory slots | `--ip`, `--timeout`, `--no-library`, `--json` |
| `meters [inputs\|buses\|outputs\|sends\|fx\|monitor\|recorder]` | each slot's peak over a window | `--ip`, `--seconds`, `--scene` (names strips), `--all`, `--json` |
| `watch REFERENCE` | every change another client or the surface makes, as it happens: subscribes, pulls the paths REFERENCE carries, then logs one line per changed path — the local time `HH:MM:SS.mmm` the desk reported it, the path, the strip, each moved field old -> new. Ends on Ctrl-C (exit 0) or after `--seconds`, spending at most two `--timeout`s reading back the paths still waiting (below), then prints the net change against the start, how many paths changed and came back, how many pushed addresses had no watched path, and the paths that still did not answer, whose net change is unknown and left out of the net change and the snippet. Sends only `/xremote` and `/node`, never a write. Exit 2 when the desk does not answer the start pull; exit 1 when the network fails mid-watch, after the summary and snippet | `--ip`, `--timeout`, `--seconds` (up to 43200; default until Ctrl-C), `--snippet OUT.snp` (the net change as a snippet, said to be possibly incomplete when a path did not answer, and warned on when it carries lines of a bus pair whose link changed; an OUT that is a directory, sits in no writable directory, or already exists without `--force` is refused before the watch starts, and nothing is written when nothing changed), `--force`, `--json` (one line per change, then a summary line carrying `unanswered` and a `snippet` that is null without `--snippet`, else `file`, `written`, `lines`, `skipped`) |

`watch` subscribes with `/xremote` before its start pull and renews the subscription through
it, keeping what the desk reports meanwhile, so a change to a path the pull has already read
is logged at the time it was reported; a change to a path it has yet to read is part of the
start. For ten seconds after `/xremote` the desk sends one message per
parameter that changes — the leaf address with its normalized value (`/ch/05/mix/fader ,f
0.4995`, `/ch/05/mix/on ,i 0`), only the fields that moved, a whole-line write split into
the fields it changed, and the desk's own mirroring onto a linked bus as a change of its
own. `watch` renews the subscription every 8 seconds, maps each leaf to the longest path in
REFERENCE above it (`/ch/05/mix/01/level` -> `/ch/05/mix/01`), and reads that line back
with `/node` at most every 150 ms per path, so a fader sweep logs a few lines, not hundreds.
A read-back is asked twice; a path silent to both is reported as unanswered. When the watch
ends, a path with a change not yet asked about, or already reported as unanswered, is asked at
once and again one `--timeout` later if still silent; a path with a read-back still out keeps
that read-back's schedule, so one on its second ask is not asked again. A path still silent two
`--timeout`s after the end is reported as unanswered. A reply that holds more than one line is not believed. A reply names
no query, so while an earlier read-back of a path that has changed since could still be
answering, a reply for that path is not believed either, nor is one that contradicts the reply
that already settled the path while an earlier read-back is still out: the path is asked again once every
read-back of it still out is six `--timeout`s old, and a reply later than that is taken as lost. The desk does
not acknowledge `/xremote`: a desk that goes away mid-watch looks like a desk nobody is
touching.

`pull`, `live-diff` and the `watch` start pull give up once 8 paths in a row go unanswered,
unless a reply arrived late during them or the last path that answered answers again: a desk
that lacks some of the reference's paths, or answers slower than `--timeout`, keeps being
read; a desk that went away is not.

Exit codes: 0 on success, 1 when a check fails (`audit`, `preflight`, a drifted or
unreadable preset in `presets-diff`), 2 when a plan or a desk read fails with nothing written
(for `watch`, the start pull); any other input error prints one line and exits 1. A file that
is not UTF-8 is refused as not a console text file (or, for a JSON document, not a JSON
document), naming it.
