# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [0.4.0] — 2026-09-14

### Added
- `swap-strips SCENE A B`, `move-strip SCENE FROM --to TO` and `reorder-strips SCENE
  FROM:TO…`: channel strips to new positions. Every `/ch/NN` line travels whole; channel
  direct-out taps on every output bank, `/config/chlink` and user-assign codes naming a moved
  channel (the factory `P0000` included) follow it, each rewrite printed. All-or-nothing;
  refuses a mapping that is not a permutation, a stereo-linked pair split or reversed, a key
  source 1–32 naming a moving channel, an automix group crossing channels 1–8, and an input
  that is not a `.scn`. Refused in `snippet --edit`.
  Library: `services.stripmove.permute_channels`, `swap_mapping`, `move_mapping`,
  `unexpected_changes`; `services.userctrl.strip_index`, `retarget`;
  `tables.tap_to_channel`, `channel_to_tap`; `Line.padded_fields`, `Line.set_fields`,
  `model.put_field`.
- `set-send-tap SCENE STRIP BUS TAP`: a channel, aux-in or FX-return send's tap point,
  written on the odd bus line of the pair and mirrored to a stereo-linked strip unless
  `--no-link`; an even BUS names the odd line it writes. Carried by `snippet --edit`.
  Library: `services.iem.set_send_tap`, `send_strip_group`, `tap_bus`.
- `set-record SCENE TRACK SRC`: a USB card record track's source, written into the
  `/config/userrout/out` slot its CARD block reads; SRC takes the words `record-map` prints
  or 0–208. Names every other AES50, card or XLR channel the slot feeds; refuses a track
  whose CARD block is not `UOUT…`. Carried by `snippet --edit`.
  Library: `services.routing_edit.set_record`, `record_slot`, `encode_out_source`;
  `services.routing.user_out_readers`.
- band-setup plan key `record`: card record track → source words, written through each
  track's CARD block after `routing`; a non-`UOUT` block, an unknown source or two tracks
  naming different sources for one slot is a plan error, exit 2. Each track prints as
  `set-record` prints it, with every other destination its slot feeds.
  Library: `band_swap.apply_plan` and `run` report `record`; `routing_edit.record_row`.
- `--console MODEL` and `X32SCENE_CONSOLE` on `ports`, `report` and `preflight`: the
  console's main output jack count from its model (X32 and M32: 16; X32 Producer, X32
  Compact, X32 Rack and M32R: 8; X32 Core and M32C: 0; each from its manual), by
  `/xinfo` model string or product name in any case. `preflight --regenerate` writes it as
  `monitor.physical_outputs` with `require_reachable`; `preflight` fills a config that
  declares no count; `ports` and `report` label physical and virtual outputs. A config
  declaring another count, or an unknown model, is refused. `monitor.physical_outputs`
  takes 0-16: with 0, every main output is virtual.
  Library: `services.console_models.console_model`, `main_jacks`;
  `preflight_regen.regenerate(..., console=)`.
- `set-fx --set` and a plan's `fx.params` write the `GEQ` and `GEQ2` bands by their labels
  (`20` … `20000`, `Master`; `20 A`, `20 B` on the dual), in the desk's own `3.0` form. Verified
  on a console; `TEQ` and `TEQ2` stay read-only.
- `--json` on `info`, `buses`, `explain`, `audit` and `live-diff`. `audit --json` carries
  `ok` and keeps its exit codes; `live-diff --json` carries `changes` and `unanswered`, with
  warnings on stderr. Library: `services.buses.channel_names`, `bus_names`, `bus_rows`;
  `services.audit.routing_drift`, `record_patch_drift`.
- `show FILE.shw --check`: a FAIL line for a file with no `show` line (empty, header-only
  or another kind), for each cue that is not a whole cue line (a scene or snippet field that is
  not a number included; plain `show` lists it undecoded), for each cue naming a scene or snippet slot the index
  lacks, and each slot whose `<show>.NNN.scn` / `.snp` companion beside the `.shw` is
  missing, unreadable, misshapen, of the other kind, or (a snippet) carries a header its
  `snippet/NNN` line does not; exit 1 on any. `--json` as `preflight`'s document.
  Library: `services.show_check.check_show`, `check_cues`, `companion`; `Show.has_show_line`.
