from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from game_screen_translator.config import PreviewConfig
from game_screen_translator.ocr.types import OcrText


def _font_candidates(configured_path: str) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if configured_path:
        candidates.append(Path(configured_path))
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates.extend(
        (
            windows_dir / "Fonts" / "msyh.ttc",
            windows_dir / "Fonts" / "msyhbd.ttc",
            windows_dir / "Fonts" / "simhei.ttf",
            windows_dir / "Fonts" / "arial.ttf",
        )
    )
    return tuple(candidates)


def _load_font(size: int, configured_path: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _font_candidates(configured_path):
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _wrap_by_width(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, width: int) -> list[str]:
    if width <= 1:
        return [text]
    lines: list[str] = []
    current = ""
    for character in text:
        if character == "\n":
            lines.append(current or " ")
            current = ""
            continue
        candidate = current + character
        if current and draw.textbbox((0, 0), candidate, font=font, stroke_width=1)[2] > width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [" "]


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    height: int,
    configured_path: str,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    upper = max(10, min(48, int(height * 0.78)))
    for size in range(upper, 8, -1):
        font = _load_font(size, configured_path)
        lines = _wrap_by_width(text, draw, font, width)
        line_height = max(1, draw.textbbox((0, 0), "国Ag", font=font, stroke_width=1)[3] + 2)
        if line_height * len(lines) <= height:
            return font, lines, line_height
    font = _load_font(9, configured_path)
    lines = _wrap_by_width(text, draw, font, width)
    line_height = max(1, draw.textbbox((0, 0), "国Ag", font=font, stroke_width=1)[3] + 1)
    return font, lines, line_height


def render_preview(
    image_path: str | Path,
    output_path: str | Path,
    observations: Sequence[OcrText],
    translations: Sequence[str],
    config: PreviewConfig,
) -> Path:
    if len(observations) != len(translations):
        raise ValueError("OCR 区域与译文数量不一致")

    source_path = Path(image_path)
    destination = Path(output_path)
    image = Image.open(source_path).convert("RGBA")
    width, height = image.size

    for observation, translated in zip(observations, translations, strict=True):
        left, top, right, bottom = observation.bounds
        padding = 3
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(width, right + padding)
        bottom = min(height, bottom + padding)
        if right <= left or bottom <= top:
            continue

        region = image.crop((left, top, right, bottom))
        if config.blur_radius > 0:
            region = region.filter(ImageFilter.GaussianBlur(config.blur_radius))
        image.paste(region, (left, top))

        draw = ImageDraw.Draw(image)
        box_width = max(1, right - left - 6)
        box_height = max(1, bottom - top - 4)
        font, lines, line_height = _fit_text(
            draw,
            translated,
            box_width,
            box_height,
            config.font_path,
        )
        total_height = line_height * len(lines)
        y = top + max(2, (bottom - top - total_height) // 2)
        for line in lines:
            line_box = draw.textbbox((0, 0), line, font=font, stroke_width=1)
            line_width = line_box[2] - line_box[0]
            x = left + max(3, (right - left - line_width) // 2)
            draw.text(
                (x, y),
                line,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 220),
            )
            y += line_height

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(destination)
    return destination.resolve()
