from __future__ import annotations

import ctypes
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    Q_ARG,
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPoint,
    QPointF,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QFontInfo, QFontMetricsF, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, QQmlProperty
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.capture_region import pixels_to_region_ratio
from game_screen_translator.config import load_config
from game_screen_translator.gui import qml_workbench as host_module
from game_screen_translator.gui import runtime as runtime_module
from game_screen_translator.gui import workbench_controller as controller_module
from game_screen_translator.gui.qml_workbench import QmlWorkbenchHost
from game_screen_translator.gui.theme import (
    HOTKEY_BEHAVIOR_TOGGLE,
    HOTKEY_BEHAVIOR_TOGGLE_SHOW,
    SKIN_DOHNA,
    SKIN_PRISM,
    load_gui_preferences,
)
from game_screen_translator.gui.workbench_controller import WorkbenchController
from game_screen_translator.live.latency import LiveLatencyStats
from game_screen_translator.live.snapshot import CacheHit, SnapshotEntry, new_snapshot, save_snapshot
from game_screen_translator.translation.cache import CacheStats
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    apply_profile_runtime_settings,
    create_game_profile,
    load_game_profile,
    save_profile_capture_settings,
    save_profile_runtime_settings,
)


@pytest.fixture(autouse=True)
def _capture_device_size(monkeypatch):
    # Keep capture scenarios independent of Qt's 800x800 offscreen screen.
    monkeypatch.setattr(WorkbenchController, "_selected_display_size", lambda self: (1920, 1080))


def _region_ratio(region):
    return pixels_to_region_ratio(region, (1920, 1080))


@pytest.fixture(autouse=True)
def _drain_deferred_qt_deletes() -> None:
    app = QApplication.instance()
    if app is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


class _SignalRecorder:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


class _TrayRecorder:
    def __init__(self) -> None:
        self.activated = _SignalRecorder()
        self.visible = False
        self.icon = None
        self.tooltip = ""

    def setIcon(self, icon) -> None:  # noqa: N802
        self.icon = icon

    def setToolTip(self, tooltip: str) -> None:  # noqa: N802
        self.tooltip = tooltip

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


class _ContextRecorder:
    def __init__(self) -> None:
        self.properties: list[tuple[str, QObject]] = []

    def setContextProperty(self, name: str, value: QObject) -> None:  # noqa: N802
        self.properties.append((name, value))


class _RecordingWindow(QQuickWindow):
    def __init__(self) -> None:
        super().__init__()
        self.release_count = 0

    def releaseResources(self) -> None:  # noqa: N802
        self.release_count += 1
        super().releaseResources()


class _EngineRecorder:
    def __init__(self, _parent: QObject) -> None:
        self.context = _ContextRecorder()
        self.quit = _SignalRecorder()
        self.loaded_urls = []
        self.root = _RecordingWindow()
        self.delete_count = 0

    def rootContext(self):  # noqa: N802
        return self.context

    def load(self, url) -> None:
        self.loaded_urls.append(url)

    def rootObjects(self):  # noqa: N802
        return [self.root]

    def deleteLater(self) -> None:  # noqa: N802
        self.delete_count += 1


class _ControllerStub(QObject):
    stateChanged = Signal()
    regionSelectionRequested = Signal(int)
    liveReady = Signal()
    liveFinished = Signal()
    liveFailed = Signal()
    workbenchHideRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.accepted_regions: list[tuple[int, int, int, int]] = []
        self.cancel_count = 0
        self.shutdown_count = 0
        self.stop_count = 0
        self.host_errors: list[tuple[str, str]] = []
        self.themePreference = "dark"
        self.effectiveTheme = "dark"
        self.skinPreference = SKIN_PRISM

    def acceptRegionSelection(self, *region: int) -> None:  # noqa: N802
        self.accepted_regions.append(region)

    def cancelRegionSelection(self) -> None:  # noqa: N802
        self.cancel_count += 1

    def stopLive(self) -> None:  # noqa: N802
        self.stop_count += 1

    def hideWorkbench(self) -> None:  # noqa: N802
        self.workbenchHideRequested.emit()

    def shutdown(self) -> None:
        self.shutdown_count += 1

    def reportHostError(self, title: str, message: str) -> None:  # noqa: N802
        self.host_errors.append((title, message))


class _ActivationController(_ControllerStub):
    def __init__(self, *, stop_result: bool = True, phase: str = "running") -> None:
        super().__init__()
        self.running = True
        self.runPhase = phase
        self.stop_result = stop_result

    def stopLive(self) -> bool:  # noqa: N802
        self.stop_count += 1
        if self.stop_result:
            self.runPhase = "stopping"
        return self.stop_result