- `x32scene --kind scn|snp|chn|efx|rou|shw COMMAND …`: the kind of a named file whose
  extension is none of those, for its shape warning, the `.scn`-only refusal of
  `swap-strips`, `move-strip` and `reorder-strips`, and `preflight --regenerate`'s
  needs-a-scene refusal. A file named with a kind's extension keeps its own.

### Changed
- `UdpTransport` moved from `services.watch` to `services.osc`.
- The sdist no longer carries `tests/`; the suite runs from a repository checkout.
- `x32scene --help` opens with what the tool does and where to read on (`x32scene <command>
  --help`, docs/cli.md) instead of the CLI module's internals.
- Every word from a fixed list is accepted in either case — `set-mute` and `set-output
  --invert` `on|off`, `set-routing` KEY and `switch REC|PLAY`, `set-output` BANK and `--pos`,
  `ports` and `apply-routing --bank`, `vocab`, `meters`, every `--scope` — and written in its
  canonical spelling. Library: `routing_edit.set_routswitch` and `set_output(pos=)` fold case.
- `band-setup` prints every changed path grouped by strip after its summary line, marking
  `(mirrored)` each send a stereo-linked pair wrote without the plan naming it.
  Library: `band_swap.mirrored_paths`; `verify` and `run` report `mirrored`.
- `apply-preset` without `--scope`, and a `band-setup` preset without `scopes`, apply only
  the sections a preset header flags present and name the scopes they skipped (`/delay` by
  path, under the config flag); a headerless
  preset is unchanged, and `presets-diff` compares the same scopes. The config flag selects
  `/delay` with `/config`; a header with no 16-bit flag mask selects as a headerless preset
  does, and `header` shows it with no sections. `extract-preset --header` flags the config
  section for `/config`.
  Library: `presets.header_scopes`, `unflagged_scopes`, `preset_selects`;
  `band_swap.apply_plan` and `run` report `preset_skipped`.

### Fixed
- `show-build` writes its index and companions all or none, refusing a directory at any
  target name before writing, as `extract-preset --all` does.
- `band-setup` applies a channel preset whose main mix is saved one field per line
  (`/mix/fader`, `/mix/pan` …) instead of refusing its own `/ch/NN/mix` write as out-of-plan.
- `ports` for a console whose 16 main outputs are all jacks heads the list without a
  `17-16 = virtual` range.
- `extract-preset --all --force` puts back every original it already replaced when a later
  target cannot be replaced, naming that target rather than the staging folder, and removes
  a DIR it created when nothing is written.
- `presets-diff` skips `._` AppleDouble sidecars and anything in DIR that is not a regular
  file, so a sidecar is no longer `UNREADABLE` and a pipe named `*.chn` no longer hangs it.
