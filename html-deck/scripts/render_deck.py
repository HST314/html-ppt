#!/usr/bin/env python3
import argparse
import html
import sys
from pathlib import Path
from common import THEMES, ROLES, read_json, load_state, save_state
from deco import cover_deco, closing_deco, quiet_deco


ROOT = Path(__file__).resolve().parents[1]

# TASK-009: 浅色视觉方向主题集合（art DNA 深色 token 在这些主题下只作用于封面/章节/尾页）
LIGHT_THEMES = {"proposal-light", "business-light", "minimal-white", "warm-human", "editorial"}


def parse_args():
    p = argparse.ArgumentParser(description="Render SlidesPlan IR to offline HTML deck.")
    p.add_argument("--ir", required=True)
    p.add_argument("--theme", default="business-dark")
    p.add_argument("--theme-css", required=False, help="detect_style.py 派生的主题覆盖 css，叠加在基础主题之后")
    p.add_argument("--output", required=True)
    p.add_argument("--state", required=False)
    p.add_argument("--preview-only", action="store_true")
    p.add_argument("--art-dna", required=False, help="extract_art_dna.py 输出；为封面/尾页注入项目专属背景")
    return p.parse_args()


def asset_text(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def esc(s):
    return html.escape(str(s or ""), quote=True)


def block_html(block):
    t = block.get("type")
    if t == "paragraph":
        return f'<p class="body" data-animate="fade-up">{esc(block.get("text"))}</p>'
    if t == "list":
        items = "".join(f'<li style="--i:{i}">{esc(x)}</li>' for i, x in enumerate(block.get("items", [])[:8]))
        return f'<ul class="content-list" data-animate="stagger-list">{items}</ul>'
    if t == "quote":
        return f'<div class="quote-mark">“</div><div class="quote-text">{esc(block.get("text"))}</div>'
    if t == "code":
        return f'<pre class="panel" style="padding:30px;font-size:25px;line-height:1.35;white-space:pre-wrap"><code>{esc(block.get("text"))}</code></pre>'
    if t == "table":
        rows = block.get("rows", [])
        body = []
        for i, row in enumerate(rows):
            if all(set(c) <= {"-", ":"} for c in row):
                continue
            tag = "th" if i == 0 else "td"
            klass = ' class="highlight"' if i == len(rows) - 1 else ""
            body.append(f'<tr style="--row:{i}"{klass}>' + "".join(f"<{tag}>{esc(c)}</{tag}>" for c in row) + "</tr>")
        return "<table>" + "".join(body) + "</table>"
    return ""


def blocks_html(slide):
    return "\n".join(block_html(b) for b in slide.get("blocks", []))


def group_card_html(group, index):
    """TASK-003: 信息组渲染为独立视觉区块（卡片），组标题可见。"""
    items = "".join(f'<li style="--i:{j}">{esc(x)}</li>' for j, x in enumerate(group.get("items", [])[:4]))
    return (
        f'<div class="panel group-card" data-animate="fade-up" style="--i:{index}">'
        f'<h3 class="group-title">{esc(group.get("title"))}</h3>'
        f'<ul class="content-list group-list">{items}</ul>'
        f'</div>'
    )


def non_list_blocks_html(slide):
    """TASK-003: groups 页的正文只保留非列表块，列表条目由组卡片承载，避免重复。"""
    return "\n".join(block_html(b) for b in slide.get("blocks", []) if b.get("type") != "list")


def img_html(img, cls="image-frame", fit="contain", index=None):
    if not img:
        return '<div class="image-frame" data-image-slot="empty"></div>'
    ctype = img.get("content_type", "")
    frame_cls = cls + (" screenshot-frame" if ctype == "screenshot" else "")
    caption = img.get("description") or img.get("alt") or img.get("id")
    source = img.get("source") or img.get("content_type") or "scene"
    badge = f'<span class="gallery-index">{index:02d}</span>' if index else ""
    return (
        f'<figure class="{frame_cls} project-image-container" data-image-slot="{esc(img["id"])}" style="--fit:{fit}" data-animate="fade-up">'
        f'{badge}'
        f'<img src="{esc(img["file"])}" alt="{esc(img["alt"])}" loading="eager">'
        f'<figcaption class="caption-bar"><span>{esc(caption)}</span><span class="caption-source">{esc(source)}</span></figcaption>'
        f'</figure>'
    )


def takeaway_html(slide):
    text = slide.get("takeaway") or "Takeaway：本页结论需要落到下一步行动。"
    return f'<div class="takeaway" data-animate="rise-in">{esc(text)}</div>'


def notes_html(slide):
    note = str(slide.get("notes") or "")
    return f'<aside class="notes">{esc(note)}</aside>'


def cover_title_html(title):
    """封面标题拆分：冒号前为主标题（白），冒号后为强调行（主题渐变）。"""
    import re
    parts = re.split(r"[：:]", title, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return (
            f'<span class="h1-line">{esc(parts[0].strip())}</span>'
            f'<span class="h1-em">{esc(parts[1].strip())}</span>'
        )
    return f'<span class="h1-line">{esc(title)}</span>'


def slide_html(slide, section_titles=None, art_dna=None):
    role = slide.get("role")
    title = esc(slide.get("title"))
    blocks = blocks_html(slide)
    images = slide.get("images", [])
    notes = notes_html(slide)
    takeaway = "" if role in {"cover", "section", "closing"} else takeaway_html(slide)
    # TASK-009: 视觉蓝图落版——layout 变体类与追溯数据属性（样式由 assets/components/layouts.css 承载）
    layout_variant = (slide.get("layout_variant") or "").strip()
    layout_pattern = (slide.get("layout_pattern") or "").strip()
    layout_cls = f" layout-{esc(layout_variant)}" if layout_variant else ""
    common = f'data-role="{esc(role)}" data-page="{slide.get("page")}"'
    if layout_pattern:
        common += f' data-pattern="{esc(layout_pattern)}" data-variant="{esc(layout_variant)}"'
    if role not in ROLES:
        role = "bullets"
    quiet = "" if art_dna or role in {"cover", "closing", "image-hero"} else quiet_deco(section=(role == "section"))
    art_layer = ""
    # TASK-017 fix: 方向更正——撤销 TASK-015 的模板回退，首尾页恢复生成式融合背景路线
    # （用户 19:42 v9 截图明确"改回去"= 保留 v9 原版首尾页：深藏蓝近黑基底、轨道圆环/横向
    # 轨迹线/星点融入背景、白标题+金副标题高对比）；cover/closing 重新注入 project-art
    # 背景层；"融为一体"根因由下方实底深色基底 + --ho 本地重声明配套 CSS 修复；
    # artDrift 与 frame 裁切层在全页面保持不变
    if art_dna:
        key = "cover_background" if role == "cover" else "closing_background" if role == "closing" else "section_background" if role == "section" else "content_background"
        # TASK-013 fix: art 背景套 overflow:hidden 裁切框——artDrift 动画 scale/translate 会越出页边界，
        # 直接子级时越界部分计入 .slide scrollable overflow（全页 scrollHeight/scrollWidth 统一 +5/+6）；
        # 中间裁切层截断溢出传播，动画视觉效果不变
        art_layer = (
            f'<div class="project-art-frame">'
            f'<img class="project-art-bg project-art-{esc(role)}" src="{esc(art_dna.get(key))}" alt="" aria-hidden="true">'
            f'</div>'
        )
    if role == "cover":
        bg = slide.get("bg_image")
        bg_html = ""
        if bg and not art_dna:
            bg_html = (
                f'<img class="cover-bg" src="{esc(bg["file"])}" alt="{esc(bg.get("alt"))}">'
                f'<div class="cover-bg-mask"></div>'
            )
        eyebrow = esc(slide.get("eyebrow") or "CONCEPT PROPOSAL · 概念方案")
        subtitle = esc(slide.get("subtitle") or "从核心主张到落地计划的一次完整汇报")
        meta = slide.get("meta") or (section_titles or [])[:3] or ["Overview", "Evidence", "Action"]
        meta_html = "".join(f"<span>{esc(m)}</span>" for m in meta)
        art_bg = art_layer
        inner = (
            f'{art_bg}{bg_html}{"" if art_dna else cover_deco()}<canvas class="fx-canvas" width="1920" height="1080"></canvas>'  # TASK-017 fix: 封面恢复生成式融合背景，仅无 art DNA 时降级经典 deco
            f'<div class="outline-number">01</div><div class="watermark-word">DECK</div>'
            f'<div class="eyebrow">{eyebrow}</div>'
            f'<h1 data-animate="fade-up">{cover_title_html(title)}</h1>'
            f'<p class="subtitle" data-animate="blur-in">{subtitle}</p>'
            f'<div class="meta-line">{meta_html}</div>'
        )
    elif role == "toc":
        inner = f'{art_layer}<div class="watermark-word">AGENDA</div><h2>{title}</h2>{blocks}'
    elif role == "section":
        inner = f'{art_layer}<div class="outline-number">{str(slide.get("section_index") or slide.get("page")).zfill(2)}</div><div class="eyebrow">Section</div><h2 data-animate="blur-in">{title}</h2><div class="deckline" data-animate="path-draw"></div>'
    elif role == "image-hero":
        im = img_html(images[0] if images else None, "image-frame hero-image", "contain")
        inner = f'{art_layer}<div class="hero-copy"><h2>{title}</h2>{blocks}</div><div class="hero-visual">{im}</div>{takeaway}'
    elif role == "image-side":
        im = img_html(images[0] if images else None, "image-frame side-image", "contain")
        inner = f'{art_layer}<div class="copy"><h2>{title}</h2>{blocks}</div><div class="visual">{im}</div>{takeaway}'
    elif role == "gallery":
        frames = "".join(img_html(img, "image-frame", "contain", i + 1) for i, img in enumerate(images[:6]))
        grid_cls = "gallery-grid" + (" gallery-small" if len(images[:6]) <= 3 else "")
        inner = f'{art_layer}<h2>{title}</h2>{blocks}<div class="{grid_cls}">{frames}</div>{takeaway}'
    elif role == "two-column":
        groups = slide.get("groups") or []
        if groups and layout_variant.startswith(("grid-", "chain-")):
            # TASK-009: 矩阵/链式变体——全部组卡片进入单一通栏容器，格阵/链式构图由 layouts.css 承载
            cards = "\n".join(group_card_html(g, i) for i, g in enumerate(groups))
            inner = (
                f'{art_layer}<h2>{title}</h2>{non_list_blocks_html(slide)}'
                f'<div class="group-grid layout-canvas">{cards}</div>{takeaway}'
            )
        elif groups:
            # TASK-003: 每组渲染为独立卡片，偶数组入左栏、奇数组入右栏，右侧 visual panel 不空置
            cards = [group_card_html(g, i) for i, g in enumerate(groups)]
            left_cards = "\n".join(cards[::2])
            right_cards = "\n".join(cards[1::2])
            if images:
                right_cards = img_html(images[0], "image-frame side-image group-image", "contain") + right_cards
            inner = (
                f'{art_layer}<div class="copy"><h2>{title}</h2>{non_list_blocks_html(slide)}'
                f'<div class="group-stack">{left_cards}</div></div>'
                f'<div class="visual panel" style="padding:34px"><div class="group-stack">{right_cards}</div></div>{takeaway}'
            )
        elif layout_variant.startswith("loop-"):
            # TASK-009: 闭环变体——列表条目渲染为环形节点 + 闭合 SVG 回授箭头 + 中心主张（蓝图焦点）
            # TASK-011 fix: 同样跳过补位块，闭环节点数只由内容驱动（与蓝图登记数一致）
            loop_items = [x for b in slide.get("blocks", []) if b.get("type") == "list" and not b.get("generated") for x in b.get("items", [])]
            nodes = "".join(f'<div class="panel loop-node loop-node-{i+1}" data-animate="fade-up" style="--i:{i}"><p>{esc(x)}</p></div>' for i, x in enumerate(loop_items[:4]))
            claim = esc((slide.get("blueprint") or {}).get("focus") or title)
            pno = slide.get("page")
            ring = (
                f'<svg class="loop-ring" viewBox="0 0 1200 660" fill="none" aria-hidden="true">'
                f'<defs><marker id="loopArrow{pno}" markerWidth="13" markerHeight="13" refX="9" refY="6.5" orient="auto">'
                f'<path d="M0 0 L13 6.5 L0 13 z" class="loop-arrow"/></marker></defs>'
                f'<path class="loop-arc" d="M 220 250 A 400 240 0 0 1 980 250" marker-end="url(#loopArrow{pno})"/>'
                f'<path class="loop-arc" d="M 985 265 A 400 240 0 0 1 610 535" marker-end="url(#loopArrow{pno})"/>'
                f'<path class="loop-arc" d="M 590 540 A 400 240 0 0 1 212 262" marker-end="url(#loopArrow{pno})"/>'
                f'</svg>'
            )
            inner = (
                f'{art_layer}<h2>{title}</h2>{non_list_blocks_html(slide)}'
                f'<div class="loop-stage">{ring}{nodes}<div class="panel loop-claim">{claim}</div></div>{takeaway}'
            )
        else:
            parts = slide.get("blocks", [])
            left = "\n".join(block_html(b) for b in parts[::2]) or blocks
            right = "\n".join(block_html(b) for b in parts[1::2]) or (img_html(images[0], "image-frame side-image", "contain") if images else "")
            inner = f'{art_layer}<div class="copy"><h2>{title}</h2>{left}</div><div class="visual panel" style="padding:34px">{right}</div>{takeaway}'
    elif role == "table":
        inner = f'<h2>{title}</h2>{blocks}{takeaway}'
    elif role == "kpi":
        nums = []
        text = " ".join(str(b.get("text", "")) + " ".join(b.get("items", [])) for b in slide.get("blocks", []))
        import re
        found = re.findall(r"(\d+)([%x倍天分]?)", text)[:4] or [("94", "%"), ("38", "%"), ("12", "天"), ("4", "倍")]
        labels = ["目标对比", "同比变化", "过程效率", "业务影响"]
        for i, (n, suffix) in enumerate(found):
            nums.append(f'<div class="panel kpi-card" data-animate="zoom-pop" style="--i:{i}"><div class="kpi-number" data-animate="count-up" data-count-to="{esc(n)}" data-suffix="{esc(suffix)}">{esc(n)}{esc(suffix)}</div><p>{esc(labels[i % len(labels)])}</p><small>含目标/同比/基准上下文</small></div>')
        inner = f'<h2>{title}</h2>{blocks}<div class="kpi-grid">{"".join(nums)}</div>{takeaway}'
    elif role == "quote":
        inner = f'<h2>{title}</h2><div class="quote-mark">“</div>{blocks}{takeaway}'
    elif role == "compare":
        fallback = '<p class="body">目标状态：更清晰、更稳定、更可复用。</p>'
        visual = img_html(images[0], "image-frame side-image", "contain") if images else fallback
        inner = f'<h2>{title}</h2><div class="compare-grid"><div class="panel compare-card"><h3>现状</h3>{blocks}</div><div class="panel compare-card"><h3>目标状态</h3>{visual}</div></div>{takeaway}'
    elif role == "timeline":
        items = []
        for b in slide.get("blocks", []):
            # TASK-011 fix: 跳过 enrich_blocks 补位块——ascend/chain 等计数变体的节点必须全部来自
            # 正文内容（渲染节点数 = 蓝图登记阶段数），禁止把占位条目落成 T+N 幻影节点卡。
            if b.get("type") == "list" and not b.get("generated"):
                items.extend(b.get("items", []))
        cards = "".join(f'<div class="panel timeline-item" style="--i:{i}"><div class="date">{esc(item.split("｜")[0] if "｜" in item else "T+" + str(i+1))}</div><p>{esc(item)}</p></div>' for i, item in enumerate(items[:6]))
        inner = f'<h2>{title}</h2><div class="timeline-row">{cards}</div>{takeaway}'
    elif role == "closing":
        eyebrow = esc(slide.get("eyebrow") or "NEXT STEP · 落地行动")
        echo = slide.get("echo")
        echo_html = ""
        if echo:
            echo_sub = esc(slide.get("echo_sub") or "HONOR GALLERY · CONCEPT PROPOSAL")
            echo_html = f'<div class="closing-echo" data-animate="fade-up">{esc(echo)}<small>{echo_sub}</small></div>'
        art_bg = art_layer
        inner = f'{art_bg}<canvas class="fx-canvas" width="1920" height="1080"></canvas>{"" if art_dna else closing_deco()}<div class="watermark-word">NEXT</div><div class="eyebrow">{eyebrow}</div><h2>{title}</h2>{blocks}{takeaway}{echo_html}'  # TASK-017 fix: 尾页恢复生成式融合背景，仅无 art DNA 时降级经典 deco
    else:
        groups = slide.get("groups") or []
        if groups:
            # TASK-003: bullets 等兜底 role 同样把登记分组渲染为独立卡片栅格
            cards = "".join(group_card_html(g, i) for i, g in enumerate(groups))
            inner = f'{art_layer}<h2>{title}</h2>{non_list_blocks_html(slide)}<div class="group-grid">{cards}</div>{takeaway}'
        else:
            inner = f'{art_layer}<h2>{title}</h2>{blocks}{takeaway}'
    if art_layer and art_layer not in inner:
        inner = art_layer + inner
    return f'<section class="slide role-{role}{layout_cls}" {common}>{quiet}{inner}{notes}</section>'


def main():
    args = parse_args()
    if args.theme not in THEMES:
        print(f"Unknown theme: {args.theme}", file=sys.stderr)
        return 1
    state = load_state(args.state) if args.state else None
    if state is not None:
        save_state(args.state, state, "render:start")
    ir = read_json(args.ir)
    slides = ir.get("slides", [])[:1] if args.preview_only else ir.get("slides", [])
    deco_css = asset_text("assets", "components", "deco.css")
    if args.theme in LIGHT_THEMES:
        # TASK-009 fix: 浅色主题下把 deco.css「art 背景页面板深色化」收窄到
        # 封面/章节/尾页（深色生成背景页）。原全局规则会把内容页 layout 变体的
        # 深蓝 accent 组件（hub 核心卡、loop 主张胶囊等）压成浅色底白字。
        deco_css = deco_css.replace(
            ".slide:has(.project-art-bg) .panel, .slide:has(.project-art-bg) .content-list li, .slide:has(.project-art-bg) .takeaway",
            ".slide:is(.role-cover,.role-section,.role-closing):has(.project-art-bg) .panel, .slide:is(.role-cover,.role-section,.role-closing):has(.project-art-bg) .content-list li, .slide:is(.role-cover,.role-section,.role-closing):has(.project-art-bg) .takeaway",
        )
    css = "\n".join([
        asset_text("assets", "themes", args.theme + ".css"),
        asset_text("assets", "components", "typography.css"),
        asset_text("assets", "components", "base.css"),
        asset_text("assets", "animations", "animations.css"),
        deco_css,
        asset_text("assets", "components", "layouts.css"),  # TASK-009: 视觉蓝图 layout-* 变体样式
    ])
    if args.theme_css and Path(args.theme_css).exists():
        css += "\n" + Path(args.theme_css).read_text(encoding="utf-8")
    js = asset_text("assets", "runtime", "runtime.js").replace("</script>", "<\\/script>")
    section_titles = [str(s.get("title")) for s in slides if s.get("role") == "section" and s.get("title")]
    art_dna = read_json(args.art_dna) if args.art_dna and Path(args.art_dna).exists() else None
    if art_dna:
        palette = art_dna.get("dna", {}).get("palette", [])
        if len(palette) >= 3:
            # TASK-009: 浅色视觉方向（proposal-light 等）下，art DNA 深色 token 只作用于
            # 封面/章节/尾页（生成式深色背景页）；内容页落在主题浅色 token 上，
            # 内容背景图按「内容页弱化」降为淡色纹理。深色主题保持原全局覆盖行为不变。
            if args.theme in LIGHT_THEMES:
                css += f'''\n/* TASK-009: art DNA 深色 token 仅作用于生成式深色背景页 */\n.role-cover,.role-section,.role-closing{{--bg:#06101d;--page-bg:#02070d;--text:#f5f7fb;--muted:#aab4c8;--accent:{palette[1]};--accent-2:{palette[2]};--line:color-mix(in srgb,{palette[1]} 30%,transparent);--surface:rgba(5,15,28,.70);--surface-2:rgba(9,25,44,.82);}}\n.slide:not(.role-cover):not(.role-section):not(.role-closing) .project-art-bg{{opacity:.12;}}\n.slide:not(.role-cover):not(.role-section):not(.role-closing):has(.project-art-bg)::after{{background:var(--line);}}\n'''
            else:
                css += f'''\n:root{{--bg:#06101d;--page-bg:#02070d;--accent:{palette[1]};--accent-2:{palette[2]};--line:color-mix(in srgb,{palette[1]} 30%,transparent);--surface:rgba(5,15,28,.70);--surface-2:rgba(9,25,44,.82);}}\n'''
            # TASK-017 fix: 首尾页生成式融合背景的对比度配套（仅 cover/closing，中间页零影响）。
            # ① 实体深色基底：.slide 本身无 background，页面底色由共享 .deck-stage 提供（浅色主题下
            #    为浅色）；封面/尾页自带 var(--bg)（#06101d 深藏蓝近黑）实底，生成背景图（opacity .82）
            #    叠在实底上 → 基底稳定在深藏蓝近黑量级，轨道圆环/轨迹线/星点低饱和融入，
            #    对标用户 v9 截图观感，不再被浅色舞台稀释成灰蓝中亮底。
            # ② --ho 系列本地重声明：CSS 自定义属性在定义处（:root）即完成 var() 替换并固化，
            #    :root 的 --ho:var(--accent) 不随首尾页局部 --accent（art DNA 金）覆盖变化；渐变标题
            #    （h1-em/closing-echo）必须按局部 accent 重推导，保证深色实底上的对比度。
            css += "\n/* TASK-017: 首尾页融合背景对比度配套 */\n.role-cover,.role-closing{background:var(--bg);--ho:var(--accent);--ho-deep:color-mix(in srgb,var(--accent) 72%,#c03505);--ho-gold:color-mix(in srgb,var(--accent) 45%,#ffd76a);}\n"
    body = "\n".join(slide_html(s, section_titles, art_dna) for s in slides)
    doc = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(ir.get("title"))}</title>
<style>{css}</style>
</head>
<body>
<main class="deck-shell"><div class="deck-stage">{body}</div></main>
<div class="deck-ui"><span data-current>1</span><span>/</span><span data-total>{len(slides)}</span><span>← → / Space / S / O / F / B</span></div>
<nav class="overview" aria-label="Slides overview"></nav>
<script>{js}</script>
</body>
</html>
'''
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    if state is not None:
        state["completed_pages"] = [s.get("page") for s in slides]
        save_state(args.state, state, "render:done", str(out))
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
