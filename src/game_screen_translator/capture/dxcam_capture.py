from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock, Thread, current_thread
from types import TracebackType
from typing import Any

import numpy as np


class CaptureDependencyError(RuntimeError):
    """Raised when DXcam is unavailable or cannot initialize capture."""


@dataclass(slots=True)
class DxcamCapture:
    monitor_index: int = 0
    region_spec: tuple[int, int, int, int] = (0, 0, 0, 0)
    target_fps: int = 15
    backend: str = "dxgi"
    max_buffer_len: int = 4
    region: tuple[int, int, int, int] | None = field(init=False, default=None)
    output_size: tuple[int, int] | None = field(init=False, default=None)
    active_backend: str | None = field(init=False, default=None)
    _camera: Any | None = field(init=False, default=None, repr=False)
    _started: bool = field(init=False, default=False, repr=False)
    _frame_lock: Any = field(init=False, default_factory=Lock, repr=False)
    _reader_stop: Event = field(init=False, default_factory=Event, repr=False)
    _reader_thread: Thread | None = field(init=False, default=None, repr=False)
    _latest_generation: int = field(init=False, default=0, repr=False)
    _delivered_generation: int = field(init=False, default=0, repr=False)
    _reader_error: Exception | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
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
        if self._started:
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
                camera.start(
                    region=self.region,
                    target_fps=self.target_fps,
                    video_mode=True,
                )
                self._started = True
                self.active_backend = backend
                self._start_reader(camera)
                return
            except Exception as exc:
                errors.append(f"{backend}: {exc}")
                self.close()
        raise CaptureDependencyError(
            f"无法启动 DXcam（monitor={self.monitor_index}, region={self.region_spec}）："
            + "；".join(errors)
            + "。如果游戏使用独占全屏，请切换为无边框窗口。"
        )

    def latest_frame(self) -> np.ndarray | None:
        if not self._started or self._camera is None:
            raise CaptureDependencyError("采集器尚未启动")
        with self._frame_lock:
            error = self._reader_error
            if error is not None:
                raise CaptureDependencyError(f"屏幕采集线程已停止：{error}") from error
            if self._delivered_generation == self._latest_generation:
                return None
            self._delivered_generation = self._latest_generation
        frame = self._camera.grab(copy=True)
        if frame is None:
            return None
        return np.asarray(frame)

    def _start_reader(self, camera: Any) -> None:
        self._reader_stop.clear()
        with self._frame_lock:
            self._latest_generation = 0
            self._delivered_generation = 0
            self._reader_error = None
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
                    if not getattr(camera, "is_capturing", True):
                        with self._frame_lock:
                            self._reader_error = RuntimeError(
                                "DXCam 后台采集已意外停止"
                            )
                        return
                    self._reader_stop.wait(0.01)
                    continue
                with self._frame_lock:
                    self._latest_generation += 1
        except Exception as exc:
            if self._reader_stop.is_set():
                return
            with self._frame_lock:
                self._reader_error = exc

    def close(self) -> None:
        camera = self._camera
        self._camera = None
        reader = self._reader_thread
        self._reader_thread = None
        was_started = self._started
        self._started = False
        self._reader_stop.set()
        if camera is None:
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

    def _resolve_region(self, output_width: int, output_height: int) -> tuple[int, int, int, int]:
        left, top, width, height = self.region_spec
        right = output_width if width == 0 else left + width
        bottom = output_height if height == 0 else top + height
        if not (0 <= left < right <= output_width and 0 <= top < bottom <= output_height):
            raise ValueError(
                f"捕获区域 {self.region_spec} 超出显示器 {output_width}x{output_height}"
            )
        return left, top, right, bottom