class _SelectorStub(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.selected_region: tuple[int, int, int, int] | None = None
        self.opened = False

    def open(self) -> None:
        self.opened = True


class _ApplicationRecorder:
    def __init__(self) -> None:
        self.aboutToQuit = _SignalRecorder()
        self.quit_count = 0

    def quit(self) -> None:
        self.quit_count += 1

    def screens(self):
        return _application().screens()


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_workbench_uses_curve_glyphs_as_the_global_text_default() -> None:
    original = QQuickWindow.textRenderType()
    try:
        QQuickWindow.setTextRenderType(
            QQuickWindow.TextRenderType.QtTextRendering,
        )
        host_module._use_smooth_quick_rendering()
        assert (
            QQuickWindow.textRenderType()
            == QQuickWindow.TextRenderType.CurveTextRendering
        )
    finally:
        QQuickWindow.setTextRenderType(original)


def _find_quick_item(
    root: QQuickWindow | QQuickItem,
    object_name: str,
) -> QQuickItem | None:
    pending = [root.contentItem() if isinstance(root, QQuickWindow) else root]
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
    return None


def _find_quick_items(
    root: QQuickWindow | QQuickItem,
    object_name: str,
) -> list[QQuickItem]:
    pending = [root.contentItem() if isinstance(root, QQuickWindow) else root]
    matches: list[QQuickItem] = []
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            matches.append(item)
        pending.extend(item.childItems())
    return matches


def _theme_for_skin(window: QQuickWindow, skin: str) -> QObject | None:
    theme_name = "dohnaTheme" if skin == SKIN_DOHNA else "prismTheme"
    return window.findChild(QObject, theme_name)


def _active_theme(window: QQuickWindow) -> QObject | None:
    return (
        window.findChild(QObject, "prismTheme")
        or window.findChild(QObject, "dohnaTheme")
    )


def _visible_text_items(root: QObject, text: str) -> list[QQuickItem]:
    return [
        item
        for item in root.findChildren(QQuickItem)
        if item.isVisible()
        and item.inherits("QQuickText")
        and item.property("text") == text
    ]


def _setting_hint_for_target(window: QQuickWindow, target: QQuickItem) -> QObject:
    matches = [
        item
        for item in window.findChildren(QObject)
        if item.objectName().startswith("settingHint-")
        and item.property("target") is target
    ]
    assert len(matches) == 1, (target.objectName(), [item.objectName() for item in matches])
    return matches[0]


def _assert_scroll_thumb_inside_track(bar: QQuickItem) -> None:
    track = _find_quick_item(bar, "prismScrollTrack")
    thumb = _find_quick_item(bar, "prismScrollThumb")
    assert track is not None and thumb is not None
    origin = thumb.mapToItem(track, QPointF(0, 0))
    assert origin.x() >= -0.5
    assert origin.y() >= -0.5
    assert origin.x() + thumb.width() <= track.width() + 0.5
    assert origin.y() + thumb.height() <= track.height() + 0.5
    assert math.isclose(origin.x() + thumb.width() / 2, track.width() / 2, abs_tol=0.1)


def _wait_for_page_layout(
    window: QQuickWindow,
    item: QQuickItem,
    app: QApplication,
    *,
    timeout_ms: int = 2500,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    previous_geometry: tuple[float, float] | None = None
    stable_frames = 0
    while time.monotonic() < deadline:
        app.processEvents()
        settled = (
            not window.property("pageTransitioning")
            and window.property("pageContentReady")
            and item.isVisible()
        )
        geometry = (
            float(item.property("width")),
            float(item.property("height")),
        )
        if settled and min(geometry) > 0:
            if geometry == previous_geometry:
                stable_frames += 1
                if stable_frames >= 2:
                    return
            else:
                stable_frames = 0
        else:
            stable_frames = 0
        previous_geometry = geometry
        # Allow a frame between samples so a queued layout polish can run.
        QTest.qWait(20)

    raise AssertionError(
        "QML page/layout did not settle within "
        f"{timeout_ms} ms: transitioning={window.property('pageTransitioning')}, "
        f"content_ready={window.property('pageContentReady')}, "
        f"visible={item.isVisible()}, geometry={geometry}"
    )


def _navigation_motion_rect(
    motion: QQuickItem,
    *,
    target: bool = False,
) -> tuple[float, float, float, float]:
    prefix = "target" if target else ""
    names = ("X", "Y", "Width", "Height") if target else ("x", "y", "width", "height")
    return tuple(float(motion.property(prefix + name)) for name in names)  # type: ignore[return-value]


def _max_geometry_delta(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    return max(abs(left - right) for left, right in zip(first, second, strict=True))


def _wait_for_navigation_motion_progress(
    window: QQuickWindow,
    motion: QQuickItem,
    app: QApplication,
    *,
    expected_presentation: float,
    start: tuple[float, float, float, float],
    toward_latest_target: bool = False,
    timeout_ms: int = 2500,
) -> tuple[float, float, float, float]:
    deadline = time.monotonic() + timeout_ms / 1000
    current = _navigation_motion_rect(motion)
    target = _navigation_motion_rect(motion, target=True)
    while time.monotonic() < deadline:
        app.processEvents()
        current = _navigation_motion_rect(motion)
        target = _navigation_motion_rect(motion, target=True)
        target_presentation = float(motion.property("targetPresentation"))
        running = bool(motion.property("positionAnimationRunning"))
        moved = _max_geometry_delta(start, current) > 1.0
        away_from_target = _max_geometry_delta(current, target) > 1.0
        toward_target = (
            _max_geometry_delta(start, target)
            - _max_geometry_delta(current, target)
            > 1.0
        )
        if (
            math.isclose(target_presentation, expected_presentation, abs_tol=0.01)
            and running
            and moved
            and away_from_target
            and (not toward_latest_target or toward_target)
        ):
            return current
        QTest.qWait(20)

    raise AssertionError(
        "Prism navigation motion did not show an intermediate position: "
        f"presentation={motion.property('presentation')}, "
        f"target_presentation={motion.property('targetPresentation')}, "
        f"current={current}, target={target}, "
        f"position_running={motion.property('positionAnimationRunning')}, "
        f"window_transitioning={window.property('pageTransitioning')}"
    )


def _wait_for_navigation_subtitle_fade(
    window: QQuickWindow,
    motion: QQuickItem,
    subtitle: QQuickItem,
    app: QApplication,
    *,
    timeout_ms: int = 1500,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        presentation = float(motion.property("presentation"))
        opacity = float(subtitle.property("opacity"))
        if (
            0.2 <= presentation <= 0.8
            and subtitle.isVisible()
            and bool(subtitle.property("text"))
            and opacity <= 0.02
        ):
            return
        QTest.qWait(10)

    raise AssertionError(
        "Prism navigation subtitle did not fade while its visible label crossed "
        f"the middle presentation range: presentation={motion.property('presentation')}, "
        f"opacity={subtitle.property('opacity')}, text={subtitle.property('text')!r}, "
        f"visible={subtitle.isVisible()}, window_visible={window.isVisible()}"
    )


def _wait_for_navigation_motion_settled(
    window: QQuickWindow,
    motion: QQuickItem,
    app: QApplication,
    *,
    expected_presentation: float,
    motion_enabled: bool,
    timeout_ms: int = 3000,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    previous: tuple[float, float, float, float, float, float] | None = None
    stable_frames = 0
    current = _navigation_motion_rect(motion)
    target = _navigation_motion_rect(motion, target=True)
    while time.monotonic() < deadline:
        app.processEvents()
        current = _navigation_motion_rect(motion)
        target = _navigation_motion_rect(motion, target=True)
        presentation = float(motion.property("presentation"))
        target_presentation = float(motion.property("targetPresentation"))
        tilt = float(motion.property("tilt"))
        target_tilt = float(motion.property("targetTilt"))
        state = (*current, presentation, tilt)
        settled = (
            bool(motion.property("positionMotionEnabled")) is motion_enabled
            and math.isclose(target_presentation, expected_presentation, abs_tol=0.01)
            and math.isclose(presentation, expected_presentation, abs_tol=0.02)
            and math.isclose(tilt, target_tilt, abs_tol=0.1)
            and _max_geometry_delta(current, target) <= 0.75
            and not bool(motion.property("positionAnimationRunning"))
            and not bool(motion.property("presentationAnimationRunning"))
            and window.property("navigationResizeActive") is False
            and window.property("pageTransitioning") is False
            and window.property("pageContentReady") is True
        )
        if settled and previous is not None and _max_geometry_delta(current, previous[:4]) <= 0.1:
            stable_frames += 1
            if stable_frames >= 3:
                return
        else:
            stable_frames = 0
        previous = state
        QTest.qWait(20)

    raise AssertionError(
        "Prism navigation motion did not converge: "
        f"current={current}, target={target}, "
        f"presentation={motion.property('presentation')}, "
        f"target_presentation={motion.property('targetPresentation')}, "
        f"enabled={motion.property('positionMotionEnabled')}, "
        f"position_running={motion.property('positionAnimationRunning')}, "
        f"presentation_running={motion.property('presentationAnimationRunning')}, "
        f"resize_active={window.property('navigationResizeActive')}, "
        f"page_transitioning={window.property('pageTransitioning')}"
    )


def _wait_for_action_motion_progress(
    window: QQuickWindow,
    motion: QQuickItem,
    app: QApplication,
    *,
    start: tuple[float, float, float, float],
    toward_latest_target: bool = False,
    timeout_ms: int = 2500,
) -> tuple[float, float, float, float]:
    deadline = time.monotonic() + timeout_ms / 1000
    current = _navigation_motion_rect(motion)
    target = _navigation_motion_rect(motion, target=True)
    while time.monotonic() < deadline:
        app.processEvents()
        current = _navigation_motion_rect(motion)
        target = _navigation_motion_rect(motion, target=True)
        moved = _max_geometry_delta(start, current) > 1.0
        away_from_target = _max_geometry_delta(current, target) > 1.0
        toward_target = (
            _max_geometry_delta(start, target)
            - _max_geometry_delta(current, target)
            > 1.0
        )
        if (
            bool(motion.property("positionMotionEnabled"))
            and moved
            and away_from_target
            and (not toward_latest_target or toward_target)
        ):
            return current
        QTest.qWait(20)

    raise AssertionError(
        "Prism CTA motion did not show an intermediate position: "
        f"current={current}, target={target}, "
        f"enabled={motion.property('positionMotionEnabled')}, "
        f"page_transitioning={window.property('pageTransitioning')}"
    )


def _wait_for_action_motion_settled(
    window: QQuickWindow,
    motion: QQuickItem,
    app: QApplication,
    *,
    motion_enabled: bool,
    timeout_ms: int = 3000,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    previous: tuple[float, float, float, float] | None = None
    stable_frames = 0
    current = _navigation_motion_rect(motion)
    target = _navigation_motion_rect(motion, target=True)
    while time.monotonic() < deadline:
        app.processEvents()
        current = _navigation_motion_rect(motion)
        target = _navigation_motion_rect(motion, target=True)
        settled = (
            bool(motion.property("positionMotionEnabled")) is motion_enabled
            and _max_geometry_delta(current, target) <= 0.75
            and window.property("navigationResizeActive") is False
            and window.property("pageTransitioning") is False
            and window.property("pageContentReady") is True
        )
        if settled and previous is not None and _max_geometry_delta(current, previous) <= 0.1:
            stable_frames += 1
            if stable_frames >= 3:
                return
        else:
            stable_frames = 0
        previous = current
        QTest.qWait(20)

    raise AssertionError(
        "Prism CTA motion did not converge: "
        f"current={current}, target={target}, "
        f"enabled={motion.property('positionMotionEnabled')}, "
        f"page_transitioning={window.property('pageTransitioning')}"
    )


def _assert_item_inside_window_viewport(
    window: QQuickWindow,
    item: QQuickItem,
) -> None:
    origin = item.mapToItem(window.contentItem(), QPointF(0, 0))
    viewport_width = float(window.contentItem().width())
    viewport_height = float(window.contentItem().height())
    bounds = (
        float(origin.x()),
        float(origin.y()),
        float(item.width()),
        float(item.height()),
    )
    assert item.isVisible() and item.isEnabled()
    assert bounds[0] >= -0.5 and bounds[1] >= -0.5, (
        item.objectName(),
        bounds,
        viewport_width,
        viewport_height,
    )
    assert bounds[0] + bounds[2] <= viewport_width + 0.5, (
        item.objectName(),
        bounds,
        viewport_width,
        viewport_height,
    )
    assert bounds[1] + bounds[3] <= viewport_height + 0.5, (
        item.objectName(),
        bounds,
        viewport_width,
        viewport_height,
    )


def _assert_item_center_inside_window_viewport(
    window: QQuickWindow,
    item: QQuickItem,
) -> None:
    center = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    assert item.isVisible() and item.isEnabled()
    assert 0 <= center.x() < window.width(), (
        item.objectName(),
        center.x(),
        window.width(),
        center.y(),
        window.height(),
    )
    assert 0 <= center.y() < window.height(), (
        item.objectName(),
        center.x(),
        window.width(),
        center.y(),
        window.height(),
    )


def _assert_zero_progress_retarget_stops_old_animation(
    motion: QQuickItem,
    app: QApplication,
) -> None:
    assert QMetaObject.invokeMethod(motion, "settle") is True
    app.processEvents()
    start = _navigation_motion_rect(motion)
    animation_children = [
        child
        for child in motion.children()
        if child.metaObject().indexOfProperty("running") >= 0
        and child.metaObject().indexOfProperty("duration") >= 0
    ]
    assert animation_children, motion.objectName()

    def animation_running() -> bool:
        aggregate = motion.property("positionAnimationRunning")
        if aggregate is not None:
            return bool(aggregate)
        return any(bool(animation.property("running")) for animation in animation_children)

    assert animation_running() is False
    stale_target_x = start[0] + 100.0
    motion.setProperty("targetX", stale_target_x)
    assert float(motion.property("targetX")) == pytest.approx(stale_target_x)
    assert animation_running() is True
    assert _max_geometry_delta(_navigation_motion_rect(motion), start) <= 0.05

    # Return to the current x before delivering another event. The target is
    # now within the component's near-equality threshold, so it must stop the
    # old animation instead of returning while that stale target keeps moving.
    motion.setProperty("targetX", start[0])
    app.processEvents()
    assert float(motion.property("targetX")) == pytest.approx(start[0])
    assert _max_geometry_delta(_navigation_motion_rect(motion), start) <= 0.05
    assert animation_running() is False

    QTest.qWait(280)
    app.processEvents()
    assert _max_geometry_delta(_navigation_motion_rect(motion), start) <= 0.75
    assert animation_running() is False


def _scroll_control_into_view(
    window: QQuickWindow,
    scroll: QQuickItem,
    target: QQuickItem,
    app: QApplication,
) -> None:
    _wait_for_page_layout(window, scroll, app)
    target_origin = target.mapToItem(scroll, QPointF(0, 0)).y()
    target_height = float(target.property("height"))
    viewport_height = float(scroll.property("height"))
    max_scroll = max(
        0.0,
        float(scroll.property("contentHeight")) - viewport_height,
    )
    desired_scroll = max(
        0.0,
        min(
            max_scroll,
            target_origin - max(0.0, (viewport_height - target_height) / 2),
        ),
    )
    scroll.setProperty("contentY", desired_scroll)
    app.processEvents()
    _wait_for_page_layout(window, target, app)
    visible_origin = target.mapToItem(scroll, QPointF(0, 0)).y()
    assert visible_origin >= -0.5
    assert visible_origin + target_height <= viewport_height + 0.5
    center = target.mapToScene(
        QPointF(target.width() / 2, target.height() / 2),
    )
    assert 0 <= center.x() <= window.width()
    assert 0 <= center.y() <= window.height()


def _key_clicks(window: QQuickWindow, text: str) -> None:
    for character in text:
        QTest.keyClick(window, ord(character))


def _click_quick_item(window: QQuickWindow, object_name: str) -> QQuickItem:
    item = _find_quick_item(window, object_name)
    assert item is not None, object_name
    assert item.property("visible") is True, object_name
    assert QMetaObject.invokeMethod(item, "click") is True, object_name
    QCoreApplication.processEvents()
    return item


def _workbench_save_button_name(window: QQuickWindow) -> str:
    theme = _active_theme(window)
    assert theme is not None
    if theme.property("refraStyle"):
        return (
            "refraDarkApplyButton"
            if window.property("fullCanvasHome")
            else "darkSaveAllButton"
        )
    return "saveAllButton"


def _workbench_start_button_name(window: QQuickWindow) -> str:
    theme = _active_theme(window)
    assert theme is not None
    if theme.property("refraStyle"):
        return (
            "refraDarkStartButton"
            if window.property("fullCanvasHome")
            else "darkStartLiveButton"
        )
    return "startLiveButton"


def _slider_scene_point(slider: QQuickItem, visual_position: float) -> QPoint:
    handle = slider.property("handle")
    assert isinstance(handle, QQuickItem)
    handle_width = float(handle.property("width"))
    effective_track_width = float(slider.property("availableWidth")) - handle_width
    local_x = (
        float(slider.property("leftPadding"))
        + handle_width / 2
        + visual_position * effective_track_width
    )
    local_y = (
        float(slider.property("topPadding"))
        + float(slider.property("availableHeight")) / 2
    )
    return slider.mapToScene(QPointF(local_x, local_y)).toPoint()


def _open_dialog(dialog: QObject) -> None:
    assert QMetaObject.invokeMethod(dialog, "open") is True
    QCoreApplication.processEvents()
    assert dialog.property("visible") is True


def _quick_popup(owner: QObject) -> QObject:
    popups = [child for child in owner.children() if child.inherits("QQuickPopup")]
    assert len(popups) == 1
    return popups[0]


def _assert_prism_dialog_palette(
    window: QQuickWindow,
    theme: QObject,
    surface_name: str,
    *,
    dark: bool,
) -> None:
    expected_tokens = {
        "Background": "inkRaised",
        "Header": "glassRaised",
        "Content": "inkRaised",
        "Actions": "panel",
    }
    for suffix, token in expected_tokens.items():
        surface = window.findChild(QObject, surface_name + suffix)
        assert surface is not None, surface_name + suffix
        actual = QColor(surface.property("color"))
        expected = QColor(theme.property(token))
        assert actual == expected
        assert actual.lightness() < 128 if dark else actual.lightness() >= 128

    assert window.findChild(QObject, surface_name + "AcceptButton") is not None
    assert window.findChild(QObject, surface_name + "RejectButton") is not None


def _write_config(path: Path) -> None:
    path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "hy-mt1.5-7b"
""",
        encoding="utf-8",
    )


def _host(
    controller: _ControllerStub,
    *,
    application=None,
    selector_factory=None,
    theme_applier=None,
    tray_factory=None,
) -> tuple[QmlWorkbenchHost, _EngineRecorder]:
    engine = None

    def create_engine(parent: QObject) -> _EngineRecorder:
        nonlocal engine
        engine = _EngineRecorder(parent)
        return engine

    kwargs = {}
    if selector_factory is not None:
        kwargs["selector_factory"] = selector_factory
    if theme_applier is not None:
        kwargs["theme_applier"] = theme_applier
    if tray_factory is not None:
        kwargs["tray_factory"] = tray_factory
    host = QmlWorkbenchHost(
        controller,
        application=application or _application(),
        qml_path=Path(__file__),
        engine_factory=create_engine,
        **kwargs,
    )
    assert engine is not None
    return host, engine


def test_host_exposes_only_workbench_and_rebuilds_engine_around_live() -> None:
    controller = _ControllerStub()
    host, engine = _host(controller)

    assert engine.context.properties == [("workbench", controller)]
    assert len(engine.loaded_urls) == 1
    host.show()
    first_window = host.window
    assert first_window is not None
    assert first_window.isVisible()

    controller.liveReady.emit()
    assert host.window is None
    assert host.engine is None
    assert engine.root.release_count == 1
    assert engine.delete_count == 1

    controller.liveFinished.emit()
    second_window = host.window
    assert second_window is not None
    assert second_window is not first_window
    assert second_window.isVisible()
    controller.liveReady.emit()
    assert host.window is None
    controller.liveFailed.emit()
    restored_window = host.window
    assert restored_window is not None
    assert restored_window.isVisible()

    restored_window.close()


def test_host_configures_smooth_rendering_before_loading_qml(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        host_module,
        "_use_smooth_quick_rendering",
        lambda: calls.append("smooth"),
    )

    host, _ = _host(_ControllerStub())

    assert calls == ["smooth"]
    host.shutdown()


def test_host_hotkey_starts_once_and_ignores_an_already_running_live_process() -> None:
    class HotkeyController(_ControllerStub):
        def __init__(self) -> None:
            super().__init__()
            self.running = False
            self.start_count = 0
            self.hotkeyPreference = "Ctrl+Alt+T"

        def startLive(self) -> None:  # noqa: N802
            self.start_count += 1

    controller = HotkeyController()
    host, _engine = _host(controller)

    host._start_live_from_hotkey()
    assert controller.start_count == 1
    controller.running = True
    host._start_live_from_hotkey()
    assert controller.start_count == 1
    host.shutdown()


@pytest.mark.parametrize(
    ("behavior", "expect_restore"),
    ((HOTKEY_BEHAVIOR_TOGGLE, False), (HOTKEY_BEHAVIOR_TOGGLE_SHOW, True)),
)
def test_host_hotkey_toggle_stops_live_and_applies_window_behavior(
    behavior: str,
    expect_restore: bool,
) -> None:
    class ToggleController(_ControllerStub):
        def __init__(self) -> None:
            super().__init__()
            self.runPhase = "stopped"
            self.hotkeyBehaviorPreference = behavior

        def stopLive(self) -> None:  # noqa: N802
            self.stop_count += 1
            self.runPhase = "stopping"

    controller = ToggleController()
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)

    controller.liveReady.emit()
    assert host.window is None
    assert tray.visible is True
    controller.runPhase = "running"
    host._start_live_from_hotkey()
    assert controller.stop_count == 1
    assert host._pending_hotkey_stop_behavior == behavior

    controller.runPhase = "stopped"
    controller.liveFinished.emit()
    assert (host.window is not None) is expect_restore
    assert tray.visible is not expect_restore
    if expect_restore:
        assert host.window is not None
        assert host.window.isVisible()
    host.shutdown()


def test_host_hotkey_toggle_keeps_visible_workbench_visible_after_stop() -> None:
    class ToggleController(_ControllerStub):
        def __init__(self) -> None:
            super().__init__()
            self.runPhase = "stopped"
            self.hotkeyBehaviorPreference = HOTKEY_BEHAVIOR_TOGGLE
            self.running = True

        def stopLive(self) -> None:  # noqa: N802
            self.stop_count += 1
            self.runPhase = "stopping"

    controller = ToggleController()
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)
    host.show()
    assert host.window is not None
    controller.liveReady.emit()
    tray.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert host.window is not None
    assert host.window.isVisible()
    assert tray.visible is False

    controller.runPhase = "running"
    host._start_live_from_hotkey()
    assert controller.stop_count == 1
    controller.runPhase = "stopped"
    controller.liveFinished.emit()
    assert host.window is not None
    assert host.window.isVisible()
    assert tray.visible is False
    host.shutdown()


def test_host_hotkey_stop_failure_clears_pending_action_for_retry() -> None:
    class FailingStopController(_ControllerStub):
        def __init__(self) -> None:
            super().__init__()
            self.runPhase = "running"
            self.hotkeyBehaviorPreference = HOTKEY_BEHAVIOR_TOGGLE

    controller = FailingStopController()
    host, _engine = _host(controller)

    host._start_live_from_hotkey()
    host._start_live_from_hotkey()

    assert controller.stop_count == 2
    assert host._pending_hotkey_stop_behavior is None
    host.shutdown()


def test_host_hotkey_stop_failure_signal_restores_workbench_and_tray() -> None:
    class FailingProcessController(_ControllerStub):
        def __init__(self) -> None:
            super().__init__()
            self.runPhase = "stopped"
            self.hotkeyBehaviorPreference = HOTKEY_BEHAVIOR_TOGGLE

        def stopLive(self) -> None:  # noqa: N802
            self.stop_count += 1
            self.runPhase = "stopping"

    controller = FailingProcessController()
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)
    controller.liveReady.emit()
    controller.runPhase = "running"
    host._start_live_from_hotkey()
    assert host._pending_hotkey_stop_behavior == HOTKEY_BEHAVIOR_TOGGLE

    controller.runPhase = "failed"
    controller.liveFailed.emit()
    assert host._pending_hotkey_stop_behavior is None
    assert host.window is not None
    assert host.window.isVisible()
    assert tray.visible is False
    host.shutdown()


def test_host_hotkey_dispatch_guard_covers_synchronous_start_event_pump() -> None:
    class ReentrantController(_ControllerStub):
        def __init__(self) -> None:
            super().__init__()
            self.runPhase = "stopped"
            self.hotkeyBehaviorPreference = HOTKEY_BEHAVIOR_TOGGLE
            self.start_count = 0

        def startLive(self) -> None:  # noqa: N802
            self.start_count += 1
            host._start_live_from_hotkey()
            self.runPhase = "starting"

    controller = ReentrantController()
    host, _engine = _host(controller)

    host._start_live_from_hotkey()

    assert controller.start_count == 1
    assert host._hotkey_dispatch_in_progress is False
    host._start_live_from_hotkey()
    assert controller.start_count == 1
    host.shutdown()


def _real_home_hotkey_host(
    tmp_path: Path,
    *,
    display_name: str = "测试游戏",
) -> tuple[QApplication, WorkbenchController, QmlWorkbenchHost, QQuickWindow]:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name=display_name,
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    # These legacy Home checks exercise the original preferences tree. Keep
    # their theme and skin explicit so an elevated Windows account's system
    # color scheme cannot silently route them through the new dark Home. Tests
    # for the replacement dark preferences enter dark mode explicitly below.
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    return app, controller, host, window


def test_trigger_selector_has_three_modes_and_only_mouse_shows_wait_control(tmp_path: Path) -> None:
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    try:
        controller.setPage("OCR")
        app.processEvents()
        selector = window.findChild(QObject, "triggerMethodSelector")
        description = window.findChild(QObject, "triggerMethodDescription")
        mouse_settings = window.findChild(QObject, "mouseDwellSettings")
        stepper = window.findChild(QObject, "mouseDwellMsStepper")
        assert selector is not None and mouse_settings is not None and stepper is not None
        assert selector.property("count") == 3
        assert selector.property("currentIndex") == 1
        assert description is not None and description.property("visible") is False
        assert mouse_settings.property("visible") is False
        assert QMetaObject.invokeMethod(selector, "activated", Q_ARG(int, 2))
        app.processEvents()
        assert controller.triggerMethodIndex == 2
        assert selector.property("currentIndex") == 2
        assert description.property("visible") is True
        assert mouse_settings.property("visible") is True
        assert stepper.property("value") == 300
        window.resize(980, 700)
        QTest.qWait(20)
        scroll = window.findChild(QObject, "ocrSettingsScroll")
        assert scroll is not None
        scroll.setProperty("contentY", max(0, scroll.property("contentHeight") - scroll.height()))
        app.processEvents()
        position = stepper.mapToItem(scroll, QPointF(0, 0))
        assert position.y() >= 0
        assert position.y() + stepper.height() <= scroll.height() + 1
        assert QMetaObject.invokeMethod(stepper, "edited", Q_ARG(int, 750))
        app.processEvents()
        assert controller.mouseDwellMs == 750
        assert controller.saveRuntimeSettings() is True
        machine = load_config(controller._config_path)
        profile = load_game_profile(controller._config_path, machine, "game")
        assert profile.runtime_settings.live.mouse_dwell_ms == 750
        assert profile.runtime_settings.live.trigger_mode == "mouse_dwell"
        assert QMetaObject.invokeMethod(selector, "activated", Q_ARG(int, 0))
        app.processEvents()
        assert controller.triggerMethodIndex == 0
        assert controller.dynamicRoiEnabled is False
        assert mouse_settings.property("visible") is False
        controller._live_process = SimpleNamespace(poll=lambda: None)
        controller._set_run_state("正在翻译", "success", True)
        app.processEvents()
        assert selector.property("enabled") is False
        assert stepper.property("enabled") is False
        controller._live_process = None
        controller._set_run_state("已停止", "neutral", False)
    finally:
        controller._live_process = None
        host.shutdown()


def _begin_home_hotkey_recording(window: QQuickWindow) -> tuple[QObject, QObject]:
    preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
    dialog = window.findChild(QObject, "refraPreferencesDialog")
    assert preferences_button is not None
    assert dialog is not None
    if dialog.property("visible") is not True:
        assert QMetaObject.invokeMethod(preferences_button, "click") is True
        QCoreApplication.processEvents()
    assert dialog.property("visible") is True

    record_button = window.findChild(QObject, "refraHotkeyRecordButton")
    recording_hint = window.findChild(QObject, "refraHotkeyRecordingHint")
    assert record_button is not None
    assert recording_hint is not None
    assert QMetaObject.invokeMethod(record_button, "click") is True
    QCoreApplication.processEvents()
    assert recording_hint.property("visible") is True
    assert recording_hint.property("text") == (
        "正在录制：按住 Ctrl、Alt、Shift 或 Win，再按另一个键；Esc 取消"
    )
    assert record_button.property("text") == "按下组合键…"
    return record_button, recording_hint


def test_home_hotkey_recording_normalizes_and_escape_cancels(
    tmp_path: Path,
) -> None:
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    field = window.findChild(QObject, "refraHotkeyField")
    display = window.findChild(QObject, "refraHotkeyDisplay")
    assert field is not None
    assert display is not None
    try:
        hint = window.findChild(QObject, "settingHint-home-hotkey-control")
        assert hint is not None
        assert hint.property("description") == (
            "按住 Ctrl、Alt、Shift 或 Win 中的至少一个，再按另一个键，例如 Ctrl+Alt+T。"
        )
        record_button, recording_hint = _begin_home_hotkey_recording(window)
        QTest.keyClick(
            window,
            Qt.Key.Key_T,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        app.processEvents()

        assert controller.hotkeyPreference == "Ctrl+Shift+T"
        assert display.property("text") == "Ctrl+Shift+T"
        assert load_gui_preferences(
            controller._config_path,
        ).hotkey == "Ctrl+Shift+T"
        recording_hint = window.findChild(QObject, "refraHotkeyRecordingHint")
        assert recording_hint is not None
        assert recording_hint.property("visible") is False
        assert record_button.property("text") == "录制快捷键"

        old_value = controller.hotkeyPreference
        record_button, recording_hint = _begin_home_hotkey_recording(window)
        QTest.keyClick(window, Qt.Key.Key_Escape)
        app.processEvents()
        assert controller.hotkeyPreference == old_value
        assert display.property("text") == old_value
        assert recording_hint.property("visible") is False
        assert record_button.property("text") == "录制快捷键"
    finally:
        host.shutdown()


def test_home_hotkey_recording_accepts_ctrl_backspace_and_exits(
    tmp_path: Path,
) -> None:
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    display = window.findChild(QObject, "refraHotkeyDisplay")
    assert display is not None
    try:
        record_button, recording_hint = _begin_home_hotkey_recording(window)
        QTest.keyClick(window, Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier)
        app.processEvents()

        assert controller.hotkeyPreference == "Ctrl+Backspace"
        assert display.property("text") == "Ctrl+Backspace"
        assert load_gui_preferences(controller._config_path).hotkey == "Ctrl+Backspace"
        assert recording_hint.property("visible") is False
        assert record_button.property("text") == "录制快捷键"
    finally:
        host.shutdown()


def test_home_hotkey_recording_maps_all_runtime_special_keys(
    tmp_path: Path,
) -> None:
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    display = window.findChild(QObject, "refraHotkeyDisplay")
    assert display is not None
    special_keys = (
        (Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier, "space"),
        (
            Qt.Key.Key_Tab,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            "tab",
        ),
        (
            Qt.Key.Key_Backtab,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            "tab",
        ),
        (Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier, "enter"),
        (Qt.Key.Key_Enter, Qt.KeyboardModifier.ControlModifier, "return"),
        (Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier, "backspace"),
        (Qt.Key.Key_Insert, Qt.KeyboardModifier.ControlModifier, "insert"),
        (Qt.Key.Key_Delete, Qt.KeyboardModifier.ControlModifier, "delete"),
        (Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier, "home"),
        (Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier, "end"),
        (Qt.Key.Key_PageUp, Qt.KeyboardModifier.ControlModifier, "pageup"),
        (Qt.Key.Key_PageDown, Qt.KeyboardModifier.ControlModifier, "pagedown"),
        (Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier, "left"),
        (Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier, "right"),
        (Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier, "up"),
        (Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier, "down"),
    )
    assert {parser_key for _qt_key, _modifiers, parser_key in special_keys} == (
        set(runtime_module._SPECIAL_KEYS) - {"esc", "escape"}
    )
    try:
        for qt_key, modifiers, parser_key in special_keys:
            record_button, recording_hint = _begin_home_hotkey_recording(window)
            modifier_names = []
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                modifier_names.append("Ctrl")
            if modifiers & Qt.KeyboardModifier.AltModifier:
                modifier_names.append("Alt")
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                modifier_names.append("Shift")
            if modifiers & Qt.KeyboardModifier.MetaModifier:
                modifier_names.append("Win")
            expected = runtime_module.parse_hotkey(
                "+".join((*modifier_names, parser_key)),
            ).display

            QTest.keyClick(window, qt_key, modifiers)
            app.processEvents()

            assert controller.hotkeyPreference == expected
            assert display.property("text") == expected
            assert recording_hint.property("visible") is False
            assert record_button.property("text") == "录制快捷键"
    finally:
        host.shutdown()


def test_home_hotkey_recording_conflict_keeps_old_value_and_reports_error(
    tmp_path: Path,
) -> None:
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    display = window.findChild(QObject, "refraHotkeyDisplay")
    assert display is not None
    errors: list[tuple[str, str]] = []
    controller.errorRaised.connect(
        lambda title, message: errors.append((title, message)),
    )

    def reject_hotkey(_value: str) -> None:
        raise runtime_module.GuiRuntimeError("快捷键已被其他程序占用")

    controller.set_hotkey_registrar(reject_hotkey)
    try:
        _begin_home_hotkey_recording(window)
        QTest.keyClick(
            window,
            Qt.Key.Key_G,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        )
        app.processEvents()

        assert controller.hotkeyPreference == "Ctrl+Alt+T"
        assert display.property("text") == "Ctrl+Alt+T"
        assert errors == [("保存全局快捷键失败", "快捷键已被其他程序占用")]
        error_dialog = window.findChild(QObject, "errorDialog")
        assert error_dialog is not None
        assert error_dialog.property("errorMessage") == "快捷键已被其他程序占用"
    finally:
        host.shutdown()


def test_home_hotkey_default_button_restores_default_and_updates_display(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    controller.setHotkey("Ctrl+Shift+T")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
    assert preferences_button is not None
    assert QMetaObject.invokeMethod(preferences_button, "click") is True
    app.processEvents()
    display = window.findChild(QObject, "refraHotkeyDisplay")
    default_button = window.findChild(QObject, "refraHotkeyDefaultButton")
    assert display is not None
    assert default_button is not None
    try:
        assert display.property("text") == "Ctrl+Shift+T"
        assert QMetaObject.invokeMethod(default_button, "click") is True
        app.processEvents()
        assert controller.hotkeyPreference == "Ctrl+Alt+T"
        assert display.property("text") == "Ctrl+Alt+T"
        assert load_gui_preferences(config_path).hotkey == "Ctrl+Alt+T"
    finally:
        host.shutdown()


def test_home_hotkey_behavior_selector_persists_and_survives_live_recreate(
    tmp_path: Path,
) -> None:
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
    assert preferences_button is not None
    assert QMetaObject.invokeMethod(preferences_button, "click") is True
    app.processEvents()
    selector = window.findChild(QObject, "refraHotkeyBehaviorSelector")
    assert selector is not None
    try:
        assert selector.property("currentText") == "仅启动"
        scroll = window.findChild(QObject, "refraPreferencesScroll")
        assert scroll is not None
        scroll.setProperty(
            "contentY",
            max(
                0.0,
                float(scroll.property("contentHeight"))
                - float(scroll.property("height")),
            ),
        )
        app.processEvents()
        assert selector.property("visible") is True
        center = selector.mapToScene(
            QPointF(selector.width() / 2, selector.height() / 2),
        ).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center)
        app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()

        assert controller.hotkeyBehaviorPreference == HOTKEY_BEHAVIOR_TOGGLE_SHOW
        assert selector.property("currentText") == "启动 / 停止并打开 GUI"
        assert (
            load_gui_preferences(controller._config_path).hotkey_behavior
            == HOTKEY_BEHAVIOR_TOGGLE_SHOW
        )

        controller.liveReady.emit()
        app.processEvents()
        assert host.window is None
        controller.liveFinished.emit()
        app.processEvents()
        recreated = host.window
        assert recreated is not None
        recreated_selector = recreated.findChild(QObject, "refraHotkeyBehaviorSelector")
        assert recreated_selector is not None
        assert recreated_selector.property("currentIndex") == 2
        assert recreated_selector.property("currentText") == "启动 / 停止并打开 GUI"
    finally:
        host.shutdown()


@pytest.mark.parametrize("skin", (SKIN_PRISM, SKIN_DOHNA))
@pytest.mark.parametrize("hover_ms", (100, 450))
def test_combo_box_opening_cancels_pending_and_visible_setting_hints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skin: str,
    hover_ms: int,
) -> None:
    # Do not let another app's global hotkey open a blocking startup dialog.
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    try:
        controller.setTheme("dark")
        controller.setSkin(skin)
        if skin == SKIN_PRISM:
            preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
            assert preferences_button is not None and preferences_button.isVisible()
            button_center = preferences_button.mapToScene(
                QPointF(preferences_button.width() / 2, preferences_button.height() / 2),
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=button_center)
            app.processEvents()
            selector = _find_quick_item(window, "refraHotkeyBehaviorSelector")
            scroll = _find_quick_item(window, "refraPreferencesScroll")
        else:
            selector = _find_quick_item(window, "homeHotkeyBehaviorSelector")
            scroll = _find_quick_item(window, "homeSecondaryScroll")
        assert selector is not None and scroll is not None
        assert selector.isVisible()
        hint = _setting_hint_for_target(window, selector)
        _scroll_control_into_view(window, scroll, selector, app)
        center = selector.mapToScene(
            QPointF(selector.width() / 2, selector.height() / 2),
        ).toPoint()
        QTest.mouseMove(window, QPoint(2, 2))
        QTest.mouseMove(window, center)
        QTest.qWait(hover_ms)
        assert hint.property("hintVisible") is (hover_ms >= 400)

        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center)
        app.processEvents()
        popup = _quick_popup(selector)
        assert popup.property("visible") is True
        assert hint.property("hintVisible") is False
        QTest.qWait(450)
        assert popup.property("visible") is True
        assert hint.property("hintVisible") is False

        options = popup.property("contentItem")
        option_center = options.mapToScene(
            QPointF(options.width() / 2, options.height() / 2),
        ).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=option_center)
        app.processEvents()
        assert popup.property("visible") is False
        assert controller.hotkeyBehaviorPreference == HOTKEY_BEHAVIOR_TOGGLE

        QTest.mouseMove(window, QPoint(2, 2))
        QTest.mouseMove(window, center)
        QTest.qWait(450)
        assert hint.property("hintVisible") is True
    finally:
        host.shutdown()


@pytest.mark.parametrize("skin", (SKIN_PRISM, SKIN_DOHNA))
def test_open_combo_box_stays_above_delayed_label_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skin: str,
) -> None:
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    try:
        controller.setSkin(skin)
        controller.setTheme("light")
        if skin == SKIN_PRISM:
            preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
            assert preferences_button is not None
            assert QMetaObject.invokeMethod(preferences_button, "click") is True
            app.processEvents()
            selector = _find_quick_item(window, "refraHotkeyBehaviorSelector")
            scroll = _find_quick_item(window, "refraPreferencesScroll")
        else:
            selector = _find_quick_item(window, "homeHotkeyBehaviorSelector")
            scroll = _find_quick_item(window, "homeSecondaryScroll")
            hint = window.findChild(QObject, "settingHint-home-hotkey-behavior-label")
        assert selector is not None and scroll is not None
        if skin == SKIN_PRISM:
            hint = _setting_hint_for_target(window, selector)
        assert selector is not None and hint is not None and scroll is not None
        # A longer explanation wraps far enough to overlap the first menu option.
        hint.setProperty("description", str(hint.property("description")) * 3)
        _scroll_control_into_view(window, scroll, selector, app)
        label = hint.property("target")
        QTest.mouseMove(window, QPoint(2, 2))
        QTest.mouseMove(
            window,
            label.mapToScene(QPointF(label.width() / 2, label.height() / 2)).toPoint(),
        )
        QTest.qWait(450)
        assert hint.property("hintVisible") is True
        popup = _quick_popup(selector)
        assert QMetaObject.invokeMethod(popup, "open") is True
        QTest.qWait(450)
        assert popup.property("visible") is True

        hint_popup = _quick_popup(hint)
        assert float(popup.property("z")) > float(hint_popup.property("z"))

        controller.setHotkeyBehavior(HOTKEY_BEHAVIOR_TOGGLE_SHOW)
        options = popup.property("contentItem")
        option_center = options.mapToScene(
            QPointF(options.width() / 2, options.height() / 2),
        ).toPoint()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            pos=option_center,
        )
        app.processEvents()
        assert popup.property("visible") is False
        assert selector.property("currentIndex") == 1
        assert controller.hotkeyBehaviorPreference == HOTKEY_BEHAVIOR_TOGGLE
    finally:
        host.shutdown()


def test_real_controller_hotkey_toggle_normal_finish_stays_in_tray(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )

    class ProcessStub:
        pid = 4321

        def __init__(self) -> None:
            self.return_code: int | None = None

        def poll(self) -> int | None:
            return self.return_code

        def terminate(self) -> None:
            self.return_code = 1

    process = ProcessStub()
    popen_calls: list[object] = []
    monkeypatch.setattr(
        controller_module,
        "_validate_ocr_device_isolated",
        lambda _device: "gpu:0 · hotkey toggle test",
    )
    monkeypatch.setattr(
        controller_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: popen_calls.append(process) or process,
    )
    monkeypatch.setattr(
        controller_module,
        "_request_live_graceful_shutdown",
        lambda current: current is process,
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setHotkeyBehavior(HOTKEY_BEHAVIOR_TOGGLE)
    tray = _TrayRecorder()
    host = QmlWorkbenchHost(
        controller,
        application=app,
        tray_factory=lambda _app: tray,
    )
    try:
        controller.startLive()
        app.processEvents()
        assert controller.runPhase == "running"
        assert host.window is None
        assert tray.visible is True

        host._start_live_from_hotkey()
        assert controller.runPhase == "stopping"
        process.return_code = 0
        controller._check_live_process()
        app.processEvents()

        assert controller.runPhase == "stopped"
        assert host.window is None
        assert tray.visible is True
        assert app.quitOnLastWindowClosed() is False

        process.return_code = None
        host._start_live_from_hotkey()
        app.processEvents()
        assert len(popen_calls) == 2
        assert controller.runPhase == "running"
        assert host.window is None
        assert tray.visible is True
        assert app.quitOnLastWindowClosed() is False
    finally:
        host.shutdown()


def test_host_tray_recalls_workbench_and_running_close_returns_to_tray() -> None:
    controller = _ControllerStub()
    tray = _TrayRecorder()
    app = _application()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)

    assert tray.icon is not None
    assert tray.icon.cacheKey() == app.windowIcon().cacheKey()
    assert host.window is not None
    assert host.window.icon().cacheKey() == app.windowIcon().cacheKey()
    assert app.quitOnLastWindowClosed() is True
    host.show()
    controller.liveReady.emit()
    assert host.window is None
    assert tray.visible is True
    assert app.quitOnLastWindowClosed() is False

    tray.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
    recalled_window = host.window
    assert recalled_window is not None
    assert recalled_window.isVisible()

    controller.workbenchHideRequested.emit()
    assert host.window is None
    assert tray.visible is True

    controller.liveFinished.emit()
    restored_window = host.window
    assert restored_window is not None
    assert restored_window.isVisible()
    assert tray.visible is False
    assert app.quitOnLastWindowClosed() is True
    host.shutdown()


def test_login_tray_start_keeps_native_target_for_second_instance_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _ControllerStub()
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)

    host.hide_to_tray()
    assert host.window is None
    assert tray.visible is True
    activation_window = host._activation_window
    assert activation_window is not None
    target_hwnd = int(activation_window.winId())

    class NativeFunction:
        def __init__(self, callback):
            self._callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self._callback(*args)

    class Message(ctypes.Structure):
        _fields_ = (
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_uint32),
            ("wParam", ctypes.c_size_t),
            ("lParam", ctypes.c_ssize_t),
            ("time", ctypes.c_uint32),
            ("pt_x", ctypes.c_long),
            ("pt_y", ctypes.c_long),
        )

    posted: list[tuple[int, int]] = []

    class User32:
        def __init__(self) -> None:
            self.FindWindowW = NativeFunction(self._find_window)  # noqa: N802
            self.PostMessageW = NativeFunction(self._post_message)  # noqa: N802
            self.ShowWindow = NativeFunction(lambda *_args: True)  # noqa: N802
            self.SetForegroundWindow = NativeFunction(  # noqa: N802
                lambda *_args: True,
            )

        def _find_window(self, _class_name, title):
            if title == runtime_module.ACTIVATION_WINDOW_TITLE:
                return target_hwnd
            return 0

        def _post_message(self, hwnd, message, _wparam, _lparam):
            posted.append((hwnd, message))
            native_message = Message(hwnd, message, 0, 0, 0, 0, 0)
            assert activation_window.nativeEvent(
                b"windows_generic_MSG",
                ctypes.addressof(native_message),
            ) == (True, 0)
            return True

    monkeypatch.setattr(runtime_module.sys, "platform", "win32")
    user32 = User32()
    monkeypatch.setattr(runtime_module.ctypes, "windll", SimpleNamespace(user32=user32))

    assert runtime_module.activate_existing_window()
    assert posted == [(target_hwnd, runtime_module.ACTIVATION_MESSAGE)]
    assert host.window is not None
    assert host.window.isVisible()
    assert tray.visible is False
    host.shutdown()


def test_second_instance_target_wins_when_main_window_is_also_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _ActivationController()
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)
    controller.liveReady.emit()
    activation_window = host._activation_window
    assert activation_window is not None
    target_hwnd = int(activation_window.winId())
    main_hwnd = target_hwnd + 1

    class NativeFunction:
        def __init__(self, callback):
            self._callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self._callback(*args)

    class Message(ctypes.Structure):
        _fields_ = (
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_uint32),
            ("wParam", ctypes.c_size_t),
            ("lParam", ctypes.c_ssize_t),
            ("time", ctypes.c_uint32),
            ("pt_x", ctypes.c_long),
            ("pt_y", ctypes.c_long),
        )

    class User32:
        def __init__(self) -> None:
            self.find_titles: list[str] = []
            self.posted: list[tuple[int, int]] = []
            self.fronted: list[int] = []
            self.FindWindowW = NativeFunction(self._find_window)  # noqa: N802
            self.PostMessageW = NativeFunction(self._post_message)  # noqa: N802
            self.ShowWindow = NativeFunction(self._show_window)  # noqa: N802
            self.SetForegroundWindow = NativeFunction(  # noqa: N802
                self._set_foreground,
            )

        def _find_window(self, _class_name, title):
            self.find_titles.append(title)
            return {
                runtime_module.GUI_WINDOW_TITLE: main_hwnd,
                runtime_module.ACTIVATION_WINDOW_TITLE: target_hwnd,
            }.get(title, 0)

        def _post_message(self, hwnd, message, _wparam, _lparam):
            self.posted.append((hwnd, message))
            native_message = Message(hwnd, message, 0, 0, 0, 0, 0)
            assert activation_window.nativeEvent(
                b"windows_generic_MSG",
                ctypes.addressof(native_message),
            ) == (True, 0)
            return True

        def _show_window(self, hwnd, _command):
            self.fronted.append(hwnd)
            return True

        def _set_foreground(self, hwnd):
            self.fronted.append(hwnd)
            return True

    user32 = User32()
    monkeypatch.setattr(runtime_module.sys, "platform", "win32")
    monkeypatch.setattr(
        runtime_module.ctypes,
        "windll",
        SimpleNamespace(user32=user32),
    )
    try:
        assert runtime_module.activate_existing_window(timeout_seconds=0)
        assert user32.find_titles == [runtime_module.ACTIVATION_WINDOW_TITLE]
        assert user32.posted == [(target_hwnd, runtime_module.ACTIVATION_MESSAGE)]
        assert user32.fronted == []
        assert controller.stop_count == 1
        assert controller.runPhase == "stopping"
        assert host.window is None
    finally:
        host.shutdown()


def test_tray_double_click_restores_running_workbench_without_stopping() -> None:
    controller = _ActivationController()
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)
    try:
        controller.liveReady.emit()
        assert host.window is None

        host._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)

        assert controller.stop_count == 0
        assert controller.runPhase == "running"
        assert host.window is not None
        assert host.window.isVisible()
        assert tray.visible is False
    finally:
        host.shutdown()


def test_second_instance_open_wins_over_pending_hotkey_toggle_hide() -> None:
    controller = _ActivationController()
    controller.hotkeyBehaviorPreference = HOTKEY_BEHAVIOR_TOGGLE
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)
    try:
        controller.liveReady.emit()
        controller.runPhase = "running"
        host._start_live_from_hotkey()
        assert controller.stop_count == 1
        assert host._pending_hotkey_stop_behavior == HOTKEY_BEHAVIOR_TOGGLE

        host._activate_from_second_instance()
        assert host._activation_restore_pending is True
        assert controller.stop_count == 1

        controller.running = False
        controller.runPhase = "stopped"
        controller.liveFinished.emit()
        assert host.window is not None
        assert host.window.isVisible()
        assert tray.visible is False
        assert host._activation_restore_pending is False
    finally:
        host.shutdown()


@pytest.mark.parametrize("terminal_signal", ("liveFinished", "liveFailed"))
def test_second_instance_waits_for_live_terminal_signal_and_stops_once(
    terminal_signal: str,
) -> None:
    controller = _ActivationController()
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)
    try:
        controller.liveReady.emit()
        assert host.window is None
        assert tray.visible is True

        host._activate_from_second_instance()
        host._activate_from_second_instance()
        assert controller.stop_count == 1
        assert host.window is None
        assert tray.visible is True

        controller.running = False
        getattr(controller, terminal_signal).emit()
        assert host.window is not None
        assert host.window.isVisible()
        assert tray.visible is False
    finally:
        host.shutdown()


def test_second_instance_stop_failure_restores_window_and_reports_error() -> None:
    controller = _ActivationController(stop_result=False)
    tray = _TrayRecorder()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)
    try:
        controller.liveReady.emit()
        assert host.window is None

        host._activate_from_second_instance()

        assert controller.stop_count == 1
        assert controller.running is True
        assert host.window is not None
        assert host.window.isVisible()
        assert tray.visible is False
        assert host._application.quitOnLastWindowClosed() is False
        assert controller.host_errors == [
            (
                "停止实时翻译失败",
                "无法请求实时翻译正常关闭；实时翻译仍在运行，已恢复主窗口。",
            )
        ]
    finally:
        host.shutdown()


def _recall_native_workbench_from_second_launcher(
    initial_state: str,
    tmp_path: Path,
) -> None:
    """Exercise native Qt in a child, without changing the test application's state."""

    app = _application()
    assert app.platformName().lower() == "windows"
    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationDisplayName(PRODUCT_NAME)
    target_title = f"{runtime_module.ACTIVATION_WINDOW_TITLE} test {os.getpid()} {initial_state}"
    mutex_name = f"Local\\{PRODUCT_NAME}.GUI.test.{os.getpid()}.{initial_state}"
    runtime_module.ACTIVATION_WINDOW_TITLE = target_title
    host_module.ACTIVATION_WINDOW_TITLE = target_title
    guard = runtime_module.SingleInstanceGuard(mutex_name)
    controller = _ActivationController() if initial_state == "running" else _ControllerStub()
    tray = _TrayRecorder()
    host = None
    process = None
    try:
        assert guard.acquire()
        host, _engine = _host(controller, tray_factory=lambda _app: tray)
        host.show()
        if initial_state == "running":
            controller.liveReady.emit()
        elif initial_state == "tray":
            host.hide_to_tray()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        child_script = """
import sys
from game_screen_translator import gui_entry
from game_screen_translator.gui import runtime
runtime.ACTIVATION_WINDOW_TITLE = sys.argv[1]
gui_entry.SingleInstanceGuard = lambda: runtime.SingleInstanceGuard(sys.argv[2])
gui_entry._show_failure = lambda message: print(message, flush=True)
def unexpected_worker(*args, **kwargs):
    raise AssertionError("second launcher must not start another worker")
gui_entry._run_owned = unexpected_worker
raise SystemExit(gui_entry.run())
"""
        process = subprocess.Popen(
            [sys.executable, "-s", "-X", "utf8", "-c", child_script, target_title, mutex_name],
            cwd=tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + 5.0
        while process.poll() is None and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(1)
        output, _ = process.communicate(timeout=1.0)
        assert process.returncode == 0, output
        app.processEvents()
        if initial_state == "running":
            assert controller.stop_count == 1
            assert controller.runPhase == "stopping"
            assert host.window is None
            controller.running = False
            controller.runPhase = "stopped"
            controller.liveFinished.emit()
        else:
            assert controller.stop_count == 0
        assert host.window is not None
        assert host.window.isVisible()
        assert tray.visible is False
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5.0)
        if host is not None:
            host.shutdown()
        guard.release()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows Qt windows")
@pytest.mark.parametrize("initial_state", ("visible", "tray", "running"))
def test_second_launcher_recalls_native_workbench_with_application_display_name(
    initial_state: str,
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="windows",
        QT_PLUGIN_PATH="",
        QT_QPA_PLATFORM_PLUGIN_PATH="",
        QT_QUICK_BACKEND="software",
    )
    child_script = """
import runpy
import sys
from pathlib import Path
tests = runpy.run_path(sys.argv[1])
tests["_recall_native_workbench_from_second_launcher"](sys.argv[2], Path(sys.argv[3]))
"""
    result = subprocess.run(
        [sys.executable, "-s", "-X", "utf8", "-c", child_script,
         str(Path(__file__).resolve()), initial_state, str(tmp_path)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=15.0,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    os.name != "nt",
    reason="requires the native Windows Qt message dispatcher",
)
def test_activation_message_is_dispatched_once_by_real_windows_qt() -> None:
    app = _application()
    if app.platformName().lower() != "windows":
        pytest.skip("requires the native Windows Qt message dispatcher")
    callbacks: list[bool] = []
    activation_window = host_module._ActivationWindow(
        lambda: callbacks.append(True),
    )
    try:
        app.processEvents()
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        post_message = user32.PostMessageW
        post_message.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        post_message.restype = ctypes.c_bool
        assert post_message(
            ctypes.c_void_p(int(activation_window.winId())),
            runtime_module.ACTIVATION_MESSAGE,
            0,
            0,
        )
        deadline = time.monotonic() + 2.0
        while not callbacks and time.monotonic() < deadline:
            app.processEvents()
        app.processEvents()
        assert callbacks == [True]
    finally:
        activation_window.close()
        activation_window.deleteLater()
        app.processEvents()


@pytest.mark.skipif(
    os.name != "nt",
    reason="requires the native Windows Qt message dispatcher",
)
def test_hotkey_message_is_dispatched_once_by_real_windows_qt() -> None:
    app = _application()
    if app.platformName().lower() != "windows":
        pytest.skip("requires the native Windows Qt message dispatcher")
    callbacks: list[bool] = []
    hotkey = runtime_module.WindowsGlobalHotkey(
        app,
        lambda: callbacks.append(True),
        lambda _message: None,
    )
    hotkey._registered = True
    app.installNativeEventFilter(hotkey)
    hotkey._native_filter_installed = True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_thread_id = kernel32.GetCurrentThreadId
        get_thread_id.argtypes = ()
        get_thread_id.restype = ctypes.c_uint32
        post_thread_message = ctypes.WinDLL(
            "user32",
            use_last_error=True,
        ).PostThreadMessageW
        post_thread_message.argtypes = (
            ctypes.c_uint32,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        post_thread_message.restype = ctypes.c_bool
        assert post_thread_message(
            get_thread_id(),
            runtime_module._WM_HOTKEY,
            hotkey._hotkey_id,
            0,
        )
        deadline = time.monotonic() + 2.0
        while not callbacks and time.monotonic() < deadline:
            app.processEvents()
        app.processEvents()
        assert callbacks == [True]
    finally:
        hotkey._registered = False
        hotkey.unregister()


def test_real_workbench_close_while_running_hides_to_tray(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller._live_process = SimpleNamespace(poll=lambda: None)
    tray = _TrayRecorder()
    host = QmlWorkbenchHost(
        controller,
        application=app,
        tray_factory=lambda _app: tray,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    assert window.isVisible()

    window.close()
    app.processEvents()

    assert host.window is None
    assert controller.running is True
    assert tray.visible is True
    host.shutdown()


def test_real_workbench_close_while_stopped_keeps_normal_exit_path(
    tmp_path: Path,
) -> None:
    app = _application()
    app.setQuitOnLastWindowClosed(False)
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    tray = _TrayRecorder()
    host = QmlWorkbenchHost(
        controller,
        application=app,
        tray_factory=lambda _app: tray,
    )
    assert app.quitOnLastWindowClosed() is True
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    assert window.isVisible()
    assert controller.running is False

    window.close()
    app.processEvents()

    # The QML onClosing handler accepts a non-running close, so Qt hides the
    # real window and follows its normal last-window quit path.  No tray
    # fallback or host disposal is involved in this branch.
    assert window.isVisible() is False
    assert host.window is window
    assert tray.visible is False
    host.shutdown()


def test_host_applies_theme_once_per_change_and_again_for_rebuilt_window() -> None:
    controller = _ControllerStub()
    applications_and_windows: list[tuple[object, QQuickWindow, str, str]] = []

    def apply_theme(application, window, preference, effective_theme) -> None:
        applications_and_windows.append(
            (application, window, preference, effective_theme)
        )

    host, first_engine = _host(controller, theme_applier=apply_theme)

    assert applications_and_windows == [
        (_application(), first_engine.root, "dark", "dark")
    ]
    host.show()
    QCoreApplication.processEvents()
    assert applications_and_windows[-1] == (
        _application(),
        first_engine.root,
        "dark",
        "dark",
    )
    assert len(applications_and_windows) == 2
    controller.stateChanged.emit()
    assert len(applications_and_windows) == 2

    controller.themePreference = "light"
    controller.effectiveTheme = "light"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][1:] == (
        first_engine.root,
        "light",
        "light",
    )
    controller.stateChanged.emit()
    assert len(applications_and_windows) == 3

    controller.liveReady.emit()
    controller.liveFinished.emit()
    QCoreApplication.processEvents()
    rebuilt_window = host.window
    assert rebuilt_window is not None
    assert rebuilt_window is not first_engine.root
    assert applications_and_windows[-1][1:] == (
        rebuilt_window,
        "light",
        "light",
    )
    # The rebuilt window is themed once on creation and once after Qt shows it.
    assert len(applications_and_windows) == 5

    controller.themePreference = "system"
    controller.effectiveTheme = "dark"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][1:] == (
        rebuilt_window,
        "system",
        "dark",
    )
    assert len(applications_and_windows) == 6
    controller.effectiveTheme = "light"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][1:] == (
        rebuilt_window,
        "system",
        "light",
    )
    assert len(applications_and_windows) == 7
    host.shutdown()


def test_window_theme_helper_sets_qt_scheme_and_optional_windows_dwm() -> None:
    class StyleHintsRecorder:
        def __init__(self) -> None:
            self.schemes: list[Qt.ColorScheme] = []

        def setColorScheme(self, scheme: Qt.ColorScheme) -> None:  # noqa: N802
            self.schemes.append(scheme)

    class ApplicationRecorder:
        def __init__(self) -> None:
            self.hints = StyleHintsRecorder()

        def styleHints(self):  # noqa: N802
            return self.hints

    class WindowRecorder:
        def winId(self) -> int:  # noqa: N802
            return 731

    application = ApplicationRecorder()
    window = WindowRecorder()
    dwm_calls: list[tuple[int, bool]] = []

    host_module._apply_workbench_window_theme(
        application,
        window,
        "dark",
        "dark",
        platform_name="win32",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )
    host_module._apply_workbench_window_theme(
        application,
        window,
        "light",
        "light",
        platform_name="win32",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )
    host_module._apply_workbench_window_theme(
        application,
        window,
        "system",
        "dark",
        platform_name="win32",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )
    host_module._apply_workbench_window_theme(
        application,
        window,
        "dark",
        "dark",
        platform_name="linux",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )

    assert application.hints.schemes == [
        Qt.ColorScheme.Dark,
        Qt.ColorScheme.Light,
        Qt.ColorScheme.Unknown,
        Qt.ColorScheme.Dark,
    ]
    assert dwm_calls == [(731, True), (731, False), (731, True)]


def test_windows_dwm_adapter_uses_documented_attribute_and_bool_size(
    monkeypatch,
) -> None:
    calls: list[tuple[object, int, object, int]] = []

    class SetterRecorder:
        argtypes = None
        restype = None

        def __call__(self, *args) -> int:
            calls.append(args)
            return 0

    setter = SetterRecorder()
    fake_windll = type(
        "WindllRecorder",
        (),
        {"dwmapi": type("DwmApiRecorder", (), {"DwmSetWindowAttribute": setter})()},
    )()
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)

    host_module._set_windows_immersive_dark_mode(731, True)

    assert len(calls) == 1
    hwnd, attribute, value_pointer, value_size = calls[0]
    assert hwnd.value == 731
    assert attribute == 20
    assert ctypes.cast(value_pointer, ctypes.POINTER(ctypes.c_int)).contents.value == 1
    assert value_size == ctypes.sizeof(ctypes.c_int)


def test_window_theme_helper_safely_ignores_platform_failures() -> None:
    class FailingStyleHints:
        def setColorScheme(self, _scheme) -> None:  # noqa: N802
            raise RuntimeError("unsupported color scheme")

    class ApplicationRecorder:
        def styleHints(self):  # noqa: N802
            return FailingStyleHints()

    class WindowRecorder:
        def winId(self) -> int:  # noqa: N802
            return 731

    def fail_dwm(_window_id: int, _dark: bool) -> None:
        raise OSError("DWM unavailable")

    host_module._apply_workbench_window_theme(
        ApplicationRecorder(),
        WindowRecorder(),
        "dark",
        "dark",
        platform_name="win32",
        dwm_setter=fail_dwm,
    )


def test_host_loads_a_real_quick_window(tmp_path: Path) -> None:
    qml_path = tmp_path / "Main.qml"
    qml_path.write_text(
        "import QtQuick\nWindow { visible: false; width: 320; height: 200 }\n",
        encoding="utf-8",
    )
    controller = _ControllerStub()
    host = QmlWorkbenchHost(
        controller,
        application=_application(),
        qml_path=qml_path,
    )

    assert isinstance(host.window, QQuickWindow)
    assert host.engine is not None
    assert host.engine.rootContext().contextProperty("workbench") is controller
    host.window.close()


def test_real_workbench_loads_exactly_seven_pages_without_qml_warnings(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    qml_warnings: list[str] = []

    def create_engine(parent: QObject) -> QQmlApplicationEngine:
        engine = QQmlApplicationEngine(parent)
        engine.warnings.connect(
            lambda errors: qml_warnings.extend(error.toString() for error in errors)
        )
        return engine

    host = QmlWorkbenchHost(
        controller,
        application=app,
        engine_factory=create_engine,
    )
    page_names = (
        "homePage",
        "capturePage",
        "ocrPage",
        "translationPage",
        "overlayPage",
        "cachePage",
        "settingsPage",
    )

    window = host.window
    initial_engine = host.engine
    assert window is not None
    assert initial_engine is not None
    engine_destroyed: list[bool] = []
    initial_engine.destroyed.connect(lambda: engine_destroyed.append(True))
    assert window.objectName() == "prismWorkbenchWindow"
    assert window.minimumWidth() == 980
    assert window.minimumHeight() == 700
    assert window.property("animationsRunning") is False
    assert (
        QQuickWindow.textRenderType()
        == QQuickWindow.TextRenderType.CurveTextRendering
    )
    assert all(window.findChild(QObject, name) is not None for name in page_names)

    page_stack = window.findChild(QObject, "pageStack")
    assert page_stack is not None
    for index, page in enumerate(
        ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS")
    ):
        controller.setPage(page)
        app.processEvents()
        assert page_stack.property("currentIndex") == index

    external_settings = window.findChild(QObject, "externalSettings")
    builtin_settings = window.findChild(QObject, "builtinSettings")
    dynamic_schedule = window.findChild(QObject, "dynamicRoiSchedule")
    full_frame_schedule = window.findChild(QObject, "fullFrameSchedule")
    merge_toggle = window.findChild(QObject, "textMergeToggle")
    prompt_editor = window.findChild(QObject, "profilePromptEditor")
    assert all(
        item is not None
        for item in (
            external_settings,
            builtin_settings,
            dynamic_schedule,
            full_frame_schedule,
            merge_toggle,
            prompt_editor,
        )
    )
    controller.setPage("TRANSLATION")
    app.processEvents()
    assert external_settings.property("visible") is True
    assert builtin_settings.property("visible") is False
    controller.setBackend("builtin")
    app.processEvents()
    assert external_settings.property("visible") is False
    assert builtin_settings.property("visible") is True
    controller.setPage("SETTINGS")
    controller.setDynamicRoiEnabled(True)
    app.processEvents()
    assert dynamic_schedule.property("visible") is True
    assert full_frame_schedule.property("visible") is False
    controller.setDynamicRoiEnabled(False)
    app.processEvents()
    assert dynamic_schedule.property("visible") is False
    assert full_frame_schedule.property("visible") is True
    controller.setPage("OCR")
    controller.setDetectionQualityIndex(0)
    app.processEvents()
    assert merge_toggle.property("enabled") is False
    controller.setPage("TRANSLATION")
    app.processEvents()
    assert prompt_editor.property("enabled") is True

    host.show()
    app.processEvents()
    assert window.property("animationsRunning") is True
    controller.setReducedMotion(True)
    app.processEvents()
    assert window.property("animationsRunning") is False
    controller.liveReady.emit()
    app.processEvents()
    assert host.window is None
    assert host.engine is None
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert engine_destroyed == [True]
    controller.liveFinished.emit()
    app.processEvents()
    rebuilt_window = host.window
    assert rebuilt_window is not None
    assert rebuilt_window is not window
    rebuilt_stack = rebuilt_window.findChild(QObject, "pageStack")
    assert rebuilt_stack is not None
    assert rebuilt_stack.property("currentIndex") == 3
    assert qml_warnings == []
    host.shutdown()


def test_host_uses_light_native_hint_for_dohna_without_changing_saved_theme() -> None:
    controller = _ControllerStub()
    applications_and_windows: list[tuple[object, QQuickWindow, str, str]] = []

    def apply_theme(application, window, preference, effective_theme) -> None:
        applications_and_windows.append(
            (application, window, preference, effective_theme)
        )

    host, _engine = _host(controller, theme_applier=apply_theme)
    controller.skinPreference = SKIN_DOHNA
    controller.themePreference = "dark"
    controller.effectiveTheme = "light"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][2:] == ("light", "light")
    assert controller.themePreference == "dark"

    controller.skinPreference = SKIN_PRISM
    controller.stateChanged.emit()
    assert applications_and_windows[-1][2:] == ("dark", "light")
    host.shutdown()


def test_real_profile_dropdown_switches_and_restores_runtime_state(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    machine_config = load_config(config_path)
    profile_a = create_game_profile(
        config_path,
        machine_config,
        "galgame-a",
        display_name="Galgame A",
    )
    profile_b = create_game_profile(
        config_path,
        machine_config,
        "galgame-b",
        display_name="Galgame B",
    )
    save_profile_capture_settings(
        profile_a,
        ProfileCaptureSettings(monitor_index=0, region_ratio=_region_ratio((10, 20, 320, 140))),
    )
    save_profile_runtime_settings(
        profile_a,
        replace(
            machine_config,
            translation=replace(machine_config.translation, model="profile-a-model"),
            ocr=replace(
                machine_config.ocr,
                device="gpu:1",
                text_filter_enabled=False,
                detection_max_side=640,
            ),
            preview=replace(machine_config.preview, overlay_opacity=0.1),
            live=replace(
                machine_config.live,
                dynamic_roi_enabled=True,
                change_poll_fps=9,
                debug_border=True,
            ),
        ),
    )
    save_profile_capture_settings(
        profile_b,
        ProfileCaptureSettings(monitor_index=0, region_ratio=_region_ratio((40, 50, 520, 220))),
    )
    save_profile_runtime_settings(
        profile_b,
        replace(
            machine_config,
            translation=replace(machine_config.translation, model="profile-b-model"),
            ocr=replace(
                machine_config.ocr,
                device="gpu:0",
                text_filter_enabled=True,
                detection_max_side=2048,
            ),
            preview=replace(machine_config.preview, overlay_opacity=0.8),
            live=replace(
                machine_config.live,
                dynamic_roi_enabled=False,
                change_poll_fps=13,
                debug_border=False,
            ),
        ),
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    selector = window.findChild(QObject, "refraDarkProfileSelector")
    assert isinstance(selector, QQuickItem)
    assert selector.isVisible()
    assert controller.profileNames == ["Galgame A", "Galgame B"]
    assert controller.currentProfileIndex == 0
    assert selector.property("currentIndex") == 0
    activated_indices: list[int] = []
    selector.activated.connect(activated_indices.append)

    def assert_active_profile(name: str) -> None:
        assert selector.isVisible()
        assert selector.property("currentText") == name
        assert controller.currentProfileName == name

    def assert_profile_a() -> None:
        assert_active_profile("Galgame A")
        assert controller.currentProfileId == "galgame-a"
        assert controller.captureLeft == 10
        assert controller.captureTop == 20
        assert controller.captureWidth == 320
        assert controller.captureHeight == 140
        assert controller.ocrDevice == "gpu:1"
        assert controller.ocrFilterEnabled is False
        assert controller.model == "profile-a-model"
        assert controller.overlayOpacity == 0.1
        assert controller.dynamicRoiEnabled is True
        assert controller.changePollFps == 9
        assert controller.debugEnabled is True
        assert selector.property("currentIndex") == 0

    def assert_profile_b() -> None:
        assert_active_profile("Galgame B")
        assert controller.currentProfileId == "galgame-b"
        assert controller.captureLeft == 40
        assert controller.captureTop == 50
        assert controller.captureWidth == 520
        assert controller.captureHeight == 220
        assert controller.ocrDevice == "gpu:0"
        assert controller.ocrFilterEnabled is True
        assert controller.model == "profile-b-model"
        assert controller.overlayOpacity == 0.8
        assert controller.dynamicRoiEnabled is False
        assert controller.changePollFps == 13
        assert controller.debugEnabled is False
        assert selector.property("currentIndex") == 1

    def choose_with_dropdown(index: int, key: Qt.Key) -> None:
        center = selector.mapToScene(
            QPointF(selector.width() / 2, selector.height() / 2)
        ).toPoint()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            center,
        )
        app.processEvents()
        QTest.keyClick(window, key)
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.currentProfileIndex == index
        assert selector.property("currentIndex") == index

    assert_profile_a()
    choose_with_dropdown(1, Qt.Key.Key_Down)
    assert_profile_b()
    choose_with_dropdown(0, Qt.Key.Key_Up)
    assert_profile_a()
    assert activated_indices == [1, 0]
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
def test_real_skin_dropdown_highlight_uses_skin_specific_surface(
    tmp_path: Path,
    skin: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setTheme("light")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    if skin == SKIN_PRISM:
        preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
        assert preferences_button is not None and preferences_button.isVisible()
        assert QMetaObject.invokeMethod(preferences_button, "click") is True
        app.processEvents()
        selector = _find_quick_item(window, "refraHomeSkinSelector")
    else:
        selector = _find_quick_item(window, "homeSkinSelector")
    theme = _active_theme(window)
    assert isinstance(selector, QQuickItem)
    assert theme is not None
    center = selector.mapToScene(
        QPointF(selector.width() / 2, selector.height() / 2)
    ).toPoint()
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        center,
    )
    app.processEvents()

    def wait_for_delegates(object_name: str, minimum: int = 1) -> list[QQuickItem]:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            app.processEvents()
            delegates = _find_quick_items(window, object_name)
            if len(delegates) >= minimum:
                return delegates
            QTest.qWait(10)
        return _find_quick_items(window, object_name)

    def assert_prism_highlight(delegates: list[QQuickItem]) -> None:
        assert delegates
        input_surface = QColor(theme.property("inputSurface"))
        accent = QColor(theme.property("accent"))
        colors = [QColor(delegate.property("color")) for delegate in delegates]
        highlighted = [color for color in colors if color != input_surface]
        assert highlighted
        for color in highlighted:
            assert (color.red(), color.green(), color.blue()) == (
                accent.red(),
                accent.green(),
                accent.blue(),
            )
            assert 0 < color.alpha() < 255
        if len(colors) >= 2:
            assert input_surface in colors
            assert len({color.name(QColor.HexArgb) for color in colors}) >= 2

    if skin == SKIN_PRISM:
        popup_backgrounds = window.findChildren(
            QObject, "prismComboBoxPopupPrismBackground"
        )
        assert popup_backgrounds
        assert any(
            background.property("visible") is True
            and QColor(background.property("color")).alpha() == 255
            for background in popup_backgrounds
        )
        rows = wait_for_delegates(
            "prismComboBoxDelegatePrismBackground",
            minimum=2,
        )
        assert_prism_highlight(rows)

        assert selector.property("highlightedIndex") == 0
        QTest.keyClick(window, Qt.Key.Key_Down)
        rows = wait_for_delegates(
            "prismComboBoxDelegatePrismBackground",
            minimum=2,
        )
        assert selector.property("highlightedIndex") == 1
        assert_prism_highlight(rows)
    else:
        cuts = wait_for_delegates("prismComboBoxDohnaDelegateCut")
        assert cuts

        def assert_borderless_selection() -> None:
            for item in wait_for_delegates("prismComboBoxDohnaDelegateCut"):
                path = item.findChild(QObject, "prismComboBoxDohnaDelegatePath")
                assert path.property("strokeWidth") == 0
                assert QColor(path.property("strokeColor")).alpha() == 0
            for name in ("prismComboBoxDohnaBodyPath", "prismComboBoxDohnaPopupPath"):
                paths = window.findChildren(QObject, name)
                assert paths
                assert all(path.property("strokeWidth") == 0 for path in paths)
            assert selector.findChild(QObject, "prismComboBoxDohnaArrowFace") is None
            assert not window.findChildren(QObject, "prismComboBoxDohnaPopupShadow")

        assert_borderless_selection()
        assert any(
            item.property("visible") is True
            and item.property("x") >= 4
            and item.property("x") + item.property("width") <= selector.width() - 13
            and item.property("height") > 0
            for item in cuts
        )
        colors = [
            QColor(item.findChild(QObject, "prismComboBoxDohnaDelegatePath").property("fillColor"))
            for item in cuts
            if item.property("visible") is True
        ]
        assert QColor(theme.property("accent")) in colors
        QTest.keyClick(window, Qt.Key.Key_Up)
        cuts = wait_for_delegates("prismComboBoxDohnaDelegateCut")
        assert selector.property("highlightedIndex") == 0
        assert any(
            item.property("visible") is True
            and item.property("x") >= 4
            and item.property("x") + item.property("width") <= selector.width() - 13
            and item.property("height") > 0
            for item in cuts
        )
        colors = [
            QColor(item.findChild(QObject, "prismComboBoxDohnaDelegatePath").property("fillColor"))
            for item in cuts
            if item.property("visible") is True
        ]
        assert QColor(theme.property("violet")) in colors
        assert QColor(theme.property("accent")) in colors
        assert_borderless_selection()

        # Border removal must keep the real keyboard selection path working.
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.skinPreference == SKIN_PRISM

    QTest.keyClick(window, Qt.Key.Key_Escape)
    app.processEvents()
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
def test_profile_delete_dialog_cancel_confirm_and_empty_state(tmp_path: Path, skin: str) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(config_path, load_config(config_path), "game", display_name="测试游戏")
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setTheme("light")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        app.processEvents()
        window = host.window
        assert window is not None
        delete_button_name = (
            "refraDarkDeleteProfile" if skin == SKIN_PRISM
            else "openDeleteProfileDialogButton"
        )
        selector_name = (
            "refraDarkProfileSelector" if skin == SKIN_PRISM
            else "homeProfileSelector"
        )
        delete_button = window.findChild(QObject, delete_button_name)
        dialog = window.findChild(QObject, "deleteProfileDialog")
        assert delete_button is not None
        assert dialog is not None
        _click_quick_item(window, delete_button_name)
        assert dialog.property("visible") is True
        assert dialog.property("profileId") == "game"
        assert dialog.property("profileName") == "测试游戏"
        _click_quick_item(window, "deleteProfileDialogRejectButton")
        assert profile.settings_path.is_file()
        assert controller.hasProfile is True
        assert dialog.property("visible") is False

        _click_quick_item(window, delete_button_name)
        controller._live_process = SimpleNamespace(poll=lambda: None)
        controller.stateChanged.emit()
        app.processEvents()
        assert delete_button.property("enabled") is False
        assert dialog.property("acceptEnabled") is False
        controller._live_process = None
        controller.stateChanged.emit()
        app.processEvents()
        _click_quick_item(window, "deleteProfileDialogAcceptButton")
        assert dialog.property("visible") is False
        assert not profile.directory.exists()
        assert controller.hasProfile is False
        assert delete_button.property("enabled") is False
        selector = window.findChild(QObject, selector_name)
        assert selector.property("currentIndex") == -1
        assert selector.property("enabled") is False
        assert load_gui_preferences(config_path).last_profile_id == ""
    finally:
        controller._live_process = None
        host.shutdown()


def test_profile_and_external_model_names_use_one_control(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(config_path, load_config(config_path), "game", display_name="测试游戏")
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        app.processEvents()
        window = host.window
        assert window is not None
        window.resize(1280, 1000)
        controller.setSkin(SKIN_PRISM)
        controller.setTheme("light")
        profile_selector = _find_quick_item(window, "refraDarkProfileSelector")
        assert profile_selector is not None and profile_selector.isVisible()
        profile_hint = _setting_hint_for_target(window, profile_selector)
        assert profile_hint is not None
        assert profile_hint.property("target") == profile_selector
        assert profile_selector.property("currentText") == "测试游戏"
        legacy_profile_selector = _find_quick_item(window, "homeProfileSelector")
        assert legacy_profile_selector is None
        assert controller.maxConcurrency == 4
        assert controller.builtinParallel == 4
        assert controller.dynamicRoiEnabled is True
        assert controller.clearAfterMs == 150
        assert controller.roiResponseTargetMs == 350

        controller.setPage("TRANSLATION")
        page = window.findChild(QObject, "translationPage")
        assert isinstance(page, QQuickItem)
        _wait_for_page_layout(window, page, app)
        model_hints = window.findChildren(QObject, "settingHint-translation-external-model-control")
        assert len(model_hints) == 1
        selector = window.findChild(QObject, "externalModelSelector")
        editor = _find_quick_item(window, "externalModelEditor")
        assert isinstance(selector, QQuickItem)
        assert isinstance(editor, QQuickItem)
        assert selector.property("editable") is True
        assert editor.property("text") == controller.model

        editor.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        _key_clicks(window, "custom-model")
        app.processEvents()
        assert controller.model == "custom-model"
        assert editor.property("text") == "custom-model"

        reply = SimpleNamespace(
            error=lambda: controller_module.QNetworkReply.NetworkError.NoError,
            readAll=lambda: b'{"data":[{"id":"server-a"},{"id":"server-b"}]}',
            deleteLater=lambda: None,
        )
        controller._model_reply = reply
        controller._models_loaded(reply, "http://127.0.0.1:1234/v1/models")
        app.processEvents()
        assert editor.property("text") == "custom-model"
        assert selector.property("count") == 3

        selector.forceActiveFocus()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            selector.mapToScene(QPointF(selector.width() - 10, selector.height() / 2)).toPoint(),
        )
        app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.model == "server-a"
        assert editor.property("text") == "server-a"
        editor.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(window, Qt.Key.Key_Backspace)
        app.processEvents()
        assert controller.model == ""
        assert editor.property("text") == ""
        _key_clicks(window, "custom-after-fetch")
        app.processEvents()
        assert controller.model == "custom-after-fetch"
        controller.setModel("server-a")
        app.processEvents()
        assert editor.property("text") == "server-a"
        assert controller.saveRuntimeSettings() is True
        restored = apply_profile_runtime_settings(
            load_config(config_path),
            load_game_profile(config_path, load_config(config_path), "game"),
        )
        assert restored.translation.model == "server-a"
    finally:
        host.shutdown()


def test_real_setting_hints_cover_editable_options_and_exclude_read_only_actions(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("dark")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    window.resize(980, 700)
    window.update()
    QTest.qWait(20)

    expected_parts = {
        "home-profile": {"control"},
        "home-skin": {"control"},
        "home-theme": {"control"},
        "home-motion": {"control"},
            "home-startup": {"control"},
            "home-hotkey": {"control"},
            "home-hotkey-behavior": {"control"},
        "capture-monitor": {"label", "control"},
        "capture-fullscreen": {"control"},
        "capture-custom": {"control"},
        "capture-left": {"label", "control"},
        "capture-top": {"label", "control"},
        "capture-width": {"label", "control"},
        "capture-height": {"label", "control"},
        "ocr-device": {"label", "control"},
        "ocr-quality": {"label", "control"},
        "ocr-filter": {"control"},
        "ocr-merge": {"control"},
        "ocr-trigger-method": {"label", "control"},
        "ocr-mouse-dwell": {"label", "control"},
        "translation-backend": {"control"},
        "translation-builtin-model": {"label", "control"},
        "translation-builtin-device": {"label", "control"},
        "translation-builtin-parallel": {"label", "control"},
        "translation-builtin-cache": {"label", "control"},
        "translation-external-url": {"label", "control"},
        "translation-external-key": {"label", "control"},
        "translation-external-model": {"label", "control"},
        "translation-external-concurrency": {"label", "control"},
        "translation-prompt": {"label", "control"},
        "overlay-opacity": {"label", "control"},
        "settings-poll-fps": {"control"},
        "settings-clear-after": {"control"},
        "settings-roi-response": {"control"},
        "settings-stable-rescan": {"control"},
        "settings-idle-rescan": {"control"},
        "settings-ocr-cooldown": {"control"},
        "settings-browser-overlay": {"label", "control"},
        "settings-debug-border": {"control"},
    }

    startup_toggle = window.findChild(QObject, "refraHomeStartupToggle")
    assert startup_toggle is not None
    assert startup_toggle.property("text") == "开机自启动"

    hint_items: dict[tuple[str, str], list[QObject]] = {}
    for item in window.findChildren(QObject):
        object_name = item.objectName()
        if object_name.startswith("settingHint-"):
            hint_name = object_name.removeprefix("settingHint-")
            part = next(
                part_name
                for part_name in ("label", "control", "editor")
                if hint_name.endswith("-" + part_name)
            )
            key = hint_name[: -(len(part) + 1)]
            hint_items.setdefault((key, part), []).append(item)

    actual_parts = {
        key: {part for (item_key, part) in hint_items if item_key == key}
        for key in expected_parts
    }
    assert actual_parts == expected_parts
    assert set(hint_items) == {
        (key, part) for key, parts in expected_parts.items() for part in parts
    }
    expected_counts = {key_and_part: 1 for key_and_part in hint_items}
    expected_counts[("translation-backend", "control")] = 2
    assert {
        key_and_part: len(items) for key_and_part, items in hint_items.items()
    } == expected_counts
    assert all(
        hint.property("description")
        and any(
            "\u4e00" <= character <= "\u9fff"
            for character in str(hint.property("description"))
        )
        for hints in hint_items.values()
        for hint in hints
    )

    named_hints = [hint for hints in hint_items.values() for hint in hints]
    hint_targets = [hint.property("target") for hint in named_hints]
    for item in window.findChildren(QObject):
        if (
            item.metaObject().indexOfProperty("readOnly") >= 0
            and item.property("readOnly") is True
        ):
            assert item not in hint_targets
    for object_name in (
        "refraDarkCreateProfile",
        "refraDarkDeleteProfile",
        "createProfileNameField",
        "ocrProbeAction",
        "openDeleteModelDialogButton",
    ):
        excluded = window.findChild(QObject, object_name)
        assert excluded is not None
        assert excluded not in hint_targets

    for editor_name, setting_key in (
        ("glossaryEditor", "translation-glossary"),
        ("correctionsEditor", "cache-corrections"),
    ):
        editor = window.findChild(QObject, editor_name)
        assert editor is not None
        assert editor.property("entryCount") == 0
        assert not any(
            item.objectName().startswith("settingHint-" + setting_key)
            for item in editor.findChildren(QObject)
        )
        action_texts = {
            "添加一行",
            "删除选中行",
            str(editor.property("saveText")),
        }
        actions = [
            item
            for item in editor.findChildren(QObject)
            if item.metaObject().indexOfProperty("settingDescription") >= 0
            and str(item.property("text")) in action_texts
        ]
        assert {str(action.property("text")) for action in actions} == action_texts
        for action in actions:
            assert action.property("settingDescription") == ""
            assert action.property("settingKey") == ""
            action_hints = [
                item
                for item in action.findChildren(QObject)
                if item.metaObject().indexOfProperty("hintVisible") >= 0
            ]
            assert len(action_hints) == 1
            assert action_hints[0].property("description") == ""
            assert action_hints[0].property("enabled") is False

    def setting_hint(object_name: str) -> tuple[QObject, QQuickItem]:
        hint = window.findChild(QObject, object_name)
        assert hint is not None
        target = hint.property("target")
        assert isinstance(target, QQuickItem)
        return hint, target

    def wait_for_settings_scroll_restore() -> None:
        sync = next(
            item
            for item in window.findChildren(QQuickItem)
            if item.property("pageKey") == "SETTINGS"
            and item.property("scrollKey") == "scheduleForm"
            and item.property("active") is True
        )
        for _ in range(30):
            if not sync.property("restoring"):
                break
            QTest.qWait(10)
            app.processEvents()
        assert sync.property("restoring") is False

    def move_out(hint: QObject) -> None:
        QTest.mouseMove(window, QPoint(2, 2))
        app.processEvents()
        assert hint.property("hintVisible") is False

    def hover_target(
        hint: QObject,
        target: QQuickItem,
        local_point: QPointF | None = None,
    ) -> None:
        point_in_target = local_point or QPointF(
            target.width() / 2,
            target.height() / 2,
        )
        point = target.mapToScene(point_in_target).toPoint()
        QTest.mouseMove(window, point)
        QTest.qWait(300)
        assert hint.property("hintVisible") is False
        QTest.qWait(150)
        assert hint.property("hintVisible") is True

    preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
    assert preferences_button is not None and preferences_button.isVisible()
    preferences_point = preferences_button.mapToScene(
        QPointF(preferences_button.width() / 2, preferences_button.height() / 2),
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=preferences_point)
    app.processEvents()
    assert startup_toggle.isVisible()
    theme_selector = _find_quick_item(window, "refraHomeThemeSelector")
    assert theme_selector is not None and theme_selector.isVisible()
    control_hint = _setting_hint_for_target(window, theme_selector)
    hover_target(control_hint, theme_selector)
    move_out(control_hint)
    accept_button = _find_quick_item(window, "refraPreferencesDialogAcceptButton")
    assert accept_button is not None and accept_button.isVisible()
    accept_point = accept_button.mapToScene(
        QPointF(accept_button.width() / 2, accept_button.height() / 2),
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=accept_point)
    app.processEvents()

    controller.setPage("SETTINGS")
    controller.setDynamicRoiEnabled(False)
    app.processEvents()
    window.update()
    QTest.qWait(20)
    wait_for_settings_scroll_restore()

    stepper_hint, stepper = setting_hint(
        "settingHint-settings-poll-fps-control"
    )
    assert stepper.objectName() == "settingsCalibrationStepper"
    assert stepper.property("stackedDetails") is True
    assert float(stepper.property("width")) > float(stepper.property("compactWidth"))
    direct_control_names = {
        "numberStepperDecrease",
        "numberStepperEditor",
        "numberStepperIncrease",
    }
    direct_controls = {
        name: _find_quick_item(stepper, name)
        for name in direct_control_names
    }
    assert all(control is not None for control in direct_controls.values())
    for child in direct_controls.values():
        assert child.isVisible()
        child_center = child.mapToItem(
            stepper,
            QPointF(child.width() / 2, child.height() / 2),
        )
        hover_target(stepper_hint, stepper, child_center)
        move_out(stepper_hint)

    increase = direct_controls["numberStepperIncrease"]
    before_click = controller.changePollFps
    increase_point = increase.mapToScene(
        QPointF(increase.width() / 2, increase.height() / 2)
    ).toPoint()
    hover_target(
        stepper_hint,
        stepper,
        increase.mapToItem(
            stepper,
            QPointF(increase.width() / 2, increase.height() / 2),
        ),
    )
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        increase_point,
    )
    app.processEvents()
    assert controller.changePollFps == before_click + 1
    move_out(stepper_hint)

    controller.setPage("OCR")
    controller.setDetectionQualityIndex(0)
    app.processEvents()
    window.update()
    QTest.qWait(20)
    merge_toggle = window.findChild(QObject, "textMergeToggle")
    assert merge_toggle is not None
    assert merge_toggle.property("enabled") is False
    disabled_hint, disabled_target = setting_hint("settingHint-ocr-merge-control")
    hover_target(disabled_hint, disabled_target)
    move_out(disabled_hint)

    controller.setPage("SETTINGS")
    app.processEvents()
    window.update()
    QTest.qWait(20)
    wait_for_settings_scroll_restore()
    edge_hint, edge_target = setting_hint(
        "settingHint-settings-ocr-cooldown-control"
    )
    ancestor = edge_target.parentItem()
    flickable = None
    while ancestor is not None:
        if (
            ancestor.metaObject().indexOfProperty("contentY") >= 0
            and ancestor.metaObject().indexOfProperty("contentHeight") >= 0
        ):
            flickable = ancestor
            break
        ancestor = ancestor.parentItem()
    assert flickable is not None
    target_in_view = edge_target.mapToItem(flickable, QPointF(0, 0))
    desired_y = float(flickable.property("height")) - edge_target.height() - 12
    requested_content_y = (
        float(flickable.property("contentY")) + target_in_view.y() - desired_y
    )
    maximum_content_y = max(
        0.0,
        float(flickable.property("contentHeight"))
        - float(flickable.property("height")),
    )
    flickable.setProperty(
        "contentY",
        max(0.0, min(maximum_content_y, requested_content_y)),
    )
    window.update()
    QTest.qWait(20)
    app.processEvents()

    hover_target(edge_hint, edge_target)

    def scene_rect(item: QQuickItem) -> tuple[float, float, float, float]:
        origin = item.mapToScene(QPointF(0, 0))
        opposite = item.mapToScene(QPointF(item.width(), item.height()))
        return (
            min(origin.x(), opposite.x()),
            min(origin.y(), opposite.y()),
            abs(opposite.x() - origin.x()),
            abs(opposite.y() - origin.y()),
        )

    def assert_hint_geometry() -> tuple[float, float]:
        target_x, target_y, target_width, target_height = scene_rect(edge_target)
        view_x, view_y, view_width, view_height = scene_rect(flickable)
        popup_x = float(edge_hint.property("hintX"))
        popup_y = float(edge_hint.property("hintY"))
        popup_width = float(edge_hint.property("hintWidth"))
        popup_height = float(edge_hint.property("hintHeight"))
        visible_left = max(0.0, view_x) + 8
        visible_top = max(0.0, view_y) + 8
        visible_right = min(float(window.width()), view_x + view_width) - 8
        visible_bottom = min(float(window.height()), view_y + view_height) - 8

        assert popup_x >= visible_left - 0.5
        assert popup_y >= visible_top - 0.5
        assert popup_x + popup_width <= visible_right + 0.5
        assert popup_y + popup_height <= visible_bottom + 0.5
        vertical_gap = min(
            abs(popup_y - (target_y + target_height)),
            abs(target_y - (popup_y + popup_height)),
        )
        assert 7.0 <= vertical_gap <= 9.0
        assert popup_x <= target_x + target_width
        assert popup_x + popup_width >= target_x
        return target_y, popup_y

    first_target_y, first_popup_y = assert_hint_geometry()
    current_content_y = float(flickable.property("contentY"))
    moved_content_y = min(maximum_content_y, current_content_y + 16)
    if math.isclose(moved_content_y, current_content_y):
        moved_content_y = max(0.0, current_content_y - 16)
    assert not math.isclose(moved_content_y, current_content_y)
    flickable.setProperty("contentY", moved_content_y)
    window.update()
    QTest.qWait(20)
    QTest.mouseMove(
        window,
        edge_target.mapToScene(
            QPointF(edge_target.width() / 2, edge_target.height() / 2)
        ).toPoint(),
    )
    QTest.qWait(40)
    assert edge_hint.property("hintVisible") is True
    second_target_y, second_popup_y = assert_hint_geometry()
    assert math.isclose(
        second_popup_y - first_popup_y,
        second_target_y - first_target_y,
        abs_tol=1.0,
    )
    move_out(edge_hint)
    host.shutdown()


def test_pair_editor_existing_rows_show_one_adjacent_hint_and_remain_editable(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.saveGlossary([{"source": "仕事", "target": "委托"}])
    controller.saveCorrections([{"source": "待て。", "target": "等等。"}])
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    window.resize(980, 700)

    def visible_hints() -> list[QObject]:
        pending = [window.contentItem()]
        result: list[QObject] = []
        while pending:
            item = pending.pop()
            result.extend(
                child
                for child in item.children()
                if child.metaObject().indexOfProperty("hintVisible") >= 0
                and child.property("hintVisible") is True
            )
            pending.extend(item.childItems())
        return result

    def scene_rect(item: QQuickItem) -> tuple[float, float, float, float]:
        origin = item.mapToScene(QPointF(0, 0))
        opposite = item.mapToScene(QPointF(item.width(), item.height()))
        return (
            min(origin.x(), opposite.x()),
            min(origin.y(), opposite.y()),
            abs(opposite.x() - origin.x()),
            abs(opposite.y() - origin.y()),
        )

    cases = (
        (
            "TRANSLATION",
            "translationPage",
            "sideMode",
            "glossary",
            "glossaryEditor",
            "translation-glossary",
        ),
        (
            "CACHE",
            "cachePage",
            None,
            None,
            "correctionsEditor",
            "cache-corrections",
        ),
    )
    for page_name, page_object, mode_property, mode, editor_name, setting_key in cases:
        controller.setPage(page_name)
        page = window.findChild(QObject, page_object)
        assert page is not None
        if mode_property == "sideMode":
            window.setProperty("translationSideMode", mode)
        app.processEvents()
        window.update()
        QTest.qWait(20)
        app.processEvents()

        editor = window.findChild(QObject, editor_name)
        assert isinstance(editor, QQuickItem)
        assert editor.property("entryCount") == 1
        assert editor.findChild(
            QObject,
            "settingHint-" + setting_key + "-editor",
        ) is None

        for part, field_name in (
            ("source", "pairSourceField-0"),
            ("target", "pairTargetField-0"),
        ):
            field = _find_quick_item(editor, field_name)
            assert isinstance(field, QQuickItem)
            hint = field.findChild(
                QObject,
                "settingHint-" + setting_key + "-" + part + "-0-control",
            )
            assert hint is not None
            assert hint.property("target") == field
            assert hint.property("enabled") is True
            assert hint.property("description")
            assert field.property("visible") is True
            assert field.width() > 0
            assert field.height() > 0
            ancestor = field
            while ancestor is not None:
                assert ancestor.property("visible") is True, (
                    page_name,
                    ancestor.objectName(),
                )
                assert float(ancestor.property("opacity")) > 0, (
                    page_name,
                    ancestor.objectName(),
                )
                ancestor = ancestor.parentItem()

            field_center = field.mapToScene(
                QPointF(field.width() / 2, field.height() / 2)
            ).toPoint()
            assert 0 <= field_center.x() < window.width(), (
                page_name,
                field_center,
            )
            assert 0 <= field_center.y() < window.height(), (
                page_name,
                field_center,
            )
            QTest.mouseMove(window, field_center)
            app.processEvents()
            assert hint.property("hovered") is True
            QTest.qWait(300)
            assert visible_hints() == []
            QTest.qWait(150)
            actual_hints = visible_hints()
            assert actual_hints == [hint], (
                hint.property("hintVisible"),
                hint.property("hovered"),
                hint.property("hintX"),
                hint.property("hintY"),
                hint.property("hintWidth"),
                hint.property("hintHeight"),
            )

            target_x, target_y, target_width, target_height = scene_rect(field)
            popup_x = float(hint.property("hintX"))
            popup_y = float(hint.property("hintY"))
            popup_width = float(hint.property("hintWidth"))
            popup_height = float(hint.property("hintHeight"))
            vertical_gap = min(
                abs(popup_y - (target_y + target_height)),
                abs(target_y - (popup_y + popup_height)),
            )
            assert 7.0 <= vertical_gap <= 9.0
            assert popup_x <= target_x + target_width
            assert popup_x + popup_width >= target_x

            before_text = str(field.property("text"))
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                field_center,
            )
            app.processEvents()
            assert field.property("activeFocus") is True
            assert visible_hints() == [hint]
            QTest.keyClick(window, Qt.Key.Key_End)
            _key_clicks(window, "x")
            app.processEvents()
            assert field.property("text") == before_text + "x"

            QTest.mouseMove(window, QPoint(2, 2))
            app.processEvents()
            assert hint.property("hintVisible") is False
            assert visible_hints() == []

    host.shutdown()


def test_real_dohna_skin_switches_from_home_and_keeps_prism_theme_preference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    window.resize(980, 700)
    app.processEvents()

    dark_skin_selector = window.findChild(QObject, "refraHomeSkinSelector")
    dark_theme_selector = window.findChild(QObject, "refraHomeThemeSelector")
    theme = window.findChild(QObject, "prismTheme")
    motion_feedback = window.findChild(QObject, "prismMotionFeedback")
    assert theme is not None
    assert motion_feedback is not None
    assert window.findChild(QObject, "opticalStage") is None
    assert dark_skin_selector is not None
    assert dark_theme_selector is not None
    assert dark_skin_selector.property("visible") is False
    assert dark_theme_selector.property("visible") is False
    assert theme.property("dohna") is False
    assert motion_feedback.property("visible") is False

    for index in range(7):
        navigation_button = _find_quick_item(window, f"refraDarkNavigationButton{index}")
        assert navigation_button is not None
        assert navigation_button.property("visible") is True
        assert not _find_quick_items(window, f"navigationButton{index}")

    preferences = window.findChild(QObject, "refraDarkPreferencesButton")
    assert preferences is not None
    center = preferences.mapToScene(
        QPointF(preferences.width() / 2, preferences.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center)
    app.processEvents()
    assert dark_skin_selector.property("visible") is True
    assert dark_theme_selector.property("visible") is True
    assert dark_skin_selector.property("currentIndex") == 0
    assert dark_skin_selector.property("currentText") == "Prism"
    assert dark_theme_selector.property("currentText") == "深色"
    assert dark_theme_selector.property("enabled") is True
    center = dark_skin_selector.mapToScene(
        QPointF(dark_skin_selector.width() / 2, dark_skin_selector.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center)
    app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_Down)
    QTest.keyClick(window, Qt.Key.Key_Return)
    app.processEvents()

    assert controller.skinPreference == SKIN_DOHNA
    assert controller.themePreference == "dark"
    assert controller.effectiveTheme == "light"
    skin_selector = window.findChild(QObject, "homeSkinSelector")
    theme_selector = window.findChild(QObject, "homeThemeSelector")
    backdrop = window.findChild(QObject, "dohnaBackdrop")
    dohna_theme = window.findChild(QObject, "dohnaTheme")
    assert skin_selector is not None
    assert theme_selector is not None
    assert backdrop is not None
    assert dohna_theme is not None
    assert skin_selector.property("currentIndex") == 1
    assert skin_selector.property("currentText") == "Dohna"
    assert dark_skin_selector.property("currentIndex") == 1
    assert theme.property("dohna") is False
    assert theme.property("dark") is False
    assert dohna_theme.property("dohna") is True
    assert dohna_theme.property("dark") is False
    for index in range(7):
        navigation_button = _find_quick_item(window, f"navigationButton{index}")
        assert navigation_button is not None
        assert navigation_button.property("visible") is True
    assert theme_selector is not None
    assert theme_selector.property("enabled") is False
    assert theme_selector.property("currentIndex") == 2
    assert theme_selector.property("currentText") == "浅色"
    assert motion_feedback.property("visible") is False
    assert backdrop.property("visible") is True
    assert window.findChild(QObject, "homeDohnaThemeHint").property("visible") is True
    assert window.findChild(QObject, "pageDisplayTitleLight").property("text") == "翻译控制台"
    skin_body = skin_selector.findChild(QObject, "prismComboBoxDohnaBody")
    assert skin_body is not None
    assert skin_body.property("visible") is True
    assert skin_body.findChild(QObject, "prismComboBoxDohnaBodyPath").property("strokeWidth") == 0
    assert skin_selector.findChild(QObject, "prismComboBoxDohnaArrowFace") is None
    assert skin_selector.findChild(QObject, "prismComboBoxDohnaShadow") is None
    assert skin_selector.findChild(QObject, "prismComboBoxDohnaCorner") is None

    secondary_scroll = window.findChild(QObject, "homeSecondaryScroll")
    assert secondary_scroll is not None
    motion_toggle = next(
        item
        for item in window.findChildren(QQuickItem)
        if item.property("settingKey") == "home-motion"
    )
    secondary_scroll.setProperty(
        "contentY",
        max(
            0.0,
            float(secondary_scroll.property("contentHeight"))
            - float(secondary_scroll.property("height")),
        ),
    )
    app.processEvents()
    motion_origin = motion_toggle.mapToItem(secondary_scroll, QPointF(0, 0))
    assert 0 <= motion_origin.y() <= secondary_scroll.height()

    page_titles = {
        "HOME": "翻译控制台",
        "CAPTURE": "画面捕获",
        "OCR": "文字识别",
        "TRANSLATION": "译文设置",
        "OVERLAY": "字幕叠加",
        "CACHE": "翻译缓存",
        "SETTINGS": "高级设置",
    }
    for page, title in page_titles.items():
        controller.setPage(page)
        app.processEvents()
        assert window.findChild(QObject, "pageDisplayTitleLight").property("text") == title

    controller.setPage("HOME")
    app.processEvents()
    create_dialog = window.findChild(QObject, "createProfileDialog")
    assert create_dialog is not None
    _open_dialog(create_dialog)
    _assert_prism_dialog_palette(window, dohna_theme, "createProfileDialog", dark=False)
    _click_quick_item(window, "createProfileDialogRejectButton")

    controller.setPage("CAPTURE")
    app.processEvents()
    assert window.findChild(QObject, "pageDisplayTitleLight").property("text") == "画面捕获"
    controller.setPage("HOME")
    controller.setSkin(SKIN_PRISM)
    app.processEvents()
    assert controller.themePreference == "dark"
    preferences = window.findChild(QObject, "refraDarkPreferencesButton")
    assert preferences is not None and preferences.isVisible()
    center = preferences.mapToScene(
        QPointF(preferences.width() / 2, preferences.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center)
    app.processEvents()
    assert dark_theme_selector.property("visible") is True
    assert dark_theme_selector.property("currentText") == "深色"
    assert dark_theme_selector.property("enabled") is True
    preferences_accept = window.findChild(QObject, "refraPreferencesDialogAcceptButton")
    assert preferences_accept is not None and preferences_accept.isVisible()
    _click_quick_item(window, "refraPreferencesDialogAcceptButton")
    assert theme_selector.property("enabled") is False
    assert theme.property("dohna") is False
    assert theme.property("dark") is True
    assert motion_feedback.property("visible") is False
    assert motion_feedback.property("motionEnabled") is False
    for saved_theme, label in (("system", "跟随系统"), ("light", "浅色")):
        controller.setTheme(saved_theme)
        controller.setSkin(SKIN_DOHNA)
        app.processEvents()
        assert theme_selector.property("currentText") == "浅色"
        assert theme_selector.property("enabled") is False
        assert controller.themePreference == saved_theme
        controller.setSkin(SKIN_PRISM)
        app.processEvents()
        if theme.property("refraStyle") is True:
            assert theme_selector.property("visible") is False
            assert theme_selector.property("enabled") is False
            preferences = window.findChild(QObject, "refraDarkPreferencesButton")
            assert preferences is not None and preferences.isVisible()
            center = preferences.mapToScene(
                QPointF(preferences.width() / 2, preferences.height() / 2)
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center)
            app.processEvents()
            assert dark_theme_selector.property("visible") is True
            assert dark_theme_selector.property("currentText") == label
            assert dark_theme_selector.property("enabled") is True
            _click_quick_item(window, "refraPreferencesDialogAcceptButton")
        else:
            assert theme_selector.property("visible") is True
            assert theme_selector.property("currentText") == label
            assert theme_selector.property("enabled") is True
    host.shutdown()


def test_real_dohna_titles_enter_opposite_content_on_every_page(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_DOHNA)
    controller.setTheme("light")
    controller.setReducedMotion(False)
    controller.setPage("SETTINGS")
    host = QmlWorkbenchHost(controller, application=app)
    try:
        window = host.window
        assert window is not None
        host.show()
        header = window.findChild(QObject, "pageHeaderTranslate")
        content = window.findChild(QObject, "pageContentTranslate")
        title = window.findChild(QQuickItem, "pageDisplayTitleLight")
        header_bar = window.findChild(QObject, "pageHeaderBar")
        assert header_bar.property("clip") is True
        for page in ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"):
            controller.setPage(page)
            QTest.qWait(10)
            assert window.property("pageTransitioning") is True
            samples = [(float(header.property("x")), float(content.property("x")))]
            title_positions = [title.mapToScene(QPointF(0, 0)).x()]
            assert samples[0][0] < 0 < samples[0][1], page
            deadline = time.monotonic() + 1.2
            while window.property("pageTransitioning"):
                QTest.qWait(20)
                app.processEvents()
                samples.append((float(header.property("x")), float(content.property("x"))))
                title_positions.append(title.mapToScene(QPointF(0, 0)).x())
                assert time.monotonic() < deadline, page
            # The title travels right and the controls travel left throughout
            # the animation; both finish at their normal layout positions.
            assert all(h <= 0 <= c for h, c in samples), page
            assert all(h1 <= h2 and c1 >= c2
                       for (h1, c1), (h2, c2) in zip(samples, samples[1:])), page
            assert samples[-1] == pytest.approx((0, 0)), page
            assert all(x1 <= x2 for x1, x2 in zip(title_positions, title_positions[1:])), page

        controller.setPage("HOME")
        controller.setReducedMotion(True)
        QTest.qWait(20)
        assert window.property("pageTransitioning") is False
        assert header.property("x") == content.property("x") == 0
        controller.setPage("CAPTURE")
        app.processEvents()
        assert header.property("x") == content.property("x") == 0
        controller.setSkin(SKIN_PRISM)
        app.processEvents()
        assert header_bar.property("clip") is True
    finally:
        host.shutdown()


@pytest.mark.parametrize("checked", [False, True])
def test_native_dohna_toggle_smooths_edges_without_shrinking_or_clipping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checked: bool,
) -> None:
    # This pixel-only test must not depend on whether another app owns the
    # user's system-wide default shortcut.
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    if app.platformName() != "windows":
        pytest.skip("requires native Windows rendering for pixel coverage checks")
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_DOHNA)
    controller.setReducedMotion(True)
    controller.setPage("SETTINGS")
    controller.setBrowserOverlayEnabled(checked)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        window = host.window
        assert window is not None
        host.show()
        QTest.qWait(100)
        toggle = _find_quick_item(window, "settingsCalibrationAction")
        assert toggle.property("checked") is checked
        form = _find_quick_item(window, "settingsFormScroll")
        assert form is not None
        form_sync = next(
            item
            for item in window.findChildren(QQuickItem)
            if item.property("scrollKey") == "scheduleForm"
            and item.property("active") is True
        )
        for _ in range(12):
            if not form_sync.property("restoring"):
                break
            QTest.qWait(10)
            app.processEvents()
        assert form_sync.property("restoring") is False
        form.setProperty(
            "contentY", max(0, form.property("contentHeight") - form.height())
        )
        QTest.qWait(20)
        app.processEvents()
        if checked:
            toggle.forceActiveFocus()
        artwork = toggle.findChild(QQuickItem, "prismToggleDohnaArtwork")
        surface = toggle.findChild(QQuickItem, "prismToggleDohnaCut")
        knob = toggle.findChild(QQuickItem, "prismToggleDohnaKnob")
        theme = _theme_for_skin(window, SKIN_DOHNA)
        background = QColor(theme.property("white")).rgb()
        palette = {QColor(theme.property(name)).rgb()
                   for name in ("white", "paper", "ink", "accent", "violet")}

        def coverage() -> tuple[int, tuple[int, int, int, int]]:
            # Keep the pointer away from the control so the native hover
            # treatment cannot change its edge pixels between runs.
            QTest.mouseMove(window, QPoint(8, 8))
            QTest.qWait(100)
            app.processEvents()
            window.update()
            QTest.qWait(60)
            frame = window.grabWindow()
            assert not frame.isNull()
            origin = artwork.mapToScene(QPointF(0, 0))
            dpr = window.devicePixelRatio()
            left, top = round(origin.x() * dpr), round(origin.y() * dpr)
            width, height = round(artwork.width() * dpr), round(artwork.height() * dpr)
            pixels = {(x, y): frame.pixel(left + x, top + y)
                      for y in range(height) for x in range(width)}
            # The antialiased outline remains fully inside its transparent
            # margin, including both the rightmost tip and the lower edge.
            edge_pixels = [
                (x, y, hex(color))
                for (x, y), color in pixels.items()
                if (x in (0, width - 1) or y in (0, height - 1))
                and color != background
            ]
            assert not edge_pixels, (
                edge_pixels[:20], background, origin, dpr, width, height,
                window.width(), window.height(), frame.width(), frame.height(),
            )
            foreground = [(x, y) for (x, y), color in pixels.items() if color != background]
            assert foreground
            bounds = (min(x for x, _ in foreground), min(y for _, y in foreground),
                      max(x for x, _ in foreground), max(y for _, y in foreground))
            return sum(color not in palette for color in pixels.values()), bounds

        smoothed_edges, smoothed_bounds = coverage()
        # Compare with the previous unfiltered drawing in the same window,
        # at the same DPI, to catch an ineffective antialiasing declaration.
        assert QQmlProperty.write(artwork, "layer.enabled", False)
        surface.setProperty("antialiasing", False)
        knob.setProperty("antialiasing", False)
        aliased_edges, aliased_bounds = coverage()
        assert smoothed_edges > aliased_edges
        assert all(abs(actual - original) <= 2
                   for actual, original in zip(smoothed_bounds, aliased_bounds))
    finally:
        host.shutdown()


def test_real_dohna_uses_local_control_feedback_and_settles_on_switch_or_hide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    controller.setSkin(SKIN_DOHNA)
    controller.setReducedMotion(False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "dohnaTheme")
    motion_feedback = window.findChild(QObject, "prismMotionFeedback")
    feedback = window.findChild(QObject, "dohnaFeedbackLayer")
    page_content = window.findChild(QObject, "pageContentMotion")
    content_translate = window.findChild(QObject, "pageContentTranslate")
    page_header = window.findChild(QObject, "pageHeaderSlice")
    page_title = window.findChild(QObject, "pageDisplayTitle")
    panel_body = window.findChild(QObject, "prismPanelDohnaBody")
    toggle_cut = window.findChild(QObject, "prismToggleDohnaCut")
    save_button = (
        window.findChild(QObject, "refraDarkApplyButton")
        or window.findChild(QObject, "darkSaveAllButton")
        or window.findChild(QObject, "saveAllButton")
    )
    nav_button = _find_quick_item(window, "navigationButton1")
    required_items = {
        "theme": theme,
        "feedback": feedback,
        "page_content": page_content,
        "content_translate": content_translate,
        "page_header": page_header,
        "page_title": page_title,
        "panel_body": panel_body,
        "toggle_cut": toggle_cut,
        "save_button": save_button,
        "nav_button": nav_button,
    }
    assert all(item is not None for item in required_items.values()), [
        name for name, item in required_items.items() if item is None
    ]
    assert motion_feedback is None
    assert window.findChild(QObject, "prismTheme") is None
    assert theme.property("dohna") is True
    for decoration in (
        "dohnaPageImpact",
        "dohnaPageImpactShadow",
        "prismPanelDohnaStamp",
        "prismPanelDohnaStampShadow",
        "prismButtonDohnaFocusSlash",
        "dohnaActionImpact",
        "dohnaActionImpactShadow",
        "dohnaActionImpactTag",
        "dohnaStartImpact",
        "dohnaStartImpactTag",
    ):
        assert not window.findChildren(QObject, decoration)
    backdrop = window.findChild(QObject, "dohnaBackdrop")
    assert backdrop is not None
    assert backdrop.findChild(QObject, "dohnaPrintFacet").property("visible") is True
    assert feedback.property("motionEnabled") is True
    assert window.findChild(QObject, "pageTransitionSweep") is None
    assert panel_body.property("visible") is True
    assert panel_body.property("width") > 0
    assert panel_body.property("height") > 0
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    assert float(panel_body.property("opacity")) == 1
    assert float(page_title.property("opacity")) == 1
    assert toggle_cut.property("width") == 34
    assert toggle_cut.property("height") == 18
    for path_name in (
        "prismToggleDohnaPathTopRight",
        "prismToggleDohnaPathBottomRight",
        "prismToggleDohnaPathBottomLeft",
    ):
        path = toggle_cut.findChild(QObject, path_name)
        assert path is not None
        assert 0 <= float(path.property("x")) <= float(toggle_cut.property("width"))
        assert 0 <= float(path.property("y")) <= float(toggle_cut.property("height"))
    dohna_shape = save_button.findChild(QObject, "prismButtonDohnaCut")
    assert dohna_shape is not None
    assert dohna_shape.property("visible") is True

    skin_selector = window.findChild(QObject, "homeSkinSelector")
    assert skin_selector is not None
    selector_center = skin_selector.mapToScene(
        QPointF(skin_selector.width() / 2, skin_selector.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=selector_center)
    QTest.qWait(30)
    app.processEvents()
    popup_bodies = window.findChildren(QObject, "prismComboBoxDohnaPopupBody")
    assert popup_bodies
    assert any(item.property("visible") is True for item in popup_bodies)
    delegate_cuts = _find_quick_items(
        window, "prismComboBoxDohnaDelegateCut"
    )
    assert delegate_cuts
    assert any(
        item.property("visible") is True
        and item.property("x") >= 4
        and item.property("x") + item.property("width") <= skin_selector.width() - 13
        and item.property("height") > 0
        for item in delegate_cuts
    )
    QTest.keyClick(window, Qt.Key.Key_Escape)
    app.processEvents()

    controller.setPage("CAPTURE")
    app.processEvents()
    assert window.property("pageContentReady") is True
    assert window.property("pageTransitioning") is True
    capture_panels = [
        window.findChild(QObject, "capturePrimaryPanel"),
        window.findChild(QObject, "captureSecondaryPanel"),
    ]
    assert all(panel is not None for panel in capture_panels)
    visible_capture_panels = [panel for panel in capture_panels if panel.isVisible()]
    assert visible_capture_panels

    def find_visible_text(item: QQuickItem) -> QQuickItem | None:
        pending = list(item.childItems())
        while pending:
            candidate = pending.pop()
            if candidate.isVisible() and candidate.metaObject().indexOfProperty("text") >= 0:
                value = candidate.property("text")
                if isinstance(value, str) and value:
                    return candidate
            pending.extend(candidate.childItems())
        return None

    capture_text = find_visible_text(visible_capture_panels[0])
    assert capture_text is not None

    def opacity_chain(item: QQuickItem) -> list[QQuickItem]:
        chain = []
        current = item
        while current is not None:
            chain.append(current)
            if current is page_content:
                break
            current = current.parentItem()
        assert chain[-1] is page_content
        return chain

    capture_chains = [
        opacity_chain(panel) for panel in visible_capture_panels
    ] + [opacity_chain(capture_text)]

    def assert_opaque_capture_tree() -> None:
        for chain in capture_chains:
            for item in chain:
                assert float(item.property("opacity")) == pytest.approx(1.0), (
                    item.objectName(),
                    float(item.property("opacity")),
                )

    assert_opaque_capture_tree()
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    assert float(page_title.property("opacity")) == 1
    assert float(content_translate.property("x")) > 40
    sampled_content_x = []
    sample_deadline = time.monotonic() + 1.2
    while window.property("pageTransitioning"):
        app.processEvents()
        assert_opaque_capture_tree()
        sampled_content_x.append(float(content_translate.property("x")))
        if time.monotonic() >= sample_deadline:
            raise AssertionError("Dohna page transition did not settle")
        QTest.qWait(40)
    # The transition can finish during qWait; include its settled frame.
    sampled_content_x.append(float(content_translate.property("x")))
    assert len(sampled_content_x) >= 3
    assert sampled_content_x[0] > 0
    assert sampled_content_x[-1] == pytest.approx(0.0)
    assert_opaque_capture_tree()
    assert float(content_translate.property("x")) == pytest.approx(0.0)
    QTest.qWait(
        int(theme.property("dohnaTitleDelay"))
        + int(theme.property("dohnaTitleMotion"))
        + 80
    )
    app.processEvents()
    assert window.property("pageTransitioning") is False
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    assert float(page_title.property("opacity")) == 1

    # The selected navigation face and ordinary action face are both slanted;
    # pressing an ordinary real button gives a local offset without rotating
    # its text hit target.
    nav_cut = nav_button.findChild(QObject, "prismNavigationCut")
    assert nav_cut is not None
    assert nav_cut.property("visible") is True
    nav_path = nav_cut.findChild(QObject, "prismNavigationDohnaPath")
    assert nav_path.property("strokeWidth") == 0
    assert QColor(nav_path.property("fillColor")) == QColor(theme.property("violet"))
    assert nav_button.findChild(QObject, "prismButtonDohnaShadow").property("visible") is False

    # Keyboard focus uses the same flat highlight as hovering, without a frame.
    other_nav = _find_quick_item(window, "navigationButton2")
    other_nav.forceActiveFocus()
    app.processEvents()
    other_path = other_nav.findChild(QObject, "prismNavigationDohnaPath")
    assert other_path.property("strokeWidth") == 0
    assert QColor(other_path.property("fillColor")) == QColor(theme.property("violet"))
    button_center = save_button.mapToScene(
        QPointF(save_button.width() / 2, save_button.height() / 2)
    ).toPoint()
    QTest.mouseMove(window, button_center)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=button_center)
    app.processEvents()
    assert save_button.property("down") is True
    assert save_button.findChild(QObject, "prismButtonDohnaFocusSlash") is None
    assert float(save_button.property("dohnaImpact")) >= 0
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=button_center)
    QTest.qWait(int(theme.property("popPressMotion")) + 50)
    app.processEvents()
    assert float(save_button.property("dohnaImpact")) == 0

    # Switches keep their feedback inside the control. The knob moves and
    # changes color without creating a page-wide action strip.
    controller.setPage("SETTINGS")
    QTest.qWait(int(theme.property("popPageMotion")) + 40)
    app.processEvents()
    settings_toggle = _find_quick_item(window, "settingsCalibrationAction")
    assert settings_toggle is not None
    toggle_knob = settings_toggle.findChild(QQuickItem, "prismToggleDohnaKnob")
    assert toggle_knob is not None
    original_checked = bool(settings_toggle.property("checked"))
    original_knob_x = float(toggle_knob.property("x"))
    _click_quick_item(window, "settingsCalibrationAction")
    QTest.qWait(int(theme.property("popPressMotion")) + 30)
    app.processEvents()
    assert bool(settings_toggle.property("checked")) is not original_checked
    assert float(toggle_knob.property("x")) != original_knob_x
    expected_knob_color = theme.property("violet") if settings_toggle.property("checked") else theme.property("ink")
    assert QColor(toggle_knob.property("color")) == QColor(expected_knob_color)
    for decoration in (
        "dohnaActionImpact",
        "dohnaActionImpactShadow",
        "dohnaActionImpactTag",
    ):
        assert not window.findChildren(QObject, decoration)

    controller.reportHostError("测试错误", "反馈动画")
    app.processEvents()
    assert feedback.property("warningPulseRunning") is True
    error_dialog = window.findChild(QObject, "errorDialog")
    assert error_dialog is not None
    _click_quick_item(window, "errorDialogAcceptButton")
    QTest.qWait(int(theme.property("popWarningMotion")) + 60)
    app.processEvents()
    assert feedback.property("warningPulseRunning") is False

    # Reduced motion and hiding the window immediately stop warning feedback.
    controller.reportHostError("测试错误", "立即停止反馈")
    app.processEvents()
    assert feedback.property("warningPulseRunning") is True
    controller.setReducedMotion(True)
    app.processEvents()
    assert feedback.property("reducedMotion") is True
    assert feedback.property("warningPulseRunning") is False
    controller.setReducedMotion(False)
    controller.setPage("HOME")
    app.processEvents()
    window.hide()
    app.processEvents()
    assert feedback.property("motionEnabled") is False
    window.show()
    app.processEvents()

    controller.setPage("OCR")
    app.processEvents()
    assert window.property("pageTransitioning") is True
    controller.setPage("OVERLAY")
    app.processEvents()
    assert window.property("pageTransitioning") is True
    assert float(content_translate.property("x")) > 0
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    QTest.qWait(
        int(theme.property("dohnaTitleDelay"))
        + int(theme.property("dohnaTitleMotion"))
        + 80
    )
    app.processEvents()
    assert window.property("pageTransitioning") is False
    assert float(content_translate.property("x")) == 0
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    controller.setSkin(SKIN_PRISM)
    app.processEvents()
    prism_motion_feedback = window.findChild(QObject, "prismMotionFeedback")
    assert prism_motion_feedback is not None
    assert prism_motion_feedback.property("motionEnabled") is True
    assert window.findChild(QObject, "pageTransitionSweep") is None
    assert feedback.property("visible") is False
    transition_deadline = time.monotonic() + 1.2
    while window.property("pageTransitioning"):
        app.processEvents()
        assert time.monotonic() < transition_deadline
        QTest.qWait(20)
    assert window.property("pageTransitioning") is False
    assert window.property("pageContentReady") is True
    host.shutdown()


def test_real_prism_dialogs_follow_dark_and_light_themes_and_keep_actions(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "prismTheme")
    create_dialog = window.findChild(QObject, "createProfileDialog")
    delete_dialog = window.findChild(QObject, "deleteModelDialog")
    error_dialog = window.findChild(QObject, "errorDialog")
    profile_name = window.findChild(QObject, "createProfileNameField")
    assert theme is not None
    assert create_dialog is not None
    assert delete_dialog is not None
    assert error_dialog is not None
    assert profile_name is not None

    rejected_events: list[bool] = []
    create_dialog.rejected.connect(lambda: rejected_events.append(True))
    _open_dialog(create_dialog)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    app.processEvents()
    assert create_dialog.property("visible") is False
    assert rejected_events == [True]
    assert controller.hasProfile is False

    _open_dialog(create_dialog)
    _assert_prism_dialog_palette(
        window,
        theme,
        "createProfileDialog",
        dark=True,
    )
    _click_quick_item(window, "createProfileDialogRejectButton")
    assert create_dialog.property("visible") is False
    assert controller.hasProfile is False

    _open_dialog(create_dialog)
    profile_name.setProperty("text", "弹窗动作测试")
    app.processEvents()
    _click_quick_item(window, "createProfileDialogAcceptButton")
    assert create_dialog.property("visible") is False
    assert controller.hasProfile is True
    assert controller.currentProfileName == "弹窗动作测试"

    _open_dialog(delete_dialog)
    _assert_prism_dialog_palette(
        window,
        theme,
        "deleteModelDialog",
        dark=True,
    )
    _click_quick_item(window, "deleteModelDialogRejectButton")
    assert delete_dialog.property("visible") is False
    assert error_dialog.property("visible") is False

    _open_dialog(delete_dialog)
    _click_quick_item(window, "deleteModelDialogAcceptButton")
    assert delete_dialog.property("visible") is False
    assert error_dialog.property("visible") is True
    assert "当前模型没有可删除的本地文件" in error_dialog.property(
        "errorMessage"
    )
    _assert_prism_dialog_palette(
        window,
        theme,
        "errorDialog",
        dark=True,
    )
    _click_quick_item(window, "errorDialogAcceptButton")
    assert error_dialog.property("visible") is False

    controller.setTheme("light")
    app.processEvents()
    assert theme.property("dark") is False
    for dialog, surface_name, close_button in (
        (create_dialog, "createProfileDialog", "createProfileDialogRejectButton"),
        (delete_dialog, "deleteModelDialog", "deleteModelDialogRejectButton"),
    ):
        _open_dialog(dialog)
        _assert_prism_dialog_palette(
            window,
            theme,
            surface_name,
            dark=False,
        )
        _click_quick_item(window, close_button)

    controller.reportHostError("浅色错误", "浅色主题仍使用 Prism 弹窗")
    app.processEvents()
    assert error_dialog.property("visible") is True
    _assert_prism_dialog_palette(
        window,
        theme,
        "errorDialog",
        dark=False,
    )
    _click_quick_item(window, "errorDialogAcceptButton")
    host.shutdown()


def test_real_number_steppers_stay_compact_in_wide_panels(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    window = host.window
    assert window is not None
    window.resize(1600, 900)
    app.processEvents()
    settings_panel = _find_quick_item(window, "settingsPrimaryPanel")
    theme = window.findChild(QObject, "prismTheme")
    assert settings_panel is not None
    assert theme is not None and theme.property("refraStyle") is True
    assert window.width() == 1600

    for page in ("CAPTURE", "TRANSLATION", "SETTINGS"):
        controller.setPage(page)
        app.processEvents()
    _wait_for_page_layout(window, settings_panel, app)

    steppers = [
        item
        for item in window.findChildren(QObject)
        if item.metaObject().indexOfProperty("compactWidth") >= 0
    ]
    assert len(steppers) == 13
    assert float(settings_panel.property("width")) > 600
    assert float(settings_panel.property("width")) > 3 * max(
        float(stepper.property("compactWidth")) for stepper in steppers
    )
    detailed_steppers = []
    for stepper in steppers:
        width = float(stepper.property("width"))
        compact_width = float(stepper.property("compactWidth"))
        if str(stepper.property("settingKey")).startswith("capture-"):
            assert stepper.property("compact") is True
            assert compact_width == 144
        else:
            assert stepper.property("compact") is False
            assert compact_width in {176.0, 200.0}
        if stepper.property("detailed") is True:
            detailed_steppers.append(stepper)
            assert width > compact_width
            parent = stepper.parentItem()
            assert parent is not None
            origin = stepper.mapToItem(parent, QPointF(0, 0))
            assert origin.x() >= -0.5
            assert origin.x() + width <= parent.width() + 0.5
            title = stepper.findChild(QObject, "numberStepperRowTitle")
            assert title is not None
            assert title.property("text") == stepper.property("rowTitle")
            value = int(stepper.property("value"))
            assert int(stepper.property("minimum")) <= value <= int(stepper.property("maximum"))
        else:
            assert width == compact_width

    assert detailed_steppers
    calibration_stepper = window.findChild(QObject, "settingsCalibrationStepper")
    assert calibration_stepper is not None and calibration_stepper.isVisible()
    calibration_title = calibration_stepper.findChild(QObject, "numberStepperRowTitle")
    assert calibration_title is not None and calibration_title.isVisible()
    assert calibration_title.property("text") == "画面变化轮询"
    increase = calibration_stepper.findChild(QObject, "numberStepperIncrease")
    assert increase is not None and increase.isVisible()
    before = controller.changePollFps
    increase_point = increase.mapToScene(
        QPointF(increase.width() / 2, increase.height() / 2),
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=increase_point)
    app.processEvents()
    assert controller.changePollFps == before + 1

    window.resize(980, 700)
    controller.setReducedMotion(True)
    window.update()
    QTest.qWait(20)
    app.processEvents()
    page_expectations = (
        ("CAPTURE", "captureSecondaryPanel", 4),
        ("TRANSLATION", "translationSecondaryPanel", 2),
        ("SETTINGS", "settingsPrimaryPanel", 6),
    )

    def scroll_stepper_into_view(panel: QQuickItem, stepper: QQuickItem) -> None:
        ancestor = stepper.parentItem()
        flickable = None
        while ancestor is not None and ancestor is not panel:
            if (
                ancestor.metaObject().indexOfProperty("contentY") >= 0
                and ancestor.metaObject().indexOfProperty("contentHeight") >= 0
            ):
                flickable = ancestor
                break
            ancestor = ancestor.parentItem()
        if flickable is None:
            return
        stepper_in_view = stepper.mapToItem(flickable, QPointF(0, 0))
        target_content_y = float(flickable.property("contentY"))
        if stepper_in_view.y() < 0:
            target_content_y += stepper_in_view.y()
        elif (
            stepper_in_view.y() + float(stepper.property("height"))
            > flickable.property("height")
        ):
            target_content_y += (
                stepper_in_view.y()
                + float(stepper.property("height"))
                - float(flickable.property("height"))
            )
        maximum_content_y = max(
            0.0,
            float(flickable.property("contentHeight"))
            - float(flickable.property("height")),
        )
        flickable.setProperty(
            "contentY",
            max(0.0, min(maximum_content_y, target_content_y)),
        )
        app.processEvents()

    def assert_stepper_geometry(panel: QQuickItem, stepper: QQuickItem) -> None:
        scroll_stepper_into_view(panel, stepper)
        panel_origin = panel.mapToScene(QPointF(0, 0))
        panel_right = panel_origin.x() + float(panel.property("width"))
        panel_bottom = panel_origin.y() + float(panel.property("height"))
        stepper_origin = stepper.mapToScene(QPointF(0, 0))
        stepper_right = stepper_origin.x() + float(stepper.property("width"))
        stepper_bottom = stepper_origin.y() + float(stepper.property("height"))
        assert stepper_origin.x() >= panel_origin.x() - 0.5
        assert stepper_origin.y() >= panel_origin.y() - 0.5
        assert stepper_right <= panel_right + 0.5
        assert stepper_bottom <= panel_bottom + 0.5

        decrease = stepper.findChild(QObject, "numberStepperDecrease")
        editor = stepper.findChild(QObject, "numberStepperEditor")
        suffix = stepper.findChild(QObject, "numberStepperSuffix")
        increase = stepper.findChild(QObject, "numberStepperIncrease")
        assert decrease is not None
        assert editor is not None
        assert suffix is not None
        assert increase is not None
        ordered_children = [decrease, editor, increase]
        child_rects = []
        for child in ordered_children:
            child_origin = child.mapToItem(stepper, QPointF(0, 0))
            child_rect = (
                child_origin.x(),
                child_origin.y(),
                float(child.property("width")),
                float(child.property("height")),
            )
            child_rects.append(child_rect)
            assert child_rect[0] >= -0.5
            assert child_rect[1] >= -0.5
            assert child_rect[0] + child_rect[2] <= stepper.property("width") + 0.5
            assert child_rect[1] + child_rect[3] <= stepper.property("height") + 0.5
        for left_rect, right_rect in zip(child_rects, child_rects[1:]):
            assert left_rect[0] + left_rect[2] <= right_rect[0] + 0.5

        decrease_rect, editor_rect, increase_rect = child_rects
        assert abs(decrease_rect[2] - increase_rect[2]) <= 0.5
        left_gap = editor_rect[0] - (decrease_rect[0] + decrease_rect[2])
        right_gap = increase_rect[0] - (editor_rect[0] + editor_rect[2])
        assert abs(left_gap - right_gap) <= 0.5
        assert abs(
            decrease_rect[0]
            - (stepper.property("width") - increase_rect[0] - increase_rect[2])
        ) <= 1.0

        if stepper.property("suffix") and not stepper.property("compact"):
            assert suffix.property("visible") is True
            assert suffix.parentItem() == editor
            suffix_origin = suffix.mapToItem(editor, QPointF(0, 0))
            assert suffix_origin.x() >= -0.5
            assert suffix_origin.y() >= -0.5
            assert (
                suffix_origin.x() + float(suffix.property("width"))
                <= editor.property("width") + 0.5
            )
            assert (
                suffix_origin.y() + float(suffix.property("height"))
                <= editor.property("height") + 0.5
            )

    for page, panel_name, expected_count in page_expectations:
        controller.setPage(page)
        window.update()
        QTest.qWait(20)
        app.processEvents()
        panel = _find_quick_item(window, panel_name)
        assert panel is not None
        page_steppers = [
            item
            for item in panel.findChildren(QObject)
            if item.metaObject().indexOfProperty("compactWidth") >= 0
        ]
        assert len(page_steppers) == expected_count
        expected_names = {
            str(stepper.property("accessibleName")) for stepper in page_steppers
        }
        assert len(expected_names) == expected_count
        checked_names = set()
        visibility_states = (
            ("external", "builtin")
            if page == "TRANSLATION"
            else (True, False) if page == "SETTINGS" else (None,)
        )
        for state in visibility_states:
            if page == "TRANSLATION":
                controller.setBackend(state)
            elif page == "SETTINGS":
                controller.setDynamicRoiEnabled(state)
            window.update()
            QTest.qWait(20)
            app.processEvents()
            for stepper in page_steppers:
                if stepper.property("visible") is not True:
                    continue
                assert_stepper_geometry(panel, stepper)
                checked_names.add(str(stepper.property("accessibleName")))
        assert checked_names == expected_names
    host.shutdown()


@pytest.mark.parametrize("window_size", [(980, 700), (1280, 820)])
def test_real_dohna_slanted_menu_and_parallel_buttons_keep_hit_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window_size: tuple[int, int],
) -> None:
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        pytest.skip("Dohna menu geometry is verified with native Windows rendering")
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(config_path, load_config(config_path), "game", display_name="测试游戏")
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_DOHNA)
    controller.setTheme("light")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        window = host.window
        assert window is not None
        window.resize(max(window_size[0], window.minimumWidth()), window_size[1])
        host.show()
        QTest.qWait(80)
        theme = window.findChild(QObject, "dohnaTheme")
        pages = ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS")
        menu_edges = []
        for index, page in enumerate(pages):
            button = _find_quick_item(window, f"navigationButton{index}")
            assert button is not None
            label = button.findChild(QQuickItem, "prismButtonLabel")
            text = label.property("text")
            assert page in text and re.search(r"[\u4e00-\u9fff]", text)
            assert "\n" not in text
            assert label.property("lineCount") == 1
            assert label.property("truncated") is False, text
            available_text_width = label.width() - label.property("leftPadding") - label.property("rightPadding")
            assert label.property("contentWidth") <= available_text_width + 1
            fitted_font = label.property("font")
            fitted_font.setPixelSize(label.property("fontInfo").property("pixelSize").toInt())
            glyph_bounds = QFontMetricsF(fitted_font).tightBoundingRect(text)
            # Measure visible glyphs, not the font's extra line spacing.  The
            # thin strips must not vertically shrink their existing lettering.
            assert 0.79 <= glyph_bounds.height() / button.height() <= 0.86
            assert fitted_font.pixelSize() == 24
            assert 24 <= button.height() < 40
            baseline = label.y() + label.property("baselineOffset")
            assert baseline + glyph_bounds.top() >= -1
            assert baseline + glyph_bounds.bottom() <= button.height() + 1
            label_left = label.mapToScene(QPointF(0, 0))
            label_right = label.mapToScene(QPointF(label.width(), 0))
            assert label_right.y() > label_left.y() + 10
            rail = button.parentItem().parentItem().parentItem()
            assert rail.property("clip") is True
            rail_left = rail.mapToScene(QPointF(0, 0)).x()
            rail_right = rail_left + rail.width()
            assert rail.width() >= 300
            assert window.width() - rail.width() >= 802
            middle_x = (rail_left + rail_right) / 2
            slope = math.tan(math.radians(button.property("rotation")))
            top = button.mapToScene(QPointF(0, 0))
            bottom = button.mapToScene(QPointF(0, button.height()))
            menu_edges.append((top.y() + (middle_x - top.x()) * slope,
                               bottom.y() + (middle_x - bottom.x()) * slope))
            # Both sloping edges span past the sidebar, so clipping leaves
            # straight, flush ends rather than exposed corners or side gaps.
            for y in (0, button.height()):
                left = button.mapToScene(QPointF(0, y))
                right = button.mapToScene(QPointF(button.width(), y))
                assert left.x() < rail_left
                assert right.x() > rail_right
                assert 0 <= left.y() <= window.height()
                assert 0 <= right.y() <= window.height()
            # The extended strips respond even at the visible sidebar edges.
            start = button.mapToScene(QPointF(0, button.height() / 2))
            end = button.mapToScene(QPointF(button.width(), button.height() / 2))
            for x in (rail_left + 1, rail_right - 1):
                y = start.y() + (x - start.x()) * (end.y() - start.y()) / (end.x() - start.x())
                point = QPointF(x, y)
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point.toPoint())
                app.processEvents()
                assert controller.currentPage == page
            path = button.findChild(QObject, "prismNavigationDohnaPath")
            assert path.property("strokeWidth") == 0
            assert QColor(path.property("fillColor")) == QColor(theme.property("violet"))
            assert QColor(label.property("color")) == QColor(theme.property("ink"))

        # Preserve the actual space between slanted edges, including layout
        # rounding, rather than retaining only the unrotated layout spacing.
        gaps = [current[0] - previous[1] for previous, current in zip(menu_edges, menu_edges[1:])]
        original_gap = 60 - 50 / math.cos(math.radians(12))
        assert all(abs(gap - original_gap) <= 0.5 for gap in gaps)

        capture_button = _find_quick_item(window, "navigationButton1")
        capture_button.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Space)
        app.processEvents()
        assert controller.currentPage == "CAPTURE"

        def assert_parallel_sides(path: QObject) -> list[tuple[float, float]]:
            assert path is not None
            top_left = (float(path.property("startX")), float(path.property("startY")))
            points = [
                (float(line.property("x")), float(line.property("y")))
                for line in path.children()
                if line.metaObject().className().startswith("QQuickPathLine")
            ]
            assert len(points) == 4
            top_right, bottom_right, bottom_left, close = points
            assert close == pytest.approx(top_left)
            assert bottom_left[0] > top_left[0]
            assert bottom_right[0] - top_right[0] == pytest.approx(bottom_left[0] - top_left[0])
            assert bottom_right[1] - top_right[1] == pytest.approx(bottom_left[1] - top_left[1])
            assert top_right[0] - top_left[0] == pytest.approx(bottom_right[0] - bottom_left[0])
            return points

        for name in ("saveAllButton", "startLiveButton", "captureScanAction", "captureCustomAction"):
            button = window.findChild(QQuickItem, name)
            assert button is not None
            assert button.property("rotation") == 0
            face = assert_parallel_sides(button.findChild(QObject, "prismButtonDohnaPath"))
            shadow = assert_parallel_sides(button.findChild(QObject, "prismButtonDohnaShadowPath"))
            assert face == shadow

        panel = window.findChild(QObject, "captureSecondaryPanel")
        for path in panel.findChildren(QObject, "prismButtonDohnaGroupPath"):
            assert_parallel_sides(path)
        for path in panel.findChildren(QObject, "prismButtonDohnaGroupShadowPath"):
            assert_parallel_sides(path)

        controller.setSkin(SKIN_PRISM)
        app.processEvents()
        theme = _theme_for_skin(window, SKIN_PRISM)
        assert theme is not None and theme.property("refraStyle") is True
        p3_sidebar_buttons = [
            _find_quick_item(window, f"navigationButton{i}")
            for i in range(len(pages))
        ]
        assert all(button is not None and button.isVisible() for button in p3_sidebar_buttons)
        p3_rail = p3_sidebar_buttons[0].parentItem().parentItem().parentItem()
        assert p3_rail.property("clip") is False
        for index, button in enumerate(p3_sidebar_buttons):
            expected_tilt = -4.0 if index % 2 == 0 else -6.2
            assert button.property("rotation") == pytest.approx(expected_tilt)
            assert button.height() == 66

        sidebar_target = p3_sidebar_buttons[-1]
        sidebar_point = sidebar_target.mapToScene(
            QPointF(sidebar_target.width() / 2, sidebar_target.height() / 2),
        ).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=sidebar_point)
        app.processEvents()
        assert controller.currentPage == "SETTINGS"

        controller.setPage("HOME")
        app.processEvents()
        hero_menu = _find_quick_item(window, "refraDarkNavigationMenu")
        assert hero_menu is not None and hero_menu.isVisible()
        assert hero_menu.property("clip") is False
        for index, page in enumerate(pages):
            controller.setPage("HOME")
            app.processEvents()
            hero_button = _find_quick_item(window, f"refraDarkNavigationButton{index}")
            assert hero_button is not None and hero_button.isVisible()
            expected_tilt = -3.8 if index % 2 == 0 else -5.7
            assert hero_button.property("rotation") == pytest.approx(expected_tilt)
            assert 70 <= hero_button.height() <= 92
            hero_center = hero_button.mapToScene(
                QPointF(hero_button.width() / 2, hero_button.height() / 2),
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=hero_center)
            app.processEvents()
            assert controller.currentPage == page
    finally:
        host.shutdown()


def test_real_dohna_number_stepper_uses_one_frame_at_bounds_and_input(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_DOHNA)
    controller.setReducedMotion(True)
    controller.setCaptureRegion(10, 20, 640, 180)
    controller.setPage("CAPTURE")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "dohnaTheme")
    capture_panel = _find_quick_item(window, "captureSecondaryPanel")
    assert capture_panel is not None
    assert theme is not None
    _wait_for_page_layout(window, capture_panel, app)
    stepper = next(
        item
        for item in capture_panel.findChildren(QObject)
        if item.metaObject().indexOfProperty("compactWidth") >= 0
        and item.property("settingKey") == "capture-left"
    )
    assert stepper is not None
    decrease = stepper.findChild(QObject, "numberStepperDecrease")
    increase = stepper.findChild(QObject, "numberStepperIncrease")
    editor = stepper.findChild(QObject, "numberStepperEditor")
    suffix = stepper.findChild(QObject, "numberStepperSuffix")
    group_surface = stepper.findChild(QObject, "prismButtonDohnaGroupSurface")
    group_shadow = stepper.findChild(QObject, "prismButtonDohnaGroupShadow")
    group_cut = stepper.findChild(QObject, "prismButtonDohnaCut")
    assert decrease is not None
    assert increase is not None
    assert editor is not None
    assert suffix is not None
    assert group_surface is not None
    assert group_shadow is not None
    assert group_cut is not None
    assert stepper.property("compact") is True
    assert stepper.property("width") == 144
    assert suffix.property("visible") is False
    assert group_surface.property("visible") is True
    assert group_shadow.property("visible") is True
    assert group_surface.property("width") == stepper.property("width")
    assert group_surface.property("height") == stepper.property("height")
    assert group_cut.property("visible") is False
    group_path = group_surface.findChild(QObject, "prismButtonDohnaGroupPath")
    assert group_path is not None
    increase.forceActiveFocus()
    app.processEvents()
    assert increase.property("activeFocus") is True
    assert QColor(group_path.property("fillColor")) == QColor(theme.property("violet"))

    controller.setCaptureRegion(0, 20, 640, 180)
    app.processEvents()
    assert stepper.property("value") == 0
    assert decrease.property("enabled") is False
    assert group_surface.property("visible") is True

    editor.forceActiveFocus()
    maximum_left = controller.captureDisplayWidth - controller.captureWidth
    editor.setProperty("text", str(maximum_left))
    QTest.keyClick(window, Qt.Key.Key_Return)
    app.processEvents()
    assert controller.captureLeft == maximum_left
    assert stepper.property("value") == maximum_left
    assert increase.property("enabled") is False
    assert group_surface.property("visible") is True

    maximum_point = increase.mapToScene(
        QPointF(increase.width() / 2, increase.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=maximum_point)
    app.processEvents()
    assert controller.captureLeft == maximum_left

    controller.setPage("SETTINGS")
    app.processEvents()
    normal_stepper = window.findChild(QObject, "settingsCalibrationStepper")
    assert normal_stepper is not None
    assert normal_stepper.property("compact") is False
    assert normal_stepper.property("width") == 200
    normal_suffix = normal_stepper.findChild(QObject, "numberStepperSuffix")
    normal_surface = normal_stepper.findChild(
        QObject,
        "prismButtonDohnaGroupSurface",
    )
    assert normal_suffix is not None
    assert normal_suffix.property("visible") is True
    assert normal_surface is not None
    assert normal_surface.property("visible") is True

    controller.useFullScreen()
    controller.setPage("CAPTURE")
    app.processEvents()
    assert stepper.property("enabled") is False
    assert group_surface.property("visible") is True
    assert float(group_surface.property("opacity")) < 1
    host.shutdown()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("window_size", [(980, 700), (1280, 820), (1600, 900)])
def test_capture_fields_use_two_rows_and_keep_geometry_clear(
    tmp_path: Path,
    theme_name: str,
    window_size: tuple[int, int],
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    controller.setCaptureRegion(30, 40, 640, 180)
    controller.setPage("CAPTURE")
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        window = host.window
        assert window is not None
        window.resize(*window_size)
        panel = _find_quick_item(window, "captureSecondaryPanel")
        assert panel is not None
        _wait_for_page_layout(window, panel, app)
        steppers = {
            str(item.property("settingKey")): item
            for item in panel.findChildren(QQuickItem)
            if item.metaObject().indexOfProperty("compactWidth") >= 0
        }
        assert set(steppers) == {
            "capture-left", "capture-top", "capture-width", "capture-height",
        }
        origins = {
            key: stepper.mapToScene(QPointF(0, 0))
            for key, stepper in steppers.items()
        }
        left = origins["capture-left"]
        top = origins["capture-top"]
        width = origins["capture-width"]
        height = origins["capture-height"]
        assert math.isclose(left.y(), top.y(), abs_tol=0.5)
        assert math.isclose(width.y(), height.y(), abs_tol=0.5)
        assert math.isclose(left.x(), width.x(), abs_tol=0.5)
        assert math.isclose(top.x(), height.x(), abs_tol=0.5)
        assert left.x() + steppers["capture-left"].width() < top.x()
        assert left.y() + steppers["capture-left"].height() < width.y()

        panel_origin = panel.mapToScene(QPointF(0, 0))
        scroll = _find_quick_item(panel, "captureSettingsScroll")
        assert scroll is not None
        bar = _find_quick_item(scroll, "prismScrollBar")
        assert bar is not None
        assert bar.isVisible() == (float(scroll.property("contentHeight")) > scroll.height())
        lane_left = bar.mapToScene(QPointF(0, 0)).x()
        content = scroll.property("contentItem")
        form = next(child for child in content.childItems() if child.width() > 30)
        for child in form.childItems():
            if child.isVisible():
                origin = child.mapToScene(QPointF(0, 0))
                assert origin.x() + child.width() <= lane_left - 7.5
        for key, stepper in steppers.items():
            origin = origins[key]
            assert stepper.width() == 144
            assert origin.x() >= panel_origin.x()
            assert origin.y() >= panel_origin.y()
            assert origin.x() + stepper.width() <= panel_origin.x() + panel.width()
            assert origin.x() + stepper.width() <= lane_left - 7.5
            assert origin.y() + stepper.height() <= panel_origin.y() + panel.height()
            editor = stepper.findChild(QQuickItem, "numberStepperEditor")
            suffix = stepper.findChild(QQuickItem, "numberStepperSuffix")
            assert editor is not None
            assert suffix is not None
            editor.forceActiveFocus()
            editor.setProperty("text", "32768")
            app.processEvents()
            # Windows' offscreen backend can report synthetic glyph widths
            # when no system font resolves; keep geometry and input checks.
            if QFontInfo(editor.property("font")).pixelSize() >= 0:
                assert (
                    float(editor.property("contentWidth"))
                    + float(editor.property("leftPadding"))
                    + float(editor.property("rightPadding"))
                    <= editor.width()
                )
            assert suffix.property("visible") is False
            editor.setProperty("text", str(stepper.property("value")))

        # Click each narrow button and verify it still edits the correct field.
        controller.setCaptureRegion(30, 40, 640, 180)
        app.processEvents()
        for stepper in steppers.values():
            original = int(stepper.property("value"))
            for button_name, expected in (
                ("numberStepperIncrease", original + 10),
                ("numberStepperDecrease", original),
            ):
                button = stepper.findChild(QQuickItem, button_name)
                assert button is not None
                point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point.toPoint())
                app.processEvents()
                assert stepper.property("value") == expected

        theme = window.findChild(QObject, "prismTheme")
        surface = _find_quick_item(window, "captureGeometrySurface")
        outline = _find_quick_item(window, "captureDisplayOutline")
        preview = _find_quick_item(window, "captureRegionPreview")
        assert all(item is not None for item in (theme, surface, outline, preview))
        assert surface.property("color") == theme.property("panel")
        assert surface.property("color").alphaF() == 1
        assert QQmlProperty(outline, "border.color").read() == theme.property("line")
        assert QQmlProperty(preview, "border.color").read() == theme.property("accent")
        assert QQmlProperty(preview, "border.width").read() == 2
        assert preview.property("visible") is True
        assert window.findChild(QObject, "opticalStage") is None

        controller.useFullScreen()
        app.processEvents()
        assert preview.property("visible") is False
        assert all(stepper.property("enabled") is False for stepper in steppers.values())
        controller.setPage("HOME")
        app.processEvents()
        assert window.findChild(QObject, "opticalStage") is None
    finally:
        host.shutdown()


def test_capture_geometry_projects_bottom_right_region_against_full_display(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    display_width = controller.captureDisplayWidth
    display_height = controller.captureDisplayHeight
    assert display_width > 0
    assert display_height > 0
    region_width = max(1, display_width // 5)
    region_height = max(1, display_height // 5)
    controller.setCaptureRegion(
        display_width - region_width,
        display_height - region_height,
        region_width,
        region_height,
    )
    controller.setPage("CAPTURE")

    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    window = host.window
    assert window is not None
    window.update()
    QTest.qWait(20)
    app.processEvents()

    stage = _find_quick_item(window, "captureGeometryStage")
    preview = _find_quick_item(window, "captureRegionPreview")
    assert stage is not None
    assert preview is not None
    assert preview.property("visible") is True
    stage_width = float(stage.property("width"))
    stage_height = float(stage.property("height"))
    preview_x = float(preview.property("x"))
    preview_y = float(preview.property("y"))
    preview_width = float(preview.property("width"))
    preview_height = float(preview.property("height"))

    assert math.isclose(preview_width, stage_width / 5, abs_tol=0.5)
    assert math.isclose(preview_height, stage_height / 5, abs_tol=0.5)
    assert math.isclose(preview_x + preview_width, stage_width, abs_tol=0.5)
    assert math.isclose(preview_y + preview_height, stage_height, abs_tol=0.5)
    assert preview_x > stage_width * 0.75
    assert preview_y > stage_height * 0.75
    host.shutdown()


def test_real_overlay_slider_updates_draft_and_profile_apply_persists_it(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n[preview]\noverlay_opacity = 0.375\n",
        encoding="utf-8",
    )
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            (
                SnapshotEntry(
                    "overlay-preview",
                    0,
                    "原文",
                    "示例译文",
                    0.9,
                    (100, 120, 500, 220),
                ),
            ),
            (),
            ocr_peak_seconds=None,
            llm_peak_seconds=None,
            canvas_size=(800, 600),
        ),
    )
    configured = load_config(config_path).preview.overlay_opacity
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    controller.setPage("OVERLAY")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = _active_theme(window)
    assert theme is not None
    window.update()
    QTest.qWait(20)
    app.processEvents()
    slider = _find_quick_item(window, "overlayProjectionAction")
    percentage = window.findChild(QObject, "overlayOpacityValue")
    preview_entry = _find_quick_item(window, "overlayLastRunEntry")
    assert slider is not None
    assert percentage is not None
    assert preview_entry is not None
    assert _find_quick_item(window, "overlayCanvasMask") is None
    assert float(slider.property("from")) == 0.0
    assert float(slider.property("to")) == 1.0
    assert float(slider.property("stepSize")) == 0.01
    assert float(slider.property("value")) == configured
    assert percentage.property("text") == f"{round(configured * 100)}%"
    assert QColor(percentage.property("color")) == QColor(
        theme.property("accentText"),
    )
    assert QColor(theme.property("accentText")) != QColor(theme.property("accent"))
    assert float(preview_entry.property("maskOpacity")) == configured
    assert controller.settingsDirty is False

    motion_feedback = window.findChild(QObject, "prismMotionFeedback")
    feedback_layer = window.findChild(QObject, "prismFeedbackLayer")
    action_rule = window.findChild(QObject, "prismActionFeedbackRule")
    assert motion_feedback is not None
    assert feedback_layer is not None
    assert action_rule is not None
    action_sequence = int(motion_feedback.property("actionSequence"))
    start_ratio = float(slider.property("visualPosition"))
    start = _slider_scene_point(slider, start_ratio)
    end_ratio = 0.73
    end = _slider_scene_point(slider, end_ratio)
    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    assert int(motion_feedback.property("actionSequence")) == action_sequence

    draft_samples = []
    for progress in (0.25, 0.5, 0.75, 1.0):
        position = _slider_scene_point(
            slider,
            start_ratio + (end_ratio - start_ratio) * progress,
        )
        QTest.mouseMove(window, position, delay=10)
        app.processEvents()
        draft_samples.append(controller.overlayOpacity)
        assert float(preview_entry.property("maskOpacity")) == controller.overlayOpacity
        assert int(motion_feedback.property("actionSequence")) == action_sequence

    assert draft_samples == sorted(draft_samples)
    assert len(set(draft_samples)) == len(draft_samples)
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        end,
    )
    app.processEvents()
    assert int(motion_feedback.property("actionSequence")) == action_sequence + 1
    assert motion_feedback.property("actionKind") == "projection"
    assert motion_feedback.property("actionPulseRunning") is True
    assert feedback_layer.property("visible") is True
    QTest.qWait(160)
    app.processEvents()
    assert action_rule.property("visible") is True
    assert float(action_rule.property("width")) > 0

    draft = controller.overlayOpacity
    assert draft > configured
    assert float(slider.property("from")) <= draft <= float(slider.property("to"))
    assert float(slider.property("value")) == draft
    assert percentage.property("text") == f"{round(draft * 100)}%"
    assert QColor(percentage.property("color")) == QColor(
        theme.property("accentText"),
    )
    assert controller.settingsDirty is True
    assert load_config(config_path).preview.overlay_opacity == configured
    assert motion_feedback.property("actionKind") == "projection"

    controller.setOverlayOpacity(0.23)
    app.processEvents()
    draft = controller.overlayOpacity
    assert draft == 0.23
    assert float(slider.property("value")) == 0.23
    assert percentage.property("text") == "23%"
    assert float(preview_entry.property("maskOpacity")) == 0.23
    assert int(motion_feedback.property("actionSequence")) == action_sequence + 1

    _click_quick_item(window, _workbench_save_button_name(window))
    assert controller.settingsDirty is False
    machine = load_config(config_path)
    saved_profile = load_game_profile(config_path, machine, "game")
    assert machine.preview.overlay_opacity == configured
    assert apply_profile_runtime_settings(
        machine,
        saved_profile,
    ).preview.overlay_opacity == draft
    QTest.qWait(int(theme.property("actionMotion")) + 40)
    app.processEvents()
    assert motion_feedback.property("actionPulseRunning") is False
    assert action_rule.property("visible") is False
    assert feedback_layer.property("visible") is False
    host.shutdown()


def test_real_ocr_quality_slider_snaps_three_presets_and_keeps_merge_guard(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setDetectionQualityIndex(1)
    assert controller.saveRuntimeSettings() is True
    assert controller.settingsDirty is False
    controller.setPage("OCR")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    slider = _find_quick_item(window, "ocrQualitySlider")
    assert slider is not None
    assert float(slider.property("from")) == 0.0
    assert float(slider.property("to")) == 2.0
    assert float(slider.property("stepSize")) == 1.0
    initial_index = controller.detectionQualityIndex
    assert initial_index in (0, 1, 2)

    start = _slider_scene_point(slider, initial_index / 2)
    quality_position = _slider_scene_point(slider, 0.76)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(window, quality_position, delay=10)
    app.processEvents()
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        quality_position,
    )
    app.processEvents()

    assert controller.detectionQualityIndex == 2
    assert float(slider.property("value")) == 2.0
    assert controller.detectionQualitySummary.startswith("质量 · ")
    assert controller.settingsDirty is True

    low_position = _slider_scene_point(slider, 0.1)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, quality_position)
    QTest.mouseMove(window, low_position, delay=10)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, low_position)
    app.processEvents()
    assert controller.detectionQualityIndex == 0
    assert controller.textMergeAllowed is False
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
def test_real_slider_press_feedback_uses_skin_specific_accent(
    tmp_path: Path,
    skin: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setPage("OCR")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    slider = _find_quick_item(window, "ocrQualitySlider")
    theme = _theme_for_skin(window, skin)
    assert isinstance(slider, QQuickItem)
    assert theme is not None
    handle = slider.property("handle")
    assert isinstance(handle, QQuickItem)
    point = _slider_scene_point(slider, float(slider.property("visualPosition")))

    QTest.mouseMove(window, point)
    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    app.processEvents()
    assert slider.property("pressed") is True
    expected_pressed = QColor(
        theme.property("violet") if skin == SKIN_DOHNA else theme.property("accent")
    )
    assert QColor(handle.property("color")) == expected_pressed

    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    app.processEvents()
    assert slider.property("pressed") is False
    assert QColor(handle.property("color")) == QColor(
        theme.property("inkRaised")
    )
    host.shutdown()


def test_real_last_run_snapshot_renders_all_output_pages_in_minimum_window(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            tuple(
                SnapshotEntry(
                    f"track-{index}",
                    index,
                    f"原文 {index}",
                    "这是一段较长的上次运行译文，用于验证页面不会因为长文本而溢出。" * 2,
                    0.8,
                    (20, index * 45, 420, index * 45 + 35),
                )
                for index in range(3)
            ),
            tuple(CacheHit(f"缓存原文 {index}", 5 - index) for index in range(5)),
            ocr_peak_seconds=0.4,
            llm_peak_seconds=2.5,
            canvas_size=(800, 600),
        ),
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    qml_warnings: list[str] = []

    def create_engine(parent: QObject) -> QQmlApplicationEngine:
        engine = QQmlApplicationEngine(parent)
        engine.warnings.connect(
            lambda errors: qml_warnings.extend(error.toString() for error in errors)
        )
        return engine

    host = QmlWorkbenchHost(
        controller,
        application=app,
        engine_factory=create_engine,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "prismTheme")
    assert theme is not None
    accent_text = QColor(theme.property("accentText"))
    window.resize(980, 700)
    app.processEvents()
    assert window.width() >= 980
    assert window.height() >= 700

    home_summary = _find_quick_item(window, "refraDarkLastRunSummary")
    home_status = _find_quick_item(window, "refraDarkLastRunStatus")
    assert home_summary is not None and home_summary.isVisible()
    assert home_status is not None and home_status.isVisible()
    assert controller.lastRunAvailable is True
    assert home_status.property("text") == controller.lastRunStatus
    visible_summary_lines = {
        str(item.property("text"))
        for item in home_summary.findChildren(QQuickItem)
        if item.isVisible() and item.property("text") is not None
    }
    assert "OCR 400 ms  ·  LLM 2.50 s" in visible_summary_lines
    controller._live_process = SimpleNamespace(poll=lambda: None)
    controller._set_run_state("正在翻译", "success", True)
    app.processEvents()
    run_state = _find_quick_item(window, "refraDarkRunState")
    assert run_state is not None and run_state.isVisible()
    assert run_state.property("text") == "正在翻译"
    assert QColor(run_state.property("color")) == accent_text
    controller._live_process = None
    controller._set_run_state("待启动", "neutral", False)
    app.processEvents()

    controller.setPage("OCR")
    app.processEvents()
    ocr_list = window.findChild(QObject, "ocrLastRunList")
    assert ocr_list is not None
    assert ocr_list.property("visible") is True
    ocr_status = _visible_text_items(ocr_list, str(controller.lastRunStatus))
    assert len(ocr_status) == 1
    assert QColor(ocr_status[0].property("color")) == accent_text
    controller.setPage("TRANSLATION")
    app.processEvents()
    translation_list = window.findChild(QObject, "translationLastRunList")
    assert translation_list is not None
    assert translation_list.property("visible") is True
    translation_status = _visible_text_items(
        translation_list,
        str(controller.lastRunStatus),
    )
    assert len(translation_status) == 1
    assert QColor(translation_status[0].property("color")) == accent_text
    connection_label = _visible_text_items(window, "连接状态")
    assert len(connection_label) == 1
    assert QColor(connection_label[0].property("color")) == accent_text
    controller.setPage("OVERLAY")
    app.processEvents()
    controller.setOverlayOpacity(0.1)
    app.processEvents()
    canvas = window.findChild(QObject, "overlayLastRunCanvas")
    canvas_item = _find_quick_item(window, "overlayLastRunCanvas")
    drawn_canvas = _find_quick_item(window, "overlayCanvas")
    assert canvas is not None
    assert canvas_item is not None
    assert drawn_canvas is not None
    assert _find_quick_item(window, "overlayCanvasMask") is None
    _wait_for_page_layout(window, canvas_item, app)
    assert float(drawn_canvas.property("width")) <= float(canvas_item.property("width"))
    assert float(drawn_canvas.property("height")) <= float(canvas_item.property("height"))
    entries = _find_quick_items(window, "overlayLastRunEntry")
    assert len(entries) == 3
    canvas_width = float(drawn_canvas.property("width"))
    canvas_height = float(drawn_canvas.property("height"))
    for entry in entries:
        for name in ("x", "y", "width", "height"):
            value = float(entry.property(name))
            assert math.isfinite(value)
        assert float(entry.property("width")) > 0
        assert float(entry.property("height")) > 0
        assert 0 <= float(entry.property("x")) <= canvas_width
        assert 0 <= float(entry.property("y")) <= canvas_height
        assert float(entry.property("x")) + float(entry.property("width")) <= canvas_width + 1e-6
        assert float(entry.property("y")) + float(entry.property("height")) <= canvas_height + 1e-6
        assert math.isclose(
            float(entry.property("maskOpacity")),
            controller.overlayOpacity,
            abs_tol=1e-6,
        )
        background = entry.property("color")
        assert background.red() == 0
        assert background.green() == 0
        assert background.blue() == 0
        assert math.isclose(
            background.alphaF(),
            controller.overlayOpacity,
            abs_tol=1 / 255,
        )
        frame_color = QQmlProperty(entry, "border.color").read()
        assert 0 < frame_color.alphaF() <= 0.25
    controller.setOverlayOpacity(0.8)
    app.processEvents()
    assert all(
        math.isclose(
            float(entry.property("maskOpacity")),
            0.8,
            abs_tol=1e-6,
        )
        for entry in entries
    )
    assert qml_warnings == []
    controller.setPage("CACHE")
    app.processEvents()
    cache_hits = window.findChild(QObject, "cacheLastRunHits")
    cache_summary = _find_quick_item(window, "cacheSummaryMetrics")
    cache_hint = _find_quick_item(window, "cacheSummarySourceHint")
    assert cache_hits is not None
    assert cache_summary is not None
    assert cache_hint is not None
    assert cache_hits.property("visible") is True
    assert cache_hint.property("text") == (
        "上方为 Profile SQLite 累计统计；上次运行命中列表仅代表最近一次运行。"
    )
    assert cache_summary.mapToItem(cache_hits, QPointF(0, 0)).y() < 0
    unavailable_titles = _find_quick_items(window, "unavailableStateTitle")
    assert not any(
        title.property("text") == "暂不支持浏览自动缓存明细"
        for title in unavailable_titles
    )
    corrections = _find_quick_item(window, "correctionsEditor")
    assert corrections is not None and corrections.isVisible()

    window.resize(1280, 820)
    controller.setPage("HOME")
    app.processEvents()
    home = _find_quick_item(window, "refraDarkHome")
    assert home is not None and home.isVisible()
    host.shutdown()


@pytest.mark.parametrize("skin,theme_name", [
    (SKIN_PRISM, "dark"), (SKIN_PRISM, "light"), (SKIN_DOHNA, "light"),
])
def test_ocr_scrollbar_has_clear_lane_and_drags_content(
    tmp_path: Path, skin: str, theme_name: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(config_path, load_config(config_path), "scroll-test")
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    controller.setPage("OCR")
    host = QmlWorkbenchHost(controller, application=app)
    try:
        window = host.window
        assert window is not None
        window.resize(max(980, window.minimumWidth()), 700)
        host.show()
        panel = _find_quick_item(window, "ocrSecondaryPanel")
        scroll = _find_quick_item(window, "ocrSettingsScroll")
        assert panel is not None and scroll is not None
        _wait_for_page_layout(window, panel, app)
        bar = _find_quick_item(scroll, "prismScrollBar")
        assert bar is not None and bar.isVisible()
        assert scroll.property("contentHeight") > scroll.height()
        content = scroll.property("contentItem")
        form = next(child for child in content.childItems() if child.width() > 30)
        lane_left = bar.mapToItem(scroll, QPointF(0, 0)).x()
        assert form.width() <= lane_left - 8 + 0.5
        for child in form.childItems():
            if child.isVisible():
                origin = child.mapToItem(scroll, QPointF(0, 0))
                assert origin.x() + child.width() <= lane_left - 7.5
        thumb = _find_quick_item(bar, "prismScrollThumb")
        assert thumb is not None
        assert thumb.property("radius") == 0
        _assert_scroll_thumb_inside_track(bar)
        start = thumb.mapToScene(QPointF(thumb.width() / 2, thumb.height() / 2)).toPoint()
        QTest.mouseMove(window, start)
        QTest.qWait(30)
        assert bar.property("hovered")
        theme = bar.property("theme")
        assert thumb.property("color") == theme.property("accent")
        _assert_scroll_thumb_inside_track(bar)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window, start + QPoint(0, 45), delay=30)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=start + QPoint(0, 45))
        app.processEvents()
        assert scroll.property("contentY") > 0
        assert bar.property("position") > 0
        _assert_scroll_thumb_inside_track(bar)
    finally:
        host.shutdown()


