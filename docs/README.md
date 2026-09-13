# x32scene documentation

| Doc | What it covers |
|---|---|
| [capabilities.md](capabilities.md) | Everything x32scene does, one page, by job: read, compare, edit, carry between scenes, snippets, plans, shows, checks, the live desk, and what it deliberately does not do |
| [cli.md](cli.md) | Every command, flag and environment variable, grouped by job |
| [python-api.md](python-api.md) | Driving the library from a script — the layers, `Scene` and `Line`, what the services own, and what the library deliberately leaves to the caller |
| [format.md](format.md) | Every file kind the console reads (`.scn` `.snp` `.chn` `.efx` `.rou` `.shw`) — line grammar, headers, the head-amp trap, every strip line field-by-field, the enumerations, the preset scope model, and what is verified vs inferred |
| [console-behavior.md](console-behavior.md) | What the desk actually does when it loads your file — name-from-filename, cosmetic re-normalization, the parse-abort failure mode, scoped recall, stereo-pair reconciliation, and the load-test loop |
| [routing.md](routing.md) | The two-layer routing model — `OUT` vs `UOUT`, why the user matrices exist, resolving a channel to its jack, the record map, and the troubleshooting order |
| [band-plan.md](band-plan.md) | The JSON plan `band-setup` applies — every section, the stage order, and the rules that decide whether a plan is accepted |
| [preflight-config.md](preflight-config.md) | The JSON expected-config `preflight` checks a scene against — every section, what each catches, and why an unknown key is a failure |
| [stage-sidecar.md](stage-sidecar.md) | The stage sidecar — recording which jack, box, device and person each output feeds, what `preflight --stage` checks against it, and the limit: an operator's assertion, never a verified cable |

The three JSON documents: a **[plan](band-plan.md)** writes a scene; a
**[preflight config](preflight-config.md)** and a **[stage sidecar](stage-sidecar.md)**
check one.

Every doc in this tree has a row here. Add one in the same change that adds a doc —
`tests/test_docs.py` fails the build otherwise.
