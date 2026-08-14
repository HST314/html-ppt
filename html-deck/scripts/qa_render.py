#!/usr/bin/env python3
import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path
from common import read_json, parse_page_semantics, is_deck_content_slide


def parse_args():
    p = argparse.ArgumentParser(description="Run visual QA with Playwright when available, otherwise structural fallback.")
    p.add_argument("--html", required=True)
    p.add_argument("--ir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--history", required=True)
    p.add_argument("--screenshots", required=False)
    p.add_argument("--manifest", required=False, help="传入后执行图片覆盖审计，漏图直接判失败")
    p.add_argument("--art-dna", required=False, help="全 Deck 项目视觉 DNA 报告")
    p.add_argument("--semantics", required=False, help="TASK-003: 页面语义登记 state/page_semantics.md；缺省取 --history 同目录下的 page_semantics.md")
    p.add_argument("--round", type=int, default=1)
    return p.parse_args()


def html_sections_by_page(text):
    """TASK-003: 按 data-page 切出每页 HTML 片段，用于分组渲染核验。"""
    sections = {}
    for m in re.finditer(r'<section class="slide[^"]*"[^>]*?data-page="(\d+)"[\s\S]*?(?=<section class="slide|$)', text):
        sections[int(m.group(1))] = m.group(0)
    return sections