@pytest.mark.parametrize("theme_name", ("dark", "light"))
def test_nearly_fitting_pages_compact_spacing_before_requiring_scroll(
    tmp_path: Path,
    theme_name: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            (SnapshotEntry("track", 0, "原文", "译文", 0.9, (20, 40, 420, 75)),),
            (),
            ocr_peak_seconds=0.4,
            llm_peak_seconds=2.5,
        ),
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        window = host.window
        assert window is not None
        theme = window.findChild(QObject, "prismTheme")
        assert theme is not None
        if theme.property("refraStyle") is True:
            dark_home = _find_quick_item(window, "refraDarkHome")
            stage = _find_quick_item(window, "refraDarkHomeStage")
            status_band = _find_quick_item(window, "refraDarkHomeStatusBand")
            actions = _find_quick_item(window, "refraDarkHomeActions")
            hero_image = _find_quick_item(window, "refraDarkHeroImage")
            assert all(item is not None for item in (dark_home, stage, status_band, actions, hero_image))
            for size in ((980, 700), (1100, 760), (1280, 820)):
                window.resize(*size)
                _wait_for_page_layout(window, dark_home, app)
                assert dark_home.isEnabled()
                for item in (stage, status_band, actions):
                    assert item.isVisible() and item.height() > 0
                    origin = item.mapToItem(dark_home, QPointF(0, 0))
                    assert origin.x() >= -0.5 and origin.y() >= -0.5
                    assert origin.x() + item.width() <= dark_home.width() + 0.5
                    assert origin.y() + item.height() <= dark_home.height() + 0.5
                assert hero_image.isVisible()
                assert hero_image.width() > 0 and hero_image.height() > 0
                assert hero_image.property("source").toString().endswith(
                    "refra-hero-dark.png"
                )
                hero_image_ready = QQmlExpression(
                    host._engine.rootContext(), hero_image, "Number(status) === 1"
                )
                ready = hero_image_ready.evaluate()
                assert not hero_image_ready.hasError()
                assert ready == (True, False)
                assert _find_quick_item(window, "refraDarkProfileSummary").isVisible()
                for index in range(7):
                    button = _find_quick_item(window, f"refraDarkNavigationButton{index}")
                    assert button is not None and button.isVisible() and button.width() > 0
        else:
            home_panel = _find_quick_item(window, "homePrimaryPanel")
            home_scroll = _find_quick_item(window, "homePrimaryScroll")
            hero = _find_quick_item(window, "homeRunHero")
            footnote = _find_quick_item(window, "homeLastRunFootnote")
            assert all(item is not None for item in (home_panel, home_scroll, hero, footnote))
            for size in ((980, 700), (1100, 760), (1280, 820)):
                window.resize(*size)
                _wait_for_page_layout(window, home_panel, app)
                assert home_scroll.property("contentHeight") <= home_scroll.height()
                assert home_scroll.property("contentY") == 0
                footnote_origin = footnote.mapToItem(home_scroll, QPointF(0, 0))
                assert footnote_origin.y() + footnote.height() <= home_scroll.height()
                assert hero.property("font").pixelSize() >= 40
                for group_name in ("homeOcrSignalGroup", "homeTranslationSignalGroup"):
                    group = _find_quick_item(window, group_name)
                    assert group is not None
                    for text in group.findChildren(QQuickItem):
                        if text.metaObject().indexOfProperty("font") < 0 or not text.isVisible():
                            continue
                        origin = text.mapToItem(group, QPointF(0, 0))
                        assert origin.y() >= 0
                        assert origin.y() + text.height() <= group.height()

        controller.setPage("OCR")
        ocr_panel = _find_quick_item(window, "ocrSecondaryPanel")
        ocr_scroll = _find_quick_item(window, "ocrSettingsScroll")
        assert ocr_panel is not None
        assert ocr_scroll is not None
        _wait_for_page_layout(window, ocr_panel, app)
        assert ocr_scroll.property("contentHeight") <= ocr_scroll.height()
        assert ocr_scroll.property("contentY") == 0
        for quality_index in range(len(controller.detectionQualityNames)):
            controller.setDetectionQualityIndex(quality_index)
            app.processEvents()
            assert ocr_scroll.property("contentHeight") <= ocr_scroll.height()
    finally:
        host.shutdown()


