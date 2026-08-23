# Security Policy

## Supported versions

The latest released version receives fixes. This is a small tool; older versions are not
back-patched.

## Reporting a vulnerability

Email **oss@phierceweb.com** with a description and, where possible, steps to reproduce.
Please do not open a public issue for a security report.

Expect an acknowledgement within a week. Once a fix ships, the release notes credit the
reporter unless anonymity is requested.

## Scope notes

x32scene parses and writes console files (`.scn` `.snp` `.chn` `.efx` `.rou` `.shw` and
JSON plans) and speaks OSC over UDP to a mixing console on the local network. Relevant
classes of issue include:

- A crafted file that causes the parser or a transform to write a file differing from
  the intended edit, or to escape the round-trip guarantee.
- A malformed OSC datagram or meter blob that causes the live layer to misattribute or
  corrupt captured console state.

The live layer is read-only: it queries the desk's state, memory index and meters and
never sets a parameter. The tool sends nothing off the local network and stores no
credentials. Scene files may
contain venue and personnel names — treat them as private data when attaching one to a
report, and prefer an anonymized reproduction.
