from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from game_screen_translator.capture.dxcam_capture import (
    CaptureDependencyError,
    DxcamCapture,
)
from game_screen_translator.capture import dxcam_capture


class FakeCamera:
    width = 640
    height = 360

    def __init__(self) -> None:
        self.start_calls: list[tuple[int, int, int, int]] = []
        self.stop_calls = 0
        self.release_calls = 0
        self.is_capturing = False
        self.grab_regions: list[tuple[int, int, int, int] | None] = []

    @property
    def region(self):
        return (0, 0, self.width, self.height)

    def start(self, *, region, target_fps, video_mode) -> None:
        del target_fps, video_mode
        self.start_calls.append(region)
        self.is_capturing = True

    def grab(self, *, region=None, copy=True, new_frame_only=True):
        del copy, new_frame_only
        self.grab_regions.append(region)
        if region is None:
            raise RuntimeError("region is required")
        left, top, right, bottom = region
        return np.zeros((bottom - top, right - left, 3), dtype=np.uint8)

    def get_latest_frame(self, *, copy=True):
        del copy
        return None

    def stop(self) -> None:
        self.stop_calls += 1
        self.is_capturing = False

    def release(self) -> None:
        self.release_calls += 1


class SessionCamera(FakeCamera):
    def __init__(self, active_sessions: list[int], *, grab_script=None) -> None:
        super().__init__()
        self.active_sessions = active_sessions
        self.active_sessions[0] += 1
        self.is_released = False
        self._duplicator = SimpleNamespace(_session=object())
        self.grab_script = list(grab_script or [])
        self.grab_calls = 0

    def grab(self, *, region=None, copy=True, new_frame_only=True):
        self.grab_calls += 1
        if self.grab_script:
            item = self.grab_script.pop(0)
            if isinstance(item, Exception):
                raise item
            if item is None:
                return None
        return super().grab(
            region=region,
            copy=copy,
            new_frame_only=new_frame_only,
        )

    def release(self) -> None:
        if self.is_released:
            return
        self.is_released = True
        self.active_sessions[0] -= 1
        self._duplicator._session = None
        super().release()


def test_on_demand_start_initializes_geometry_without_stream_or_reader(monkeypatch):
    camera = FakeCamera()
    monkeypatch.setitem(
        sys.modules,
        "dxcam",
        SimpleNamespace(create=lambda **_kwargs: camera),
    )
    capture = DxcamCapture(continuous=False, target_fps=30)

    capture.start()

    assert capture.output_size == (640, 360)
    assert capture.region == (0, 0, 640, 360)
    assert capture.active_backend == "dxgi"
    assert camera.start_calls == []
    assert capture._reader_thread is None
    assert not capture._started

    capture.close()
    assert camera.stop_calls == 0
    assert camera.release_calls == 1


def test_on_demand_capture_starts_grabs_and_stops_exactly_once(monkeypatch):
    camera = FakeCamera()
    monkeypatch.setitem(
        sys.modules,
        "dxcam",
        SimpleNamespace(create=lambda **_kwargs: camera),
    )
    capture = DxcamCapture(continuous=False, region_ratio=(0.25, 0.25, 0.5, 0.5))
    capture.start()

    frame = capture.capture_once()

    assert frame is not None
    assert frame.shape == (180, 320, 3)
    assert camera.start_calls == []
    assert camera.grab_regions == [(160, 90, 480, 270)]
    assert camera.stop_calls == 0
    assert capture._reader_thread is None
    assert not capture._started

    capture.close()
    assert camera.release_calls == 1


def test_on_demand_region_override_does_not_look_like_geometry_change(monkeypatch):
    camera = FakeCamera()
    monkeypatch.setitem(
        sys.modules,
        "dxcam",
        SimpleNamespace(create=lambda **_kwargs: camera),
    )
    capture = DxcamCapture(continuous=False, region_ratio=(0.25, 0.25, 0.5, 0.5))
    capture.start()

    frames = [capture.capture_once() for _ in range(3)]

    assert all(frame is not None and frame.shape == (180, 320, 3) for frame in frames)
    assert camera.region == (0, 0, 640, 360)
    assert camera.grab_regions == [(160, 90, 480, 270)] * 3
    assert capture.region == (160, 90, 480, 270)
    assert capture.geometry_generation == 0
    capture.close()


def test_winrt_on_demand_releases_session_after_start_and_each_frame(monkeypatch):
    active_sessions = [0]
    cameras: list[SessionCamera] = []

    def create(**kwargs):
        assert kwargs["backend"] == "winrt"
        camera = SessionCamera(active_sessions)
        cameras.append(camera)
        return camera

    monkeypatch.setitem(sys.modules, "dxcam", SimpleNamespace(create=create))
    capture = DxcamCapture(
        continuous=False,
        backend="winrt",
        region_ratio=(0.25, 0.25, 0.5, 0.5),
    )

    capture.start()
    assert active_sessions == [0]
    assert cameras[-1].is_released
    assert cameras[-1]._duplicator._session is None

    for _ in range(2):
        frame = capture.capture_once()
        assert frame is not None and frame.shape == (180, 320, 3)
        assert active_sessions == [0]
        assert cameras[-1].is_released
        assert cameras[-1]._duplicator._session is None

    assert len(cameras) == 3
    capture.close()
    assert active_sessions == [0]
    assert all(camera.is_released for camera in cameras)


