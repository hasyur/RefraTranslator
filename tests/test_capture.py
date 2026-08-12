import sys
from types import SimpleNamespace

import numpy as np
import pytest

from game_screen_translator.capture.dxcam_capture import DxcamCapture


def test_capture_region_zero_size_extends_to_output_edge() -> None:
    capture = DxcamCapture(region_spec=(100, 200, 0, 0))

    assert capture._resolve_region(1920, 1080) == (100, 200, 1920, 1080)


def test_capture_region_uses_width_and_height() -> None:
    capture = DxcamCapture(region_spec=(100, 200, 800, 400))

    assert capture._resolve_region(1920, 1080) == (100, 200, 900, 600)


def test_capture_region_rejects_out_of_bounds() -> None:
    capture = DxcamCapture(region_spec=(1800, 100, 200, 200))

    with pytest.raises(ValueError, match="超出显示器"):
        capture._resolve_region(1920, 1080)


def test_dxgi_failure_falls_back_to_winrt(monkeypatch) -> None:
    backends: list[str] = []

    class FakeCamera:
        width = 1920
        height = 1080

        def __init__(self) -> None:
            self.started_region = None
            self.released = False

        def start(self, *, region, target_fps, video_mode) -> None:
            self.started_region = region

        def get_latest_frame(self, *, copy=True):
            return np.zeros((100, 200, 3), dtype=np.uint8)

        def stop(self) -> None:
            pass

        def release(self) -> None:
            self.released = True

    camera = FakeCamera()

    def create(**kwargs):
        backends.append(kwargs["backend"])
        if kwargs["backend"] == "dxgi":
            raise PermissionError("denied")
        return camera

    monkeypatch.setitem(sys.modules, "dxcam", SimpleNamespace(create=create))
    capture = DxcamCapture(region_spec=(10, 20, 200, 100), backend="dxgi")

    capture.start()

    assert backends == ["dxgi", "winrt"]
    assert capture.active_backend == "winrt"
    assert capture.region == (10, 20, 210, 120)
    assert capture.latest_frame().shape == (100, 200, 3)
    capture.close()
    assert camera.released
