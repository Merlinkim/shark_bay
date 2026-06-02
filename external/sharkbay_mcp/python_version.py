"""Python runtime compatibility checks for the standalone SharkBay MCP."""

from __future__ import annotations

import sys
from collections.abc import Sequence

MIN_PYTHON = (3, 10)
RECOMMENDED_PYTHON = "3.12"


def version_string(version_info: Sequence[int] | None = None) -> str:
    """Return a human-readable Python version string from a sys.version_info-like value."""
    version = version_info or sys.version_info
    return ".".join(str(part) for part in version[:3])


def build_version_error(version_info: Sequence[int] | None = None) -> str:
    """Build the startup error shown when Python is too old."""
    return (
        "ERROR:\n"
        "Python 3.10+ is required.\n\n"
        "Detected:\n"
        f"Python {version_string(version_info)}\n\n"
        "Recommended:\n"
        f"Python {RECOMMENDED_PYTHON}"
    )


def enforce_supported_python(version_info: Sequence[int] | None = None) -> None:
    """Exit gracefully when the current interpreter is older than Python 3.10."""
    version = version_info or sys.version_info
    if tuple(version[:2]) < MIN_PYTHON:
        print(build_version_error(version), file=sys.stderr)
        raise SystemExit(1)
