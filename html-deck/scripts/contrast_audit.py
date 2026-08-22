#!/usr/bin/env python3
"""TASK-027: 全篇文字/符号可见性核查工具（独立脚本，不接入主流水线）。

背景：qa_render.py 的 playwright 模式此前只检查"当前页是否可见"与"内容是否
溢出画布"两项，从未真正测量过任何文字与背景的实际对比度——`state/qa_report.md`
连续几轮显示"对比度检测通过"其实是没有这项检测，不是测了之后通过。用户肉眼
发现目录页 01-06 编号与底色几乎重合后，要求补上真正的、覆盖全篇（不止正文
段落，也包括 ss-ghost-num/outline-number/kpi-number/gallery-index/cp-date 等
装饰性但承载语义的编号/符号）的可见性核查。

方法：不依赖静态解析 CSS 声明的颜色值（渐变背景、opacity 叠加、text-stroke
描边这些场景静态解析很容易算错——这正是本轮 ss-ghost-num 双重透明度叠加被
之前几轮漏掉的原因），改为量测"实际渲染出来的像素"：
1. Playwright 逐页截图（device_scale_factor=2，与 CSS px 的映射关系已知）。
2. 对每个"承载文字或编号符号"的 DOM 元素，取其 getBoundingClientRect() 换算
   成截图像素坐标，从截图里裁出对应区域。
3. 裁出的区域转灰度图，用直方图取 5%/50%/95% 分位灰度值——中位数近似背景
   （文字油墨通常占比 <50% 面积），5%/95% 中偏离中位数更远的一侧近似文字前
   景色，再按 WCAG 相对亮度公式换算成对比度。这个"量测渲染像素"的方法天然
   能覆盖渐变底、半透明叠加、text-stroke 描边等静态 CSS 解析容易出错的场景，
   等价于用程序代替肉眼去比对每一处文字与背景的反差。
4. 正文类元素（字号 <32px 且非粗体，或字号 <24px）要求 ≥4.5:1；大标题/大号
   装饰符号（字号 ≥32px，或 ≥24px 且加粗）要求 ≥3:1，未达标直接在报告里点名。

用法：
  python scripts/contrast_audit.py --html dist/deck.html --out state/contrast_audit.md
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image


def parse_args():
    p = argparse.ArgumentParser(description="逐页测量所有可见文字/符号元素的真实渲染对比度")
    p.add_argument("--html", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--shots-dir", required=False, help="截图保存目录，默认 --out 同目录下 contrast_shots/")
    p.add_argument("--pages", type=int, default=24)
    return p.parse_args()


COLLECT_JS = r"""
() => {
  const slide = document.querySelector('.slide.is-active');
  if (!slide) return [];
  const symbolClasses = ['ss-ghost-num','outline-number','kpi-number','gallery-index',
    'li-index','cp-date','date','watermark-word','cp-current-tag','num-big','tag-pill',
    'mc-num','li-mark','deckline'];
  function directText(el) {
    let t = '';
    for (const node of el.childNodes) {
      if (node.nodeType === 3) t += node.textContent;
    }
    return t.replace(/\s+/g, '').trim();
  }
  function cumulativeOpacity(el) {
    let op = 1;
    let node = el;
    while (node) {
      const cs = getComputedStyle(node);
      const o = parseFloat(cs.opacity);
      if (!isNaN(o)) op *= o;
      if (node === slide) break;
      node = node.parentElement;
    }
    return op;
  }
  const all = slide.querySelectorAll('*');
  const results = [];
  all.forEach((el) => {
    if (el.closest('.deck-ui, .notes, .overview, script, style')) return;
    const cls = Array.from(el.classList || []);
    const hasSymbol = cls.some((c) => symbolClasses.includes(c));
    const dt = directText(el);
    if (!hasSymbol && dt.length === 0) return;
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return;
    if (rect.bottom < 0 || rect.right < 0 || rect.left > window.innerWidth || rect.top > window.innerHeight) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    const op = cumulativeOpacity(el);
    if (op < 0.03) return;
    results.push({
      tag: el.tagName.toLowerCase(),
      cls: cls.join('.'),
      text: (dt || el.textContent.trim()).slice(0, 24),
      x: rect.x, y: rect.y, w: rect.width, h: rect.height,
      fontSize: parseFloat(cs.fontSize) || 0,
      fontWeight: parseInt(cs.fontWeight) || 400,
      opacity: op,
    });
  });
  return results;
}
"""


def relative_luminance(gray_0_255):
    c = gray_0_255 / 255.0
    if c <= 0.03928:
        lin = c / 12.92
    else:
        lin = ((c + 0.055) / 1.055) ** 2.4
    return lin


def contrast_ratio(l1, l2):
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def otsu_threshold(hist):
    """标准 Otsu 双峰阈值法：自适应找出让"类间方差"最大的灰度分界点，不像
    固定百分位那样预设"背景一定占多数"——CJK 粗体字形/小色块徽标经常占据
    自身包围盒的一半以上面积，固定百分位在这类场景会把整块都当成同一类，
    算出假的高对比度或假的低对比度（本脚本第一版用百分位法时就在
    li-mark/表格 th/td 上大量出现这类误判，改用 Otsu 后消除）。"""
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_b = 0
    w_b = 0
    max_var = -1.0
    threshold = 0
    for i, h in enumerate(hist):
        w_b += h
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * h
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = i
    return threshold


def _otsu_split(crop_l):
    """对灰度裁图跑 Otsu 分类，两侧都至少占 1.5% 像素才算真的分出了"文字/
    背景"两类；否则整块区域近似纯色（没有可判定的边界），返回 None 而不是
    硬凑一个没有意义的 1:1。
    TASK-027 fix: 每一侧的代表灰度取该侧出现次数最多的单一灰度值（众数/
    峰值），不取算术平均——细描边文字（如巨型幽灵数字的 2px 描边）抗锯齿
    过渡像素的数量远超描边本身的纯色核心像素，取平均会把"文字侧"的代表值
    拉向背景，实测会把肉眼可辨的描边算成比实际观感更低的对比度；取众数能
    定位到每一类真正的"纯色核心"，更贴近人眼实际分辨到的前景色/背景色。"""
    hist = crop_l.histogram()
    total = sum(hist)
    if total == 0:
        return None
    t = otsu_threshold(hist)
    dark_cnt = sum(hist[: t + 1])
    light_cnt = sum(hist[t + 1:])
    if dark_cnt < total * 0.015 or light_cnt < total * 0.015:
        return None
    dark_mode = max(range(0, t + 1), key=lambda i: hist[i])
    light_mode = max(range(t + 1, 256), key=lambda i: hist[i])
    return contrast_ratio(relative_luminance(dark_mode), relative_luminance(light_mode))


def measure_element(img, dpr, el):
    """TASK-027 fix: 两级采样策略。
    优先取元素包围盒本身（不加边距）——大多数"文字+自带底色"的元素（表格
    单元格、gallery-index 实心徽标：自己的 background 已经把文字和底色都
    包在同一个盒子里）只用盒子本身就能分出真正的两类颜色，不该往外扩，
    否则会把盒子外面复杂的照片/纹理背景一起卷进来，反而把测量结果搅乱
    （实测 gallery-index 徽标在照片上加边距后对比度被拉低到不真实的水平）。
    只有当盒子本身是"近似纯色、Otsu 分不出两类"时（典型如 14x14 的纯色
    li-mark 方块、紧贴字形边缘裁切的箭头符号——整个盒子就是同一种颜色，
    没有自带背景像素可比），才退一步，向外扩一圈边距（短边 25%，至少 4px）
    把盒子周围真实的页面背景像素也纳入，再测一次。"""
    x0b = max(0, int(round(el["x"] * dpr)))
    y0b = max(0, int(round(el["y"] * dpr)))
    x1b = min(img.width, int(round((el["x"] + el["w"]) * dpr)))
    y1b = min(img.height, int(round((el["y"] + el["h"]) * dpr)))
    if x1b - x0b >= 3 and y1b - y0b >= 3:
        result = _otsu_split(img.crop((x0b, y0b, x1b, y1b)).convert("L"))
        if result is not None:
            return result
    margin = max(4, int(round(min(el["w"], el["h"]) * 0.25)))
    x0 = max(0, int(round((el["x"] - margin) * dpr)))
    y0 = max(0, int(round((el["y"] - margin) * dpr)))
    x1 = min(img.width, int(round((el["x"] + el["w"] + margin) * dpr)))
    y1 = min(img.height, int(round((el["y"] + el["h"] + margin) * dpr)))
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    return _otsu_split(img.crop((x0, y0, x1, y1)).convert("L"))


def is_large_text(font_size, font_weight):
    return font_size >= 32 or (font_size >= 24 and font_weight >= 700)


def main():
    args = parse_args()
    from playwright.sync_api import sync_playwright

    shots_dir = Path(args.shots_dir or (Path(args.out).parent / "contrast_shots"))
    shots_dir.mkdir(parents=True, exist_ok=True)

    dpr = 2
    all_issues = []
    total_checked = 0
    with sync_playwright() as p:
        browser = None
        for kwargs in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
            try:
                browser = p.chromium.launch(**kwargs)
                break
            except Exception:
                continue
        if browser is None:
            print("无法启动 Chromium/Edge，退出", file=sys.stderr)
            sys.exit(1)
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=dpr)
        page.goto(Path(args.html).resolve().as_uri())
        page.wait_for_timeout(800)
        page.add_style_tag(content=".slide * { animation: none !important; transition: none !important; }")
        for i in range(1, args.pages + 1):
            page.keyboard.press("Home")
            page.wait_for_timeout(300)
            for _ in range(i - 1):
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(50)
            page.wait_for_timeout(700)
            shot_path = shots_dir / f"slide-{i:02d}.png"
            page.screenshot(path=str(shot_path))
            elements = page.evaluate(COLLECT_JS)
            img = Image.open(shot_path)
            page_issues = []
            for el in elements:
                ratio = measure_element(img, dpr, el)
                if ratio is None:
                    continue
                total_checked += 1
                large = is_large_text(el["fontSize"], el["fontWeight"])
                threshold = 3.0 if large else 4.5
                if ratio < threshold:
                    page_issues.append({
                        "tag": el["tag"], "cls": el["cls"], "text": el["text"],
                        "fontSize": round(el["fontSize"], 1), "large": large,
                        "ratio": round(ratio, 2), "threshold": threshold,
                    })
            if page_issues:
                all_issues.append({"page": i, "issues": page_issues})
        browser.close()

    lines = ["# 全篇文字/符号可见性核查（像素级实测对比度）", ""]
    lines.append(f"- 共实测元素：{total_checked}")
    lines.append(f"- 未达标元素：{sum(len(p['issues']) for p in all_issues)}")
    lines.append(f"- 涉及页数：{len(all_issues)}")
    lines.append("")
    if not all_issues:
        lines.append("全部元素对比度达标（正文 ≥4.5:1，大字号/装饰符号 ≥3:1）。")
    else:
        for p in all_issues:
            lines.append(f"## P{p['page']}")
            for it in p["issues"]:
                lines.append(
                    f"- `{it['tag']}.{it['cls']}` \"{it['text']}\" 字号{it['fontSize']}px "
                    f"{'(大字号/符号，阈值3:1)' if it['large'] else '(正文，阈值4.5:1)'} "
                    f"实测对比度 {it['ratio']}:1 < {it['threshold']}:1"
                )
            lines.append("")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"共实测 {total_checked} 个元素，{sum(len(p['issues']) for p in all_issues)} 个未达标，涉及 {len(all_issues)} 页")
    print(f"报告已写入 {args.out}")
    print(json.dumps(all_issues, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
