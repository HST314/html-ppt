#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from common import read_json


def parse_args():
    p = argparse.ArgumentParser(description="Run visual QA with Playwright when available, otherwise structural fallback.")
    p.add_argument("--html", required=True)
    p.add_argument("--ir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--history", required=True)
    p.add_argument("--screenshots", required=False)
    p.add_argument("--manifest", required=False, help="传入后执行图片覆盖审计，漏图直接判失败")
    p.add_argument("--round", type=int, default=1)
    return p.parse_args()


def structural(text, ir):
    rows = []
    slide_count = text.count('<section class="slide')
    external = bool(re.search(r'https?://', text))
    abs_path = bool(re.search(r'/(home|Users|tmp)/[^"\\s<]+', text))
    # 必查动画按 deck 实际用到的 role 动态确定，避免无 kpi 页的 deck 被 count-up 误伤
    ir_slides = ir.get("slides", [])
    required_anims = ["fade-up", "stagger-list", "rise-in"]
    if any(s.get("role") == "kpi" for s in ir_slides):
        required_anims.append("count-up")
    if any(s.get("images") for s in ir_slides):
        required_anims.append("kenburns")
    for slide in ir_slides:
        issues = []
        score = 100
        role = slide.get("role")
        title = slide.get("title", "")
        if role not in {"cover", "section"}:
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
        rows.append({"page": slide.get("page"), "score": max(0, score), "mode": "structural-fallback", "issues": issues})
    return rows


def try_playwright(args, ir):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
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
    rows = try_playwright(args, ir)
    if rows is None:
        rows = structural(text, ir)
    else:
        # playwright 模式同样执行内容容量规则，两种检查取并集
        struct_map = {r["page"]: r for r in structural(text, ir)}
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
    report = ["# QA Report", "", f"- mode: {rows[0]['mode'] if rows else 'none'}", f"- pages: {len(rows)}", f"- average_score: {avg:.1f}", f"- failed_pages: {len(failed)}", "", "## Page Scores"]
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