def test_real_overlay_snapshot_keeps_portrait_canvas_contain_fit(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            (SnapshotEntry("portrait", 0, "竖屏原文", "竖屏译文", 0.9, (20, 80, 260, 420)),),
            (),
            ocr_peak_seconds=None,
            llm_peak_seconds=None,
            canvas_size=(600, 1200),
        ),
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    controller.setPage("OVERLAY")
    app.processEvents()
    canvas_item = _find_quick_item(window, "overlayLastRunCanvas")
    drawn_canvas = _find_quick_item(window, "overlayCanvas")
    assert canvas_item is not None
    assert drawn_canvas is not None
    _wait_for_page_layout(window, canvas_item, app)
    assert float(drawn_canvas.property("width")) <= float(canvas_item.property("width"))
    assert float(drawn_canvas.property("height")) <= float(canvas_item.property("height"))
    assert float(drawn_canvas.property("height")) > float(drawn_canvas.property("width"))
    host.shutdown()


def test_page_subtitle_stays_clear_of_dividers_across_pages_themes_and_sizes(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    header = _find_quick_item(window, "pageHeaderBar")
    rule = _find_quick_item(window, "prismPageHeaderRule")
    subtitle = _find_quick_item(window, "pageSubtitle")
    theme = _theme_for_skin(window, SKIN_PRISM)
    assert header is not None
    assert rule is not None
    assert subtitle is None
    assert theme is not None

    pages = ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS")
    for width, height in ((980, 700), (1280, 820)):
        window.resize(width, height)
        app.processEvents()
        for theme_name in ("dark", "light"):
            controller.setTheme(theme_name)
            app.processEvents()
            for page in pages:
                controller.setPage(page)
                app.processEvents()
                if theme.property("refraStyle") is True and page == "HOME":
                    dark_home = _find_quick_item(window, "refraDarkHome")
                    assert dark_home is not None and dark_home.isVisible()
                    assert header.isVisible() is False
                    assert subtitle is None
                    continue

                _wait_for_page_layout(window, header, app)
                assert header.isVisible() is True
                assert rule.isVisible() is True
                rule_top = rule.mapToItem(header, QPointF(0, 0)).y()
                if theme.property("refraStyle") is True:
                    english = _find_quick_item(window, "refraEnglishPageTitle")
                    chinese = _find_quick_item(window, "refraChinesePageTitle")
                    assert english is not None and english.isVisible()
                    assert chinese is not None and chinese.isVisible()
                    assert subtitle is None
                    assert english.property("y") < rule_top
                    assert chinese.property("y") < rule_top
                    assert rule_top >= 0
                    assert rule_top + rule.height() <= float(header.property("height"))
                else:
                    assert subtitle is None

    host.shutdown()


def test_real_workbench_uses_responsive_titles_and_settling_page_motion(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    controller.setReducedMotion(False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    title = window.findChild(QObject, "pageHeaderSlice")
    title_light = window.findChild(QObject, "refraEnglishPageTitle")
    title_heavy = window.findChild(QObject, "refraChinesePageTitle")
    header_rule = window.findChild(QObject, "prismPageHeaderRule")
    divider_line = header_rule.findChild(QObject, "prismDividerLine")
    page_subtitle = window.findChild(QObject, "pageSubtitle")
    header_bar = window.findChild(QObject, "pageHeaderBar")
    theme = window.findChild(QObject, "prismTheme")
    save_button = (
        window.findChild(QObject, "refraDarkApplyButton")
        or window.findChild(QObject, "darkSaveAllButton")
        or window.findChild(QObject, "saveAllButton")
    )
    required_items = {
        "title": title,
        "title_light": title_light,
        "title_heavy": title_heavy,
        "header_rule": header_rule,
        "divider_line": divider_line,
        "header_bar": header_bar,
        "theme": theme,
    }
    assert all(item is not None for item in required_items.values()), [
        name for name, item in required_items.items() if item is None
    ]
    assert page_subtitle is None

    display_fonts = theme.property("displayFonts")
    if hasattr(display_fonts, "toVariant"):
        display_fonts = display_fonts.toVariant()
    assert list(display_fonts)[:2] == ["Arial Narrow", "Bahnschrift"]
    assert theme.property("refraStyle") is True
    refra_english_title = window.findChild(QObject, "refraEnglishPageTitle")
    refra_chinese_title = window.findChild(QObject, "refraChinesePageTitle")
    # Home uses the full-canvas layout, so the shared header is hidden until
    # the test switches to a settings page below.
    assert refra_english_title is not None
    assert refra_chinese_title is not None
    assert refra_english_title.isVisible() is False
    assert refra_chinese_title.isVisible() is False
    assert refra_english_title.property("font").family() == "Arial Black"
    assert refra_english_title.property("font").weight() >= int(QFont.Weight.Black)
    assert refra_english_title.property("font").italic() is True
    assert window.findChild(QObject, "pageTitleCyanSlice") is None
    assert window.findChild(QObject, "pageTitleSpectrumSlice") is None
    assert window.findChild(QObject, "opticalStage") is None
    assert window.findChild(QObject, "pageTransitionSweep") is None
    assert window.findChild(QObject, "prismFoldRuleFacet") is None
    assert 40 <= refra_english_title.property("font").pixelSize() <= 76

    page_titles = {
        "HOME": ("HOME", "总览"),
        "CAPTURE": ("CAPTURE", "捕获"),
        "OCR": ("OCR", "文字识别"),
        "TRANSLATION": ("TRANSLATE", "翻译"),
        "OVERLAY": ("OVERLAY", "覆盖层"),
        "CACHE": ("CACHE", "缓存"),
        "SETTINGS": ("SETTINGS", "设置"),
    }
    for page, (english_title, chinese_title) in page_titles.items():
        controller.setPage(page)
        app.processEvents()
        assert title_light.property("text") == english_title
        assert title_heavy.property("text") == chinese_title
        assert refra_english_title.property("text") == english_title
        assert refra_chinese_title.property("text") == chinese_title
        if page == "HOME":
            assert header_bar.isVisible() is False
            assert header_rule.isVisible() is False
            assert refra_english_title.isVisible() is False
            assert refra_chinese_title.isVisible() is False
        else:
            assert header_bar.isVisible() is True
            assert header_rule.isVisible() is True
            assert refra_english_title.isVisible() is True
            assert refra_chinese_title.isVisible() is True

    assert divider_line.property("height") == 1
    assert divider_line.property("width") == header_rule.property("width")
    assert divider_line.property("color") == theme.property("line")
    assert divider_line.isVisible() is True

    def assert_subtitle_clearance() -> None:
        if theme.property("refraStyle"):
            assert page_subtitle is None
            return
        subtitle_top = page_subtitle.mapToItem(header_bar, QPointF(0, 0)).y()
        subtitle_bottom = subtitle_top + float(page_subtitle.property("height"))
        rule_bottom = header_rule.mapToItem(
            header_bar,
            QPointF(0, float(header_rule.property("height"))),
        ).y()
        assert subtitle_top >= rule_bottom + 3
        assert subtitle_bottom <= float(header_bar.property("height")) - 4

    def assert_title_fits() -> None:
        if theme.property("refraStyle"):
            active_title = window.findChild(QObject, "refraEnglishPageTitle")
            profile_name = window.findChild(QObject, "darkHeaderProfileName")
            assert active_title is not None and profile_name is not None
            assert active_title is title_light
            assert active_title.property("visible") is True
            title_right = active_title.mapToItem(
                header_bar,
                QPointF(float(active_title.property("width")), 0),
            ).x()
            profile_left = profile_name.mapToItem(header_bar, QPointF(0, 0)).x()
            assert title_right + 8 <= profile_left
            return
        title_right = title_light.mapToItem(
            header_bar,
            QPointF(float(title_light.property("width")), 0),
        ).x()
        assert save_button is not None
        save_left = save_button.mapToItem(header_bar, QPointF(0, 0)).x()
        assert title_light.property("y") >= 0
        assert title_light.property("y") + title_light.property("height") <= title.property("height")
        assert title_right + 8 <= save_left

    window.resize(980, 700)
    controller.setTheme("dark")
    controller.setPage("OVERLAY")
    app.processEvents()
    compact_title = window.findChild(QObject, "refraEnglishPageTitle")
    assert compact_title is not None
    compact_title_size = compact_title.property("font").pixelSize()
    assert 48 <= compact_title_size <= 60
    assert_title_fits()
    assert_subtitle_clearance()

    window.resize(1280, 820)
    controller.setPage("SETTINGS")
    app.processEvents()
    assert 68 <= compact_title.property("font").pixelSize() <= 76
    assert_title_fits()
    assert_subtitle_clearance()

    QTest.qWait(int(theme.property("pageMotion")) + 30)
    controller.setPage("CAPTURE")
    app.processEvents()
    QTest.qWait(1)
    content_translate = window.findChild(QObject, "pageContentTranslate")
    page_content = window.findChild(QObject, "pageContentMotion")
    header_translate = window.findChild(QObject, "pageHeaderTranslate")
    page_header = window.findChild(QObject, "pageHeaderSlice")
    primary_panel = window.findChild(QObject, "capturePrimaryPanel")
    secondary_panel = window.findChild(QObject, "captureSecondaryPanel")
    assert content_translate is not None
    assert page_content is not None
    assert header_translate is not None
    assert page_header is not None
    assert primary_panel is not None
    assert secondary_panel is not None
    assert window.property("pageTransitioning") is True
    assert window.property("pageContentReady") is True
    assert abs(float(content_translate.property("x"))) > 0.5
    assert abs(float(header_translate.property("x"))) > 0.5
    assert float(page_content.property("opacity")) == 1
    assert primary_panel.property("entryRunning") is True
    assert secondary_panel.property("entryRunning") is True

    QTest.qWait(int(theme.property("pageMotion")) + 40)
    app.processEvents()
    assert window.property("pageTransitioning") is False
    assert window.property("pageContentReady") is True
    assert content_translate.property("x") == 0
    assert header_translate.property("x") == 0
    assert primary_panel.property("entryRunning") is False
    assert secondary_panel.property("entryRunning") is False
    assert float(primary_panel.property("opacity")) == 1
    assert float(secondary_panel.property("opacity")) == 1
    assert_subtitle_clearance()
    host.shutdown()

@pytest.mark.parametrize(
    ("skin", "theme_name"),
    [(SKIN_PRISM, "dark"), (SKIN_PRISM, "light"), (SKIN_DOHNA, "light")],
)
def test_workbench_text_is_readable_and_controls_fit_across_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skin: str,
    theme_name: str,
) -> None:
    # Layout checks must not show a hotkey conflict dialog over the page.
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path, load_config(config_path), "game", display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        window = host.window
        assert window is not None
        prism_style = skin == SKIN_PRISM
        pages = (
            ("HOME", "refraDarkHome" if prism_style else "homePrimaryPanel"),
            ("CAPTURE", "captureSecondaryPanel"),
            ("OCR", "ocrSecondaryPanel"),
            ("TRANSLATION", "translationSecondaryPanel"),
            ("OVERLAY", "overlaySecondaryPanel"),
            ("CACHE", "cacheSecondaryPanel"),
            ("SETTINGS", "settingsPrimaryPanel"),
        )
        # Shrink an already laid out wide window, then grow and shrink again.
        for width, height in ((1280, 820), (980, 700), (1600, 900), (980, 700)):
            window.resize(max(width, window.minimumWidth()), height)
            for page, panel_name in pages:
                controller.setPage(page)
                panel = _find_quick_item(window, panel_name)
                assert panel is not None, panel_name
                _wait_for_page_layout(window, panel, app)
                page_item = _find_quick_item(window, page.lower() + "Page")
                assert page_item is not None, page
                if page == "HOME" and prism_style:
                    assert panel.isEnabled()
                    for name in (
                        "refraDarkHomeStage",
                        "refraDarkHomeStatusBand",
                        "refraDarkHomeActions",
                    ):
                        content = _find_quick_item(window, name)
                        assert content is not None and content.isVisible()
                        origin = content.mapToItem(panel, QPointF(0, 0))
                        assert origin.x() >= -0.5 and origin.y() >= -0.5
                        assert origin.x() + content.width() <= panel.width() + 0.5
                        assert origin.y() + content.height() <= panel.height() + 0.5
                    assert _find_quick_item(window, "refraDarkHeroImage").isVisible()
                    status_band = _find_quick_item(window, "refraDarkHomeStatusBand")
                    assert status_band is not None
                    headings = [
                        _find_quick_item(window, name)
                        for name in (
                            "refraDarkProfileHeading",
                            "refraDarkOcrHeading",
                            "refraDarkTranslationHeading",
                            "refraDarkLastRunHeading",
                        )
                    ]
                    assert all(heading is not None and heading.isVisible() for heading in headings)
                    heading_y = [
                        heading.mapToItem(status_band, QPointF(0, 0)).y()
                        for heading in headings
                    ]
                    assert max(heading_y) - min(heading_y) <= 0.5

                    ocr_status = _find_quick_item(window, "refraDarkOcrStatus")
                    assert ocr_status is not None
                    assert ocr_status.property("text") == controller.ocrStatus
                    assert ocr_status.property("lineCount") <= 2
                    status_origin = ocr_status.mapToItem(status_band, QPointF(0, 0))
                    assert status_origin.y() + ocr_status.height() <= status_band.height() + 0.5

                    footer_rule = _find_quick_item(window, "refraDarkHomeActionRule")
                    assert footer_rule is not None
                    footer_rule_y = footer_rule.mapToItem(panel, QPointF(0, 0)).y()
                    for name in (
                        "refraDarkRefreshProfiles",
                        "refraDarkCreateProfile",
                        "refraDarkDeleteProfile",
                    ):
                        profile_action = _find_quick_item(window, name)
                        assert profile_action is not None and profile_action.isVisible()
                        action_bottom = profile_action.mapToItem(
                            panel,
                            QPointF(0, profile_action.height()),
                        ).y()
                        assert action_bottom <= footer_rule_y + 0.5, (
                            width, name, action_bottom, footer_rule_y,
                        )
                    page_panels = []
                else:
                    page_panels = [
                        _find_quick_item(window, page.lower() + role + "Panel")
                        for role in ("Primary", "Secondary")
                    ]
                if page_panels:
                    for page_panel in page_panels:
                        assert page_panel is not None, page
                        origin = page_panel.mapToItem(page_item, QPointF(0, 0))
                        assert origin.x() >= -0.5, (page, page_panel.objectName())
                        assert origin.x() + page_panel.width() <= page_item.width() + 0.5, (
                            page, page_panel.objectName(), window.width(),
                            origin.x(), page_panel.width(), page_item.width(),
                        )
                        scene_origin = page_panel.mapToScene(QPointF(0, 0))
                        assert scene_origin.x() + page_panel.width() <= window.width() + 0.5
                    primary, secondary = page_panels
                    secondary_origin = secondary.mapToItem(page_item, QPointF(0, 0))
                    primary_right = primary.mapToItem(page_item, QPointF(primary.width(), 0))
                    panel_gap = 8 if page == "SETTINGS" and skin == SKIN_PRISM else 16
                    assert secondary_origin.x() - primary_right.x() >= panel_gap - 0.5, page

                pending = [window.contentItem()]
                checked = 0
                while pending:
                    item = pending.pop()
                    pending.extend(item.childItems())
                    if not item.isVisible() or not any(
                        item.inherits(kind)
                        for kind in ("QQuickText", "QQuickTextInput", "QQuickTextEdit")
                    ):
                        continue
                    text = str(item.property("text") or "")
                    if not text:
                        continue
                    font_size = item.property("font").pixelSize()
                    minimum_font_size = (
                        10
                        if prism_style and text in {
                                "GAME SCREEN TRANSLATOR", "FPS", "50—1000 MS", "100—5000 MS",
                        }
                        else 11
                        if prism_style and (page == "HOME" or text == "当前配置")
                        else 12
                    )
                    assert font_size >= minimum_font_size, (page, text, font_size)
                    if item.inherits("QQuickTextInput"):
                        assert font_size >= 15, (page, text, font_size)
                        available_height = (
                            item.height()
                            - float(item.property("topPadding"))
                            - float(item.property("bottomPadding"))
                        )
                        assert item.property("contentHeight") <= available_height + 1
                    checked += 1
                assert checked > 10, page

                if skin == SKIN_PRISM and page == "TRANSLATION" and width == 980:
                    unavailable = _find_quick_item(
                        window,
                        "translationLastRunUnavailable",
                    )
                    assert unavailable is not None
                    assert unavailable.isVisible()
                    eyebrow = unavailable.findChild(
                        QQuickItem,
                        "unavailableStateEyebrow",
                    )
                    assert eyebrow is not None
                    assert eyebrow.isVisible()
                    assert eyebrow.property("lineCount") >= 1
                    assert eyebrow.property("text") == "LAST RUN TRANSLATION · UNAVAILABLE"
                    theme = window.findChild(QObject, "prismTheme")
                    assert theme is not None
                    assert QColor(eyebrow.property("color")) == QColor(
                        theme.property("accentText"),
                    )
                    eyebrow_origin = eyebrow.mapToItem(unavailable, QPointF(0, 0))
                    assert eyebrow_origin.y() >= 0
                    assert eyebrow_origin.y() + eyebrow.height() <= unavailable.height()
                    assert eyebrow.width() <= unavailable.width() - 40 + 0.5
                    assert float(eyebrow.property("paintedWidth")) <= eyebrow.width() + 0.5

            for name in (
                *(f"navigationButton{index}" for index in range(7)),
                *( ("darkSaveAllButton", "darkStartLiveButton") if prism_style else ("saveAllButton", "startLiveButton") ),
            ):
                button = _find_quick_item(window, name)
                assert button is not None, name
                label = button.findChild(QQuickItem, "prismButtonLabel")
                assert label is not None, name
                assert label.property("font").pixelSize() >= 13
                # Windows' offscreen plugin may have no resolved system fonts.
                # Check text fitting when Qt has real glyph metrics; the same
                # test also runs with the native Windows platform for validation.
                if QFontInfo(label.property("font")).pixelSize() >= 0:
                    assert label.property("truncated") is False, (
                        name, label.property("text"), label.width(),
                        label.property("implicitWidth"),
                    )
            if prism_style:
                start_button = _find_quick_item(window, "darkStartLiveButton")
                apply_button = _find_quick_item(window, "darkSaveAllButton")
                assert start_button is not None and apply_button is not None
                start_x = start_button.mapToItem(window.contentItem(), QPointF(0, 0)).x()
                apply_x = apply_button.mapToItem(window.contentItem(), QPointF(0, 0)).x()
                assert start_x < apply_x
                assert start_button.property("p3Action") is True
                assert apply_button.property("p3Action") is True
    finally:
        host.shutdown()


def test_real_workbench_pages_and_themes_are_usable(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("dark")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = _theme_for_skin(window, SKIN_PRISM)
    title_dark = _find_quick_item(window, "refraEnglishPageTitle")
    title_dark_chinese = _find_quick_item(window, "refraChinesePageTitle")
    motion_feedback = _find_quick_item(window, "prismMotionFeedback")
    feedback_layer = _find_quick_item(window, "prismFeedbackLayer")
    assert all(
        item is not None
        for item in (
            theme, title_dark, title_dark_chinese,
            motion_feedback, feedback_layer,
        )
    )
    assert window.findChild(QObject, "pageDisplayTitleLight") is None
    assert window.findChild(QObject, "opticalStage") is None
    assert window.findChild(QObject, "pageTransitionSweep") is None

    pages = (
        ("HOME", "总览", "OVERVIEW", "总览", "homeSecondaryPanel"),
        ("CAPTURE", "捕获", "CAPTURE", "捕获", "captureSecondaryPanel"),
        ("OCR", "文字识别", "OCR", "文字识别", "ocrSecondaryPanel"),
        ("TRANSLATION", "翻译", "TRANSLATION", "翻译", "translationSecondaryPanel"),
        ("OVERLAY", "覆盖层", "OVERLAY", "覆盖层", "overlaySecondaryPanel"),
        ("CACHE", "缓存", "CACHE", "缓存", "cacheSecondaryPanel"),
        ("SETTINGS", "设置", "SETTINGS", "设置", "settingsSecondaryPanel"),
    )
    assert feedback_layer.property("visible") is False

    def contrast_ratio(foreground: QColor, background: QColor) -> float:
        def luminance(color: QColor) -> float:
            channels = [color.redF(), color.greenF(), color.blueF()]
            linear = [
                channel / 12.92 if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4
                for channel in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        first = luminance(foreground)
        second = luminance(background)
        return (max(first, second) + 0.05) / (min(first, second) + 0.05)

    for theme_name, expected_paper, expected_panel in (
        ("dark", "#03143b", "#071a3c"),
        ("light", "#f7f9fc", "#ffffff"),
    ):
        controller.setTheme(theme_name)
        controller.setPage("HOME")
        app.processEvents()
        assert theme.property("dark") is (theme_name == "dark")
        prism_style = theme.property("refraStyle") is True
        paper = QColor(theme.property("paper"))
        panel = QColor(theme.property("panel"))
        text = QColor(theme.property("text"))
        text_soft = QColor(theme.property("textSoft"))
        assert paper.name() == expected_paper
        assert panel.name() == expected_panel
        assert paper.alpha() == panel.alpha() == 255
        assert contrast_ratio(text, paper) >= 7
        assert contrast_ratio(text_soft, paper) >= 4.5
        assert QColor(theme.property("inputSurface")).alpha() == 255
        if prism_style:
            preferences_button = _find_quick_item(window, "refraDarkPreferencesButton")
            assert preferences_button is not None and preferences_button.isVisible()
            point = preferences_button.mapToScene(
                QPointF(preferences_button.width() / 2, preferences_button.height() / 2),
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
            app.processEvents()
            skin_selector = _find_quick_item(window, "refraHomeSkinSelector")
        else:
            skin_selector = _find_quick_item(window, "homeSkinSelector")
        assert skin_selector is not None and skin_selector.isVisible()
        combo_surface = skin_selector.findChild(QObject, "prismComboBoxBackground")
        chevron = skin_selector.findChild(QObject, "prismComboBoxChevron")
        assert combo_surface is not None
        assert chevron is not None
        assert QColor(combo_surface.property("color")).alpha() == 255
        assert chevron.property("visible") is True
        if prism_style:
            accept_button = _find_quick_item(window, "refraPreferencesDialogAcceptButton")
            assert accept_button is not None and accept_button.isVisible()
            point = accept_button.mapToScene(
                QPointF(accept_button.width() / 2, accept_button.height() / 2),
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
            app.processEvents()
        else:
            save_button = _find_quick_item(window, _workbench_save_button_name(window))
            start_button = _find_quick_item(window, _workbench_start_button_name(window))
            assert save_button is not None and save_button.property("visible") is True
            assert start_button is not None and start_button.property("visible") is True

        for index, (page, page_title, code, nav_title, panel_name) in enumerate(pages):
            controller.setPage(page)
            app.processEvents()
            assert window.property("pageContentReady") is True
            assert window.property("pageTransitioning") is False
            assert not window.findChildren(QObject, "prismFoldRuleFacet")
            if prism_style and page == "HOME":
                dark_home = _find_quick_item(window, "refraDarkHome")
                assert dark_home is not None and dark_home.isVisible()
                nav_button = _find_quick_item(window, f"refraDarkNavigationButton{index}")
                assert nav_button is not None and nav_button.isVisible()
                for action_name in ("refraDarkApplyButton", "refraDarkStartButton"):
                    home_action = _find_quick_item(window, action_name)
                    assert home_action is not None and home_action.isVisible()
            else:
                if prism_style:
                    assert title_dark.property("text") == ("TRANSLATE" if page == "TRANSLATION" else page)
                    assert title_dark.property("visible") is True
                    assert title_dark_chinese.property("text") == page_title
                    assert title_dark_chinese.property("visible") is True
                else:
                    assert title_light.property("text") == page_title
                    assert title_light.property("visible") is True
                    assert window.findChild(QObject, "pageDisplayTitleHeavy").property("text") == ""
                visible_dividers = [
                    line for line in window.findChildren(QObject, "prismDividerLine")
                    if line.property("visible")
                ]
                assert len(visible_dividers) >= 3
                for line in visible_dividers:
                    assert line.property("height") == 1
                    assert line.property("width") == line.parentItem().width()
                    assert line.property("color") == theme.property("line")
                    assert len(line.parentItem().childItems()) == 1
                nav_button = _find_quick_item(window, f"navigationButton{index}")
                assert nav_button is not None and nav_button.property("visible") is True
                if prism_style:
                    save_button = _find_quick_item(window, _workbench_save_button_name(window))
                    start_button = _find_quick_item(window, _workbench_start_button_name(window))
                    assert save_button is not None and save_button.property("visible") is True
                    assert start_button is not None and start_button.property("visible") is True
                else:
                    save_button = _find_quick_item(window, _workbench_save_button_name(window))
                    start_button = _find_quick_item(window, _workbench_start_button_name(window))
                    assert save_button is not None
                    assert start_button is not None
                    assert save_button.property("visible") is True
                    assert start_button.property("visible") is True
            nav_title_label = nav_button.findChild(QObject, "navigationTitleLabel")
            nav_code_label = nav_button.findChild(QObject, "navigationCodeLabel")
            nav_subtitle_label = nav_button.findChild(QObject, "navigationSubtitleLabel")
            assert nav_title_label is not None
            if prism_style:
                assert nav_subtitle_label is not None
                assert nav_title_label.property("text") == ("TRANSLATE" if page == "TRANSLATION" else page)
                assert nav_subtitle_label.property("text") == nav_title
            else:
                assert nav_code_label is not None
                assert nav_title_label.property("text") == nav_title
                assert nav_code_label.property("text") == code
                assert nav_code_label.property("font").pixelSize() >= 12

            if not (prism_style and page == "HOME"):
                primary_panel = _find_quick_item(window, panel_name)
                assert primary_panel is not None
                panel_surface = primary_panel.findChild(QObject, "prismPanelSurface")
                grid_rule = primary_panel.findChild(QObject, "prismPanelGridRule")
                assert panel_surface is not None
                assert grid_rule is not None
                assert panel_surface.property("color").alpha() == 0
                assert QQmlProperty(panel_surface, "border.width").read() == 0
                assert grid_rule.property("visible") is True

    assert motion_feedback.property("visible") is False
    assert feedback_layer.property("visible") is False
    host.shutdown()


def test_real_prism_button_feedback_tracks_pointer_and_reduced_motion(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    controller.setReducedMotion(False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    button = _find_quick_item(window, "refraDarkNavigationButton0")
    theme = window.findChild(QObject, "prismTheme")
    assert button is not None
    assert theme is not None
    QTest.qWait(int(theme.property("pageMotion")) + 60)
    app.processEvents()

    button_point = button.mapToScene(
        QPointF(button.width() / 2, button.height() / 2)
    ).toPoint()
    outside_point = QPoint(window.width() - 4, window.height() - 4)
    fast = int(theme.property("fast"))
    QTest.mouseMove(window, outside_point)
    QTest.qWait(fast + 20)
    app.processEvents()
    assert button.property("hovered") is False
    assert abs(float(button.property("scale")) - 1.0) < 0.001

    QTest.mouseMove(window, button_point)
    app.processEvents()
    assert button.property("hovered") is True
    QTest.qWait(max(5, fast // 2))
    hover_midpoint = float(button.property("scale"))
    assert 1.0 < hover_midpoint < 1.004
    QTest.qWait(fast + 20)
    assert abs(float(button.property("scale")) - 1.004) < 0.001

    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert button.property("down") is True
    QTest.qWait(max(5, fast // 2))
    press_midpoint = float(button.property("scale"))
    assert 0.994 < press_midpoint < 1.004
    QTest.qWait(fast + 20)
    assert abs(float(button.property("scale")) - 0.994) < 0.001

    controller.setReducedMotion(True)
    app.processEvents()
    assert theme.property("fast") == 0
    assert abs(float(button.property("scale")) - 0.994) < 0.001
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert button.property("down") is False
    assert abs(float(button.property("scale")) - 1.004) < 0.001
    QTest.mouseMove(window, outside_point)
    app.processEvents()
    assert button.property("hovered") is False
    assert abs(float(button.property("scale")) - 1.0) < 0.001

    button.setProperty("enabled", False)
    app.processEvents()
    QTest.mouseMove(window, button_point)
    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert button.property("down") is False
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert controller.currentPage == "HOME"
    assert abs(float(button.property("scale")) - 1.0) < 0.001
    host.shutdown()


def test_real_page_operations_show_local_feedback_and_settle(tmp_path: Path) -> None:
    class ActionController(WorkbenchController):
        def __init__(self, config_path: Path) -> None:
            super().__init__(config_path, probe_ocr_devices=False)
            self.probe_calls = 0

        @Slot()
        def probeOcrDevices(self) -> None:  # noqa: N802
            self.probe_calls += 1

    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = ActionController(config_path)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    selectors: list[_SelectorStub] = []
    selector_failure: list[Exception] = []

    def make_selector(_screen) -> _SelectorStub:
        if selector_failure:
            raise selector_failure.pop()
        selector = _SelectorStub()
        selectors.append(selector)
        return selector

    host = QmlWorkbenchHost(
        controller,
        application=app,
        selector_factory=make_selector,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    motion_feedback = window.findChild(QObject, "prismMotionFeedback")
    feedback_layer = window.findChild(QObject, "prismFeedbackLayer")
    action_rule = window.findChild(QObject, "prismActionFeedbackRule")
    warning_rule = window.findChild(QObject, "prismWarningFeedbackRule")
    theme = window.findChild(QObject, "prismTheme")
    assert motion_feedback is not None
    assert feedback_layer is not None
    assert action_rule is not None
    assert warning_rule is not None
    assert theme is not None
    assert window.findChild(QObject, "opticalStage") is None
    assert window.findChild(QObject, "transientFeedbackLayer") is None
    assert feedback_layer.property("enabled") is False
    assert feedback_layer.parent() == motion_feedback.parent()
    assert feedback_layer.property("z") > motion_feedback.property("z")

    previous_sequence = int(motion_feedback.property("actionSequence"))
    controller.setPage("CAPTURE")
    app.processEvents()
    custom_action = _click_quick_item(window, "captureCustomAction")
    assert int(motion_feedback.property("actionSequence")) == previous_sequence
    assert motion_feedback.property("actionPulseRunning") is False
    assert selectors[-1].opened is True
    assert window.isVisible() is False
    selectors[-1].selected_region = (10, 20, 640, 180)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Accepted))
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    assert window.isVisible() is True
    assert controller.captureLeft == 10
    assert controller.captureTop == 20
    assert controller.captureWidth == 640
    assert controller.captureHeight == 180
    assert motion_feedback.property("actionKind") == "scan"
    assert int(motion_feedback.property("actionSequence")) == previous_sequence + 1
    assert motion_feedback.property("actionPulseRunning") is True
    assert feedback_layer.property("visible") is True
    assert action_rule.property("visible") is True
    assert float(action_rule.property("width")) > 0
    previous_sequence += 1
    QTest.qWait(int(theme.property("actionMotion")) + 20)
    app.processEvents()
    assert motion_feedback.property("actionPulseRunning") is False
    assert action_rule.property("visible") is False

    _click_quick_item(window, "captureCustomAction")
    assert window.isVisible() is False
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    assert window.isVisible() is True
    assert int(motion_feedback.property("actionSequence")) == previous_sequence
    assert motion_feedback.property("actionPulseRunning") is False

    selector_failure.append(RuntimeError("selector unavailable"))
    _click_quick_item(window, "captureCustomAction")
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    assert window.isVisible() is True
    assert int(motion_feedback.property("actionSequence")) == previous_sequence
    assert motion_feedback.property("actionPulseRunning") is False
    error_dialog = window.findChild(QObject, "errorDialog")
    assert error_dialog is not None
    assert error_dialog.property("visible") is True
    _click_quick_item(window, "errorDialogAcceptButton")
    QTest.qWait(int(theme.property("warningMotion")) + 20)
    app.processEvents()
    assert warning_rule.property("visible") is False

    assert custom_action.property("text") == "自定义区域"
    assert window.findChild(QObject, "captureRegionSelectAction") is None
    assert not any(
        str(item.property("text")) in {"框选区域", "保存区域"}
        for item in window.findChildren(QObject)
    )

    operations = (
        ("OCR", "ocrProbeAction", "focus"),
        ("TRANSLATION", "translationTraceAction", "trace"),
        ("CACHE", "cacheRippleAction", "ripple"),
        ("SETTINGS", None, "calibrate"),
    )
    for page, button_name, action_kind in operations:
        controller.setPage(page)
        app.processEvents()
        if button_name is None:
            button_name = _workbench_save_button_name(window)
        _click_quick_item(window, button_name)
        assert motion_feedback.property("actionKind") == action_kind
        assert int(motion_feedback.property("actionSequence")) == previous_sequence + 1
        assert motion_feedback.property("actionPulseRunning") is True
        assert feedback_layer.property("visible") is True
        assert action_rule.property("visible") is True
        assert float(action_rule.property("width")) > 0
        previous_sequence += 1
    assert controller.probe_calls == 1

    QTest.qWait(int(theme.property("actionMotion")) + 30)
    app.processEvents()
    assert motion_feedback.property("actionPulseRunning") is False
    assert feedback_layer.property("visible") is False
    assert action_rule.property("visible") is False
    assert motion_feedback.property("actionProgress") == 1

    controller.setReducedMotion(True)
    controller.setPage("OCR")
    app.processEvents()
    assert controller.reducedMotion is True
    assert window.property("reduceMotion") is True
    assert motion_feedback.property("reducedMotion") is True
    QTest.qWait(16)
    app.processEvents()
    assert motion_feedback.property("actionPulseRunning") is False
    _click_quick_item(window, "ocrProbeAction")
    assert motion_feedback.property("actionKind") == "focus"
    assert int(motion_feedback.property("actionSequence")) == previous_sequence + 1
    assert motion_feedback.property("actionPulseRunning") is False
    assert motion_feedback.property("actionProgress") == 1
    assert feedback_layer.property("visible") is False
    assert action_rule.property("visible") is False
    assert window.property("pageTransitioning") is False
    host.shutdown()


def test_capture_custom_action_preserves_cancel_and_applies_boundary_edits(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("light")
    controller.setReducedMotion(True)
    selectors: list[_SelectorStub] = []

    def make_selector(_screen) -> _SelectorStub:
        selector = _SelectorStub()
        selectors.append(selector)
        return selector

    controller.setPage("CAPTURE")
    host = QmlWorkbenchHost(
        controller,
        application=app,
        selector_factory=make_selector,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None

    custom_action = window.findChild(QObject, "captureCustomAction")
    assert custom_action is not None
    assert custom_action.property("text") == "自定义区域"
    assert window.findChild(QObject, "captureRegionSelectAction") is None
    assert controller.customRegion is False
    original_region = (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    )

    _click_quick_item(window, "captureCustomAction")
    assert window.isVisible() is False
    assert selectors[-1].opened is True
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    app.processEvents()
    assert window.isVisible() is True
    assert controller.customRegion is False
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == original_region

    _click_quick_item(window, "captureCustomAction")
    selectors[-1].selected_region = (10, 20, 640, 180)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Accepted))
    app.processEvents()
    assert window.isVisible() is True
    assert controller.customRegion is True
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (10, 20, 640, 180)
    saved_profile = load_game_profile(config_path, load_config(config_path), "game")
    assert saved_profile.capture_settings.region_ratio == _region_ratio((10, 20, 640, 180))

    desired_values = {
        "捕获区域左边界": 30,
        "捕获区域上边界": 40,
        "捕获区域宽度": 800,
        "捕获区域高度": 400,
    }
    steppers = {
        str(item.property("accessibleName")): item
        for item in window.findChildren(QObject)
        if str(item.property("accessibleName")) in desired_values
    }
    assert set(steppers) == set(desired_values)
    for name, value in desired_values.items():
        stepper = steppers[name]
        assert stepper.property("enabled") is True
        editor = stepper.findChild(QObject, "numberStepperEditor")
        assert editor is not None
        editor.forceActiveFocus()
        editor.setProperty("text", str(value))
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()

    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (30, 40, 800, 400)
    assert controller.settingsDirty is True

    _click_quick_item(window, _workbench_save_button_name(window))
    app.processEvents()
    assert controller.settingsDirty is False
    saved_profile = load_game_profile(config_path, load_config(config_path), "game")
    assert saved_profile.capture_settings.region_ratio == _region_ratio((30, 40, 800, 400))
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
def test_start_button_waits_for_prelude_and_reduced_motion_runs_immediately(
    tmp_path: Path,
    skin: str,
) -> None:
    class RecordingController(WorkbenchController):
        def __init__(self, config_path: Path) -> None:
            super().__init__(config_path, probe_ocr_devices=False)
            self.toggle_calls = 0

        @Slot()
        def toggleLive(self) -> None:  # noqa: N802
            self.toggle_calls += 1

    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = RecordingController(config_path)
    controller.setSkin(skin)
    controller.setTheme("light")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    theme = _theme_for_skin(window, skin)
    motion_feedback = window.findChild(QObject, "prismMotionFeedback")
    start_feedback = window.findChild(QObject, "prismStartProgressRule")
    feedback_layer = window.findChild(QObject, "prismFeedbackLayer")
    dohna_feedback = window.findChild(QObject, "dohnaFeedbackLayer")
    assert theme is not None
    if skin == SKIN_PRISM:
        assert motion_feedback is not None
        assert start_feedback is not None
        assert feedback_layer is not None
        assert dohna_feedback is None
    else:
        assert motion_feedback is None
        assert start_feedback is None
        assert feedback_layer is None
        assert dohna_feedback is not None

    _click_quick_item(window, _workbench_start_button_name(window))
    assert window.property("startPreludePending") is True
    assert controller.toggle_calls == 0
    if skin == SKIN_DOHNA:
        assert dohna_feedback.property("warningPulseRunning") is False
        assert not window.findChildren(QObject, "dohnaStartImpact")
        assert not window.findChildren(QObject, "dohnaStartImpactTag")
    else:
        assert motion_feedback.property("startPreludeRunning") is True
        assert start_feedback.property("visible") is True
        assert motion_feedback.property("startPreludeSequence") == 1
    QTest.qWait(280)
    assert controller.toggle_calls == 0
    QTest.qWait(100)
    app.processEvents()
    assert controller.toggle_calls == 1
    assert window.property("startPreludePending") is False
    QTest.qWait(80)
    assert controller.toggle_calls == 1

    _click_quick_item(window, _workbench_start_button_name(window))
    assert window.property("startPreludePending") is True
    assert controller.toggle_calls == 1
    controller.setReducedMotion(True)
    app.processEvents()
    assert controller.toggle_calls == 2
    assert window.property("startPreludePending") is False
    if skin == SKIN_PRISM:
        assert start_feedback.property("visible") is False
        assert feedback_layer.property("visible") is False
    else:
        assert dohna_feedback.property("warningPulseRunning") is False
    assert not window.findChildren(QObject, "dohnaStartImpact")
    assert not window.findChildren(QObject, "dohnaStartImpactTag")
    QTest.qWait(16)
    app.processEvents()
    if skin == SKIN_PRISM:
        assert motion_feedback.property("startPreludeRunning") is False
    else:
        assert dohna_feedback.property("warningPulseRunning") is False

    _click_quick_item(window, _workbench_start_button_name(window))
    assert controller.toggle_calls == 3
    assert window.property("startPreludePending") is False

    # Switching skins during the pending prelude must settle only the visual
    # pulse; the one-shot timer still toggles the real controller exactly once.
    controller.setReducedMotion(False)
    controller.setSkin(SKIN_DOHNA if skin == SKIN_PRISM else SKIN_PRISM)
    app.processEvents()
    _click_quick_item(window, _workbench_start_button_name(window))
    assert window.property("startPreludePending") is True
    pending_calls = controller.toggle_calls
    controller.setSkin(skin)
    app.processEvents()
    assert window.property("startPreludePending") is True
    QTest.qWait(int(theme.property("startPreludeMotion")) + 70)
    app.processEvents()
    assert controller.toggle_calls == pending_calls + 1
    assert window.property("startPreludePending") is False
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
@pytest.mark.parametrize("window_size", [(1280, 820), (980, 700)])
@pytest.mark.parametrize("dynamic_roi", [True, False], ids=["dynamic_roi", "full_frame"])
def test_settings_keeps_output_controls_left_and_diagnostics_selectable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skin: str,
    window_size: tuple[int, int],
    dynamic_roi: bool,
) -> None:
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "settings-layout",
        display_name="高级设置布局验证 " + "长名称用于验证真实 Profile 诊断换行。" * 12,
    )
    log_path = tmp_path / "output" / "live.log"
    log_path.parent.mkdir()
    stats = LiveLatencyStats()
    for kind in ("roi", "full"):
        stats.record_ocr_pipeline(
            scan_kind=kind, scan_label="局部 ROI" if kind == "roi" else "整帧回退",
            change_activity_seconds=0.1, scheduling_seconds=0.05,
            preparation_seconds=0.01, worker_queue_seconds=0,
            ocr_seconds=0.2, collection_seconds=0.01, processing_seconds=0.02,
        )
    stats.record_translation(
        stability_seconds=0.1, queue_seconds=0.002,
        llm_seconds=1.2, total_seconds=1.8, batch_size=2,
    )
    log_text = (
        "诊断测试夹具：不代表真实翻译运行。\n实时统计：OCR 2 次\n"
        + "延迟统计：" + stats.render().replace("\n", "；") + "\n"
        + stats.render_ocr_summary() + "\n"
    )
    log_path.write_text(log_text, encoding="utf-8")
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setTheme("dark")
    controller.setReducedMotion(True)
    controller.setDynamicRoiEnabled(dynamic_roi)
    assert controller.saveRuntimeSettings() is True
    controller.setPage("SETTINGS")
    host = QmlWorkbenchHost(controller, application=app)

    try:
        window = host.window
        assert window is not None
        window.resize(max(window_size[0], window.minimumWidth()), window_size[1])
        host.show()
        primary = _find_quick_item(window, "settingsPrimaryPanel")
        secondary = _find_quick_item(window, "settingsSecondaryPanel")
        assert primary is not None and secondary is not None
        _wait_for_page_layout(window, primary, app)

        def item(name: str) -> QQuickItem:
            result = _find_quick_item(window, name)
            assert result is not None, name
            return result

        form = item("settingsFormScroll")
        debug = item("settingsDebugToggle")
        browser = item("settingsCalibrationAction")
        url = item("settingsBrowserOverlayUrl")
        profile_scroll = item("settingsProfileScroll")
        diagnostic = item("settingsProfileDiagnostic")
        log_scroll = item("settingsLatencyScroll")
        ocr = item("settingsOcrLatency")
        translation = item("settingsTranslationLatency")
        summary = item("settingsLatencySummary")
        refresh = item("settingsRefreshDiagnostics")

        def is_descendant(child: QQuickItem, ancestor: QQuickItem) -> bool:
            current = child.parentItem()
            while current is not None and current is not ancestor:
                current = current.parentItem()
            return current is ancestor

        for control in (debug, browser, url):
            assert is_descendant(control, primary)
            assert not is_descendant(control, secondary)
        for control in (profile_scroll, log_scroll, refresh):
            assert is_descendant(control, secondary)
        assert debug.property("settingKey") == "settings-debug-border"
        assert browser.property("settingKey") == "settings-browser-overlay"
        assert url.property("text") == controller.browserOverlayUrl
        assert item("dynamicRoiSchedule").isVisible() is dynamic_roi
        assert item("fullFrameSchedule").isVisible() is not dynamic_roi
        if skin == SKIN_PRISM:
            legacy_setting_labels = (
                "settingsPollLegacyLabel",
                "settingsClearAfterLegacyLabel",
                "settingsRoiLegacyLabel",
                "settingsStableRescanLegacyLabel",
                "settingsIdleRescanLegacyLabel",
                "settingsOcrCooldownLegacyLabel",
            )
            assert all(_find_quick_item(window, name) is None for name in legacy_setting_labels)
            active_rows = (
                ("settingsCalibrationStepper", "settingsClearAfterStepper", "settingsRoiResponseStepper")
                if dynamic_roi else
                ("settingsCalibrationStepper", "settingsClearAfterStepper", "settingsStableRescanStepper",
                 "settingsIdleRescanStepper", "settingsOcrCooldownStepper")
            )
            assert all(item(name).isVisible() for name in active_rows)
            assert all(item(name).isEnabled() for name in active_rows)
            decrement_x: list[float] = []
            increment_right: list[float] = []
            for row_name in active_rows:
                row = item(row_name)
                decrement = _find_quick_item(row, "numberStepperDecrease")
                increment = _find_quick_item(row, "numberStepperIncrease")
                title = _find_quick_item(row, "numberStepperRowTitle")
                meta = _find_quick_item(row, "numberStepperRowMeta")
                assert all(node is not None for node in (decrement, increment, title, meta))
                assert title.property("text") in {
                    "画面变化轮询",
                    "字幕消失判定",
                    "ROI 响应目标",
                    "稳定后复扫",
                    "空闲复扫",
                    "OCR 冷却",
                }
                if window_size == (980, 700):
                    assert row.property("stackedDetails") is True
                    assert title.property("truncated") is False
                    assert meta.property("truncated") is False
                    assert increment.isVisible() and increment.isEnabled()
                    assert decrement.isVisible()
                if window_size == (1280, 820):
                    assert row.property("stackedDetails") is False
                decrement_x.append(decrement.mapToItem(form, QPointF(0, 0)).x())
                increment_right.append(
                    increment.mapToItem(form, QPointF(increment.width(), 0)).x()
                )
                title_center = title.mapToItem(form, QPointF(0, title.height() / 2)).y()
                meta_center = meta.mapToItem(form, QPointF(0, meta.height() / 2)).y()
                assert abs(title_center - meta_center) <= 1
        if skin == SKIN_PRISM and window_size == (1280, 820):
            assert max(decrement_x) - min(decrement_x) <= 1
            assert max(increment_right) - min(increment_right) <= 1

        def assert_contained(child: QQuickItem, viewport: QQuickItem) -> None:
            point = child.mapToItem(viewport, QPointF(0, 0))
            assert point.x() >= -0.5
            assert point.y() >= -0.5
            assert point.x() + child.width() <= viewport.width() + 0.5
            assert point.y() + child.height() <= viewport.height() + 0.5

        if skin == SKIN_PRISM and window_size == (980, 700):
            # Every full-frame scheduler stepper stays reachable at the
            # minimum window size; scroll the actual form so the plus target
            # is within its viewport before checking its real click behavior.
            for row_name in active_rows:
                row = item(row_name)
                button = _find_quick_item(row, "numberStepperIncrease")
                assert button is not None
                visible_top = row.mapToItem(form, QPointF(0, 0)).y()
                scroll_delta = max(
                    visible_top + row.height() - form.height() + 8,
                    min(0.0, visible_top - 8),
                )
                max_scroll = max(
                    0.0,
                    float(form.property("contentHeight")) - form.height(),
                )
                form.setProperty(
                    "contentY",
                    max(0.0, min(max_scroll, float(form.property("contentY")) + scroll_delta)),
                )
                app.processEvents()
                assert button.isVisible() and button.isEnabled()
                assert_contained(button, form)

            first_row = item(active_rows[0])
            first_plus = _find_quick_item(first_row, "numberStepperIncrease")
            first_minus = _find_quick_item(first_row, "numberStepperDecrease")
            assert first_plus is not None and first_minus is not None
            original_value = int(first_row.property("value"))
            first_plus_point = first_plus.mapToScene(
                QPointF(first_plus.width() / 2, first_plus.height() / 2)
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=first_plus_point)
            app.processEvents()
            assert int(first_row.property("value")) > original_value
            first_minus_point = first_minus.mapToScene(
                QPointF(first_minus.width() / 2, first_minus.height() / 2)
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=first_minus_point)
            app.processEvents()
            assert int(first_row.property("value")) == original_value

        if dynamic_roi and window_size == (1280, 820):
            assert float(form.property("contentY")) == 0
            assert_contained(debug, form)
        assert_contained(profile_scroll, secondary)
        assert_contained(log_scroll, secondary)
        assert_contained(refresh, secondary)
        form_bar = _find_quick_item(form, "prismScrollBar")
        assert form_bar is not None
        if skin == SKIN_PRISM:
            bar_right = form_bar.mapToScene(QPointF(form_bar.width(), 0)).x()
            divider_left = secondary.mapToScene(QPointF(0, 0)).x()
            assert 8 <= divider_left - bar_right <= 16.5
        for viewport, texts in (
            (profile_scroll, (diagnostic,)),
            (log_scroll, (ocr, translation, summary)),
        ):
            bar = _find_quick_item(viewport, "prismScrollBar")
            assert bar is not None
            _assert_scroll_thumb_inside_track(bar)
            track = _find_quick_item(bar, "prismScrollTrack")
            origin = track.mapToItem(viewport, QPointF(0, 0))
            assert origin.y() >= 1
            assert origin.y() + track.height() <= viewport.height() - 1
            assert origin.x() + track.width() <= viewport.width() - 1
            lane_left = bar.mapToItem(viewport, QPointF(0, 0)).x()
            for text in texts:
                origin = text.mapToItem(viewport, QPointF(0, 0))
                assert origin.x() + text.width() <= lane_left - 7.5
        if window_size == (1280, 820):
            assert log_scroll.height() > 142  # The former log viewport height.
        else:
            assert log_scroll.height() >= 100
        assert log_scroll.mapToItem(secondary, QPointF(0, log_scroll.height())).y() < (
            refresh.mapToItem(secondary, QPointF(0, 0)).y()
        )

        # Optional native screenshots capture this real QML host and the
        # explicitly labelled diagnostic fixture, never a simulated live run.
        screenshot_dir = os.environ.get("REFRA_SETTINGS_SCREENSHOT_DIR")
        capture_name = (
            f"settings-{skin}-{window.width()}x{window.height()}-"
            f"{'dynamic' if dynamic_roi else 'full'}"
        )

        def capture(suffix: str) -> None:
            if not screenshot_dir:
                return
            destination = Path(screenshot_dir)
            destination.mkdir(parents=True, exist_ok=True)
            window.update()
            QTest.qWait(80)
            frame = window.grabWindow()
            assert not frame.isNull()
            target = destination / f"{capture_name}-{suffix}.png"
            assert frame.save(str(target))
            print(f"NATIVE QML SCREENSHOT: {target.resolve()}")

        capture("initial")

        def saved_config():
            machine = load_config(config_path)
            return apply_profile_runtime_settings(
                machine, load_game_profile(config_path, machine, profile.profile_id)
            )

        before = saved_config()
        actions: list[str] = []
        settings_page = item("settingsPage")
        settings_page.visualAction.connect(actions.append)
        for control, expected in (
            (debug, controller.debugEnabled),
            (browser, controller.browserOverlayEnabled),
        ):
            control.forceActiveFocus()
            app.processEvents()
            QTest.qWait(20)
            app.processEvents()
            assert_contained(control, form)
            # A stretched checkbox can have blank space outside its hit area.
            indicator = control.property("indicator")
            assert isinstance(indicator, QQuickItem)
            position = indicator.mapToScene(
                QPointF(indicator.width() / 2, indicator.height() / 2)
            )
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position.toPoint())
            app.processEvents()
            assert bool(control.property("checked")) is not expected
        assert actions == ["calibrate", "calibrate"]
        assert controller.settingsDirty is True
        assert controller.running is False
        unsaved = saved_config()
        assert unsaved.live.debug_border == before.live.debug_border
        assert unsaved.recording.browser_overlay_enabled == before.recording.browser_overlay_enabled
        assert controller.saveRuntimeSettings() is True
        saved = saved_config()
        assert saved.live.debug_border == controller.debugEnabled
        assert saved.recording.browser_overlay_enabled == controller.browserOverlayEnabled
        capture("output")

        for text_area, expected in (
            (diagnostic, controller.infoText),
            (ocr, controller.latencyDiagnostics["ocr"]),
            (translation, controller.latencyDiagnostics["translation"]),
            (summary, controller.latencyDiagnostics["summary"]),
        ):
            assert text_area.property("text") == expected
            assert text_area.property("readOnly") is True
            assert text_area.property("selectByMouse") is True
            assert QMetaObject.invokeMethod(text_area, "selectAll") is True
            assert text_area.property("selectedText") == expected
        assert "P50" not in ocr.property("text")
        assert "LLM 请求：1.20s" in translation.property("text")
        assert "P95" in summary.property("text")
        assert "所有 Profile 共用" in str(item("settingsPage").property("diagnostics"))

        # Profile diagnostics use the outer ScrollView. Latency blocks are
        # fixed-height selectable TextAreas in the current skin layout.
        for scroll in (profile_scroll,):
            QTest.qWait(100)
            app.processEvents()
            assert scroll.property("clip") is True
            flickable = scroll.property("contentItem")
            assert isinstance(flickable, QQuickItem)
            assert float(flickable.property("contentHeight")) > flickable.height()
            position = scroll.mapToScene(QPointF(scroll.width() / 2, scroll.height() / 2))
            QTest.mouseMove(window, position.toPoint())
            maximum = float(flickable.property("contentHeight")) - flickable.height()
            for _ in range(math.ceil(maximum / 16) + 10):
                wheel = QWheelEvent(
                    position,
                    QPointF(window.mapToGlobal(position.toPoint())),
                    QPoint(0, 0),
                    QPoint(0, -120),
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.NoScrollPhase,
                    False,
                )
                QCoreApplication.sendEvent(window, wheel)
                app.processEvents()
                QTest.qWait(10)
                if float(flickable.property("contentY")) >= maximum:
                    break
            QTest.qWait(450)  # Let the native Flickable finish its edge rebound.
            app.processEvents()
            maximum = float(flickable.property("contentHeight")) - flickable.height()
            assert math.isclose(float(flickable.property("contentY")), maximum, abs_tol=1), (
                scroll.objectName(), flickable.property("contentY"), maximum
            )

        # Scroll the primary settings form with real wheel events through to
        # its final URL field, proving the fixed footer leaves the field usable.
        form_content = form
        form_maximum = max(
            0.0,
            float(form_content.property("contentHeight")) - form_content.height(),
        )
        if form_maximum > 0:
            position = form.mapToScene(QPointF(form.width() / 2, form.height() / 2))
            QTest.mouseMove(window, position.toPoint())
            for _ in range(math.ceil(form_maximum / 16) + 10):
                wheel = QWheelEvent(
                    position,
                    QPointF(window.mapToGlobal(position.toPoint())),
                    QPoint(0, 0),
                    QPoint(0, -120),
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.NoScrollPhase,
                    False,
                )
                QCoreApplication.sendEvent(window, wheel)
                app.processEvents()
                QTest.qWait(10)
                current = float(form_content.property("contentY"))
                form_maximum = max(
                    0.0,
                    float(form_content.property("contentHeight")) - form_content.height(),
                )
                if current >= form_maximum:
                    break
            QTest.qWait(450)
            app.processEvents()
            form_maximum = max(
                0.0,
                float(form_content.property("contentHeight")) - form_content.height(),
            )
            assert math.isclose(
                float(form_content.property("contentY")), form_maximum, abs_tol=1
            )
        assert_contained(url, form)
        assert url.property("text") == controller.browserOverlayUrl
        capture("diagnostic-end")

        log_path.write_text("[RefraTranslator Live] ready\n", encoding="utf-8")
        assert ocr.property("text") != controller.latencyDiagnostics["ocr"]
        position = refresh.mapToScene(QPointF(refresh.width() / 2, refresh.height() / 2))
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position.toPoint())
        app.processEvents()
        assert ocr.property("text") == controller.latencyDiagnostics["ocr"]
        assert translation.property("text") == controller.latencyDiagnostics["translation"]
        assert summary.property("text") == controller.latencyDiagnostics["summary"]
        assert "尚无" in item("settingsLatencyStatus").property("text")
        assert actions[-1] == "calibrate"
        assert_contained(refresh, secondary)
        capture("empty")
    finally:
        host.shutdown()


def test_refra_dark_home_keeps_one_enabled_navigation_tree_and_shared_preferences(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "dark-home-layout",
        display_name="长配置名称用于暗色首页检查配置字段可读性与错误状态分布",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme("dark")
    controller.setReducedMotion(True)
    controller.setPage("HOME")
    host = QmlWorkbenchHost(controller, application=app)

    try:
        window = host.window
        assert window is not None
        host.show()
        window.resize(980, 700)
        app.processEvents()

        def item(name: str) -> QQuickItem:
            result = _find_quick_item(window, name)
            assert result is not None, name
            return result

        theme = window.findChild(QObject, "prismTheme")
        assert theme is not None
        dark_home = item("refraDarkHome")
        assert dark_home.isVisible() and dark_home.isEnabled()
        assert _find_quick_item(window, "homePrimaryPanel") is None
        assert _find_quick_item(window, "homePrimaryScroll") is None
        controller.setPage("SETTINGS")
        app.processEvents()
        brand = item("refraBrandWordmark")
        assert brand.isVisible()
        assert brand.property("truncated") is False
        controller.setPage("HOME")
        app.processEvents()
        assert _find_quick_item(window, "homePrimaryPanel") is None
        assert _find_quick_item(window, "homePrimaryScroll") is None
        assert item("refraDarkHeroImage").isVisible()
        assert item("refraDarkProfileSelector").isVisible()
        assert item("refraDarkApplyButton").isEnabled()

        navigation = [item(f"refraDarkNavigationButton{i}") for i in range(7)]
        assert all(button.isVisible() and button.isEnabled() for button in navigation)
        assert navigation[0].property("primary") is True
        assert navigation[0].property("navigationSubtitle") == "总览"
        if app.platformName() == "windows":
            english_menu_title = navigation[0].findChild(
                QObject, "navigationTitleLabel"
            )
            assert english_menu_title is not None
            actual_menu_font = QFontInfo(english_menu_title.property("font"))
            assert actual_menu_font.family().casefold() == "arial black"
            assert actual_menu_font.weight() >= int(QFont.Weight.Black)
            assert actual_menu_font.italic() is True

        window.resize(1280, 820)
        app.processEvents()

        start_button = item("refraDarkStartButton")
        apply_button = item("refraDarkApplyButton")
        assert apply_button.isEnabled() is controller.hasProfile
        assert start_button.isEnabled() is (
            controller.runPhase != "stopping"
            and not bool(item("homePage").property("startPreludePending"))
            and (controller.canStart or controller.running)
        )
        controller._set_run_state("正在停止", "warning", False)
        app.processEvents()
        assert controller.runPhase == "stopping"
        assert not start_button.isEnabled()
        controller._set_run_state("待启动", "neutral", False)
        app.processEvents()
        assert start_button.isEnabled() is controller.canStart

        # Exercise the actual dark menu hit targets, not only their bound
        # page labels. Reduced motion keeps the page transition immediate.
        page_ids = ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS")
        for page_id, button in zip(page_ids, navigation, strict=True):
            controller.setPage("HOME")
            app.processEvents()
            point = button.mapToScene(
                QPointF(button.width() / 2, button.height() / 2)
            )
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point.toPoint())
            app.processEvents()
            assert controller.currentPage == page_id
        controller.setPage("HOME")
        app.processEvents()

        # The overview keeps real long model text reachable instead of
        # truncating it into an unreadable single line.
        long_model = "preview-model/" + "long-model-segment-" * 48
        controller.setModel(long_model)
        app.processEvents()
        model_scroll = item("refraDarkModelScroll")
        model_text = item("refraDarkModelName")
        assert model_text.property("text") == long_model
        model_max = max(
            0.0,
            float(model_scroll.property("contentHeight")) - model_scroll.height(),
        )
        assert model_max > 0
        assert model_scroll.property("clip") is True
        assert model_scroll.property("interactive") is True
        model_origin = model_text.mapToItem(model_scroll, QPointF(0, 0))
        assert 0 <= model_origin.y() < model_scroll.height()

        controller._set_run_state("连接失败：" + "诊断信息较长。" * 12, "error", False)
        app.processEvents()
        run_state = item("refraDarkRunState")
        assert run_state.property("text") == controller.runState
        assert run_state.property("color") == theme.property("danger")
        controller._set_run_state("待启动", "neutral", False)
        app.processEvents()

        display_fonts = theme.property("displayFonts")
        if hasattr(display_fonts, "toVariant"):
            display_fonts = display_fonts.toVariant()
        assert list(display_fonts)[0] == "Arial Narrow"
        assert theme.property("displayCjkFont") == "Microsoft YaHei UI"

        assert _find_quick_item(window, "homeThemeSelector") is None
        preferences_button = item("refraDarkPreferencesButton")
        position = preferences_button.mapToScene(
            QPointF(preferences_button.width() / 2, preferences_button.height() / 2)
        )
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position.toPoint())
        app.processEvents()
        preferences_dialog = window.findChild(QObject, "refraPreferencesDialog")
        assert preferences_dialog is not None
        assert preferences_dialog.property("visible") is True
        dark_theme_selector = item("refraHomeThemeSelector")
        dark_skin_selector = item("refraHomeSkinSelector")
        reduced_motion_toggle = item("refraHomeReducedMotionToggle")
        assert dark_theme_selector.isVisible()
        assert dark_skin_selector.isVisible()
        assert reduced_motion_toggle.isVisible()
        assert reduced_motion_toggle.property("checked") is True
        dark_theme_selector.forceActiveFocus()
        app.processEvents()
        assert dark_theme_selector.property("activeFocus") is True

        # Toggle reduced motion through the real preferences control and make
        # sure its setting remains connected to the shared controller.
        toggle = reduced_motion_toggle.property("indicator")
        assert isinstance(toggle, QQuickItem)
        toggle_point = toggle.mapToScene(QPointF(toggle.width() / 2, toggle.height() / 2))
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=toggle_point.toPoint())
        app.processEvents()
        assert controller.reducedMotion is False
        assert reduced_motion_toggle.property("checked") is False
        controller.setReducedMotion(True)
        app.processEvents()
        assert reduced_motion_toggle.property("checked") is True

        # The active skin's preferences dialog stays bound to the shared
        # Workbench theme preference.
        theme_point = dark_theme_selector.mapToScene(
            QPointF(dark_theme_selector.width() / 2, dark_theme_selector.height() / 2)
        )
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=theme_point.toPoint())
        app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.themePreference == "light"
        assert dark_home.isVisible() and dark_home.isEnabled()
        assert _find_quick_item(window, "homePrimaryPanel") is None
        assert _find_quick_item(window, "homePrimaryScroll") is None
        assert theme.property("refraDark") is False
        assert theme.property("refraStyle") is True
        controller.setTheme("dark")
        app.processEvents()
        assert dark_home.isVisible() and dark_home.isEnabled()
        assert _find_quick_item(window, "homePrimaryPanel") is None
        assert _find_quick_item(window, "homePrimaryScroll") is None

        # The dark preferences dialog can also change skin through its actual
        # selector; Dohna remains fixed-light and Prism restores the approved
        # dark workbench branch with the same current page.
        position = item("refraDarkPreferencesButton").mapToScene(
            QPointF(
                item("refraDarkPreferencesButton").width() / 2,
                item("refraDarkPreferencesButton").height() / 2,
            )
        )
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position.toPoint())
        app.processEvents()
        dark_skin_selector = item("refraHomeSkinSelector")
        dark_skin_selector.forceActiveFocus()
        assert dark_skin_selector.property("activeFocus") is True
        skin_point = dark_skin_selector.mapToScene(
            QPointF(dark_skin_selector.width() / 2, dark_skin_selector.height() / 2)
        )
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=skin_point.toPoint())
        app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.skinPreference == SKIN_DOHNA
        assert controller.effectiveTheme == "light"
        dohna_theme = _theme_for_skin(window, SKIN_DOHNA)
        assert dohna_theme is not None
        assert dohna_theme.property("dohna") is True
        assert item("homePrimaryPanel").isVisible()
        controller.setSkin(SKIN_PRISM)
        controller.setTheme("dark")
        controller.setPage("HOME")
        app.processEvents()
        prism_theme = _theme_for_skin(window, SKIN_PRISM)
        assert prism_theme is not None
        assert prism_theme.property("refraDark") is True
        assert item("refraDarkHome").isVisible()
    finally:
        host.shutdown()


@pytest.mark.parametrize("theme_name", ("dark", "light"))
def test_prism_navigation_motion_retargets_and_settles_across_lifecycle_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme_name: str,
) -> None:
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme(theme_name)
    controller.setReducedMotion(False)
    controller.setPage("HOME")
    host = QmlWorkbenchHost(controller, application=app)

    try:
        host.show()
        window = host.window
        assert window is not None
        window.resize(1280, 820)
        app.processEvents()
        motion = _find_quick_item(window, "prismNavigationMotion0")
        overlay = _find_quick_item(window, "sharedNavigationOverlay")
        theme = _theme_for_skin(window, SKIN_PRISM)
        assert motion is not None
        assert overlay is not None
        assert theme is not None and theme.property("refraStyle") is True

        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=1.0,
            motion_enabled=True,
        )
        home_buttons = []
        for index in range(7):
            visible = [
                item
                for item in _find_quick_items(
                    window,
                    f"refraDarkNavigationButton{index}",
                )
                if item.isVisible()
            ]
            assert len(visible) == 1, (index, len(visible))
            _assert_item_center_inside_window_viewport(window, visible[0])
            home_buttons.append(visible[0])
        home_subtitle = home_buttons[0].findChild(QQuickItem, "navigationSubtitleLabel")
        assert home_subtitle is not None and home_subtitle.isVisible()
        assert home_subtitle.property("text") == "总览"
        assert home_subtitle.property("opacity") == pytest.approx(1.0)
        home_start = _navigation_motion_rect(motion)
        hero_button = home_buttons[2]
        assert len(_find_quick_items(window, "refraDarkNavigationButton2")) == 1
        click_point = hero_button.mapToScene(
            QPointF(hero_button.width() / 2, hero_button.height() / 2),
        ).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=click_point)
        app.processEvents()
        assert controller.currentPage == "OCR"
        first_midpoint = _wait_for_navigation_motion_progress(
            window,
            motion,
            app,
            expected_presentation=0.0,
            start=home_start,
        )
        assert _max_geometry_delta(home_start, first_midpoint) > 1
        assert _max_geometry_delta(
            first_midpoint,
            _navigation_motion_rect(motion, target=True),
        ) > 1
        _wait_for_navigation_subtitle_fade(window, motion, home_subtitle, app)
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=0.0,
            motion_enabled=True,
        )
        rail_buttons = []
        for index in range(7):
            visible = [
                item
                for item in _find_quick_items(window, f"navigationButton{index}")
                if item.isVisible()
            ]
            assert len(visible) == 1, (index, len(visible))
            _assert_item_center_inside_window_viewport(window, visible[0])
            rail_buttons.append(visible[0])
        rail_subtitle = rail_buttons[0].findChild(QQuickItem, "navigationSubtitleLabel")
        assert rail_subtitle is not None and rail_subtitle.isVisible()
        assert rail_subtitle.property("text") == "总览"
        assert rail_subtitle.property("opacity") == pytest.approx(1.0)

        rail_start = _navigation_motion_rect(motion)
        rail_button = rail_buttons[0]
        assert len(_find_quick_items(window, "navigationButton0")) == 1
        click_point = rail_button.mapToScene(
            QPointF(rail_button.width() / 2, rail_button.height() / 2),
        ).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=click_point)
        app.processEvents()
        assert controller.currentPage == "HOME"
        rail_to_home_midpoint = _wait_for_navigation_motion_progress(
            window,
            motion,
            app,
            expected_presentation=1.0,
            start=rail_start,
        )
        assert _max_geometry_delta(rail_start, rail_to_home_midpoint) > 1
        assert _max_geometry_delta(
            rail_to_home_midpoint,
            _navigation_motion_rect(motion, target=True),
        ) > 1
        _wait_for_navigation_subtitle_fade(window, motion, rail_subtitle, app)
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=1.0,
            motion_enabled=True,
        )
        assert home_subtitle.property("opacity") == pytest.approx(1.0)

        reversal_start = _navigation_motion_rect(motion)
        next_hero_button = home_buttons[1]
        click_point = next_hero_button.mapToScene(
            QPointF(next_hero_button.width() / 2, next_hero_button.height() / 2),
        ).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=click_point)
        app.processEvents()
        assert controller.currentPage == "CAPTURE"
        _wait_for_navigation_motion_progress(
            window,
            motion,
            app,
            expected_presentation=0.0,
            start=reversal_start,
        )
        reversal_start = _navigation_motion_rect(motion)
        controller.setPage("HOME")
        app.processEvents()
        assert controller.currentPage == "HOME"
        reverse_midpoint = _wait_for_navigation_motion_progress(
            window,
            motion,
            app,
            expected_presentation=1.0,
            start=reversal_start,
            toward_latest_target=True,
        )
        assert _max_geometry_delta(reverse_midpoint, reversal_start) > 1
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=1.0,
            motion_enabled=True,
        )

        window.resize(1100, 760)
        app.processEvents()
        assert window.property("navigationResizeActive") is True
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=1.0,
            motion_enabled=True,
        )

        window.hide()
        app.processEvents()
        assert window.isVisible() is False
        controller.setPage("OVERLAY")
        app.processEvents()
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=0.0,
            motion_enabled=False,
        )
        host.show()
        app.processEvents()
        assert window.isVisible() is True
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=0.0,
            motion_enabled=True,
        )

        controller.setReducedMotion(True)
        controller.setPage("HOME")
        app.processEvents()
        assert window.property("navigationMotionEnabled") is False
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=1.0,
            motion_enabled=False,
        )
        controller.setPage("SETTINGS")
        app.processEvents()
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=0.0,
            motion_enabled=False,
        )

        controller.setSkin(SKIN_DOHNA)
        app.processEvents()
        dohna_theme = _theme_for_skin(window, SKIN_DOHNA)
        assert dohna_theme is not None
        assert dohna_theme.property("refraStyle") is False
        assert overlay.property("visible") is False
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=0.0,
            motion_enabled=False,
        )
        visible_dohna_buttons = [
            item
            for item in _find_quick_items(window, "navigationButton0")
            if item.isVisible()
        ]
        assert len(visible_dohna_buttons) == 1

        controller.setSkin(SKIN_PRISM)
        app.processEvents()
        prism_theme = _theme_for_skin(window, SKIN_PRISM)
        assert prism_theme is not None
        assert prism_theme.property("refraStyle") is True
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=0.0,
            motion_enabled=False,
        )
        assert overlay.property("visible") is True
        assert window.property("navigationMotionEnabled") is False

        controller.setReducedMotion(False)
        controller.setPage("HOME")
        app.processEvents()
        _wait_for_navigation_motion_settled(
            window,
            motion,
            app,
            expected_presentation=1.0,
            motion_enabled=True,
        )
        _assert_zero_progress_retarget_stops_old_animation(motion, app)
    finally:
        host.shutdown()


