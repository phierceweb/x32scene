# The X32 scene file format

Everything x32scene knows about the files an X32 reads and writes — scenes (`.scn`),
snippets (`.snp`), channel, effect and routing presets (`.chn` `.efx` `.rou`) and shows
(`.shw`). Verified against a corpus of real console exports, files X32-Edit and a console
wrote on request, and values read back from a live desk over OSC; where something is
inferred rather than sourced, it says so — see [Verified vs inferred](#verified-vs-inferred).
Where a published table is cited it is Patrick-Gilles Maillot's *Unofficial X32/M32 OSC
Remote Protocol* (v4.06); where it and the console disagreed, the console won and the
disagreement is recorded.

A worked example ships with the repo: [`tests/fixtures/example.scn`](../tests/fixtures/example.scn),
a full 32-channel console scene.

## The shape of a file

Plain text, **one OSC parameter per line**:

```
/path token token …
```

The path *is* the index. A full scene is ~2,100 lines, so to answer a targeted question
**grep the path family** rather than reading the whole file:

```bash
grep -E '^/headamp/' scene.scn        # every record gain + phantom
grep -E '^/ch/20/'   scene.scn        # one channel's whole strip
grep -E '^/outputs/' scene.scn        # the physical output patch
```

- **LF line endings, no CR.** A CRLF file is rejected rather than silently normalized.
- **Quoted strings may contain spaces** and count as one token: `/ch/01/config "Lead Vox" 1 1 1`
  tokenizes to `['/ch/01/config', '"Lead Vox"', '1', '1', '1']`. Quotes are retained so the
  value round-trips byte-for-byte.
- **`-oo`** is −∞ (off / fully down).

### Headers

A `.scn` opens with a header line padded with spaces to **127 characters**:

```
#4.0# "Example Rig" "" %000000000 1
```

The version differs by firmware — `#2.7#`, `#3.1#` and `#4.0#` all occur. **Scene names
truncate to about 16 characters** in the header.

The scene header's `%` field is the **scene safes**: nine digits read right to left, bit 0
unused, then Talkback, Effects, Mix Buses, Chan Process, Configuration, Preamp (HA), Output
Patch, Routing I/O — `%000000110` is "talkback and effects safe". A safe group is *not*
recalled when the scene loads. `x32scene header` decodes it.

A `.chn` header is **optional**: files from the console's library carry one, files that begin
straight at `/preamp` load too, and both round-trip. Every preset kind shares one shape:

```
#4.0# <slot> "<name>" <kind> <flags> 1
```

`slot` is the library's physical storage slot (not the alphabetical row the desk lists it
at), `kind` is 0 channel, 1 effect, 2 routing, 3 monitor, and the version is the firmware
that wrote the preset — a desk on 4.06 still exports a `#2.0#` preset saved years ago. For
a channel preset the flags are a `%` bitstring read right to left like the `/grp` masks:
bits 8–13 say which sections the file carries (preamp, config, low cut, gate, EQ,
dynamics) and bits 0–5 whether each is switched on (phantom, delay, low cut, gate, EQ,
dynamics), so `%0011111100111000` is "every section present; gate, EQ and dynamics on".
Confirmed against presets exported from a console; `x32scene extract-preset --header`
writes one. An effect preset's flags field is a plain integer naming the effect's display
type; a routing preset's is all zeros.

> The on-console scene name comes from the **filename**, not this header — see
> [console-behavior.md](console-behavior.md).

## The number-one trap: gain and phantom are not on the channel

Do **not** read record gain or +48V off `/ch/NN/preamp`. That line is the channel's
*digital* trim, polarity and low-cut; its `ON`/`OFF` tokens are polarity and HPF, not
phantom.

The real analog gain and +48V live in **`/headamp/NNN`, indexed by physical input, not by
channel number**:

| `/headamp/` index | Physical input |
|---|---|
| `000`–`031` | Local 1–32 |
| `032`–`079` | AES50-A 1–48 |
| `080`–`127` | AES50-B 1–48 |

`/headamp/003 +19.0 OFF` = +19 dB, phantom off.

