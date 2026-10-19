"""Small, deterministic mouse-motion gate for on-demand live capture."""

from __future__ import annotations

import math
from dataclasses import dataclass


Point = tuple[float, float]

MOUSE_DWELL_DISTANCE_PX = 30.0
MOUSE_DWELL_JITTER_PX = 2.0
MOUSE_DWELL_POLL_INTERVAL_MS = 20


@dataclass(frozen=True, slots=True)
class MouseDwellRequest:
    request_id: int
    position: Point
    motion_revision: int


class MouseDwellGate:
    """Require a stable position, and 30px movement after the first scan."""

    def __init__(self, dwell_ms: int) -> None:
        if type(dwell_ms) is not int or not 0 <= dwell_ms <= 10_000:
            raise ValueError("dwell_ms 必须是 0 到 10000 的整数")
        self.dwell_seconds = dwell_ms / 1000.0
        self._last_position: Point | None = None
        self._stable_position: Point | None = None
        self._stable_since: float | None = None
        self._last_poll_at = 0.0
        self._scan_anchor: Point | None = None
        self._motion_revision = 0
        self._request_id = 0
        self._in_flight: MouseDwellRequest | None = None

    @property
    def in_flight(self) -> bool:
        return self._in_flight is not None

    def poll(
        self,
        position: Point,
        now: float,
        *,
        ready: bool = True,
    ) -> MouseDwellRequest | None:
        point = (float(position[0]), float(position[1]))
        if not all(math.isfinite(value) for value in point):
            raise ValueError("鼠标坐标必须是有限数字")
        if self._last_position is None:
            self._last_position = point
            self._stable_position = point
            self._stable_since = now
            self._last_poll_at = now
            return None

        self._last_position = point
        self._last_poll_at = now
        assert self._stable_position is not None
        assert self._stable_since is not None
        movement = _distance(point, self._stable_position)
        if movement > 0.0 and movement >= MOUSE_DWELL_JITTER_PX:
            self._stable_position = point
            self._stable_since = now
            self._motion_revision += 1

        if not ready or self._in_flight is not None:
            return None
        if now - self._stable_since < self.dwell_seconds:
            return None

        initial_scan = self._scan_anchor is None
        moved_far_enough = (
            not initial_scan
            and _distance(point, self._scan_anchor) >= MOUSE_DWELL_DISTANCE_PX
        )
        if not (initial_scan or moved_far_enough):
            return None

        self._request_id += 1
        request = MouseDwellRequest(
            self._request_id,
            point,
            self._motion_revision,
        )
        self._in_flight = request
        return request

    def request_is_current(self, request: MouseDwellRequest) -> bool:
        return (
            self._in_flight == request
            and request.motion_revision == self._motion_revision
        )

    def complete(
        self,
        request: MouseDwellRequest,
        *,
        successful: bool = True,
    ) -> bool:
        """Release the gate and anchor only a successful, current capture."""
        if self._in_flight != request:
            return False
        current = request.motion_revision == self._motion_revision
        self._in_flight = None
        if current and successful:
            self._scan_anchor = request.position
            self._stable_position = self._last_position or request.position
        elif not successful:
            # Avoid immediately retrying a failed capture on the next 20ms poll.
            self._stable_since = self._last_poll_at
        return current and successful


def _distance(left: Point, right: Point) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])