def test_winrt_fallback_releases_each_session_after_dxgi_creation_fails(monkeypatch):
    active_sessions = [0]
    cameras: list[SessionCamera] = []
    backends: list[str] = []

    def create(**kwargs):
        backend = kwargs["backend"]
        backends.append(backend)
        if backend == "dxgi":
            raise RuntimeError("DXGI unavailable")
        camera = SessionCamera(active_sessions)
        cameras.append(camera)
        return camera

    monkeypatch.setitem(sys.modules, "dxcam", SimpleNamespace(create=create))
    capture = DxcamCapture(continuous=False, backend="dxgi")

    capture.start()
    assert capture.active_backend == "winrt"
    assert active_sessions == [0]
    assert cameras[-1].is_released
    assert cameras[-1]._duplicator._session is None

    assert capture.capture_once() is not None
    assert backends == ["dxgi", "winrt", "winrt"]
    assert active_sessions == [0]
    assert all(camera.is_released for camera in cameras)
    assert all(camera._duplicator._session is None for camera in cameras)
    capture.close()
    assert active_sessions == [0]


@pytest.mark.parametrize("failure", ["none", "exception"])
def test_winrt_on_demand_releases_session_after_none_or_grab_exception(
    monkeypatch,
    failure,
):
    active_sessions = [0]
    cameras: list[SessionCamera] = []

    def create(**_kwargs):
        script = []
        if len(cameras) == 1:
            script = (
                [None] * 20
                if failure == "none"
                else [RuntimeError("grab failed")]
            )
        camera = SessionCamera(active_sessions, grab_script=script)
        cameras.append(camera)
        return camera

    monkeypatch.setattr(dxcam_capture, "_WINRT_FIRST_FRAME_WAIT_SECONDS", 0.01)
    monkeypatch.setitem(sys.modules, "dxcam", SimpleNamespace(create=create))
    capture = DxcamCapture(continuous=False, backend="winrt")
    capture.start()

    if failure == "none":
        assert capture.capture_once() is None
    else:
        with pytest.raises(CaptureDependencyError, match="单帧屏幕采集或资源释放失败"):
            capture.capture_once()

    assert active_sessions == [0]
    assert cameras[-1].is_released
    assert cameras[-1]._duplicator._session is None
    capture.close()
    assert active_sessions == [0]


def test_winrt_waits_briefly_for_its_first_frame_then_releases_session(monkeypatch):
    active_sessions = [0]
    cameras: list[SessionCamera] = []

    def create(**_kwargs):
        script = [None, None] if cameras else []
        camera = SessionCamera(active_sessions, grab_script=script)
        cameras.append(camera)
        return camera

    monkeypatch.setitem(sys.modules, "dxcam", SimpleNamespace(create=create))
    capture = DxcamCapture(continuous=False, backend="winrt")
    capture.start()

    frame = capture.capture_once()

    assert frame is not None
    # Two no-frame attempts plus the successful first frame.
    assert cameras[-1].grab_calls == 3
    assert cameras[-1].grab_regions == [(0, 0, 640, 360)]
    assert active_sessions == [0]
    assert cameras[-1].is_released
    assert cameras[-1]._duplicator._session is None
    capture.close()


def test_on_demand_capture_refreshes_geometry_before_the_next_frame(monkeypatch):
    camera = FakeCamera()
    monkeypatch.setitem(
        sys.modules,
        "dxcam",
        SimpleNamespace(create=lambda **_kwargs: camera),
    )
    capture = DxcamCapture(continuous=False, region_ratio=(0.1, 0.1, 0.8, 0.8))
    capture.start()
    assert capture.capture_once().shape == (288, 512, 3)

    camera.width = 800
    camera.height = 400
    frame = capture.capture_once()

    assert frame.shape == (320, 640, 3)
    assert capture.output_size == (800, 400)
    assert capture.region == (80, 40, 720, 360)
    assert capture.geometry_generation == 1
    assert camera.start_calls == []
    assert camera.grab_regions == [
        (64, 36, 576, 324),
        (80, 40, 720, 360),
    ]
    assert camera.stop_calls == 0
    capture.close()


def test_latest_frame_does_not_implicitly_start_on_demand_camera(monkeypatch):
    camera = FakeCamera()
    monkeypatch.setitem(
        sys.modules,
        "dxcam",
        SimpleNamespace(create=lambda **_kwargs: camera),
    )
    capture = DxcamCapture(continuous=False)
    capture.start()

    with pytest.raises(CaptureDependencyError, match="尚未启动"):
        capture.latest_frame()
    assert camera.start_calls == []
    capture.close()
