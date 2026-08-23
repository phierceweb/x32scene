# What the console does when it loads your file

A file that round-trips byte-for-byte and diffs clean can still not do what you meant once
the desk reads it. Round-trip proves the file is *structurally* correct; only the console
proves it is *semantically* correct.

Everything here was learned by writing a file, loading it on hardware, saving the live state
back off the desk, and diffing the two. That loop is at the bottom — it is the only ground
truth, and it is worth running before you trust any generated scene at a gig.

## The scene name comes from the filename, not the header

The desk names a scene from its **filename / console slot**, and overwrites the `#4.0#`
header title on its next save. Setting the header title is still correct for a file you will
read back with a tool, but do not rely on it for what shows on the console.

## Cosmetic re-normalization is expected and harmless

On load the console rewrites tokens into its own house style. All of the following are
normal and mean your value was accepted:

- **Numeric columns are re-padded.** Editing a line collapses the console's alignment
  spacing; the desk restores it.
- **Decimals are forced.** `+4.0` becomes `+4.00`; a ratio of `4` becomes `4.0`.
- **Frequencies snap to the console's own steps.** `4k50` may come back `4k52`, `3k00` may
  come back `2k99`. The desk has a fixed detent grid and moves your value to the nearest
  one. The same holds for every logarithmic effect parameter: a reverb decay of `2.10`
  loaded through X32-Edit came back `2.11`, a damping of `8k00` came back `8k34`.

A value being valid means it survives as the nearest detent — not that it comes back
character-identical. Do not treat a snapped frequency as a failed write.

## A bad token aborts the rest of the line

This is the most dangerous failure mode, because it is silent and partial.

If a token is **in range but in the wrong format**, the console rejects it and **abandons
parsing the remainder of that line**. Fields *before* the bad token take; every field
*after* it reverts to its previous value on recall.

The known case is the compressor ratio. `/dyn` field 6 must be a canonical enum token —
single-digit ratios carry one decimal (`4.0`, not `4`). Writing a bare `4` means `on` and
`thr` apply while ratio, knee, makeup, attack, hold and release all silently revert.

The signature to recognize: **the first few fields of a line took, and everything after one
particular field did not.** That is a format rejection, not a failed edit and not a muted
channel.

The defence is to match the corpus's exact string formatting, not merely the value. Two
fields that look interchangeable often are not — the low-cut frequency in `/preamp` is a
bare integer (`80`) while an EQ frequency carries a decimal (`80.0`).

## Scene recall is scoped, and channels can be safed

A scene load does **not** necessarily overwrite everything in the file. The console's Scene
Scope and Channel/Parameter Safes let a user protect parts of the desk from recall.

In practice this means a generated scene may load only partially, and which parts depends on
settings that live on the console, not in your file. Observed directly: an output-routing
port applied every `/outputs/*` line verbatim, while several untouched channels kept the
desk's own values rather than the file's.

If an edit "didn't take", check the desk's scope and safes before suspecting the file.

The safes fall into eight groups — per the OSC protocol documentation, not the load loop
below: Talkback, Effects, Mix Buses, Channel Process, Configuration (channel links, mute
groups, DP48, monitor and solo settings), Preamp (head-amp gain, +48V, channel HPF, trim and
polarity), Output Patch (every `/outputs` bank and the user-out slots) and Routing I/O (the
routing banks and REC/PLAY). Everything `preflight` checks for the monitor skeleton sits in
the last three. When a checked value did not take on recall, one of those groups being safed
is the first thing to rule out.

## Stereo-linked pairs reconcile on recall

Buses, channels and other strips can be **stereo-linked in pairs** (`/config/buslink` and
friends carry one ON/OFF token per pair). On recall the console reconciles a linked pair.

The consequence: **writing one side of a linked pair is not durable.** If you set the odd
bus and leave the even side untouched, the link reverts the odd side's level to match the
untouched even side when the scene is recalled. Pan and tap live on the odd line only, so
they survive — producing the tell-tale pattern *pan and tap recalled correctly, level did
not, and only one bus was affected.*