- A write that fails (a missing folder, a directory in OUT's place, no permission) names the
  OUT given, not the temporary file behind it, for every `-o` writer and `--regenerate`.
  Library: `Scene.save` raises the OSError against its path; `model.write_file`.
- A file that is not UTF-8 is refused in one line naming it — a scene, snippet or preset as
  not a console text file, a plan, preflight config or stage sidecar as not a JSON document —
  instead of a codec error naming nothing. Library: `Scene.load` and `model.read_file` raise
  ValueError.
- A plan, preflight config or stage sidecar that repeats a key inside one object, at any
  depth, is refused naming the key and file instead of keeping the last value: `band-setup`
  exits 2 with nothing written, `preflight` exits 1. Library: `services.jsonfile.read_json`.
- `preflight SCENE --regenerate` exits 1 with nothing written when SCENE has no channel
  strips (a JSON file, a header-only scene), instead of writing a near-empty config.
- `pull`, `live-diff` and `watch`'s start pull exit 2 once 8 paths in a row go unanswered,
  no late reply arrived during them, and the last path that answered does not answer again,
  instead of waiting out every
  remaining path. Library: `pull_lines(give_up=)`; `pull_scene_like` defaults it to
  `osc.GIVE_UP`.
- `watch` never takes a late `/node` reply to an earlier read-back for the answer to a newer
  one, so a stale line no longer reaches the log, the net change or `--snippet`, and a reply
  nothing asked for is ignored; nor does a slow reply that lands after its retry's fresher one.
  A path whose reply could answer either is asked again once
  every read-back of it still out is `watch.LATE` reply timeouts old, so one slow reply
  during a fader ride holds that path for one such window rather than until the ride stops.
- `watch` no longer dates a change from a push its start pull already held. Library:
  `pull_lines(asked=)`, `pull_scene_like(asked=)`, `Watch.run(pulled=)`.

### Docs
- `docs/console-behavior.md`: the main-pan rule for linking and unlinking a bus pair,
  observed from ten starting pan pairs; `set-bus-link` matches the desk in each.
- console-behavior.md: a `swap-strips` file root-written to the desk line by line matched a full
  pull, remapped direct-out tap and user-control page jumps included.
- console-behavior.md: the table-of-contents link to the load test resolves on GitHub, and
  `set-bus-link` records its X32-Edit load test.
- cli.md: `watch` states which paths the end of a watch asks again, and how often.
- format.md: a Channel references section (values that point at a channel, key sources,
  look-alikes); `/ch/NN/config` field order corrected to name, icon, colour, source; the
  `keysrc` enumeration and which dyn lines carry it; automix acts on channels 1–8 only;
  user-assign `P0051` is the FX1 page; routing presets may carry output lines (published).
- format.md: how a channel preset header's section flags map to apply scopes.
- format.md: the send taps `IN/LC`, `<-EQ` and `GRP` are desk-verified (written and read back on
  firmware 4.06) but not yet seen in a saved file.
- console-behavior.md: X32-Edit load tests on firmware 4.06 — a `swap-strips` scene, a
  `band-setup` scene (channel processing, an FX type and parameter, a CARD block, a record
  slot, `rec`/`aes` taps), a routing preset that changes a block, and a `--header` channel
  preset all loaded as written; which channel-processing values the desk snaps; a write to
  one side of a stereo-linked channel pair mirrors to the other, so a one-sided file ends
  at the even side's values.
- format.md: `GEQ`/`GEQ2` band order and gain form verified on a console; output taps `20`
  and `75` written and read back; X32-Edit reads a preset header x32scene writes.

## [0.3.0] — 2026-09-12

### Added
- `preflight SCENE --regenerate OUT.json`: writes the expected-config SCENE satisfies instead
  of checking it — every section the scene holds, keys sorted, byte-identical for the same
  scene and date. A value the scene cannot verify is left out; `monitor.physical_outputs` and
  `require_reachable` are never written. Refuses an OUT that is a directory or sits in no
  writable directory, an existing OUT without `--force`, the scene itself, an OUT named as a
  scene, snippet, preset or show file even with `--force`, a snippet, preset or show file as
  SCENE, and `--config`, `--stage` or `--json` alongside.
  `--force` without `--regenerate` exits 1.
  Library: `services.preflight_regen.regenerate`, `dumps`.
- `move-inputs SCENE CH:IN… --to A|B`: channels onto AES50 stage-box inputs (port in either
  case), head-amp gain and phantom travelling with each (`--no-gain` leaves them).
  All-or-nothing; refuses a channel listed twice, two channels onto one input, a user-in
  slot another channel or aux-in also reads, and a gain move onto an input a channel or
  aux-in outside the batch still reads.
  Library: `services.stagebox.move_to_stagebox`, returning each move.
- `set-bus-link SCENE BUS on|off`: links or unlinks a stereo mix-bus pair with the changes
  the desk makes — on link, the even bus takes the odd bus's send on/level from every
  sender, its colour, key filter and matrix sends, and — as the scene's link preferences
  allow — its EQ, dynamics and insert, groups and mix; matrix-send pans spread and centred
  main pans spread. On unlink, matrix-send pans centre and fully spread main pans centre.
  Prints the outputs either bus feeds. Refuses a pair already in that state and a scene
  missing a line it writes. `on|off` in either case. Refused in `snippet --edit`: a snippet
  cannot carry the link.
  Library: `services.buslink.set_bus_link`, `relinked_pairs`,
  `services.routing.outputs_from_buses`.
- `presets-diff DIR SCENE`: each `.chn` in a folder against the channel it names — MATCH,
  DRIFT with each differing path, NO CHANNEL, AMBIGUOUS or UNREADABLE, and a count per
  verdict. Compares tokens over the paths the preset carries (`--scope` narrows), the head
  amp by value at the channel's current input, and a desk-written preset's `/config` and
  split main-mix lines field by field. Exit 1 when a preset drifts or is UNREADABLE; `--json`.
- `extract-preset SCENE --all -o DIR`: one `<scribble name>.chn` per named channel. Channels
  sharing a file name are all skipped and named. The rest are written in full to a staging
  folder before any target is replaced; refuses a directory in a target's place, every file name the filesystem refuses, a DIR that is not
  a directory or cannot be written and, without `--force`, any existing target.
  Library: `services.preset_library.check_library`, `extract_library`.
- `watch REFERENCE`: a timestamped log of every change made on the running desk, one line
  per changed path, dated when the desk reported it, with the moved fields named, ending
  on Ctrl-C or `--seconds` with the net change, the count of paths that changed and came
  back, ignored addresses, and the paths whose last read-back never answered, left out of the
  net change. A network failure mid-watch still prints the summary and writes the snippet,
  then exits 1. Subscribes before the
  start pull, so a change to a path already pulled is logged. `--snippet OUT.snp` writes the
  net change as a snippet, its destination checked before the watch starts; `--json` writes
  JSON lines.
  Sends only `/xremote` and `/node`.
  Library: `services.watch.Watch`, `subscribe`, `Subscription`; `services.osc.node_line`,
  and `between=` on `pull_lines` and `pull_scene_like`.

### Changed
- Licensed under Apache-2.0 (was MIT), with a `NOTICE` file.
- `snippet A B` and `watch --snippet` warn when the snippet carries a line of a bus pair whose
  link changed: a snippet cannot carry the link.
- A `.chn` read with no bare channel path, or with more than one head-amp line, prints a
  shape warning on stderr.

### Fixed
- `pull`, `live-diff`: a `/node` reply holding more than one line is reported unanswered,
  never written into the scene.
- `diff --by-strip` names a bus's or the main's send to a matrix `send -> matrix N`, not
  `send -> bus N`.
- `apply-preset` takes a desk-saved preset: its three-field `/config` (the source slot
  stays the channel's) and its per-field `/mix/fader`, `/mix/st`… lines. A preset with EQ
  bands 5-6 — a bus, matrix or main strip — is refused, in a `band-setup` plan too.
- `transforms.move_inputs_to_stagebox`: chained and swapped moves in one batch carry each
  channel's own head amp.
- A line with no values that an edit writes, or an `iem_copy` reads, is a one-line error
  naming it: exit 2 with nothing written for `band-setup`, 1 elsewhere.
- A plan, preflight config or stage sidecar nested too deeply to parse is a one-line error
  naming the file (exit 2 for `band-setup`, 1 elsewhere).
- A symlink loop as an input or `-o` path is a one-line error, not a traceback.
- `x32scene <command> --help` opens with the command's description.
- `buses` tallies an unlinked even bus's sends, taking each sender's tap from its odd-bus line.

### Docs
- `docs/band-plan.md` and `docs/preflight-config.md`: the two JSON documents that check or
  write a scene — every section, every key, and the rules that decide whether one is
  accepted.
- `docs/python-api.md`: the library map for a script — the layers, `Scene` and `Line`,
  what each service owns, and what the library leaves to the caller.
- A table of contents in every doc, and `tests/test_docs.py`, which fails the build on a
  command missing from `docs/cli.md`, a flag that appears nowhere in it, a flag a command's
  row names that the command does not take, a doc missing from the index, a
  table-of-contents entry with no heading, or a relative link to a missing file.

## [0.2.0] — 2026-09-07

### Added
- Every file named on the command line is checked for the shape of its kind, and a
  mismatch — a truncated scene, an empty file, text that is not a scene, a header-only
  snippet — warns on stderr. A warning, never a refusal: the exit code is unchanged and
  `--json` stays a clean pipe. `audit` reports the same finding as an exit-1 violation.
  Each kind is judged by its own shape, so a headerless `.chn`, an unpadded `.shw` header
  and a partial `.snp` all pass. Presets a `band-setup` plan names, and the library sweeps
  `audit` and `history`, keep their own reporting.
- `--force` on every command that writes.

### Changed
- An `-o` that already exists is refused without `--force`. An input is refused outright
  and `--force` does not unlock it — including files an argument does not name: presets a
  `band-setup` plan reads, a preset named inside `snippet --edit`, and the scenes and
  snippets `show-build` writes alongside in `-o DIR`.
- `pull`, `live-diff`, `desk` and `meters` accept a reply only from the desk's own
  address; a hostname is resolved before the comparison.
- `desk` gives up after three unanswered queries rather than sweeping every slot.
- All 47 subcommands appear in `x32scene --help`.

**Breaking:** an invocation whose output already existed used to succeed and now exits 1.
`--f` no longer abbreviates `--freq` on `set-eq` and `set-lowcut`, since `--force` now
shares the prefix.

### Fixed
- A plan that is not a JSON object is a plan error — exit 2, nothing written.
- A JSON boolean in a plan is refused rather than read as a number, for a channel
  `source`, an output `src` and an FX `params` value.
- A plan's `title`, a channel `name` and every `preset` path must be strings; a wrong type
  is a named plan error.
- A `routing.banks` entry must be one of the console's bank names.
- Two plan keys naming one FX slot or one output — `"9"` beside `"09"` — collide instead
  of applying in JSON key order, and a zero-padded key names the path the plan writes.
- A meter blob with a negative float count, or a non-finite level, is rejected; one
  unusable frame no longer discards the window.
- `--timeout` and `meters --seconds` are bounded, from the flag and from
  `X32SCENE_TIMEOUT`.
- `desk` keeps `--timeout` as an upper bound while filtering replies by sender.
- `pull` with a reference carrying no queryable paths returns empty.

## [0.1.0] — 2026-09-07

First release.

### Files
- Byte-faithful parser for every file the console reads and writes — scenes (`.scn`),
  snippets (`.snp`), channel, effect and routing presets (`.chn` `.efx` `.rou`) and shows
  (`.shw`): `Scene.parse(text).dump() == text`. CRLF files and tokens that would break a
  line are rejected; headers of every firmware revision keep their padding through an edit.
- `header` decodes any file's header: scene safes, snippet filter masks, a preset's slot,
  kind and sections. Bit orders confirmed against files a console and X32-Edit wrote.
- Every line family a full scene carries has named fields (`tables.line_fields`); every
  enumeration spelling was read back from a console, including the full send-tap and
  output tap-point lists, the FX default parameter line for all 61 effect types, and the
  routing bank vocabulary as scenes spell it.

### Reading
- `info`, `inputs`, `ports` (`--bank`, `--config`, `--stage`), `buses`, `iem`, `iem-matrix`
  (`--compare`), `record-map`, `fx`, `fx-types`, `dca`, `console`, `explain`, `report`,
  `show`, `vocab`; `diff` (`--by-strip` names the strip and the fields that moved),
  `history` across a dated library, `audit` of a library's invariants. `--json` throughout.

### Editing (always to a new file)
- Strips: `rename`, `set-fader`, `set-mute`, `set-pan`, `set-eq`, `set-lowcut`,
  `set-comp`, `set-gate`; edits mirror to a stereo-linked partner unless `--no-link`.
  Values are written in the console's own token formats, checked at the range ends.
- FX: `set-fx` by parameter name; a type change resets to the desk's default line; slots
  5–8 refuse the types the desk keeps out of its side rack.
- Routing: `set-routing`, `set-input`, `set-output`, all checked against the console's
  vocabulary.
- Between scenes: `transplant` (a whole monitor mix, path patterns, or a channel's
  sections with the head amp re-mapped); `extract-preset` / `apply-preset`,
  `extract-fx` / `apply-fx`, `extract-routing` / `apply-routing`, `port-iem`.
- `snippet`: a delta between two scenes, edits applied in memory, or one monitor mix
  whole (`--bus`, `--only`); filter masks derived from the body, split lines carry only
  the fields that moved.
- `band-setup`: one JSON plan for names, presets, head amps, faders, DCAs, monitor
  copies and trims, per-channel processing, FX, routing and output patch, validated
  whole and verified to change only the paths it named; `--snippet` writes the delta.
- `show-build`: a show index with cues and its companion files, as X32-Edit imports them.

### Checks
- `preflight` against an expected-config: outputs, monitor skeleton, routing, stereo
  links, send taps and presence, groups; a stage sidecar (`--stage`) for the jack, box,
  device and wearer each output feeds. `FAIL` exits 1; reports end with what was checked.

### Live desk (read-only)
- `pull` the running desk into a scene file, `live-diff` against a file, `desk` for
  identity, status, preferences and memory slots, `meters` for each slot's peak.

### Docs
- `docs/capabilities.md`, `format.md`, `console-behavior.md` (including how a file reaches
  the desk and what the desk snaps or rejects), `routing.md`, `stage-sidecar.md`.