def structural(text, ir, art_dna=None, semantics=None):
    rows = []
    slide_count = text.count('<section class="slide')
    external = bool(re.search(r'https?://', text))
    abs_path = bool(re.search(r'/(home|Users|tmp)/[^"\\s<]+', text))
    # 必查动画按 deck 实际用到的 role 动态确定，避免无 kpi 页的 deck 被 count-up 误伤
    ir_slides = ir.get("slides", [])
    deck_issues = []
    # TASK-003: deck 正文页序号（与 page_semantics.md 页码对应）与每页 HTML 片段
    deck_ordinals = {}
    ordinal = 0
    for s in ir_slides:
        if is_deck_content_slide(s):
            ordinal += 1
            deck_ordinals[s.get("page")] = ordinal
    html_sections = html_sections_by_page(text)
    # TASK-003: build_ir/render 自动改 role 的标记，此类页不参与 role 一致性判定
    auto_transform_markers = ("moved to pre-closing", "overflow image", "unrelated images split", "auto-split")
    if art_dna:
        required = ["cover_background", "content_background", "section_background", "closing_background"]
        missing = [k for k in required if not art_dna.get(k)]
        if missing:
            deck_issues.append("项目视觉系统缺少角色背景：" + ",".join(missing))
        if text.count('class="project-art-bg') < len(ir_slides):
            deck_issues.append("项目视觉 DNA 未覆盖全部页面")
    if len(ir_slides) < 2 or ir_slides[1].get("role") != "toc":
        deck_issues.append("第 2 页缺少目录")
    if not ir_slides or ir_slides[-1].get("role") != "closing":
        deck_issues.append("最后一页不是 closing")
    else:
        closing = ir_slides[-1]
        closing_blocks = closing.get("blocks", [])
        if len(closing_blocks) > 1 or closing.get("takeaway") or any(b.get("type") in {"list", "table", "code"} for b in closing_blocks) or len(closing.get("images", [])) > 1:
            deck_issues.append("结束页负载过高：只允许一个短句和一个 CTA")
    if len(ir_slides) < 2 or ir_slides[-2].get("role") in {"cover", "toc", "section", "closing"}:
        deck_issues.append("结束页之前缺少独立行动/决策页")
    required_anims = ["fade-up", "stagger-list", "rise-in"]
    if any(s.get("role") == "kpi" for s in ir_slides):
        required_anims.append("count-up")
    if any(s.get("images") for s in ir_slides):
        if not re.search(r'class="[^"]*project-image-container', text):
            deck_issues.append("项目图片缺少独立容器")
        if re.search(r'<(?:figure|img)[^>]+data-animate="kenburns"', text):
            deck_issues.append("项目图片使用持续缩放动画")
        if re.search(r'class="[^"]*project-image-container[^"]*"[^>]*style="[^"]*--fit:cover', text):
            deck_issues.append("项目图片默认使用 cover，存在内容裁切风险")
        if re.search(r'role-image-hero[\s\S]{0,1200}hero-image::after', text):
            deck_issues.append("项目图片与文字或背景发生融合")
    for slide in ir_slides:
        issues = []
        score = 100
        role = slide.get("role")
        title = slide.get("title", "")
        if role not in {"cover", "section", "closing"}:
            compact = re.sub(r"\s+", "", title)
            if len(compact) < 12 or not re.search(r"\d|提升|下降|完成|验证|锁定|进入|减少|扩大|转化|发布|交付|超过|低于|形成|支撑", title):
                issues.append("标题不是观点式 action title")
                score -= 8
            if not slide.get("takeaway"):
                issues.append("缺少 takeaway")
                score -= 10
            content_blocks = sum(1 for b in slide.get("blocks", []) if b.get("type") in {"paragraph", "list", "table", "quote", "code"})
            if slide.get("takeaway"):
                content_blocks += 1
            if role in {"kpi", "gallery", "image-hero", "image-side", "compare", "table", "two-column"} or slide.get("images"):
                content_blocks += 1
            if content_blocks < 3:
                issues.append("信息密度低于 3 个内容块")
                score -= 12
        if len(title) > 42:
            issues.append("标题超过 42 字")
            score -= 6
        note_len = len(str(slide.get("notes", "")))
        if note_len < 120:
            issues.append("演讲备注低于 120 字")
            score -= 8
        for b in slide.get("blocks", []):
            if b.get("type") == "list":
                if len(b.get("items", [])) > 8:
                    issues.append("列表超过 8 条")
                    score -= 8
                if any(len(x) > 58 for x in b.get("items", [])):
                    issues.append("列表单条超过 58 字")
                    score -= 6
            if b.get("type") == "table":
                real_rows = [r for r in b.get("rows", []) if not all(set(c) <= {"-", ":"} for c in r)]
                if len(real_rows) < 5:
                    issues.append("表格少于 4 行数据加表头")
                    score -= 8
                if len(real_rows) > 10:
                    issues.append("表格行数偏多")
                    score -= 6
        for img in slide.get("images", []):
            if img.get("id") and img.get("alt") and "object-fit" not in text:
                issues.append("图片缺少 object-fit 约束")
                score -= 12
            if img.get("content_type") == "screenshot" and "screenshot-frame" not in text:
                issues.append("截图缺少美化框")
                score -= 10
            if img.get("description") and img.get("description") not in text:
                issues.append("图片缺少说明条")
                score -= 8
        for required in required_anims:
            if required not in text:
                issues.append("关键动画缺失：" + required)
                score -= 3
        if external:
            issues.append("HTML 含外链，不满足离线要求")
            score -= 20
        if abs_path:
            issues.append("HTML 可能泄露绝对路径")
            score -= 20
        if slide_count != len(ir.get("slides", [])):
            issues.append("HTML 页数与 IR 不一致")
            score -= 15
        if deck_issues:
            issues.extend(deck_issues)
            score -= 30
        # ── TASK-003: 语义门禁（仅对 deck 正文页生效）────────────────────────
        page_no = slide.get("page")
        if is_deck_content_slide(slide):
            decision = slide.get("decision") or ""
            sem_row = semantics.get(deck_ordinals.get(page_no)) if semantics is not None else None
            if "default content role" in decision:
                issues.append("未经语义判断的默认 bullets（decision=default content role），需回到页面语义分析层")
                score -= 30
            if semantics is None:
                issues.append("缺少语义登记文件 state/page_semantics.md")
                score -= 25
            elif sem_row is None:
                issues.append("缺少语义登记：page_semantics.md 中无此页")
                score -= 25
            else:
                auto_transformed = any(m in decision for m in auto_transform_markers)
                reg_role = sem_row.get("role") or ""
                if reg_role and reg_role != role and not auto_transformed:
                    issues.append(f"IR role 与语义登记不一致（登记 {reg_role} / IR {role}）")
                    score -= 25
                if role == "bullets" and not auto_transformed and "并列" not in (sem_row.get("logic") or ""):
                    issues.append("内容页使用 bullets 但语义登记未写明并列逻辑理由")
                    score -= 25
                reg_groups = sem_row.get("groups") or []
                if reg_groups:
                    sect = html_sections.get(page_no, "")
                    titles_missing = [g["title"] for g in reg_groups
                                      if g.get("title") and g["title"] not in sect and html_lib.escape(g["title"], quote=True) not in sect]
                    if sect.count("group-card") < len(reg_groups) or titles_missing:
                        issues.append("登记分组未渲染为独立视觉区块（缺组卡片或组标题）")
                        score -= 20
                    if not slide.get("groups"):
                        issues.append("语义登记分组未进入 IR（提示）")
                        score -= 6
                else:
                    list_items = sum(len(b.get("items", [])) for b in slide.get("blocks", []) if b.get("type") == "list")
                    if list_items >= 4:
                        issues.append("≥4 条信息未提供语义分组，已走兜底渲染（提示）")
                        score -= 4
        rows.append({"page": page_no, "score": max(0, score), "mode": "structural-fallback", "issues": issues})
    return rows


