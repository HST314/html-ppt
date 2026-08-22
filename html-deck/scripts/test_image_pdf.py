#!/usr/bin/env python3
"""End-to-end positive and adversarial tests for the image-PDF route."""

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, PngImagePlugin
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
RENDER = ROOT / "render_image_pdf.py"
QA = ROOT / "qa_image_pdf.py"
BLUEPRINT = {
    "focus": "中心结论", "title_pos": "顶部", "main_area": "中部主体",
    "aux_area": "底部说明", "whitespace": "30%", "svg_need": "否",
    "image_need": "按页面角色", "reason": "让语义关系可视化",
}
VISUAL_LANGUAGE = {
    "schema": "ProjectVisualLanguage", "version": "1.0",
    "source": {"kind": "image-description-md", "files": ["fixture-image.md"]},
    "keywords": ["卫星", "航天", "徽章"], "motifs": ["badge", "orbit"],
    "evidence": {"badge": "徽章", "orbit": "航天"},
    "palette": {},
    "word_art": {"cover": "ascent", "toc": "orbit", "section": "seal", "content": "cut", "closing": "converge"},
    "composition": {"cover": "launch", "toc": "orbit-map", "section": "gate", "content": "panels", "closing": "trails"},
    "derived_components": {"background": ["orbit"], "container": ["satellite"], "flow": ["orbit"], "transition": ["rocket"]},
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(*args, ok=True):
    result = subprocess.run([sys.executable, *map(str, args)], text=True, capture_output=True)
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    if not ok and result.returncode == 0:
        raise AssertionError("expected failure: " + " ".join(map(str, args)))
    return result


def sync_mutated_page(report, row, image, audit, root, stem):
    """Update every renderer-controlled artifact, as a hostile renderer could."""
    png = root / f"{stem}.png"
    jpg = root / f"{stem}.jpg"
    rgb_hash = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
    audit["rendered_rgb_sha256"] = rgb_hash
    info = PngImagePlugin.PngInfo()
    info.add_text("image_pdf_audit", json.dumps(audit, ensure_ascii=False, sort_keys=True))
    image.save(png, "PNG", optimize=True, pnginfo=info)
    image.save(jpg, "JPEG", quality=94, optimize=True, progressive=True)
    row["png"], row["jpg"] = str(png), str(jpg)
    row["png_rgb_sha256"] = rgb_hash
    row["jpg_sha256"] = hashlib.sha256(jpg.read_bytes()).hexdigest()
    pdf = root / f"{stem}.pdf"
    document = canvas.Canvas(str(pdf), pagesize=(960, 540), pageCompression=1)
    for current in report["slides"]:
        document.drawImage(current["jpg"], 0, 0, width=960, height=540, preserveAspectRatio=False)
        document.showPage()
    document.save()
    return pdf


def slide(page, role, title, pattern=None, variant=None, images=None, blocks=None, section="复验矩阵"):
    value = {
        "page": page, "role": role, "title": title, "section": section,
        "blocks": blocks if blocks is not None else [{"type": "list", "items": ["结论一", "证据二", "行动三"]}],
        "images": images or [], "takeaway": "", "notes": "测试",
    }
    if pattern:
        value.update({"layout_pattern": pattern, "layout_variant": variant, "blueprint": dict(BLUEPRINT)})
    return value


def fixture(root):
    image_dir = root / "images"
    image_dir.mkdir()
    manifest_rows = []
    for index, color in enumerate(((180, 70, 60), (35, 115, 145)), start=1):
        path = image_dir / f"img-{index}.png"
        canvas = Image.new("RGB", (1200, 800), color)
        ImageDraw.Draw(canvas).text((80, 80), f"ASSET {index}", fill="white")
        canvas.save(path)
        manifest_rows.append({"id": f"img-{index}", "file": path.name, "alt": f"素材 {index}"})
    manifest = image_dir / "manifest.json"
    write_json(manifest, {"version": "1.0", "images": manifest_rows})
    toc = slide(2, "toc", "四个判断节点", blocks=[], section=None)
    toc["toc_cards"] = [{"num": f"0{i}", "title": title, "desc": "完整章节"} for i, title in enumerate(("定位", "结构", "证据", "落地"), 1)]
    slides = [slide(1, "cover", "图片路线独立复验", section=None), toc]
    chapter_pages = [
        ("定位", slide(4, "two-column", "中心结论向四项证据展开", "center-hub", "hub-left", blocks=[{"type": "list", "items": ["结论一", "证据二", "证据三", "行动四"]}], section="定位")),
        ("结构", slide(6, "two-column", "三项能力形成交付闭环", "tri-loop", "loop-3", section="结构")),
        ("证据", slide(8, "image-side", "左文右图保留完整证据", "text-image", "anchor-right", images=[{"id": "img-1"}], section="证据")),
        ("落地", slide(10, "image-hero", "英雄主图承载核心视觉", "product-hero", None, images=[{"id": "img-2"}], section="落地")),
    ]
    for index, (title, content) in enumerate(chapter_pages, start=1):
        transition = slide(content["page"] - 1, "section", title, blocks=[], section=title)
        transition["section_index"] = index
        slides.extend((transition, content))
    slides.insert(4, slide(5, "compare", "两类方案真实对照", "compare", "balanced", blocks=[{"type": "list", "items": ["旧方案留白过大", "新方案内容紧致", "旧元素无关", "新元素有据"]}], section="定位"))
    structure_end = next(index for index, value in enumerate(slides) if value.get("role") == "section" and value.get("section") == "证据")
    slides.insert(structure_end, slide(7, "timeline", "三步形成可复跑路径", "timeline", "steps", blocks=[{"type": "list", "items": ["输入", "渲染", "复验"]}], section="结构"))
    landing_end = len(slides)
    slides.insert(landing_end, slide(11, "kpi", "三项数字绑定交付", "big-number", "cards", blocks=[{"type": "list", "items": ["2 张素材", "14 页演示", "100% 覆盖"]}], section="落地"))
    slides.append(slide(11, "closing", "整改证据链已经闭环", blocks=[], section=None))
    plan = root / "outline.json"
    write_json(plan, {"schema": "SlidesPlan", "version": "3.0", "theme_recommendation": "tech-dark", "visual_language": VISUAL_LANGUAGE, "visual_semantics": {"keywords": ["卫星", "航天", "徽章"], "motifs": ["badge", "orbit"], "evidence": {"badge": "徽章", "orbit": "航天"}}, "slides": slides})
    return plan, manifest


def main():
    with tempfile.TemporaryDirectory(prefix="image-pdf-test-") as tmp:
        root = Path(tmp)
        plan, manifest = fixture(root)
        pdf, report, qa = root / "deck.pdf", root / "render.json", root / "qa.json"
        run(RENDER, "--ir", plan, "--manifest", manifest, "--output", pdf, "--slides-dir", root / "slides", "--report", report, "--strict-images")
        run(QA, "--pdf", pdf, "--ir", plan, "--manifest", manifest, "--render-report", report, "--output", qa)
        assert json.loads(qa.read_text(encoding="utf-8"))["status"] == "pass"

        missing_section_plan = json.loads(plan.read_text(encoding="utf-8"))
        missing_section_plan["slides"] = [row for row in missing_section_plan["slides"] if row.get("section") != "结构"]
        missing_section_path = root / "missing-section-outline.json"
        write_json(missing_section_path, missing_section_plan)
        run(RENDER, "--ir", missing_section_path, "--manifest", manifest, "--output", root / "missing-section.pdf", "--slides-dir", root / "missing-section-slides", "--report", root / "missing-section-render.json", "--strict-images")
        missing_section_qa = root / "missing-section-qa.json"
        run(QA, "--pdf", root / "missing-section.pdf", "--ir", missing_section_path, "--manifest", manifest, "--render-report", root / "missing-section-render.json", "--output", missing_section_qa, ok=False)
        assert "目录节点与章节转场未按顺序一一对应" in "\n".join(json.loads(missing_section_qa.read_text(encoding="utf-8"))["failures"])

        red_report = json.loads(report.read_text(encoding="utf-8"))
        section_row = next(row for row in red_report["slides"] if row["source_role"] == "section")
        red_path = root / "red-section.png"
        with Image.open(section_row["png"]) as original:
            audit = original.info.get("image_pdf_audit")
        red_image = Image.new("RGB", (1600, 900), (196, 55, 50))
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("image_pdf_audit", audit)
        red_image.save(red_path, pnginfo=pnginfo)
        section_row["png"] = str(red_path)
        red_report_path = root / "red-section-render.json"
        write_json(red_report_path, red_report)
        red_qa = root / "red-section-qa.json"
        run(QA, "--pdf", pdf, "--ir", plan, "--manifest", manifest, "--render-report", red_report_path, "--output", red_qa, ok=False)
        assert "蓝白视觉体系" in "\n".join(json.loads(red_qa.read_text(encoding="utf-8"))["failures"])

        forged = json.loads(report.read_text(encoding="utf-8"))
        first_png = forged["slides"][0]["png"]
        for row in forged["slides"]:
            row["png"] = first_png
        forged_path = root / "forged-report.json"
        write_json(forged_path, forged)
        forged_qa = root / "forged-qa.json"
        run(QA, "--pdf", pdf, "--ir", plan, "--manifest", manifest, "--render-report", forged_path, "--output", forged_qa, ok=False)
        assert "逐页 PNG 路径不唯一" in "\n".join(json.loads(forged_qa.read_text(encoding="utf-8"))["failures"])

        overflow_plan = json.loads(plan.read_text(encoding="utf-8"))
        overflow_plan["slides"][2]["title"] = "这是一个故意制造的超长标题" * 12
        overflow_path = root / "overflow-outline.json"
        write_json(overflow_path, overflow_plan)
        run(RENDER, "--ir", overflow_path, "--manifest", manifest, "--output", root / "overflow.pdf", "--slides-dir", root / "overflow-slides", "--report", root / "overflow-render.json", "--strict-images", ok=False)

        missing_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        missing_manifest["images"].append({"id": "img-unused", "file": "img-1.png", "alt": "故意未引用"})
        missing_path = root / "images" / "missing-manifest.json"
        write_json(missing_path, missing_manifest)
        missing_qa = root / "missing-qa.json"
        run(QA, "--pdf", pdf, "--ir", plan, "--manifest", missing_path, "--render-report", report, "--output", missing_qa, ok=False)
        assert "manifest 图片未被 IR 覆盖" in "\n".join(json.loads(missing_qa.read_text(encoding="utf-8"))["failures"])

        loose_report = json.loads(report.read_text(encoding="utf-8"))
        loose_row = next(row for row in loose_report["slides"] if row["role"] == "kpi")
        with Image.open(loose_row["png"]) as original:
            loose_audit = json.loads(original.info["image_pdf_audit"])
            loose_pixels = original.convert("RGB")
        # Hostile-renderer case: add a real KPI-sized empty card but omit it
        # from visible_containers, then synchronize PNG/report/JPEG/PDF/hashes.
        loose_draw = ImageDraw.Draw(loose_pixels)
        loose_draw.rounded_rectangle((390, 690, 1210, 840), radius=24, fill="#D9ECF2", outline="#28C2D1", width=3)
        loose_pdf = sync_mutated_page(loose_report, loose_row, loose_pixels, loose_audit, root, "unreported-kpi-empty-card")
        loose_report_path = root / "loose-text-render.json"
        write_json(loose_report_path, loose_report)
        loose_qa = root / "loose-text-qa.json"
        run(QA, "--pdf", loose_pdf, "--ir", plan, "--manifest", manifest, "--render-report", loose_report_path, "--output", loose_qa, ok=False)
        loose_result = json.loads(loose_qa.read_text(encoding="utf-8"))
        assert loose_result["checks"]["text_boxes_fit_content"] is False
        assert "像素发现漏报可见卡片" in "\n".join(loose_result["failures"])

        unrelated_report = json.loads(report.read_text(encoding="utf-8"))
        unrelated_row = unrelated_report["slides"][0]
        with Image.open(unrelated_row["png"]) as original:
            unrelated_audit = json.loads(original.info["image_pdf_audit"])
            unrelated_pixels = original.convert("RGB")
        # Hostile-renderer case: paint a leaf but continue to claim badge, then
        # consistently update its crop hash, PNG/report/JPEG/PDF.
        leaf_box = unrelated_row["visual_elements"][0]["bbox"]
        lx1, ly1, lx2, ly2 = leaf_box
        leaf_draw = ImageDraw.Draw(unrelated_pixels)
        leaf_draw.rectangle(tuple(leaf_box), fill=unrelated_pixels.getpixel((lx1, ly1)))
        leaf_draw.ellipse((lx1 + 8, ly1 + 8, lx2 - 12, ly2 - 10), fill="#36A852", outline="#0E6F32", width=7)
        leaf_draw.line((lx1 + 22, ly2 - 18, lx2 - 18, ly1 + 18), fill="#F3F7D3", width=6)
        crop_hash = hashlib.sha256(unrelated_pixels.crop(tuple(leaf_box)).tobytes()).hexdigest()
        unrelated_audit["visual_elements"][0]["pixel_sha256"] = crop_hash
        unrelated_row["visual_elements"][0]["pixel_sha256"] = crop_hash
        unrelated_pdf = sync_mutated_page(unrelated_report, unrelated_row, unrelated_pixels, unrelated_audit, root, "leaf-disguised-as-badge")
        unrelated_report_path = root / "unrelated-render.json"
        write_json(unrelated_report_path, unrelated_report)
        unrelated_qa = root / "unrelated-qa.json"
        run(QA, "--pdf", unrelated_pdf, "--ir", plan, "--manifest", manifest, "--render-report", unrelated_report_path, "--output", unrelated_qa, ok=False)
        unrelated_result = json.loads(unrelated_qa.read_text(encoding="utf-8"))
        assert unrelated_result["checks"]["visual_elements_semantically_grounded"] is False
        assert "QA 独立 badge 允许特征不匹配" in "\n".join(unrelated_result["failures"])

        # New final-QA rule 1: move a real semantic icon onto a real text box,
        # then synchronize renderer-controlled artifacts. Project images are
        # deliberately not part of this decorative-overlap rule.
        overlap_report = json.loads(report.read_text(encoding="utf-8"))
        overlap_row = overlap_report["slides"][0]
        with Image.open(overlap_row["png"]) as original:
            overlap_audit = json.loads(original.info["image_pdf_audit"])
            overlap_pixels = original.convert("RGB")
        source_box = overlap_audit["visual_elements"][0]["bbox"]
        target_text = overlap_audit["text_boxes"][0]
        target_box = [int(target_text["x"]), int(target_text["y"]), int(target_text["x"] + source_box[2] - source_box[0]), int(target_text["y"] + source_box[3] - source_box[1])]
        icon = overlap_pixels.crop(tuple(source_box))
        overlap_pixels.paste(icon, (target_box[0], target_box[1]))
        icon_hash = hashlib.sha256(overlap_pixels.crop(tuple(target_box)).tobytes()).hexdigest()
        overlap_audit["visual_elements"][0].update({"bbox": target_box, "pixel_sha256": icon_hash})
        overlap_row["visual_elements"][0].update({"bbox": target_box, "pixel_sha256": icon_hash})
        overlap_pdf = sync_mutated_page(overlap_report, overlap_row, overlap_pixels, overlap_audit, root, "icon-over-text")
        overlap_report_path, overlap_qa = root / "icon-over-text-render.json", root / "icon-over-text-qa.json"
        write_json(overlap_report_path, overlap_report)
        run(QA, "--pdf", overlap_pdf, "--ir", plan, "--manifest", manifest, "--render-report", overlap_report_path, "--output", overlap_qa, ok=False)
        overlap_result = json.loads(overlap_qa.read_text(encoding="utf-8"))
        assert overlap_result["checks"]["icons_and_illustrations_do_not_obscure_text"] is False

        # New rule 2: synchronize a genuinely busy line field behind a TOC.
        busy_report = json.loads(report.read_text(encoding="utf-8"))
        busy_row = next(row for row in busy_report["slides"] if row["role"] == "toc")
        with Image.open(busy_row["png"]) as original:
            busy_audit = json.loads(original.info["image_pdf_audit"])
            busy_pixels = original.convert("RGB")
        busy_draw = ImageDraw.Draw(busy_pixels)
        for offset in range(-900, 1600, 18):
            busy_draw.line((offset, 0, offset + 900, 900), fill="#6C93A2", width=3)
        busy_pdf = sync_mutated_page(busy_report, busy_row, busy_pixels, busy_audit, root, "busy-toc-background")
        busy_report_path, busy_qa = root / "busy-toc-render.json", root / "busy-toc-qa.json"
        write_json(busy_report_path, busy_report)
        run(QA, "--pdf", busy_pdf, "--ir", plan, "--manifest", manifest, "--render-report", busy_report_path, "--output", busy_qa, ok=False)
        busy_result = json.loads(busy_qa.read_text(encoding="utf-8"))
        assert busy_result["checks"]["busy_narrative_pages_use_restrained_backgrounds"] is False

        # New rule 3: a real display-rule is drawn through the word face and
        # declared consistently; geometry still rejects the lost text primacy.
        art_report = json.loads(report.read_text(encoding="utf-8"))
        art_row = next(row for row in art_report["slides"] if row["source_role"] == "section")
        with Image.open(art_row["png"]) as original:
            art_audit = json.loads(original.info["image_pdf_audit"])
            art_pixels = original.convert("RGB")
        text_box = art_audit["word_art"][0]["text_bbox"]
        crossing = [text_box[0], (text_box[1] + text_box[3]) // 2 - 3, text_box[2], (text_box[1] + text_box[3]) // 2 + 3]
        ImageDraw.Draw(art_pixels).rectangle(tuple(crossing), fill="#FFC857")
        art_audit["word_art"][0]["ornament_bboxes"].append(crossing)
        art_row["word_art"][0]["ornament_bboxes"].append(crossing)
        art_pdf = sync_mutated_page(art_report, art_row, art_pixels, art_audit, root, "word-art-crossing")
        art_report_path, art_qa = root / "word-art-crossing-render.json", root / "word-art-crossing-qa.json"
        write_json(art_report_path, art_report)
        run(QA, "--pdf", art_pdf, "--ir", plan, "--manifest", manifest, "--render-report", art_report_path, "--output", art_qa, ok=False)
        art_result = json.loads(art_qa.read_text(encoding="utf-8"))
        assert art_result["checks"]["word_art_preserves_text_primacy"] is False

        # New rule 4: render a title that promises four steps while retaining
        # only three real timeline nodes; the mismatch must be independently visible.
        mismatch_plan = json.loads(plan.read_text(encoding="utf-8"))
        mismatch_timeline = next(row for row in mismatch_plan["slides"] if row.get("role") == "timeline")
        mismatch_timeline["title"] = "四步形成可复跑路径"
        mismatch_path = root / "title-body-mismatch.json"
        write_json(mismatch_path, mismatch_plan)
        mismatch_pdf, mismatch_report, mismatch_qa = root / "title-body-mismatch.pdf", root / "title-body-mismatch-render.json", root / "title-body-mismatch-qa.json"
        run(RENDER, "--ir", mismatch_path, "--manifest", manifest, "--output", mismatch_pdf, "--slides-dir", root / "title-body-mismatch-slides", "--report", mismatch_report, "--strict-images")
        run(QA, "--pdf", mismatch_pdf, "--ir", mismatch_path, "--manifest", manifest, "--render-report", mismatch_report, "--output", mismatch_qa, ok=False)
        mismatch_result = json.loads(mismatch_qa.read_text(encoding="utf-8"))
        assert mismatch_result["checks"]["body_content_matches_title_claim"] is False

        # A clean regeneration must still fail when a project original enters
        # through bg_image: originals are content evidence, never backgrounds.
        background_plan = json.loads(plan.read_text(encoding="utf-8"))
        image_slide = next(row for row in background_plan["slides"] if row.get("images"))
        image_slide["bg_image"] = image_slide["images"].pop(0)
        background_path = root / "project-image-as-background.json"
        write_json(background_path, background_plan)
        background_pdf = root / "project-image-as-background.pdf"
        background_report = root / "project-image-as-background-render.json"
        run(RENDER, "--ir", background_path, "--manifest", manifest, "--output", background_pdf,
            "--slides-dir", root / "project-image-as-background-slides", "--report", background_report, "--strict-images")
        background_qa = root / "project-image-as-background-qa.json"
        run(QA, "--pdf", background_pdf, "--ir", background_path, "--manifest", manifest,
            "--render-report", background_report, "--output", background_qa, ok=False)
        background_result = json.loads(background_qa.read_text(encoding="utf-8"))
        assert background_result["checks"]["project_images_intact_and_not_backgrounds"] is False
        assert "项目原图登记为背景" in "\n".join(background_result["failures"])

        # Remove 10% from every edge while preserving the source aspect ratio,
        # resize the damaged center crop back into the unchanged rendered_bbox,
        # then synchronize PNG audit/report/JPEG/PDF and every hash. Geometry is
        # still a perfect contain claim; only a source-derived pixel baseline can
        # detect that the original edge content was lost.
        cropped_report = json.loads(report.read_text(encoding="utf-8"))
        cropped_row = next(row for row in cropped_report["slides"] if row.get("image_placements"))
        with Image.open(cropped_row["png"]) as original:
            cropped_audit = json.loads(original.info["image_pdf_audit"])
            cropped_pixels = original.convert("RGB")
        placement = cropped_audit["image_placements"][0]
        box = placement["rendered_bbox"]
        source_id = placement["image_id"]
        source_file = next(row["file"] for row in json.loads(manifest.read_text(encoding="utf-8"))["images"] if row["id"] == source_id)
        with Image.open(manifest.parent / source_file) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            inset_x, inset_y = source.width // 10, source.height // 10
            damaged_source = source.crop((inset_x, inset_y, source.width - inset_x, source.height - inset_y))
            damaged = damaged_source.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
        cropped_pixels.paste(damaged, (box[0], box[1]))
        cropped_pdf = sync_mutated_page(cropped_report, cropped_row, cropped_pixels, cropped_audit, root, "same-ratio-center-cropped-project-image")
        cropped_report_path = root / "cropped-project-image-render.json"
        write_json(cropped_report_path, cropped_report)
        cropped_qa = root / "cropped-project-image-qa.json"
        run(QA, "--pdf", cropped_pdf, "--ir", plan, "--manifest", manifest,
            "--render-report", cropped_report_path, "--output", cropped_qa, ok=False)
        cropped_result = json.loads(cropped_qa.read_text(encoding="utf-8"))
        assert cropped_result["checks"]["project_images_intact_and_not_backgrounds"] is False
        assert "完整 contain 像素基准不一致" in "\n".join(cropped_result["failures"])

        unsupported_plan = json.loads(plan.read_text(encoding="utf-8"))
        unsupported_plan["visual_semantics"] = {"keywords": ["卫星", "航天"], "motifs": ["leaf"], "evidence": {"leaf": "叶片"}}
        unsupported_path = root / "unsupported-semantics.json"
        write_json(unsupported_path, unsupported_plan)
        run(RENDER, "--ir", unsupported_path, "--manifest", manifest, "--output", root / "unsupported.pdf", "--slides-dir", root / "unsupported-slides", "--report", root / "unsupported-render.json", "--strict-images")
        unsupported_qa = root / "unsupported-qa.json"
        run(QA, "--pdf", root / "unsupported.pdf", "--ir", unsupported_path, "--manifest", manifest, "--render-report", root / "unsupported-render.json", "--output", unsupported_qa, ok=False)
        assert "缺少来自正文" in "\n".join(json.loads(unsupported_qa.read_text(encoding="utf-8"))["failures"])
    print("image-pdf tests: fifteen checks + eight adversarial cases + regressions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
