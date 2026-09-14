# The band-setup plan

The JSON document `x32scene band-setup TEMPLATE PLAN.json -o OUT.scn` applies to a
known-good template scene: names, head amps, per-channel processing, DCA membership,
monitor mixes, effects, routing, the output patch and the USB record patch, in one file.

Do not confuse it with the two other JSON documents this tool reads. A **plan** *writes* a
scene; the [preflight config](preflight-config.md) and the [stage sidecar](stage-sidecar.md)
only *check* one.

Start from [`config/example-plan.json`](../config/example-plan.json).

---

## Table of contents

- [How a plan is applied](#how-a-plan-is-applied)
- [Top-level keys](#top-level-keys)
- [`channels`](#channels)
- [`dca`](#dca)
- [`iem_copy` and `iem_sends`](#iem_copy-and-iem_sends)
- [`outputs` and `output_patch`](#outputs-and-output_patch)
- [`fx`](#fx)
- [`routing`](#routing)
- [`record`](#record)
- [Rules that decide whether a plan works](#rules-that-decide-whether-a-plan-works)
- [Failure modes](#failure-modes)
- [Adding a new plan section](#adding-a-new-plan-section)

## How a plan is applied

Validate the whole plan → apply → verify → save. Nothing is written until every value has
passed, and nothing is saved until the result is proved to differ from the template only in
paths the plan named. A plan error exits **2** with nothing written.

The stage order is fixed and load-bearing:

1. `title`
2. per channel: `preset`, then `name`, then head amp, then fader/mute, then processing
3. `dca`
4. `iem_copy`
5. `iem_sends`
6. `outputs`
7. `fx`, `routing`, `output_patch`
8. `record`

A preset applies before the plan's own values, so a plan key always wins over the preset
that carried it. A copy replaces a destination send wholesale, so `iem_sends` runs after
`iem_copy` — a trim written the other way round would be erased.

## Top-level keys

Any other key is an error. Keys beginning `_` are comments and are ignored.

| Key | Shape | Writes |
|---|---|---|
| `title` | string | the scene header title |
| `channels` | object, key `"1"`–`"32"` | `/ch/NN/*`, `/headamp/NNN` |
| `dca` | object, key `"1"`–`"8"` → list of channels | `/ch/NN/grp` |
| `iem_copy` | list of `{src, dst}` | every send into the destination bus |
| `iem_sends` | list of `{strip, bus, level?, on?}` | one send each |
| `outputs` | object, `"1"`–`"16"` → bus `1`–`16` | `/outputs/main/NN` |
| `fx` | object, key `"1"`–`"8"` | `/fx/N*` |
| `routing` | object | `/config/routing/*` |
| `output_patch` | object, bank → output → spec | `/outputs/<bank>/NN` |
| `record` | object, track `"1"`–`"32"` → source | `/config/userrout/out` |

## `channels`

```json
"channels": {
  "1":  {"name": "Kick", "gain_db": 27.0, "phantom": false,
         "lowcut": {"on": true, "freq": 40},
         "eq":   {"2": {"type": "PEQ", "freq": 100, "gain": 3.0, "q": 1.5}},
         "comp": {"thr": -18, "ratio": "3", "attack": 10, "release": 80},
         "gate": {"thr": -45, "range": 40}},
  "20": {"name": "Gtr 2", "preset": "Channel/Guitar.chn", "scopes": ["eq", "comp"],
         "fader": "-oo", "mute": true, "pan": -30, "source": "aes50-a 3"}
}
```

| Key | Value |
|---|---|
| `name` | string; the scribble-strip name |
| `preset` | path to a `.chn`, resolved **relative to the plan file** (absolute wins) |
| `scopes` | list from `ha scribble gate comp eq sends mainfader insert automix`; limits what the preset carries. Omitted, a preset header's section flags decide, as `apply-preset` does ([format.md](format.md#channel-presets-chn)), and the report names each channel's skipped scopes |
| `gain_db` | −12…+60, the analog head amp — not the channel's digital trim |
| `phantom` | `true`/`false`; a JSON string is refused |
| `fader` | −90…+10 dB, or `"-oo"` / `"oo"` (synonyms here) |
| `mute` | `true`/`false`; `true` = muted |
| `pan` | −100…+100 |
| `source` | an input source in words: `"local 5"`, `"aes50-a 3"`, `"card 7"`, `"aux 2"`, `"off"` |
| `lowcut` | `{on, freq}` |
| `eq` | band `"1"`–`"6"` → `{type, freq, gain, q}` |
| `comp` | `{thr, ratio, makeup, attack, release}` |
| `gate` | `{thr, range, attack, release}` |

`comp.ratio` is the one **string** among the numbers: one of the console's twelve enum
tokens `"1.1" "1.3" "1.5" "2.0" "2.5" "3.0" "4.0" "5.0" "7.0" "10" "20" "100"`, with
`"2" "3" "4" "5" "7"` accepted as aliases that normalize to the decimal spelling. A JSON
number (`3`) is refused — the console rejects a bare `4` and abandons the rest of the line
([console-behavior.md](console-behavior.md#a-bad-token-aborts-the-rest-of-the-line)).

Every other numeric value must be a JSON number; a quoted number is refused rather than
coerced, because a quoted level is how a plan silently kills a send.

Naming `gain_db` or `phantom` on a channel whose source is a card, an aux or OFF raises:
those sources have no head amp. See [format.md](format.md#the-number-one-trap-gain-and-phantom-are-not-on-the-channel).

**Processing written by a plan does not mirror to a stereo-linked partner.** A plan names
its channels explicitly, so mirroring would write a path the plan never asked for — and
the verify step would then refuse the whole run. Name both sides of a linked pair
yourself.

## `dca`

```json
"dca": {"3": [19, 20, 21, 22]}
```

A plan names a DCA's **whole membership**. Every channel not in the list is removed from
that group. Groups the plan does not name are untouched.

## `iem_copy` and `iem_sends`

```json
"iem_copy":  [{"src": 1, "dst": 5}],
"iem_sends": [{"strip": 23, "bus": 5, "level": -14.0}]
```

`iem_copy` duplicates a whole monitor mix — every sender's send into `src` becomes their
send into `dst`, both sides of a stereo pair.

`iem_sends` trims one send. `strip` is a channel number or a send-strip path
(`"/auxin/05"`, `"/fxrtn/03"`); `bus` is 1–16; `level` is −90…+10 dB or `"-oo"`; `on` is a
boolean.

Three rules, each of which raises:

- A record needs `level` and/or `on`, or it does nothing.
- `"on": true` needs a `level` too. An OFF send keeps a stored level that `x32scene iem`
  does not show, so turning one on blind can drop a strip into someone's ears at an
  unknown level.
- A `level` alone on a send that is currently OFF changes nothing audible — add `"on": true`.

Unlike channel processing, a send **is** mirrored: each record writes every send the
console mirrors it to, both sides of a stereo bus pair and of a stereo strip pair. Name
only one side, or the two records collide and the plan is refused. `iem_copy` writes both
buses of a linked destination the same way. `band-setup` lists every path it changed and
marks each send no record named `(mirrored)`.

## `outputs` and `output_patch`

```json
"outputs":      {"9": 1, "10": 2},
"output_patch": {"main": {"11": {"src": "bus 12", "pos": "PRE+M"}},
                 "p16":  {"1":  {"src": "direct out ch 5"}}}
```

`outputs` is the shorthand: physical output ← mix bus. It reaches `/outputs/main/1-16`
only; the `aux` bank is not routable this way.

`output_patch` is the full form, per bank — `main` (1–16), `aux` (1–6), `p16` (1–16),
`aes` (1–2), `rec` (1–2):

| Key | Value |
|---|---|
| `src` | a tap in words — `"bus 12"`, `"main l"`, `"matrix 2"`, `"direct out ch 5"`, `"off"` — or the raw number |
| `pos` | `IN/LC` `<-EQ` `EQ->` `PRE` `POST`; the first four also as `+M` (there is no `POST+M`) |
| `invert` | boolean; `rec` has no polarity field and refuses it |

## `fx`

```json
"fx": {"4": {"type": "HALL", "source": "MIX15,MIX16", "params": {"Decay": 2.1}},
       "2": {"preset": "FX/Plate.efx"}}
```

A `preset` or a `type` resets the slot to the console's own default parameter line before
`params` is applied, exactly as the desk does. Parameter names are the desk's own — run
`x32scene fx-types CODE` to list them.

Slots 5–8 are inserts: they take only the 34 insert-style types and have no `source`.

## `routing`

```json
"routing": {"switch": "REC", "IN": {"1-8": "A1-8"},
            "preset": "Routing/Local.rou", "banks": ["CARD"]}
```

`preset` banks land first, then named blocks. `banks` limits which banks the preset
contributes and is only meaningful beside a `preset`. `switch` is `REC` or `PLAY`.

Every block token is checked against the console's vocabulary for that bank and block —
`x32scene vocab routing KEY` lists it. A token the desk would not accept is a plan error,
not a silent no-op. See [routing.md](routing.md) for what the banks mean.

## `record`

```json
"record": {"5": "Output 9", "17": "Local input 1", "32": "Monitor R"}
```

Each key is a USB card record track, 1–32, and each value the source that track records:
a word `record-map` prints (`"Local input 5"`, `"AES50-A input 3"`, `"Card 7"`, `"Aux In
2"`, `"Talkback Int"`, `"Output 9"`, `"P16 5"`, `"Aux Out 2"`, `"Monitor L"`), a `set-input`
word (`"local 5"`, `"aes50-b 12"`), `"off"`, or the number 0–208. A track map copied out of
one scene's `record-map` drops straight in.

A track is written through its `/config/routing/CARD` block into the user-out slot that
block reads, exactly as `set-record` does ([routing.md](routing.md#the-record-map)). The
section runs after `routing`, so a plan that re-points a card block records through the new
block. A track whose block is not `UOUT…` is a plan error naming the block's token, as are
two tracks that read one slot and name different sources. Every track resolves before any
is written.

A user-out slot is one signal wherever it is read: an AES50 or XLR block reading the same
slot carries the new source too. `band-setup` prints each track as `set-record` does —
`record track 3: Local input 3 -> Output 9 (user-out slot 3)`, then every other AES50, card
or XLR channel that slot feeds — and `run`'s report carries the same rows as `record`.

## Rules that decide whether a plan works

- **Preset paths resolve relative to the plan file**, not the working directory. An
  absolute path wins.
- **A zero-padded key names the path it writes**, and `"9"` beside `"09"` collides loudly
  rather than applying in JSON key order.
- **The result is verified against the template.** If the applied plan changed any path
  the plan did not name, nothing is saved. That check is what makes a plan safe to run
  against a scene you care about.
- **Every send line keeps its bus's field count.** The verify step refuses a run that
  broke the odd/even parity rule in
  [format.md](format.md#bus-sends--and-the-oddeven-field-count-invariant).
- `--snippet OUT.snp` writes the same change as a snippet the desk recalls in place.

## Failure modes

| Exit | Meaning |
|---|---|
| 0 | applied and saved; the summary names the line and path counts |
| 1 | an output that already exists (pass `--force`), or an input refused outright |
| 2 | a plan error — nothing written; the message names the key |

A plan that is not a JSON object, a key repeated inside one object, an unknown key, a
typo'd scope, a channel the template lacks, a template line the plan writes or copies from
that has lost its values, a bus out of range, a `true` where a number belongs: all exit 2
before any line is written.

After a plan runs, `x32scene diff template.scn out.scn --by-strip` shows what moved, and
the console is still the only proof the result is right — see
[console-behavior.md](console-behavior.md).

## Adding a new plan section

1. Add the key to `PLAN_KEYS` in `orchestrators/_schema.py`.
2. Write its validator there (or in `_sections.py` if it is a processing/FX/routing/output
   family), and call it from `validate_plan`.
3. Apply it in `band_swap.apply_plan`, in the stage order that section needs.
4. Extend `allowed_paths` with exactly the paths it may write — a wider grant lets a stray
   change pass the verify step unflagged.
5. Add a row to the [top-level keys](#top-level-keys) table and a section here.
