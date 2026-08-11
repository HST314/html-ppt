#!/usr/bin/env python3
import argparse
import html
import sys
from pathlib import Path
from common import THEMES, ROLES, read_json, load_state, save_state
from deco import cover_deco, closing_deco, quiet_deco


ROOT = Path(__file__).resolve().parents[1]


def parse_args():
    p = argparse.ArgumentParser(description="Render SlidesPlan IR to offline HTML deck.")
    p.add_argument("--ir", required=True)
    p.add_argument("--theme", default="business-dark")
    p.add_argument("--theme-css", required=False, help="detect_style.py 派生的主题覆盖 css，叠加在基础主题之后")
    p.add_argument("--output", required=True)
    p.add_argument("--state", required=False)
    p.add_argument("--preview-only", action="store_true")
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


def img_html(img, cls="image-frame", fit="cover", index=None):
    if not img:
        return '<div class="image-frame" data-image-slot="empty"></div>'
    ctype = img.get("content_type", "")
    frame_cls = cls + (" screenshot-frame" if ctype == "screenshot" else "")
    caption = img.get("description") or img.get("alt") or img.get("id")
    source = img.get("source") or img.get("content_type") or "scene"
    badge = f'<span class="gallery-index">{index:02d}</span>' if index else ""
    return (
        f'<figure class="{frame_cls}" data-image-slot="{esc(img["id"])}" style="--fit:{fit}" data-animate="kenburns">'
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


def slide_html(slide, section_titles=None):
    role = slide.get("role")
    title = esc(slide.get("title"))
    blocks = blocks_html(slide)
    images = slide.get("images", [])
    notes = notes_html(slide)
    takeaway = "" if role in {"cover", "section"} else takeaway_html(slide)
    common = f'data-role="{esc(role)}" data-page="{slide.get("page")}"'
    if role not in ROLES:
        role = "bullets"
    quiet = "" if role in {"cover", "closing", "image-hero"} else quiet_deco(section=(role == "section"))
    if role == "cover":
        bg = slide.get("bg_image")
        bg_html = ""
        if bg:
            bg_html = (
                f'<img class="cover-bg" src="{esc(bg["file"])}" alt="{esc(bg.get("alt"))}">'
                f'<div class="cover-bg-mask"></div>'
            )
        eyebrow = esc(slide.get("eyebrow") or "CONCEPT PROPOSAL · 概念方案")
        subtitle = esc(slide.get("subtitle") or "从核心主张到落地计划的一次完整汇报")
        meta = slide.get("meta") or (section_titles or [])[:3] or ["Overview", "Evidence", "Action"]
        meta_html = "".join(f"<span>{esc(m)}</span>" for m in meta)
        inner = (
            f'{bg_html}{cover_deco()}<canvas class="fx-canvas" width="1920" height="1080"></canvas>'
            f'<div class="outline-number">01</div><div class="watermark-word">DECK</div>'
            f'<div class="eyebrow">{eyebrow}</div>'
            f'<h1 data-animate="fade-up">{cover_title_html(title)}</h1>'
            f'<p class="subtitle" data-animate="blur-in">{subtitle}</p>'
            f'<div class="meta-line">{meta_html}</div>'
        )
    elif role == "toc":
        inner = f'<div class="watermark-word">AGENDA</div><h2>{title}</h2>{blocks}'
    elif role == "section":
        inner = f'<div class="outline-number">{str(slide.get("section_index") or slide.get("page")).zfill(2)}</div><div class="eyebrow">Section</div><h2 data-animate="blur-in">{title}</h2><div class="deckline" data-animate="path-draw"></div>'
    elif role == "image-hero":
        im = img_html(images[0] if images else None, "image-frame hero-image", "cover")
        inner = f'{im}<div class="hero-copy"><h2>{title}</h2>{blocks}</div>{takeaway}'
    elif role == "image-side":
        im = img_html(images[0] if images else None, "image-frame side-image", "contain")
        inner = f'<div class="copy"><h2>{title}</h2>{blocks}</div><div class="visual">{im}</div>{takeaway}'
    elif role == "gallery":
        frames = "".join(img_html(img, "image-frame", "cover", i + 1) for i, img in enumerate(images[:6]))
        grid_cls = "gallery-grid" + (" gallery-small" if len(images[:6]) <= 3 else "")
        inner = f'<h2>{title}</h2>{blocks}<div class="{grid_cls}">{frames}</div>{takeaway}'
    elif role == "two-column":
        parts = slide.get("blocks", [])
        left = "\n".join(block_html(b) for b in parts[::2]) or blocks
        right = "\n".join(block_html(b) for b in parts[1::2]) or (img_html(images[0], "image-frame side-image", "contain") if images else "")
        inner = f'<div class="copy"><h2>{title}</h2>{left}</div><div class="visual panel" style="padding:34px">{right}</div>{takeaway}'
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
            if b.get("type") == "list":
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
        inner = f'<canvas class="fx-canvas" width="1920" height="1080"></canvas>{closing_deco()}<div class="watermark-word">NEXT</div><div class="eyebrow">{eyebrow}</div><h2>{title}</h2>{blocks}{takeaway}{echo_html}'
    else:
        inner = f'<h2>{title}</h2>{blocks}{takeaway}'
    return f'<section class="slide role-{role}" {common}>{quiet}{inner}{notes}</section>'


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
    css = "\n".join([
        asset_text("assets", "themes", args.theme + ".css"),
        asset_text("assets", "components", "typography.css"),
        asset_text("assets", "components", "base.css"),
        asset_text("assets", "animations", "animations.css"),
        asset_text("assets", "components", "deco.css"),
    ])
    if args.theme_css and Path(args.theme_css).exists():
        css += "\n" + Path(args.theme_css).read_text(encoding="utf-8")
    js = asset_text("assets", "runtime", "runtime.js").replace("</script>", "<\\/script>")
    section_titles = [str(s.get("title")) for s in slides if s.get("role") == "section" and s.get("title")]
    body = "\n".join(slide_html(s, section_titles) for s in slides)
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
