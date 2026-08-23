"""Byte-faithful X32 / M32 scene-file toolkit."""

from importlib.metadata import PackageNotFoundError, version

from .model import Line, Scene, tokenize
from .services import (  # noqa: F401
    audit, channelfx, diff, fx, groups, iem, presets, routing, scopes,
    transforms,
)

try:
    __version__ = version("x32scene")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0.dev0"

__all__ = ["Line", "Scene", "tokenize", "__version__"]
