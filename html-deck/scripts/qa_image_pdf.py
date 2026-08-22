#!/usr/bin/env python3
"""Independent image-PDF QA: recompute truth from SlidesPlan, manifest and PNGs."""

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, deque
from pathlib import Path

DEPENDENCY_ERROR = None
try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover
    DEPENDENCY_ERROR = exc

SUPPORTED_ROLES = {
    "cover", "toc", "section", "gallery", "closing", "image-side", "image-hero",
    "compare", "timeline", "table", "kpi", "quote", "bullets", "two-column",
}
PATTERN_ROLES = {
    "timeline": "timeline", "path-flow": "timeline", "compare": "compare",
    "big-number": "kpi", "matrix": "table", "text-image": "image-side",
    "product-hero": "image-hero", "hero-details": "image-hero",
    "center-hub": "two-column", "tri-loop": "two-column", "asym-mix": "two-column",
    "hierarchy-space": "two-column",
}
ROLE_CAPACITY = {
    "cover": (4, 260), "toc": (12, 360), "section": (2, 100), "gallery": (2, 120),
    "closing": (3, 140), "image-side": (7, 520), "image-hero": (5, 400),
    "compare": (9, 600), "timeline": (6, 500), "table": (42, 900), "kpi": (6, 420),
    "quote": (4, 380), "bullets": (8, 620), "two-column": (9, 650),
}

# QA-owned visual contracts.  These are deliberately not imported from the
# renderer: changing a renderer declaration or crop hash must not change what
# QA considers a badge, satellite, orbit, and so on.
SEMANTIC_ALIASES = {
    "badge": "badge", "medal": "badge", "徽章": "badge", "勋章": "badge",
    "ribbon": "ribbon", "绶带": "ribbon",
    "star": "star", "starburst": "star", "星芒": "star", "星": "star",
    "orbit": "orbit", "space": "orbit", "轨道": "orbit", "太空": "orbit",
    "satellite": "satellite", "卫星": "satellite",
    "rocket": "rocket", "火箭": "rocket",
    "leaf": "leaf", "叶片": "leaf", "生态": "leaf",
}
CARD_FILL_COLORS = (
    (217, 236, 242), (239, 248, 250), (255, 255, 255),  # tech-dark
    (221, 232, 238), (244, 247, 248),                    # business-dark
    (241, 223, 197), (255, 248, 237),                    # warm-human
    (243, 232, 210), (250, 246, 236), (255, 253, 247),  # default
)
QA_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def image_pixels(image):
    """Use Pillow's current API while retaining compatibility with older releases."""
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter else image.getdata()


def parse_args():
    parser = argparse.ArgumentParser(description="基于 manifest/IR 独立检查图片型演示，不信任渲染报告汇总字段。")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--ir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--render-report", required=True, help="用于定位逐页 PNG/JPEG 并与 PNG 内嵌审计交叉核验；不读取其汇总结论")
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-width", type=int, default=1600)
    parser.add_argument("--min-height", type=int, default=900)
    return parser.parse_args()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def image_id(item):
    return str(item.get("id") if isinstance(item, dict) else item or "")


def slide_image_ids(slide):
    values = list(slide.get("images") or [])
    if slide.get("bg_image"):
        values.insert(0, slide["bg_image"])
    return [image_id(value) for value in values if image_id(value)]


def flatten_blocks(blocks):
    values = []
    for block in blocks or []:
        if block.get("type") == "list":
            values.extend(str(value) for value in block.get("items") or [])
        elif block.get("type") == "table":
            values.extend(" · ".join(map(str, row)) for row in block.get("rows") or [])
        elif block.get("text"):
            values.append(str(block["text"]))
    return values


def source_texts(slide):
    values = [str(slide.get("title") or "")]
    values.extend(flatten_blocks(slide.get("blocks")))
    values.extend(str(card.get("title") or "") for card in slide.get("toc_cards") or [])
    if slide.get("takeaway"):
        values.append(str(slide["takeaway"]))
    return [value for value in values if value]


def effective_role(slide):
    return PATTERN_ROLES.get(slide.get("layout_pattern"), slide.get("role") or "bullets")


def text_capacity_failures(slide, page):
    role = effective_role(slide)
    texts = source_texts(slide)
    failures = []
    max_items, max_chars = ROLE_CAPACITY.get(role, (0, 0))
    if len(texts) > max_items:
        failures.append(f"第 {page} 页文本块 {len(texts)} 超过 {role} 容量 {max_items}")
    if sum(len(re.sub(r"\s+", "", value)) for value in texts) > max_chars:
        failures.append(f"第 {page} 页文本总量超过 {role} 安全容量 {max_chars} 字")
    title_limit = 46 if role in {"cover", "section", "closing"} else 38
    if len(re.sub(r"\s+", "", str(slide.get("title") or ""))) > title_limit:
        failures.append(f"第 {page} 页标题超过 {role} 安全容量 {title_limit} 字")
    return failures


