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
    from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin
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
TEXT_BOX_AUDIT = []
VISIBLE_CONTAINERS = []
ACTIVE_SEMANTICS = {"keywords": [], "motifs": [], "evidence": {}}
ACTIVE_VISUAL_LANGUAGE = {}
USED_MOTIFS = []
VISUAL_ELEMENTS = []
IMAGE_PLACEMENTS = []
DERIVED_COMPONENTS = []
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
    parser.add_argument("--visual-language", help="由图片 MD 描述提取的 ProjectVisualLanguage JSON")
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
    if lines:
        widths = [text_width(draw, line, typeface) for line in lines]
        # The text frame is content-sized instead of inheriting the whole layout
        # column. This makes short copy a compact object while long copy expands.
        frame_width = max(widths)
        frame_height = len(lines) * line_height - line_gap
        ink_area = sum(max(1, width) * typeface.size for width in widths)
        frame_area = max(1, frame_width * frame_height)
        TEXT_BOX_AUDIT.append({
            "text": str(text), "x": round(float(x), 1), "y": round(float(xy[1]), 1),
            "width": frame_width, "height": frame_height, "font_size": typeface.size,
            "line_count": len(lines), "ink_fill_ratio": round(min(1.0, ink_area / frame_area), 4),
        })
    return y


def compact_panel_height(draw, texts, typeface, width, padding=44, line_gap=8, item_gap=14, minimum=96, maximum=360):
    """Size a visible card from its copy instead of from the remaining canvas."""
    heights = []
    for value in texts:
        lines = wrap_text(draw, value, typeface, width, None) or [""]
        heights.append(len(lines) * (typeface.size + line_gap) - line_gap)
    needed = padding * 2 + sum(heights) + item_gap * max(0, len(heights) - 1)
    return max(minimum, min(maximum, needed))


def record_container(box, texts, kind="card", padding=12):
    """Register the boundary users actually see, not a synthetic glyph frame."""
    x1, y1, x2, y2 = (int(round(value)) for value in box)
    VISIBLE_CONTAINERS.append({
        "kind": kind, "bbox": [x1, y1, x2, y2], "padding": int(padding),
        "texts": [str(value) for value in texts if str(value).strip()],
    })


