"""Every file a command will write, named from its parsed arguments and checked at dispatch,
before any runner reads an input or writes a file."""

from __future__ import annotations

from ._cli_files import refuse_not_directory, refuse_unwritable

# the file a command writes beside -o; show-build's --snippet is an input
_SECOND_OUTPUT = {"band-setup": "snippet", "watch": "snippet", "preflight": "regenerate"}


def file_outputs(args) -> list[tuple[str, str]]:
    """(path, flag) for each file ``args`` will write; the directory outputs of
    ``extract-preset --all`` and ``show-build`` are not files."""
    outs = []
    if getattr(args, "out", None) is not None and not (args.cmd == "extract-preset" and args.all):
        outs.append((args.out, "-o"))
    dest = _SECOND_OUTPUT.get(args.cmd)
    if dest is not None and getattr(args, dest) is not None:
        outs.append((getattr(args, dest), f"--{dest}"))
    return outs


def refuse_unwritable_outputs(args) -> None:
    """Refuse any output that is a directory or sits in no writable directory, and a
    directory output that is not one, before any input is read."""
    for path, flag in file_outputs(args):
        refuse_unwritable(path, flag)
    if args.cmd == "show-build":
        refuse_not_directory(args.dir, "-o")
    elif args.cmd == "extract-preset" and args.all:
        refuse_not_directory(args.out, "-o")