The address space reserves 32 slots for local inputs across the console family; a given
model only populates as many as it has jacks (an X32 Rack fills `000`–`015` and leaves
`016`–`031` at defaults). Every model writes all 128 lines.

**Channel → headamp** is not 1:1 in general. The last token of
`/ch/NN/config "Name" colour icon SRC` is a source *slot*; resolve it through the routing
indirection first ([routing.md](routing.md)), then subtract one:
`headamp index = source number − 1` for input sources 1–128. Card, Aux and OFF sources
have no head amp at all.

## Strip lines, field by field

Token formats at the range ends were read back from a console: Q writes `10` at its top
and `0.3` at its bottom, frequency `20k00` and `20.0`, EQ gain `+15.0`, fader and send level
`+10.0` and `-oo`, dynamics hold `2000`, attack `120`, release `4000`, makeup `24.0`, ratio
`100`, delay `500.0`, trim `+18.0`, low cut `400`. The writers in `services/channelfx.py` and
`services/transforms.py` produce exactly these.

Each line packs its parameters **positionally**. Range-checking a decode is how you confirm
you counted correctly — a value outside its documented range means you mis-counted.

### Main mix and pan

```
/ch/NN/mix <on> <fader dB> <LR-on> <pan −100…+100> <mono-on> <mono-level>
```

The channel's main pan is **field 4**. `ON -6.1 ON -94 OFF -oo` = fader −6.1 dB, panned
hard left.

### Bus sends — and the odd/even field-count invariant

```
/ch/NN/mix/MM <on> <level dB> <pan> <tap> <0>
```

**Odd-numbered buses carry five tokens; even-numbered buses carry exactly two** (`<on>
<level>`). Pan and tap live only on the odd line; the even side inherits them.

This is decided by **parity, not by stereo linking** — it holds on unlinked pairs too. In
`example.scn` all 256 odd-bus send lines carry 5 tokens and all 256 even-bus lines carry 2,
including the unlinked 13/14 pair.

> Writing five fields onto an even-bus line produces a line no console ever wrote. It will
> still round-trip and still diff clean, because both are byte-level checks — neither knows
> the shape rule. Code that copies sends between buses must respect parity.

`tap` is one of `IN/LC` (input, after the low cut), `<-EQ` (pre-EQ), `EQ->` (post-EQ),
`PRE` (pre-fader), `POST` (post-fader), `GRP` (subgroup), in the console's own order — all
six read back from a desk (`tables.SEND_TAPS`); `PRE`, `POST` and `EQ->` are what real
scenes mostly carry. The trailing `0` is invariant across every send line in the corpus.

### Preamp (digital — not the head amp)

```
/ch/NN/preamp <trim ±18 dB> <polarity> <lowcut-on> <slope 12|18|24> <freq Hz>
```

**The low-cut frequency is a bare integer** — `80`, not `80.0`. Across the real console
lines the token is always `NN` or `NNN`. This differs from EQ frequencies, which *do* carry
a decimal (below) — the two fields use different formats and confusing them is a real bug.

### Gate

```
/ch/NN/gate <on> <mode> <thr> <range> <attack> <hold> <release> <keysrc>
```

`mode` ∈ `EXP2` `EXP3` `EXP4` `GATE` `DUCK` · `thr` −80…0 dB · `range` 0…60 dB (console
minimum 3) · `attack` 0…120 ms · `hold` 0.02…2000 ms · `release` 5…4000 ms · `keysrc` 0 = self.

### Dynamics

```
/ch/NN/dyn <on> <mode> <det> <env> <thr> <ratio> <knee> <mgain>
           <attack> <hold> <release> <pos> <keysrc> <mix> <auto>
```

`mode` `COMP`/`EXP` · `det` `PEAK`/`RMS` · `env` `LIN`/`LOG` · `thr` −60…0 dB · `knee` 0–5 ·
`mgain` 0…24 dB (disabled when `auto` is ON) · `pos` `PRE`/`POST` · `mix` 0–100 %
(100 = full, below that is parallel).

**`ratio` is an enum, and its token format matters when writing:**

```
1.1  1.3  1.5  2.0  2.5  3.0  4.0  5.0  7.0  10  20  100
```

