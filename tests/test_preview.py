from pathlib import Path

from PIL import Image

from game_screen_translator.config import PreviewConfig
from game_screen_translator.ocr.types import OcrText
from game_screen_translator.preview.renderer import render_preview


def test_render_preview_blurs_and_draws_region(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "preview.png"
    Image.new("RGB", (240, 100), (220, 30, 30)).save(source)
    observation = OcrText(
        "こんにちは",
        0.99,
        ((30, 25), (210, 25), (210, 75), (30, 75)),
    )

    resolved = render_preview(
        source,
        output,
        (observation,),
        ("你好，欢迎回来。",),
        PreviewConfig(blur_radius=3, overlay_opacity=0.55),
    )

    assert resolved == output.resolve()
    assert output.is_file()
    with Image.open(output) as rendered:
        assert rendered.size == (240, 100)
        assert rendered.getpixel((35, 30)) != (220, 30, 30)
