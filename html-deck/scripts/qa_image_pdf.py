#!/usr/bin/env python3
"""Independent image-PDF QA: recompute truth from SlidesPlan, manifest and PNGs."""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

DEPENDENCY_ERROR = None
try:
    from PIL import Image
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


def parse_args():
    parser = argparse.ArgumentParser(description="基于 manifest/IR 独立检查图片型演示，不信任渲染报告汇总字段。")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--ir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--render-report", required=True, help="仅用于定位逐页 PNG；覆盖结论不从报告读取")
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


def main():
    args = parse_args()
    if DEPENDENCY_ERROR:
        raise SystemExit("图片 PDF QA 需要 Pillow 与 pypdf：python3 -m pip install Pillow pypdf") from DEPENDENCY_ERROR
    plan, manifest, report = load(args.ir), load(args.manifest), load(args.render_report)
    slides = plan.get("slides") or []
    manifest_rows = manifest.get("images") or []
    manifest_ids = [image_id(row) for row in manifest_rows]
    failures = []
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
    for index, page in enumerate(pdf.pages, start=1):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
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
    }
    qa = {
        "schema": "ImagePdfQA", "version": "2.0", "route": "image-pdf",
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
