# Command reference

Every command, flag and environment variable. `x32scene <command> --help` prints the same
for one command. Edit commands always write a new file with `-o`: writing over an input is
refused outright, and an OUT that already exists is refused unless you pass `--force`. Every
writing command takes that flag, and `show-build` applies the same rule to each file it puts
in `-o DIR`, writing them all or none. A file named by `-o OUT`, `band-setup --snippet`,
`watch --snippet` or `preflight --regenerate` is checked before any input is read: a name
that is a directory, or sits in no directory or in one that cannot be written, exits 1 with
nothing written, even with `--force`; so is the `-o DIR` of `show-build` and `extract-preset
--all`, which must be a directory or a name one can be made at. `STRIP` is a channel number or a strip path (`/bus/01`,
`/main/st`, `/dca/3`).
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
- [Loading onto the desk](#loading-onto-the-desk)

## Environment

| Variable | Used by | Meaning |
|---|---|---|
| `X32SCENE_CONFIG` | `ports`, `report`, `preflight` | expected-config JSON ([preflight-config.md](preflight-config.md)); start from `config/example-preflight.json`. `preflight --regenerate` never reads it |
| `X32SCENE_CONSOLE` | `ports`, `report`, `preflight` | the console model, for how many main outputs have a rear jack ([console models](preflight-config.md#console-models)); `preflight --regenerate` reads it too |
| `X32SCENE_STAGE` | `ports`, `report`, `preflight` | stage sidecar JSON ([stage-sidecar.md](stage-sidecar.md)); start from `config/example-stage.json` |
| `X32SCENE_CORPUS` | `audit`, `history`, the round-trip test | directory of `.scn` files; the round-trip test also reads every `.snp`, `.chn`, `.efx`, `.rou` and `.shw` under it |
| `X32SCENE_REGEN_SCENE` | the rig-config drift test | a scene; with `X32SCENE_CONFIG`, the test regenerates a config from it and fails, printing the diff, when the two differ |
| `X32SCENE_IP` | `pull`, `live-diff`, `desk`, `meters`, `watch`, `load` | the console's address (UDP 10023) |
| `X32SCENE_TIMEOUT` | `pull`, `live-diff`, `desk`, `watch`, `load` | seconds to wait for each path's reply (default 0.5); for `watch`, the least a read-back waits ([below](#the-live-desk-read-only)) |
| `LOG_FILE` | every command | a JSON-lines log of each invocation |

`bin/run` sources `.env`, so a checkout runs commands bare; `.env.example` lists the values.

## Reading a scene

| Command | Arguments | Flags |
|---|---|---|
| `info SCENE` | title, channel and bus names | `--json` |
| `inputs SCENE` | each channel's physical source through the routing banks and user patch; a slot whose `/config/routing/IN` block holds a token the console does not write there reads `?` | `--json` |
| `ports SCENE` | every output's source, tap point and mirrors: each AES50 channel a main output leaves on, through an `OUT` block on the port or a `UOUT` block whose user-out slot carries it (`AES50-B 3 via user-out 3`) | `--bank main\|aux\|p16\|aes\|rec\|all`, `--config` (labels physical vs virtual outputs from `monitor.physical_outputs`; exit 1 when `monitor` is not an object or the count is not a whole number 0–16), `--console MODEL` (the same labels from the model's jack count; exit 1 when `--config` declares another count), `--stage` (jack, device, wearer), `--json` (`physical_outputs`, the count or null, then each output in `outputs` with `physical`: true for a main output a rear jack carries as `/config/routing/OUT` patches it, false for a virtual one, null in the other banks or without a count, and `jack`: that jack's number or null; the text view names a jack that is not the output's own number) |
| `buses SCENE` | the 16 mix buses: pairs, FX sends, PRE/POST tallies (a linked pair's on its odd row) | `--json` (each bus with `linked` for its pair, `fx` null or `slot`, `type`, `name`, and `sends` per tap) |
| `iem SCENE BUS` | one monitor mix | `--json` |
| `iem-matrix SCENE` | every monitor mix, senders down, buses across | `--buses 1,3,9`, `--all` (silent strips too), `--compare OTHER` (before>after), `--json` |
| `record-map SCENE` | the USB card tracks a DAW receives | `--json` |
| `fx SCENE` | the FX rack, parameters by name | `--json` |
| `fx-types [CODE]` | every effect type, where it may go, its parameters with default tokens | `--json` |
| `dca SCENE` | DCA and mute-group membership | `--json` |
| `console SCENE` | monitor, talkback, oscillator, recorder, automix, DP48, delays, iQ, user assign | `--json` |
| `explain SCENE` | every readout at once | `--json` (`title`, then `inputs`, `buses`, `outputs` (every bank), `record_map`, `fx`, `groups`, each that command's own `--json` document) |
| `report SCENE` | the scene as markdown | `--config` and `--console MODEL` (both as `ports`, the same exits included), `--stage` |
| `header FILE` | a file's header decoded; a channel preset whose header has no 16-bit flag mask shows no sections (`null` in `--json`), since every scope its body carries applies | `--json`; a file with no header line exits 1 — legal for a `.chn`, which may start straight at `/preamp` |
| `show FILE.shw` | a show index: cues (each with the MIDI command it sends on recall, when one is set), scenes, snippets | `--json`; `--check` exits 1, one line per finding, unless the file has a `show` line (an empty, header-only or non-show file fails), no `scene/NNN`, `snippet/NNN` or `cue/NNN` slot is listed twice (one finding per such slot: which line X32-Edit or the desk reads is unknown), every cue's scene and snippet slot is in the index and every slot's `<show>.NNN.scn` / `.snp` companion beside the `.shw` exists, has its kind's shape and, for a snippet, the header its `snippet/NNN` line copies |
| `vocab routing\|taps\|sources [KEY]` | the tokens the console accepts; `routing` takes a bank key | `--json` |

## Comparing

| Command | Arguments | Flags |
|---|---|---|
| `diff A B` | what changed, path by path | `--by-strip` (grouped, fields named), `--json` |
| `history PATH…` | one path's timeline across a dated library | `--dir DIR`, `--json` |
| `audit [DIR]` | structural invariants across a library; exit 1 on violations | `--json` (`ok`, `load_errors`, `violations`, and each change down the chronology in `routing` and `record_patch`, every slot) |
| `presets-diff DIR SCENE` | each `.chn` regular file directly in DIR (a `._` AppleDouble sidecar, a folder, a pipe or a dangling link is skipped) against the channel it names: `MATCH`, `DRIFT` (each differing path, preset value -> scene value), `NOTHING COMPARED` (a header whose flags leave out every section the body carries, a `--scope` the preset has none of, or only a head amp its channel lacks), `NO CHANNEL`, `AMBIGUOUS` (two channels share the name; never guessed) or `UNREADABLE`, then a count per verdict. A compared preset whose header leaves out scopes its body carries names them as skipped, as `apply-preset` does (`skipped` in `--json`). A preset names its channel by its own `/config` scribble, else its file name, ignoring case and surrounding space; a file name also matches the name `extract-preset --all` would have written it from. A preset that cannot be read or parsed warns on stderr. Tokens are compared, not text, over the scopes an `apply-preset` would write (`--scope`, else a header's section flags); `/config`'s input-source field is not compared; a desk-written `/mix/fader`-style line is compared with that field of the scene's `/mix`; a `/headamp` line is compared by value against the channel's current head amp, and listed as not compared when its source has none; a send on a stereo-linked bus pair is compared on the on and level an `apply-preset` gives it, the partner bus included, and on its own bus alone when the scene has no `/config/buslink`; a send line short of its bus's tokens is compared on the tokens it carries. Exit 1 when any preset drifts or is `UNREADABLE`; `NOTHING COMPARED`, `NO CHANNEL` and `AMBIGUOUS` leave the exit at 0 | `--scope` (repeatable), `--json` |

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
| `set-fx SCENE SLOT -o OUT` | | `--type CODE` (parameters reset to the desk's defaults), `--source L[,R]` (`INS`, `MIX1`…`MIX16`, `M/C`; slots 1–4), `--set NAME=VALUE` (repeatable; a `GEQ`/`GEQ2` band or master outside −15…15 dB exits 1 with nothing written, naming the parameter; no other type's values are range-checked) |
| `set-input SCENE CH SOURCE -o OUT` | `"local 5"`, `"aes50-a 3"`, `"aes50-b 12"`, `"card 7"`, `"aux 2"`, `off`, or 0–168 | |
| `move-inputs SCENE CH:IN… --to A\|B -o OUT` | each channel 1–32 onto stage-box input 1–48 of that AES50 port, through its user-in slot; head-amp gain and phantom travel with it. All-or-nothing, exit 1 with nothing written: refused are a channel listed twice, two channels onto one input, a channel that is direct-routed, OFF or on the aux bank, a channel whose `/config/routing/IN` block holds a token the console does not write there, a user-in slot another channel or aux-in also reads, and (unless `--no-gain`) an input a channel or aux-in outside the batch still reads | `--to` (required, no default; either case), `--no-gain` (leave the new inputs' head amps as they are) |
| `set-output SCENE BANK N -o OUT` | bank `main\|aux\|p16\|aes\|rec` | `--src` (`"bus 12"`, `"main l"`, `"matrix 2"`, `"direct out ch 5"`, `off`, 0–76), `--pos` (`IN/LC` `<-EQ` `EQ->` `PRE` `POST`; the first four also as `+M`), `--invert on\|off` |
| `set-record SCENE TRACK SRC -o OUT` | USB card record TRACK 1–32 ← SRC, written into the `/config/userrout/out` slot the track's `/config/routing/CARD` block reads ([routing.md](routing.md#the-record-map)). SRC is a word `record-map` prints (`"Local input 5"`, `"Card 7"`, `"Output 9"`, `"P16 5"`, `"Aux Out 2"`, `"Monitor L"`, `"Talkback Int"`), the `set-input` words, `off`, or 0–208. Prints `track N: old -> new (user-out slot S)` and every other AES50 channel, card track or `XLR-out routing` position (`/config/routing/OUT`, a rear jack only up to the console's jack count) that slot also feeds. Exit 1 with nothing written for a track outside 1–32, a track whose CARD block is not `UOUT…` or is a `UOUT` token the console does not write, such as a hand-edited `UOUT` or `UOUT0-7` (the block and its token are named), or an unknown source. Carried by `snippet --edit` | |
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
| `extract-preset SCENE --all -o DIR` | one `<scribble name>.chn` per channel 1–32 with a name, into DIR (created if missing); unnamed channels are listed as skipped, and so is every channel on a file name another channel also lands on (compared without case or Unicode normalization), named with that file name. `/ \ : * ? " < > \|` in a name, and a leading `.`, become `_`, and a Windows device name (`CON`, `PRN`, `AUX`, `NUL`, `CONIN$`, `CONOUT$`, `COM1`–`COM9`, `LPT1`–`LPT9`, `COM¹`–`COM³`, `LPT¹`–`LPT³`, in any case, alone or before a `.`, with any spaces before that) gains a leading `_`: `Aux` is written `_Aux.chn`. The rest are written all or nothing, exit 1 with nothing written: a target that is a directory, a file name the filesystem refuses, or any target that already exists without `--force` — every one is named. With `--force`, a target the filesystem will not replace (a locked file) names that file, and every target already replaced gets its original back. A DIR the command created is removed again when nothing is written. Also exit 1 with nothing written when every named channel is skipped, or DIR is not a directory, lies under a file, or cannot be written | `--scope`, `--header`, `--force` |
| `apply-preset SCENE CH PRESET -o OUT` | exit 1 with nothing written for a preset with CR line endings, or with EQ bands 5-6: a bus, matrix or main preset, whose matrix sends would land on the channel's bus sends. Without `--scope`, a preset header's section flags pick the scopes ([format.md](format.md#channel-presets-chn)) and the summary names each scope the body carries but the header leaves out as skipped, and `/delay` when the config flag is off; a headerless preset applies every scope it carries. A send to one bus of a stereo-linked pair is written to both buses, on and level, the pair taking the preset's later line of the two as a line-by-line load leaves it, and the summary names each send so mirrored; a scene with no `/config/buslink` is refused, exit 1 with nothing written, when the preset writes a send. A send line short of its bus's tokens, as an older desk preset's odd-bus send is, keeps the target's rest; one without on and level, or longer than its bus's line, is refused, exit 1 with nothing written. On a stereo-linked channel the preset's sends are written to the partner too, on, level and tap (the pan stays per side), as the desk mirrors them; processing is written to CH only, and the summary says the partner keeps its own ([console-behavior.md](console-behavior.md#stereo-linked-pairs-reconcile-on-recall)) | `--scope` |
| `extract-fx SCENE SLOT -o OUT.efx` | | `--name` |
| `apply-fx SCENE SLOT PRESET -o OUT` | | `--source` (take the preset's feed too) |
| `extract-routing SCENE -o OUT.rou` | | `--name` |
| `apply-routing SCENE PRESET -o OUT` | | `--bank` (repeatable) |
| `port-iem SRC DST -o OUT` | SRC's output routing onto DST | |

## Snippets, plans and shows

| Command | Arguments | Flags |
|---|---|---|
| `snippet A B -o OUT.snp` | the delta between two scenes. When A and B differ in a bus pair's `/config/buslink` token and the snippet carries a line of either bus (its strip, or a send to it), it is written with a warning on stderr: a snippet cannot carry the link | `--bus N`, `--only GLOB` (keep the delta to a mix or pattern), `--name` |
| `snippet A -o OUT.snp --edit "…"` | edits applied in memory, all of them before anything is printed; only what moved is written. Exit 1 with nothing written when an edit fails or writes a line a snippet cannot carry, named with the edit and the command to run on the scene instead: `set-routing switch` (`/config/routing`), `set-output rec`, an `apply-preset` that changes `/automix` (or name the other scopes in the edit) | `--edit` repeatable: any `set-*` but `set-bus-link`, and `rename`, `apply-preset`, `apply-fx`, `apply-routing`, each without its scene and `-o` |
| `snippet A -o OUT.snp --bus N` | one monitor mix as it is (or `--only GLOB`) | |
| `band-setup TEMPLATE PLAN -o OUT` | apply a JSON plan ([band-plan.md](band-plan.md)), verify, save; exit 2 with nothing written on a plan error (a plan that is not a JSON object included). Prints the line and path count, each plan `record` track as `set-record` prints it (the other destinations its user-out slot feeds included), then every changed path grouped by strip as `diff --by-strip` does, a send the plan wrote only because the console mirrors a stereo-linked pair marked `(mirrored)`; a channel `preset` whose stereo-linked partner the plan does not give the same preset and scopes is named, as `apply-preset` names it | `--snippet OUT.snp` (the plan's delta against TEMPLATE, left unwritten and said so when the plan changes nothing a snippet can carry, an existing one that `--force` named removed rather than left stale; exit 1 with neither file written when it names OUT or an input, or already exists without `--force`; OUT and the snippet are written all or nothing, and a file that appears at either path while the plan builds is neither replaced nor removed: exit 1 when it is OUT or a snippet the plan writes), `--force` |
| `show-build -o DIR --name NAME` | a `.shw` index with companions | `--scene FILE` (repeatable), `--snippet FILE` (repeatable), `--cue "1 Opener scene=0 snippet=1 skip"` (repeatable) |

## Checks

| Command | Arguments | Flags |
|---|---|---|
| `preflight SCENE` | the scene against a documented rig; exit 1 on `FAIL`, and on `--force`, which only applies to `--regenerate` | `--config`, `--console MODEL` (fills `monitor.physical_outputs` into a `monitor` section that declares none, and the `checked:` line and `--json` `checked` count it; exit 1 when the config declares another whole number), `--stage`, `--json` |
| `preflight SCENE --regenerate OUT.json` | write the expected-config SCENE satisfies instead of checking it: every section the scene holds, keys sorted, byte-identical for the same scene on the same day. Exit 1 with nothing written, before SCENE is read, for an OUT that is a directory or sits in no writable directory, even with `--force`; exit 1 with nothing written for an existing OUT without `--force`, OUT naming SCENE, an OUT named `.scn`, `.snp`, `.chn`, `.efx`, `.rou` or `.shw` even with `--force`, a `.snp`, `.chn`, `.efx`, `.rou` or `.shw` SCENE, a SCENE whose header is a snippet's, a preset's or of no known shape whatever its name, a SCENE with no channel strips (a JSON file, a header-only scene), or `--config`, `--stage` or `--json` typed alongside; the `X32SCENE_CONFIG` and `X32SCENE_STAGE` defaults are ignored. `monitor.physical_outputs` and `require_reachable` are written only with a console model, from `--console` or `X32SCENE_CONSOLE`; exit 1 with nothing written for an unknown model ([preflight-config.md](preflight-config.md#generating-one)) | `--force`, `--console MODEL` |

## The live desk (read-only)

| Command | Arguments | Flags |
|---|---|---|
| `pull REFERENCE -o OUT.scn` | the desk's state, for the paths REFERENCE carries; a reply holding more than one line counts as unanswered | `--ip`, `--timeout`, `--force` |
| `live-diff SCENE` | the desk against a file | `--ip`, `--timeout`, `--json` (`changes` as `diff --json` gives them, and `unanswered`; the warning stays on stderr) |
| `desk` | identity, status, preferences, memory slots | `--ip`, `--timeout`, `--no-library`, `--json` |
| `meters [inputs\|buses\|outputs\|sends\|fx\|monitor\|recorder]` | each slot's peak over a window | `--ip`, `--seconds`, `--scene` (names strips), `--all`, `--json` |
| `watch REFERENCE` | every change another client or the surface makes, as it happens: subscribes, pulls the paths REFERENCE carries, then logs one line per changed path — the local time `HH:MM:SS.mmm` the desk reported it, the path, the strip, each moved field old -> new. Ends on Ctrl-C (exit 0) or after `--seconds`, spending at most two round-trip estimates reading back the paths still waiting (below), then prints the net change against the start, how many paths changed and came back, how many pushed addresses had no watched path, and the paths that still did not answer, whose net change is unknown and left out of the net change and the snippet. Sends only `/xremote` and `/node`, never a write. Exit 2 when the desk does not answer the start pull; exit 1 when the network fails mid-watch, after the summary and snippet | `--ip`, `--timeout`, `--seconds` (up to 43200; default until Ctrl-C), `--snippet OUT.snp` (the net change as a snippet, said to be possibly incomplete when a path did not answer, and warned on when it carries lines of a bus pair whose link changed; an OUT that is a directory, sits in no writable directory, or already exists without `--force` is refused before the watch starts, and nothing is written when nothing changed), `--force`, `--json` (one line per change, then a summary line carrying `unanswered` and a `snippet` that is null without `--snippet`, else `file`, `written`, `lines`, `skipped`) |

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
A read-back is asked twice; a path silent to both is reported as unanswered. How long it waits
before asking again follows the link, as TCP's retransmission timer does (RFC 6298). The
round-trip estimate is the smoothed round trip plus four times its variation, and at least a
quarter `--timeout` above the round trip. It is learned from the start pull's replies and from
each reply to a read-back that was its path's only one out. A read-back that goes unanswered
doubles the wait until the next such reply. The wait is never less than `--timeout` nor more
than four `--timeout`s, so on a link slower than `--timeout` a fader ride is logged while it
happens, about once a round trip; raise `--timeout` for a desk slower than that.

When the watch ends, a path with a change not yet asked about, or already reported as
unanswered, is asked at once and again one round-trip estimate later if still silent. A path
with a read-back still out keeps that read-back's schedule, waiting one estimate at most, so one
on its second ask is not asked again. A path still silent two estimates after the end is
reported as unanswered.

A reply that holds more than one line is not believed. A reply names no query, so while an
earlier read-back of a path that has changed since could still be answering, a reply for that
path is not believed either, nor is one that contradicts the reply that already settled the
path while an earlier read-back is still out. The path is asked again once each read-back of it
still out has had a reply or is six round-trip estimates old (at least six `--timeout`s), and a
reply later than that is taken as lost. A reply for a path with no read-back out is not believed
either, but when it differs from the path's last line the path is read back again. The desk
does not acknowledge `/xremote`: a desk that goes away mid-watch looks like a desk nobody is
touching.

`pull`, `live-diff` and the `watch` start pull give up once the first 3 paths go unanswered
with nothing received, or once 8 paths in a row go unanswered, unless a reply arrived late
during them, the last path that answered answers again, or, while no path has answered yet,
the desk answers `/node ch/01/config`, a path every X32 and M32 firmware has: a desk that
lacks some of the reference's paths, even its first ones, or answers slower than `--timeout`,
keeps being read; a desk that went away, or never answered, is not. The error says whether
the device answers `/xinfo` but no `/node` (not an X32/M32, or not ready) or nothing at all.
`desk` gives up once its first 3 status paths go unanswered; when the first 3 preference or
memory-slot paths go unanswered, it asks for `ch/01/config` the same way and reads on when the
desk answers; and it gives up on the memory slots as `pull` does, once 8 in a row go
unanswered and the last slot that answered stays silent too.

Exit codes: 0 on success, 1 when a check fails (`audit`, `preflight`, a drifted or
unreadable preset in `presets-diff`), 2 when a plan or a desk read fails with nothing written
(for `watch`, the start pull; for `load`, also a desk that stops answering after writes went
out, said so), 130 when Ctrl-C ends `load`; any other input error prints one line and exits 1. A file that
is not UTF-8 is refused as not a console text file (or, for a JSON document, not a JSON
document), naming it.

## Loading onto the desk

| Command | Writes | Flags |
|---|---|---|
| `load FILE` | a `.scn` or `.snp` onto the running desk: every line the desk does not hold (padding aside), as `/` root writes in file order, an FX slot's type line given half a second before its parameters follow; then every line of the file read back (a write can change another: a linked pair's mirror, an FX type resetting its parameters) and what still differs written again, up to `--passes` rounds. Each pass writes slower than the last. Prints each pass's count, then whether the desk holds the file, and names the head amps it wrote. A path the desk did not answer at the start is written and read back once; one it never answers is named as not verified and not asked again. Exit 1 for a path the desk still answers with another value after the last pass (its own grid, a linked pair's mirror), shown as the file's line and the desk's, and for a path never read back; exit 2 when the desk does not answer, before any write (a single silent path is probed with `/node ch/01/config`, so a one-line file never writes blind) or after writes went out, when the passes and head amps written are still printed and the desk may hold part of the file, said so (a failed send ends the same way); exit 130 on Ctrl-C, saying whether anything was written. Exit 1 with nothing written, the desk never contacted, for a `.chn`, `.efx`, `.rou`, `.shw` or a file whose header is not a scene's or a snippet's; a body line that is not a parameter of a scene or snippet (`/config`, `/ch`, `/auxin`, `/fxrtn`, `/bus`, `/mtx`, `/main`, `/dca`, `/fx`, `/outputs`, `/headamp`), since a root write also reaches the desk's actions and preferences (`/-action`, `/-prefs`); a scene whose header marks a group safe, or a snippet line outside its own masks, since the desk's recall skips those and a root write does not; no parameter lines; a last line without its newline | `--ip`, `--timeout`, `--passes` (1–10, default 3), `--json` (`file`, `ok`, `passes` as lists of paths, `written`, `stuck` as `diff --json` gives changes, `unanswered`, `error` when the desk stopped answering or a send failed after writes went out, `interrupted` after Ctrl-C) |
