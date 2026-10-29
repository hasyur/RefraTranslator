"""Keep the GitHub showcase usable in a checkout and source release."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
LINKS = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", README)
IMAGES = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", README)


@pytest.mark.parametrize("target", LINKS)
def test_readme_local_links_resolve(target: str) -> None:
    url = urlsplit(target)
    if url.scheme or url.netloc:
        return
    if url.path:
        path = (ROOT / unquote(url.path)).resolve()
        assert path.is_relative_to(ROOT), target
        assert path.is_file(), target
    elif url.fragment:
        headings = re.findall(r"^#{1,6} (.+)$", README, re.MULTILINE)
        anchors = {
            re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
            for heading in headings
        }
        assert unquote(url.fragment) in anchors, target


def test_readme_screenshots_are_bundled_public_assets() -> None:
    assert IMAGES, "The product showcase must include screenshots"
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include docs/images *.png" in manifest


@pytest.mark.parametrize("target", IMAGES)
def test_readme_screenshot_includes_a_readable_scene_background(target: str) -> None:
    assert target.startswith("docs/images/"), target
    with Image.open(ROOT / target) as screenshot:
        assert screenshot.format == "PNG"
        assert screenshot.width >= 980 and screenshot.height >= 700
        screenshot.load()
        # A transparent overlay alone omits the scene needed to show the effect.
        assert screenshot.convert("RGBA").getextrema()[3] == (255, 255)