def draw_semantic_motifs(page, page_no):
    """Draw small vector motifs selected by project semantics, never stock decoration."""
    motifs = list(dict.fromkeys(ACTIVE_SEMANTICS.get("motifs") or []))[:2]
    if not motifs:
        return page
    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = page.size
    preferred_anchors = (
        ((w - 155, 122), (92, 122), (w - 92, h - 92), (92, h - 92)),
        ((92, h - 92), (w - 92, h - 92), (92, 122), (w - 155, 122)),
    )
    color = hex_rgb(PALETTE["blue"]) + (196,)
    accent = hex_rgb(PALETTE["gold"]) + (224,)
    for motif_index, motif in enumerate(motifs):
        candidates = preferred_anchors[min(motif_index, len(preferred_anchors) - 1)]
        cx, cy = candidates[0]
        for candidate_x, candidate_y in candidates:
            candidate_bbox = (candidate_x - 58, candidate_y - 55, candidate_x + 58, candidate_y + 55)
            if not any(
                candidate_bbox[0] < placement["rendered_bbox"][2]
                and candidate_bbox[2] > placement["rendered_bbox"][0]
                and candidate_bbox[1] < placement["rendered_bbox"][3]
                and candidate_bbox[3] > placement["rendered_bbox"][1]
                for placement in IMAGE_PLACEMENTS
            ):
                cx, cy = candidate_x, candidate_y
                break
        bbox = [cx - 58, cy - 55, cx + 58, cy + 55]
        if motif in {"badge", "medal", "徽章", "勋章"}:
            draw.polygon(((cx - 20, cy - 35), (cx, cy + 5), (cx + 20, cy - 35)), fill=color)
            draw.ellipse((cx - 29, cy - 10, cx + 29, cy + 48), outline=accent, width=6)
            draw.ellipse((cx - 12, cy + 7, cx + 12, cy + 31), fill=accent)
        elif motif in {"ribbon", "绶带"}:
            draw.polygon(((cx - 42, cy - 18), (cx + 36, cy - 18), (cx + 18, cy), (cx + 36, cy + 18), (cx - 42, cy + 18)), fill=color)
        elif motif in {"star", "starburst", "星芒", "星"}:
            points = []
            for i in range(16):
                radius = 34 if i % 2 == 0 else 14
                angle = math.pi * i / 8 - math.pi / 2
                points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
            draw.polygon(points, fill=accent)
        elif motif in {"orbit", "space", "轨道", "太空"}:
            draw.ellipse((cx - 48, cy - 20, cx + 48, cy + 20), outline=color, width=5)
            draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=accent)
            draw.ellipse((cx + 34, cy - 18, cx + 46, cy - 6), fill=accent)
        elif motif in {"satellite", "卫星"}:
            draw.rectangle((cx - 13, cy - 13, cx + 13, cy + 13), fill=accent)
            draw.rectangle((cx - 54, cy - 10, cx - 19, cy + 10), outline=color, width=4)
            draw.rectangle((cx + 19, cy - 10, cx + 54, cy + 10), outline=color, width=4)
            draw.line((cx - 19, cy, cx + 19, cy), fill=color, width=4)
        elif motif in {"rocket", "火箭"}:
            draw.polygon(((cx, cy - 48), (cx + 20, cy + 14), (cx, cy + 32), (cx - 20, cy + 14)), fill=color)
            draw.polygon(((cx - 10, cy + 28), (cx, cy + 50), (cx + 10, cy + 28)), fill=accent)
        elif motif in {"leaf", "叶片", "生态"}:
            draw.ellipse((cx - 38, cy - 28, cx + 20, cy + 30), outline=color, width=5)
            draw.line((cx - 22, cy + 22, cx + 30, cy - 28), fill=accent, width=4)
        else:
            continue
        USED_MOTIFS.append(motif)
        VISUAL_ELEMENTS.append({"type": "semantic-motif", "semantic_id": motif, "bbox": bbox})
    composed = Image.alpha_composite(page.convert("RGBA"), overlay).convert("RGB")
    for element in VISUAL_ELEMENTS:
        crop = composed.crop(tuple(element["bbox"]))
        element["pixel_sha256"] = hashlib.sha256(crop.tobytes()).hexdigest()
    return composed


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
    fitted_size = fitted.size
    px = x1 + (target[0] - fitted.width) // 2
    py = y1 + (target[1] - fitted.height) // 2
    if background:
        panel = Image.new("RGB", target, background)
        panel.paste(fitted, ((target[0] - fitted.width) // 2, (target[1] - fitted.height) // 2))
        fitted = panel
        canvas_image.paste(fitted, (x1, y1))
    else:
        canvas_image.paste(fitted, (px, py))
    return [px, py, px + fitted_size[0], py + fitted_size[1]]


def place_project_image(page, item, box, purpose="content-evidence", background=None):
    """Place source material intact; project originals never become page backgrounds."""
    source = open_rgb(item)
    rendered = paste_contain(page, source, box, background)
    IMAGE_PLACEMENTS.append({
        "image_id": image_id(item), "purpose": purpose, "fit": "contain",
        "container_bbox": [int(round(value)) for value in box],
        "rendered_bbox": rendered, "source_size": list(source.size),
    })
    return rendered


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


def draw_derived_background(page, role):
    """Build a role-aware spaceflight field from the MD-derived language."""
    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = page.size
    dark = role in {"cover", "closing", "toc"}
    blue = hex_rgb(PALETTE["blue"]) + ((92 if dark else 42),)
    gold = hex_rgb(PALETTE["gold"]) + ((76 if dark else 34),)
    paper = hex_rgb(PALETTE["paper_2"]) + ((22 if dark else 92),)
    # Starfield and coordinate grid come directly from the MD descriptions.
    for i in range(38):
        x, y = (i * 271 + 53) % w, (i * 149 + 31) % h
        radius = 1 + i % 3
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=paper)
    if role not in {"cover", "closing"}:
        for x in range(70, w, 126):
            draw.line((x, 76, x, h-60), fill=hex_rgb(PALETTE["blue"]) + (13,), width=1)
        for y in range(94, h, 108):
            draw.line((54, y, w-54, y), fill=hex_rgb(PALETTE["blue"]) + (13,), width=1)
    # Asymmetric orbit map: no fixed badge/ribbon stock decoration remains.
    cx, cy = (int(w * .78), int(h * .42)) if role != "closing" else (int(w * .72), int(h * .52))
    for rx, ry, color, width in ((430, 210, blue, 7), (315, 118, gold, 4), (210, 68, paper, 3)):
        draw.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), outline=color, width=width)
    for angle in (18, 77, 139, 212, 286, 337):
        x = cx + math.cos(math.radians(angle)) * 315
        y = cy + math.sin(math.radians(angle)) * 118
        draw.rectangle((x-7, y-7, x+7, y+7), fill=gold)
    # Launch corridor / plume builds the diagonal motion shared by every role.
    draw.polygon(((0, h), (0, h-95), (w*.72, 0), (w*.83, 0)), fill=hex_rgb(PALETTE["blue"]) + (24,))
    draw.polygon(((w*.10, h), (w*.17, h), (w*.78, 0), (w*.74, 0)), fill=hex_rgb(PALETTE["gold"]) + (20,))
    DERIVED_COMPONENTS.extend([
        {"type": "theme-background", "source_motif": "starfield", "bbox": [0, 0, w, h]},
        {"type": "orbital-field", "source_motif": "orbit", "bbox": [max(0, cx-430), max(0, cy-210), w, min(h, cy+210)]},
        {"type": "launch-corridor", "source_motif": "rocket", "bbox": [0, 0, w, h]},
    ])
    return Image.alpha_composite(page.convert("RGBA"), overlay).convert("RGB")