Single-digit steps carry one decimal. Writing a bare `4` makes the console reject the token
**and abandon parsing the rest of the line** — every field after `ratio` silently reverts on
recall. See [console-behavior.md](console-behavior.md#a-bad-token-aborts-the-rest-of-the-line).

### EQ

```
/ch/NN/eq/N <type> <freq> <gain> <Q>
```

`type` ∈ `LCut` `LShv` `PEQ` `VEQ` `HShv` `HCut` (the console's own order). **Channel strips have 4 bands; bus and
main strips have 6** — band count is the quickest way to tell a channel preset from a bus
preset.

Frequencies use **"k" notation above 1 kHz**, where `k` replaces the decimal point:
`85.3` = 85.3 Hz, `4k37` = 4.37 kHz, `10k02` = 10.02 kHz.

### Group membership

```
/ch/NN/grp <dca-mask %8> <mute-mask %6>
```

X32 `%` bitstrings, **LSB = group 1**. `%00000100` = DCA 3. Names live in `/dca/N/config`.
Group membership belongs to no save scope, so it never travels in a preset.

`/config/mute` carries the **engaged** state of the six mute groups, saved into the scene and
applied on recall — six positional `ON`/`OFF` tokens, field 1 = group 1, left to right. That
is the opposite convention from the `%` masks above, which read right to left; a scene saved
with a group engaged silences its members the moment it loads.

### Stereo links

```
/config/chlink   16 × ON|OFF   channel pairs 1/2 … 31/32
/config/buslink   8 × ON|OFF   bus pairs 1/2 … 15/16
/config/auxlink   4 × ON|OFF   aux-in pairs
/config/fxlink    4 × ON|OFF   FX-return pairs
/config/mtxlink   3 × ON|OFF   matrix pairs
/config/linkcfg   4 × ON|OFF   what a link mirrors: head amp + delay, EQ, dynamics, fader + mute
```

One token per odd/even pair, left to right. A missing link line must be read as *unknown*,
never as "all pairs mono" — every write would then go out one-sided.

## Console configuration lines

The `/config` family holds the desk-wide settings. Every enumeration below was read back
from a console; `x32scene console` prints them in words and `tables.line_fields` names
each field.

| Line | Fields |
|---|---|
| `/config/mono` | mode `LR+M`/`LCR`, link to LR `ON`/`OFF` |
| `/config/solo` | monitor level, source (`OFF` `LR` `LR+C` `LRPFL` `LRAFL` `AUX56` `AUX78`), source trim dB, solo mode for channels / buses / DCAs (`PFL`/`AFL`), exclusive, follow select, follow solo, dim attenuation dB, dim, mono, delay, delay time ms, master control, mute, dim on PFL |
| `/config/talk` | enable, source `INT`/`EXT` |
| `/config/talk/A`, `/B` | level, dim, latch, destination mask: 18 bits read right to left, mix buses 1–16 then main LR and M/C |
| `/config/osc` | level, F1, F2 (frequency tokens like the EQ's), which one (`F1`/`F2`), type (`SINE` `PINK` `WHITE`), destination as an integer: 0–15 mix bus 1–16, 16 L, 17 R, 18 L+R, 19 M/C, 20–25 matrix 1–6 |
| `/config/tape` | recorder gain L, gain R (dB), autoplay |
| `/config/amixenable` | automix group X, group Y |
| `/config/dp48` | scope mask, broadcast, port `AESA`/`AESB`; `/assign` 48 group numbers, `/link` 24 pair flags, `/grpname` 12 names |
| `/config/userctrl/A`…`C` | layer colour; `/enc` four encoder strings, `/btn` eight button strings (buttons are numbered 5–12) |
| `/config/mute` | six mute-group states |
| `/config/chlink` `buslink` `auxlink` `fxlink` `mtxlink` | one `ON`/`OFF` per odd/even pair |
| `/config/linkcfg` | what a link shares: head-amp/delay, EQ, dynamics, fader/mute |
| `/outputs/<bank>/NN/delay` | on, time ms (`0.3`–`500.0`) |
| `/outputs/p16/NN/iQ` | group (`OFF` `A` `B`), speaker (`none` `iQ8` `iQ10` `iQ12` `iQ15` `iQ15B` `iQ18B`), EQ (`Linear` `Live` `Speech` `Playback` `User`), model |

The user-assign strings are compact codes — `F00` is "fader, channel 1", `S0004` "channel
1's send to bus 5", `X001` "FX 1 parameter 2", `P0051` "jump to channel 1's Config page",
`O85` "mute group 6", `Mn01064` "MIDI note toggle, channel 1, value 64". Strip indexes run
channels 0–31, aux-ins 32–39, FX returns 40–47, buses 48–63, matrices 64–69, main LR 70,
M/C 71, DCAs 72–79, mute groups 80–85. `services/userctrl.py` decodes them; a shape it
does not know is shown as the code, never guessed.

## Output lines

```
/outputs/main/NN <src> <pos> <invert>    main 1–16, each with a /outputs/main/NN/delay sibling
/outputs/aux/NN  <src> <pos> <invert>    aux 1–6
/outputs/p16/NN  <src> <pos> <invert>    p16 1–16, each with a /outputs/p16/NN/iQ sibling
/outputs/aes/NN  <src> <pos> <invert>    aes 1–2
/outputs/rec/NN  <src> <pos>             rec 1–2 — two fields, no invert
```

`src` is the [output tap](#output-taps) enumeration. `pos` is the tap point, one of
`IN/LC`, `<-EQ`, `EQ->`, `PRE`, `POST` or the `+M` main-mute variant of the first four —
all nine read back from a console (`tables.OUTPUT_POS`; the [tap-point list](#output-taps)
below gives the order). `<-EQ` here and `EQ->` on a send line are different taps. `invert` is `ON` or
`OFF`.

A three-field `rec` line or a two-field `main` line round-trips and diffs clean while being a
line no console ever wrote — the same trap as the [odd/even send parity](#bus-sends--and-the-oddeven-field-count-invariant)
above. Address output lines by exact path: the `/delay` and `/iQ` siblings share the prefix.

## Enumerations

### Input sources

Used by `/config/userrout/in` and by the source slot on `/ch/NN/config`.

| Range | Domain |
|---|---|
| `0` | OFF |
| `1`–`32` | Local inputs 1–32 |
| `33`–`80` | AES50-A 1–48 |
| `81`–`128` | AES50-B 1–48 |
| `129`–`160` | USB card (DAW playback) 1–32 |
| `161`–`166` | Aux in 1–6 |
| `167`, `168` | Talkback (internal, external) |

Channel source slots **39 and 40** — the last two of the aux bank — are the console's USB
player. They are not routed inputs and no number in this table names them; `x32scene inputs`
labels them directly.

### Output sources

**`/config/userrout/out` uses a wider enumeration than the input table — do not decode it
with the input table.** It shares `0`–`168` and extends past it with the console's own
outputs:

| Range | Domain |
|---|---|
| `169`–`184` | Output 1–16 (the console's own output slots) |
| `185`–`200` | P16 1–16 |
| `201`–`206` | Aux out 1–6 |
| `207`, `208` | Monitor L, Monitor R |

This is the recording patch: decode `/config/userrout/out` with the *output* enum to get the
source of each DAW track, in order. A value in `169`–`184` names an **output slot**, not a
mix bus — what that track actually carries is whatever `/outputs/main/NN` assigns to the
output, so resolving it takes a second hop through the output table below.

Both enumerations are published in Maillot's *Unofficial X32/M32 OSC Remote Protocol*
(v4.06) and agree with every observed scene.

### Output taps

The value after an output index in `/outputs/main/NN`, `/outputs/aux/NN`, `/outputs/p16/NN`,
`/outputs/aes/NN` and `/outputs/rec/NN` — one enumeration for all five banks:

| Value | Source |
|---|---|
| `0` | OFF |
| `1`, `2`, `3` | Main L, Main R, Main M/C |
| `4`–`19` | Mix bus 1–16 |
| `20`–`25` | Matrix 1–6 |
| `26`–`57` | Direct out, channel 1–32 |
| `58`–`65` | Direct out, aux in 1–8 |
| `66`–`73` | Direct out, FX return 1L, 1R … 4R |
| `74`, `75`, `76` | Monitor L, Monitor R, Talkback |

The `pos` token after it is the tap point, in the console's enumeration order: `IN/LC`,
`IN/LC+M`, `<-EQ`, `<-EQ+M`, `EQ->`, `EQ->+M`, `PRE`, `PRE+M`, `POST` (`+M` adds the mono
sum). An odd bus send's tap token is one of `IN/LC`, `<-EQ`, `EQ->`, `PRE`, `POST`, `GRP`.
Both lists were read back from a console (`tables.OUTPUT_POS`, `tables.SEND_TAPS`).

So **bus *n* = tap *n* + 3**. `/outputs/main/05 14` routes physical output 5 from bus 11. The
P16 bank is normally patched from channel direct outs, which is why its values sit in
`26`–`57`. Published in Maillot's protocol document; the bus, channel-direct-out and
FX-direct-out bands are also observed in files, the matrix, aux-direct-out and monitor bands
are not.

## Channel presets (`.chn`)

A `.chn` is **one strip saved with bare paths** — the `/ch/NN` or `/bus/NN` prefix stripped,
so it loads onto any strip. Query the bare family (`^/eq/`, `^/mix/`), not `^/ch/`.

The console's save dialog has a checkbox per section, and **only checked sections are
written**. A preset therefore omits whatever wasn't scoped, and leaves that part of the
target strip untouched on load:

| Checkbox | Paths |
|---|---|
| HA Config | `/preamp` `/headamp/NNN` `/delay` |
| Scribble Strip | `/config` |
| Gate | `/gate` `/gate/filter` |
| Compressor | `/dyn` `/dyn/filter` |
| EQ | `/eq` `/eq/N` |
| Sends | `/mix/01`…`/mix/16` |
| Main/Fader | `/mix` `/mix/fader` `/mix/st` `/mix/pan` `/mix/mono` `/mix/mlevel` |

`insert` and `automix` have no checkbox of their own. x32scene gives them scopes anyway,
because without one they vanish silently from a full preset.

The head-amp index inside a `.chn` is fixed at save time (`/headamp/000`). Applying that
preset to a channel on a different physical input means **remapping the index** —
`apply_preset` does this for you.

The same checkboxes apply to "Save as scene", so a `.scn` can legitimately be partial.

## FX

- `/fx/N <TYPE>` — the slot's effect short-code (`PLAT` plate, `VRM` vintage room, `D/CR`,
  `CR/R`, `EXC` exciter, `LIM` limiter, `GEQ`/`GEQ2` graphic EQ; the console offers ~70).
- `/fx/N/source MIXmm` — which bus feeds the slot.
- `/fx/N/par …` — **positional and specific to the effect type.**

x32scene maps the parameter order for every effect type (`services/fx.py`), each
corroborated against a line a console wrote — the scene fixtures, a desk's effect-preset
library, and the default parameter line the desk returns for each type. Two published
tables disagree with the desk: the stereo enhancer has a ninth parameter (`Solo`), and the
dual pitch shifter has twelve, not thirteen. The graphic EQs (`GEQ`, `GEQ2`, `TEQ`, `TEQ2`)
decode 31 band gains plus a master per side for reading, but writes are refused, because
the band labels are the standard ISO series rather than console-verified.

## Verified vs inferred

Everything above is observed in real files unless listed here. These are honest gaps, not
oversights:

| Item | Status |
|---|---|
| `/config/userrout` enumerations | Published (Maillot v4.06). Earlier releases decoded `169`–`184` as mix buses and `167`/`168` as the USB player; they are output slots 1–16 and talkback |
| Output taps `20`–`25`, `58`–`65`, `74`–`76` | Published enumeration; not yet seen in a file |
| GEQ band labels | Standard ISO series, not verified band-by-band on a console |
| `PIT` parameters 4–5 | The desk's default line carries a low-cut-like value and a frequency where the published table has Gain and Pan; named `Lo Cut`/`Hi Cut` from the defaults |
| Total line count per scene | Varies with console model and firmware — only *agreement across a library* is checkable |

## Related save types

All share the line grammar and round-trip through `Scene`; `x32scene header` names any of
them.

**Snippets** (`.snp`) store a subset the console recalls *in place* — everything else on the
desk is untouched, which is what makes them mid-show safe. The header carries four filter
masks the console reads to decide what to recall:

```
#4.0# "<name>" <eventtyp> <channels> <auxbuses> <maingrps> 1
```

`eventtyp` bits 0–26 are the parameter families (preamp, config, EQ, gate & comp, insert,
groups, fader/pan, mute, sends 1–8 / 9–12 / 13–16, M/C–LR, matrix sends, FX 1–8, monitor,
talkback, routing, out patch, user in, user out); `channels` is one bit per channel;
`auxbuses` is aux-ins 0–7, FX returns 8–15, mix buses 16–31; `maingrps` is matrix 0–5, main
LR 6, main M/C 7, DCA 8–15. A full-desk snippet is `134217727 -1 -1 65535`. Bits 21–26
were read from X32-Edit saves with one filter ticked: the protocol document swaps monitor
and talkback and stops at bit 24. The body is scene lines,
except that a strip's main-mix line, a DCA line and the routing banks are **split one
sub-path per field** (`/ch/01/mix/fader`, `/ch/01/mix/on`, `/dca/1/fader`,
`/config/routing/IN/1-8`, …), each keeping the padding the scene wrote. `x32scene snippet`
writes one from a delta and derives the masks from the body.

A snippet x32scene wrote from two fader edits was loaded through X32-Edit onto a live
console: a full pull afterwards differed from the baseline in exactly those two fields.

**Effect presets** (`.efx`) are one FX slot without its slot number, and — unlike every other
file — **without the leading slash**: `type PLAT`, `source MIX13 MIX13`, `par …` (64 values).
The header's fifth field is the display-type integer from the protocol appendix
(`tables_fx.FX_DISPLAY_TYPE`). Switching a slot's type resets its parameters to a fixed
default line per type; `tables_fx.FX_DEFAULTS` holds all 61 as a console returned them,
and `set-fx` writes them on a type change. Slots 5–8 accept only the 34 insert-style types.
An effect preset x32scene wrote loaded on a console through X32-Edit; the desk **snapped
two logarithmic values to its own grid** (a decay of `2.10` became `2.11`, a damping of
`8k00` became `8k34`), the same clamping the protocol document describes for faders. Read
a slot back after loading before trusting a value to the digit.

**Routing presets** (`.rou`) are the four input routing banks, `/config/routing/{IN,AES50A,
AES50B,CARD}`, as scene lines. Each block token comes from a fixed vocabulary per bank and
block (`tables.routing_vocab`): 24 input-bank sources for `IN`/`PLAY` plus 16 for their
`AUX` block, 36 for the `AES50A`/`AES50B`/`CARD` blocks (inputs, outputs, P16, `AUX/CR`,
`AUX/TB`, user slots), and 36 four-wide ones for `OUT`, where blocks `1-4`/`9-12` take the
low half of each eight (`AN1-4`, `AN9-12` …) and `5-8`/`13-16` the high half. The two
monitor tokens the protocol document spells `AUX1-6/Mon` and `AuxIN1-6/TB` are written
`AUX/CR` and `AUX/TB`. `extract-routing` writes a preset; `set-routing` edits a bank.

**Show files** (`.shw`) are an index X32-Edit writes next to `<show>.NNN.scn` and
`<show>.NNN.snp` companions: a `show "<name>" …` line, then one `cue/NNN`, `scene/NNN` or
`snippet/NNN` line per slot. A scene or snippet line carries that file's own header fields;
the companions are byte-identical to standalone exports. A cue line is

```
cue/000 100 "Opener" 0 0 -1 0 1 0 0
```

the cue number times 100 (`1.2.3` is `123`), its name, skip, the scene slot and snippet
slot it recalls (`-1` for none), then the MIDI type, channel and two values. `x32scene
show` lists one; `x32scene show-build` writes one from scene and snippet files and cue
lines, in the shape X32-Edit imports.

**Cues** pair a scene with a snippet (and MIDI); they live only in the show index.
