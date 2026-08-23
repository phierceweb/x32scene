# x32scene documentation

| Doc | What it covers |
|---|---|
| [capabilities.md](capabilities.md) | Everything x32scene does, one page, by job: read, compare, edit, carry between scenes, snippets, plans, shows, checks, the live desk, and what it deliberately does not do |
| [cli.md](cli.md) | Every command, flag and environment variable, grouped by job |
| [format.md](format.md) | Every file kind the console reads (`.scn` `.snp` `.chn` `.efx` `.rou` `.shw`) — line grammar, headers, the head-amp trap, every strip line field-by-field, the enumerations, the preset scope model, and what is verified vs inferred |
| [console-behavior.md](console-behavior.md) | What the desk actually does when it loads your file — name-from-filename, cosmetic re-normalization, the parse-abort failure mode, scoped recall, stereo-pair reconciliation, and the load-test loop |
| [routing.md](routing.md) | The two-layer routing model — `OUT` vs `UOUT`, why the user matrices exist, resolving a channel to its jack, the record map, and the troubleshooting order |
| [stage-sidecar.md](stage-sidecar.md) | The stage sidecar — recording which jack, box, device and person each output feeds, what `preflight --stage` checks against it, and the limit: an operator's assertion, never a verified cable |

Every doc in this tree has a row here. Add one in the same change that adds a doc.