def story_structure_failures(slides):
    """Ensure every TOC node expands into a real chapter with content."""
    failures = []
    toc_slides = [slide for slide in slides if slide.get("role") == "toc"]
    if len(toc_slides) != 1:
        return [f"目录页数量必须为 1，实际为 {len(toc_slides)}"]
    toc_titles = [str(card.get("title") or "").strip() for card in toc_slides[0].get("toc_cards") or []]
    section_rows = [(index, slide) for index, slide in enumerate(slides) if slide.get("role") == "section"]
    section_titles = [str(slide.get("title") or slide.get("section") or "").strip() for _, slide in section_rows]
    if not 3 <= len(toc_titles) <= 6:
        failures.append(f"目录节点须为 3–6 个，实际为 {len(toc_titles)}")
    if toc_titles != section_titles:
        failures.append("目录节点与章节转场未按顺序一一对应")
    for order, (start, section_slide) in enumerate(section_rows, start=1):
        end = section_rows[order][0] if order < len(section_rows) else len(slides)
        title = section_titles[order - 1]
        if section_slide.get("section_index") != order:
            failures.append(f"章节“{title}”的 section_index 应为 {order}")
        content = [slide for slide in slides[start + 1:end] if slide.get("role") not in {"section", "closing"}]
        if not content:
            failures.append(f"目录章节“{title}”没有对应内容页")
        mismatched = [slide.get("page") for slide in content if str(slide.get("section") or "").strip() != title]
        if mismatched:
            failures.append(f"章节“{title}”内容页归属不一致：{mismatched}")
    return failures


def section_palette_failure(image, page):
    """Reject visually abrupt red-dominant chapter transitions."""
    sample = image.convert("RGB").resize((160, 90))
    pixels = list(image_pixels(sample))
    red_dominant = sum(1 for red, green, blue in pixels if red > 120 and red > green * 1.18 and red > blue * 1.18)
    ratio = red_dominant / max(1, len(pixels))
    return f"第 {page} 页章节转场红色主导像素占比 {ratio:.1%}，未延续蓝白视觉体系" if ratio > 0.18 else None


