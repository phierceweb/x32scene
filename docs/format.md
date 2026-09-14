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

---

## Table of contents

- [The shape of a file](#the-shape-of-a-file)
- [The number-one trap: gain and phantom are not on the channel](#the-number-one-trap-gain-and-phantom-are-not-on-the-channel)
- [Strip lines, field by field](#strip-lines-field-by-field)
- [Console configuration lines](#console-configuration-lines)
- [Output lines](#output-lines)
- [Enumerations](#enumerations)
- [Channel references](#channel-references)
- [Channel presets (`.chn`)](#channel-presets-chn)
- [FX](#fx)
- [Verified vs inferred](#verified-vs-inferred)
- [Related save types](#related-save-types)

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
- **Quoted strings may contain spaces** and count as one token: `/ch/01/config "Lead Vox" 1 YE 1`
  tokenizes to `['/ch/01/config', '"Lead Vox"', '1', 'YE', '1']`. Quotes are retained so the
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
Confirmed against presets exported from a console, and X32-Edit reads a header x32scene
writes the same way: a preset carrying gate, EQ and dynamics showed exactly those three in
its Flags column, EQ lit as the active one, and Load wrote only those sections.
`x32scene extract-preset --header` writes one, and `apply-preset` takes its default scope
from the present bits ([channel presets](#channel-presets-chn)). An effect preset's flags field is a plain integer naming the effect's display
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
`/ch/NN/config "Name" icon colour SRC` is a source *slot*; resolve it through the routing
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

### Config

```
/ch/NN/config <name> <icon> <colour> <source>
```

`/ch/01/config "Kick" 2 YEi 1` = name Kick, icon 2, colour `YEi`, source slot 1. `icon` 1…74 ·
`colour` ∈ `OFF` `RD` `GN` `YE` `BL` `MG` `CY` `WH` and the same eight with an `i` suffix ·
`source` a slot resolved through the routing banks ([routing.md](routing.md)), published as
`0`–`64`: OFF, In01…32, Aux 1…6, USB L, USB R, FX 1L…4R, bus 1…16. It is not a physical
input and not a channel number, although a scene often has slot *NN* on channel *NN*. The
order is published and observed in files.

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
`PRE` (pre-fader), `POST` (post-fader), `GRP` (subgroup), in the console's own order
(`tables.SEND_TAPS`). All six were written to a desk and read back verbatim (firmware 4.06);
`PRE`, `POST` and `EQ->` are the ones seen in saved scenes. The trailing `0` is invariant
across every send line in the corpus.

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
minimum 3) · `attack` 0…120 ms · `hold` 0.02…2000 ms · `release` 5…4000 ms.

`keysrc` is the side-chain source, published as `0`–`64`: `0` self (`OFF` in the published
table), `1`–`32` In01…32, `33`–`38` Aux 1…6, `39`, `40` USB L, USB R, `41`–`48` FX 1L…4R,
`49`–`64` bus 1…16. **What `1`–`32` names is unverified.** The published labels are the
channel source slot's, which is an input slot; X32-Edit labels the same list `Self`,
`Channel 01`…`Channel 32`, which is a strip. Every observed file carries `0`.

### Dynamics

```
/ch/NN/dyn <on> <mode> <det> <env> <thr> <ratio> <knee> <mgain>
           <attack> <hold> <release> <pos> <keysrc> <mix> <auto>
```

`mode` `COMP`/`EXP` · `det` `PEAK`/`RMS` · `env` `LIN`/`LOG` · `thr` −60…0 dB · `knee` 0–5 ·
`mgain` 0…24 dB (disabled when `auto` is ON) · `pos` `PRE`/`POST` · `keysrc` as on the
[gate](#gate) · `mix` 0–100 % (100 = full, below that is parallel).

`/bus/NN/dyn` has the same 15 fields, `keysrc` included: it is the only key source outside
the channel strips. `/mtx/NN/dyn`, `/main/st/dyn` and `/main/m/dyn` have 14, with no
`keysrc`, so `mix` is field 13 there. Aux-in and FX-return strips have no gate or dynamics
line. Published and observed in files.

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

### Automix

```
/ch/NN/automix <group OFF|X|Y> <weight ±12 dB>
```

Every channel carries the line (`/ch/01/automix OFF  +0.0`), but **group and weight
take effect only on channels 1–8** — published, not verified on a console.
`/config/amixenable` switches groups X and Y on.

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

Flipping a `buslink` token is not all the desk does when a pair is linked or unlinked: it
also copies the odd bus onto the even one and moves pans. See
[console-behavior.md](console-behavior.md#linking-or-unlinking-a-pair).

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
| `/config/amixenable` | automix group X, group Y; only channels 1–8 [take part](#automix) |
| `/config/dp48` | scope mask, broadcast, port `AESA`/`AESB`; `/assign` 48 group numbers, `/link` 24 pair flags, `/grpname` 12 names |
| `/config/userctrl/A`…`C` | layer colour; `/enc` four encoder strings, `/btn` eight button strings (buttons are numbered 5–12) |
| `/config/mute` | six mute-group states |
| `/config/chlink` `buslink` `auxlink` `fxlink` `mtxlink` | one `ON`/`OFF` per odd/even pair |
| `/config/linkcfg` | what a link shares: head-amp/delay, EQ, dynamics, fader/mute |
| `/outputs/<bank>/NN/delay` | on, time ms (`0.3`–`500.0`) |
| `/outputs/p16/NN/iQ` | group (`OFF` `A` `B`), speaker (`none` `iQ8` `iQ10` `iQ12` `iQ15` `iQ15B` `iQ18B`), EQ (`Linear` `Live` `Speech` `Playback` `User`), model |

The user-assign strings are compact codes — `F00` is "fader, channel 1", `S0004` "channel
1's send to bus 5", `X001` "FX 1 parameter 2", `P0001` "jump to channel 1's Config page",
`P0051` "jump to the FX1 page", `O85` "mute group 6", `Mn01064` "MIDI note toggle, MIDI
channel 1, value 64". Strip indexes run channels 0–31, aux-ins 32–39, FX returns 40–47,
buses 48–63, matrices 64–69, main LR 70, M/C 71, DCAs 72–79, mute groups 80–85. A page jump
`Pxxyz` names a strip only when its target `y` is `0`; for any other target `xx` is not a
strip index. `services/userctrl.py` decodes them; a shape it does not know is shown as the
code, never guessed.

The solo, talkback and oscillator lines store no channel; `/config/chlink` and the
user-assign codes do — see [Channel references](#channel-references).

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

Used by `/config/userrout/in`. A channel's `/ch/NN/config` source is an input *slot*, 0-64, not this table ([Config](#config)).

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

## Channel references

The lines below hold a channel number *as a value* rather than in their path. Every
`/ch/NN/*` line belongs to channel *NN* by its path; its values name no other channel apart
from the key sources below. Provenance: *published* is Maillot's protocol document,
*observed* is seen in files a console or X32-Edit wrote.

### Values that point at a channel

| Line | Field | Encoding | Provenance |
|---|---|---|---|
| `/outputs/{main,aux,p16,aes,rec}/NN` | 1, `src` | `26`–`57` = direct out of channel 1–32 (channel = value − 25); no other value names a channel, and neither do `pos`, `invert` or the output index | published for all five banks; observed on `p16` only |
| `/config/chlink` | token *k* | `ON` links channels 2*k*−1 and 2*k* | published, observed |
| `/config/userctrl/{A,B,C}/enc` | 1–4 | `Fxx` fader, `Pxx` pan, `Sxxyy` send: `xx` `00`–`31` = channel `xx`+1; `yy` is a bus | published; not yet seen naming a channel in a file |
| `/config/userctrl/{A,B,C}/btn` | 1–8 (buttons 5–12) | `Oxx` mute, `Ixx` insert, `Pxx0z` page jump: `xx` `00`–`31` = channel `xx`+1. A page jump with any other target `y` names no strip | published; `P0000` (channel 1, Home) observed as the factory default on layer B buttons 11 and 12 |

Outside scenes, a snippet header's `channels` mask and the `snippet/NNN` lines of a show
index hold one bit per channel ([Related save types](#related-save-types)).

Position matters without any reference: [automix](#automix) group and weight act only on
channels 1–8.

### Key sources, meaning unverified

| Line | Field | Encoding | Provenance |
|---|---|---|---|
| `/ch/NN/gate` | 8, `keysrc` | `0` self, `1`–`32` a channel or an input slot, `33`–`64` aux, USB, FX, bus ([gate](#gate)) | enumeration published; field position observed; only `0` observed |
| `/ch/NN/dyn` | 13, `keysrc` | as the gate | as the gate |
| `/bus/NN/dyn` | 13, `keysrc` | as the gate; the only key source outside the channel strips | as the gate |

### Values that look like channel numbers but are not

| Line | What the value is | Provenance |
|---|---|---|
| `/ch/NN/config` source (field 4) | an input slot, resolved through the routing banks ([Config](#config)) | published, observed |
| `/headamp/NNN` | the index is a physical input | published, observed |
| `/config/userrout/in`, `/config/userrout/out` | input sources and output slots; the output enumeration has no channel direct-out band | published, observed |
| `/config/routing`, `/config/routing/*` | routing block tokens | published, observed |
| `/auxin/NN/config` source | an input slot on an aux-in strip | published, observed |
| `/config/solo`, `/config/talk/A`, `/config/talk/B`, `/config/osc` | no channel field (below) | published, observed |
| `/config/dp48/assign`, `/config/dp48/link` | indexed by the DP48 personal mixer's own 48 channels, not by console channel | published, observed |
| `/fx/N/source`, `/ch/NN/insert` | `INS`, `MIX1`…`MIX16`, `M/C`; FX slot sides and aux sends | published, observed |
| `.chn` `.efx` `.rou` header slot | a library slot | observed on `.chn` and `.efx` |
| `.shw` cue MIDI channel, user-assign `Mxyyzzz` `yy` | a MIDI channel | published; observed in cue lines |

**No scene-file solo, monitor, talkback or oscillator setting stores a channel.** The solo
source, the talkback destination masks and the oscillator destination name buses, main and
matrix only. Channel solo switches and the selected channel exist only as live state
(`/-stat/solosw/NN`, `/-stat/selidx`), published and never observed in a file.

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

A preset the desk writes differs from the scene lines it came from in two ways: `/config`
carries the name, icon and colour but **not the input-source field**, and the main mix is
**split one sub-path per field** (`/mix/fader`, `/mix/st`, `/mix/pan`, `/mix/mono`,
`/mix/mlevel`, with no mute) where a scene has one `/mix` line. Its columns are padded as
the desk pads them, so compare a preset with a scene by tokens, never by text.

The head-amp index inside a `.chn` is fixed at save time (`/headamp/000`). Applying that
preset to a channel on a different physical input means **remapping the index** —
`apply_preset` does this for you.

The same checkboxes apply to "Save as scene", so a `.scn` can legitimately be partial.

When a preset has a [header](#headers), `apply-preset` without `--scope` applies only the
sections its flags mark present: preamp and low cut select HA Config, config selects
Scribble Strip and `/delay`, gate Gate, EQ EQ, and dynamics Compressor. Sends, Main/Fader,
insert and automix have no flag, so they apply whenever the body carries them. A headerless
preset, or one whose header carries no 16-bit `%` flag mask, applies every scope it carries,
and `--scope` overrides the header (`/delay` is then HA Config). `extract-preset
--header` sets the config flag for a `/config` or `/delay` line.

## FX

- `/fx/N <TYPE>` — the slot's effect short-code (`PLAT` plate, `VRM` vintage room, `D/CR`,
  `CR/R`, `EXC` exciter, `LIM` limiter, `GEQ`/`GEQ2` graphic EQ; 61 in all).
- `/fx/N/source MIXmm` — which bus feeds the slot.
- `/fx/N/par …` — **positional and specific to the effect type.**

x32scene maps the parameter order for every effect type (`services/fx.py`), each
corroborated against a line a console wrote — the scene fixtures, a desk's effect-preset
library, and the default parameter line the desk returns for each type. Two published
tables disagree with the desk: the stereo enhancer has a ninth parameter (`Solo`), and the
dual pitch shifter has twelve, not thirteen. The graphic EQs (`GEQ`, `GEQ2`, `TEQ`, `TEQ2`)
carry 31 band gains plus a master per side: `par` 1–31 are the ISO bands 20 Hz to 20 kHz
in order, 32 the master, and on the dual types 33–64 the B side the same way. Verified on
a console for `GEQ` and `GEQ2` — X32-Edit labels the faders 20 … 20k, and a value written
to `par` 1 moved the 20 Hz fader, to 31 the 20 kHz one, to 33 the B side's 20 Hz. Gains are
`-15.0`…`15.0` written as `3.0`, `-6.0`, `0.0`, no plus sign. `TEQ` and `TEQ2` are assumed
to match and stay read-only.

## Verified vs inferred

Everything above is observed in real files unless listed here. These are honest gaps, not
oversights:

| Item | Status |
|---|---|
| `/config/userrout` enumerations | Published (Maillot v4.06). Earlier releases decoded `169`–`184` as mix buses and `167`/`168` as the USB player; they are output slots 1–16 and talkback |
| Output taps `20`–`25`, `58`–`65`, `74`–`76` | Published enumeration; `20` (Matrix 1) and `75` (Monitor R) written to a desk through X32-Edit and read back as written; the rest not yet seen in a file |
| Output taps `26`–`57` on the `main`, `aux`, `aes` and `rec` banks | Published; observed on `p16` only |
| Gate and dynamics `keysrc` `1`–`64` | Published enumeration; only `0` observed. Whether `1`–`32` names a channel or an input slot is unverified |
| User-assign codes naming a channel (`Fxx`, `Pxx`, `Sxxyy`, `Oxx`, `Ixx`, `Pxx0z`) | Published; only the factory `P0000` observed |
| Automix on channels 1–8 only | Published; not verified on a console |
| Send taps `IN/LC`, `<-EQ`, `GRP` | Taken and read back verbatim on a desk (OSC root write, `/node` read-back, firmware 4.06); not yet seen in a saved file |
| Output lines in a `.rou` | Published; not yet seen in a file |
| GEQ band labels | Verified on a console for `GEQ` and `GEQ2` (fader labels, and `par` 1, 31 and 33 moved the 20 Hz, 20 kHz and B-side 20 Hz faders); `TEQ`/`TEQ2` assumed to match |
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

**Routing presets** (`.rou`), as x32scene writes them, are the four input routing banks,
`/config/routing/{IN,AES50A,AES50B,CARD}`, as scene lines. Each block token comes from a
fixed vocabulary per bank and block (`tables.routing_vocab`): 24 input-bank sources for
`IN`/`PLAY` plus 16 for their `AUX` block, 36 for the `AES50A`/`AES50B`/`CARD` blocks
(inputs, outputs, P16, `AUX/CR`, `AUX/TB`, user slots), and 36 four-wide ones for `OUT`,
where blocks `1-4`/`9-12` take the low half of each eight (`AN1-4`, `AN9-12` …) and
`5-8`/`13-16` the high half. The two monitor tokens the protocol document spells
`AUX1-6/Mon` and `AuxIN1-6/TB` are written `AUX/CR` and `AUX/TB`. `extract-routing` writes a
preset; `set-routing` edits a bank. The protocol document's routing-preset list is longer:
`/config/routing/routswitch`, `OUT` and `PLAY`, and the `/outputs/main`, `aux`, `p16` and
`aes` lines with their `/delay` and `/iQ` siblings. A routing preset may therefore carry the
output patch, channel direct outs included — published, not yet seen in a file.

**Show files** (`.shw`) are an index X32-Edit writes next to `<show>.NNN.scn` and
`<show>.NNN.snp` companions: a `show "<name>" …` line, then one `cue/NNN`, `scene/NNN` or
`snippet/NNN` line per slot. A scene or snippet line carries that file's own header fields;
the companions are byte-identical to standalone exports. A cue line is

```
cue/000 100 "Opener" 0 0 -1 0 1 0 0
```

the cue number times 100 (`1.2.3` is `123`), its name, skip, the scene slot and snippet
slot it recalls (`-1` for none), then the MIDI type, channel and two values. `x32scene
show` lists one and `show --check` checks its cues and companions; `x32scene show-build`
writes one from scene and snippet files and cue lines, in the shape X32-Edit imports.

**Cues** pair a scene with a snippet (and MIDI); they live only in the show index.
