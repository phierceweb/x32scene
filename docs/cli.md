# Command reference

Every command, flag and environment variable. `x32scene <command> --help` prints the same
for one command. Edit commands always write a new file with `-o`: writing over an input is
refused outright, and an OUT that already exists is refused unless you pass `--force`. Every
writing command takes that flag, and `show-build` applies the same rule to each file it puts
in `-o DIR`. `STRIP` is a channel number or a strip path (`/bus/01`, `/main/st`, `/dca/3`).

A file named on the command line that does not have the shape of its kind — a truncated
scene, an empty file, a header-only snippet — prints `x32scene: warning: …` on stderr and
carries on. It is never an error: reading a damaged file to find out what survived is
exactly when you need to, and the warning goes to stderr so `--json` stays a clean pipe.
`audit` treats the same finding as a violation and exits 1; it and `history` sweep a
directory and report there instead.

## Environment

| Variable | Used by | Meaning |
|---|---|---|
| `X32SCENE_CONFIG` | `ports`, `report`, `preflight` | expected-config JSON; start from `config/example-preflight.json` |
| `X32SCENE_STAGE` | `ports`, `report`, `preflight` | stage sidecar JSON; start from `config/example-stage.json` |
| `X32SCENE_CORPUS` | `audit`, `history`, the round-trip test | directory of `.scn` files |
| `X32SCENE_IP` | `pull`, `live-diff`, `desk`, `meters` | the console's address (UDP 10023) |
| `X32SCENE_TIMEOUT` | `pull`, `live-diff`, `desk` | seconds to wait for each path's reply (default 0.5) |
| `LOG_FILE` | every command | a JSON-lines log of each invocation |

`bin/run` sources `.env`, so a checkout runs commands bare; `.env.example` lists the values.

## Reading a scene

| Command | Arguments | Flags |
|---|---|---|
| `info SCENE` | title, channel and bus names | |
| `inputs SCENE` | each channel's physical source through the routing banks and user patch | `--json` |
| `ports SCENE` | every output's source, tap point and mirrors | `--bank main\|aux\|p16\|aes\|rec\|all`, `--config` (labels physical vs virtual outputs from `monitor.physical_outputs`), `--stage` (jack, device, wearer), `--json` |
| `buses SCENE` | the 16 mix buses: pairs, FX sends, PRE/POST tallies | |
| `iem SCENE BUS` | one monitor mix | `--json` |
| `iem-matrix SCENE` | every monitor mix, senders down, buses across | `--buses 1,3,9`, `--all` (silent strips too), `--compare OTHER` (before>after), `--json` |
| `record-map SCENE` | the USB card tracks a DAW receives | `--json` |
| `fx SCENE` | the FX rack, parameters by name | `--json` |
| `fx-types [CODE]` | every effect type, where it may go, its parameters with default tokens | `--json` |
| `dca SCENE` | DCA and mute-group membership | `--json` |
| `console SCENE` | monitor, talkback, oscillator, recorder, automix, DP48, delays, iQ, user assign | `--json` |
| `explain SCENE` | every readout at once | |
| `report SCENE` | the scene as markdown | `--config`, `--stage` |
| `header FILE` | any file's header decoded | `--json` |
| `show FILE.shw` | a show index: cues, scenes, snippets | `--json` |
| `vocab routing\|taps\|sources [KEY]` | the tokens the console accepts; `routing` takes a bank key | `--json` |

## Comparing

| Command | Arguments | Flags |
|---|---|---|
| `diff A B` | what changed, path by path | `--by-strip` (grouped, fields named), `--json` |
| `history PATH…` | one path's timeline across a dated library | `--dir DIR`, `--json` |
| `audit [DIR]` | structural invariants across a library; exit 1 on violations | |

## Editing one thing

All mirror to the partner of a stereo-linked pair unless `--no-link`.

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
| `set-output SCENE BANK N -o OUT` | bank `main\|aux\|p16\|aes\|rec` | `--src` (`"bus 12"`, `"main l"`, `"matrix 2"`, `"direct out ch 5"`, `off`, 0–76), `--pos` (`IN/LC` `<-EQ` `EQ->` `PRE` `POST`, each with `+M`), `--invert on\|off` |
| `set-routing SCENE KEY BLOCK=TOKEN… -o OUT` | key `IN\|AES50A\|AES50B\|CARD\|OUT\|PLAY`, or `switch REC\|PLAY` | |

## Carrying between scenes

| Command | Arguments | Flags |
|---|---|---|
| `transplant SRC DST -o OUT` | lines from SRC into DST, nothing else | `--bus N` (a whole monitor mix, pair-aware), `--path GLOB`, `--ch N`, `--scope` (with `--ch`), all repeatable |
| `extract-preset SCENE CH -o OUT.chn` | | `--scope` (repeatable; `ha scribble gate comp eq sends mainfader insert automix`), `--header` |
| `apply-preset SCENE CH PRESET -o OUT` | | `--scope` |
| `extract-fx SCENE SLOT -o OUT.efx` | | `--name` |
| `apply-fx SCENE SLOT PRESET -o OUT` | | `--source` (take the preset's feed too) |
| `extract-routing SCENE -o OUT.rou` | | `--name` |
| `apply-routing SCENE PRESET -o OUT` | | `--bank` (repeatable) |
| `port-iem SRC DST -o OUT` | SRC's output routing onto DST | |

## Snippets, plans and shows

| Command | Arguments | Flags |
|---|---|---|
| `snippet A B -o OUT.snp` | the delta between two scenes | `--bus N`, `--only GLOB` (keep the delta to a mix or pattern), `--name` |
| `snippet A -o OUT.snp --edit "…"` | edits applied in memory; only what moved is written | `--edit` repeatable: any `set-*`, `rename`, `apply-preset`, `set-fx`, `apply-fx`, `set-routing`, `set-input`, `set-output`, `apply-routing` without its scene and `-o` |
| `snippet A -o OUT.snp --bus N` | one monitor mix as it is (or `--only GLOB`) | |
| `band-setup TEMPLATE PLAN -o OUT` | apply a JSON plan, verify, save; exit 2 with nothing written on a plan error (a plan that is not a JSON object included) | `--snippet OUT.snp`, `--force` |
| `show-build -o DIR --name NAME` | a `.shw` index with companions | `--scene FILE` (repeatable), `--snippet FILE` (repeatable), `--cue "1 Opener scene=0 snippet=1 skip"` (repeatable) |

## Checks

| Command | Arguments | Flags |
|---|---|---|
| `preflight SCENE` | the scene against a documented rig; exit 1 on `FAIL` | `--config`, `--stage`, `--json` |

## The live desk (read-only)

| Command | Arguments | Flags |
|---|---|---|
| `pull REFERENCE -o OUT.scn` | the desk's state, for the paths REFERENCE carries | `--ip`, `--timeout`, `--force` |
| `live-diff SCENE` | the desk against a file | `--ip`, `--timeout` |
| `desk` | identity, status, preferences, memory slots | `--ip`, `--timeout`, `--no-library`, `--json` |
| `meters [inputs\|buses\|outputs\|sends\|fx\|monitor\|recorder]` | each slot's peak over a window | `--ip`, `--seconds`, `--scene` (names strips), `--all`, `--json` |

Exit codes: 0 on success, 1 when a check fails (`audit`, `preflight`), 2 when a plan or a
desk read fails with nothing written; any other input error prints one line and exits 1.
