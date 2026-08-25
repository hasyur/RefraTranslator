from __future__ import annotations

import json
from urllib.request import Request, urlopen

from game_screen_translator.live.tracker import TrackedText
from game_screen_translator.overlay.browser import (
    BrowserOverlayServer,
    build_browser_overlay_scene,
)


def _track(
    track_id: str,
    *,
    bounds: tuple[int, int, int, int],
    translation: str | None,
    suppressed: bool = False,
) -> TrackedText:
    return TrackedText(
        track_id=track_id,
        revision=2,
        text="原文",
        confidence=0.99,
        bounds=bounds,
        first_seen=1.0,
        last_seen=2.0,
        observations=2,
        translated_text=translation,
        translation_suppressed=suppressed,
    )


def test_browser_overlay_scene_uses_monitor_coordinates_and_visible_text() -> None:
    scene = build_browser_overlay_scene(
        canvas_size=(1920, 1080),
        capture_region=(200, 300, 1200, 700),
        tracks=(
            _track("visible", bounds=(10, 20, 210, 60), translation="翻译结果"),
            _track("pending", bounds=(20, 80, 220, 120), translation=None),
            _track(
                "suppressed",
                bounds=(20, 140, 220, 180),
                translation="不应显示",
                suppressed=True,
            ),
        ),
    )

    assert scene["canvasWidth"] == 1920
    assert scene["canvasHeight"] == 1080
    assert scene["items"] == [
        {
            "key": "visible:2",
            "text": "翻译结果",
            "left": 206,
            "top": 316,
            "width": 208,
            "height": 48,
        }
    ]


def test_browser_overlay_scene_clips_boxes_to_capture_region() -> None:
    scene = build_browser_overlay_scene(
        canvas_size=(640, 480),
        capture_region=(100, 100, 300, 200),
        tracks=(
            _track("edge", bounds=(-10, -10, 210, 110), translation="边缘"),
        ),
    )

    assert scene["items"] == [
        {
            "key": "edge:2",
            "text": "边缘",
            "left": 100,
            "top": 100,
            "width": 200,
            "height": 100,
        }
    ]


def test_browser_overlay_server_serves_transparent_page_and_live_state() -> None:
    server = BrowserOverlayServer(
        canvas_size=(1280, 720),
        capture_region=(100, 200, 900, 600),
        port=0,
    )
    server.start()
    try:
        with urlopen(server.url, timeout=2) as response:  # noqa: S310 - loopback test
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "rgba(0, 0, 0, 0)" in html
            assert 'fetch("/state"' in html

        server.publish(
            (_track("track", bounds=(20, 30, 320, 80), translation="已录制"),)
        )
        state_url = server.url.removesuffix("/overlay") + "/state"
        with urlopen(state_url, timeout=2) as response:  # noqa: S310 - loopback test
            state = json.loads(response.read())
            assert response.headers["Cache-Control"] == "no-store"
            assert state["revision"] >= 2
            assert state["items"][0]["text"] == "已录制"
            assert state["items"][0]["left"] == 116

        request = Request(server.url, method="HEAD")
        with urlopen(request, timeout=2) as response:  # noqa: S310 - loopback test
            assert response.status == 200
            assert response.read() == b""
    finally:
        server.close()

    assert not server.running
