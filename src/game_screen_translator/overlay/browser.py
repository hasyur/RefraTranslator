from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Sequence
from urllib.parse import urlsplit

from game_screen_translator.live.tracker import TrackedText


_BROWSER_OVERLAY_HTML = b"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>RefraTranslator Browser Overlay</title>
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: rgba(0, 0, 0, 0);
    }
    #stage {
      position: fixed;
      inset: 0;
      overflow: hidden;
      pointer-events: none;
    }
    .translation {
      position: absolute;
      box-sizing: border-box;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      padding: 4px;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.72);
      color: white;
      font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
      font-weight: 600;
      line-height: 1.12;
      text-align: center;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      text-shadow:
        -1px -1px 0 rgba(0, 0, 0, 0.95),
         0   -1px 0 rgba(0, 0, 0, 0.95),
         1px -1px 0 rgba(0, 0, 0, 0.95),
        -1px  0   0 rgba(0, 0, 0, 0.95),
         1px  0   0 rgba(0, 0, 0, 0.95),
        -1px  1px 0 rgba(0, 0, 0, 0.95),
         0    1px 0 rgba(0, 0, 0, 0.95),
         1px  1px 0 rgba(0, 0, 0, 0.95);
    }
  </style>
</head>
<body>
  <div id="stage"></div>
  <script>
    const stage = document.getElementById("stage");
    let scene = null;
    let latestRevision = -1;
    let failures = 0;

    function clearStage() {
      stage.replaceChildren();
    }

    function fitText(node, maximum) {
      let low = 8;
      let high = Math.max(low, Math.floor(maximum));
      let best = low;
      while (low <= high) {
        const middle = Math.floor((low + high) / 2);
        node.style.fontSize = `${middle}px`;
        if (
          node.scrollWidth <= node.clientWidth + 1 &&
          node.scrollHeight <= node.clientHeight + 1
        ) {
          best = middle;
          low = middle + 1;
        } else {
          high = middle - 1;
        }
      }
      node.style.fontSize = `${best}px`;
    }

    function render() {
      clearStage();
      if (!scene || scene.canvasWidth <= 0 || scene.canvasHeight <= 0) {
        return;
      }
      const scaleX = window.innerWidth / scene.canvasWidth;
      const scaleY = window.innerHeight / scene.canvasHeight;
      const scale = Math.min(scaleX, scaleY);
      for (const item of scene.items) {
        const node = document.createElement("div");
        node.className = "translation";
        node.dataset.key = item.key;
        node.textContent = item.text;
        node.style.left = `${item.left * scaleX}px`;
        node.style.top = `${item.top * scaleY}px`;
        node.style.width = `${item.width * scaleX}px`;
        node.style.height = `${item.height * scaleY}px`;
        node.style.padding = `${Math.max(2, 4 * scale)}px`;
        node.style.borderRadius = `${Math.max(2, 4 * scale)}px`;
        stage.appendChild(node);
        fitText(node, Math.min(48 * scale, item.height * scaleY * 0.64));
      }
    }

    async function refresh() {
      try {
        const response = await fetch("/state", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const next = await response.json();
        failures = 0;
        if (next.revision !== latestRevision) {
          latestRevision = next.revision;
          scene = next;
          render();
        }
      } catch (_error) {
        failures += 1;
        if (failures >= 5) {
          scene = null;
          latestRevision = -1;
          clearStage();
        }
      } finally {
        window.setTimeout(refresh, 100);
      }
    }

    window.addEventListener("resize", render);
    refresh();
  </script>
</body>
</html>
"""


def build_browser_overlay_scene(
    *,
    canvas_size: tuple[int, int],
    capture_region: tuple[int, int, int, int],
    tracks: Sequence[TrackedText],
) -> dict[str, object]:
    """Build the transparent recording scene in monitor-native coordinates."""

    canvas_width, canvas_height = canvas_size
    if canvas_width < 1 or canvas_height < 1:
        raise ValueError("Browser Source 画布尺寸必须大于 0")
    capture_left, capture_top, capture_right, capture_bottom = capture_region
    if not (
        0 <= capture_left < capture_right <= canvas_width
        and 0 <= capture_top < capture_bottom <= canvas_height
    ):
        raise ValueError("Browser Source 捕获区域超出画布")

    items: list[dict[str, object]] = []
    padding = 4
    for track in tracks:
        translation = track.display_translation
        if not translation:
            continue
        source_left, source_top, source_right, source_bottom = track.bounds
        left = max(capture_left, capture_left + source_left - padding)
        top = max(capture_top, capture_top + source_top - padding)
        right = min(capture_right, capture_left + source_right + padding)
        bottom = min(capture_bottom, capture_top + source_bottom + padding)
        if right <= left or bottom <= top:
            continue
        items.append(
            {
                "key": f"{track.track_id}:{track.revision}",
                "text": translation,
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
            }
        )
    return {
        "version": 1,
        "canvasWidth": canvas_width,
        "canvasHeight": canvas_height,
        "items": items,
    }


class _OverlayHttpServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class BrowserOverlayServer:
    """Serve a loopback-only transparent overlay for recorder composition."""

    def __init__(
        self,
        *,
        canvas_size: tuple[int, int],
        capture_region: tuple[int, int, int, int],
        port: int,
    ) -> None:
        self._canvas_size = canvas_size
        self._capture_region = capture_region
        self._requested_port = port
        self._bound_port = port
        self._lock = threading.Lock()
        self._revision = 0
        self._scene_signature = ""
        self._state_bytes = b""
        self._httpd: _OverlayHttpServer | None = None
        self._thread: threading.Thread | None = None
        self.publish(())

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._bound_port}/overlay"

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        if self._httpd is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802 - HTTP callback name
                owner._handle_request(self, include_body=True)

            def do_HEAD(self) -> None:  # noqa: N802 - HTTP callback name
                owner._handle_request(self, include_body=False)

            def log_message(self, format: str, *args: object) -> None:
                return

        httpd = _OverlayHttpServer(("127.0.0.1", self._requested_port), Handler)
        self._httpd = httpd
        self._bound_port = int(httpd.server_address[1])
        thread = threading.Thread(
            target=httpd.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="refra-browser-overlay",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def publish(self, tracks: Sequence[TrackedText]) -> None:
        scene = build_browser_overlay_scene(
            canvas_size=self._canvas_size,
            capture_region=self._capture_region,
            tracks=tracks,
        )
        signature = json.dumps(
            scene,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._lock:
            if signature == self._scene_signature:
                return
            self._scene_signature = signature
            self._revision += 1
            scene["revision"] = self._revision
            self._state_bytes = json.dumps(
                scene,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

    def close(self) -> None:
        httpd = self._httpd
        thread = self._thread
        self._httpd = None
        self._thread = None
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _handle_request(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        include_body: bool,
    ) -> None:
        path = urlsplit(handler.path).path
        if path in {"/", "/overlay"}:
            self._send(
                handler,
                status=200,
                content_type="text/html; charset=utf-8",
                body=_BROWSER_OVERLAY_HTML,
                include_body=include_body,
                content_security_policy=(
                    "default-src 'none'; connect-src 'self'; "
                    "script-src 'unsafe-inline'; style-src 'unsafe-inline'"
                ),
            )
            return
        if path == "/state":
            with self._lock:
                body = self._state_bytes
            self._send(
                handler,
                status=200,
                content_type="application/json; charset=utf-8",
                body=body,
                include_body=include_body,
            )
            return
        if path == "/favicon.ico":
            self._send(
                handler,
                status=204,
                content_type="image/x-icon",
                body=b"",
                include_body=include_body,
            )
            return
        self._send(
            handler,
            status=404,
            content_type="text/plain; charset=utf-8",
            body="Not Found".encode("utf-8"),
            include_body=include_body,
        )

    @staticmethod
    def _send(
        handler: BaseHTTPRequestHandler,
        *,
        status: int,
        content_type: str,
        body: bytes,
        include_body: bool,
        content_security_policy: str | None = None,
    ) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        if content_security_policy is not None:
            handler.send_header("Content-Security-Policy", content_security_policy)
        handler.end_headers()
        if include_body and body:
            handler.wfile.write(body)
