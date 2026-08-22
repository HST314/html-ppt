#!/usr/bin/env python3
"""Render a JSON slide plan to full-page PNGs and an image-only PDF."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
except ImportError as exc:
    raise SystemExit("Pillow is required: python3 -m pip install Pillow") from exc


FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
CANVAS = (1920, 1080)


def resolve(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    if not Path(path).exists():
        raise SystemExit(f"CJK font not found: {path}")
    return ImageFont.truetype(path, size=size)


def cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)


def contain(image: Image.Image, box: tuple[int, int]) -> Image.Image:
    copy = image.convert("RGBA")
    copy.thumbnail(box, Image.Resampling.LANCZOS)
    return copy


def rounded_panel(layer: Image.Image, box, fill=(4, 18, 40, 210), outline=(218, 176, 88, 105), radius=30):
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def wrap(draw: ImageDraw.ImageDraw, text: str, face, max_width: int) -> list[str]:
    lines = []
    for paragraph in str(text).split("\n"):
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and draw.textbbox((0, 0), candidate, font=face)[2] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines or [""]


def draw_wrapped(draw, xy, text, face, fill, max_width, spacing=12, max_lines=None):
    lines = wrap(draw, text, face, max_width)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    x, y = xy
    line_h = face.size + spacing
    for line in lines:
        draw.text((x, y), line, font=face, fill=fill)
        y += line_h
    return y


def paste_source(canvas: Image.Image, path: Path, box):
    source = Image.open(path)
    tile = contain(source, (box[2] - box[0], box[3] - box[1]))
    x = box[0] + (box[2] - box[0] - tile.width) // 2
    y = box[1] + (box[3] - box[1] - tile.height) // 2
    canvas.paste(tile, (x, y), tile)


def base_slide(background: Path) -> Image.Image:
    canvas = cover_crop(Image.open(background), CANVAS)
    veil = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(veil, "RGBA").rectangle((0, 0, *CANVAS), fill=(1, 8, 24, 38))
    return Image.alpha_composite(canvas.convert("RGBA"), veil)


def draw_footer(draw, number: int, total: int):
    draw.text((1540, 1012), f"CHANGZHENG 8A  /  {number:02d}—{total:02d}", font=font(22), fill=(190, 204, 224, 190))


def render_cover(canvas, slide):
    panel = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    rounded_panel(panel, (105, 154, 960, 858), fill=(2, 14, 34, 195), radius=38)
    canvas = Image.alpha_composite(canvas, panel)
    draw = ImageDraw.Draw(canvas)
    draw.text((150, 205), slide.get("kicker", "MISSION VISUAL ARCHIVE"), font=font(25, True), fill=(225, 184, 92, 255))
    y = draw_wrapped(draw, (150, 315), slide["title"], font(76, True), (247, 249, 255, 255), 730, 18, 3)
    subtitle = slide.get("subtitle", "")
    if subtitle:
        draw_wrapped(draw, (155, y + 38), subtitle, font(35), (184, 207, 235, 255), 700, 14, 3)
    draw.line((152, 748, 430, 748), fill=(225, 184, 92, 255), width=4)
    draw.text((152, 783), slide.get("meta", "IMAGE-BASED PDF · 16:9"), font=font(24), fill=(186, 197, 216, 230))
    return canvas


def render_toc(canvas, slide):
    draw = ImageDraw.Draw(canvas)
    draw.text((95, 64), slide["title"], font=font(55, True), fill=(250, 251, 255, 255))
    draw.text((99, 132), slide.get("subtitle", "CONTENTS"), font=font(22, True), fill=(226, 184, 94, 255))
    items = slide.get("body", [])[:7]
    positions = [(105, 255), (105, 410), (105, 565), (1240, 255), (1240, 410), (1240, 565), (1240, 720)]
    overlay = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for i, item in enumerate(items):
        x, y = positions[i]
        rounded_panel(overlay, (x, y, x + 570, y + 112), fill=(2, 20, 46, 215), radius=22)
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    for i, item in enumerate(items):
        x, y = positions[i]
        draw.text((x + 25, y + 21), f"{i + 1:02d}", font=font(27, True), fill=(227, 184, 93, 255))
        label = item.get("title", "") if isinstance(item, dict) else str(item)
        page_range = item.get("page_range", "") if isinstance(item, dict) else ""
        draw_wrapped(draw, (x + 95, y + 15), label, font(27, True), (242, 246, 253, 255), 335, 8, 2)
        if page_range:
            draw.text((x + 465, y + 39), page_range, font=font(22, True), fill=(187, 206, 230, 230))
    return canvas


def render_section(canvas, slide):
    veil = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(veil, "RGBA").rectangle((0, 0, 1920, 1080), fill=(0, 8, 25, 95))
    canvas = Image.alpha_composite(canvas, veil)
    draw = ImageDraw.Draw(canvas)
    draw.text((120, 180), slide.get("kicker", "CHAPTER"), font=font(25, True), fill=(227, 184, 93, 255))
    draw_wrapped(draw, (120, 305), slide["title"], font(72, True), (250, 252, 255, 255), 1300, 18, 3)
    if slide.get("subtitle"):
        draw_wrapped(draw, (125, 600), slide["subtitle"], font(36), (189, 210, 236, 255), 1120, 14, 3)
    return canvas


def render_content(canvas, slide):
    draw = ImageDraw.Draw(canvas)
    draw.text((88, 55), slide.get("kicker", "MISSION VISUAL SYSTEM"), font=font(22, True), fill=(228, 185, 94, 255))
    draw_wrapped(draw, (88, 102), slide["title"], font(51, True), (250, 252, 255, 255), 1450, 12, 2)
    if slide.get("subtitle"):
        draw_wrapped(draw, (90, 225), slide["subtitle"], font(27), (183, 205, 232, 255), 1400, 10, 2)

    overlay = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    layout = slide.get("layout", "split")
    source = slide.get("source_image")
    if layout == "matrix":
        boxes = [(85, 330, 895, 595), (935, 330, 1745, 595), (85, 635, 895, 900), (935, 635, 1745, 900)]
    elif source:
        boxes = [(85, 330, 1015, 590), (85, 625, 1015, 910)]
        rounded_panel(overlay, (1080, 315, 1815, 925), fill=(2, 16, 38, 218), radius=34)
    else:
        boxes = [(85, 330, 865, 900), (905, 330, 1685, 900)]
    for box in boxes:
        rounded_panel(overlay, box, fill=(3, 18, 42, 220), radius=28)
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    body = slide.get("body", [])
    if layout == "timeline":
        y = 500
        draw.line((160, y, 1740, y), fill=(226, 184, 94, 230), width=4)
        for i, item in enumerate(body[:6]):
            x = 180 + i * 290
            draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=(226, 184, 94, 255))
            draw.text((x - 20, y - 88), f"{i + 1:02d}", font=font(25, True), fill=(226, 184, 94, 255))
            draw_wrapped(draw, (x - 55, y + 45), item, font(27, True), (241, 246, 253, 255), 225, 9, 4)
    else:
        for i, item in enumerate(body[: len(boxes)]):
            box = boxes[i]
            draw.text((box[0] + 32, box[1] + 28), f"{i + 1:02d}", font=font(24, True), fill=(226, 184, 94, 255))
            draw_wrapped(draw, (box[0] + 32, box[1] + 86), item, font(31, True), (242, 247, 254, 255), box[2] - box[0] - 64, 12, 7)
    if source:
        paste_source(canvas, Path(source), (1110, 345, 1785, 895))
    return canvas


def render_closing(canvas, slide):
    draw = ImageDraw.Draw(canvas)
    title = slide["title"]
    bbox = draw.textbbox((0, 0), title, font=font(64, True))
    x = (1920 - (bbox[2] - bbox[0])) // 2
    draw.text((x, 285), title, font=font(64, True), fill=(250, 252, 255, 255))
    if slide.get("subtitle"):
        sub = slide["subtitle"]
        bbox = draw.textbbox((0, 0), sub, font=font(32))
        x = (1920 - (bbox[2] - bbox[0])) // 2
        draw.text((x, 390), sub, font=font(32), fill=(202, 216, 235, 255))
    return canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--pdf", required=True)
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    base = spec_path.parent
    backgrounds = {k: resolve(base, v) for k, v in spec["backgrounds"].items()}
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    slides = spec["slides"]
    chapters = spec.get("chapters", [])
    chapter_ranges = {}
    for chapter in chapters:
        page_numbers = [i for i, s in enumerate(slides, 1) if s.get("chapter_id") == chapter["id"]]
        if page_numbers:
            chapter_ranges[chapter["id"]] = f"{min(page_numbers):02d}–{max(page_numbers):02d}"
    rendered_paths = []

    for index, slide in enumerate(slides, 1):
        role = slide.get("role", "content")
        bg_role = "toc" if role == "toc" else "closing" if role == "closing" else "cover" if role == "cover" else "content"
        canvas = base_slide(backgrounds[bg_role])
        slide = dict(slide)
        if role == "toc" and chapters:
            slide["body"] = [dict(chapter, page_range=chapter_ranges.get(chapter["id"], "")) for chapter in chapters]
        if slide.get("source_image"):
            slide["source_image"] = str(resolve(base, slide["source_image"]))
        canvas = {"cover": render_cover, "toc": render_toc, "section": render_section, "closing": render_closing}.get(role, render_content)(canvas, slide)
        draw_footer(ImageDraw.Draw(canvas), index, len(slides))
        safe_title = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", slide.get("title", "slide"))[:26].strip("-")
        out = output_dir / f"{index:02d}-{safe_title or 'slide'}.png"
        rgb = canvas.convert("RGB")
        # Avoid Pillow's expensive PNG optimizer; image-PDF pages are already
        # compressed again by the PDF writer and deterministic render speed is
        # more important than shaving a few percent from intermediate PNGs.
        rgb.save(out, "PNG", compress_level=6)
        rgb.close()
        canvas.close()
        rendered_paths.append(out)

    pdf_path = Path(args.pdf).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    # Keep source files lazy to avoid retaining every decoded 1920x1080 frame in RAM.
    pdf_images = [Image.open(path) for path in rendered_paths]
    try:
        pdf_images[0].save(pdf_path, "PDF", save_all=True, append_images=pdf_images[1:], resolution=150.0)
    finally:
        for image in pdf_images:
            image.close()
    print(json.dumps({"pages": len(rendered_paths), "output_dir": str(output_dir), "pdf": str(pdf_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
