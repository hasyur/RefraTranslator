from pathlib import Path

from game_screen_translator import first_run
from game_screen_translator.runtime_resources import OcrResource, OcrResourceInventory


def test_ready_first_run_cleans_successful_download_cache_without_opening_a_window(
    tmp_path: Path, monkeypatch,
) -> None:
    config = tmp_path / "installed-app" / "config.toml"
    inventory = OcrResourceInventory((OcrResource("ready resources", 0, True),))
    monkeypatch.setattr(first_run, "inspect_ocr_resources", lambda _config: inventory)
    cleaned = []
    monkeypatch.setattr(first_run, "cleanup_prepared_downloads", lambda path: cleaned.append(path))
    monkeypatch.setattr(first_run, "OcrResourcesWindow", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ready resources must not open preparation window")))
    assert first_run.main(["--config", str(config)]) == 0
    assert cleaned == [config]
