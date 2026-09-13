# The preflight expected-config

The JSON document `x32scene preflight SCENE --config rig.json` checks a scene against: the
rig as it is supposed to be. It describes one console's intended state — channel names and
sources, the monitor skeleton, routing, stereo links, send taps, group membership — and
`preflight` reports every way the scene departs from it.

Do not confuse it with the two other JSON documents this tool reads. This one and the
[stage sidecar](stage-sidecar.md) *check* a scene; a [band-setup plan](band-plan.md)
*writes* one. The sidecar records what is true off the desk — jacks, transmitters, wearers —
and is a separate file passed with `--stage`.

`ports --config` and `report --config` read the same file, for `monitor.physical_outputs`
alone. Start from [`config/example-preflight.json`](../config/example-preflight.json), or
write a complete one from a scene with `preflight SCENE --regenerate rig.json` — see
[generating one](#generating-one).

---

## Table of contents

- [How it reads](#how-it-reads)
- [Top-level keys](#top-level-keys)
- [`channels`](#channels)
- [`record` and `fx`](#record-and-fx)
- [`monitor`](#monitor)
- [`outputs`](#outputs)
- [`routing`](#routing)
- [`links`](#links)
- [`sends`](#sends)
- [`groups`](#groups)
- [Reading the report](#reading-the-report)
- [Generating one](#generating-one)
- [Adding a new check family](#adding-a-new-check-family)

## How it reads

**Every section is optional.** A config with only a `monitor` section is legitimate and
checks only that. The `checked:` line at the end of the report counts what each section
covered, so a clean run never claims more than what actually ran.

Three rules govern the whole document:

- **An unknown or misspelled key is a `FAIL`, never a silent skip.** A config that quietly
  checks nothing is worse than no config, so a typo is reported rather than ignored.
- **Keys beginning `_` are comments,** at every level. The shipped example uses `_comment`
  to carry its own notes.
- **Gain is the only `WARN`;** every other mismatch is a `FAIL`, and any `FAIL` exits 1.
  Record gains drift by design, so they are compared against `gain_tolerance_db`.

A section keyed by number rejects a non-numeric key, a key out of range, and `"9"` beside
`"09"` — each as its own `FAIL` rather than an arbitrary last-wins.

## Top-level keys

| Key | Shape | Checks |
|---|---|---|
| `gain_tolerance_db` | number | how far a head-amp gain may drift before it warns |
| `channels` | `"1"`–`"32"` → object | name, source, audibility, phantom, gain |
| `record` | `"1"`–`"32"` → string | what each USB record track carries |
| `fx` | `"1"`–`"8"` → string | each slot's effect type code |
| `monitor` | object | the monitor skeleton — reachability, pairs, live senders |
| `outputs` | bank → number → object | every output's source, tap and polarity |
| `routing` | object | REC/PLAY, pinned routing blocks, pinned user-routing slots |
| `links` | object | stereo pairing per family, and what a link mirrors |
| `sends` | bus → object | send taps, and who must be audible in a mix |
| `groups` | object | DCA and mute-group membership |

## `channels`

```json
"channels": {
  "1": {"name": "Kick", "source": "Local input 1", "in_main": true,
        "gain": 27.0, "phantom": false}
}
```

| Key | Meaning |
|---|---|
| `name` | the scribble-strip name, compared exactly |
| `source` | the physical input the channel resolves to, in words — the same string `x32scene inputs` prints |
| `in_main` | `true` = audibly in the Main L/R blend: ON, LR assigned, and fader above −∞. `false` = silenced any of those three ways |
| `phantom` | `true`/`false`, read from `/headamp/NNN` |
| `gain` | the analog head-amp gain in dB. `WARN` beyond `gain_tolerance_db`, never `FAIL` |

`source` and `gain` both resolve through the routing banks to the physical input, so a
channel re-pointed at another jack fails on `source` — which is the point. See
[routing.md](routing.md) and [format.md](format.md#the-number-one-trap-gain-and-phantom-are-not-on-the-channel).

## `record` and `fx`

```json
"record": {"1": "Local input 1", "17": "AES50-A input 1"},
"fx":     {"1": "PLAT", "2": "VRM"}
```

`record` pins what each of the 32 USB tracks a DAW receives actually carries, decoded
through `routing/CARD` and `userrout/out` — the string `x32scene record-map` prints. It is
the check that catches a record patch someone re-pointed between gigs.

`fx` pins each slot's type code. `x32scene fx-types` lists all 61.

## `monitor`

```json
"monitor": {"physical_outputs": 8, "stereo_pairs": ["main", "aux"],
            "require_reachable": true, "require_live_senders": true}
```

| Key | Meaning |
|---|---|
| `physical_outputs` | 1–16 — how many `/outputs/main` have a rear jack on **this** console (8 = X32 Rack, 16 = full-size). The file cannot say, so the config must |
| `stereo_pairs` | banks (`main`, `aux`) where an odd output carrying an odd bus must be followed by its partner |
| `require_reachable` | every virtual output with a source must leave the console via an AES50/card block or a user-out slot |
| `require_live_senders` | every bus that feeds an output must have at least one sender ON above −∞ |

`require_reachable` and `require_live_senders` are the two checks that catch a silently dead
monitor mix: a bus routed to an output that has no way off the desk, and a bus whose
senders are all down.

## `outputs`

```json
"outputs": {
  "main": {"1": {"bus": 1, "pos": "POST", "invert": false},
           "9": {"bus": 3, "pos": "POST", "invert": false}},
  "rec":  {"1": {"src": 1, "pos": "<-EQ"}}
}
```

Banks are `main` (1–16), `aux` (1–6), `p16` (1–16), `aes` (1–2), `rec` (1–2).

| Key | Meaning |
|---|---|
| `bus` | 1–16 — the mix bus this output must carry. The readable form |
| `src` | 0–76 — the raw tap number, for a source that is not a bus (a main, a matrix, a direct out) |
| `pos` | the tap point: `IN/LC` `<-EQ` `EQ->` `PRE` `POST`, the first four also as `+M` |
| `invert` | polarity. The `rec` bank has no polarity field and refuses the key |

Declare `bus` **or** `src`, not both — naming both is a `FAIL`.
[format.md](format.md#output-taps) has the tap enumeration.

## `routing`

```json
"routing": {"mode": "REC",
            "blocks": {"IN": {"1": "UIN1-8", "5": "AUX1-4"}, "AES50A": {"2": "OUT9-16"}},
            "userrout": {"out": {"1": 1, "16": 16}, "in": {"29": 157}}}
```

| Key | Meaning |
|---|---|
| `mode` | `REC` or `PLAY` |
| `blocks` | bank → **1-based block index** → the token that block must carry |
| `userrout` | `in` / `out` → **1-based slot number** → the raw source value |

Pin only the load-bearing blocks. Repeated placeholder filler on an unused port is not
worth enforcing, and pinning it turns a harmless cosmetic difference into a `FAIL`. Which
blocks matter, and why `OUT9-16` and `UOUT9-16` are different signals, is
[routing.md](routing.md).

## `links`

```json
"links": {"ch":  {"1": false, "11": true},
          "bus": {"1": true, "13": false},
          "linkcfg": {"hadly": true, "eq": true, "dyn": true, "fdrmute": true},
          "require_send_symmetry": true}
```

Families are `ch` (1–32), `bus` (1–16), `auxin` (1–8), `fxrtn` (1–8), `mtx` (1–6), each
**keyed by the odd strip of the pair** and holding a boolean.

`linkcfg` is what a link mirrors — `hadly` (head amp + delay), `eq`, `dyn`, `fdrmute`.

`require_send_symmetry` checks that both sides of every linked bus pair carry the same
on/level for every sender. This is the check for the failure mode in
[console-behavior.md](console-behavior.md#stereo-linked-pairs-reconcile-on-recall): the
console reverts a one-sided write on recall, so an asymmetric pair in a saved scene is a
monitor mix that will not survive being loaded.

## `sends`

```json
"sends": {"1": {"tap": "PRE"},
          "9": {"tap": "PRE",
                "except": {"/fxrtn": "POST", "/ch/11": "POST"},
                "present": ["/ch/23"], "absent": ["/ch/05"]}}
```

Keyed by bus.

| Key | Meaning |
|---|---|
| `tap` | the tap point every sender into this bus uses |
| `except` | a strip family (`/ch`, `/auxin`, `/fxrtn`) or one strip, overriding `tap` |
| `present` | strips that must be audible in this mix — ON and above −∞ |
| `absent` | strips that must be silent in it |

A send's tap lives on the odd bus of a pair and governs both sides, so declare `tap` on the
odd bus. `present` and `absent` are legal on either side.
[format.md](format.md#bus-sends--and-the-oddeven-field-count-invariant) explains why.

## `groups`

```json
"groups": {"dca":  {"1": {"name": "Drums", "members": ["/ch/01", "/ch/02"]}},
           "mute": {"1": {"members": ["/ch/05"]}},
           "mute_engaged": []}
```

Membership is compared as a set **in both directions** — a missing member and a stray one
are both reported. Members are channel numbers or strip paths; buses, matrices and the
mains carry a `/grp` line too.

`mute_engaged` lists the mute groups deliberately saved engaged. Any other engaged group is
a `FAIL`: `/config/mute` is recalled with the scene, so a group left engaged silences its
members the moment the scene loads.

## Reading the report

```
PREFLIGHT OK — checked: channels(31) record(32) fx(4) outputs(5) monitor(4) routing(3)
links(7) sends(2) groups(3) stage(3)
```

The `checked:` counts are the honest scope of the run. A section absent from the config is
absent from that line — it was not checked and the report does not imply it was.

`--json` emits the same findings and coverage for a machine. Exit 0 when nothing failed,
1 when any finding is a `FAIL`. A `WARN` does not fail the run.

## Generating one

```bash
x32scene preflight scene.scn --regenerate rig.json [--force]
```

writes the config `scene.scn` satisfies instead of checking it. Checking the same scene
against the result reports nothing but the line-shape findings no config turns off, and the
`checked:` line names every section the file holds; a section the scene has nothing to
declare for is left out. A snippet, preset or show file is refused, since the config
describes a whole console. The file is stable — keys sorted (numbered keys by number),
two-space indent, one trailing newline — so regenerating from an unchanged scene changes
only the date in `_comment`, and `git diff` on a tracked copy shows what moved on the desk.

It is a full snapshot, not a curated one:

| Section | What the generator writes |
|---|---|
| `channels` | every channel's name, source and `in_main`; `gain` and `phantom` where a head amp feeds it |
| `record`, `fx` | every track, every slot |
| `outputs` | every output of every bank — `bus` for a bus feed, `src` otherwise |
| `routing` | the mode, **every** block and **every** user-routing slot — the advice under [`routing`](#routing) to pin only load-bearing blocks is for a config written by hand |
| `links` | every pair, the four link preferences, and `require_send_symmetry` |
| `sends` | per odd bus the tap with the fewest `except` rules that fit; per bus every sender in `present` or `absent` |
| `groups` | every DCA's name and members, every mute group's members, the engaged groups |
| `monitor` | `stereo_pairs` and `require_live_senders` |

What it cannot write:

- **`monitor.physical_outputs` and `require_reachable`.** A scene does not record how many
  rear jacks the console has, and reachability is judged against that count. Neither
  survives a regenerate, so a rig that relies on them adds them back after each one.
- **The [stage sidecar](stage-sidecar.md).** Cabling is not in the file.
- **A value its check could not verify.** A policy — `stereo_pairs`,
  `require_live_senders`, `require_send_symmetry` — is written `true` only when every line
  it reads is present and the scene passes it, and `false` or left out of the list
  otherwise. A value read from a missing, short or unreadable line is left out: one absent
  send line drops that bus's `tap`, and a non-numeric gain drops that `gain`. A routing
  line the resolver would otherwise fill with a default drops what resolves through it: a
  channel's `source`, `gain` and `phantom`, or a `record` track. One strip without its
  `/grp` line drops `members` from every DCA or mute group, since any strip could belong
  to any group.

`_NOT_INVERTIBLE` in `services/preflight_regen.py` names any section the generator leaves
out; today it is empty.

## Where the real one lives

The shipped example is neutral. A rig's actual config names people, venues and gain values,
so it belongs outside this repository, next to that rig's [stage sidecar](stage-sidecar.md),
and is pointed at with `X32SCENE_CONFIG`. With `X32SCENE_REGEN_SCENE` also set, the test
suite regenerates a config from that scene and fails, printing the diff, when its values
differ from the tracked one (`27` and `27.0` are the same value).

## Adding a new check family

1. Write `services/preflight_<family>.py` exporting `SECTIONS` (its config keys) and
   `check(scene, expected, out)`.
2. Add the module to `_MODULES` in `services/preflight.py`. The top-level allowlist is
   derived from it, so a section cannot exist without its check.
3. Call `fail_unknown` against the family's own key set — an unchecked key must fail, not
   pass silently.
4. Report coverage, so the `checked:` line counts what ran.
5. Invert it in `services/preflight_regen.py`, or name the section in `_NOT_INVERTIBLE` with
   the reason. The section-parity test fails until one is done.
6. Add a row to the [top-level keys](#top-level-keys) table and a section here, and a
   neutral example to `config/example-preflight.json`.
