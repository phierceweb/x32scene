# What the console does when it loads your file

A file that round-trips byte-for-byte and diffs clean can still not do what you meant once
the desk reads it. Round-trip proves the file is *structurally* correct; only the console
proves it is *semantically* correct.

Everything here was learned by writing a file, loading it on hardware, saving the live state
back off the desk, and diffing the two. That loop is at the bottom — it is the only ground
truth, and it is worth running before you trust any generated scene at a gig.

---

## Table of contents

- [The scene name comes from the filename, not the header](#the-scene-name-comes-from-the-filename-not-the-header)
- [Cosmetic re-normalization is expected and harmless](#cosmetic-re-normalization-is-expected-and-harmless)
- [A bad token aborts the rest of the line](#a-bad-token-aborts-the-rest-of-the-line)
- [Scene recall is scoped, and channels can be safed](#scene-recall-is-scoped-and-channels-can-be-safed)
- [Stereo-linked pairs reconcile on recall](#stereo-linked-pairs-reconcile-on-recall)
- [Linking or unlinking a pair](#linking-or-unlinking-a-pair)
- [Effect parameter order is real but type-specific](#effect-parameter-order-is-real-but-type-specific)
- [Getting a file onto the desk](#getting-a-file-onto-the-desk)
- [The desk's own show memory](#the-desks-own-show-memory)
- [The load test — the only ground truth](#the-load-test--the-only-ground-truth)

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
  loaded through X32-Edit came back `2.11`, a damping of `8k00` came back `8k34`. Channel
  processing snaps the same way: an EQ band at `200.0` came back `202.3`, a low cut at `80`
  came back `79`, a compressor release of `120` came back `124`.

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
friends carry one ON/OFF token per pair). Observed on firmware 4.06: **a write to one side
of a linked channel pair is mirrored to the other side at once.** A root write of a send's
level to the odd channel put the same level on the even channel's send, a tap point written
to one side appeared on the other, and the send pans stayed per side (`-100` / `+100`).
X32-Edit's Load pushes a file line by line, so a file whose two sides disagree ends with the
pair equal to whichever line was pushed last — the even channel's, in scene order: a scene
with a one-sided send level and tap loaded and came back with both sides at the even
channel's values, the odd side's edit gone. Recall from a USB stick on the desk has not
been watched.

The head amps follow the same rule when the `hadly` link preference is ON: a root write of
`+6.0` to the head amp feeding the odd channel of a linked pair put `+6.0` on the head amp
feeding the even channel within a second, and writing the first back took the second back
with it (firmware 4.06, an AES50 stage-box pair).

The consequence: **writing one side of a linked pair is not durable.** Anything that copies
or sets a send must write **both sides** of a linked pair. x32scene does this by default and
exposes `--no-link` to opt out; `preflight`'s `require_send_symmetry` checks a file for the
same reason.

Note this interacts with the parity rule in [format.md](format.md#bus-sends--and-the-oddeven-field-count-invariant):
the even-side line carries only `<on> <level>`, which is exactly the field that must match.

## Linking or unlinking a pair

The section above is about **recalling a file** whose linked sides disagree. This one is
about the **link itself changing** — the link key on the desk, or a `/config/buslink`
write — and what the desk writes into the live state the moment it does. Observed on a
mix-bus pair, bus N (odd) and bus N+1 (even), by toggling the link on firmware 4.06 and
pulling the full scene before and after, with the link preferences (`/config/linkcfg`) all
ON and then with each of EQ, dynamics and fader/mute turned OFF.

**Link.** The odd bus is the source. Bus N+1 takes from bus N:

- **Every sender's send** — channels, aux-ins, FX returns: the send to bus N+1 takes the
  on and level of the same sender's send to bus N. The bus N send lines, with their pan and
  tap, are untouched.
- **The strip**: the colour (the name and icon stay) and the dynamics key filter, always;
  the rest only when its link preference is ON:

  | Preference | Copied only when it is ON |
  |---|---|
  | `eq` | EQ on/off and all six bands |
  | `dyn` | dynamics and insert |
  | `fdrmute` | group membership, and every main-mix field but pan — on, fader, LR assign, mono assign, mono level |

  `hadly` (head amp + delay) was not seen to change anything on a bus.
- **The matrix sends**: on and level, and the tap on the odd matrix lines — whatever the
  preferences say, as are the sends above and the pans below.

Pans move too:

- **Matrix-send pans** (the odd matrix lines 1, 3 and 5): bus N goes to `-100`, bus N+1 to
  `+100`, every time.
- **Main pans** (`/bus/NN/mix` field 4): both centred go to `-100` / `+100`; any other pair
  stays as it was. Observed from ten starting pairs on firmware 4.06: `+0/+0` spread, while
  `+30/+0`, `+0/+30`, `+30/+30`, `-50/+50`, `-100/+100`, `+100/-100`, `+30/-20`, `-100/+0`
  and `+0/+100` stayed.

**Unlink.** The link token and pans only. Matrix-send pans centre to `+0` on both buses;
main pans at exactly `-100` / `+100` centre to `+0`, any other main pans stay — `+100/-100`
included (the same ten starting pairs). Sends and
strip settings stay as the link left them, so bus N+1 keeps bus N's copied values — link
then unlink does not restore what bus N+1 had.

Both directions keep every line's field count: send-line shape follows bus parity, not the
link ([format.md](format.md#bus-sends--and-the-oddeven-field-count-invariant)).

A **channel pair** linked by a `/config/chlink` root write (firmware 4.06, every link
preference ON) followed the same rules: the even channel took the odd channel's on and level
on every bus send and its colour (name and icon stayed), and the main pans and the odd-send
pans went from `+0`/`+0` to `-100`/`+100` on both sides. The pair's EQ, dynamics and
fader/mute were already equal, so that copy could not be seen. The copy is not instant: a
line written to the pair within about 0.1 s of the link line was overwritten by it, while
from 0.1 s on the write landed and mirrored its on and level to the other side, pans per
side. After an unlink, writes 0 to 1 s later mirrored nothing.

`x32scene set-bus-link` writes the same changes into a file. A file it wrote linking a pair
has been loaded through X32-Edit, and a full pull afterwards matched the file with zero
changed paths ([Getting a file onto the desk](#getting-a-file-onto-the-desk)).

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

Writing `/fx/N` with the type the slot already holds leaves `/fx/N/par` as it is. Writing
another type had reset `/par` to that type's defaults by the first read, 15 ms after the
write, and a `/par` line sent right after the type line held (0 to 0.5 s after it, firmware
4.06).

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
- Show Control → Scenes → Import + Load pushed a whole scene written by x32scene — one
  re-sourcing channels onto stage-box inputs with their head amps, one linking a bus pair.
  A full pull afterwards matched each file with zero changed paths. So did a `swap-strips`
  scene: two strips exchanged, a P16 output moved to the other strip's direct-out tap, and
  two user-assign page jumps re-pointed.
- The same route carried a `band-setup` scene with a channel's low cut, EQ band, compressor,
  gate and pan, an FX slot's type and a parameter, a CARD routing block, a record track's
  user-out slot, and `rec` and `aes` outputs re-pointed to Monitor R and Matrix 1. Every line
  took; three values came back on the desk's grid (EQ `200.0` as `202.3`, low cut `80` as
  `79`, compressor release `120` as `124`).
- Library → Routing → Import + Load of a routing preset that changes a CARD block, with
  only Channel In, AES50 Out and Card Out ticked in Recall Patching Scope, changed exactly
  `/config/routing/CARD`.
- Library → Channel → Import + Load of a channel preset x32scene wrote with `--header`:
  X32-Edit's Flags column showed exactly the sections the header flags present (gate, EQ,
  dynamics, with EQ lit as the active one), and Load wrote only those sections onto the
  selected channel, every Recall Scope tick on.
- Library → Routing → Load has a **Recall Patching Scope** panel with eight ticks, all on
  by default. Five cover sections a routing preset does not carry (XLR out, out patch,
  aux and P16 patch, user slots); untick those or X32-Edit may write defaults there.
- X32-Edit's scene export equals the desk's own state byte for byte apart from the title,
  so its files are ground truth for token formats.

**Over OSC, one line at a time.** A `/` root write of each line a scene changes sets those
nodes directly. It is what X32-Edit's Load does, minus X32-Edit. On firmware 4.06, a
`swap-strips` file exchanging two strips (52 lines) was loaded this way. The two strips, a
P16 output moved to the other strip's direct-out tap, and user-control page jumps
re-pointed to the moved channel (`P0000` to `P2800`) all took. A full pull matched the file
with zero changed paths. That proves the desk accepts the tokens; it is not a recall.

`x32scene load FILE` takes that route and adds the read-back: it writes every line the
desk does not hold, reads those paths back with `/node`, and writes again what still
differs, three passes by default. Observed on a Wi-Fi link (firmware 4.06): one X32-Edit
Load of a full scene left two or three sends at their old values, a different few each
time, and a second Load put them right — a line can go missing on the way, so a load is
not a load until it is read back. A line the desk still answers with another value after
the last pass is reported: its own grid (an EQ frequency, a pan) or a linked pair's mirror.
After an FX type line and after a link line `load` waits half a second, since the desk
follows each with writes of its own and a line written inside that window is lost to them
([Linking or unlinking a pair](#linking-or-unlinking-a-pair)). A file that links a pair
still takes two passes: the link moves lines the desk already held as the file has them
(the pans, the even side's sends), so they are written only once the read-back finds them.
For the same reason `load --keep-bus` and `--keep`, which leave lines as the desk holds
them, keep the other side of every pair the desk links where it copies a write, and refuse
a file that changes the link of a pair a kept line belongs to. A link line carries every
pair's token, but a token re-sent unchanged moves nothing: the channel-link write above
moved only the pair it changed while four linked pairs' `ON` tokens went out with it, and a
`/config/chlink` or `/config/buslink` line written back token for token changed no path. They
refuse a file that changes a `/config/linkcfg` preference gating a kept line on a linked
pair as well, since whether changing a preference copies across a pair already linked has
not been watched.
A root write sets the node whatever the desk's safes say: with a channel safed
(`/-show/showfile/show/chan32`), a root write of its pan still took. Safes govern recall,
so a load through root writes ignores them, and so would ignore a scene header's own safes
and a snippet's masks: `load` refuses such a file rather than write what a recall skips. Head amps on a stagebox read back late: of a
1,146-line load, the dozen AES50 head amps were the lines still reading their old values
0.2 s after the write, and held the new ones by the next pass.

X32-Edit's Load pushes a file's lines from the computer. Loading the same file from a USB
stick on the desk is the other route, through the desk's own recall and its header masks;
the body is identical either way, but that route has not been watched. A snippet saved into
a desk slot and recalled from there does honour them ([below](#the-desks-own-show-memory)).

## The desk's own show memory

The Show Control → Mixer tabs hold 100 scene, 100 snippet and 100 cue slots, all reachable
over OSC (observed on firmware 4.06). `x32scene desk` lists the occupied ones.

- `/save scene N "name" "notes"` and `/save snippet N "name"` write the desk's live state
  into slot N. A snippet slot captures its `eventtyp` categories for exactly the strips its
  masks select: a slot filtered to Send 9–12 on the channels, aux-ins and FX returns, saved
  and then recalled, moved those sends and nothing else. The Preamp HA category follows the
  channel mask the same way, so a snippet recalls head amps only for the channels it names.
  Send 1–8 is one category: a snippet cannot carry some of a strip's sends into buses 1–8
  without all of them.
- `/delete scene N` and `/delete snippet N` clear a slot.
- `/-action/gocue N` fires cue slot N (an action the protocol text does not list; observed).
  The recall lands without the *Confirm Pop-Ups →
  Scene Load* prompt, which X32-Edit's Go and the desk's own Mixer Cues Load wait for while
  `/-prefs/confirm_sceneload` is ON; that preference is writable over OSC.
- `/add cue` left slot 001 empty between the first and second cue added; writing the
  `/-show/showfile/cue/NNN/*` fields directly gives contiguous slots. A cue slot's `/node`
  reply has no hasdata field, unlike a scene, snippet or library slot: an empty one reads
  `0 "" 0 -1 -1 0 1 0 0`.

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
