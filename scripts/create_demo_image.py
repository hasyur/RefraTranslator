from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser(description="生成用于 OCR 纵向链路的日文测试截图")
    parser.add_argument("output", nargs="?", type=Path, default=Path("output/demo_source.png"))
    args = parser.parse_args()

    canvas = Image.new("RGB", (1280, 360), (16, 22, 34))
    draw = ImageDraw.Draw(canvas)
    font_path = Path(r"C:\Windows\Fonts\YuGothB.ttc")
    font = ImageFont.truetype(str(font_path), 46)
    small = ImageFont.truetype(str(font_path), 30)

    draw.rounded_rectangle((70, 65, 1210, 295), radius=20, fill=(10, 12, 18), outline=(96, 110, 138), width=3)
    draw.text((110, 102), "お前、本当に来たんだな。", font=font, fill=(248, 248, 252))
    draw.text((110, 174), "まあ、座れよ。仕事の話をしよう。", font=font, fill=(248, 248, 252))
    draw.text((930, 258), "フィクサー", font=small, fill=(124, 204, 255))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
