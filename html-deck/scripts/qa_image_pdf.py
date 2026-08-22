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
    from PIL import Image, ImageChops, ImageDraw, ImageStat
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
        if score < 0.24:
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
    for row in manifest_rows:
        path = Path(str(row.get("file") or ""))
        path = path if path.is_absolute() else manifest_root / path
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
        "text_complete_and_within_capacity": not any("文本" in value or "标题超过" in value or "截断" in value for value in failures),
        "blueprint_and_roles_supported": not any("blueprint" in value or "role/pattern" in value or "蓝图/role" in value for value in failures),
        "toc_sections_complete": not structure_failures,
        "section_palette_consistent": not palette_failures,
        "text_boxes_fit_content": not any("文本框" in value or "紧致文本框" in value or "可见容器" in value or "漏报可见卡片" in value or "文字占用" in value or "真实像素" in value or "像素与逐页 PNG" in value for value in failures),
        "visual_elements_semantically_grounded": not any("主题语义" in value or "设计母题" in value or "装饰元素" in value or "visual_semantics" in value or "元素清单" in value or "可见元素" in value or "真实像素" in value or "像素与逐页 PNG" in value for value in failures),
    }
    qa = {
        "schema": "ImagePdfQA", "version": "2.3", "route": "image-pdf",
        "status": "pass" if not failures else "fail", "pdf": str(Path(args.pdf).resolve()),
        "ir_sha256": ir_hash, "manifest_sha256": manifest_hash, "page_count": len(pdf.pages),
        "manifest_image_count": len(manifest_set), "ir_used_image_count": len(set(ir_refs)),
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