@pytest.mark.parametrize("theme_name", ("dark", "light"))
def test_prism_action_motion_preserves_start_and_apply_handlers_on_both_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme_name: str,
) -> None:
    class RecordingController(WorkbenchController):
        def __init__(self, config_path: Path) -> None:
            super().__init__(config_path, probe_ocr_devices=False)
            self.toggle_calls = 0

        @Slot()
        def toggleLive(self) -> None:  # noqa: N802
            self.toggle_calls += 1

    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = RecordingController(config_path)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme(theme_name)
    controller.setReducedMotion(False)
    controller.setPage("HOME")
    host = QmlWorkbenchHost(controller, application=app)

    try:
        host.show()
        window = host.window
        assert window is not None
        app.processEvents()
        start_motion = _find_quick_item(window, "prismActionMotion0")
        apply_motion = _find_quick_item(window, "prismActionMotion1")
        assert start_motion is not None and apply_motion is not None
        _wait_for_action_motion_settled(
            window,
            start_motion,
            app,
            motion_enabled=True,
        )
        _wait_for_action_motion_settled(
            window,
            apply_motion,
            app,
            motion_enabled=True,
        )
        _assert_item_inside_window_viewport(
            window,
            _find_quick_item(window, "refraDarkStartButton"),
        )
        _assert_item_inside_window_viewport(
            window,
            _find_quick_item(window, "refraDarkApplyButton"),
        )

        def visible_button(object_name: str) -> QQuickItem:
            matches = [
                item
                for item in _find_quick_items(window, object_name)
                if item.isVisible()
            ]
            assert len(matches) == 1, (object_name, len(matches))
            assert matches[0].isEnabled(), object_name
            return matches[0]

        def click(target: QQuickItem) -> None:
            assert target.isVisible() and target.isEnabled()
            position = target.mapToScene(
                QPointF(target.width() / 2, target.height() / 2),
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
            app.processEvents()

        def wait_for_toggle_calls(expected: int) -> None:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                app.processEvents()
                if controller.toggle_calls == expected:
                    return
                QTest.qWait(20)
            assert controller.toggle_calls == expected

        home_start_rect = _navigation_motion_rect(start_motion)
        home_apply_rect = _navigation_motion_rect(apply_motion)
        click(visible_button("refraDarkNavigationButton1"))
        assert controller.currentPage == "CAPTURE"
        _wait_for_action_motion_progress(
            window,
            start_motion,
            app,
            start=home_start_rect,
        )
        _wait_for_action_motion_progress(
            window,
            apply_motion,
            app,
            start=home_apply_rect,
        )
        _wait_for_action_motion_settled(
            window,
            start_motion,
            app,
            motion_enabled=True,
        )
        _wait_for_action_motion_settled(
            window,
            apply_motion,
            app,
            motion_enabled=True,
        )

        _assert_item_inside_window_viewport(
            window,
            visible_button("darkStartLiveButton"),
        )
        _assert_item_inside_window_viewport(
            window,
            visible_button("darkSaveAllButton"),
        )
        assert len(_find_quick_items(window, "darkStartLiveButton")) == 1
        assert len(_find_quick_items(window, "darkSaveAllButton")) == 1
        previous_debug = controller.debugEnabled
        controller.setDebugEnabled(not previous_debug)
        assert controller.settingsDirty is True
        click(visible_button("darkSaveAllButton"))
        assert controller.settingsDirty is False
        saved_profile = load_game_profile(
            config_path,
            load_config(config_path),
            "game",
        )
        assert saved_profile.runtime_settings.live.debug_border is not previous_debug

        click(visible_button("darkStartLiveButton"))
        assert window.property("startPreludePending") is True
        wait_for_toggle_calls(1)
        assert controller._live_process is None
        assert window.property("startPreludePending") is False

        rail_start_rect = _navigation_motion_rect(start_motion)
        rail_apply_rect = _navigation_motion_rect(apply_motion)
        click(visible_button("navigationButton0"))
        assert controller.currentPage == "HOME"
        _wait_for_action_motion_progress(
            window,
            start_motion,
            app,
            start=rail_start_rect,
        )
        _wait_for_action_motion_progress(
            window,
            apply_motion,
            app,
            start=rail_apply_rect,
        )
        _wait_for_action_motion_settled(
            window,
            start_motion,
            app,
            motion_enabled=True,
        )
        _wait_for_action_motion_settled(
            window,
            apply_motion,
            app,
            motion_enabled=True,
        )

        _assert_item_inside_window_viewport(
            window,
            visible_button("refraDarkStartButton"),
        )
        _assert_item_inside_window_viewport(
            window,
            visible_button("refraDarkApplyButton"),
        )
        assert len(_find_quick_items(window, "refraDarkStartButton")) == 1
        assert len(_find_quick_items(window, "refraDarkApplyButton")) == 1
        controller.setDebugEnabled(previous_debug)
        assert controller.settingsDirty is True
        click(visible_button("refraDarkApplyButton"))
        assert controller.settingsDirty is False
        saved_profile = load_game_profile(
            config_path,
            load_config(config_path),
            "game",
        )
        assert saved_profile.runtime_settings.live.debug_border is previous_debug

        click(visible_button("refraDarkStartButton"))
        assert window.property("startPreludePending") is True
        wait_for_toggle_calls(2)
        assert controller._live_process is None
        assert window.property("startPreludePending") is False
        _assert_zero_progress_retarget_stops_old_animation(start_motion, app)
        _assert_zero_progress_retarget_stops_old_animation(apply_motion, app)
    finally:
        host.shutdown()


@pytest.mark.parametrize("theme_name", ("dark", "light"))
def test_refra_dark_home_surfaces_save_state_and_preferences_hotkey_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme_name: str,
) -> None:
    # Keep this real QML interaction isolated from the user's global shortcut.
    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    controller.setSkin(SKIN_PRISM)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    controller.setPage("HOME")
    app.processEvents()

    try:
        def item(name: str) -> QQuickItem:
            result = _find_quick_item(window, name)
            assert result is not None, name
            return result

        def click(target: QQuickItem) -> None:
            assert target.isVisible() and target.isEnabled(), target.objectName()
            position = target.mapToScene(
                QPointF(target.width() / 2, target.height() / 2),
            ).toPoint()
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
            app.processEvents()

        # The compact operation strip remains in the approved home composition
        # at both supported sizes, and follows controller status rather than
        # displaying preview-only copy.
        for width, height in ((980, 700), (1280, 820)):
            window.resize(width, height)
            app.processEvents()
            actions = item("refraDarkHomeActions")
            feedback = item("refraDarkHomeActionFeedback")
            status_row = item("refraDarkHomeFeedbackRow")
            status = item("refraDarkHomeStatusText")
            assert feedback.isVisible() and status_row.isVisible() and status.isVisible()
            assert status.property("text") == controller.statusText
            for child in (feedback, status_row, status):
                origin = child.mapToItem(actions, QPointF(0, 0))
                assert origin.x() >= -0.5 and origin.y() >= -0.5
                assert origin.x() + child.width() <= actions.width() + 0.5
                assert origin.y() + child.height() <= actions.height() + 0.5

        # Change a real Settings control, return through the shared visible
        # navigation, and apply from the dark home action.
        controller.setPage("SETTINGS")
        app.processEvents()
        form = item("settingsFormScroll")
        debug_toggle = item("settingsDebugToggle")
        indicator = debug_toggle.property("indicator")
        assert isinstance(indicator, QQuickItem)
        toggle_origin = debug_toggle.mapToItem(form, QPointF(0, 0))
        max_scroll = max(0.0, float(form.property("contentHeight")) - form.height())
        form.setProperty(
            "contentY",
            max(
                0.0,
                min(
                    max_scroll,
                    float(form.property("contentY"))
                    + toggle_origin.y()
                    - max(0.0, (form.height() - debug_toggle.height()) / 2),
                ),
            ),
        )
        app.processEvents()
        before_debug = controller.debugEnabled
        click(indicator)
        assert controller.debugEnabled is not before_debug
        assert controller.settingsDirty is True

        home_navigation = item("navigationButton0")
        click(home_navigation)
        assert controller.currentPage == "HOME"
        unsaved = item("refraDarkHomeUnsavedStatus")
        status = item("refraDarkHomeStatusText")
        assert unsaved.isVisible()
        assert unsaved.property("text") == "有未应用更改"
        assert unsaved.property("color") == window.findChild(QObject, "prismTheme").property("amber")
        assert status.isVisible() is False

        click(item("refraDarkApplyButton"))
        assert controller.settingsDirty is False
        status = item("refraDarkHomeStatusText")
        assert status.isVisible()
        assert status.property("text") == controller.statusText
        assert "已应用" in controller.statusText
        theme = window.findChild(QObject, "prismTheme")
        expected_status_accent = (
            theme.property("electric")
            if theme.property("refraLight")
            else theme.property("accent")
        )
        assert status.property("color") == expected_status_accent
        saved_profile = load_game_profile(
            controller._config_path,
            load_config(controller._config_path),
            "game",
        )
        assert saved_profile.runtime_settings.live.debug_border is controller.debugEnabled

        # Exercise the replacement preferences entry by physical clicks. A
        # special key is accepted, Esc cancels, and a registrar conflict keeps
        # the current value while opening the existing error dialog.
        click(item("refraDarkPreferencesButton"))
        dialog = window.findChild(QObject, "refraPreferencesDialog")
        field = item("refraHotkeyField")
        display = item("refraHotkeyDisplay")
        record = item("refraHotkeyRecordButton")
        recording_hint = item("refraHotkeyRecordingHint")
        assert dialog is not None and dialog.property("visible") is True
        assert field.isVisible() and display.isVisible() and record.isVisible()

        click(record)
        assert recording_hint.isVisible()
        assert field.property("activeFocus") is True
        QTest.keyClick(window, Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert controller.hotkeyPreference == "Ctrl+Backspace"
        assert display.property("text") == controller.hotkeyPreference
        assert recording_hint.isVisible() is False

        old_hotkey = controller.hotkeyPreference
        click(record)
        assert recording_hint.isVisible()
        QTest.keyClick(window, Qt.Key.Key_Escape)
        app.processEvents()
        assert controller.hotkeyPreference == old_hotkey
        assert display.property("text") == old_hotkey
        assert recording_hint.isVisible() is False

        def reject_hotkey(_value: str) -> None:
            raise runtime_module.GuiRuntimeError("快捷键已被其他程序占用")

        controller.set_hotkey_registrar(reject_hotkey)
        click(record)
        QTest.keyClick(
            window,
            Qt.Key.Key_K,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        )
        app.processEvents()
        error_dialog = window.findChild(QObject, "errorDialog")
        assert controller.hotkeyPreference == old_hotkey
        assert error_dialog is not None and error_dialog.property("visible") is True
        assert error_dialog.property("errorMessage") == "快捷键已被其他程序占用"
    finally:
        host.shutdown()


@pytest.mark.parametrize("font_state", ["missing", "registration-fails"])
def test_workbench_starts_when_optional_system_display_font_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    font_state: str,
) -> None:
    app = _application()
    font_directory = tmp_path / "Fonts"
    font_directory.mkdir()
    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.setattr(host_module, "_SYSTEM_DISPLAY_FONTS_CHECKED", False)
    monkeypatch.setattr(host_module, "_REGISTERED_DISPLAY_FONT_IDS", [])

    if font_state == "registration-fails":
        for filename in (
            "ARIALN.TTF",
            "ARIALNB.TTF",
            "ARIALNI.TTF",
            "ARIALNBI.TTF",
            "ARIBLK.TTF",
        ):
            (font_directory / filename).touch()

        def fail_registration(_path: str) -> int:
            raise RuntimeError("font unavailable")

        monkeypatch.setattr(
            host_module.QFontDatabase,
            "addApplicationFont",
            fail_registration,
        )

    with monkeypatch.context() as platform_override:
        platform_override.setattr(host_module.sys, "platform", "win32")
        host_module._register_optional_system_display_fonts()
    assert host_module._SYSTEM_DISPLAY_FONTS_CHECKED is True
    assert host_module._REGISTERED_DISPLAY_FONT_IDS == []

    monkeypatch.setattr(host_module.WindowsGlobalHotkey, "register", lambda *_args: None)
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "font-fallback",
        display_name="字体回退启动测试",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        app.processEvents()
        assert host.window is not None
        dark_home = _find_quick_item(host.window, "refraDarkHome")
        assert dark_home is not None and dark_home.isVisible()
    finally:
        host.shutdown()