def rgb_sha256(image):
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def pixel_content_extent(image, bbox, padding):
    """Measure visible ink inside a flat rendered container from pixels alone."""
    x1, y1, x2, y2 = (int(value) for value in bbox)
    pad = max(8, int(padding or 0))
    crop = image.convert("RGB").crop((x1 + pad, y1 + pad, x2 - pad, y2 - pad))
    if crop.width <= 0 or crop.height <= 0:
        return 0.0, 0.0
    colors = Counter(image_pixels(crop.resize((max(1, crop.width // 4), max(1, crop.height // 4)))))
    background = colors.most_common(1)[0][0]
    points = []
    for y in range(crop.height):
        for x in range(crop.width):
            pixel = crop.getpixel((x, y))
            if sum(abs(pixel[channel] - background[channel]) for channel in range(3)) >= 80:
                points.append((x, y))
    if not points:
        return 0.0, 0.0
    xs, ys = zip(*points)
    return (max(xs) - min(xs) + 1) / crop.width, (max(ys) - min(ys) + 1) / crop.height


def _close_color(pixel, target, tolerance=14):
    return max(abs(pixel[channel] - target[channel]) for channel in range(3)) <= tolerance


def discover_visible_containers(image):
    """Find flat, card-sized page regions without consulting renderer output."""
    scale = 4
    sample = image.convert("RGB").resize((image.width // scale, image.height // scale))
    width, height = sample.size
    pixels = sample.load()
    mask = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            if any(_close_color(pixels[x, y], color) for color in CARD_FILL_COLORS):
                mask[y * width + x] = 1
    visited = bytearray(width * height)
    candidates = []
    for start_y in range(height):
        for start_x in range(width):
            start = start_y * width + start_x
            if not mask[start] or visited[start]:
                continue
            queue = deque([(start_x, start_y)])
            visited[start] = 1
            count = 0
            min_x = max_x = start_x
            min_y = max_y = start_y
            while queue:
                x, y = queue.popleft()
                count += 1
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        position = ny * width + nx
                        if mask[position] and not visited[position]:
                            visited[position] = 1
                            queue.append((nx, ny))
            box_width, box_height = max_x - min_x + 1, max_y - min_y + 1
            rectangularity = count / max(1, box_width * box_height)
            # Rounded cards retain >70% of their flat fill after text/lines are
            # excluded. Full-page backgrounds and tiny labels are not cards.
            if (box_width * scale >= 220 and box_height * scale >= 68
                    and box_width * box_height * scale * scale >= 18000
                    and rectangularity >= 0.68
                    and not (box_width > width * 0.91 and box_height > height * 0.91)):
                candidates.append({
                    "bbox": [min_x * scale, min_y * scale,
                             min(image.width, (max_x + 1) * scale),
                             min(image.height, (max_y + 1) * scale)],
                    "rectangularity": round(rectangularity, 3),
                })
    return candidates


def box_iou(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    union = max(1, (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection)
    return intersection / union


def boxes_overlap(first, second, margin=0):
    ax1, ay1, ax2, ay2 = map(float, first)
    bx1, by1, bx2, by2 = map(float, second)
    return ax1 - margin < bx2 and ax2 + margin > bx1 and ay1 - margin < by2 and ay2 + margin > by1


def background_edge_density(image, audit):
    """Estimate residual background busyness after masking narrative objects."""
    sample = image.convert("RGB").resize((320, 180))
    mask_draw = ImageDraw.Draw(sample)
    protected = []
    protected.extend(row.get("bbox") for row in audit.get("visible_containers") or [])
    protected.extend(row.get("rendered_bbox") for row in audit.get("image_placements") or [])
    protected.extend(row.get("bbox") for row in audit.get("visual_elements") or [])
    protected.extend([row.get("x"), row.get("y"), row.get("x", 0) + row.get("width", 0), row.get("y", 0) + row.get("height", 0)] for row in audit.get("text_boxes") or [])
    for box in protected:
        if len(box or []) == 4:
            scaled = tuple(int(value / 5) for value in box)
            mask_draw.rectangle(scaled, fill=(128, 128, 128))
    edges = sample.convert("L").filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(edges).mean[0] / 255.0


CHINESE_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def title_body_correspondence_failures(slide, page):
    """Independently verify count-bearing action titles against visible evidence."""
    role = effective_role(slide)
    if role == "kpi":
        return []
    title = str(slide.get("title") or "")
    match = re.search(r"([一二两三四五六七八九十]|\d+)\s*(种|步|段|款|项|张|组)", title)
    if not match:
        return []
    expected = int(match.group(1)) if match.group(1).isdigit() else CHINESE_NUMBERS[match.group(1)]
    if role == "gallery":
        actual, noun = len(slide.get("images") or []), "项目证据图"
    elif role in {"timeline", "compare", "two-column", "bullets"}:
        actual, noun = len(flatten_blocks(slide.get("blocks"))), "正文证据项"
    elif role == "toc":
        actual, noun = len(slide.get("toc_cards") or []), "目录节点"
    else:
        return []
    return [f"第 {page} 页标题承诺 {expected}{match.group(2)}，正文仅提供 {actual} 个{noun}"] if actual != expected else []


def expected_gallery_label(item):
    return re.sub(r"\s+", " ", str(item.get("audience_label") or item.get("alt") or "")).strip()


def qa_font(size):
    for candidate in QA_FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("未找到 QA 可用的中文字体")


def gallery_label_pixel_visible(image, row, expected):
    """Render the source-owned full name independently and verify its real ink."""
    bbox, origin = row.get("bbox") or [], row.get("text_origin") or []
    size = int(row.get("font_size") or 0)
    if len(bbox) != 4 or len(origin) != 2 or not 12 <= size <= 22:
        return False
    x1, y1, x2, y2 = map(int, bbox)
    if x1 < 0 or y1 < 0 or x2 > image.width or y2 > image.height or x2 <= x1 or y2 <= y1:
        return False
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).text(tuple(map(int, origin)), expected, font=qa_font(size), fill=255)
    mask_crop = mask.crop((x1, y1, x2, y2))
    actual = image.convert("RGB").crop((x1, y1, x2, y2))
    points = [(x, y) for y in range(mask_crop.height) for x in range(mask_crop.width)
              if mask_crop.getpixel((x, y)) >= 80]
    if not points:
        return False
    lit = lambda pixel: sum(pixel) / 3 >= 168 and max(pixel) - min(pixel) <= 75
    overall = sum(1 for point in points if lit(actual.getpixel(point))) / len(points)
    right_edge = max(x for x, _ in points)
    tail = [point for point in points if point[0] >= right_edge - max(10, (x2 - x1) // 5)]
    tail_ratio = sum(1 for point in tail if lit(actual.getpixel(point))) / max(1, len(tail))
    # CJK anti-aliasing leaves roughly 18–20% mid-tone edge pixels even when
    # renderer and QA use the same font. Missing tail glyphs remain near zero.
    return overall >= 0.76 and tail_ratio >= 0.76


def gallery_label_failures(slide, image, audit, report_row, manifest_index, page):
    if effective_role(slide) != "gallery":
        return []
    failures = []
    expected = []
    for image_id_value in slide_image_ids(slide)[:6]:
        item = manifest_index.get(image_id_value) or {}
        label = expected_gallery_label(item)
        expected.append((image_id_value, label))
        if not label or label == image_id_value or re.fullmatch(r"[a-z0-9_-]+", label, re.I):
            failures.append(f"第 {page} 页图集标签不完整：{image_id_value} 缺少观众可读名称")
    declared = audit.get("gallery_labels") or []
    if declared != (report_row.get("gallery_labels") or []):
        failures.append(f"第 {page} 页图集标签在 PNG 与渲染报告间不一致")
    if [row.get("image_id") for row in declared] != [value[0] for value in expected]:
        failures.append(f"第 {page} 页图集标签不完整：未与项目图片逐项对应")
    for index, (image_id_value, label) in enumerate(expected):
        if index >= len(declared):
            failures.append(f"第 {page} 页图集可见名称缺失：{label or image_id_value}")
            continue
        row = declared[index]
        if row.get("text") != label:
            failures.append(f"第 {page} 页图集标签不完整：{image_id_value} 应显示“{label}”")
        if not gallery_label_pixel_visible(image, row, label):
            failures.append(f"第 {page} 页图集可见名称未完整绘制：{label or image_id_value}")
    return failures


def new_visual_rule_failures(slide, image, audit, report_row, page):
    failures = []
    text_boxes = [[row.get("x", 0), row.get("y", 0), row.get("x", 0) + row.get("width", 0), row.get("y", 0) + row.get("height", 0)] for row in audit.get("text_boxes") or []]
    for element in audit.get("visual_elements") or []:
        bbox = element.get("bbox") or []
        if len(bbox) == 4 and any(boxes_overlap(bbox, text_box, 4) for text_box in text_boxes):
            failures.append(f"第 {page} 页图标插图遮挡文字；装饰元素必须删除或避让")
    word_art = audit.get("word_art") or []
    if word_art != (report_row.get("word_art") or []):
        failures.append(f"第 {page} 页艺术字几何在 PNG 与渲染报告间不一致")
    if not word_art:
        failures.append(f"第 {page} 页缺少艺术字主体几何审计")
    for row in word_art:
        text_bbox = row.get("text_bbox") or []
        if len(text_bbox) != 4:
            failures.append(f"第 {page} 页艺术字缺少文字主体边界")
            continue
        if any(len(box or []) == 4 and boxes_overlap(text_bbox, box) for box in row.get("ornament_bboxes") or []):
            failures.append(f"第 {page} 页艺术字字体与装饰线条重叠，文字主体性不足")
    narrative_load = len(audit.get("visible_containers") or []) + len(audit.get("image_placements") or [])
    if effective_role(slide) in {"toc", "gallery"} or narrative_load >= 4:
        density = background_edge_density(image, audit)
        if density > 0.105:
            failures.append(f"第 {page} 页叙事元素较多但背景未删减（独立边缘密度 {density:.1%}）")
    failures.extend(title_body_correspondence_failures(slide, page))
    return failures


def container_discovery_failures(image, containers, page):
    discovered = discover_visible_containers(image)
    declared = [row.get("bbox") or [] for row in containers if len(row.get("bbox") or []) == 4]
    failures = []
    for candidate in discovered:
        if not any(box_iou(candidate["bbox"], box) >= 0.48 for box in declared):
            failures.append(f"第 {page} 页像素发现漏报可见卡片：{candidate['bbox']}")
    return failures


def _template_mask(size, semantic_id):
    """Build a QA-owned shape template for an approved semantic family."""
    width, height = size
    mask = Image.new("1", size, 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = width // 2, height // 2
    sx, sy = width / 116.0, height / 110.0
    family = SEMANTIC_ALIASES.get(str(semantic_id))
    def box(left, top, right, bottom):
        return (int(cx + left * sx), int(cy + top * sy), int(cx + right * sx), int(cy + bottom * sy))
    line = max(2, int(round(5 * min(sx, sy))))
    if family == "badge":
        draw.polygon(((cx - int(20*sx), cy - int(35*sy)), (cx, cy + int(5*sy)), (cx + int(20*sx), cy - int(35*sy))), fill=1)
        draw.ellipse(box(-29, -10, 29, 48), outline=1, width=line)
        draw.ellipse(box(-12, 7, 12, 31), fill=1)
    elif family == "ribbon":
        draw.polygon(((cx-int(42*sx),cy-int(18*sy)),(cx+int(36*sx),cy-int(18*sy)),(cx+int(18*sx),cy),(cx+int(36*sx),cy+int(18*sy)),(cx-int(42*sx),cy+int(18*sy))), fill=1)
    elif family == "star":
        points = []
        for index in range(16):
            radius = 34 if index % 2 == 0 else 14
            angle = math.pi * index / 8 - math.pi / 2
            points.append((cx + radius * sx * math.cos(angle), cy + radius * sy * math.sin(angle)))
        draw.polygon(points, fill=1)
    elif family == "orbit":
        draw.ellipse(box(-48, -20, 48, 20), outline=1, width=line)
        draw.ellipse(box(-7, -7, 7, 7), fill=1)
        draw.ellipse(box(34, -18, 46, -6), fill=1)
    elif family == "satellite":
        draw.rectangle(box(-13, -13, 13, 13), fill=1)
        draw.rectangle(box(-54, -10, -19, 10), outline=1, width=line)
        draw.rectangle(box(19, -10, 54, 10), outline=1, width=line)
        draw.line((cx-int(19*sx), cy, cx+int(19*sx), cy), fill=1, width=line)
    elif family == "rocket":
        draw.polygon(((cx,cy-int(48*sy)),(cx+int(20*sx),cy+int(14*sy)),(cx,cy+int(32*sy)),(cx-int(20*sx),cy+int(14*sy))), fill=1)
        draw.polygon(((cx-int(10*sx),cy+int(28*sy)),(cx,cy+int(50*sy)),(cx+int(10*sx),cy+int(28*sy))), fill=1)
    elif family == "leaf":
        draw.ellipse(box(-38, -28, 20, 30), outline=1, width=line)
        draw.line((cx-int(22*sx),cy+int(22*sy),cx+int(30*sx),cy-int(28*sy)), fill=1, width=line)
    return mask


def semantic_template_score(crop, semantic_id):
    """Compare actual pixels with QA's template, independent of claimed hashes."""
    rgb = crop.convert("RGB")
    template = _template_mask(rgb.size, semantic_id)
    if not template.getbbox():
        return 0.0
    border = []
    for x in range(rgb.width):
        border.extend((rgb.getpixel((x, 0)), rgb.getpixel((x, rgb.height - 1))))
    for y in range(rgb.height):
        border.extend((rgb.getpixel((0, y)), rgb.getpixel((rgb.width - 1, y))))
    background = tuple(sorted(pixel[channel] for pixel in border)[len(border)//2] for channel in range(3))
    salient = Image.new("1", rgb.size, 0)
    salient_pixels = salient.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            pixel = rgb.getpixel((x, y))
            if sum(abs(pixel[channel] - background[channel]) for channel in range(3)) >= 42:
                salient_pixels[x, y] = 1
    template_values, salient_values = list(image_pixels(template)), list(image_pixels(salient))
    intersection = sum(1 for a, b in zip(template_values, salient_values) if a and b)
    expected_count = sum(bool(value) for value in template_values)
    salient_count = sum(bool(value) for value in salient_values)
    recall = intersection / max(1, expected_count)
    precision = intersection / max(1, salient_count)
    return 2 * precision * recall / max(1e-9, precision + recall)


def semantic_color_feature_failure(crop, semantic_id, page):
    """Reject strong features outside the QA-owned semantic family profile."""
    family = SEMANTIC_ALIASES.get(str(semantic_id))
    pixels = list(image_pixels(crop.convert("RGB").resize((58, 55))))
    green = sum(1 for red, green, blue in pixels
                if green > 75 and green > red * 1.28 and green > blue * 1.40)
    green_ratio = green / max(1, len(pixels))
    if family != "leaf" and green_ratio > 0.055:
        return f"第 {page} 页可见元素与 QA 独立 {semantic_id} 允许特征不匹配（叶片绿色 {green_ratio:.1%}）"
    return None


def visible_design_failures(image, audit, report_row, page, motifs):
    failures = []
    containers = audit.get("visible_containers") or []
    if containers != (report_row.get("visible_containers") or []):
        failures.append(f"第 {page} 页可见容器清单在 PNG 与渲染报告间不一致")
    required = audit.get("role") in {"compare", "timeline", "kpi"}
    if required and not containers:
        failures.append(f"第 {page} 页缺少真实可见容器清单")
    if required:
        failures.extend(container_discovery_failures(image, containers, page))
    for container in containers:
        bbox = container.get("bbox") or []
        if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            failures.append(f"第 {page} 页可见容器几何无效")
            continue
        width_ratio, height_ratio = pixel_content_extent(image, bbox, container.get("padding"))
        if not container.get("texts") or height_ratio < 0.34 or width_ratio < 0.10:
            failures.append(f"第 {page} 页可见容器文字占用过低（像素宽 {width_ratio:.1%} / 高 {height_ratio:.1%}）")
    elements = audit.get("visual_elements") or []
    if elements != (report_row.get("visual_elements") or []):
        failures.append(f"第 {page} 页可核验元素清单在 PNG 与渲染报告间不一致")
    used = []
    for element in elements:
        bbox = element.get("bbox") or []
        semantic_id = element.get("semantic_id")
        if len(bbox) != 4 or semantic_id not in motifs:
            failures.append(f"第 {page} 页存在未获语义批准的可见元素")
            continue
        actual = hashlib.sha256(image.convert("RGB").crop(tuple(bbox)).tobytes()).hexdigest()
        if actual != element.get("pixel_sha256"):
            failures.append(f"第 {page} 页可见元素像素与元素清单不一致")
        crop = image.convert("RGB").crop(tuple(bbox))
        score = semantic_template_score(crop, semantic_id)
        if score < 0.18:
            failures.append(f"第 {page} 页可见元素与 QA 独立 {semantic_id} 模板不匹配（特征分 {score:.2f}）")
        color_failure = semantic_color_feature_failure(crop, semantic_id, page)
        if color_failure:
            failures.append(color_failure)
        used.append(semantic_id)
    if used != (audit.get("used_motifs") or []):
        failures.append(f"第 {page} 页实际元素清单与设计母题声明不一致")
    return failures


def pdf_page_binding_failure(pdf_page, png_image, report_row, page):
    """Bind each PDF page to its PNG through the actual embedded raster."""
    try:
        candidates = list(pdf_page.images)
    except Exception as exc:
        return f"PDF 第 {page} 页无法提取内嵌页面图像：{exc}"
    if len(candidates) != 1:
        return f"PDF 第 {page} 页应恰好包含 1 张页面图像，实际 {len(candidates)}"
    embedded = candidates[0]
    jpg_path = Path(str(report_row.get("jpg") or ""))
    if not jpg_path.exists() or digest(jpg_path) != report_row.get("jpg_sha256"):
        return f"PDF 第 {page} 页对应 JPEG 文件与渲染报告不一致"
    decoded = embedded.image.convert("RGB")
    expected = png_image.convert("RGB")
    if decoded.size != expected.size:
        return f"PDF 第 {page} 页像素尺寸与逐页 PNG 不一致"
    difference = ImageChops.difference(decoded, expected)
    mean_delta = sum(ImageStat.Stat(difference).mean) / 3
    return f"PDF 第 {page} 页像素与逐页 PNG 不一致（平均色差 {mean_delta:.2f}）" if mean_delta > 5.0 else None


def semantic_contract_failures(plan, manifest):
    semantics = plan.get("visual_semantics") or {}
    keywords = [str(value).strip() for value in semantics.get("keywords") or [] if str(value).strip()]
    motifs = [str(value).strip() for value in semantics.get("motifs") or [] if str(value).strip()]
    evidence = {str(key): str(value).strip() for key, value in (semantics.get("evidence") or {}).items() if str(value).strip()}
    corpus = " ".join(keywords + [value for slide in plan.get("slides") or [] for value in source_texts(slide)] + [str(row.get("alt") or "") for row in manifest.get("images") or []])
    failures = []
    if len(keywords) < 2:
        failures.append("visual_semantics 至少需要 2 个项目主题关键词")
    if not motifs:
        failures.append("visual_semantics 未登记与项目主题关联的设计母题")
    for motif in motifs:
        source = evidence.get(motif)
        if not source or source not in corpus:
            failures.append(f"设计母题 {motif} 缺少来自正文/主题词/manifest alt 的语义证据")
    return failures, keywords, motifs, evidence


def visual_language_failures(plan, report):
    """Require one MD-derived language contract instead of legacy motif fallbacks."""
    language = plan.get("visual_language") or {}
    failures = []
    if language.get("schema") != "ProjectVisualLanguage" or language.get("version") != "1.0":
        return ["缺少 ProjectVisualLanguage 1.0；不得回退旧元素提取流程"]
    source = language.get("source") or {}
    if source.get("kind") != "image-description-md" or len(source.get("files") or []) < 1:
        failures.append("视觉语言未绑定图片 MD 描述来源")
    required_roles = {"cover", "toc", "section", "content", "closing"}
    if not required_roles.issubset(language.get("word_art") or {}):
        failures.append("艺术字语言未覆盖封面/目录/转场/内容/结尾")
    if not required_roles.issubset(language.get("composition") or {}):
        failures.append("非规则构成语言未覆盖封面/目录/转场/内容/结尾")
    components = language.get("derived_components") or {}
    if not {"background", "container", "flow", "transition"}.issubset(components):
        failures.append("MD 主题元素未衍生到背景/容器/流程/转场")
    expected_hash = hashlib.sha256(json.dumps(language, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    report_language = report.get("visual_language") or {}
    report_hash = hashlib.sha256(json.dumps(report_language, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if expected_hash != report_hash:
        failures.append("渲染报告使用的视觉语言与 IR 不一致")
    return failures


def project_image_failures(slide, audit, report_row, manifest_index, page, page_image):
    """Independently enforce intact, contained source images and derived backgrounds."""
    failures = []
    if slide.get("bg_image"):
        failures.append(f"第 {page} 页把项目原图登记为背景；项目原图只能完整等比展示")
    placements = audit.get("image_placements") or []
    if placements != (report_row.get("image_placements") or []):
        failures.append(f"第 {page} 页项目图片放置清单在 PNG 与渲染报告间不一致")
    expected_ids = slide_image_ids(slide)
    placed_ids = [str(row.get("image_id") or "") for row in placements]
    if Counter(placed_ids) != Counter(expected_ids):
        failures.append(f"第 {page} 页项目图片放置清单未逐一覆盖 IR 图片")
    width, height = page_image.size
    for placement in placements:
        image_id_value = str(placement.get("image_id") or "")
        row = manifest_index.get(image_id_value)
        container = placement.get("container_bbox") or []
        rendered = placement.get("rendered_bbox") or []
        if placement.get("fit") != "contain" or "background" in str(placement.get("purpose") or ""):
            failures.append(f"第 {page} 页项目图片 {image_id_value} 未使用完整等比 contain 内容展示")
            continue
        if len(container) != 4 or len(rendered) != 4:
            failures.append(f"第 {page} 页项目图片 {image_id_value} 缺少可核验容器/实际边界")
            continue
        cx1, cy1, cx2, cy2 = map(float, container)
        rx1, ry1, rx2, ry2 = map(float, rendered)
        if not (0 <= cx1 < cx2 <= width and 0 <= cy1 < cy2 <= height and cx1 <= rx1 < rx2 <= cx2 and cy1 <= ry1 < ry2 <= cy2):
            failures.append(f"第 {page} 页项目图片 {image_id_value} 边界越界或疑似裁切")
            continue
        if ((cx2-cx1) * (cy2-cy1)) / max(1, width * height) > .72:
            failures.append(f"第 {page} 页项目图片 {image_id_value} 占据页面主体背景区域")
        if row:
            source_path = Path(str(row.get("_path") or ""))
            try:
                with Image.open(source_path) as source:
                    # This is intentionally QA-owned and mirrors a documented
                    # file-format contract, not renderer output: normalize EXIF
                    # orientation, convert to RGB, then LANCZOS-contain the full
                    # manifest original into the declared rendered rectangle.
                    source = ImageOps.exif_transpose(source).convert("RGB")
                    source_ratio = source.width / source.height
                    target_size = (int(round(rx2-rx1)), int(round(ry2-ry1)))
                    expected = ImageOps.contain(source, target_size, Image.Resampling.LANCZOS)
                rendered_ratio = (rx2-rx1) / (ry2-ry1)
                if abs(rendered_ratio / source_ratio - 1) > .015:
                    failures.append(f"第 {page} 页项目图片 {image_id_value} 实际边界比例与原图不一致（疑似变形）")
                actual = page_image.convert("RGB").crop((int(round(rx1)), int(round(ry1)), int(round(rx2)), int(round(ry2))))
                if actual.size != expected.size:
                    failures.append(f"第 {page} 页项目图片 {image_id_value} 实际裁片尺寸与完整 contain 基准不一致")
                else:
                    difference = ImageChops.difference(actual, expected)
                    if difference.getbbox() is not None:
                        mean_delta = sum(ImageStat.Stat(difference).mean) / 3
                        failures.append(
                            f"第 {page} 页项目图片 {image_id_value} 实际裁片与 manifest 原图完整 contain 像素基准不一致"
                            f"（平均色差 {mean_delta:.2f}）"
                        )
            except Exception:
                failures.append(f"第 {page} 页无法读取项目图片 {image_id_value} 以核验完整比例")
    components = audit.get("derived_components") or []
    if components != (report_row.get("derived_components") or []):
        failures.append(f"第 {page} 页衍生设计组件清单在 PNG 与渲染报告间不一致")
    component_types = {str(row.get("type") or "") for row in components}
    required_background = {"theme-background", "orbital-field"}
    if effective_role(slide) not in {"toc", "gallery"}:
        required_background.add("launch-corridor")
    if not required_background.issubset(component_types):
        failures.append(f"第 {page} 页缺少贯穿背景的项目母题衍生组件")
    if effective_role(slide) in {"timeline", "toc"} and "theme-flow" not in component_types:
        failures.append(f"第 {page} 页时间轴未从项目母题衍生")
    if effective_role(slide) == "section" and "theme-transition" not in component_types:
        failures.append(f"第 {page} 页转场未从项目母题衍生")
    if effective_role(slide) in {"toc", "compare", "timeline", "kpi", "image-hero", "two-column", "bullets", "image-side"} and "theme-container" not in component_types:
        failures.append(f"第 {page} 页文本框/内容容器未从项目母题衍生")
    if "word-art" not in component_types:
        failures.append(f"第 {page} 页未应用项目主题艺术字")
    return failures


def audit_design_failures(audit, page, keywords, motifs, evidence):
    failures = []
    boxes = audit.get("text_boxes")
    if not isinstance(boxes, list) or not boxes:
        failures.append(f"第 {page} 页缺少紧致文本框审计")
    else:
        for box in boxes:
            width, height = float(box.get("width") or 0), float(box.get("height") or 0)
            fill = float(box.get("ink_fill_ratio") or 0)
            if width <= 0 or height <= 0 or fill < 0.45:
                failures.append(f"第 {page} 页文本框与文字量不协调（过度留白）")
                break
    if audit.get("semantic_keywords") != keywords or audit.get("approved_motifs") != motifs or audit.get("semantic_evidence") != evidence:
        failures.append(f"第 {page} 页主题语义审计与 IR 不一致")
    used = audit.get("used_motifs") or []
    if not used:
        failures.append(f"第 {page} 页未使用项目主题设计母题")
    elif any(value not in motifs for value in used):
        failures.append(f"第 {page} 页使用了未经项目语义批准的装饰元素")
    return failures


def main():
    args = parse_args()
    if DEPENDENCY_ERROR:
        raise SystemExit("图片 PDF QA 需要 Pillow 与 pypdf：python3 -m pip install Pillow pypdf") from DEPENDENCY_ERROR
    plan, manifest, report = load(args.ir), load(args.manifest), load(args.render_report)
    slides = plan.get("slides") or []
    manifest_rows = manifest.get("images") or []
    manifest_ids = [image_id(row) for row in manifest_rows]
    failures = []
    semantic_failures, semantic_keywords, semantic_motifs, semantic_evidence = semantic_contract_failures(plan, manifest)
    failures.extend(semantic_failures)
    failures.extend(visual_language_failures(plan, report))
    structure_failures = story_structure_failures(slides)
    failures.extend(structure_failures)
    palette_failures = []
    if plan.get("schema") != "SlidesPlan":
        failures.append("IR schema 不是 SlidesPlan")
    duplicates = sorted(key for key, count in Counter(manifest_ids).items() if key and count > 1)
    if duplicates:
        failures.append("manifest 图片 ID 重复：" + ", ".join(duplicates))
    manifest_set = set(manifest_ids)
    manifest_root = Path(args.manifest).resolve().parent
    manifest_index = {}
    for row in manifest_rows:
        path = Path(str(row.get("file") or ""))
        path = path if path.is_absolute() else manifest_root / path
        enriched = dict(row)
        enriched["_path"] = str(path.resolve())
        manifest_index[image_id(row)] = enriched
        if not path.exists():
            failures.append(f"manifest 图片文件不存在：{image_id(row)} -> {path}")
    ir_refs = [value for slide in slides for value in slide_image_ids(slide)]
    unknown = sorted(set(ir_refs) - manifest_set)
    missing = sorted(manifest_set - set(ir_refs))
    if unknown:
        failures.append("IR 引用了 manifest 外图片：" + ", ".join(unknown))
    if missing:
        failures.append("manifest 图片未被 IR 覆盖：" + ", ".join(missing))
    for page, slide in enumerate(slides, start=1):
        role = effective_role(slide)
        if role not in SUPPORTED_ROLES:
            failures.append(f"第 {page} 页不支持 role/pattern：{slide.get('role')}/{slide.get('layout_pattern')}")
        if slide.get("layout_pattern") and slide.get("role") not in {"cover", "toc", "section", "closing", "gallery"}:
            if not slide.get("blueprint"):
                failures.append(f"第 {page} 页登记 layout_pattern 但缺少 blueprint 八字段")
            elif any(not str(slide["blueprint"].get(key) or "").strip() for key in ("focus", "title_pos", "main_area", "aux_area", "whitespace", "svg_need", "image_need", "reason")):
                failures.append(f"第 {page} 页 blueprint 字段不完整")
        failures.extend(text_capacity_failures(slide, page))

    pdf = PdfReader(args.pdf)
    if len(pdf.pages) != len(slides):
        failures.append(f"PDF 页数 {len(pdf.pages)} != IR 页数 {len(slides)}")
    for index, pdf_page in enumerate(pdf.pages, start=1):
        width, height = float(pdf_page.mediabox.width), float(pdf_page.mediabox.height)
        if height <= 0 or abs(width / height - 16 / 9) > 0.01:
            failures.append(f"PDF 第 {index} 页不是 16:9：{width:.2f}×{height:.2f}pt")

    rows = report.get("slides") or []
    if len(rows) != len(slides):
        failures.append(f"渲染报告逐页记录 {len(rows)} != IR 页数 {len(slides)}")
    png_paths, png_hashes = [], []
    ir_hash, manifest_hash = digest(args.ir), digest(args.manifest)
    language_hash = hashlib.sha256(json.dumps(plan.get("visual_language") or {}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    for index, slide in enumerate(slides, start=1):
        if index > len(rows):
            break
        path = Path(str(rows[index - 1].get("png") or "")).resolve()
        png_paths.append(str(path))
        if not path.exists():
            failures.append(f"缺少第 {index} 页 PNG：{path}")
            continue
        png_hashes.append(digest(path))
        with Image.open(path) as image:
            image.load()
            if image.width < args.min_width or image.height < args.min_height or abs(image.width / image.height - 16 / 9) > 0.01:
                failures.append(f"第 {index} 页 PNG 尺寸/比例不合格：{image.size}")
            try:
                audit = json.loads(image.info.get("image_pdf_audit") or "{}")
            except json.JSONDecodeError:
                audit = {}
            if audit.get("page") != index:
                failures.append(f"第 {index} 页 PNG 缺少匹配的内嵌页码审计")
            if audit.get("ir_sha256") != ir_hash or audit.get("manifest_sha256") != manifest_hash:
                failures.append(f"第 {index} 页 PNG 的 IR/manifest 指纹不匹配")
            if audit.get("visual_language_sha256") != language_hash or rows[index - 1].get("visual_language_sha256") != language_hash:
                failures.append(f"第 {index} 页 PNG/报告未绑定同一 MD 视觉语言")
            if audit.get("source_texts") != source_texts(slide):
                failures.append(f"第 {index} 页 PNG 内嵌文本清单与 IR 不一致")
            if audit.get("image_ids") != slide_image_ids(slide):
                failures.append(f"第 {index} 页 PNG 内嵌图片清单与 IR 不一致")
            if audit.get("role") != effective_role(slide):
                failures.append(f"第 {index} 页 PNG 未按蓝图/role 渲染")
            if audit.get("text_overflows"):
                failures.append(f"第 {index} 页渲染发生文字截断/省略")
            actual_rgb_hash = rgb_sha256(image)
            if actual_rgb_hash != audit.get("rendered_rgb_sha256") or actual_rgb_hash != rows[index - 1].get("png_rgb_sha256"):
                failures.append(f"第 {index} 页真实像素与 PNG/报告双侧指纹不一致")
            failures.extend(audit_design_failures(audit, index, semantic_keywords, semantic_motifs, semantic_evidence))
            failures.extend(visible_design_failures(image, audit, rows[index - 1], index, semantic_motifs))
            failures.extend(project_image_failures(slide, audit, rows[index - 1], manifest_index, index, image))
            # Geometry and pixels are checked after the legacy gates so these
            # four user rules remain independent final-QA decisions.
            failures.extend(new_visual_rule_failures(slide, image, audit, rows[index - 1], index))
            failures.extend(gallery_label_failures(slide, image, audit, rows[index - 1], manifest_index, index))
            if index <= len(pdf.pages):
                binding_failure = pdf_page_binding_failure(pdf.pages[index - 1], image, rows[index - 1], index)
                if binding_failure:
                    failures.append(binding_failure)
            if slide.get("role") == "section":
                palette_failure = section_palette_failure(image, index)
                if palette_failure:
                    palette_failures.append(palette_failure)
                    failures.append(palette_failure)
    if len(set(png_paths)) != len(png_paths):
        failures.append("逐页 PNG 路径不唯一（疑似重复指向同一文件）")
    if len(set(png_hashes)) != len(png_hashes):
        failures.append("逐页 PNG 内容不唯一（疑似整套复用同一张图）")

    checks = {
        "pdf_matches_ir": len(pdf.pages) == len(slides) and not any("PDF 第" in value for value in failures),
        "manifest_coverage_recomputed": not unknown and not missing and not duplicates,
        "png_identity_and_provenance": not any("PNG" in value or "指纹" in value for value in failures),
        "text_complete_and_within_capacity": not any("文本" in value or "标题超过" in value or "截断" in value or "图集标签" in value for value in failures),
        "blueprint_and_roles_supported": not any("blueprint" in value or "role/pattern" in value or "蓝图/role" in value for value in failures),
        "toc_sections_complete": not structure_failures,
        "section_palette_consistent": not palette_failures,
        "text_boxes_fit_content": not any("文本框" in value or "紧致文本框" in value or "可见容器" in value or "漏报可见卡片" in value or "文字占用" in value or "真实像素" in value or "像素与逐页 PNG" in value for value in failures),
        "visual_elements_semantically_grounded": not any("主题语义" in value or "设计母题" in value or "装饰元素" in value or "visual_semantics" in value or "元素清单" in value or "可见元素" in value or "真实像素" in value or "像素与逐页 PNG" in value for value in failures),
        "project_images_intact_and_not_backgrounds": not any("项目原图" in value or "项目图片" in value or "衍生设计" in value or "项目母题衍生" in value for value in failures),
        "md_visual_language_applied": not any("视觉语言" in value or "艺术字语言" in value or "非规则构成" in value or "旧元素提取流程" in value for value in failures),
        "icons_and_illustrations_do_not_obscure_text": not any("图标插图遮挡文字" in value for value in failures),
        "busy_narrative_pages_use_restrained_backgrounds": not any("背景未删减" in value for value in failures),
        "word_art_preserves_text_primacy": not any("艺术字" in value and ("重叠" in value or "主体" in value or "几何" in value) for value in failures),
        "body_content_matches_title_claim": not any("标题承诺" in value or "图集可见名称" in value for value in failures),
    }
    qa = {
        "schema": "ImagePdfQA", "version": "2.7", "route": "image-pdf",
        "status": "pass" if not failures else "fail", "pdf": str(Path(args.pdf).resolve()),
        "ir_sha256": ir_hash, "manifest_sha256": manifest_hash, "page_count": len(pdf.pages),
        "manifest_image_count": len(manifest_set), "ir_used_image_count": len(set(ir_refs)),
        "project_image_pixel_policy": {
            "orientation": "EXIF transpose", "color_mode": "RGB",
            "scaling": "Pillow ImageOps.contain / LANCZOS",
            "comparison": "exact RGB pixels within rendered_bbox", "max_mean_abs_delta": 0.0,
        },
        "checks": checks,
    }
    if failures:
        qa["failures"] = failures
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"image-pdf independent QA: {qa['status']} -> {output}")
    for failure in failures:
        print("- " + failure, file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
