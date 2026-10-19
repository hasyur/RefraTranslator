from __future__ import annotations

from dataclasses import dataclass, field
import time
from threading import Event, Lock, RLock, Thread, current_thread
from types import TracebackType
from typing import Any

import numpy as np

from game_screen_translator.capture_region import (
    FULL_SCREEN_REGION,
    RegionRatio,
    region_to_pixels,
    validate_region_ratio,
)


class CaptureDependencyError(RuntimeError):
    """Raised when DXcam is unavailable or cannot initialize capture."""


_WINRT_FIRST_FRAME_WAIT_SECONDS = 0.5
_WINRT_FRAME_POLL_SECONDS = 0.005


@dataclass(slots=True)
class DxcamCapture:
    monitor_index: int = 0
    region_ratio: RegionRatio = FULL_SCREEN_REGION
    target_fps: int = 15
    backend: str = "dxgi"
    max_buffer_len: int = 4
    continuous: bool = True
    region: tuple[int, int, int, int] | None = field(init=False, default=None)
    output_size: tuple[int, int] | None = field(init=False, default=None)
    active_backend: str | None = field(init=False, default=None)
    geometry_generation: int = field(init=False, default=0)
    _camera: Any | None = field(init=False, default=None, repr=False)
    _started: bool = field(init=False, default=False, repr=False)
    _lifecycle_lock: Any = field(init=False, default_factory=RLock, repr=False)
    _frame_lock: Any = field(init=False, default_factory=Lock, repr=False)
    _reader_stop: Event = field(init=False, default_factory=Event, repr=False)
    _reader_thread: Thread | None = field(init=False, default=None, repr=False)
    _latest_generation: int = field(init=False, default=0, repr=False)
    _delivered_generation: int = field(init=False, default=0, repr=False)
    _reader_error: Exception | None = field(init=False, default=None, repr=False)
    _geometry_pending: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        self.region_ratio = validate_region_ratio(self.region_ratio)
        if self.monitor_index < 0:
            raise ValueError("monitor_index 不能为负数")
        if self.target_fps < 1:
            raise ValueError("target_fps 必须大于 0")

    def __enter__(self) -> DxcamCapture:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def start(self) -> None:
        with self._lifecycle_lock:
            self._start_unlocked()

    def _start_unlocked(self) -> None:
        if self._camera is not None:
            return
        if (
            not self.continuous
            and self.active_backend == "winrt"
            and self.output_size is not None
        ):
            return
        try:
            import dxcam
        except ImportError as exc:
            raise CaptureDependencyError(
                "尚未安装采集依赖。请运行：.\\bootstrap.ps1 -WithGui"
            ) from exc
        errors: list[str] = []
        backends = (self.backend, "winrt") if self.backend == "dxgi" else (self.backend,)
        for backend in backends:
            try:
                camera = dxcam.create(
                    output_idx=self.monitor_index,
                    region=None,
                    output_color="RGB",
                    max_buffer_len=self.max_buffer_len,
                    backend=backend,
                )
                self._camera = camera
                self.output_size = (int(camera.width), int(camera.height))
                self.region = self._resolve_region(*self.output_size)
                self.active_backend = backend
                if self.continuous:
                    self._activate_unlocked(camera, start_reader=True)
                elif backend == "winrt":
                    camera.release()
                    self._camera = None
                return
            except Exception as exc:
                errors.append(f"{backend}: {exc}")
                self.close()
        raise CaptureDependencyError(
            f"无法启动 DXcam（monitor={self.monitor_index}, region_ratio={self.region_ratio}）："
            + "；".join(errors)
            + "。如果游戏使用独占全屏，请切换为无边框窗口。"
        )

    def capture_once(self) -> np.ndarray | None:
        """Capture one frame without maintaining a background stream.

        Continuous capture keeps its established reader/latest-frame behavior.
        In on-demand mode the DXcam object is initialized by ``start()``, but
        ``grab`` performs the frame capture directly without starting a stream.
        """
        if self.continuous:
            return self.latest_frame()
        with self._lifecycle_lock:
            self._start_unlocked()
            backend = self.active_backend
            if backend is None:
                raise CaptureDependencyError("采集器尚未选择后端")
            release_after_capture = backend == "winrt"
            camera = self._camera
            frame = None
            capture_error: Exception | None = None
            try:
                if release_after_capture:
                    if camera is not None:
                        raise CaptureDependencyError(
                            "待机中的 WinRT 采集会话未释放"
                        )
                    camera = self._create_camera(backend)
                    self._camera = camera
                if camera is None:
                    raise CaptureDependencyError("采集器尚未初始化")
                self._ensure_current_geometry(camera)
                if release_after_capture:
                    frame = self._grab_winrt_frame(camera, self.region)
                else:
                    frame = camera.grab(
                        region=self.region,
                        copy=True,
                        new_frame_only=False,
                    )
            except Exception as exc:
                capture_error = exc
            finally:
                if release_after_capture and camera is not None:
                    try:
                        camera.release()
                    except Exception as exc:
                        if capture_error is None:
                            capture_error = exc
                    else:
                        if self._camera is camera:
                            self._camera = None
            if capture_error is not None:
                raise CaptureDependencyError(
                    f"单帧屏幕采集或资源释放失败：{capture_error}"
                ) from capture_error
            if frame is None:
                return None
            return np.asarray(frame)

    @staticmethod
    def _grab_winrt_frame(camera: Any, region: tuple[int, int, int, int]) -> Any:
        """Wait briefly for a new WinRT frame before releasing its session.

        DXcam's WinRT one-shot grab waits for only a few milliseconds for its
        first frame. A fresh capture session can need longer to deliver that
        frame, so retry until a bounded deadline rather than releasing an
        empty session immediately.
        """
        deadline = time.monotonic() + _WINRT_FIRST_FRAME_WAIT_SECONDS
        while True:
            frame = camera.grab(
                region=region,
                copy=True,
                new_frame_only=True,
            )
            if frame is not None:
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(_WINRT_FRAME_POLL_SECONDS, remaining))

    def _create_camera(self, backend: str) -> Any:
        import dxcam

        return dxcam.create(
            output_idx=self.monitor_index,
            region=None,
            output_color="RGB",
            max_buffer_len=self.max_buffer_len,
            backend=backend,
        )

    def _activate_unlocked(self, camera: Any, *, start_reader: bool) -> None:
        if self._started:
            return
        try:
            camera.start(
                region=self.region,
                target_fps=self.target_fps,
                video_mode=True,
            )
        except Exception as exc:
            raise CaptureDependencyError(f"无法启动 DXcam：{exc}") from exc
        self._started = True
        if start_reader:
            self._start_reader(camera)

    def latest_frame(self) -> np.ndarray | None:
        with self._lifecycle_lock:
            if not self._started or self._camera is None:
                raise CaptureDependencyError("采集器尚未启动")
            camera = self._camera
            self._ensure_current_geometry(camera)
            camera = self._camera
            if camera is None or not self._started:
                raise CaptureDependencyError("采集器尚未启动")
            with self._frame_lock:
                error = self._reader_error
                if error is not None:
                    raise CaptureDependencyError(
                        f"屏幕采集线程已停止：{error}"
                    ) from error
                if self._delivered_generation == self._latest_generation:
                    return None
                self._delivered_generation = self._latest_generation
            frame = camera.grab(copy=True)
            if frame is None:
                return None
            return np.asarray(frame)

    def _start_reader(self, camera: Any) -> None:
        self._reader_stop.clear()
        with self._frame_lock:
            self._latest_generation = 0
            self._delivered_generation = 0
            self._reader_error = None
            self._geometry_pending = False
        reader = Thread(
            target=self._read_frames,
            args=(camera,),
            name="refra-capture-reader",
            daemon=True,
        )
        self._reader_thread = reader
        reader.start()

    def _read_frames(self, camera: Any) -> None:
        try:
            while not self._reader_stop.is_set():
                frame = camera.get_latest_frame(copy=False)
                if self._reader_stop.is_set():
                    return
                if frame is None:
                    self._observe_camera_geometry(camera)
                    if not getattr(camera, "is_capturing", True):
                        with self._frame_lock:
                            self._reader_error = RuntimeError(
                                "DXCam 后台采集已意外停止"
                            )
                        return
                    self._reader_stop.wait(0.01)
                    continue
                self._observe_camera_geometry(camera)
                with self._frame_lock:
                    self._latest_generation += 1
        except Exception as exc:
            if self._reader_stop.is_set():
                return
            with self._frame_lock:
                self._reader_error = exc

    def close(self) -> None:
        with self._lifecycle_lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        camera = self._camera
        self._camera = None
        reader = self._reader_thread
        self._reader_thread = None
        was_started = self._started
        self._started = False
        self._reader_stop.set()
        if camera is None:
            with self._frame_lock:
                self._latest_generation = 0
                self._delivered_generation = 0
                self._reader_error = None
                self._geometry_pending = False
            return
        try:
            if was_started:
                camera.stop()
        finally:
            if (
                reader is not None
                and reader is not current_thread()
                and reader.is_alive()
            ):
                reader.join(timeout=1)
            camera.release()
            with self._frame_lock:
                self._latest_generation = 0
                self._delivered_generation = 0
                self._reader_error = None
                self._geometry_pending = False

    def _ensure_current_geometry(self, camera: Any) -> None:
        current_size = self._camera_output_size(camera)
        if current_size is None:
            return
        expected_region = self._resolve_region(*current_size)
        # DXcam's one-shot ``grab(region=...)`` selects pixels for that call
        # without changing the camera object's configured region. Only the
        # continuous stream path can use camera.region as a geometry signal.
        camera_region = self._camera_region(camera) if self.continuous else None
        region_changed = (
            self.region != expected_region
            or (camera_region is not None and camera_region != expected_region)
        )
        size_changed = current_size != self.output_size
        with self._frame_lock:
            geometry_pending = self._geometry_pending
        if not (size_changed or region_changed or geometry_pending):
            return
        self._mark_geometry_changed()
        self._rebuild_camera_region(camera, current_size)

    def _observe_camera_geometry(self, camera: Any) -> None:
        current_size = self._camera_output_size(camera)
        if current_size is None:
            return
        expected_region = self._resolve_region(*current_size)
        camera_region = self._camera_region(camera)
        changed = current_size != self.output_size or self.region != expected_region
        if camera_region is not None:
            changed = changed or camera_region != expected_region
        if changed:
            self._mark_geometry_changed()

    def _mark_geometry_changed(self) -> None:
        with self._frame_lock:
            if self._geometry_pending:
                return
            self._geometry_pending = True
            self.geometry_generation += 1

    def _rebuild_camera_region(
        self,
        camera: Any,
        output_size: tuple[int, int],
    ) -> None:
        region = self._resolve_region(*output_size)
        if not self._started:
            self.output_size = output_size
            self.region = region
            self._camera = camera
            with self._frame_lock:
                self._latest_generation = 0
                self._delivered_generation = 0
                self._reader_error = None
                self._geometry_pending = False
            return
        reader = self._reader_thread
        self._reader_thread = None
        self._started = False
        self._reader_stop.set()
        stop_error: Exception | None = None
        try:
            camera.stop()
        except Exception as exc:
            stop_error = exc
        finally:
            if (
                reader is not None
                and reader is not current_thread()
                and reader.is_alive()
            ):
                reader.join(timeout=1)
        if reader is not None and reader.is_alive():
            stop_error = stop_error or RuntimeError(
                "屏幕采集线程未能在重建前停止"
            )
        if stop_error is not None:
            try:
                camera.release()
            finally:
                self._camera = None
                with self._frame_lock:
                    self._latest_generation = 0
                    self._delivered_generation = 0
                    self._reader_error = None
                    self._geometry_pending = False
            raise CaptureDependencyError(
                f"无法重建屏幕采集区域：{stop_error}"
            ) from stop_error

        try:
            camera.start(
                region=region,
                target_fps=self.target_fps,
                video_mode=True,
            )
        except Exception as exc:
            try:
                camera.release()
            finally:
                self._camera = None
                with self._frame_lock:
                    self._latest_generation = 0
                    self._delivered_generation = 0
                    self._reader_error = None
                    self._geometry_pending = False
            raise CaptureDependencyError(
                f"无法重建屏幕采集区域 {region}：{exc}"
            ) from exc

        self.output_size = output_size
        self.region = region
        self._camera = camera
        self._started = True
        if self.continuous:
            self._start_reader(camera)

    @staticmethod
    def _camera_output_size(camera: Any) -> tuple[int, int] | None:
        try:
            width = int(camera.width)
            height = int(camera.height)
        except (AttributeError, TypeError, ValueError):
            return None
        if width < 1 or height < 1:
            return None
        return width, height

    @staticmethod
    def _camera_region(camera: Any) -> tuple[int, int, int, int] | None:
        value = getattr(camera, "region", None)
        if value is None:
            return None
        try:
            region = tuple(int(item) for item in value)
        except (TypeError, ValueError):
            return None
        if len(region) != 4:
            return None
        return region  # type: ignore[return-value]

    def _resolve_region(self, output_width: int, output_height: int) -> tuple[int, int, int, int]:
        return region_to_pixels(self.region_ratio, (output_width, output_height))