def test_qml_sources_use_explicit_unavailable_states_without_mock_timers() -> None:
    qml_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "game_screen_translator"
        / "gui"
        / "qml"
    )
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(qml_root.rglob("*.qml"))
    )

    assert 'readonly property var pageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]' in sources
    assert "LAST RUN OCR · UNAVAILABLE" in sources
    assert "LAST RUN TRANSLATION · UNAVAILABLE" in sources
    assert "LAST RUN CACHE · UNAVAILABLE" in sources
    assert "Math.random" not in sources
    assert 'objectName: "startPreludeTimer"' in sources
    assert 'interval: 400' in sources
    assert re.search(r"workbench\.apiKey\b", sources) is None
    assert re.search(
        r"font\.family:\s*(?:(?:root\.)?theme|prism)\."
        r"(?:uiFont|displayFont|monoFont)\b",
        sources,
    ) is None

    prism_root = qml_root / "skins" / "prism"
    dohna_root = qml_root / "skins" / "dohna"
    prism_workbench_source = (prism_root / "Workbench.qml").read_text(
        encoding="utf-8"
    )
    dohna_workbench_source = (dohna_root / "Workbench.qml").read_text(
        encoding="utf-8"
    )
    capture_source = (prism_root / "pages" / "CapturePage.qml").read_text(
        encoding="utf-8"
    )
    ocr_source = (prism_root / "pages" / "OcrPage.qml").read_text(encoding="utf-8")
    settings_source = (prism_root / "pages" / "SettingsPage.qml").read_text(
        encoding="utf-8"
    )
    main_source = (qml_root / "Main.qml").read_text(encoding="utf-8")
    title_source = (dohna_root / "components" / "RefractedTitle.qml").read_text(
        encoding="utf-8"
    )
    feedback_source = (prism_root / "components" / "PrismFeedbackLayer.qml").read_text(
        encoding="utf-8"
    )
    motion_source = (prism_root / "components" / "PrismMotionFeedback.qml").read_text(
        encoding="utf-8"
    )
    fold_source = (prism_root / "components" / "PrismFoldRule.qml").read_text(
        encoding="utf-8"
    )
    assert '"captureCustomAction"' in capture_source
    assert "selectRegion()" in capture_source
    assert 'text: "框选区域"' not in capture_source
    assert 'text: "保存区域"' not in capture_source
    assert 'root.visualAction("scan")' in capture_source
    assert 'title: "捕获区域"' in capture_source
    assert 'title: "字幕区域"' not in capture_source
    assert "CAPTURE PREVIEW · UNAVAILABLE" not in capture_source
    assert "实时捕获画面未接入工作台" not in capture_source
    assert "itemEnabled: root.workbench.ocrDeviceAvailability" in ocr_source
    assert '"ocrProbeAction"' in ocr_source
    assert '"ocrQualitySlider"' in ocr_source
    assert "stepSize: 1" in ocr_source
    assert 'root.visualAction("focus")' in ocr_source
    assert ocr_source.count("setTriggerMethodIndex") == 1
    assert ocr_source.count("setMouseDwellMs") == 1
    assert "setTriggerMethodIndex" not in settings_source
    assert "setMouseDwellMs" not in settings_source
    assert settings_source.count('root.visualAction("calibrate")') >= 8
    assert '"darkSaveAllButton"' in prism_workbench_source
    assert 'root.pulseVisualAction("calibrate")' in prism_workbench_source
    assert "PrismMotionFeedback" in prism_workbench_source
    assert "PrismFeedbackLayer" in prism_workbench_source
    assert "DohnaFeedbackLayer" not in prism_workbench_source
    assert "PrismMotionFeedback" not in dohna_workbench_source
    assert "PrismFeedbackLayer" not in dohna_workbench_source
    assert "navigationTargetBounds" not in dohna_workbench_source
    assert "OpticalStage {" not in prism_workbench_source
    assert "TransientFeedbackLayer {" not in prism_workbench_source
    assert "pageTransitionSweep" not in prism_workbench_source
    assert '"prismActionFeedbackRule"' in feedback_source
    assert '"prismStartProgressRule"' in feedback_source
    assert 'property real actionProgress: 1' in motion_source
    assert 'function settleMotion()' in motion_source
    assert "ShapePath" not in fold_source
    assert '"prismDividerLine"' in fold_source
    assert "pageTitleCyanSlice" not in title_source
    assert "pageTitleSpectrumSlice" not in title_source
    assert "style: Text.Raised" not in title_source
    assert "font.weight: Font.Bold" in title_source
    assert title_source.count("renderType: Text.CurveRendering") == 2
    assert title_source.count(
        "renderTypeQuality: Text.VeryHighRenderTypeQuality"
    ) == 2
    assert "layer.enabled: true" not in title_source
    assert '"pageHeaderUnderline"' in dohna_workbench_source

    assert 'import "skins/prism" as PrismSkin' in main_source
    assert 'import "skins/dohna" as DohnaSkin' in main_source
    assert "PrismSkin.Workbench" in main_source
    assert "DohnaSkin.Workbench" in main_source
    assert "workbench.setSkin" not in main_source
    skin_sources = {
        "prism": sorted(prism_root.rglob("*.qml")),
        "dohna": sorted(dohna_root.rglob("*.qml")),
    }
    for skin_source in (prism_workbench_source, dohna_workbench_source):
        assert re.search(
            r"(?:root\.)?theme\.(?:dohna|refraStyle)\b|"
            r"prism\.(?:dohna|refraStyle)\b",
            skin_source,
        ) is None
    for skin_name, skin_files in skin_sources.items():
        skin_root = prism_root if skin_name == "prism" else dohna_root
        assert len([path for path in skin_files if path.parent.name == "pages"]) == 7
        assert any(path.name == "Workbench.qml" for path in skin_files)
        assert any(path.name.endswith("Theme.qml") for path in skin_files)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in skin_files)
        assert not re.search(r'import\s+"[^\"]*(?:skins/)?(?:prism|dohna)(?:/|\")', combined)
        for path in skin_files:
            if path.name.endswith("Theme.qml"):
                continue
            assert re.search(
                r"(?:root\.)?theme\.(?:dohna|refraStyle)\b|"
                r"prism\.(?:dohna|refraStyle)\b",
                path.read_text(encoding="utf-8"),
            ) is None, (
                f"skin-specific visual branch remains in "
                f"{skin_name}/{path.relative_to(skin_root)}"
            )
        if skin_name == "prism":
            assert 'import "components"' in prism_workbench_source
            assert 'import "pages"' in prism_workbench_source
            assert "PrismNavigationMotion.qml" in {
                path.name for path in (prism_root / "components").glob("*.qml")
            }
            assert "PrismP3ActionMotion.qml" in {
                path.name for path in (prism_root / "components").glob("*.qml")
            }
        else:
            assert {"DohnaBackdrop.qml", "DohnaFeedbackLayer.qml", "RefractedTitle.qml"} <= {
                path.name for path in (dohna_root / "components").glob("*.qml")
            }
            assert not {
                "PrismNavigationMotion.qml",
                "PrismP3ActionMotion.qml",
                "PrismFeedbackLayer.qml",
            } & {path.name for path in (dohna_root / "components").glob("*.qml")}


