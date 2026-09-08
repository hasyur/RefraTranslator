"""Compatibility entry point for the native QML workbench."""

from __future__ import annotations

from pathlib import Path


def run_launcher(
    config_path: Path,
    *,
    duration_seconds: float | None = None,
) -> int:
    """Run the production QML workbench through the historical import path."""

    from .qml_workbench import run

    return run(config_path, duration_seconds=duration_seconds)


__all__ = ("run_launcher",)
