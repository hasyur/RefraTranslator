import sys
import threading
import time
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
            self.is_capturing = False
            self._frame_delivered = False
            self._stop = threading.Event()

        def start(self, *, region, target_fps, video_mode) -> None:
            self.started_region = region
            self.is_capturing = True

        def get_latest_frame(self, *, copy=True):
            if not self._frame_delivered:
                self._frame_delivered = True
                return np.zeros((100, 200, 3), dtype=np.uint8)
            self._stop.wait(timeout=2)
            return None

        def grab(self, *, copy=True):
            return np.zeros((100, 200, 3), dtype=np.uint8)

        def stop(self) -> None:
            self.is_capturing = False
            self._stop.set()

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
    deadline = time.monotonic() + 1
    frame = None
    while frame is None and time.monotonic() < deadline:
        frame = capture.latest_frame()
        time.sleep(0.005)
    assert frame is not None
    assert frame.shape == (100, 200, 3)
    capture.close()
    assert camera.released


def test_latest_frame_does_not_wait_for_blocked_dxcam_reader(monkeypatch) -> None:
    class BlockingCamera:
        width = 1920
        height = 1080

        def __init__(self) -> None:
            self.is_capturing = False
            self.reader_waiting = threading.Event()
            self.release_reader = threading.Event()

        def start(self, *, region, target_fps, video_mode) -> None:
            self.is_capturing = True

        def get_latest_frame(self, *, copy=True):
            self.reader_waiting.set()
            self.release_reader.wait(timeout=2)
            return None

        def grab(self, *, copy=True):
            raise AssertionError("没有新帧时不应读取环形缓冲区")

        def stop(self) -> None:
            self.is_capturing = False
            self.release_reader.set()

        def release(self) -> None:
            pass

    camera = BlockingCamera()
    monkeypatch.setitem(
        sys.modules,
        "dxcam",
        SimpleNamespace(create=lambda **kwargs: camera),
    )
    capture = DxcamCapture()
    capture.start()
    assert camera.reader_waiting.wait(timeout=1)

    completed = threading.Event()
    result: list[np.ndarray | None] = []

    def read_latest() -> None:
        result.append(capture.latest_frame())
        completed.set()

    caller = threading.Thread(target=read_latest, daemon=True)
    caller.start()

    assert completed.wait(timeout=1)
    assert result == [None]
    capture.close()
    caller.join(timeout=1)
