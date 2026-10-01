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
- A crafted file that gets `load` to write anything but the parameters a scene or snippet
  carries, or a group the file's own header leaves out of its recall.

The live layer reads the desk: it queries its state, memory index and meters, and `watch`
subscribes to the desk's change reports with `/xremote`. One command, `load`, writes: it puts
the parameter lines of a scene or snippet you name onto the desk, over the local network,
and refuses a file that carries anything else, such as the desk's actions or preferences
(`/-action`, `/-prefs`). Nothing else sets a parameter.
The tool sends nothing off the local network and stores no credentials. Scene files may
contain venue and personnel names — treat them as private data when attaching one to a
report, and prefer an anonymized reproduction.
