# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

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
