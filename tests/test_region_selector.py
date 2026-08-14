import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.gui.region_selector import RegionSelector, scale_selection_region


def test_scale_selection_region_handles_150_percent_dpi() -> None:
    assert scale_selection_region(
        (100, 200, 800, 300),
        (2560, 1440),
        (3840, 2160),
    ) == (150, 300, 1200, 450)


def test_scale_selection_region_clamps_to_monitor_edge() -> None:
    assert scale_selection_region(
        (1800, 900, 300, 300),
        (1920, 1080),
        (1920, 1080),
    ) == (1800, 900, 120, 180)


@pytest.mark.parametrize(
    ("selection", "logical", "capture"),
    [
        ((0, 0, 0, 20), (1920, 1080), (1920, 1080)),
        ((2000, 0, 20, 20), (1920, 1080), (1920, 1080)),
        ((0, 0, 20, 20), (0, 1080), (1920, 1080)),
    ],
)
def test_scale_selection_region_rejects_invalid_geometry(
    selection,
    logical,
    capture,
) -> None:
    with pytest.raises(ValueError):
        scale_selection_region(selection, logical, capture)


def test_region_selector_accepts_a_mouse_drag() -> None:
    app = QApplication.instance() or QApplication([])
    selector = RegionSelector(app.primaryScreen())
    selector.show()
    app.processEvents()

    assert selector.windowTitle().startswith(PRODUCT_NAME)

    QTest.mousePress(
        selector,
        Qt.MouseButton.LeftButton,
        pos=QPoint(20, 30),
    )
    QTest.mouseMove(selector, QPoint(220, 130))
    QTest.mouseRelease(
        selector,
        Qt.MouseButton.LeftButton,
        pos=QPoint(220, 130),
    )

    assert selector.selected_region is not None
    left, top, width, height = selector.selected_region
    assert left >= 0 and top >= 0
    assert width > 0 and height > 0
    selector.close()
    app.processEvents()
