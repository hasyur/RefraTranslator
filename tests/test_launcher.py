from pathlib import Path

import pytest

from game_screen_translator.gui import launcher as launcher_module
from game_screen_translator.gui import qml_workbench as qml_workbench_module


def test_launcher_module_is_only_a_qml_compatibility_entrypoint() -> None:
    source = Path(launcher_module.__file__).read_text(encoding="utf-8")

    assert "LauncherWindow" not in source
    assert "QMainWindow" not in source
    assert "QtWidgets" not in source
    assert launcher_module.__all__ == ("run_launcher",)


def test_production_launcher_delegates_to_the_native_qml_workbench(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, float | None]] = []
    monkeypatch.setattr(
        qml_workbench_module,
        "run",
        lambda config_path, *, duration_seconds=None: calls.append(
            (config_path, duration_seconds)
        )
        or 23,
    )

    config_path = tmp_path / "config.toml"
    assert launcher_module.run_launcher(config_path, duration_seconds=0.25) == 23
    assert calls == [(config_path, 0.25)]
