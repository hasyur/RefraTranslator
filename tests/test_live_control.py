import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.live.runtime import LiveControlWindow


def test_live_control_collapses_and_restores_runtime_information() -> None:
    app = QApplication.instance() or QApplication([])
    stopped: list[bool] = []
    paused: list[bool] = []
    window = LiveControlWindow(
        lambda: stopped.append(True),
        lambda value: paused.append(value),
    )
    window.adjustSize()
    window.move(700, 20)
    expanded_width = window.width()
    expanded_height = window.height()
    expanded_right = window.geometry().right()

    assert window.windowTitle() == PRODUCT_NAME
    assert window._pause_button.text() == "暂停翻译"

    window._pause_button.click()
    assert paused == [True]
    assert window._pause_button.text() == "恢复翻译"

    window._pause_button.click()
    assert paused == [True, False]
    assert window._pause_button.text() == "暂停翻译"

    window._shrink_button.click()
    app.processEvents()

    assert all(widget.isHidden() for widget in window._diagnostic_widgets)
    assert window._shrink_button.isHidden()
    assert not window._restore_button.isHidden()
    assert window._restore_button.text() == "恢复"
    assert not window._pause_button.isHidden()
    assert window._pause_button.text() == "暂停翻译"
    assert not window._stop_button.isHidden()
    assert window._stop_button.text() == "关闭翻译"
    assert window.width() < expanded_width
    assert window.height() < expanded_height
    assert window.geometry().right() == expanded_right

    window._restore_button.click()
    app.processEvents()

    assert all(not widget.isHidden() for widget in window._diagnostic_widgets)
    assert not window._shrink_button.isHidden()
    assert window._restore_button.isHidden()
    assert not window._stop_button.isHidden()
    assert window.width() == expanded_width
    assert window.height() == expanded_height
    assert window.geometry().right() == expanded_right

    window._stop_button.click()
    assert stopped == [True]
    window.close()
    app.processEvents()
