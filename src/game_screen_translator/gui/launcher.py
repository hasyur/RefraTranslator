"""Compatibility entry point for the native QML workbench."""

from __future__ import annotations

from pathlib import Path


def run_launcher(
    config_path: Path,
    *,
    duration_seconds: float | None = None,
    startup: bool = False,
) -> int:
    """Run the production QML workbench through the historical import path."""

    from .qml_workbench import run

    arguments = {"duration_seconds": duration_seconds}
    if startup:
        arguments["startup"] = True
    return run(config_path, **arguments)


__all__ = ("run_launcher",)