@pytest.mark.parametrize("skin,theme_name", [
    (SKIN_PRISM, "dark"), (SKIN_PRISM, "light"), (SKIN_DOHNA, "light"),
])
def test_cache_large_metrics_and_multiline_hits_stay_clear_of_scrollbar(
    tmp_path: Path, skin: str, theme_name: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path, load_config(config_path), "cache-layout", display_name="缓存布局测试夹具",
    )
    save_snapshot(profile.directory, new_snapshot(
        (SnapshotEntry("track", 0, "布局测试原文", "布局测试译文", 0.9, (20, 40, 420, 75)),),
        tuple(CacheHit(f"CONTROLS - BASIC MOVEMENT {i}\n" + "长缓存原文 " * 12, 10882 - i)
                  for i in range(5)), ocr_peak_seconds=None, llm_peak_seconds=None,
    ))
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    controller.setPage("CACHE")
    controller._set_cache_stats(CacheStats(
        automatic_entries=4649, automatic_hits=10882, manual_corrections=12345678, manual_hits=0,
    ))
    host = QmlWorkbenchHost(controller, application=app)
    try:
        window = host.window
        assert window is not None
        host.show()
        panel = _find_quick_item(window, "cachePrimaryPanel")
        assert panel is not None
        for width, height in ((980, 700), (1280, 820), (1600, 900)):
            window.resize(max(width, window.minimumWidth()), height)
            _wait_for_page_layout(window, panel, app)
            corrections = _find_quick_item(window, "correctionsEditor")
            secondary = _find_quick_item(window, "cacheSecondaryPanel")
            assert corrections is not None and corrections.isVisible()
            assert secondary is not None
            assert corrections.isEnabled()
            assert corrections.width() > 0 and corrections.height() > 0
            origin = corrections.mapToItem(secondary, QPointF(0, 0))
            assert origin.x() >= 0 and origin.y() >= 0
            assert origin.x() + corrections.width() <= secondary.width()
            assert origin.y() + corrections.height() <= secondary.height()
            assert _visible_text_items(secondary, "人工修订")
            assert not _visible_text_items(window, "自动缓存")
            assert not _visible_text_items(window, "暂不支持浏览自动缓存明细")
            grid = _find_quick_item(panel, "cacheSummaryMetrics")
            assert grid is not None
            assert grid.property("columns") == (4 if grid.width() >= 510 else 2)
            values = _find_quick_items(panel, "cacheMetricValue")
            assert {value.property("text") for value in values} == {"4649", "10882", "12345678", "0"}
            for value in values:
                card = value.parentItem().parentItem()
                origin = value.mapToItem(card, QPointF(0, 0))
                assert origin.x() >= 11.5
                assert origin.x() + value.width() <= card.width() - 11.5
                assert value.property("contentWidth") <= value.width() + 0.5
                assert value.property("contentHeight") <= value.height() + 0.5
                assert not value.property("truncated")
            scroll = _find_quick_item(panel, "cacheLastRunHits")
            assert scroll is not None
            bar = _find_quick_item(scroll, "prismScrollBar")
            assert bar is not None
            lane_left = bar.mapToItem(scroll, QPointF(0, 0)).x()
            content = scroll.property("contentItem")
            form = next(child for child in content.childItems() if child.width() > 30)
            for child in form.childItems():
                if child.isVisible():
                    origin = child.mapToItem(scroll, QPointF(0, 0))
                    assert origin.x() + child.width() <= lane_left - 7.5
            for name in ("cacheHitSource", "cacheHitCount"):
                texts = _find_quick_items(scroll, name)
                assert len(texts) == 5
                for text in texts:
                    origin = text.mapToItem(scroll, QPointF(0, 0))
                    assert origin.x() + text.width() <= lane_left - 7.5
                    assert text.property("lineCount") == 1
                    assert text.property("contentHeight") <= text.parentItem().height() + 0.5
                    if name == "cacheHitCount":
                        assert not text.property("truncated")
            screenshot_dir = os.environ.get("REFRA_CACHE_SCREENSHOT_DIR")
            if screenshot_dir:
                destination = Path(screenshot_dir)
                destination.mkdir(parents=True, exist_ok=True)
                QTest.qWait(80)
                assert window.grabWindow().save(str(destination / f"cache-fixture-{skin}-{theme_name}-{width}.png"))
            maximum = max(0, scroll.property("contentHeight") - scroll.height())
            scroll.setProperty("contentY", maximum)
            app.processEvents()
            hint = _find_quick_item(scroll, "cacheSummarySourceHint")
            assert hint is not None
            hint_origin = hint.mapToItem(scroll, QPointF(0, 0))
            assert hint_origin.y() >= -0.5
            assert hint_origin.y() + hint.height() <= scroll.height() + 0.5
            scroll.setProperty("contentY", 0)
    finally:
        host.shutdown()


