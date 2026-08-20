from pathlib import Path

from PIL import Image

from game_screen_translator.config import PreviewConfig
from game_screen_translator.ocr.types import OcrText
from game_screen_translator.preview.renderer import render_preview


def test_render_preview_blurs_and_draws_region(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "preview.png"
    source_image = Image.new("RGB", (240, 100), (220, 30, 30))
    source_image.paste((30, 30, 220), (120, 0, 240, 100))
    source_image.save(source)
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
        PreviewConfig(blur_radius=3, overlay_opacity=0.0),
    )

    assert resolved == output.resolve()
    assert output.is_file()
    with Image.open(output) as rendered:
        assert rendered.size == (240, 100)
        assert rendered.getpixel((30, 24)) == (220, 30, 30)
        assert rendered.getpixel((119, 24)) not in {
            (220, 30, 30),
            (30, 30, 220),
        }
        extrema = rendered.crop((30, 25, 210, 75)).getextrema()
        assert all(channel_max >= 245 for _, channel_max in extrema[:3])


def test_render_preview_can_darken_the_blurred_region(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "preview.png"
    Image.new("RGB", (240, 100), (200, 120, 80)).save(source)
    observation = OcrText(
        "こんにちは",
        0.99,
        ((30, 25), (210, 25), (210, 75), (30, 75)),
    )

    render_preview(
        source,
        output,
        (observation,),
        ("你好",),
        PreviewConfig(blur_radius=0, overlay_opacity=0.55),
    )

    with Image.open(output) as rendered:
        red, green, blue = rendered.getpixel((28, 23))
        assert red < 200
        assert green < 120
        assert blue < 80
