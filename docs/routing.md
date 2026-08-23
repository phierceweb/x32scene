# Routing: the two-layer model

Routing is the hardest part of the X32 to read off a file, because the console has **two
parallel layers** that look alike in a scene and carry different signals. This page explains
the model; [format.md](format.md) has the raw field layouts.

The commands `x32scene inputs`, `record-map` and `ports` exist to resolve all of this for
you. Read this when you need to know *why* an answer came out the way it did — or when you
are patching by hand.

## Inputs: a channel does not name its jack

`/ch/NN/config "Name" colour icon SRC` ends with a source **slot** (1–32), not a physical
input. How a slot becomes a jack depends on the matching **8-wide block** in
`/config/routing/IN`:

```
/config/routing/IN UIN1-8 UIN9-16 UIN17-24 UIN25-32 AUX1-4
```

There are two kinds of block:

- **`UINk` — user input.** The slot is an index into `/config/userrout/in`, whose value is
  then decoded with the input enumeration. **Two hops.**
- **`ANk`, `Ak`, `Bk`, `CARDk`, `AUXk` — direct.** The slot maps straight onto that domain,
  offset by the block's own range. **One hop.**

A block carries its own range offset, so `UIN9-16` sitting in bank 0 maps slot 1 to
`userrout/in` index 8, not index 0. Getting this wrong shifts every channel by eight.

Once you have a source *number*, the head-amp index is `number − 1` for sources 1–128.
Card, Aux and OFF sources have no head amp.

## Outputs: `OUT` and `UOUT` are not the same signal

Every destination — AES50-A, AES50-B, the USB card, the rear XLR bank — does not carry
"buses" directly. It carries **assignable blocks**, each filled from one of a few source
banks. AES50-A and AES50-B carry six 8-channel blocks, the card four, and `/config/routing/IN`
four plus a fifth block for the aux bank. The rear XLR bank (`/config/routing/OUT`) is the odd
one out: four blocks of **four**, with their own vocabulary, and `OUT1-4 OUT5-8 OUT9-12
OUT13-16` on every console seen — it is the outputs themselves, not a way off the desk.

| Source bank | What it is | Hops |
|---|---|---|
| `OUT1-8`, `OUT9-16` | The **direct output bank** — the 16 outputs you assign on the XLR-Out page, each tapped from a bus, main or direct out | one |
| `UOUT1-8` … `UOUT41-48` | The **User-Out matrix** — a separate 48-slot patchbay you fill first, then point a block at | two |
| `P161-8`, `P169-16` | The 16-channel Ultranet / P16 personal-mixer bank | one |
| `CARD`, `AUX`, `AES50A/B in` | Returns used as sources (card playback, stage inputs passed through) | — |
| `ANk`, `Ak`, `Bk` | Direct inputs passed straight through — local, AES50-A, AES50-B | one |

**The trap: `OUT9-16` and `UOUT9-16` are different signals.** `OUT9-16` is the direct output
bank. `UOUT9-16` is whatever you patched into User-Out slots 9–16. Mixing both layers across
one card's blocks is legal and works — but it means you must look in two different places to
know what a given AES50 channel carries. This is the single biggest source of confusion when
tracing a rig from a file.

### Why the user layer exists

Out of the box every routing destination fills in **fixed blocks of eight**. On the direct
layer you cannot send eight arbitrary, individually-chosen signals to one card block.

(File tokens are not always the spellings the OSC documentation uses — a real file writes
`AUX/CR` and `AUX/TB` where the document says `AUX1-6/Mon` and `AuxIN1-6/TB`. The full
vocabulary per bank and block, spelled as files write it, is `x32scene vocab routing`;
`set-routing` and the `routing` plan section refuse anything outside it.)

The **User-In / User-Out matrices** are the official escape hatch: a free 32-slot (in) and
48-slot (out) patchbay where each slot takes *any* single source, after which you point a
block at `UIN…` / `UOUT…`. That is what makes a patch like "channels 29–32 come from
scattered card and AES sources" expressible at all — no fixed bank of eight can say it.

So: use the direct `OUT` layer when a whole 8-block lines up, and the user layer when you
need per-channel freedom. The cost is the two-place indirection.

### Reading a real block list

From [`tests/fixtures/example.scn`](../tests/fixtures/example.scn):

```
/config/routing/AES50A UOUT1-8 OUT9-16 UOUT17-24 UOUT25-32 UOUT33-40 UOUT41-48
/config/routing/AES50B UOUT1-8 UOUT9-16 OUT1-8 UOUT41-48 UOUT41-48 UOUT41-48
```

Two things to notice, both typical of real rigs:

- **Block 2 of AES50-A is `OUT9-16`, breaking an otherwise all-`UOUT` pattern.** On many
  consoles outputs 9–16 have no rear jack, so a card block is their only way out of the
  desk. A block like this is load-bearing — it is not an inconsistency to tidy up.
- **AES50-B repeats `UOUT41-48` across blocks 4–6.** Repeated blocks on an output-only or
  partly-unused port are placeholder filler, not a working patch. Harmless, but they make a
  patch look more deliberate than it is.

A tidier rig sources everything from the direct banks and makes both ports identical:

```
/config/routing/AES50A OUT1-8 OUT9-16 OUT1-8 OUT9-16 P161-8 P169-16
/config/routing/AES50B OUT1-8 OUT9-16 OUT1-8 OUT9-16 P161-8 P169-16
```

One page tells you everything, and either stage box carries the same feeds.

> **Re-pointing a block is a real re-patch, not a cleanup.** Because `OUTx` and `UOUTx` are
> different signals, changing a block from one to the other changes which signal physically
> lands on each stage-box output — and therefore which monitor feed. After any such change,
> walk every output and re-verify before trusting it.

## The record map

`/config/routing/CARD` says which bank fills each block of eight card-send channels:

```
/config/routing/CARD UOUT1-8 UOUT9-16 UOUT17-24 UOUT25-32
```

For a `UOUTk` block, the source is `/config/userrout/out[k−1]` — decoded with the **output**
enumeration, which is wider than the input one and is *not* interchangeable with it (see
[format.md](format.md#output-sources)). That decoded list, in order, is what your DAW
receives.

Worth knowing when reading an old file: **the record patch is not constant across a rig's
history.** A library can contain scenes that record raw inputs and scenes that record the
mix buses instead, depending on when they were saved. `x32scene audit` prints the chronology
so you can see where a patch changed.

## Changing routing from a file

`set-routing KEY BLOCK=TOKEN …` edits one bank's blocks, `set-input CH "aes50-a 3"` points a
channel at a source, `set-output BANK N --src "bus 12" --pos PRE+M` re-patches an output,
and `extract-routing` / `apply-routing` move the input banks as a routing preset. All of
them write a new file; load it and re-walk the outputs, because a routing change is a
re-patch of what physically reaches each jack.

## Troubleshooting "the signal isn't arriving"

A break at any of these three points looks identical at the far end. Check them in order:

1. Is the bus feeding the right **OUT** or **User-Out slot**?
2. Is the **card block** (`AES50A` / `AES50B` / `CARD`) pointed at that bank?
3. Is the **stage box's own output patch** sending that channel to the right physical jack?

Only the first two are visible in a scene file. The third is visible only if someone wrote it
down: a [stage sidecar](stage-sidecar.md) records which jack an output feeds and who hears it,
and `preflight --stage` checks the scene against that record. It is an operator's assertion,
not a reading of the stagebox — if all three check out on paper, the problem is downstream
of anything x32scene can see.
