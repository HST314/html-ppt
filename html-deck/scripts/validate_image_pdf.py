#!/usr/bin/env python3
"""Validate dimensions, ordering, page count, and absence of a PDF text layer."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Pillow is required: python3 -m pip install Pillow") from exc


def run_text_check(pdf: Path) -> tuple[bool, str]:
    exe = shutil.which("pdftotext")
    if not exe:
        return False, "pdftotext unavailable"
    result = subprocess.run([exe, str(pdf), "-"], check=False, capture_output=True, text=True)
    return not result.stdout.strip(), result.stdout.strip()[:200]


def pdf_page_count(pdf: Path) -> tuple[int, str | None]:
    exe = shutil.which("pdfinfo")
    if not exe:
        return 0, "pdfinfo unavailable"
    result = subprocess.run([exe, str(pdf)], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return 0, result.stderr.strip()[:200]
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip()), None
    return 0, "pdfinfo did not report Pages"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    slides = spec.get("slides", [])
    chapters = spec.get("chapters", [])

    pages = sorted(Path(args.pages).glob("*.png"))
    pdf = Path(args.pdf)
    errors = []
    chapter_ids = [chapter.get("id") for chapter in chapters]
    if not 3 <= len(chapters) <= 7:
        errors.append(f"chapters must contain 3–7 items, got {len(chapters)}")
    if len(chapter_ids) != len(set(chapter_ids)):
        errors.append("chapter ids must be unique")
    toc_pages = [slide for slide in slides if slide.get("role") == "toc"]
    if len(toc_pages) != 1:
        errors.append(f"expected exactly one toc slide, got {len(toc_pages)}")
    observed = []
    for chapter in chapters:
        cid = chapter.get("id")
        title = chapter.get("title")
        owned = [(i, slide) for i, slide in enumerate(slides, 1) if slide.get("chapter_id") == cid]
        sections = [(i, slide) for i, slide in owned if slide.get("role") == "section"]
        contents = [(i, slide) for i, slide in owned if slide.get("role") == "content"]
        if len(sections) != 1:
            errors.append(f"chapter {cid}: expected one section slide, got {len(sections)}")
            continue
        if sections[0][1].get("title") != title:
            errors.append(f"chapter {cid}: section title must equal chapter title")
        if not contents:
            errors.append(f"chapter {cid}: requires at least one content slide")
        indices = [i for i, _ in owned]
        if indices and indices != list(range(min(indices), max(indices) + 1)):
            errors.append(f"chapter {cid}: pages must be contiguous")
        if contents and sections[0][0] >= contents[0][0]:
            errors.append(f"chapter {cid}: section must precede content")
        observed.append(cid)
    observed_order = []
    for slide in slides:
        cid = slide.get("chapter_id")
        if cid and (not observed_order or observed_order[-1] != cid):
            observed_order.append(cid)
        if slide.get("role") in {"section", "content"} and cid not in chapter_ids:
            errors.append(f"slide {slide.get('id')}: unknown or missing chapter_id")
    if observed_order != chapter_ids:
        errors.append(f"chapter order mismatch: expected {chapter_ids}, got {observed_order}")
    for index, page in enumerate(pages, 1):
        with Image.open(page) as image:
            if image.size != (args.width, args.height):
                errors.append(f"{page.name}: expected {args.width}x{args.height}, got {image.size}")
        if not page.name.startswith(f"{index:02d}-"):
            errors.append(f"{page.name}: invalid sequence prefix, expected {index:02d}-")
    if not pages:
        errors.append("no PNG pages found")
    if not pdf.exists() or pdf.stat().st_size == 0:
        errors.append("PDF missing or empty")

    pdf_pages, page_error = pdf_page_count(pdf) if pdf.exists() else (0, "PDF missing")
    if page_error:
        errors.append(f"cannot inspect PDF pages: {page_error}")
    if pdf_pages != len(pages):
        errors.append(f"PDF page count {pdf_pages} != PNG count {len(pages)}")

    text_empty, text_sample = run_text_check(pdf) if pdf.exists() else (False, "")
    if shutil.which("pdftotext") and not text_empty:
        errors.append(f"PDF contains a text layer: {text_sample}")

    report = {
        "status": "pass" if not errors else "fail",
        "png_pages": len(pages),
        "pdf_pages": pdf_pages,
        "dimensions": [args.width, args.height],
        "pdf_text_layer_empty": text_empty,
        "chapters": len(chapters),
        "navigation_alignment": not any("chapter" in error or "section" in error or "toc" in error for error in errors),
        "errors": errors,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