def test_cache_page_hides_numeric_metrics_without_a_profile(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setPage("CACHE")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    metrics = window.findChild(QObject, "cacheSummaryMetrics")
    assert metrics is not None
    assert metrics.property("visible") is False
    visible_text = {
        str(item.property("text"))
        for item in window.findChildren(QObject)
        if item.property("visible") is True and item.property("text") is not None
    }
    assert "尚未选择 Profile" in visible_text
    assert controller.hasProfile is False
    host.shutdown()


def test_region_selector_accepts_or_cancels_then_restores_workbench() -> None:
    controller = _ControllerStub()
    selectors: list[_SelectorStub] = []

    def make_selector(_screen) -> _SelectorStub:
        selector = _SelectorStub()
        selectors.append(selector)
        return selector

    host, engine = _host(controller, selector_factory=make_selector)
    host.show()
    first_window = host.window
    assert first_window is not None

    controller.regionSelectionRequested.emit(0)
    assert not first_window.isVisible()
    assert selectors[-1].opened is True
    selectors[-1].selected_region = (10, 20, 800, 300)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Accepted))
    assert controller.accepted_regions == [(10, 20, 800, 300)]
    assert first_window.isVisible()

    controller.regionSelectionRequested.emit(0)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    assert controller.cancel_count == 1
    assert first_window.isVisible()

    controller.regionSelectionRequested.emit(0)
    controller.liveReady.emit()
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    assert controller.cancel_count == 2
    assert host.window is None
    assert engine.root.release_count == 1
    controller.liveFailed.emit()
    restored_window = host.window
    assert restored_window is not None
    assert restored_window.isVisible()

    restored_window.close()


def test_region_selector_construction_failure_is_reported_without_escaping() -> None:
    controller = _ControllerStub()

    def fail_selector(_screen):
        raise RuntimeError("selector unavailable")

    host, _engine = _host(controller, selector_factory=fail_selector)
    host.show()

    controller.regionSelectionRequested.emit(0)

    window = host.window
    assert window is not None
    assert window.isVisible() is True
    assert controller.cancel_count == 1
    assert controller.host_errors == [
        ("无法打开区域选择器", "selector unavailable")
    ]
    host.shutdown()


def test_about_to_quit_uses_shutdown_without_stopping_live() -> None:
    controller = _ControllerStub()
    application = _ApplicationRecorder()
    host, _engine = _host(controller, application=application)

    application.aboutToQuit.emit()
    host.shutdown()

    assert controller.shutdown_count == 1
    assert controller.stop_count == 0
    assert host.window is None


def test_real_host_and_controller_rebuild_workbench_after_live_exit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )

    class ProcessStub:
        pid = 4321

        def __init__(self) -> None:
            self.return_code: int | None = None
            self.poll_count = 0

        def poll(self) -> int | None:
            self.poll_count += 1
            return self.return_code

        def terminate(self) -> None:
            self.return_code = 0

    process = ProcessStub()
    monkeypatch.setattr(
        controller_module,
        "_validate_ocr_device_isolated",
        lambda _device: "gpu:0 · integration test",
    )
    monkeypatch.setattr(
        controller_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    host = QmlWorkbenchHost(controller, application=app)
    controller.setPage("TRANSLATION")
    host.show()
    first_window = host.window
    assert first_window is not None

    translation_page = first_window.findChild(QObject, "translationPage")
    glossary_editor = first_window.findChild(QObject, "glossaryEditor")
    assert translation_page is not None
    assert glossary_editor is not None
    first_window.setProperty("translationSideMode", "glossary")
    app.processEvents()
    add_row_button = glossary_editor.findChild(QObject, "addPairRowButton")
    assert add_row_button is not None
    click_position = add_row_button.mapToScene(
        QPointF(
            add_row_button.property("width") / 2,
            add_row_button.property("height") / 2,
        )
    ).toPoint()
    QTest.mouseClick(
        first_window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        click_position,
    )
    app.processEvents()
    assert glossary_editor.property("entryCount") == 1
    assert glossary_editor.property("dirty") is True
    assert controller.glossaryEntries == [{"source": "", "target": ""}]
    assert controller.glossaryDirty is True
    first_window.update()
    QTest.qWait(20)
    app.processEvents()
    source_field = _find_quick_item(first_window, "pairSourceField-0")
    target_field = _find_quick_item(first_window, "pairTargetField-0")
    assert source_field is not None
    assert target_field is not None
    source_field.forceActiveFocus()
    _key_clicks(first_window, "unsaved source")
    target_field.forceActiveFocus()
    _key_clicks(first_window, "unsaved target")
    app.processEvents()
    assert controller.glossaryEntries == [
        {"source": "unsaved source", "target": "unsaved target"}
    ]
    controller.setPage("OCR")

    controller.startLive()
    app.processEvents()

    assert controller.runPhase == "running"
    assert controller._live_monitor.isActive() is True
    assert host.window is None
    assert host.engine is None
    polls_while_hidden = process.poll_count
    controller._check_live_process()
    assert process.poll_count > polls_while_hidden
    assert controller._live_monitor.isActive() is True

    process.return_code = 0
    controller._check_live_process()
    app.processEvents()

    restored_window = host.window
    assert restored_window is not None
    assert restored_window is not first_window
    assert restored_window.isVisible() is True
    restored_stack = restored_window.findChild(QObject, "pageStack")
    assert restored_stack is not None
    assert restored_stack.property("currentIndex") == 2
    restored_editor = restored_window.findChild(QObject, "glossaryEditor")
    assert restored_editor is not None
    assert restored_editor.property("entryCount") == 1
    assert restored_editor.property("dirty") is True
    restored_source = _find_quick_item(restored_window, "pairSourceField-0")
    restored_target = _find_quick_item(restored_window, "pairTargetField-0")
    assert restored_source is not None
    assert restored_target is not None
    assert restored_source.property("text") == "unsaved source"
    assert restored_target.property("text") == "unsaved target"
    assert controller.glossaryDirty is True
    assert controller._live_monitor.isActive() is False
    assert controller.runPhase == "stopped"

    process.return_code = None
    controller.startLive()
    app.processEvents()
    assert host.window is None
    process.return_code = 7
    controller._check_live_process()
    app.processEvents()

    failed_window = host.window
    assert failed_window is not None
    error_dialog = failed_window.findChild(QObject, "errorDialog")
    assert error_dialog is not None
    assert error_dialog.property("visible") is True
    assert controller.runPhase == "failed"
    failed_editor = failed_window.findChild(QObject, "glossaryEditor")
    assert failed_editor is not None
    assert failed_editor.property("entryCount") == 1
    assert failed_editor.property("dirty") is True
    host.shutdown()


def test_run_keeps_config_duration_and_probe_compatibility(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = {}

    class ApplicationStub:
        @staticmethod
        def instance():
            return None

        def __init__(self, arguments) -> None:
            calls["arguments"] = arguments

        def setApplicationName(self, value: str) -> None:  # noqa: N802
            calls["application_name"] = value

        def setApplicationDisplayName(self, value: str) -> None:  # noqa: N802
            calls["display_name"] = value

        def platformName(self) -> str:  # noqa: N802
            return "test"

        def primaryScreen(self):  # noqa: N802
            return None

        def quit(self) -> None:
            calls["quit"] = True

        def exec(self) -> int:
            return 17

    class ControllerStub:
        def __init__(self, config_path: Path, *, probe_ocr_devices: bool) -> None:
            calls["controller"] = (config_path, probe_ocr_devices)

        def shutdown(self) -> None:
            calls["controller_shutdown"] = calls.get("controller_shutdown", 0) + 1

    class HostStub:
        def __init__(self, controller, *, application) -> None:
            calls["host"] = (controller, application)
            self.window = object()

        def show(self) -> None:
            calls["shown"] = True

        def shutdown(self) -> None:
            calls["host_shutdown"] = True

    class TimerStub:
        @staticmethod
        def singleShot(milliseconds: int, callback) -> None:  # noqa: N802
            calls.setdefault("timers", []).append((milliseconds, callback))

    monkeypatch.setattr(host_module, "QApplication", ApplicationStub)
    monkeypatch.setattr(host_module, "WorkbenchController", ControllerStub)
    monkeypatch.setattr(host_module, "QmlWorkbenchHost", HostStub)
    monkeypatch.setattr(host_module, "QTimer", TimerStub)

    config_path = tmp_path / "config.toml"
    assert host_module.run(
        config_path,
        duration_seconds=0.25,
        probe_ocr_devices=False,
    ) == 17

    assert calls["controller"] == (config_path, False)
    assert [milliseconds for milliseconds, _callback in calls["timers"]] == [0, 250]
    assert calls["shown"] is True
    assert calls["host_shutdown"] is True


def test_skin_switch_transfers_shared_ui_session_and_scroll_state(
    tmp_path: Path,
) -> None:
    app, controller, host, window = _real_home_hotkey_host(
        tmp_path,
        display_name="高级设置滚动继承验证 " + "长名称用于验证诊断换行。" * 36,
    )
    window.setWidth(980)
    window.setHeight(700)
    app.processEvents()
    original_window = window
    try:
        assert window.property("boundWorkbench") == controller

        controller.setPage("TRANSLATION")
        app.processEvents()
        glossary_button = next(
            item
            for item in window.findChildren(QQuickItem)
            if item.isVisible() and item.property("text") == "术语表"
        )
        assert QMetaObject.invokeMethod(glossary_button, "click") is True
        app.processEvents()
        assert window.property("translationSideMode") == "glossary"

        controller.setPage("HOME")
        controller.setSkin(SKIN_DOHNA)
        QTest.qWait(30)
        app.processEvents()
        controller.setPage("TRANSLATION")
        QTest.qWait(30)
        app.processEvents()
        dohna_translation = window.findChild(QObject, "translationPage")
        assert dohna_translation is not None
        assert dohna_translation.property("sideMode") == "glossary"
        assert window.findChildren(QObject, "translationPage") == [dohna_translation]

        def find_flickable(scroll_name: str) -> QObject:
            scroll_view = window.findChild(QObject, scroll_name)
            assert scroll_view is not None
            if scroll_name == "settingsProfileScroll":
                flickable = scroll_view.property("contentItem")
                assert flickable is not None
                return flickable
            return scroll_view

        for page, scroll_name in (
            ("OCR", "ocrSettingsScroll"),
            ("SETTINGS", "settingsFormScroll"),
            ("SETTINGS", "settingsProfileScroll"),
        ):
            controller.setPage("HOME")
            controller.setSkin(SKIN_PRISM)
            QTest.qWait(20)
            app.processEvents()
            controller.setPage(page)
            QTest.qWait(20)
            app.processEvents()
            prism_scroll = find_flickable(scroll_name)
            _wait_for_page_layout(window, prism_scroll, app)
            source_maximum = max(
                0.0,
                float(prism_scroll.property("contentHeight"))
                - float(prism_scroll.property("height")),
            )
            assert source_maximum > 20, (page, scroll_name, source_maximum)
            source_sync = next(
                child
                for child in window.findChildren(QQuickItem)
                if child.property("pageKey") == page
                and child.property("scrollKey") == {
                    "captureSettingsScroll": "captureSettings",
                    "ocrSettingsScroll": "ocrSettings",
                    "settingsFormScroll": "scheduleForm",
                    "settingsProfileScroll": "profileDiagnostics",
                }[scroll_name]
                and child.property("active") is True
            )
            assert source_sync.property("active") is True, (
                page,
                window.property("activeSkin"),
            )
            for _ in range(8):
                if not source_sync.property("restoring"):
                    break
                QTest.qWait(10)
                app.processEvents()
            assert source_sync.property("restoring") is False, (page, scroll_name)
            source_position = min(96.0, source_maximum)
            prism_scroll.setProperty("contentY", source_position)
            QTest.qWait(10)
            app.processEvents()
            source_position = float(prism_scroll.property("contentY"))

            controller.setPage("HOME")
            controller.setSkin(SKIN_DOHNA)
            QTest.qWait(20)
            app.processEvents()
            controller.setPage(page)
            QTest.qWait(30)
            app.processEvents()
            dohna_scroll = find_flickable(scroll_name)
            _wait_for_page_layout(window, dohna_scroll, app)
            assert len(window.findChildren(QObject, scroll_name)) == 1
            dohna_maximum = max(
                0.0,
                float(dohna_scroll.property("contentHeight"))
                - float(dohna_scroll.property("height")),
            )
            expected_dohna_position = min(source_position, dohna_maximum)
            assert float(dohna_scroll.property("contentY")) == pytest.approx(
                expected_dohna_position, abs=1.5
            ), (
                window.property("scrollPositions").toVariant(),
                source_sync.property("active"),
                source_sync.property("restoring"),
            )

            latest_position = min(42.0, dohna_maximum)
            dohna_scroll.setProperty("contentY", latest_position)
            QTest.qWait(10)
            app.processEvents()
            latest_position = float(dohna_scroll.property("contentY"))
            dohna_session = window.property("scrollPositions").toVariant()
            assert dohna_session[page][source_sync.property("scrollKey")] == pytest.approx(
                latest_position, abs=1.5
            ), (scroll_name, latest_position, dohna_session)
            controller.setPage("HOME")
            controller.setSkin(SKIN_PRISM)
            QTest.qWait(20)
            app.processEvents()
            switched_session = window.property("scrollPositions").toVariant()
            assert switched_session[page][source_sync.property("scrollKey")] == pytest.approx(
                latest_position, abs=1.5
            ), (scroll_name, latest_position, switched_session)
            returned_scroll = find_flickable(scroll_name)
            returned_maximum = max(
                0.0,
                float(returned_scroll.property("contentHeight"))
                - float(returned_scroll.property("height")),
            )
            assert returned_maximum > 20, (page, scroll_name, returned_maximum)
            controller.setPage(page)
            QTest.qWait(30)
            app.processEvents()
            _wait_for_page_layout(window, returned_scroll, app)
            returned_maximum = max(
                0.0,
                float(returned_scroll.property("contentHeight"))
                - float(returned_scroll.property("height")),
            )
            assert float(returned_scroll.property("contentY")) == pytest.approx(
                min(latest_position, returned_maximum), abs=1.5
            ), (
                scroll_name,
                latest_position,
                returned_maximum,
                window.property("scrollPositions").toVariant(),
            )

        controller.setPage("HOME")
        controller.setSkin(SKIN_DOHNA)
        QTest.qWait(30)
        app.processEvents()
        record_button = _find_quick_item(window, "homeHotkeyRecordButton")
        skin_selector = window.findChild(QObject, "homeSkinSelector")
        assert record_button is not None and skin_selector is not None
        assert QMetaObject.invokeMethod(record_button, "click") is True
        app.processEvents()
        assert window.property("hotkeyRecording") is True
        assert QMetaObject.invokeMethod(
            skin_selector, "activated", Q_ARG(int, 0)
        ) is True
        QTest.qWait(40)
        app.processEvents()
        assert controller.skinPreference == SKIN_PRISM
        assert window.property("hotkeyRecording") is True
        preferences = window.findChild(QObject, "refraPreferencesDialog")
        hotkey_field = window.findChild(QObject, "refraHotkeyField")
        assert preferences is not None and preferences.property("visible") is True
        assert hotkey_field is not None and hotkey_field.property("activeFocus") is True
        QTest.keyClick(window, Qt.Key.Key_Escape)
        app.processEvents()
        assert window.property("hotkeyRecording") is False

        assert host.window is original_window
        assert host._controller is controller
    finally:
        host.shutdown()


@pytest.mark.parametrize(
    "source_skin",
    (SKIN_PRISM, SKIN_DOHNA),
    ids=("prism-to-dohna", "dohna-to-prism"),
)
@pytest.mark.parametrize(
    "pair_kind",
    ("glossary", "corrections"),
    ids=("glossary", "corrections"),
)
def test_skin_activation_refreshes_latest_unsaved_pair_editor_draft(
    tmp_path: Path,
    source_skin: str,
    pair_kind: str,
) -> None:
    app, controller, host, window = _real_home_hotkey_host(tmp_path)
    other_skin = SKIN_DOHNA if source_skin == SKIN_PRISM else SKIN_PRISM
    page = "TRANSLATION" if pair_kind == "glossary" else "CACHE"
    editor_name = "glossaryEditor" if pair_kind == "glossary" else "correctionsEditor"
    save_text = "保存术语表" if pair_kind == "glossary" else "保存人工修订"
    initial_pair = {
        "source": f"previous {pair_kind} source",
        "target": f"previous {pair_kind} target",
    }
    edited_pair = {
        "source": f"latest {pair_kind} source",
        "target": f"latest {pair_kind} target",
    }

    def open_pair_editor() -> QObject:
        controller.setPage(page)
        app.processEvents()
        if pair_kind == "glossary":
            mode_button = next(
                item
                for item in window.findChildren(QQuickItem)
                if item.isVisible() and item.property("text") == "术语表"
            )
            assert QMetaObject.invokeMethod(mode_button, "click") is True
            app.processEvents()
        editor = window.findChild(QObject, editor_name)
        assert editor is not None
        return editor

    def field_text(field_name: str) -> str:
        field = _find_quick_item(window, field_name)
        assert field is not None
        return str(field.property("text"))

    def replace_field(field_name: str, value: str) -> None:
        field = _find_quick_item(window, field_name)
        assert field is not None
        field.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        _key_clicks(window, value)
        app.processEvents()

    try:
        if pair_kind == "glossary":
            controller.saveGlossary([initial_pair])
        else:
            controller.saveCorrections([initial_pair])
        app.processEvents()

        # Load both cached skin trees before editing so the return path uses
        # an already-existing PairEditor with an older ListModel.
        controller.setPage("HOME")
        controller.setSkin(other_skin)
        QTest.qWait(30)
        app.processEvents()
        controller.setSkin(source_skin)
        QTest.qWait(30)
        app.processEvents()

        source_editor = open_pair_editor()
        assert source_editor.property("entryCount") == 1
        assert field_text("pairSourceField-0") == initial_pair["source"]
        assert field_text("pairTargetField-0") == initial_pair["target"]

        controller.setPage("HOME")
        controller.setSkin(other_skin)
        QTest.qWait(30)
        app.processEvents()
        target_editor = open_pair_editor()
        assert target_editor.property("entryCount") == 1
        assert field_text("pairSourceField-0") == initial_pair["source"]

        revision_before_edit = controller.profileRevision
        replace_field("pairSourceField-0", edited_pair["source"])
        replace_field("pairTargetField-0", edited_pair["target"])
        entries_property = "glossaryEntries" if pair_kind == "glossary" else "correctionEntries"
        dirty_property = "glossaryDirty" if pair_kind == "glossary" else "correctionsDirty"
        assert getattr(controller, entries_property) == [edited_pair]
        assert getattr(controller, dirty_property) is True
        assert controller.profileRevision == revision_before_edit

        # Return to the original skin. Its rows must re-read the shared draft
        # once on activation, without changing profile revisions per keystroke.
        controller.setPage("HOME")
        controller.setSkin(source_skin)
        QTest.qWait(30)
        app.processEvents()
        restored_editor = open_pair_editor()
        assert restored_editor.property("entryCount") == 1
        assert field_text("pairSourceField-0") == edited_pair["source"]
        assert field_text("pairTargetField-0") == edited_pair["target"]
        assert getattr(controller, dirty_property) is True

        save_button = next(
            item
            for item in window.findChildren(QQuickItem)
            if item.isVisible() and item.property("text") == save_text
        )
        assert QMetaObject.invokeMethod(save_button, "click") is True
        app.processEvents()
        assert getattr(controller, dirty_property) is False

        profile = load_game_profile(
            controller._config_path,
            load_config(controller._config_path),
            "game",
        )
        if pair_kind == "glossary":
            saved_pairs = [
                {"source": entry.source, "target": entry.target}
                for entry in profile.glossary
            ]
        else:
            saved_pairs = [
                {"source": entry.source_text, "target": entry.translated_text}
                for entry in profile.cache.list_manual_corrections(
                    source_language=controller._config.ocr.language,
                    target_language=controller._config.translation.target_language,
                )
            ]
        assert saved_pairs == [edited_pair]
    finally:
        host.shutdown()