def try_playwright(args, ir):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"Playwright QA 降级：{exc}", file=sys.stderr)
        return None
    out_dir = Path(args.screenshots or Path(args.output).parent / "screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        with sync_playwright() as p:
            browser = None
            for kwargs in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
                try:
                    browser = p.chromium.launch(**kwargs)
                    break
                except Exception:
                    continue
            if browser is None:
                return None
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            page.goto(Path(args.html).resolve().as_uri())
            page.wait_for_timeout(800)
            # 测量前禁用动画，避免 kenburns 等设计性放大造成溢出误报
            page.add_style_tag(content=".slide * { animation: none !important; transition: none !important; }")
            for i, slide in enumerate(ir.get("slides", []), start=1):
                page.keyboard.press("Home")
                page.wait_for_timeout(350)
                for _ in range(i - 1):
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(60)
                page.wait_for_timeout(900)  # 等过渡动画结束再截图
                overflow = page.evaluate(
                    "(() => { const el = document.querySelector('.slide.is-active');"
                    " if (!el) return false;"
                    " return el.scrollHeight > el.clientHeight + 4"
                    " || el.scrollWidth > el.clientWidth + 4; })()"
                )
                page.add_style_tag(content=".slide * { animation: none !important; }")
                page.screenshot(path=str(out_dir / f"slide-{i:02d}.png"))
                visible = page.locator(".slide.is-active").count() == 1
                score = 100
                issues = []
                if not visible:
                    score -= 25
                    issues.append("当前页可见状态异常")
                if overflow:
                    score -= 20
                    issues.append("页面内容溢出屏幕")
                rows.append({"page": slide.get("page"), "score": score, "mode": "playwright", "issues": issues})
            browser.close()
    except Exception:
        return None
    return rows


def main():
    args = parse_args()
    text = Path(args.html).read_text(encoding="utf-8")
    ir = read_json(args.ir)
    # TASK-005: art_dna 文件缺失时按降级标注而非报错崩溃
    art_dna = read_json(args.art_dna) if args.art_dna and Path(args.art_dna).exists() else None
    # TASK-003: 语义门禁读取 state/page_semantics.md（默认与 --history 同目录）
    sem_path = args.semantics or (Path(args.history).parent / "page_semantics.md")
    semantics = parse_page_semantics(sem_path)
    rows = try_playwright(args, ir)
    if rows is None:
        rows = structural(text, ir, art_dna, semantics)
    else:
        # playwright 模式同样执行内容容量规则，两种检查取并集
        struct_map = {r["page"]: r for r in structural(text, ir, art_dna, semantics)}
        for r in rows:
            s = struct_map.get(r["page"])
            if s:
                r["score"] = max(0, r["score"] - (100 - s["score"]))
                r["issues"] = r["issues"] + [x for x in s["issues"] if x not in r["issues"]]
    hist = Path(args.history)
    hist.parent.mkdir(parents=True, exist_ok=True)
    with hist.open("a", encoding="utf-8") as f:
        for row in rows:
            record = {"round": args.round, **row}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    failed = [r for r in rows if r["score"] < 90]
    avg = sum(r["score"] for r in rows) / max(1, len(rows))
    # TASK-005: art DNA 来源标注，区分 像素提取 / md 解读 / 降级
    if art_dna is None:
        art_dna_label = "fallback（无项目视觉 DNA，基础主题装饰降级）"
    elif art_dna.get("source_mode") == "md":
        art_dna_label = "md（图片 md 解读路径，生成式融合背景）"
    else:
        art_dna_label = "image（图片像素提取路径）"
    report = ["# QA Report", "", f"- mode: {rows[0]['mode'] if rows else 'none'}", f"- art_dna: {art_dna_label}", f"- pages: {len(rows)}", f"- average_score: {avg:.1f}", f"- failed_pages: {len(failed)}", "", "## Page Scores"]
    for row in rows:
        issues = "；".join(row["issues"]) if row["issues"] else "无"
        report.append(f"- P{row['page']}: {row['score']} 分，问题：{issues}")
    # 图片覆盖审计：传入 manifest 时核验每张输入图都出现在 HTML 中，漏图直接判失败
    coverage = None
    if args.manifest:
        from audit_images import audit
        coverage = audit(read_json(args.manifest), text)
        report += ["", "## Image Coverage",
                   f"- total_images: {coverage['total']}",
                   f"- covered: {coverage['covered']}",
                   f"- missing: {len(coverage['missing'])}"]
        for row in coverage["rows"]:
            pages = ", ".join(f"P{p}" for p in row["pages"]) if row["pages"] else "-"
            mark = "OK" if row["status"] == "covered" else "MISSING"
            report.append(f"- [{mark}] {row['id']}: {pages}")
        if coverage["missing"]:
            report.append("- 结论：存在漏图，QA 判失败，请重跑 build_ir 自动拆页/汇入后再渲染。")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(str(out))
    return 1 if failed or (coverage and coverage["missing"]) else 0


if __name__ == "__main__":
    sys.exit(main())
