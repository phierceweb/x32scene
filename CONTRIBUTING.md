# Contributing to x32scene

Thanks for your interest. Bug reports, format findings, and console-verified fixes are all
welcome.

## The one rule: don't break the round-trip

`Scene.parse(text).dump() == text` is the correctness anchor. Every line is preserved
verbatim unless a transform deliberately changes it — that is what makes editing a scene
safe. Any change that breaks round-trip on a real file is a bug, no matter what else it
fixes.

Before opening a PR, run the round-trip against your own scene library:

```bash
X32SCENE_CORPUS=~/path/to/your/scenes bin/run pytest tests/test_roundtrip.py
```

If you find a file that does **not** round-trip, that is the most valuable bug report you
can file. Please include the console model, firmware version, and how the file was saved —
you don't need to attach the scene itself.

## Setup

```bash
python3 -m venv .venv
bin/run pip install -e ".[dev]"
bin/run pytest
bin/run lint
```

## Conventions

- **Verify against real hardware or a real file.** Decoding claims need evidence — a scene
  the console wrote, or a console re-save that confirms a value took. A value that is
  in-range but wrong-*format* can be silently rejected by the desk.
- **One concern per file.** `bin/run lint` runs pf-core's structural gate; the limits are
  pf-core's `GuardsConfig` defaults. If a file is over, split it rather than grandfathering it.
- Single-domain operations go in `services/`; multi-step workflows in `orchestrators/`;
  presentation in `_views.py`. The library layer stays free of logging and CLI concerns.
- `X | None` types, src-layout, no `sys.path` manipulation.
- Edit commands must never overwrite in place — write a new file.

## Tests

New behavior needs a test. Tests must pass on a fresh clone with no hardware and no user
files — use `tests/fixtures/*.scn`. Anything needing a real console or a personal scene
library is opt-in behind `X32SCENE_CORPUS` and must skip cleanly without it.

## Reporting security issues

Email **oss@phierceweb.com** rather than opening a public issue.