Anything that copies or sets a send must write **both sides** of a linked pair. x32scene
does this by default and exposes `--no-link` to opt out.

Note this interacts with the parity rule in [format.md](format.md#bus-sends--and-the-oddeven-field-count-invariant):
the even-side line carries only `<on> <level>`, which is exactly the field that must match.

## Effect parameter order is real but type-specific

`/fx/N/par` is positional and specific to the effect type. The orders x32scene ships were
confirmed by correlating real `par` values against the console editor's own parameter
display, field by field.

One quirk worth knowing: a parameter the editor draws as a separate top-level knob may still
sit in the middle of the positional list. On a plate reverb, `Level` is parameter index 5
even though the UI presents it apart from the bottom parameter row.

Every effect type's order has since been corroborated against a line a console wrote — the
desk's own effect library and the default parameter line it returns for each type — so
all 61 read and write. The graphic EQs are the exception: their band gains decode but the
band labels are the standard ISO series, not desk-verified, so writes are refused.

## Getting a file onto the desk

The desk reads a file two ways, and they are not the same act.

**From a USB stick, on the desk itself.** The Scenes, Library and Utility pages import
`.scn`, `.snp`, `.chn`, `.efx` and `.rou` files into the desk's own slots and recall them
from there. This is the path that honours a snippet's header masks and a preset's recall
scope on the console.

**Through X32-Edit.** Its Import buttons read the same files onto the computer, and its
Load buttons then push the values to the desk from there. Observed on a live console:

- Library → Import + Load applied an effect preset to a slot, but the desk's own library
  slot stayed empty — X32-Edit never wrote it. The same for a routing preset.
- Show Control → Snippets → Import + Load applied a snippet's body; a full pull afterwards
  differed from the baseline in exactly the snippet's lines. The snippet did not reach a
  desk show slot, and Copy/Paste does not cross from the computer list to the Mixer list.
- The same route carried a **whole monitor mix** between two bands' scenes: with one
  band's scene loaded, a 144-line snippet of another band's bus pair (both bus strips and
  every sender's send into them) was loaded. A full pull differed from the first scene
  in exactly that pair's lines — 58 channel sends, 8 FX-return sends, 4 aux-in sends and
  the two bus names — and every one of the 134 paths that make up the mix matched the
  second scene byte for byte. Every other aux was untouched. Reloading the first band's
  scene returned the desk to a zero-diff pull.

X32-Edit's Load pushes a file's lines from the computer. Loading the same file from a USB
stick on the desk is the other route, through the desk's own recall and its header masks;
the body is identical either way, but that route has not been watched.
- Library → Routing → Load has a **Recall Patching Scope** panel with eight ticks, all on
  by default. Five cover sections a routing preset does not carry (XLR out, out patch,
  aux and P16 patch, user slots); untick those or X32-Edit may write defaults there.
- X32-Edit's scene export equals the desk's own state byte for byte apart from the title,
  so its files are ground truth for token formats.

## The load test — the only ground truth

Reading values off the console's on-screen editor is unreliable. So is trusting the file you
just wrote. The loop that actually settles a question:

1. Write the file with x32scene.
2. Load it on the console.
3. **Save the live state back off the desk** to a new file.
4. `x32scene diff yours.scn from-desk.scn`

The diff shows precisely what the console accepted, rewrote, or ignored. A full-scene diff
is what turns "the monitor mix didn't load" into "only bus 11's level differs, and its pair
is unlinked in the file" — which points straight at the cause.

Two cautions from experience:

- **The first save-back may be a file echo, not a real recall.** Make sure the console has
  actually recalled the scene, not merely re-exported what it was handed.
- **Wrong theories are cheap and confident.** In one investigation, channel safes, dropped
  OSC messages and load scope were each blamed before the full-scene diff showed a
  one-sided write to a stereo-linked pair. Diff first; theorize second.

Keep experimental scenes out of the directory you load from at a gig.
