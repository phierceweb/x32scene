# The stage sidecar

A `.scn` records only what happens inside the console. Which physical connector an output
lands on, which stagebox that is, which transmitter or headphone amp it feeds, and who is
wearing the pack are stage facts the file cannot hold — and they are exactly the facts
that decide whether a monitor mix reaches the right ears.

The stage sidecar is a small JSON document that records them. It is supplied to `preflight`
and `ports` with `--stage stage.json` (or `X32SCENE_STAGE`), and it is keyed exactly like the
expected-config's `outputs` section — output bank, then output number — because that is the
one handle a scene file offers that survives a re-patch. Start from
[`config/example-stage.json`](../config/example-stage.json).

## What it is, and what it is not

Every value in the sidecar is an **operator's assertion**. x32scene can check the scene
against it; it cannot verify a cable. When a documented jack carries the wrong bus, that is
evidence about the file or about the note — the tool cannot tell you which. The load test and
walking every beltpack remain the ground truth, as
[console-behavior.md](console-behavior.md) says of everything else.

## Shape

```json
{
  "outputs": {
    "main": {
      "9":  {"jack": "Box A out 1", "box": "Stagebox A", "device": "IEM TX 1",
             "wearer": "Drums", "bus": 3, "confirmed": "2026-09-04"},
      "10": {"jack": "Box A out 2", "box": "Stagebox A", "device": "IEM TX 1",
             "wearer": "Drums", "bus": 4}
    },
    "aux": {
      "1":  {"jack": "Aux out 1", "device": "Headphone amp", "wearer": "Bass", "bus": 7,
             "notes": "wired feed — confirm at soundcheck"}
    }
  }
}
```

| Key | Type | Meaning |
|---|---|---|
| `jack` | string | The connector's label as printed on the box |
| `box` | string | Which enclosure that connector is on; `(box, jack)` must be unique |
| `device` | string | What is plugged into it |
| `wearer` | string | Who hears it |
| `bus` | 1–16, optional | The mix bus this output is documented to carry — cross-checked against the scene |
| `confirmed` | string, optional | A date; an entry without one is shown as *unconfirmed* |
| `notes` | string | Anything else |

Banks are `main` (1–16), `aux` (1–6), `p16` (1–16), `aes` (1–2) and `rec` (1–2). The tool
enumerates no transmitter models, stagebox models, jack-numbering schemes or roles — every
value is free text, so the sidecar describes any rig. Keys starting with `_` are comments.

A malformed document is refused whole before anything is checked: an unknown key, an unknown
bank, an output number outside its bank, `"9"` beside `"09"`, a `bus` outside 1–16, a
non-string label, or two entries claiming the same jack on the same box.

## What preflight checks

For every documented output, all `FAIL`:

- the scene has that output line;
- it carries something (its source is not `OFF`) — a jack written down as feeding someone's
  ears that carries nothing is the silently-dead-mix case the sidecar exists to catch;
- when the entry names a `bus`, the scene's output carries that bus;
- when the expected-config's `outputs` section also pins that output, the two documents
  agree — two hands on one fact drift, and a disagreement is reported rather than one side
  silently winning.

The `checked:` line at the end of a report counts the sidecar's entries as `stage(N)`, so a
run without one never claims to have checked it.

## What ports shows

`x32scene ports --stage stage.json` prints, under each documented output, the jack (and
box), the device and wearer, and either `confirmed <date>` or `unconfirmed` — so the note
that still needs a soundcheck is visible before doors. `--bank all` covers every bank, and
`--config rig.json` labels main outputs physical or virtual from the config's
`monitor.physical_outputs`, since the console model is not in the file either.

## Where the real one lives

The example ships with neutral labels. A rig's actual sidecar names people and equipment, so
it belongs next to that rig's preflight config, outside this repository, and is pointed at
with `X32SCENE_STAGE`.
