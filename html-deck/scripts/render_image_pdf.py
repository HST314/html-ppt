#!/usr/bin/env python3
"""Render SlidesPlan IR as raster slide images and a review-ready 16:9 PDF."""

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

DEPENDENCY_ERROR = None
try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, PngImagePlugin
    from reportlab.pdfgen import canvas
except ImportError as exc:  # pragma: no cover
    DEPENDENCY_ERROR = exc


PALETTE = {
    "ink": "#102A3A", "paper": "#F3E8D2", "paper_2": "#FAF6EC",
    "red": "#CB4B43", "gold": "#E1A93B", "blue": "#287E91",
    "muted": "#6B7576", "white": "#FFFDF7",
}
THEMES = {
    "business-dark": {"ink": "#091C2A", "paper": "#DDE8EE", "paper_2": "#F4F7F8", "red": "#E5574F", "gold": "#E6B85C", "blue": "#2B8FA3", "muted": "#657681", "white": "#FFFFFF"},
    "tech-dark": {"ink": "#071725", "paper": "#D9ECF2", "paper_2": "#EFF8FA", "red": "#F05A67", "gold": "#FFC857", "blue": "#28C2D1", "muted": "#617D88", "white": "#FFFFFF"},
    "warm-human": {"ink": "#382B28", "paper": "#F1DFC5", "paper_2": "#FFF8ED", "red": "#C95D45", "gold": "#D69A3A", "blue": "#4F8B88", "muted": "#796C64", "white": "#FFFDF8"},
}
TEXT_OVERFLOWS = []
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def parse_args():
    parser = argparse.ArgumentParser(description="把 SlidesPlan outline.json 渲染为逐页 PNG 与图片型 PDF。")
    parser.add_argument("--ir", required=True, help="SlidesPlan outline.json")
    parser.add_argument("--manifest", required=True, help="images/manifest.json")
    parser.add_argument("--output", required=True, help="输出 PDF")
    parser.add_argument("--slides-dir", help="逐页 PNG 目录；缺省为 PDF 同级 slides/")
    parser.add_argument("--report", help="渲染覆盖报告 JSON")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--quality", type=int, default=94)
    parser.add_argument("--strict-images", action="store_true", help="清单图片未全部使用时失败")
    return parser.parse_args()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def font_path(bold=False):
    candidates = list(FONT_CANDIDATES)
    if bold:
        candidates.insert(0, "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
    for value in candidates:
        if Path(value).exists():
            return value
    raise RuntimeError("未找到可用的中文字体；请安装 Noto Sans CJK SC")


def font(size, bold=False):
    return ImageFont.truetype(font_path(bold), size=size)


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def text_width(draw, text, typeface):
    box = draw.textbbox((0, 0), text, font=typeface)
    return box[2] - box[0]


def wrap_text(draw, text, typeface, max_width, max_lines=None):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    lines, current = [], ""
    for char in text:
        candidate = current + char
        if current and text_width(draw, candidate, typeface) > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
    if max_lines and len(lines) > max_lines:
        TEXT_OVERFLOWS.append(str(text))
        lines = lines[:max_lines]
        last = lines[-1]
        while last and text_width(draw, last + "…", typeface) > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def draw_text(draw, xy, text, typeface, fill, max_width, line_gap=8, max_lines=None):
    x, y = xy
    lines = wrap_text(draw, text, typeface, max_width, max_lines)
    line_height = typeface.size + line_gap
    for line in lines:
        draw.text((x, y), line, font=typeface, fill=fill)
        y += line_height
    return y


def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def image_id(item):
    return str((item or {}).get("id") or "")


def resolve_manifest(manifest_path, manifest):
    root = Path(manifest_path).resolve().parent
    index = {}
    for item in manifest.get("images", []):
        value = Path(str(item.get("file", "")))
        path = value if value.is_absolute() else root / value
        enriched = dict(item)
        enriched["_path"] = path.resolve()
        index[image_id(item)] = enriched
    return index


def resolve_slide_images(slide, index):
    output = []
    candidates = list(slide.get("images") or [])
    if slide.get("bg_image"):
        candidates.insert(0, slide["bg_image"])
    for value in candidates:
        if isinstance(value, str):
            item = index.get(value)
        elif isinstance(value, dict):
            item = index.get(image_id(value)) or dict(value)
            if item and "_path" not in item and item.get("file"):
                item["_path"] = Path(item["file"]).resolve()
        else:
            item = None
        if item and item.get("_path") and Path(item["_path"]).exists():
            output.append(item)
    return output


def open_rgb(item):
    with Image.open(item["_path"]) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def paste_contain(canvas_image, source, box, background=None):
    x1, y1, x2, y2 = map(int, box)
    target = (max(1, x2 - x1), max(1, y2 - y1))
    fitted = ImageOps.contain(source, target, Image.Resampling.LANCZOS)
    if background:
        panel = Image.new("RGB", target, background)
        panel.paste(fitted, ((target[0] - fitted.width) // 2, (target[1] - fitted.height) // 2))
        fitted = panel
    canvas_image.paste(fitted, (x1 + (target[0] - fitted.width) // 2, y1 + (target[1] - fitted.height) // 2))


def paste_cover(canvas_image, source, box):
    x1, y1, x2, y2 = map(int, box)
    target = (max(1, x2 - x1), max(1, y2 - y1))
    fitted = ImageOps.fit(source, target, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    canvas_image.paste(fitted, (x1, y1))


def add_texture(page):
    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = page.size
    for i in range(22):
        x, y = int((i * 173) % w), int((i * 97) % h)
        draw.ellipse((x, y, x + 3, y + 3), fill=hex_rgb(PALETTE["ink"]) + (24,))
    draw.arc((w - 460, -220, w + 150, 390), 40, 245, fill=hex_rgb(PALETTE["gold"]) + (70,), width=5)
    draw.arc((-180, h - 300, 370, h + 240), 195, 355, fill=hex_rgb(PALETTE["red"]) + (48,), width=4)
    return Image.alpha_composite(page.convert("RGBA"), overlay).convert("RGB")


def flatten_blocks(blocks):
    result = []
    for block in blocks or []:
        kind = block.get("type")
        if kind == "list":
            result.extend(str(x) for x in block.get("items", []))
        elif kind == "table":
            result.extend(" · ".join(map(str, row)) for row in block.get("rows", []))
        elif block.get("text"):
            result.append(str(block["text"]))
    return result


def source_texts(slide):
    """Canonical visible strings used by both render metadata and independent QA."""
    values = [str(slide.get("title") or "")]
    values.extend(flatten_blocks(slide.get("blocks")))
    values.extend(str(card.get("title") or "") for card in slide.get("toc_cards") or [])
    if slide.get("takeaway"):
        values.append(str(slide["takeaway"]))
    return [value for value in values if value]


def effective_role(slide):
    """Consume the visual blueprint before falling back to the semantic role."""
    pattern = slide.get("layout_pattern")
    mapping = {
        "timeline": "timeline", "path-flow": "timeline", "compare": "compare",
        "big-number": "kpi", "matrix": "table", "text-image": "image-side",
        "product-hero": "image-hero", "hero-details": "image-hero",
        "center-hub": "two-column", "tri-loop": "two-column",
        "asym-mix": "two-column", "hierarchy-space": "two-column",
    }
    return mapping.get(pattern, slide.get("role") or "bullets")


def apply_theme(plan):
    chosen = THEMES.get(plan.get("theme_recommendation"))
    if chosen:
        PALETTE.update(chosen)
    dna = plan.get("art_dna") or {}
    colors = dna.get("colors") or dna.get("palette") or {}
    if isinstance(colors, dict):
        for key in PALETTE:
            value = colors.get(key)
            if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                PALETTE[key] = value


def slide_chrome(page, page_no, total, section=None, dark=False):
    draw = ImageDraw.Draw(page)
    w, _ = page.size
    ink = PALETTE["paper_2"] if dark else PALETTE["ink"]
    draw.line((74, 64, w - 74, 64), fill=PALETTE["gold"] if dark else "#C9B996", width=2)
    draw.text((76, 26), (section or "IMAGE DECK").upper(), font=font(18, True), fill=ink)
    marker = f"{page_no:02d} / {total:02d}"
    marker_font = font(18, True)
    draw.text((w - 76 - text_width(draw, marker, marker_font), 26), marker, font=marker_font, fill=ink)


def render_cover(slide, images, size, page_no, total):
    w, h = size
    page = Image.new("RGB", size, PALETTE["ink"])
    draw = ImageDraw.Draw(page)
    if images:
        source = ImageEnhance.Color(open_rgb(images[0])).enhance(0.82)
        paste_cover(page, source, (w * 0.55, 0, w, h))
        veil = Image.new("RGBA", size, (0, 0, 0, 0))
        vd = ImageDraw.Draw(veil)
        vd.rectangle((w * 0.50, 0, w, h), fill=(16, 42, 58, 70))
        for x in range(int(w * 0.42), int(w * 0.72)):
            alpha = int(255 * (1 - (x - w * 0.42) / (w * 0.30)))
            vd.line((x, 0, x, h), fill=(16, 42, 58, max(0, alpha)))
        page = Image.alpha_composite(page.convert("RGBA"), veil).convert("RGB")
        draw = ImageDraw.Draw(page)
    slide_chrome(page, page_no, total, slide.get("section"), dark=True)
    draw.text((90, 176), "VISUAL STORY · 图片演示", font=font(24, True), fill=PALETTE["gold"])
    y = draw_text(draw, (88, 242), slide.get("title", "Untitled"), font(74, True), PALETTE["paper_2"], int(w * 0.47), 14, 4)
    subtitle = slide.get("subtitle") or "从素材洞察到视觉叙事的完整表达"
    draw_text(draw, (92, y + 28), subtitle, font(28), "#D7D8CF", int(w * 0.43), 10, 3)
    draw.rectangle((92, h - 136, 330, h - 126), fill=PALETTE["red"])
    draw.text((92, h - 108), "16:9 · IMAGE-FIRST · PDF", font=font(17, True), fill="#CED4D2")
    return page


def render_toc(slide, size, page_no, total):
    page = add_texture(Image.new("RGB", size, PALETTE["paper"]))
    draw = ImageDraw.Draw(page)
    w, h = size
    slide_chrome(page, page_no, total, slide.get("section"))
    draw.text((80, 102), "目录 / STORY MAP", font=font(25, True), fill=PALETTE["red"])
    draw_text(draw, (78, 150), slide.get("title", "叙事路径"), font(53, True), PALETTE["ink"], w - 156, 8, 2)
    cards = slide.get("toc_cards") or []
    if not cards:
        items = flatten_blocks(slide.get("blocks"))[:6]
        cards = [{"num": f"{i + 1:02d}", "title": item, "desc": ""} for i, item in enumerate(items)]
    cards = cards[:6]
    cols = 3 if len(cards) > 4 else 2
    rows = max(1, math.ceil(len(cards) / cols))
    gap, x0, y0 = 22, 80, 285
    card_w = (w - 160 - gap * (cols - 1)) // cols
    card_h = (h - y0 - 82 - gap * (rows - 1)) // rows
    for index, card in enumerate(cards):
        col, row = index % cols, index // cols
        x, y = x0 + col * (card_w + gap), y0 + row * (card_h + gap)
        rounded(draw, (x, y, x + card_w, y + card_h), 22, PALETTE["paper_2"], "#D7C6A4", 2)
        draw.text((x + 24, y + 20), str(card.get("num") or f"{index + 1:02d}"), font=font(36, True), fill=PALETTE["red"])
        draw_text(draw, (x + 24, y + 78), card.get("title", ""), font(27, True), PALETTE["ink"], card_w - 48, 5, 2)
        draw_text(draw, (x + 24, y + card_h - 60), card.get("desc", ""), font(16), PALETTE["muted"], card_w - 48, 4, 2)
    return page


def render_section(slide, images, size, page_no, total):
    w, h = size
    page = Image.new("RGB", size, PALETTE["red"])
    draw = ImageDraw.Draw(page)
    if images:
        source = ImageEnhance.Color(open_rgb(images[0])).enhance(0.6).filter(ImageFilter.GaussianBlur(1.2))
        paste_cover(page, source, (w * 0.50, 0, w, h))
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle((w * 0.42, 0, w, h), fill=(203, 75, 67, 125))
        page = Image.alpha_composite(page.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(page)
    slide_chrome(page, page_no, total, slide.get("section"), dark=True)
    number = str(slide.get("section_index") or page_no).zfill(2)
    draw.text((82, 130), number, font=font(150, True), fill="#E7B04B")
    draw_text(draw, (88, 350), slide.get("title", "章节"), font(68, True), PALETTE["white"], int(w * 0.48), 12, 4)
    draw.line((92, h - 142, 480, h - 142), fill=PALETTE["white"], width=3)
    draw.text((92, h - 112), "CHAPTER TRANSITION", font=font(18, True), fill="#F3DCC9")
    return page


def render_gallery(slide, images, size, page_no, total):
    page = add_texture(Image.new("RGB", size, PALETTE["paper_2"]))
    draw = ImageDraw.Draw(page)
    w, h = size
    slide_chrome(page, page_no, total, slide.get("section"))
    draw_text(draw, (78, 103), slide.get("title", "视觉证据"), font(47, True), PALETTE["ink"], w - 156, 8, 2)
    images = images[:6]
    cols = 3 if len(images) > 4 else 2
    rows = max(1, math.ceil(len(images) / cols))
    gap, x0, y0 = 18, 78, 226
    cell_w = (w - 156 - gap * (cols - 1)) // cols
    cell_h = (h - y0 - 72 - gap * (rows - 1)) // rows
    for index, item in enumerate(images):
        col, row = index % cols, index // cols
        x, y = x0 + col * (cell_w + gap), y0 + row * (cell_h + gap)
        rounded(draw, (x, y, x + cell_w, y + cell_h), 18, "#E3D7BF", "#CFB990", 2)
        paste_contain(page, open_rgb(item), (x + 10, y + 10, x + cell_w - 10, y + cell_h - 10), PALETTE["ink"])
        badge = str(item.get("id") or index + 1)
        rounded(draw, (x + 16, y + 16, x + 152, y + 51), 14, PALETTE["ink"])
        draw.text((x + 30, y + 22), badge[:12], font=font(15, True), fill=PALETTE["white"])
    return page


def content_frame(slide, size, page_no, total, label):
    page = add_texture(Image.new("RGB", size, PALETTE["paper_2"]))
    draw = ImageDraw.Draw(page)
    w, _ = size
    slide_chrome(page, page_no, total, slide.get("section"))
    draw.text((78, 103), label, font=font(20, True), fill=PALETTE["red"])
    title_y = draw_text(draw, (78, 140), slide.get("title", ""), font(47, True), PALETTE["ink"], w - 156, 8, 2)
    return page, draw, max(245, title_y + 22)


def render_compare(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "COMPARE · 对照")
    w, h = size
    items = flatten_blocks(slide.get("blocks"))
    split = max(1, math.ceil(len(items) / 2))
    groups = [items[:split], items[split:]]
    for col, group in enumerate(groups):
        x1 = 78 + col * ((w - 176) // 2 + 20)
        x2 = 78 + (col + 1) * ((w - 176) // 2) + col * 20
        rounded(draw, (x1, top, x2, h - 76), 24, PALETTE["paper"], PALETTE["red"] if col == 0 else PALETTE["blue"], 3)
        draw.text((x1 + 26, top + 24), "A / BEFORE" if col == 0 else "B / AFTER", font=font(22, True), fill=PALETTE["red"] if col == 0 else PALETTE["blue"])
        y = top + 78
        for value in group[:4]:
            y = draw_text(draw, (x1 + 28, y), "• " + value, font(23), PALETTE["ink"], x2 - x1 - 56, 6, 3) + 18
    draw.ellipse((w // 2 - 38, top + 100, w // 2 + 38, top + 176), fill=PALETTE["ink"])
    draw.text((w // 2 - 22, top + 121), "VS", font=font(21, True), fill=PALETTE["white"])
    return page


def render_timeline(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "FLOW · 路径")
    w, h = size
    items = flatten_blocks(slide.get("blocks"))[:5]
    if not items:
        items = [slide.get("takeaway") or "确认关键检查点"]
    y = top + 70
    draw.line((130, y, w - 130, y), fill=PALETTE["gold"], width=8)
    step_w = (w - 260) / max(1, len(items) - 1)
    for index, value in enumerate(items):
        x = int(130 + index * step_w)
        draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill=PALETTE["red"] if index % 2 == 0 else PALETTE["blue"])
        draw.text((x - 10, y - 18), str(index + 1), font=font(24, True), fill=PALETTE["white"])
        box_x = max(78, min(x - 120, w - 318))
        rounded(draw, (box_x, y + 58, box_x + 240, h - 86), 18, PALETTE["paper"], "#D2C09E", 2)
        draw_text(draw, (box_x + 18, y + 82), value, font(21, index == 0), PALETTE["ink"], 204, 6, 5)
    return page


def render_kpi(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "KPI · 关键数字")
    w, h = size
    items = flatten_blocks(slide.get("blocks"))[:4] or [slide.get("takeaway") or "关键指标"]
    card_w = (w - 156 - 22 * (len(items) - 1)) // len(items)
    for index, value in enumerate(items):
        x = 78 + index * (card_w + 22)
        rounded(draw, (x, top, x + card_w, h - 80), 24, PALETTE["ink"] if index == 0 else PALETTE["paper"], PALETTE["gold"], 2)
        match = re.search(r"[-+]?\d[\d,.]*\s*(?:%|倍|万|亿|天|项|个)?", value)
        number = match.group(0) if match else f"0{index + 1}"
        draw_text(draw, (x + 24, top + 55), number, font(54, True), PALETTE["gold"] if index == 0 else PALETTE["red"], card_w - 48, 6, 2)
        draw_text(draw, (x + 24, top + 175), value, font(22), PALETTE["white"] if index == 0 else PALETTE["ink"], card_w - 48, 7, 6)
    return page


def render_table(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "MATRIX · 矩阵")
    w, h = size
    rows = next((block.get("rows") for block in slide.get("blocks", []) if block.get("type") == "table"), None)
    if not rows:
        values = flatten_blocks(slide.get("blocks"))[:6]
        rows = [[str(i + 1), value] for i, value in enumerate(values)]
    rows = rows[:8]
    cols = max((len(row) for row in rows), default=1)
    row_h = max(42, (h - top - 76) // max(1, len(rows)))
    col_w = (w - 156) // cols
    for ri, row in enumerate(rows):
        for ci in range(cols):
            x1, y1 = 78 + ci * col_w, top + ri * row_h
            fill = PALETTE["ink"] if ri == 0 else PALETTE["paper"] if ri % 2 else PALETTE["paper_2"]
            draw.rectangle((x1, y1, x1 + col_w, y1 + row_h), fill=fill, outline="#C7B58F", width=2)
            draw_text(draw, (x1 + 14, y1 + 10), row[ci] if ci < len(row) else "", font(18, ri == 0), PALETTE["white"] if ri == 0 else PALETTE["ink"], col_w - 28, 3, 2)
    return page


def render_quote(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "QUOTE · 主张")
    w, h = size
    value = next((b.get("text") for b in slide.get("blocks", []) if b.get("type") == "quote"), None) or (flatten_blocks(slide.get("blocks")) or [""])[0]
    draw.text((100, top - 16), "“", font=font(138, True), fill=PALETTE["gold"])
    draw_text(draw, (190, top + 60), value, font(42, True), PALETTE["ink"], w - 330, 14, 6)
    draw.line((190, h - 130, w - 190, h - 130), fill=PALETTE["red"], width=5)
    return page


def render_image_hero(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "HERO · 主视觉")
    w, h = size
    if images:
        paste_cover(page, open_rgb(images[0]), (78, top, w - 78, h - 76))
        veil = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(veil).rectangle((78, h - 265, w - 78, h - 76), fill=(16, 42, 58, 185))
        page = Image.alpha_composite(page.convert("RGBA"), veil).convert("RGB")
        draw = ImageDraw.Draw(page)
        for index, extra in enumerate(images[1:4]):
            x1 = w - 98 - (index + 1) * 170
            rounded(draw, (x1 - 6, top + 20, x1 + 154, top + 126), 12, PALETTE["paper_2"], PALETTE["gold"], 2)
            paste_contain(page, open_rgb(extra), (x1, top + 26, x1 + 148, top + 120), PALETTE["ink"])
    items = flatten_blocks(slide.get("blocks"))[:3]
    draw_text(draw, (112, h - 230), " · ".join(items), font(24, True), PALETTE["white"], w - 224, 7, 4)
    return page


def render_two_column(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, f"{(slide.get('layout_pattern') or 'TWO COLUMN').upper()} · 蓝图")
    w, h = size
    values = flatten_blocks(slide.get("blocks"))[:6]
    groups = slide.get("groups") or []
    if groups:
        values = [f"{g.get('title')}: " + " / ".join(g.get('items') or []) for g in groups]
    pattern = slide.get("layout_pattern")
    if pattern == "center-hub":
        hub_w = int(w * 0.43)
        rounded(draw, (78, top + 70, hub_w, h - 150), 30, PALETTE["ink"], PALETTE["gold"], 3)
        draw_text(draw, (112, top + 118), values[0] if values else slide.get("title", ""), font(30, True), PALETTE["white"], hub_w - 150, 9, 5)
        branch_values = values[1:] or ["识别", "秩序", "延展"]
        branch_h = min(128, (h - top - 110) // len(branch_values))
        for index, value in enumerate(branch_values):
            y = top + 28 + index * (branch_h + 22)
            draw.line((hub_w, top + 220, int(w * 0.55), y + branch_h // 2), fill=PALETTE["gold"], width=4)
            rounded(draw, (int(w * 0.55), y, w - 78, y + branch_h), 20, PALETTE["paper"], PALETTE["red"] if index == 0 else PALETTE["blue"], 2)
            draw_text(draw, (int(w * 0.55) + 24, y + 22), value, font(22, index == 0), PALETTE["ink"], int(w * 0.37), 6, 3)
        return page
    if pattern == "tri-loop":
        loop_values = (values or ["识别", "秩序", "延展"])[:3]
        positions = [(w // 2 - 190, top + 5), (int(w * 0.25) - 170, top + 240), (int(w * 0.75) - 170, top + 240)]
        centers = [(x + 170, y + 75) for x, y in positions]
        for start, end in zip(centers, centers[1:] + centers[:1]):
            draw.line((*start, *end), fill=PALETTE["gold"], width=8)
        draw.ellipse((w // 2 - 82, top + 180, w // 2 + 82, top + 344), fill=PALETTE["ink"], outline=PALETTE["gold"], width=5)
        draw.text((w // 2 - 46, top + 242), "闭环", font=font(28, True), fill=PALETTE["white"])
        for index, (value, (x, y)) in enumerate(zip(loop_values, positions)):
            rounded(draw, (x, y, x + 340, y + 150), 28, PALETTE["paper"], [PALETTE["red"], PALETTE["blue"], PALETTE["gold"]][index], 4)
            draw_text(draw, (x + 26, y + 32), value, font(23, True), PALETTE["ink"], 288, 6, 4)
        return page
    if pattern == "hierarchy-space":
        layer_values = values or ["战略层", "能力层", "执行层"]
        for index, value in enumerate(layer_values[:5]):
            shrink = index * 70
            x1, x2 = 120 + shrink, w - 120 - shrink
            y1 = top + index * 105
            rounded(draw, (x1, y1, x2, y1 + 82), 18, PALETTE["ink"] if index == 0 else PALETTE["paper"], PALETTE["gold"], 2)
            draw_text(draw, (x1 + 26, y1 + 20), f"L{index + 1}  {value}", font(22, index == 0), PALETTE["white"] if index == 0 else PALETTE["ink"], x2 - x1 - 52, 5, 2)
        return page
    variant = slide.get("layout_variant") or "asym-cards"
    split = 0.58 if variant in {"hub-left", "anchor-right", "num-anchor"} else 0.5
    left_w = int((w - 176) * split)
    for index, value in enumerate(values):
        col = 0 if index < math.ceil(len(values) / 2) else 1
        row = index if col == 0 else index - math.ceil(len(values) / 2)
        x = 78 if col == 0 else 98 + left_w
        cw = left_w if col == 0 else w - x - 78
        ch = 118
        y = top + row * (ch + 18)
        rounded(draw, (x, y, x + cw, min(y + ch, h - 76)), 20, PALETTE["ink"] if index == 0 else PALETTE["paper"], PALETTE["gold"], 2)
        draw_text(draw, (x + 22, y + 22), value, font(22, index == 0), PALETTE["white"] if index == 0 else PALETTE["ink"], cw - 44, 5, 3)
    return page


def render_content(slide, images, size, page_no, total):
    page = add_texture(Image.new("RGB", size, PALETTE["paper_2"]))
    draw = ImageDraw.Draw(page)
    w, h = size
    slide_chrome(page, page_no, total, slide.get("section"))
    draw.text((78, 103), (slide.get("role") or "CONTENT").replace("-", " ").upper(), font=font(20, True), fill=PALETTE["red"])
    title_y = draw_text(draw, (78, 140), slide.get("title", ""), font(49, True), PALETTE["ink"], w - 156, 8, 2)
    top = max(245, title_y + 22)
    items = flatten_blocks(slide.get("blocks"))
    if images:
        image_box = (78, top, int(w * 0.63), h - 76)
        rounded(draw, image_box, 24, PALETTE["ink"], "#BDA67D", 2)
        paste_contain(page, open_rgb(images[0]), (image_box[0] + 12, image_box[1] + 12, image_box[2] - 12, image_box[3] - 12), PALETTE["ink"])
        tx, ty = int(w * 0.67), top
        for index, item in enumerate(items[:5]):
            draw.ellipse((tx, ty + 5, tx + 18, ty + 23), fill=[PALETTE["red"], PALETTE["gold"], PALETTE["blue"]][index % 3])
            ty = draw_text(draw, (tx + 34, ty), item, font(23, index == 0), PALETTE["ink"], w - tx - 82, 6, 4) + 20
        if len(images) > 1:
            thumb_w, thumb_h = 142, 96
            for index, extra in enumerate(images[1:4]):
                x, y = w - 78 - (index + 1) * (thumb_w + 10), h - 78 - thumb_h
                rounded(draw, (x - 5, y - 5, x + thumb_w + 5, y + thumb_h + 5), 10, PALETTE["paper"])
                paste_contain(page, open_rgb(extra), (x, y, x + thumb_w, y + thumb_h), PALETTE["ink"])
    else:
        cards = items[:6] or [slide.get("takeaway") or "本页聚焦一个清晰结论。"]
        cols, rows, gap = 2, math.ceil(len(cards) / 2), 20
        card_w = (w - 156 - gap) // 2
        card_h = (h - top - 84 - gap * (rows - 1)) // rows
        for index, item in enumerate(cards):
            col, row = index % cols, index // cols
            x, y = 78 + col * (card_w + gap), top + row * (card_h + gap)
            rounded(draw, (x, y, x + card_w, y + card_h), 22, PALETTE["paper"], "#D2C09E", 2)
            draw.text((x + 24, y + 18), f"{index + 1:02d}", font=font(28, True), fill=PALETTE["red"])
            draw_text(draw, (x + 24, y + 64), item, font(24, index == 0), PALETTE["ink"], card_w - 48, 7, 4)
    takeaway = slide.get("takeaway")
    if takeaway:
        rounded(draw, (w * 0.64, h - 178, w - 78, h - 76), 18, PALETTE["ink"])
        draw_text(draw, (w * 0.66, h - 157), takeaway, font(20, True), PALETTE["white"], int(w * 0.29), 5, 3)
    return page


def render_closing(slide, images, size, page_no, total):
    w, h = size
    page = Image.new("RGB", size, PALETTE["ink"])
    draw = ImageDraw.Draw(page)
    if images:
        source = open_rgb(images[0]).filter(ImageFilter.GaussianBlur(2))
        paste_cover(page, source, (0, 0, w, h))
        page = Image.alpha_composite(page.convert("RGBA"), Image.new("RGBA", size, (16, 42, 58, 195))).convert("RGB")
        draw = ImageDraw.Draw(page)
    slide_chrome(page, page_no, total, slide.get("section"), dark=True)
    draw.text((80, 198), "END NOTE · 收束", font=font(24, True), fill=PALETTE["gold"])
    draw_text(draw, (78, 268), slide.get("title", "谢谢"), font(72, True), PALETTE["white"], w - 300, 14, 3)
    draw.rectangle((80, h - 170, 420, h - 160), fill=PALETTE["red"])
    draw.text((80, h - 132), "让视觉成为叙事的证据。", font=font(25), fill="#D8DDD8")
    return page


def render_slide(slide, images, size, page_no, total):
    role = effective_role(slide)
    if role == "cover":
        return render_cover(slide, images, size, page_no, total)
    if role == "toc":
        return render_toc(slide, size, page_no, total)
    if role == "section":
        return render_section(slide, images, size, page_no, total)
    if role == "gallery":
        return render_gallery(slide, images, size, page_no, total)
    if role == "compare":
        return render_compare(slide, images, size, page_no, total)
    if role == "timeline":
        return render_timeline(slide, images, size, page_no, total)
    if role == "kpi":
        return render_kpi(slide, images, size, page_no, total)
    if role == "table":
        return render_table(slide, images, size, page_no, total)
    if role == "quote":
        return render_quote(slide, images, size, page_no, total)
    if role == "image-hero":
        return render_image_hero(slide, images, size, page_no, total)
    if role == "two-column":
        return render_two_column(slide, images, size, page_no, total)
    if role == "closing":
        return render_closing(slide, images, size, page_no, total)
    return render_content(slide, images, size, page_no, total)


def build_pdf(jpegs, output, width, height):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    page_width = 13.333333 * 72
    page_height = page_width * height / width
    document = canvas.Canvas(str(output), pagesize=(page_width, page_height), pageCompression=1)
    document.setTitle(output.stem)
    for path in jpegs:
        document.drawImage(str(path), 0, 0, width=page_width, height=page_height, preserveAspectRatio=False)
        document.showPage()
    document.save()


def main():
    args = parse_args()
    if DEPENDENCY_ERROR:
        raise SystemExit("图片 PDF 路线需要 Pillow 与 reportlab：python3 -m pip install Pillow reportlab") from DEPENDENCY_ERROR
    if args.width < 800 or args.height < 450:
        raise SystemExit("输出尺寸过小；建议保持默认 1600×900")
    if abs(args.width / args.height - 16 / 9) > 0.01:
        raise SystemExit("图片 PDF 路线只接受 16:9 输出尺寸")
    plan = load_json(args.ir)
    if plan.get("schema") != "SlidesPlan" or not isinstance(plan.get("slides"), list):
        raise SystemExit("--ir 必须是含 slides[] 的 SlidesPlan")
    apply_theme(plan)
    manifest = load_json(args.manifest)
    index = resolve_manifest(args.manifest, manifest)
    missing_files = [key for key, item in index.items() if not Path(item["_path"]).exists()]
    if missing_files:
        raise SystemExit("图片文件不存在：" + ", ".join(missing_files))
    output = Path(args.output).resolve()
    slides_dir = Path(args.slides_dir).resolve() if args.slides_dir else output.parent / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    total = len(plan["slides"])
    used_ids, jpegs, slide_rows = set(), [], []
    for page_no, slide in enumerate(plan["slides"], start=1):
        TEXT_OVERFLOWS.clear()
        images = resolve_slide_images(slide, index)
        used_ids.update(image_id(item) for item in images if image_id(item))
        page = render_slide(slide, images, (args.width, args.height), page_no, total)
        png_path = slides_dir / f"slide-{page_no:02d}.png"
        jpg_path = slides_dir / f"slide-{page_no:02d}.jpg"
        audit = {
            "schema": "ImageSlideAudit", "page": page_no, "role": effective_role(slide),
            "layout_pattern": slide.get("layout_pattern"), "layout_variant": slide.get("layout_variant"),
            "ir_sha256": hashlib.sha256(Path(args.ir).read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
            "source_texts": source_texts(slide), "image_ids": [image_id(item) for item in images],
            "text_overflows": list(TEXT_OVERFLOWS),
        }
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("image_pdf_audit", json.dumps(audit, ensure_ascii=False, sort_keys=True))
        page.save(png_path, "PNG", optimize=True, pnginfo=pnginfo)
        page.save(jpg_path, "JPEG", quality=args.quality, optimize=True, progressive=True)
        jpegs.append(jpg_path)
        slide_rows.append({"page": page_no, "role": effective_role(slide), "source_role": slide.get("role"), "layout_pattern": slide.get("layout_pattern"), "layout_variant": slide.get("layout_variant"), "title": slide.get("title"), "image_ids": [image_id(item) for item in images], "png": str(png_path), "text_overflows": list(TEXT_OVERFLOWS)})
    build_pdf(jpegs, output, args.width, args.height)
    manifest_ids = set(index)
    missing_ids = sorted(manifest_ids - used_ids)
    overflow_pages = [row["page"] for row in slide_rows if row["text_overflows"]]
    report = {
        "route": "image-pdf", "status": "pass" if not missing_ids else "warning",
        "pdf": str(output), "page_count": total, "slide_size": [args.width, args.height],
        "manifest_image_count": len(manifest_ids), "used_image_count": len(used_ids),
        "ir_sha256": hashlib.sha256(Path(args.ir).read_bytes()).hexdigest(), "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
        "theme": plan.get("theme_recommendation"), "used_image_ids": sorted(used_ids), "slides": slide_rows,
    }
    if missing_ids:
        report["missing_image_ids"] = missing_ids
    if overflow_pages:
        report["text_overflow_pages"] = overflow_pages
    report_path = Path(args.report).resolve() if args.report else output.with_suffix(".render.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.strict_images and (missing_ids or overflow_pages):
        print(("图片覆盖失败：" + ", ".join(missing_ids)) if missing_ids else ("文字溢出：" + ", ".join(map(str, overflow_pages))), file=sys.stderr)
        return 1
    print(f"Rendered {total} image slides -> {output}")
    print(f"Coverage {len(used_ids)}/{len(manifest_ids)} -> {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
