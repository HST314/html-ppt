#!/usr/bin/env python3
"""End-to-end positive and adversarial tests for the image-PDF route."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
RENDER = ROOT / "render_image_pdf.py"
QA = ROOT / "qa_image_pdf.py"
BLUEPRINT = {
    "focus": "中心结论", "title_pos": "顶部", "main_area": "中部主体",
    "aux_area": "底部说明", "whitespace": "30%", "svg_need": "否",
    "image_need": "按页面角色", "reason": "让语义关系可视化",
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
        ("定位", slide(4, "two-column", "中心结论向四项证据展开", "center-hub", "hub-left", section="定位")),
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
    write_json(plan, {"schema": "SlidesPlan", "version": "2.1", "theme_recommendation": "tech-dark", "visual_semantics": {"keywords": ["卫星", "航天"], "motifs": ["satellite", "orbit"], "evidence": {"satellite": "卫星", "orbit": "航天"}}, "slides": slides})
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
        from PIL import PngImagePlugin
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
        loose_row = next(row for row in loose_report["slides"] if row["role"] == "compare")
        loose_path = root / "loose-text-box.png"
        with Image.open(loose_row["png"]) as original:
            loose_audit = original.info["image_pdf_audit"]
            loose_pixels = original.convert("RGB")
        # A real visual mutation: cover a legitimate content card with a much
        # larger empty card while leaving both audit payloads untouched.
        loose_draw = ImageDraw.Draw(loose_pixels)
        x1, y1, x2, y2 = loose_row["visible_containers"][0]["bbox"]
        loose_draw.rounded_rectangle((x1, y1, x2, min(850, y2 + 330)), radius=24, fill="#D9ECF2", outline="#287E91", width=3)
        from PIL import PngImagePlugin
        loose_info = PngImagePlugin.PngInfo()
        loose_info.add_text("image_pdf_audit", loose_audit)
        loose_pixels.save(loose_path, pnginfo=loose_info)
        loose_row["png"] = str(loose_path)
        loose_report_path = root / "loose-text-render.json"
        write_json(loose_report_path, loose_report)
        loose_qa = root / "loose-text-qa.json"
        run(QA, "--pdf", pdf, "--ir", plan, "--manifest", manifest, "--render-report", loose_report_path, "--output", loose_qa, ok=False)
        loose_result = json.loads(loose_qa.read_text(encoding="utf-8"))
        assert loose_result["checks"]["text_boxes_fit_content"] is False
        assert "文字占用过低" in "\n".join(loose_result["failures"])

        unrelated_report = json.loads(report.read_text(encoding="utf-8"))
        unrelated_row = unrelated_report["slides"][0]
        unrelated_path = root / "unrelated-decoration.png"
        with Image.open(unrelated_row["png"]) as original:
            unrelated_audit = original.info["image_pdf_audit"]
            unrelated_pixels = original.convert("RGB")
        # A real pixel mutation: replace an approved motif crop with an obvious
        # green leaf. The semantic element list and audit remain unchanged.
        leaf_box = unrelated_row["visual_elements"][0]["bbox"]
        lx1, ly1, lx2, ly2 = leaf_box
        leaf_draw = ImageDraw.Draw(unrelated_pixels)
        leaf_draw.ellipse((lx1 + 8, ly1 + 8, lx2 - 12, ly2 - 10), fill="#36A852", outline="#0E6F32", width=7)
        leaf_draw.line((lx1 + 22, ly2 - 18, lx2 - 18, ly1 + 18), fill="#F3F7D3", width=6)
        unrelated_info = PngImagePlugin.PngInfo()
        unrelated_info.add_text("image_pdf_audit", unrelated_audit)
        unrelated_pixels.save(unrelated_path, pnginfo=unrelated_info)
        unrelated_row["png"] = str(unrelated_path)
        unrelated_report_path = root / "unrelated-render.json"
        write_json(unrelated_report_path, unrelated_report)
        unrelated_qa = root / "unrelated-qa.json"
        run(QA, "--pdf", pdf, "--ir", plan, "--manifest", manifest, "--render-report", unrelated_report_path, "--output", unrelated_qa, ok=False)
        unrelated_result = json.loads(unrelated_qa.read_text(encoding="utf-8"))
        assert unrelated_result["checks"]["visual_elements_semantically_grounded"] is False
        assert "可见元素像素与元素清单不一致" in "\n".join(unrelated_result["failures"])

        unsupported_plan = json.loads(plan.read_text(encoding="utf-8"))
        unsupported_plan["visual_semantics"] = {"keywords": ["卫星", "航天"], "motifs": ["leaf"], "evidence": {"leaf": "叶片"}}
        unsupported_path = root / "unsupported-semantics.json"
        write_json(unsupported_path, unsupported_plan)
        run(RENDER, "--ir", unsupported_path, "--manifest", manifest, "--output", root / "unsupported.pdf", "--slides-dir", root / "unsupported-slides", "--report", root / "unsupported-render.json", "--strict-images")
        unsupported_qa = root / "unsupported-qa.json"
        run(QA, "--pdf", root / "unsupported.pdf", "--ir", unsupported_path, "--manifest", manifest, "--render-report", root / "unsupported-render.json", "--output", unsupported_qa, ok=False)
        assert "缺少来自正文" in "\n".join(json.loads(unsupported_qa.read_text(encoding="utf-8"))["failures"])
    print("image-pdf tests: structure + palette + provenance + overflow + coverage + text-fit + semantics passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