def derived_card(draw, box, radius, fill, outline=None, width=1):
    """A chamfered mission panel derived from satellite wings and trajectory cuts."""
    x1, y1, x2, y2 = map(int, box)
    cut = min(24, max(10, (x2 - x1) // 20))
    points = ((x1+cut, y1), (x2, y1), (x2, y2-cut), (x2-cut, y2), (x1, y2), (x1, y1+cut))
    draw.polygon(points, fill=fill, outline=outline)
    if outline:
        draw.line(points + (points[0],), fill=outline, width=width)
    draw.line((x1+cut, y1, min(x2-16, x1+cut*5), y1), fill=PALETTE["gold"], width=4)
    draw.rectangle((x2-cut-8, y2-cut-8, x2-cut+8, y2-cut+8), fill=PALETTE["blue"])
    DERIVED_COMPONENTS.append({"type": "theme-container", "source_motif": "satellite", "bbox": [x1, y1, x2, y2]})


def draw_word_art(draw, xy, text, size, role, max_width, variant=0):
    """Render theme-fit display type with ascent, orbit and metal-layer cues."""
    x, y = map(int, xy)
    face = font(size, True)
    lines = wrap_text(draw, text, face, max_width, 4 if role in {"cover", "closing"} else 2)
    line_height = size + 12
    for index, line in enumerate(lines):
        ly = y + index * line_height
        if role in {"cover", "closing"}:
            draw.text((x+7, ly+7), line, font=face, fill=PALETTE["blue"], stroke_width=2, stroke_fill=PALETTE["ink"])
            draw.text((x, ly), line, font=face, fill=PALETTE["white"], stroke_width=2, stroke_fill=PALETTE["gold"])
            draw.line((x, ly+size+7, x+min(max_width, text_width(draw, line, face)), ly+size+7), fill=PALETTE["gold"], width=4)
        elif role == "section":
            # Four chapters deliberately use different, theme-derived display
            # treatments: launch ascent, orbital seal, engineering cut and
            # horizon convergence. They remain blue/white/gold as one family.
            chapter_style = int(variant or 0) % 4
            if chapter_style == 1:
                rule_width = min(max_width, text_width(draw, line, face))
                draw.text((x+10, ly-4), line, font=face, fill=PALETTE["paper"], stroke_width=4, stroke_fill=PALETTE["blue"])
                draw.text((x, ly), line, font=face, fill=PALETTE["ink"], stroke_width=1, stroke_fill=PALETTE["gold"])
                draw.line((x-18, ly+size//2, x+rule_width, ly+size//2), fill=PALETTE["gold"], width=3)
            elif chapter_style == 2:
                draw.rounded_rectangle((x-18, ly-12, x+min(max_width, text_width(draw, line, face))+26, ly+size+16), radius=24, outline=PALETTE["blue"], width=5)
                draw.text((x+4, ly+4), line, font=face, fill=PALETTE["gold"])
                draw.text((x, ly), line, font=face, fill=PALETTE["ink"], stroke_width=1, stroke_fill=PALETTE["paper_2"])
            elif chapter_style == 3:
                draw.polygon(((x-20, ly-10), (x+26, ly-10), (x+8, ly+size+14), (x-38, ly+size+14)), fill=PALETTE["gold"])
                draw.text((x+8, ly+6), line, font=face, fill=PALETTE["blue"], stroke_width=2, stroke_fill=PALETTE["paper_2"])
                draw.text((x, ly), line, font=face, fill=PALETTE["ink"])
            else:
                draw.text((x+8, ly+7), line, font=face, fill=PALETTE["blue"])
                draw.text((x, ly), line, font=face, fill=PALETTE["paper_2"], stroke_width=3, stroke_fill=PALETTE["ink"])
                draw.line((x, ly+size+10, x+min(max_width, text_width(draw, line, face)), ly+size+10), fill=PALETTE["gold"], width=7)
        else:
            draw.text((x+4, ly+4), line, font=face, fill="#B7D8E8")
            draw.text((x, ly), line, font=face, fill=PALETTE["ink"])
    if lines:
        widths = [text_width(draw, line, face) for line in lines]
        frame_width = max(widths)
        frame_height = len(lines) * line_height - 12
        ink_area = sum(max(1, width) * size for width in widths)
        TEXT_BOX_AUDIT.append({
            "text": str(text), "x": x, "y": y, "width": frame_width,
            "height": frame_height, "font_size": size, "line_count": len(lines),
            "ink_fill_ratio": round(min(1.0, ink_area / max(1, frame_width * frame_height)), 4),
            "style": (ACTIVE_VISUAL_LANGUAGE.get("word_art", {}).get(role, role)
                      + (f"-chapter-{int(variant or 0) % 4 + 1}" if role == "section" else "")),
        })
    DERIVED_COMPONENTS.append({"type": "word-art", "source_motif": "rocket", "bbox": [x, y, x+max_width, y+max(1, len(lines))*line_height]})
    return y + len(lines) * line_height


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


def apply_theme(plan, visual_language=None):
    global ACTIVE_SEMANTICS, ACTIVE_VISUAL_LANGUAGE
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
    ACTIVE_VISUAL_LANGUAGE = visual_language or plan.get("visual_language") or {}
    language_palette = ACTIVE_VISUAL_LANGUAGE.get("palette") or {}
    palette_map = {"ink": "deep_space", "paper": "silver", "paper_2": "paper", "gold": "champagne_gold", "blue": "ion_blue", "red": "plume"}
    for target, source in palette_map.items():
        value = language_palette.get(source)
        if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            PALETTE[target] = value
    semantics = plan.get("visual_semantics") or {
        "keywords": ACTIVE_VISUAL_LANGUAGE.get("keywords") or [],
        "motifs": ACTIVE_VISUAL_LANGUAGE.get("motifs") or [],
        "evidence": ACTIVE_VISUAL_LANGUAGE.get("evidence") or {},
    }
    ACTIVE_SEMANTICS = {
        "keywords": [str(value).strip() for value in semantics.get("keywords") or [] if str(value).strip()],
        "motifs": [str(value).strip() for value in semantics.get("motifs") or [] if str(value).strip()],
        "evidence": {str(key): str(value).strip() for key, value in (semantics.get("evidence") or {}).items() if str(value).strip()},
    }


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
    page = draw_derived_background(Image.new("RGB", size, PALETTE["ink"]), "cover")
    draw = ImageDraw.Draw(page)
    if images:
        # A 16:9 mission window keeps the source complete without large matte bands.
        derived_card(draw, (880, 250, w - 76, 640), 28, PALETTE["paper_2"], PALETTE["gold"], 3)
        place_project_image(page, images[0], (900, 264, w - 96, 604), "cover-evidence", PALETTE["ink"])
    slide_chrome(page, page_no, total, slide.get("section"), dark=True)
    draw.text((90, 176), "VISUAL STORY · 图片演示", font=font(24, True), fill=PALETTE["gold"])
    y = draw_word_art(draw, (88, 230), slide.get("title", "Untitled"), 70, "cover", int(w * 0.47))
    subtitle = slide.get("subtitle") or "从素材洞察到视觉叙事的完整表达"
    draw_text(draw, (92, y + 28), subtitle, font(28), "#D7D8CF", int(w * 0.43), 10, 3)
    draw.rectangle((92, h - 136, 330, h - 126), fill=PALETTE["red"])
    draw.text((92, h - 108), "16:9 · IMAGE-FIRST · PDF", font=font(17, True), fill="#CED4D2")
    return page


def render_toc(slide, size, page_no, total):
    page = draw_derived_background(Image.new("RGB", size, PALETTE["ink"]), "toc")
    draw = ImageDraw.Draw(page)
    w, h = size
    slide_chrome(page, page_no, total, slide.get("section"), dark=True)
    draw.text((80, 102), "目录 / ORBITAL STORY MAP", font=font(23, True), fill=PALETTE["gold"])
    draw_word_art(draw, (78, 148), slide.get("title", "叙事路径"), 47, "cover", int(w*.48))
    cards = slide.get("toc_cards") or []
    if not cards:
        items = flatten_blocks(slide.get("blocks"))[:6]
        cards = [{"num": f"{i + 1:02d}", "title": item, "desc": ""} for i, item in enumerate(items)]
    cards = cards[:6]
    cx, cy, rx, ry = int(w*.70), int(h*.56), int(w*.25), int(h*.29)
    draw.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), outline=PALETTE["gold"], width=5)
    draw.ellipse((cx-rx+48, cy-ry+34, cx+rx-48, cy+ry-34), outline=PALETTE["blue"], width=3)
    for index, card in enumerate(cards):
        angle = math.radians(-90 + index * 360 / max(1, len(cards)))
        x, y = int(cx + rx*math.cos(angle)), int(cy + ry*math.sin(angle))
        box_w, box_h = 264, 112
        bx = max(610, min(w-box_w-56, x-box_w//2))
        by = max(220, min(h-box_h-60, y-box_h//2))
        derived_card(draw, (bx, by, bx+box_w, by+box_h), 18, PALETTE["paper_2"], PALETTE["gold"], 2)
        record_container((bx, by, bx+box_w, by+box_h), [card.get("title", ""), card.get("desc", "")], "toc-orbit-node")
        draw.text((bx+18, by+14), str(card.get("num") or f"{index+1:02d}"), font=font(25, True), fill=PALETTE["blue"])
        draw_text(draw, (bx+62, by+17), card.get("title", ""), font(23, True), PALETTE["ink"], box_w-78, 4, 2)
        draw_text(draw, (bx+20, by+68), card.get("desc", ""), font(15), PALETTE["muted"], box_w-40, 3, 2)
    DERIVED_COMPONENTS.append({"type": "theme-flow", "source_motif": "orbit", "bbox": [cx-rx, cy-ry, cx+rx, cy+ry]})
    return page


def render_section(slide, images, size, page_no, total):
    w, h = size
    # Chapter transitions must stay inside the deck's blue/white visual system.
    # Red remains a small accent elsewhere, never a full-page transition field.
    page = draw_derived_background(Image.new("RGB", size, PALETTE["paper_2"]), "section")
    draw = ImageDraw.Draw(page)
    draw.polygon(((w * 0.63, 0), (w, 0), (w, h), (w * 0.48, h)), fill=PALETTE["blue"])
    draw.ellipse((w - 390, 130, w - 85, 435), outline=PALETTE["white"], width=5)
    draw.ellipse((w - 315, 205, w - 160, 360), outline=PALETTE["gold"], width=4)
    draw.line((w * 0.58, h - 125, w - 92, 132), fill=PALETTE["white"], width=3)
    DERIVED_COMPONENTS.append({"type": "theme-transition", "source_motif": "rocket", "bbox": [int(w*.48), 0, w, h]})
    if images:
        derived_card(draw, (w * .69, 170, w - 92, h - 150), 22, PALETTE["paper_2"], PALETTE["gold"], 3)
        place_project_image(page, images[0], (w * .70, 184, w - 106, h - 164), "section-evidence", PALETTE["ink"])
    slide_chrome(page, page_no, total, slide.get("section"))
    number = str(slide.get("section_index") or page_no).zfill(2)
    draw.text((82, 130), number, font=font(150, True), fill=PALETTE["blue"])
    draw_word_art(draw, (88, 350), slide.get("title", "章节"), 66, "section", int(w * 0.48), int(slide.get("section_index") or page_no) - 1)
    draw.line((92, h - 142, 480, h - 142), fill=PALETTE["blue"], width=3)
    draw.text((92, h - 112), "CHAPTER TRANSITION", font=font(18, True), fill=PALETTE["muted"])
    return page


def render_gallery(slide, images, size, page_no, total):
    page = draw_derived_background(add_texture(Image.new("RGB", size, PALETTE["paper_2"])), "gallery")
    draw = ImageDraw.Draw(page)
    w, h = size
    slide_chrome(page, page_no, total, slide.get("section"))
    draw_word_art(draw, (78, 103), slide.get("title", "视觉证据"), 45, "content", w - 156)
    images = images[:6]
    cols = 3 if len(images) > 4 else 2
    rows = max(1, math.ceil(len(images) / cols))
    gap, x0, y0 = 18, 78, 226
    cell_w = (w - 156 - gap * (cols - 1)) // cols
    cell_h = (h - y0 - 72 - gap * (rows - 1)) // rows
    for index, item in enumerate(images):
        col, row = index % cols, index // cols
        x, y = x0 + col * (cell_w + gap), y0 + row * (cell_h + gap)
        derived_card(draw, (x, y, x + cell_w, y + cell_h), 18, "#E3D7BF", "#CFB990", 2)
        badge = str(item.get("id") or index + 1)
        rounded(draw, (x + 16, y + 12, x + 152, y + 47), 14, PALETTE["ink"])
        draw.text((x + 30, y + 18), badge[:12], font=font(15, True), fill=PALETTE["white"])
        # Reserve a separate header strip: labels and decorative motifs must
        # never cover the source-derived rendered_bbox used for intactness QA.
        place_project_image(page, item, (x + 10, y + 54, x + cell_w - 10, y + cell_h - 10), "gallery-evidence", PALETTE["ink"])
    if len(images) == 1:
        # A single evidence image anchors the left; the right becomes an
        # information-bearing orbit instrument rather than decorative void.
        panel = (int(w*.55), y0, w-78, h-72)
        derived_card(draw, panel, 24, PALETTE["ink"], PALETTE["gold"], 3)
        record_container(panel, ["ORBITAL ORDER", "阵列", "精度", "协同"], "gallery-orbit-instrument", padding=22)
        px1, py1, px2, py2 = panel
        draw.text((px1+30, py1+24), "ORBITAL ORDER", font=font(22, True), fill=PALETTE["gold"])
        cx, cy = (px1+px2)//2, (py1+py2)//2+20
        for radius, color, width in ((150, PALETTE["blue"], 5), (104, PALETTE["gold"], 3), (58, PALETTE["paper"], 2)):
            draw.ellipse((cx-radius, cy-radius//2, cx+radius, cy+radius//2), outline=color, width=width)
        labels = (("阵列", cx-118, cy-22), ("精度", cx-24, cy-82), ("协同", cx+78, cy+18))
        for label, lx, ly in labels:
            draw.ellipse((lx-10, ly-10, lx+10, ly+10), fill=PALETTE["gold"])
            draw.text((lx+16, ly-16), label, font=font(22, True), fill=PALETTE["white"])
        DERIVED_COMPONENTS.append({"type": "theme-flow", "source_motif": "orbit", "bbox": [px1, py1, px2, py2]})
    return page


def content_frame(slide, size, page_no, total, label):
    page = draw_derived_background(add_texture(Image.new("RGB", size, PALETTE["paper_2"])), effective_role(slide))
    draw = ImageDraw.Draw(page)
    w, _ = size
    slide_chrome(page, page_no, total, slide.get("section"))
    draw.text((78, 103), label, font=font(20, True), fill=PALETTE["red"])
    title_y = draw_word_art(draw, (78, 140), slide.get("title", ""), 45, "content", w - 156)
    return page, draw, max(245, title_y + 22)


def render_compare(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "COMPARE · 对照")
    w, h = size
    items = flatten_blocks(slide.get("blocks"))
    split = max(1, math.ceil(len(items) / 2))
    groups = [items[:split], items[split:]]
    body_font = font(23)
    for col, group in enumerate(groups):
        x1 = 78 + col * ((w - 176) // 2 + 20)
        x2 = 78 + (col + 1) * ((w - 176) // 2) + col * 20
        panel_h = compact_panel_height(draw, ["• " + value for value in group], body_font, x2 - x1 - 56, padding=24, item_gap=16, minimum=120, maximum=h - top - 80) + 52
        panel_y = top + max(0, (h - 76 - top - panel_h) // 2)
        derived_card(draw, (x1, panel_y, x2, panel_y + panel_h), 24, PALETTE["paper"], PALETTE["red"] if col == 0 else PALETTE["blue"], 3)
        record_container((x1, panel_y, x2, panel_y + panel_h), ["A / BEFORE" if col == 0 else "B / AFTER", *group], "compare-card")
        draw.text((x1 + 26, panel_y + 24), "A / BEFORE" if col == 0 else "B / AFTER", font=font(22, True), fill=PALETTE["red"] if col == 0 else PALETTE["blue"])
        y = panel_y + 78
        for value in group[:4]:
            y = draw_text(draw, (x1 + 28, y), "• " + value, body_font, PALETTE["ink"], x2 - x1 - 56, 6, 3) + 18
    badge_y = top + (h - 76 - top) // 2
    draw.ellipse((w // 2 - 38, badge_y - 38, w // 2 + 38, badge_y + 38), fill=PALETTE["ink"])
    draw.text((w // 2 - 22, badge_y - 17), "VS", font=font(21, True), fill=PALETTE["white"])
    return page


def render_timeline(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "FLOW · 路径")
    w, h = size
    items = flatten_blocks(slide.get("blocks"))[:5]
    if not items:
        items = [slide.get("takeaway") or "确认关键检查点"]
    y = top + 70
    draw.arc((90, y - 70, w - 90, y + 100), 190, 350, fill=PALETTE["gold"], width=8)
    DERIVED_COMPONENTS.append({"type": "theme-flow", "source_motif": "orbit", "bbox": [90, y-70, w-90, y+100]})
    step_w = (w - 260) / max(1, len(items) - 1)
    for index, value in enumerate(items):
        x = int(130 + index * step_w)
        draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill=PALETTE["red"] if index % 2 == 0 else PALETTE["blue"])
        draw.text((x - 10, y - 18), str(index + 1), font=font(24, True), fill=PALETTE["white"])
        box_x = max(78, min(x - 120, w - 318))
        panel_h = compact_panel_height(draw, [value], font(21, index == 0), 204, padding=20, minimum=84, maximum=170)
        derived_card(draw, (box_x, y + 58, box_x + 240, y + 58 + panel_h), 18, PALETTE["paper"], "#D2C09E", 2)
        record_container((box_x, y + 58, box_x + 240, y + 58 + panel_h), [value], "flow-card")
        draw_text(draw, (box_x + 18, y + 82), value, font(21, index == 0), PALETTE["ink"], 204, 6, 5)
    return page


def render_kpi(slide, images, size, page_no, total):
    page, draw, top = content_frame(slide, size, page_no, total, "KPI · 关键数字")
    w, h = size
    items = flatten_blocks(slide.get("blocks"))[:4] or [slide.get("takeaway") or "关键指标"]
    card_w = (w - 156 - 22 * (len(items) - 1)) // len(items)
    body_font = font(22)
    number_font = font(54, True)
    natural_heights = []
    for index, value in enumerate(items):
        match = re.search(r"[-+]?\d[\d,.]*\s*(?:%|倍|万|亿|天|项|个)?", value)
        number = match.group(0) if match else f"0{index + 1}"
        natural_heights.append(compact_panel_height(draw, [number, value], body_font, card_w - 48, padding=24, line_gap=7, item_gap=18, minimum=166, maximum=216))
    card_h = max(natural_heights)
    card_y = top + max(8, (h - 80 - top - card_h) // 2)
    for index, value in enumerate(items):
        x = 78 + index * (card_w + 22)
        box = (x, card_y, x + card_w, card_y + card_h)
        derived_card(draw, box, 24, PALETTE["ink"] if index == 0 else PALETTE["paper"], PALETTE["gold"], 2)
        match = re.search(r"[-+]?\d[\d,.]*\s*(?:%|倍|万|亿|天|项|个)?", value)
        number = match.group(0) if match else f"0{index + 1}"
        record_container(box, [number, value], "kpi-card")
        draw_text(draw, (x + 24, card_y + 24), number, number_font, PALETTE["gold"] if index == 0 else PALETTE["red"], card_w - 48, 6, 2)
        draw_text(draw, (x + 24, card_y + 102), value, body_font, PALETTE["white"] if index == 0 else PALETTE["ink"], card_w - 48, 7, 4)
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
        derived_card(draw, (78, top, int(w * .69), h - 76), 24, PALETTE["ink"], PALETTE["gold"], 2)
        place_project_image(page, images[0], (92, top + 14, int(w * .69) - 14, h - 90), "hero-evidence", PALETTE["ink"])
        for index, extra in enumerate(images[1:4]):
            x1 = w - 98 - (index + 1) * 170
            rounded(draw, (x1 - 6, top + 20, x1 + 154, top + 126), 12, PALETTE["paper_2"], PALETTE["gold"], 2)
            place_project_image(page, extra, (x1, top + 26, x1 + 148, top + 120), "detail-evidence", PALETTE["ink"])
    items = flatten_blocks(slide.get("blocks"))[:3]
    draw_text(draw, (int(w * .72), top + 170), " · ".join(items), font(23, True), PALETTE["ink"], int(w * .23), 7, 7)
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
        hub_value = values[0] if values else slide.get("title", "")
        hub_font = font(30, True)
        hub_h = compact_panel_height(draw, [hub_value], hub_font, hub_w - 150, padding=42, minimum=150, maximum=280)
        hub_y = top + max(30, (h - 100 - top - hub_h) // 2)
        derived_card(draw, (78, hub_y, hub_w, hub_y + hub_h), 30, PALETTE["ink"], PALETTE["gold"], 3)
        draw_text(draw, (112, hub_y + (hub_h - hub_font.size) // 2 - 6), hub_value, hub_font, PALETTE["white"], hub_w - 150, 9, 5)
        branch_values = values[1:] or ["识别", "秩序", "延展"]
        branch_h = min(128, (h - top - 110) // len(branch_values))
        for index, value in enumerate(branch_values):
            y = top + 28 + index * (branch_h + 22)
            draw.line((hub_w, hub_y + hub_h // 2, int(w * 0.55), y + branch_h // 2), fill=PALETTE["gold"], width=4)
            derived_card(draw, (int(w * 0.55), y, w - 78, y + branch_h), 20, PALETTE["paper"], PALETTE["red"] if index == 0 else PALETTE["blue"], 2)
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
            derived_card(draw, (x, y, x + 340, y + 150), 28, PALETTE["paper"], [PALETTE["red"], PALETTE["blue"], PALETTE["gold"]][index], 4)
            draw_text(draw, (x + 26, y + 32), value, font(23, True), PALETTE["ink"], 288, 6, 4)
        return page
    if pattern == "hierarchy-space":
        layer_values = values or ["战略层", "能力层", "执行层"]
        for index, value in enumerate(layer_values[:5]):
            shrink = index * 70
            x1, x2 = 120 + shrink, w - 120 - shrink
            y1 = top + index * 105
            derived_card(draw, (x1, y1, x2, y1 + 82), 18, PALETTE["ink"] if index == 0 else PALETTE["paper"], PALETTE["gold"], 2)
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
        derived_card(draw, (x, y, x + cw, min(y + ch, h - 76)), 20, PALETTE["ink"] if index == 0 else PALETTE["paper"], PALETTE["gold"], 2)
        draw_text(draw, (x + 22, y + 22), value, font(22, index == 0), PALETTE["white"] if index == 0 else PALETTE["ink"], cw - 44, 5, 3)
    return page


def render_content(slide, images, size, page_no, total):
    page = draw_derived_background(add_texture(Image.new("RGB", size, PALETTE["paper_2"])), effective_role(slide))
    draw = ImageDraw.Draw(page)
    w, h = size
    slide_chrome(page, page_no, total, slide.get("section"))
    draw.text((78, 103), (slide.get("role") or "CONTENT").replace("-", " ").upper(), font=font(20, True), fill=PALETTE["red"])
    title_y = draw_word_art(draw, (78, 140), slide.get("title", ""), 47, "content", w - 156)
    top = max(245, title_y + 22)
    items = flatten_blocks(slide.get("blocks"))
    if images:
        image_box = (78, top, int(w * 0.63), h - 76)
        derived_card(draw, image_box, 24, PALETTE["ink"], "#BDA67D", 2)
        place_project_image(page, images[0], (image_box[0] + 12, image_box[1] + 12, image_box[2] - 12, image_box[3] - 12), "content-evidence", PALETTE["ink"])
        tx, ty = int(w * 0.67), top
        for index, item in enumerate(items[:5]):
            draw.ellipse((tx, ty + 5, tx + 18, ty + 23), fill=[PALETTE["red"], PALETTE["gold"], PALETTE["blue"]][index % 3])
            ty = draw_text(draw, (tx + 34, ty), item, font(23, index == 0), PALETTE["ink"], w - tx - 82, 6, 4) + 20
        if len(images) > 1:
            thumb_w, thumb_h = 142, 96
            for index, extra in enumerate(images[1:4]):
                x, y = w - 78 - (index + 1) * (thumb_w + 10), h - 78 - thumb_h
                derived_card(draw, (x - 5, y - 5, x + thumb_w + 5, y + thumb_h + 5), 10, PALETTE["paper"])
                place_project_image(page, extra, (x, y, x + thumb_w, y + thumb_h), "detail-evidence", PALETTE["ink"])
    else:
        cards = items[:6] or [slide.get("takeaway") or "本页聚焦一个清晰结论。"]
        cols, rows, gap = 2, math.ceil(len(cards) / 2), 20
        card_w = (w - 156 - gap) // 2
        card_font = font(24)
        card_h = max(compact_panel_height(draw, [item], card_font, card_w - 48, padding=30, minimum=132, maximum=205) for item in cards)
        grid_h = rows * card_h + gap * (rows - 1)
        grid_y = top + max(0, (h - 76 - top - grid_h) // 2)
        for index, item in enumerate(cards):
            col, row = index % cols, index // cols
            x, y = 78 + col * (card_w + gap), grid_y + row * (card_h + gap)
            derived_card(draw, (x, y, x + card_w, y + card_h), 22, PALETTE["paper"], "#D2C09E", 2)
            draw.text((x + 24, y + 18), f"{index + 1:02d}", font=font(28, True), fill=PALETTE["red"])
            draw_text(draw, (x + 24, y + 64), item, font(24, index == 0), PALETTE["ink"], card_w - 48, 7, 4)
    takeaway = slide.get("takeaway")
    if takeaway:
        derived_card(draw, (w * 0.64, h - 178, w - 78, h - 76), 18, PALETTE["ink"])
        draw_text(draw, (w * 0.66, h - 157), takeaway, font(20, True), PALETTE["white"], int(w * 0.29), 5, 3)
    return page


def render_closing(slide, images, size, page_no, total):
    w, h = size
    page = draw_derived_background(Image.new("RGB", size, PALETTE["ink"]), "closing")
    draw = ImageDraw.Draw(page)
    if images:
        derived_card(draw, (w * .66, 162, w - 88, h - 128), 26, PALETTE["paper_2"], PALETTE["gold"], 3)
        place_project_image(page, images[0], (w * .675, 178, w - 104, h - 144), "closing-evidence", PALETTE["ink"])
    slide_chrome(page, page_no, total, slide.get("section"), dark=True)
    draw.text((80, 198), "END NOTE · 收束", font=font(24, True), fill=PALETTE["gold"])
    draw_word_art(draw, (78, 260), slide.get("title", "谢谢"), 70, "closing", w - 300)
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
    visual_language = load_json(args.visual_language) if args.visual_language else None
    if visual_language and visual_language.get("schema") != "ProjectVisualLanguage":
        raise SystemExit("--visual-language 必须是 ProjectVisualLanguage")
    apply_theme(plan, visual_language)
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
        TEXT_BOX_AUDIT.clear()
        VISIBLE_CONTAINERS.clear()
        USED_MOTIFS.clear()
        VISUAL_ELEMENTS.clear()
        IMAGE_PLACEMENTS.clear()
        DERIVED_COMPONENTS.clear()
        images = resolve_slide_images(slide, index)
        used_ids.update(image_id(item) for item in images if image_id(item))
        page = render_slide(slide, images, (args.width, args.height), page_no, total)
        page = draw_semantic_motifs(page, page_no)
        png_path = slides_dir / f"slide-{page_no:02d}.png"
        jpg_path = slides_dir / f"slide-{page_no:02d}.jpg"
        audit = {
            "schema": "ImageSlideAudit", "page": page_no, "role": effective_role(slide),
            "layout_pattern": slide.get("layout_pattern"), "layout_variant": slide.get("layout_variant"),
            "ir_sha256": hashlib.sha256(Path(args.ir).read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
            "source_texts": source_texts(slide), "image_ids": [image_id(item) for item in images],
            "text_overflows": list(TEXT_OVERFLOWS),
            "text_boxes": list(TEXT_BOX_AUDIT),
            "visible_containers": list(VISIBLE_CONTAINERS),
            "semantic_keywords": list(ACTIVE_SEMANTICS["keywords"]),
            "approved_motifs": list(ACTIVE_SEMANTICS["motifs"]),
            "semantic_evidence": dict(ACTIVE_SEMANTICS["evidence"]),
            "visual_language_sha256": hashlib.sha256(json.dumps(ACTIVE_VISUAL_LANGUAGE, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            "used_motifs": list(USED_MOTIFS),
            "visual_elements": list(VISUAL_ELEMENTS),
            "image_placements": list(IMAGE_PLACEMENTS),
            "derived_components": list(DERIVED_COMPONENTS),
            "rendered_rgb_sha256": hashlib.sha256(page.tobytes()).hexdigest(),
        }
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("image_pdf_audit", json.dumps(audit, ensure_ascii=False, sort_keys=True))
        page.save(png_path, "PNG", optimize=True, pnginfo=pnginfo)
        page.save(jpg_path, "JPEG", quality=args.quality, optimize=True, progressive=True)
        jpegs.append(jpg_path)
        slide_rows.append({"page": page_no, "role": effective_role(slide), "source_role": slide.get("role"), "layout_pattern": slide.get("layout_pattern"), "layout_variant": slide.get("layout_variant"), "title": slide.get("title"), "image_ids": [image_id(item) for item in images], "png": str(png_path), "jpg": str(jpg_path), "png_rgb_sha256": hashlib.sha256(page.tobytes()).hexdigest(), "jpg_sha256": hashlib.sha256(jpg_path.read_bytes()).hexdigest(), "text_overflows": list(TEXT_OVERFLOWS), "text_box_count": len(TEXT_BOX_AUDIT), "visible_containers": list(VISIBLE_CONTAINERS), "visual_elements": list(VISUAL_ELEMENTS), "used_motifs": list(USED_MOTIFS), "image_placements": list(IMAGE_PLACEMENTS), "derived_components": list(DERIVED_COMPONENTS), "visual_language_sha256": audit["visual_language_sha256"]})
    build_pdf(jpegs, output, args.width, args.height)
    manifest_ids = set(index)
    missing_ids = sorted(manifest_ids - used_ids)
    overflow_pages = [row["page"] for row in slide_rows if row["text_overflows"]]
    report = {
        "route": "image-pdf", "status": "pass" if not missing_ids else "warning",
        "pdf": str(output), "page_count": total, "slide_size": [args.width, args.height],
        "manifest_image_count": len(manifest_ids), "used_image_count": len(used_ids),
        "ir_sha256": hashlib.sha256(Path(args.ir).read_bytes()).hexdigest(), "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
        "theme": plan.get("theme_recommendation"), "visual_semantics": ACTIVE_SEMANTICS,
        "visual_language": ACTIVE_VISUAL_LANGUAGE,
        "used_image_ids": sorted(used_ids), "slides": slide_rows,
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
