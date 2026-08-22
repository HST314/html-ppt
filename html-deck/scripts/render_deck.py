#!/usr/bin/env python3
import argparse
import html
import math
import re
import sys
from pathlib import Path
from common import THEMES, ROLES, LAYOUT_VARIANTS, read_json, load_state, save_state
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
    # TASK-041: classify_theme_domain.py 输出的 state/theme_domain.json 路径，
    # 供 select_toc_template() 按项目主题域挑选目录页版式；可选参数，缺省或
    # 文件不存在时 select_toc_template() 走 generic-fallback 兜底，不报错。
    p.add_argument("--theme-domain", required=False, help="classify_theme_domain.py 输出的 state/theme_domain.json 路径；用于目录页版式按主题域调度")
    return p.parse_args()


def asset_text(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def esc(s):
    return html.escape(str(s or ""), quote=True)


# TASK-024 fix（终审二次升级 U2 命中修复）：page-logic-patterns.md §17.1 要求
# 正文关键词/数据用 .hl/.num 突出（每页 1-3 处），typography.css 里两个 class
# 早已定义样式，但渲染管线一直没有任何机制能把 deck.md 正文文本转成
# `<span class="hl">`——`esc()` 对纯文本做 html.escape，即使手工在 deck.md 里
# 写 `<span>` 也会被转义成字面文本，等于该规则从未真正可执行。现补一个轻量
# `**关键词**` 行内标记（约定俗成的 Markdown 强调语法，作者友好、不引入新语法
# 学习成本）：先正常转义原文，再对转义后的文本做正则替换插入 <span class="hl">
# ——插入的标签来自代码而非用户文本，不产生新的 HTML 注入面。
_HL_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def esc_hl(s):
    return _HL_PATTERN.sub(r'<span class="hl">\1</span>', esc(s))


# TASK-022: 正文关系/逻辑类型里出现这些关键词，才说明列表条目之间存在真实
# 先后顺序（递进推进 / 流程步骤 / 时间轴节点）；并列、对比、总分、层级等无
# 先后关系的登记不触发数字编号——数字编号只承诺"有顺序"这一件事，用在并列
# 列表上就是误导性符号（口径见 references/visual-symbol-system.md）。
ORDERED_RELATION_HINTS = ("递进", "流程", "时间轴")


def is_ordered_content(slide):
    text = " ".join(str(slide.get(k) or "") for k in ("content_relation", "content_logic"))
    return any(h in text for h in ORDERED_RELATION_HINTS)


def block_html(block, ordered=False):
    t = block.get("type")
    if t == "paragraph":
        return f'<p class="body" data-animate="fade-up">{esc_hl(block.get("text"))}</p>'
    if t == "list":
        # TASK-021: 扁平列表条目补编号徽标（而非纯方点），即使内容没有正式分组
        # 登记（如 image-hero/image-side 的段落叙事页），也不再是纯文字竖排——
        # 这是"标题+竖排列表"退化复现率最高的落点，从组件根源上补视觉符号。
        # TASK-022 fix：数字编号只在页面正文关系确有先后顺序时才渲染（见
        # is_ordered_content）；并列/对比/层级等无顺序关系改用不暗示顺序的
        # 类目标记 .li-mark（纯方块，无数字），不再用 01/02/03 暗示一个内容
        # 本身并不存在的顺序——但仍然是一个真实的结构符号（标签/标记类，
        # 口径见 visual-symbol-system.md），不是把符号直接砍掉。
        def _li(i, x):
            if ordered:
                badge = f'<span class="li-index">{i+1:02d}</span>'
            else:
                badge = '<span class="li-mark" aria-hidden="true"></span>'
            return f'<li style="--i:{i}">{badge}{esc_hl(x)}</li>'
        items = "".join(_li(i, x) for i, x in enumerate(block.get("items", [])[:8]))
        return f'<ul class="content-list" data-animate="stagger-list">{items}</ul>'
    if t == "quote":
        return f'<div class="quote-mark">"</div><div class="quote-text">{esc(block.get("text"))}</div>'
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


def blocks_html(slide, ordered=False):
    return "\n".join(block_html(b, ordered=ordered) for b in slide.get("blocks", []))


def group_card_html(group, index):
    """TASK-003: 信息组渲染为独立视觉区块（卡片），组标题可见。"""
    items = "".join(f'<li style="--i:{j}">{esc_hl(x)}</li>' for j, x in enumerate(group.get("items", [])[:4]))
    return (
        f'<div class="panel group-card" data-animate="fade-up" style="--i:{index}">'
        f'<h3 class="group-title">{esc(group.get("title"))}</h3>'
        f'<ul class="content-list group-list">{items}</ul>'
        f'</div>'
    )


def extract_lead_number(*texts):
    """TASK-021: 从文本里抽取首个「数字+单位」，供 kpi 与 num-anchor 共用。"""
    joined = " ".join(str(t or "") for t in texts)
    m = re.search(r"(\d+(?:\.\d+)?)([%x倍天分米mm]?)", joined)
    if m:
        return m.group(1), m.group(2)
    return "01", ""


def _split_lead(text, maxlen=12):
    """TASK-021: 把一条扁平列表条目拆成（短标题, 正文）用于卡片化渲染。

    优先按「｜/：/:/，/,」切出短前段作标题；切不出合适短标题时退化为
    截取前 maxlen 字。始终保留完整原文本，不丢信息。
    """
    s = str(text or "").strip()
    for sep in ("｜", "：", ":", "，", ","):
        if sep in s:
            lead, rest = s.split(sep, 1)
            lead = lead.strip()
            rest = rest.strip()
            if lead and 0 < len(lead) <= maxlen and rest:
                return lead, rest
    if len(s) > maxlen:
        return s[:maxlen].rstrip("，。、,."), s
    return s, s


def synth_groups(items, max_n=4):
    """TASK-021: 无语义分组登记时，把扁平列表条目合成伪分组（标题+单条内容）。

    仅用于渲染层补足视觉符号结构，不改变 IR 语义；数量裁到 max_n，
    避免节点数超出变体推荐区间。
    """
    out = []
    for x in (items or [])[:max_n]:
        lead, rest = _split_lead(x)
        out.append({"title": lead, "items": [rest]})
    return out


# TASK-022: checkpoint-3 的节点标题必须是日期/里程碑标签（cp-date 徽章），不是
# _split_lead 默认切出的首段文本（行动编号等）。列表条目形如
# "交付01｜设计团队｜T+7 天｜完成…" 时，_split_lead 会把"交付01"当标题，真正
# 的时间坐标"T+7 天"反而被埋进正文——检查点轴的核心语义就是"时间节点"，
# 标题必须是时间点。优先从条目里挖出真实日期/相对时点，挖不到才退化为
# _split_lead 默认切法。
_DATE_HINT = re.compile(r"T[+-]\s*\d+\s*(?:天|小时|h|min|分钟)|20\d{2}[-/年]\s*\d{1,2}|Q[1-4]")


def synth_checkpoint_groups(items, max_n=4):
    out = []
    for x in (items or [])[:max_n]:
        s = str(x or "").strip()
        m = _DATE_HINT.search(s)
        if m:
            title = m.group(0).replace(" ", "")
            # TASK-024 fix（终审复核发现，非 15 条正式条目但属实测残留文本）：
            # 日期挖取自条目中段时（如"交付01｜设计团队｜T+7 天｜完成…"），
            # 挖走 "T+7 天" 后左右分隔符相邻成 "｜｜"——str.strip() 只清理首尾，
            # 中段残留双分隔符会原样渲染成正文里一个刺眼的空竖线，命中
            # page-logic-patterns.md §17.5 残留文本清理。改用正则先把连续
            # 分隔符/空白折叠成单个 "｜"，再去首尾。
            rest = s.replace(m.group(0), "", 1)
            rest = re.sub(r"[\s｜:：，,]{2,}", "｜", rest).strip(" ｜:：，,")
            out.append({"title": title, "items": [rest or s]})
        else:
            lead, rest = _split_lead(s)
            out.append({"title": lead, "items": [rest]})
    return out


def list_items_of(slide):
    """TASK-021/复用 TASK-011 口径：跳过 enrich_blocks 补位块，取真实列表条目。"""
    return [x for b in slide.get("blocks", []) if b.get("type") == "list" and not b.get("generated") for x in b.get("items", [])]


def group_grid_html(groups):
    """TASK-021: grid-/chain- 族与其它「全部卡片入单一通栏容器」变体共用的格阵。"""
    cards = "\n".join(group_card_html(g, i) for i, g in enumerate(groups))
    return f'<div class="group-grid layout-canvas">{cards}</div>'


def loop_stage_html(items, focus_text, page):
    """TASK-021: 三模块闭环 loop-3/loop-4——环形 SVG 回授箭头 + 节点 + 中心主张。"""
    nodes = "".join(f'<div class="panel loop-node loop-node-{i+1}" data-animate="fade-up" style="--i:{i}"><p>{esc(x)}</p></div>' for i, x in enumerate(items[:4]))
    claim = esc(focus_text or "")
    ring = (
        f'<svg class="loop-ring" viewBox="0 0 1200 660" fill="none" aria-hidden="true">'
        f'<defs><marker id="loopArrow{page}" markerWidth="13" markerHeight="13" refX="9" refY="6.5" orient="auto">'
        f'<path d="M0 0 L13 6.5 L0 13 z" class="loop-arrow"/></marker></defs>'
        f'<path class="loop-arc" d="M 220 250 A 400 240 0 0 1 980 250" marker-end="url(#loopArrow{page})"/>'
        f'<path class="loop-arc" d="M 985 265 A 400 240 0 0 1 610 535" marker-end="url(#loopArrow{page})"/>'
        f'<path class="loop-arc" d="M 590 540 A 400 240 0 0 1 212 262" marker-end="url(#loopArrow{page})"/>'
        f'</svg>'
    )
    return f'<div class="loop-stage">{ring}{nodes}<div class="panel loop-claim">{claim}</div></div>'


def ascend_row_html(items):
    """TASK-021: 补齐此前从未被真正生成过的 ascend-4 阶梯上行——timeline-row/timeline-item。
    日期徽标里补一个"↑"方向符呼应阶梯上行的递进语义（CSS 的 margin-top 阶梯只是
    空间位置差异，没有字符层面的方向信号，静态扫描与观众都感知不到"为什么在
    上升"）；箭头放在卡片内部而非作为新的兄弟节点插入，避免打乱
    `.layout-ascend-4 .timeline-item:nth-child(N)` 依赖的阶梯位次。
    """
    cards = "".join(
        f'<div class="panel timeline-item ascend-step" style="--i:{i}">'
        f'<div class="date">{"↑ " if i else ""}0{i+1}</div><p>{esc(x)}</p></div>'
        for i, x in enumerate(items[:4])
    )
    return f'<div class="timeline-row ascend-row">{cards}</div>'


def split_generic_html(groups, images):
    """TASK-021: hub-left/hub-radiate/hub-return/asym-cards/anchor-right/cause-effect/
    vs-split/layers-N 共用的通用双栏拆分——偶数组入左栏、奇数组入右栏；
    右栏有真实图片时保留图片在前，不用合成面板顶替，保证项目图片不丢失。
    """
    cards = [group_card_html(g, i) for i, g in enumerate(groups)]
    left_cards = "\n".join(cards[::2])
    right_cards = "\n".join(cards[1::2]) or (cards[0] if len(cards) == 1 else "")
    if len(cards) == 1:
        left_cards = cards[0]
        right_cards = ""
    if images:
        right_cards = img_html(images[0], "image-frame side-image group-image", "contain") + right_cards
    left_html = f'<div class="group-stack">{left_cards}</div>'
    right_html = f'<div class="group-stack">{right_cards}</div>' if right_cards else ""
    return left_html, right_html


def render_structural_variant(variant, groups, focus_text, page):
    """TASK-021 A.2b: 补齐 6 个此前是死代码的结构级变体（gather-3/hub-top/hub-spoke/
    num-anchor/checkpoint-3/ed-strip）的 HTML 生成器；对应 CSS 已在 layouts.css 就位，
    只是从未被渲染器调用。返回 (mode, html_or_pair)：
      mode == "single" -> 单个通栏 html 片段
      mode == "split"  -> (left_html, right_html) 供 .copy/.visual 承载
      mode is None      -> 该 variant 不在本函数职责范围内
    """
    n = groups or []
    if variant == "gather-3":
        needs = "".join(
            f'<div class="panel group-card" style="--i:{i}"><h3 class="group-title">{esc(g["title"])}</h3>'
            f'<ul class="content-list group-list"><li>{esc_hl(g["items"][0])}</li></ul></div>'
            for i, g in enumerate(n[:4])
        )
        arrows = "".join('<span>↓</span>' for _ in n[:4])
        core = f'<div class="panel gather-core"><h3 class="group-title">{esc(focus_text or "核心结论")}</h3></div>'
        html_out = (
            f'<div class="group-grid gather-rows">'
            f'<div class="gather-needs">{needs}</div>'
            f'<div class="gather-links">{arrows}</div>'
            f'{core}</div>'
        )
        return "single", html_out
    if variant == "hub-top":
        core = f'<div class="hub-top-core"><h3 class="group-title">{esc(focus_text or "统领主张")}</h3></div>'
        branches = n[:3]
        # TASK-021 fix（实测发现）：分支上限本就是 2-3 个（上方 n[:3]），但静态 CSS
        # .hub-top-branches/.hub-top-links 一直写死 repeat(2, ...)——3 个分支时第 3
        # 张卡挤到独占的第二行，行高不再共享同一批 grid 兄弟的 stretch 基线，实测
        # 会跟第一行两张卡产生真实像素高度差（Playwright sibling-uniformity 核验命中）。
        # 按实际分支数内联覆盖列数，2/3 个分支都保持单行等宽排布，不再依赖静态 2 列。
        col_style = f' style="grid-template-columns:repeat({len(branches)},minmax(0,1fr))"' if branches else ""
        arrows = "".join('<span>↓</span>' for _ in branches)
        cards = "".join(
            f'<div class="panel group-card" style="--i:{i}"><h3 class="group-title">{esc(g["title"])}</h3>'
            f'<ul class="content-list group-list"><li>{esc(g["items"][0])}</li></ul></div>'
            for i, g in enumerate(branches)
        )
        html_out = (
            f'<div class="group-grid hub-top-rows">{core}'
            f'<div class="hub-top-links"{col_style}>{arrows}</div>'
            f'<div class="hub-top-branches"{col_style}>{cards}</div></div>'
        )
        return "single", html_out
    if variant == "hub-spoke":
        left = n[0::2][:2]
        right = n[1::2][:3]
        core = f'<div class="panel spoke-core"><h3 class="group-title">{esc(focus_text or "核心结论")}</h3></div>'
        def col(gs):
            return "".join(
                f'<div class="panel group-card" style="--i:{i}"><h3 class="group-title">{esc(g["title"])}</h3>'
                f'<ul class="content-list group-list"><li>{esc(g["items"][0])}</li></ul></div>'
                for i, g in enumerate(gs)
            )
        html_out = (
            f'<div class="group-grid spoke-grid">'
            f'<div class="spoke-col">{col(left)}</div>{core}<div class="spoke-col">{col(right)}</div>'
            f'</div>'
        )
        return "single", html_out
    if variant == "num-anchor":
        chain_cards = "".join(
            f'<div class="panel group-card" style="--i:{i}"><h3 class="group-title">{esc(g["title"])}</h3>'
            f'<ul class="content-list group-list"><li>{esc(g["items"][0])}</li></ul></div>'
            for i, g in enumerate(n[:4])
        )
        left_html = f'<div class="goal-chain">{chain_cards}</div>'
        num, suffix = extract_lead_number(focus_text, *(x for g in n for x in g.get("items", [])))
        tags = "".join(f'<span class="tag-pill">{esc(g["title"])}</span>' for g in n[:6])
        right_html = (
            f'<div class="panel num-panel">'
            f'<span class="num-big">{esc(num)}<small>{esc(suffix)}</small></span>'
            f'<p class="num-note">{esc(focus_text or "")}</p>'
            f'<div class="tag-pill-row">{tags}</div></div>'
        )
        return "split", (left_html, right_html)
    if variant == "checkpoint-3":
        nodes = n[:4]
        current_idx = max(0, len(nodes) - 1)
        parts = []
        for i, g in enumerate(nodes):
            cur = " is-current" if i == current_idx else ""
            tag = '<span class="cp-current-tag">当前锁定</span>' if i == current_idx else ""
            parts.append(
                f'<div class="checkpoint-node{cur}"><span class="cp-date">{esc(g["title"])}</span>'
                f'<p class="body">{esc_hl(g["items"][0])}</p>{tag}</div>'
            )
            if i < len(nodes) - 1:
                parts.append('<div class="cp-link">→</div>')
        html_out = f'<div class="group-grid checkpoint-flow">{"".join(parts)}</div>'
        return "single", html_out
    if variant == "ed-strip":
        rows = "".join(
            f'<div class="ed-strip"><span class="ed-name">{esc(g["title"])}</span><p class="ed-text">{esc(g["items"][0])}</p></div>'
            for g in n[:4]
        )
        html_out = f'<div class="ed-flow">{rows}</div>'
        if focus_text:
            html_out += f'<div class="ed-brand">{esc(focus_text)}</div>'
        return "single", html_out
    return None, None


# TASK-021: 单容器结构级变体——内容天然是"序列/汇聚/分支"时，允许从扁平列表条目
# 合成伪分组来驱动渲染（无正式语义分组登记也能落版）。split 族（hub-left 等）
# 只在真正有语义分组登记时才重组正文，避免把语义层刻意登记为"不分组"的
# 段落叙事页（如 image-hero/image-side 的图文长叙事）强行拆成卡片。
SELF_CONTAINED_SYNTH_VARIANTS = {
    "grid-2x2", "grid-2x3", "chain-3", "chain-4", "ascend-4",
    "loop-3", "loop-4", "gather-3", "hub-top", "hub-spoke", "checkpoint-3", "ed-strip",
}


def render_variant_body(slide, layout_variant, layout_pattern, groups, images):
    """TASK-021 A.2: 唯一的"结构+符号"渲染出口，只认 groups/layout_variant 是否存在，
    不认 role——把原先只挂在 role=="two-column" 分支下的 grid/chain/hub/loop/
    vs-split/cause-effect/layers 生成逻辑解耦为共享函数，供 bullets/two-column/
    image-hero/image-side 等角色统一调用。

    返回 dict：{"mode": "single"|"split"|None, "single": str, "left": str, "right": str}
    mode 为 None 表示该角色/该页不适合结构化渲染（变体为空或内容不足，或语义层
    明确登记为不分组的段落叙事页遇上需要真实分组的 split 族变体），调用方须保留
    角色原有默认渲染，不强行套壳。
    """
    variant = (layout_variant or "").strip()
    empty = {"mode": None, "single": "", "left": "", "right": ""}
    if not variant or variant not in LAYOUT_VARIANTS:
        return empty
    list_items = list_items_of(slide)
    has_real_groups = bool(groups)
    if has_real_groups:
        effective_groups = groups
    elif variant == "checkpoint-3":
        # TASK-022: 检查点轴的节点标题必须是真实时间点，走专用日期提取合成
        effective_groups = synth_checkpoint_groups(list_items)
    elif variant in SELF_CONTAINED_SYNTH_VARIANTS:
        effective_groups = synth_groups(list_items)
    else:
        effective_groups = []
    if not effective_groups:
        return empty
    focus_text = (slide.get("blueprint") or {}).get("focus") or slide.get("takeaway") or slide.get("title")
    page = slide.get("page")

    # num-anchor 的右栏是合成数字面板，会顶替真实图片；已有项目图片时改走
    # 通用双栏拆分保留图片，不牺牲"图片零裁切/不遮挡"的既有约束。
    if variant == "num-anchor" and images:
        left, right = split_generic_html(effective_groups, images)
        return {"mode": "split", "single": "", "left": left, "right": right}

    # ── 6 个结构级变体（A.2b，此前是死代码）──
    mode, out = render_structural_variant(variant, effective_groups, focus_text, page)
    if mode == "single":
        return {"mode": "single", "single": out, "left": "", "right": ""}
    if mode == "split":
        left, right = out
        return {"mode": "split", "single": "", "left": left, "right": right}

    # ── grid-/chain- 族：全部卡片入单一通栏容器 ──
    if variant in {"grid-2x2", "grid-2x3", "chain-3", "chain-4"}:
        return {"mode": "single", "single": group_grid_html(effective_groups), "left": "", "right": ""}

    # ── ascend-4：阶梯上行（此前从未被真正生成过，本次一并补齐）──
    if variant == "ascend-4":
        raw_items = list_items or [g["items"][0] for g in effective_groups]
        return {"mode": "single", "single": ascend_row_html(raw_items), "left": "", "right": ""}

    # ── loop-3/loop-4：环形 SVG 回授箭头 + 节点 + 中心主张 ──
    if variant in {"loop-3", "loop-4"}:
        loop_items = list_items or [g["items"][0] for g in effective_groups]
        return {"mode": "single", "single": loop_stage_html(loop_items, focus_text, page), "left": "", "right": ""}

    if not has_real_groups:
        return empty

    # ── layers-N：分层条 L1…Ln 自上而下递缩，必须是单列顺序堆叠（CSS 靠
    #    [class*="layout-layers"] .group-card:nth-child(N) 逐层递增 margin-left
    #    做阶梯缩进、counter(layer) 逐层编号 L1/L2/L3），不能像 hub-left/
    #    asym-cards 等真双栏变体那样把分组按奇偶拆进左右两个独立 .group-stack——
    #    拆成两栏后每栏各自的 nth-child 计数与 counter 都从 1 重新起算，实测会
    #    渲染出"L1/L2/L1"这种层号错乱、且视觉顺序也被打乱（核心平台/省部级平台
    #    落左栏、国家级平台单独落右栏，不再是"核心→国家级→省部级"的原始层序）。
    #    全部分组塞进同一个 .copy 内的单个 .group-stack，右栏留空。 ──
    if variant.startswith("layers-"):
        cards = "".join(group_card_html(g, i) for i, g in enumerate(effective_groups))
        return {"mode": "split", "single": "", "left": f'<div class="group-stack">{cards}</div>', "right": ""}

    # ── hub-left/hub-radiate/hub-return/asym-cards/anchor-right/cause-effect/
    #    vs-split：通用双栏拆分，CSS 靠 .slide.layout-X 差异化描边/符号；
    #    只在真正有语义分组登记时重组（has_real_groups），否则保留原段落渲染 ──
    left, right = split_generic_html(effective_groups, images)
    return {"mode": "split", "single": "", "left": left, "right": right}


def non_list_blocks_html(slide):
    """TASK-003: groups 页的正文只保留非列表块，列表条目由组卡片承载，避免重复。"""
    return "\n".join(block_html(b) for b in slide.get("blocks", []) if b.get("type") != "list")


# TASK-025: kpi 页导语裁到一句话——数字卡片（kpi-grid）才是本页视觉焦点，列表
# 条目已经被解析消费成大数字卡片（见 role=="kpi" 分支），导语只承担"引导句"
# 职能，不需要在数字卡片之外再铺陈一段可有可无的说明文字。
_SENTENCE_END = re.compile(r"[。！？.!?]")


def kpi_lead_html(slide, maxlen=40):
    for b in slide.get("blocks", []):
        if b.get("type") == "paragraph":
            text = str(b.get("text") or "").strip()
            if not text:
                continue
            m = _SENTENCE_END.search(text)
            lead = text[:m.end()] if m else text
            if not m and len(lead) > maxlen:
                lead = lead[:maxlen].rstrip("，,、") + "…"
            return f'<p class="body" data-animate="fade-up">{esc_hl(lead)}</p>'
    return ""


# TASK-025: gallery 每条列表条目形如"图一·金珐琅星空浮雕｜奢华航天美学，掐丝
# 珐琅与高浮雕铸就庄重质感"——"｜"之后、首个逗号之前是风格定位短语（4-8字），
# 提炼出来追加进对应图片自己的 caption-bar，让说明文字长在图片身上，正文不再
# 逐条复述（见 role=="gallery" 分支与 references/page-logic-patterns.md §17.7）。
def gallery_style_tag(item, maxlen=8):
    s = str(item or "").strip()
    if "｜" in s:
        s = s.split("｜", 1)[1]
    for sep in ("，", ",", "。"):
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    s = s.strip()
    return s[:maxlen] if len(s) > maxlen else s


def img_html(img, cls="image-frame", fit="contain", index=None, caption_override=None):
    """caption_override（TASK-025）：gallery 等角色把正文列表条目消费成图片自己的
    图注补充时传入（追加在默认 caption 之后），避免同一批信息在正文列表与图片
    说明里各出现一遍——见 role=="gallery" 分支与 references/page-logic-patterns.md
    §17.7。不传时保持原有行为不变。"""
    if not img:
        return '<div class="image-frame" data-image-slot="empty"></div>'
    ctype = img.get("content_type", "")
    frame_cls = cls + (" screenshot-frame" if ctype == "screenshot" else "")
    caption = img.get("description") or img.get("alt") or img.get("id")
    if caption_override:
        caption = f"{caption}｜{caption_override}" if caption else caption_override
    source = img.get("source") or img.get("content_type") or "scene"
    badge = f'<span class="gallery-index">{index:02d}</span>' if index else ""
    return (
        f'<figure class="{frame_cls} project-image-container" data-image-slot="{esc(img["id"])}" style="--fit:{fit}" data-animate="fade-up">'
        f'{badge}'
        f'<img src="{esc(img["file"])}" alt="{esc(img["alt"])}" loading="eager">'
        f'<figcaption class="caption-bar"><span>{esc(caption)}</span><span class="caption-source">{esc(source)}</span></figcaption>'
        f'</figure>'
    )


# TASK-022: takeaway 从"每个内容页强制渲染"改为"默认不渲染"——此前的兜底文案
# "Takeaway：本页结论需要落到下一步行动。"和自动复制导语的 infer_takeaway 一样，
# 都是为了填满一个"必须存在"的坑而制造的复读/空话。现在没有 takeaway 就不生成
# 这个 DOM 节点，slide-foot/内联位置自然收缩或被 :empty 规则隐藏（见 base.css）。
def takeaway_html(slide):
    text = str(slide.get("takeaway") or "").strip()
    if not text:
        return ""
    return f'<div class="takeaway" data-animate="rise-in">{esc(text)}</div>'


def notes_html(slide):
    note = str(slide.get("notes") or "")
    return f'<aside class="notes">{esc(note)}</aside>'


def toc_modern_card_html(cards, main_title, fallback_html):
    """toc 角色专属渲染：商务简约异形圆角卡片目录（slide_templates/toc/toc-modern-card.html
    接入版，样式见 assets/components/toc-modern-card.css）。顶部主标题 + 下方 flex
    自动换行卡片阵列，每张卡片承载编号 + 章节名 + 一句话描述，天然适配任意节点数量。
    cards 为空（如非 storyline 驱动的其它项目未产出 toc_cards）时退回旧版列表渲染，
    保证目录页不会因缺数据而空白。
    """
    if not cards:
        return f'<div class="watermark-word">AGENDA</div><h2>{main_title}</h2>{fallback_html}'
    # TASK-036：补入场动画（此前是库里唯一没有 data-animate 的已接入 toc 版式）——
    # 标题头 fade-up；卡片逐张 fade-up + 按 i 递增的内联 animation-delay（不用
    # stagger-list 包一层 wrapper，理由同 toc_orbit_hub_html：
    # check_sibling_uniformity 对 `.mc-grid>.mc-card` 做直接子级选择器核验，
    # 多包一层会破坏该 QA 规则）。
    card_html = "".join(
        f'<div class="mc-card" data-idx="{i + 1}" data-animate="fade-up" style="animation-delay:{120 + i * 70}ms">'
        f'<span class="mc-num">{esc(c.get("num"))}</span>'
        f'<h3 class="mc-title-row">{esc(c.get("title"))}</h3>'
        f'<p class="mc-desc">{esc(c.get("desc"))}</p>'
        f'</div>'
        for i, c in enumerate(cards)
    )
    return (
        f'<div class="toc-modern-card">'
        f'<div class="mc-bg-glow"></div>'
        f'<div class="mc-head" data-animate="fade-up"><p class="mc-eyebrow">CONTENTS</p>'
        f'<h1 class="mc-title">{main_title}</h1><div class="mc-head-line"></div></div>'
        f'<div class="mc-grid">{card_html}</div>'
        f'</div>'
    )


# TASK-031: 目录铭牌（.ss-plaque）标题超长时的通用精简规则。铭牌是固定
# height:152px + -webkit-line-clamp:2 的定高卡片（见 toc-segment-strip.css
# 头部注释里的算法：2 行 × 30px 字号 × 1.34 行高 ≈ 80px 内容高度 + 上下
# padding ≈146px，取 152px），按当前字号/卡片宽度实测可安全容纳约 12~13 个
# 汉字（2 行、每行约 6~7 字）。deck.md 的 `##` 二级标题有的是"章节名：一句
# 评语"这种复合短句（如"作品深读：每一枚徽章都是一扇门"共 15 字），超出
# 铭牌可安全容纳的字数时，与其让浏览器在行末硬截断出突兀的半截句子，不如
# 直接只取冒号前的"章节核心名"——冒号后半句通常是修饰性评语，砍掉不影响
# 观众理解目录结构（其余 5 个章节名本身就是"序章：一切准备就绪"这类不含
# 长评语的短句，或者压根没有冒号，天然不会触发本规则）。
# 优先级：① 未超阈值——原样返回，交给 CSS line-clamp 兜底（正常不触发）；
# ② 超阈值且含"："/":"——取冒号前半句，仍超阈值才继续到③；③ 硬截断补
# 省略号（双重兜底，配合 CSS line-clamp，理论上不会用到，但防止未来出现
# "冒号前半句本身也超长"或"完全没有冒号的超长标题"这类边界情况）。
# 6 个铭牌一视同仁地跑同一条规则，不是只修某一个。
TOC_PLAQUE_TITLE_MAXLEN = 12


def shrink_toc_plaque_title(title, max_chars=TOC_PLAQUE_TITLE_MAXLEN):
    t = str(title or "").strip()
    if len(t) <= max_chars:
        return t
    for sep in ("：", ":"):
        if sep in t:
            head = t.split(sep, 1)[0].strip()
            if head:
                t = head
            break
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def toc_segment_strip_html(cards, main_title, fallback_html):
    """toc 角色可选渲染版式之一（TASK-032：不再是当前生效版式，改由
    toc_orbit_hub_html 接替，函数保留供以后按场景切回/选用，不删除）：
    分栏满版色块目录（slide_templates/toc/
    toc-segment-strip.html 接入版，样式见 assets/components/toc-segment-strip.css）。
    深色渐变海报底 + 顶部主标题 + 下方等分栏，每栏巨型幽灵数字打底、底部异形
    圆角铭牌（非对称圆角 + 左上角悬浮圆形徽标）承载编号对应的章节名。只渲染
    实际传入的栏数（本项目 6 栏），不补齐模板预留的 7/8 栏空位。
    cards 为空时退回旧版列表渲染，保证目录页不会因缺数据而空白。
    TASK-027 fix：铭牌不再渲染一句话描述（ss-plaque-desc）——用户反馈目录页
    "不要那么多字都堆叠在底下，只用出现每一部分的小标题就够了"，目录页的
    作用是让观众一眼扫过 6 栏抓住 6 个章节名，正文/解释放在各章节自己的
    内容页里讲。cards 数据结构里的 desc 字段本身不删（build_ir.py 仍产出，
    留给其他可能消费它的模板），这里只是不再消费。
    """
    if not cards:
        return f'<div class="watermark-word">AGENDA</div><h2>{main_title}</h2>{fallback_html}'
    # TASK-036：补入场动画（此前库里唯一没有 data-animate 的已接入 toc 版式）——
    # 标题头 fade-up；每栏（ss-seg，含幽灵数字 + 铭牌）fade-up + 按 i 递增的
    # 内联 animation-delay，节奏与 toc_orbit_hub_html/toc_modern_card_html 一致。
    seg_html = "".join(
        f'<div class="ss-seg" data-idx="{i + 1}" data-animate="fade-up" style="animation-delay:{120 + i * 70}ms">'
        f'<span class="ss-ghost-num">{esc(c.get("num"))}</span>'
        f'<div class="ss-plaque">'
        f'<h3 class="ss-plaque-title">{esc(shrink_toc_plaque_title(c.get("title")))}</h3>'
        f'</div>'
        f'</div>'
        for i, c in enumerate(cards)
    )
    return (
        f'<div class="toc-segment-strip">'
        f'<div class="ss-head" data-animate="fade-up"><p class="ss-eyebrow">CONTENTS</p>'
        f'<h1 class="ss-title">{main_title}</h1></div>'
        f'<div class="ss-row">{seg_html}</div>'
        f'</div>'
    )


# ── TASK-032: toc-orbit-hub —— 中心枢纽 + 环形卫星节点目录 ──────────────────
# 画布固定 1920×1080（与 .slide 既定假设一致，见 assets/components/base.css），
# 中心枢纽（hub）承载目录总标题，直径固定不随节点数 N 变化——枢纽是一份稳定
# 的"品牌识别"元素，不该随章节多寡改变形状。卫星节点直径同一份 deck 内全部
# 统一（并列容器尺寸一致纪律，见 references/final-quality-check.md V4），
# 仅当 N 较大（实测到 N=8）导致节点按最大直径环绕一圈会互相重叠时，才整体
# 下调直径，直到不重叠为止，绝不通过"部分节点大、部分节点小"来腾地方。
#
# 轨道半径 R 取三个约束的可行解：① 不与枢纽重叠（留出辐条间隙 hub_gap）；
# ② 相邻节点不互相咬合（留出最小间隙 spacing_gap，用 360°/N 的弦长公式
# `2*R*sin(pi/N)` 反推）；③ 不超出画布纵向可视区（画布 1080px 高是横向
# 16:9 画布里更紧张的一维，纵向留白 v_margin 后夹出上限）。三者中先取
# ①②的较大值作为下限，再用③夹一个上限；下限超过上限时（N 很大、直径已在
# sat_d_min 兜底仍冲突的极端情况）整体缩小卫星直径重新求解，直到二者相容
# 或直径触底——这就是本函数替代 toc-arc-card.html/toc-curve-timeline.html
# 硬编码 8 节点坐标表的通用做法：任意 N 都精确用 360°/N 均匀计算角度与
# 半径，不依赖 CSS 里写死的坐标。
def compute_orbit_layout(n, canvas_w=1920, canvas_h=1080, hub_d=380,
                          sat_d_max=250, sat_d_min=210, hub_gap=45,
                          spacing_gap=16, v_margin=50):
    cx, cy = canvas_w / 2, canvas_h / 2
    hub_r = hub_d / 2
    v_budget = canvas_h / 2 - v_margin
    n_eff = max(int(n), 2)
    sat_d = sat_d_max
    while True:
        sat_r = sat_d / 2
        vcap = v_budget - sat_r
        hub_cap = hub_r + sat_r + hub_gap
        spacing_min = (sat_d + spacing_gap) / (2 * math.sin(math.pi / n_eff))
        r_orbit = max(hub_cap, spacing_min)
        if r_orbit <= vcap or sat_d <= sat_d_min:
            r_orbit = min(r_orbit, vcap)
            r_orbit = max(r_orbit, hub_r + sat_r + 8)  # 保底：任何情况都不与枢纽重叠
            break
        sat_d -= 10
    return {
        "cx": cx, "cy": cy, "hub_d": hub_d, "hub_r": hub_r,
        "sat_d": sat_d, "sat_r": sat_r, "r_orbit": r_orbit,
    }


def orbit_node_position(i, n, layout):
    """第 i 个节点（0-based）的角度：从正上方 12 点钟方向起、按 360°/N 顺时针
    均匀分布（theta = i * 360/N）。用 math.sin/cos 直接算出节点中心像素坐标
    与枢纽边缘上同方向的连接点坐标（供辐条连线起点使用），对任意 N 都精确
    均匀，不是从预先写死的坐标表里查表。"""
    theta = math.radians(i * (360.0 / max(int(n), 1)))
    cx, cy, r, hub_r = layout["cx"], layout["cy"], layout["r_orbit"], layout["hub_r"]
    nx = cx + r * math.sin(theta)
    ny = cy - r * math.cos(theta)
    hx = cx + hub_r * math.sin(theta)
    hy = cy - hub_r * math.cos(theta)
    return nx, ny, hx, hy


# TASK-032: orbit-hub 卫星节点圆形直径比 segment-strip 铭牌略小（见
# compute_orbit_layout 的 sat_d_max=250），可用文字宽度更窄，标题上限比铭牌
# （TOC_PLAQUE_TITLE_MAXLEN=12）收紧到 10 字；复用 shrink_toc_plaque_title
# 同一套算法（冒号截取优先，仍超阈值再硬截断补省略号），不重复实现。
TOC_ORBIT_NODE_TITLE_MAXLEN = 10


def shrink_toc_node_title(title, max_chars=TOC_ORBIT_NODE_TITLE_MAXLEN):
    return shrink_toc_plaque_title(title, max_chars)


# 中心枢纽直径固定 380px，明显大于卫星节点，可容纳的文字量也更宽松，阈值
# 放宽到 16 字（2 行 × 8 字/行），同样复用 shrink_toc_plaque_title 的算法。
TOC_ORBIT_HUB_TITLE_MAXLEN = 16


def shrink_toc_hub_title(title, max_chars=TOC_ORBIT_HUB_TITLE_MAXLEN):
    return shrink_toc_plaque_title(title, max_chars)


def toc_orbit_hub_html(cards, main_title, fallback_html):
    """toc 角色专属渲染（TASK-032 新增，当前生效版）：中心枢纽 + 环形卫星节点
    目录（slide_templates/toc/toc-orbit-hub.html 预览版接入，样式见
    assets/components/toc-orbit-hub.css）。深色科技风：中心一颗径向渐变发光
    球体（hub）承载目录总标题，N 个卫星节点圆形按 360°/N 精确均匀环绕
    （compute_orbit_layout()/orbit_node_position() 用 Python math.cos/sin
    现场计算像素坐标，对任意 N 通用，不硬编码坐标表——吸取
    toc-arc-card.html/toc-curve-timeline.html 硬编码 8 节点坐标导致 N<8 时
    分布不均、留白缺口的教训）。--accent-2 派生的暖色辐条虚线连接 hub 与
    各节点，外圈叠加一条穿过全部节点圆心的虚线轨道环。
    卫星节点圆形直径同一份 deck 内固定统一（见 compute_orbit_layout），标题
    经 shrink_toc_node_title 精简 + CSS -webkit-line-clamp 双重兜底，
    杜绝文字压边/溢出容器边界。
    典型适用节点数 3-8（与目录页节点数上限一致）。
    cards 为空（如非 storyline 驱动的其它项目未产出 toc_cards）时退回旧版
    列表渲染，保证目录页不会因缺数据而空白。
    """
    if not cards:
        return f'<div class="watermark-word">AGENDA</div><h2>{main_title}</h2>{fallback_html}'
    n = len(cards)
    layout = compute_orbit_layout(n)
    sat_d, sat_r = layout["sat_d"], layout["sat_r"]
    hub_d, hub_r = layout["hub_d"], layout["hub_r"]
    cx, cy = layout["cx"], layout["cy"]
    # TASK-032 fix（首版截图核对时实测发现）：内边距不能用 CSS 百分比——
    # .oh-hub/.oh-node 的包含块是铺满整页的 .toc-orbit-hub（宽度 1920px），
    # 百分比 padding（含上下方向）一律按包含块宽度折算，不是按圆形自身
    # 直径，会把内边距撑到几百像素，配合 box-sizing:border-box「内边距
    # 撑爆时盒子被迫增宽」的规则，把球体/节点压成扁椭圆（实测截图复现，
    # 见 assets/components/toc-orbit-hub.css 文件头说明）。改为按各自实际
    # 直径现场算出具体 px 内边距，用内联 style 下发，不依赖 CSS 百分比。
    node_pad = round(sat_d * 0.13)
    hub_pad_h = round(hub_d * 0.14)

    # TASK-034：目录页入场动画——用户反馈"目录页要适当加点动画效果"，克制起见
    # 只用 ANIMATIONS.md 已登记的三个名称、各司其职，不叠加多层：
    # ① 卫星节点 fade-up + 按 i 递增的 animation-delay（内联 style，不依赖
    #    stagger-list 容器）——逐个"浮现"的节奏感。之所以不用现成的
    #    stagger-list 机制（[data-animate="stagger-list"] > * 靠父容器统一
    #    分发），是因为 qa_render.py::check_sibling_uniformity 对
    #    `.toc-orbit-hub :scope > .oh-node` 做直接子级选择器核验（见该函数
    #    NODE_SIBLING_GROUPS 登记），若给 6 个节点包一层 wrapper div 才能用
    #    stagger-list，会破坏这条已验证的 QA 规则；改用 fade-up 单动画名 +
    #    内联 animation-delay 精确控制每个节点自己的入场时机，节点仍是
    #    .toc-orbit-hub 的直接子级，不改变现有 DOM 结构。
    # ② 辐条连线 path-draw——挂在 <svg> 容器上，只对其内部真实 <line>（辐条）
    #    生效，轨道圆环/端点圆点（circle）不受影响、正常静态显示，克制不
    #    过度动画化。
    # ③ 中心球体 zoom-pop——独立于节点/连线，延迟 0（先出现，作为"中心先
    #    立住，卫星再依次浮现"的视觉引导起点）；外层柔光晕（.oh-hub-glow）
    #    不单独加动画，避免同一区域双重动效显得杂乱。
    NODE_FADE_BASE_DELAY_MS = 150   # 节点开始入场前，先留出给中心球体站定的时间
    NODE_FADE_STEP_MS = 90          # 每个节点之间的错开间隔

    node_html_parts = []
    spoke_parts = []
    dot_parts = []
    for i, c in enumerate(cards):
        nx, ny, hx, hy = orbit_node_position(i, n, layout)
        node_delay = NODE_FADE_BASE_DELAY_MS + i * NODE_FADE_STEP_MS
        node_html_parts.append(
            f'<div class="oh-node" data-idx="{i + 1}" data-animate="fade-up" '
            f'style="left:{nx - sat_r:.1f}px;top:{ny - sat_r:.1f}px;width:{sat_d:.1f}px;height:{sat_d:.1f}px;'
            f'padding:{node_pad}px;animation-delay:{node_delay}ms">'
            f'<span class="oh-node-num">{esc(c.get("num"))}</span>'
            f'<h3 class="oh-node-title">{esc(shrink_toc_node_title(c.get("title")))}</h3>'
            f'<p class="oh-node-desc">{esc(c.get("desc"))}</p>'
            f'</div>'
        )
        spoke_parts.append(f'<line class="oh-spoke" x1="{hx:.1f}" y1="{hy:.1f}" x2="{nx:.1f}" y2="{ny:.1f}"/>')
        dot_parts.append(f'<circle class="oh-spoke-dot" cx="{hx:.1f}" cy="{hy:.1f}" r="6"/>')

    svg_html = (
        f'<svg class="oh-orbit-svg" viewBox="0 0 1920 1080" aria-hidden="true" data-animate="path-draw">'
        f'<circle class="oh-orbit-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="{layout["r_orbit"]:.1f}"/>'
        f'{"".join(spoke_parts)}{"".join(dot_parts)}'
        f'</svg>'
    )
    glow_d = hub_d * 1.6
    hub_html = (
        f'<div class="oh-hub-glow" style="left:{cx - glow_d / 2:.1f}px;top:{cy - glow_d / 2:.1f}px;'
        f'width:{glow_d:.1f}px;height:{glow_d:.1f}px"></div>'
        f'<div class="oh-hub" data-animate="zoom-pop" style="left:{cx - hub_r:.1f}px;top:{cy - hub_r:.1f}px;'
        f'width:{hub_d:.1f}px;height:{hub_d:.1f}px;padding:0 {hub_pad_h}px">'
        f'<p class="oh-hub-eyebrow">CONTENTS</p>'
        f'<h1 class="oh-hub-title">{shrink_toc_hub_title(main_title)}</h1>'
        f'<div class="oh-hub-rule"></div>'
        f'</div>'
    )
    return f'<div class="toc-orbit-hub">{svg_html}{hub_html}{"".join(node_html_parts)}</div>'


# ── TASK-036: toc-grid-matrix —— 矩阵网格式目录（新增版式一） ──────────────
# 参考 skill reference learning/beautiful-html-templates-main/templates/
# neo-grid-bold/template.html 的 .s-toc：工整网格、标题占满顶部、下方卡片
# 按行列精确铺满，强对比、编辑设计感，适合信息密度较高（条目数偏多）的
# 目录场景。列数不写死坐标表，用 compute_grid_columns() 按 N 算出"列数"这
# 一个参数，交给 CSS Grid（grid-template-columns:repeat(cols,1fr) +
# grid-auto-rows:1fr）自动铺满行列的具体位置——延续 toc_orbit_hub_html 用
# 数学公式代替坐标表的做法，任意 N=3~8 通用，不重演 toc-arc-card.html/
# toc-curve-timeline.html 硬编码 8 节点坐标导致 N<8 时分布不均的反面案例。
def compute_grid_columns(n):
    """按条目数选一个让末行也尽量饱满的列数：3/4 条单行铺满；5/6 条 3 列（两行
    3+2 或 3+3）；7/8 条 4 列（两行 4+3 或 4+4）。只决策"列数"这一个整数，
    每个格子在网格里的具体像素位置仍全部交给 CSS Grid 自动排布计算，不是
    逐条目写死坐标。"""
    n = max(int(n), 1)
    if n <= 4:
        return n
    if n <= 6:
        return 3
    return 4


TOC_GRID_TITLE_MAXLEN = 14


def shrink_toc_grid_title(title, max_chars=TOC_GRID_TITLE_MAXLEN):
    return shrink_toc_plaque_title(title, max_chars)


def toc_grid_matrix_html(cards, main_title, fallback_html):
    """toc 角色可选渲染版式（TASK-036 新增）：矩阵网格式目录（
    slide_templates/toc/toc-grid-matrix.html 预览版接入，样式见
    assets/components/toc-grid-matrix.css）。顶部主标题占满整行 + 右侧条目
    计数，下方卡片按 compute_grid_columns(N) 算出的列数用 CSS Grid 精确铺满
    行列，每张卡片承载编号 + 大号幽灵数字底纹 + 章节名 + 一句话描述。
    入场动画：标题头 fade-up；卡片逐张 fade-up + 按 i 递增的内联
    animation-delay（同 toc_orbit_hub_html 的理由：check_sibling_uniformity
    对 `.tgm-grid>.tgm-card` 做直接子级选择器核验，不能包 stagger-list 的
    wrapper）。
    cards 为空时退回旧版列表渲染，保证目录页不会因缺数据而空白。
    """
    if not cards:
        return f'<div class="watermark-word">AGENDA</div><h2>{main_title}</h2>{fallback_html}'
    n = len(cards)
    cols = compute_grid_columns(n)
    card_html = "".join(
        f'<div class="tgm-card" data-idx="{i + 1}" data-animate="fade-up" style="animation-delay:{150 + i * 70}ms">'
        f'<span class="tgm-ghost" aria-hidden="true">{esc(c.get("num"))}</span>'
        f'<span class="tgm-num">{esc(c.get("num"))}</span>'
        f'<h3 class="tgm-card-title">{esc(shrink_toc_grid_title(c.get("title")))}</h3>'
        f'<p class="tgm-desc">{esc(c.get("desc"))}</p>'
        f'</div>'
        for i, c in enumerate(cards)
    )
    return (
        f'<div class="toc-grid-matrix">'
        f'<div class="tgm-head" data-animate="fade-up">'
        f'<p class="tgm-eyebrow">CONTENTS</p>'
        f'<h1 class="tgm-title-main">{main_title}</h1>'
        f'<span class="tgm-count">{n:02d}</span>'
        f'</div>'
        f'<div class="tgm-grid" style="--cols:{cols}">{card_html}</div>'
        f'</div>'
    )


# ── TASK-036: toc-magazine-index —— 杂志索引式目录（新增版式二） ──────────
# 参考 skill reference learning/beautiful-html-templates-main/templates/
# peoples-platform 与 pin-and-paper 的目录页气质：编号 + 标题 + 虚线引导线 +
# 页码横向单行排列，行与行之间用实线分隔，纯文本导向、克制——是此前
# html-deck 目录库里完全没有的"极简书目录"风格。逐行用 flex:1 均分纵向
# 可用空间，天然适配任意 N=3~8 条目，不依赖硬编码坐标或行高表。
TOC_MAGAZINE_TITLE_MAXLEN = 22


def shrink_toc_magazine_title(title, max_chars=TOC_MAGAZINE_TITLE_MAXLEN):
    return shrink_toc_plaque_title(title, max_chars)


def toc_magazine_index_html(cards, main_title, fallback_html):
    """toc 角色可选渲染版式（TASK-036 新增）：杂志索引式目录（
    slide_templates/toc/toc-magazine-index.html 预览版接入，样式见
    assets/components/toc-magazine-index.css）。编号 + 标题 + 虚线引导线 +
    页码单行横排，纯文本导向、克制，适合章节数偏少、希望目录本身极简的
    场景。每行 flex:1 1 0 均分 .tmi-list 的纵向可用空间，条目越少单行越
    宽裕、越多单行越紧凑，均不会溢出（行高由 flex 分配，不是固定像素）。
    入场动画：标题头 fade-up；每行 fade-up + 按 i 递增的内联
    animation-delay（不用 stagger-list wrapper，保持 `.tmi-list>.tmi-row`
    直接子级结构，便于以后接入 check_sibling_uniformity 一类核验）。
    cards 为空时退回旧版列表渲染，保证目录页不会因缺数据而空白。
    """
    if not cards:
        return f'<div class="watermark-word">AGENDA</div><h2>{main_title}</h2>{fallback_html}'
    row_html = "".join(
        f'<div class="tmi-row" data-idx="{i + 1}" data-animate="fade-up" style="animation-delay:{150 + i * 70}ms">'
        f'<span class="tmi-num">{esc(c.get("num"))}</span>'
        f'<h3 class="tmi-row-title">{esc(shrink_toc_magazine_title(c.get("title")))}</h3>'
        f'<span class="tmi-leader" aria-hidden="true"></span>'
        f'<span class="tmi-page">{i + 1:02d}</span>'
        f'</div>'
        for i, c in enumerate(cards)
    )
    return (
        f'<div class="toc-magazine-index">'
        f'<div class="tmi-head" data-animate="fade-up">'
        f'<p class="tmi-eyebrow">CONTENTS</p>'
        f'<h1 class="tmi-title-main">{main_title}</h1>'
        f'</div>'
        f'<div class="tmi-rule"></div>'
        f'<div class="tmi-list">{row_html}</div>'
        f'</div>'
    )


# ── TASK-041: toc-collage-asym —— 非对称拼贴式目录（目录页调度精简新增） ──
# 背景：toc-modern-card/toc-segment-strip/toc-grid-matrix 三款诊断确认本质
# 都是"编号+标题+一句描述"套不同卡片容器形状，尺寸/信息结构完全同质（同一批
# 卡片彼此等大，只是外壳形状不同），toc-orbit-hub（中心枢纽环形）与
# toc-magazine-index（纯文字索引）才是真正结构不同的两款。本版式补一种库里
# 从未出现过的"尺寸不对称"结构语言：第 1 个章节（数据里排在最前、通常也是
# 全篇最重要的开篇/总纲）放大为一张占据左侧约 58% 宽度、纵向占满全部可用
# 高度的"头条卡"（.tca-headline，含编号+标题+一句话说明，字号/留白都明显
# 大于其余条目）；其余 N-1 个章节收进右侧纵向排列的紧凑编号短条列表
# （.tca-list > .tca-row，仅编号+标题单行，不放描述，突出"短条"的克制感）。
# 这种"一大+多小"的拼贴构图是版式库里独有的，不是同款卡片换容器皮。
#
# 通用 N 版式做法（与 toc_orbit_hub_html/toc_grid_matrix_html 同一原则，
# 禁止硬编码坐标表）：头条卡与列表都是纯 flex 布局——头条卡 flex:0 0 58%
# 自动占满 tca-body 的全部高度（不随 N 变化，只随头部区域高度变化）；列表
# 内 N-1 个短条各 flex:1 1 0，由浏览器按可用高度自动等分，天然适配 N=3~8
# （N=3 时短条更宽裕、N=8 时更紧凑，均由 flex 计算，不是 Python 侧按 N 查表
# 分支出不同像素值）。
TOC_COLLAGE_HEADLINE_TITLE_MAXLEN = 18
TOC_COLLAGE_ROW_TITLE_MAXLEN = 12


def shrink_toc_collage_headline_title(title, max_chars=TOC_COLLAGE_HEADLINE_TITLE_MAXLEN):
    return shrink_toc_plaque_title(title, max_chars)


def shrink_toc_collage_row_title(title, max_chars=TOC_COLLAGE_ROW_TITLE_MAXLEN):
    return shrink_toc_plaque_title(title, max_chars)


def toc_collage_asym_html(cards, main_title, fallback_html):
    """toc 角色可选渲染版式（TASK-041 新增）：非对称拼贴式目录
    （slide_templates/toc/toc-collage-asym.html 预览版接入，样式见
    assets/components/toc-collage-asym.css）。顶部主标题头（同其余版式一致
    的 CONTENTS eyebrow + h1）之下，左侧一张放大的"头条卡"承载第 1 个章节
    （编号+标题+一句话说明），右侧纵向排列其余章节的紧凑编号短条（仅编号+
    标题，不放描述）。适合希望"点出全篇最重要的开篇章节、其余章节收敛为
    索引"的叙事型 deck（人文温暖/非遗类项目见 select_toc_template()）。
    防溢出三层机制：① Python 侧标题精简（头条卡 18 字阈值、短条 12 字阈值，
    复用 shrink_toc_plaque_title 同一套"冒号截取优先、仍超阈值硬截断补省略号"
    算法）；② CSS 侧 -webkit-line-clamp 双重兜底（头条标题/说明各 3 行，
    短条标题 1 行）；③ 头条卡固定 flex:0 0 58% 占满 tca-body 全高，短条组
    内 flex:1 1 0 统一等分高度（并列容器尺寸一致纪律，纳入
    qa_render.py::check_sibling_uniformity 的 .tca-list>.tca-row 核验）——
    头条卡与短条本就设计为不同尺寸（非对称是本版式的核心视觉语言），一致性
    约束只用于"同一批短条彼此之间"，不要求头条卡也跟短条同高。
    cards 为空时退回旧版列表渲染，保证目录页不会因缺数据而空白。
    """
    if not cards:
        return f'<div class="watermark-word">AGENDA</div><h2>{main_title}</h2>{fallback_html}'
    headline, rest = cards[0], cards[1:]
    row_html = "".join(
        f'<div class="tca-row" data-idx="{i + 2}" data-animate="fade-up" style="animation-delay:{260 + i * 70}ms">'
        f'<span class="tca-row-ghost" aria-hidden="true">{esc(c.get("num"))}</span>'
        f'<span class="tca-row-num">{esc(c.get("num"))}</span>'
        f'<h3 class="tca-row-title">{esc(shrink_toc_collage_row_title(c.get("title")))}</h3>'
        f'</div>'
        for i, c in enumerate(rest)
    )
    headline_html = (
        f'<div class="tca-headline" data-idx="1" data-animate="fade-up" style="animation-delay:150ms">'
        f'<span class="tca-headline-ghost" aria-hidden="true">{esc(headline.get("num"))}</span>'
        f'<span class="tca-headline-num">{esc(headline.get("num"))}</span>'
        f'<h2 class="tca-headline-title">{esc(shrink_toc_collage_headline_title(headline.get("title")))}</h2>'
        f'<p class="tca-headline-desc">{esc(headline.get("desc"))}</p>'
        f'</div>'
    )
    return (
        f'<div class="toc-collage-asym">'
        f'<div class="tca-head" data-animate="fade-up"><p class="tca-eyebrow">CONTENTS</p>'
        f'<h1 class="tca-title-main">{main_title}</h1></div>'
        f'<div class="tca-body">{headline_html}<div class="tca-list">{row_html}</div></div>'
        f'</div>'
    )


# ── TASK-041: 目录页调度精简——按项目主题域挑选目录版式 ────────────────────
# 背景：此前 role=="toc" 分支是"代码维护层面的手动开关"，全库所有项目固定
# 调用同一个函数，导致不同主题的项目目录页趋同。THEME_DOMAINS.md 已把项目
# 主题判定成"8 类 domain + 1 兜底"的地基层（scripts/classify_theme_domain.py
# 产出 state/theme_domain.json），本函数消费其 domain 字段作为目录版式选择
# 的第一优先级输入，取代手动开关。
#
# 调度面精简：toc-modern-card/toc-segment-strip 诊断确认与 toc-grid-matrix
# 本质同质（同款卡片换容器皮），不再进入调度候选（函数保留，仅供以后按场景
# 手动切回）；实际参与调度的 4 款为 toc-orbit-hub（环形辐射，深色科技感）/
# toc-magazine-index（纯文字索引，克制正式）/ toc-grid-matrix（卡片网格，
# 通用默认代表款，compute_grid_columns(N) 条目数自适应）/
# toc-collage-asym（非对称拼贴，头条大卡+紧凑短条列表，叙事感）。
#
# node_count 只在同一 domain 存在多款候选时起二级细分作用（本表内目前只有
# consumer-lifestyle-future 一个 domain 映射两款候选：条目数较多时更适合
# toc-orbit-hub 的环形铺陈展示丰富度，条目数较少时更适合 toc-collage-asym
# 的"聚焦头条章节"叙事感），不是第一优先级，其余 domain 均为单一映射。
TOC_TEMPLATE_DOMAIN_MAP = {
    "aerospace-defense-tech": "toc-orbit-hub",
    "academic-institutional": "toc-magazine-index",
    "corporate-professional": "toc-magazine-index",
    "cultural-heritage-formal": "toc-magazine-index",
    "product-launch-design": "toc-grid-matrix",
    "cultural-heritage-warm": "toc-collage-asym",
    # consumer-lifestyle-future 由 select_toc_template() 按 node_count 二级细分，不在此表登记单一值
    "generic-fallback": "toc-grid-matrix",
}

TOC_TEMPLATE_FUNCS = {
    "toc-modern-card": toc_modern_card_html,
    "toc-segment-strip": toc_segment_strip_html,
    "toc-orbit-hub": toc_orbit_hub_html,
    "toc-grid-matrix": toc_grid_matrix_html,
    "toc-magazine-index": toc_magazine_index_html,
    "toc-collage-asym": toc_collage_asym_html,
}

# consumer-lifestyle-future 的二级细分阈值：条目数达到该值时选 toc-orbit-hub
# （环形节点更多时视觉更丰富、沉浸感更强），低于该值时选 toc-collage-asym
# （头条卡在章节更少时更能突出"聚焦开篇"的叙事效果，避免右侧短条列表在
# 章节很多时显得比头条卡拥挤）。
CONSUMER_FUTURE_ORBIT_THRESHOLD = 6


def select_toc_template(domain, node_count=None):
    """按项目主题域（domain）挑选目录页版式 key（TOC_TEMPLATE_FUNCS 的键之一）。
    domain 通常来自 state/theme_domain.json 的 "domain" 字段（见 --theme-domain
    参数与 main() 里的读取逻辑）；domain 为空/未知/不在映射表内时一律兜底为
    generic-fallback 的选择（toc-grid-matrix），不报错。node_count 为该 deck
    目录条目数，仅在 domain 存在多款候选时起二级细分作用（见上方
    CONSUMER_FUTURE_ORBIT_THRESHOLD），不是第一优先级。
    """
    domain = domain if domain in TOC_TEMPLATE_DOMAIN_MAP or domain == "consumer-lifestyle-future" else "generic-fallback"
    if domain == "consumer-lifestyle-future":
        n = int(node_count) if node_count else 0
        return "toc-orbit-hub" if n >= CONSUMER_FUTURE_ORBIT_THRESHOLD else "toc-collage-asym"
    return TOC_TEMPLATE_DOMAIN_MAP.get(domain, "toc-grid-matrix")


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


# TASK-021 B.2: data-autofit 标记注入——标题/正文列表/分组卡片/takeaway 容器打标记，
# 供 autofit.js 迭代降字号；用整页 HTML 的正则后处理而非逐角色分支手改，因为这些
# 容器的开标签在十余个 role 分支里散落生成，正则一次性覆盖更不易漏标/不易出错。
_AUTOFIT_RULES = (
    (re.compile(r"<h1(?=[ >])"), "title"),
    (re.compile(r"<h2(?=[ >])"), "title"),
    (re.compile(r'<div class="takeaway"'), "body"),
    (re.compile(r'<div class="panel group-card"'), "body"),
    (re.compile(r'<ul class="content-list(?=["\s])'), "body"),
)


def apply_autofit_markers(doc_html):
    for pat, kind in _AUTOFIT_RULES:
        doc_html = pat.sub(lambda m, k=kind: m.group(0) + f' data-autofit="{k}"', doc_html)
    return doc_html


# ── TASK-030: 内容页主题插画通用兜底机制 ─────────────────────────────────
# 背景：TASK-028 的主题线条插画（rocket-ascent/cloud-swirl/... 这类从项目图
# 提炼出的可识别图形）此前只允许出现在骨架页（cover/section/toc/closing），
# 原因是骨架页天然留白大、内容页信息密度高，贸然照搬同一套"按 role 静态匹配
# 素材"的机制会有遮挡风险。用户明确要求把封面这种插画效果推广到"每一个
# 页面"。内容页与骨架页的关键差异是：同一个 role（如 bullets/kpi）会跨越
# 全部章节反复出现，静态"role -> 素材"映射无法区分"这一页具体在讲什么"，
# 因此内容页改用与骨架页完全不同的动态选择算法（见 select_content_motif），
# 而不是简单放宽骨架页那张白名单。
#
# 角色 -> 呈现参数表：逐页截图核对当前项目 24 页版式后归纳出两类版式，不是
# 拍脑袋数值——
#   ① 网格铺满型（gallery：5 张图铺满全屏，任何一角都可能被卡片占满，没有
#      稳定留白角）：改用星尘素材同款"整页低透明度纹理"（motif-pos-full），
#      透明度压到骨架页的三分之一左右；纹理本身弥散不成形，被卡片盖住的
#      部分自然不可见，不存在"插画正好贴在卡片轮廓上"的风险。
#   ② 留白角落型（其余角色）：单体角标插画，尺寸压到骨架页的三分之一左右、
#      透明度也再调低，具体放哪一角按版式结构定：
#      - 右侧带独立可视化面板的角色（image-hero/image-side/two-column/
#        compare：正文在左、图或面板在右）→ 放左下角，避开右侧可视化区；
#        这几个角色的正文列表条目数固定（本项目均为 4 条），不会像纯卡片
#        角色那样堆叠到贴近页面底边，左下角实测截图确认长期留空。
#      - 纯正文/卡片角色（bullets/kpi/table/timeline/quote）→ 放右上角
#        （而不是右下角）。初版曾用右下角，逐页截图复核时发现 bullets 角色
#        的卡片数量取决于 deck.md 正文条目数、不像 image-hero 系那样固定，
#        条目一多就会堆成多行卡片一路顶到页面底边（本项目"数字孪生"页 4
#        张卡片堆叠，右下角插画的火箭鼻锥被卡片右边缘越出可见区域切穿，
#        判定为真实碰撞，见交付记录截图）——右下角的"留白"其实是"当前这页
#        恰好卡片不多"的偶然结果，不是版式结构保证。标题栏（slide-head）
#        高度只取决于标题字数（有上限截断），与正文条目数无关，是唯一在
#        全部纯正文/卡片角色页面里都结构性保证留白的角落，正文卡片/表格/
#        列表在 DOM 顺序上必然排在标题之后、不会侵入标题行的留白区，因此
#        改用右上角作为通用安全位。
CONTENT_MOTIF_LAYOUT = {
    "gallery": {"position": "motif-pos-full", "opacity_cap": 0.05, "size": None},
    "kpi": {"position": "motif-pos-tr", "opacity_cap": 0.06, "size": 100},
    "table": {"position": "motif-pos-tr", "opacity_cap": 0.06, "size": 100},
    "bullets": {"position": "motif-pos-tr", "opacity_cap": 0.06, "size": 100},
    "timeline": {"position": "motif-pos-tr", "opacity_cap": 0.06, "size": 100},
    "quote": {"position": "motif-pos-tr", "opacity_cap": 0.06, "size": 100},
    "image-hero": {"position": "motif-pos-bl", "opacity_cap": 0.055, "size": 100},
    "image-side": {"position": "motif-pos-bl", "opacity_cap": 0.055, "size": 100},
    "two-column": {"position": "motif-pos-bl", "opacity_cap": 0.055, "size": 100},
    "compare": {"position": "motif-pos-bl", "opacity_cap": 0.055, "size": 100},
}


def _slide_text_for_motif(slide):
    """拼出这一页用于关键词打分的纯文本：标题 + 章节名 + 全部正文段落/列表项。"""
    parts = [str(slide.get("title") or ""), str(slide.get("section") or "")]
    for b in slide.get("blocks", []):
        if b.get("text"):
            parts.append(str(b["text"]))
        for item in (b.get("items") or []):
            parts.append(str(item))
    return " ".join(parts)


def select_content_motif(slide, assets):
    """内容页素材选择：按本页文本命中每条素材 content_keywords 的次数打分，
    命中最多的素材胜出（同分取 art_motifs.json 里登记顺序靠前的一个，保持
    确定性、可复现，不引入随机数）。content_keywords 是项目侧登记的、有明确
    出处的触发词（见 state/art_motifs.json 的 _content_keywords_rationale
    字段），不是脚本自己猜的。

    全部素材都 0 命中（本页文本恰好不含任何触发词，或项目没登记
    content_keywords）时，按页码对素材数量取模做确定性轮换兜底——保证内容页
    也能用上全部素材、且同一份稿子重复渲染结果完全一致。
    """
    if not assets:
        return None
    text = _slide_text_for_motif(slide)
    best_idx, best_score = 0, -1
    for i, a in enumerate(assets):
        score = sum(text.count(k) for k in (a.get("content_keywords") or []) if k)
        if score > best_score:
            best_idx, best_score = i, score
    if best_score <= 0:
        best_idx = int(slide.get("page") or 0) % len(assets)
    return assets[best_idx]


def slide_html(slide, section_titles=None, art_dna=None, theme_domain=None):
    role = slide.get("role")
    title = esc(slide.get("title"))
    blocks = blocks_html(slide, ordered=is_ordered_content(slide))
    images = slide.get("images", [])
    notes = notes_html(slide)
    takeaway = "" if role in {"cover", "section", "closing"} else takeaway_html(slide)
    # TASK-021 A.3: role 本身没有内建 .copy/.visual 12 列栅格时（如 bullets 命中
    # split 族变体），补一个显式 layout-split 类强制栅格——:has() 的 Python 侧双保险。
    need_split_grid = False
    # TASK-009: 视觉蓝图落版——layout 变体类与追溯数据属性（样式由 assets/components/layouts.css 承载）
    layout_variant = (slide.get("layout_variant") or "").strip()
    # TASK-024 fix（终审 D1 命中修复）：normalize_layout_variant() 对
    # hero-left-info-right/hero-right-info-left/details-3/kpi-4col/gallery-5/
    # table-5x4 等"角色原生变体"（common.py _VARIANT_ALIASES 显式设计为
    # 归一到 ""，交由角色默认渲染承接）会把 layout_variant 清空，导致
    # data-variant 属性也随之清空——这些原始变体名因此彻底没有任何 CSS 钩子
    # 可用，同一角色下不同变体（如 image-hero 的图左/图右镜像）渲染成完全
    # 相同的四元组（标题位置×内容区切分×焦点位置×模块节奏），命中
    # html-layout-system.md §9 deck 结构配额（本项目 P7/P8/P10 三页曾撞车）。
    # data-variant 改为优先取归一 slug、归一为空时回退原始变体名，只新增
    # CSS 可选中的钩子，不改变既有 layout-{slug} class 的判定逻辑（仍只用
    # 归一后的 23 词表 slug），不影响其它页面已验证的渲染。
    layout_variant_raw = (slide.get("layout_variant_raw") or "").strip()
    data_variant = layout_variant or layout_variant_raw
    layout_pattern = (slide.get("layout_pattern") or "").strip()
    layout_cls = f" layout-{esc(layout_variant)}" if layout_variant else ""
    common = f'data-role="{esc(role)}" data-page="{slide.get("page")}"'
    if layout_pattern:
        common += f' data-pattern="{esc(layout_pattern)}" data-variant="{esc(data_variant)}"'
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
        # TASK-028/TASK-030: 主题线条插画装饰层——两条路径二选一，按 role 是否被
        # 项目显式登记过区分：
        # ① 显式登记（art_motifs.json 某条素材的 roles 里直接写了这个 role，
        #    骨架页 cover/section/toc/closing 的既有用法就是这样）——原样按登记
        #    的位置/透明度/尺寸渲染，允许同一页叠多个素材（如封面同时叠"火箭"+
        #    "星尘"，这是已验证过的效果，不因本轮改动而改变）。
        # ② 未显式登记（绝大多数项目的内容页角色，没有也不需要逐条手写）——
        #    落到 CONTENT_MOTIF_LAYOUT 通用兜底：按 select_content_motif() 的
        #    关键词打分自动选 1 个素材，用远低于骨架页的透明度/尺寸和避开正文
        #    的角落位置渲染，见该常量表与函数上方的长注释。
        assets = (art_dna.get("motifs") or {}).get("assets", [])
        explicit = [m for m in assets if role in (m.get("roles") or []) and m.get("_inline_svg")]
        motif_html = ""
        if explicit:
            for m in explicit:
                motif_html += (
                    f'<div class="project-art-motif {esc(m.get("position"))}" '
                    f'style="--motif-size:{int(m.get("size", 320))}px;opacity:{float(m.get("opacity", 0.14))}" '
                    f'aria-hidden="true">{m["_inline_svg"]}</div>'
                )
        elif role in CONTENT_MOTIF_LAYOUT and assets:
            chosen = select_content_motif(slide, assets)
            svg_inline = chosen.get("_inline_svg") if chosen else None
            if svg_inline:
                layout = CONTENT_MOTIF_LAYOUT[role]
                size = layout["size"] or chosen.get("size", 320)
                opacity = min(float(chosen.get("opacity", 0.14)), layout["opacity_cap"])
                motif_html = (
                    f'<div class="project-art-motif {layout["position"]}" '
                    f'style="--motif-size:{int(size)}px;opacity:{opacity:.3f}" '
                    f'aria-hidden="true">{svg_inline}</div>'
                )
        art_layer = (
            f'<div class="project-art-frame">'
            f'<img class="project-art-bg project-art-{esc(role)}" src="{esc(art_dna.get(key))}" alt="" aria-hidden="true">'
            f'{motif_html}'
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
        # TASK-041：从"代码维护层面的手动开关"改为按项目主题域自动调度——
        # select_toc_template() 消费 theme_domain（main() 从 --theme-domain 指向
        # 的 state/theme_domain.json 读取，缺省时兜底 generic-fallback），
        # 结合本页目录条目数做（至多）二级细分，选出目录版式 key 后从
        # TOC_TEMPLATE_FUNCS 取出对应渲染函数。所有 6 个 toc_*_html 函数仍
        # 保留在代码里未删除，只是不再全部参与调度（toc-modern-card/
        # toc-segment-strip 降级为仅供手动切回的历史兼容款，详见
        # SKILL.md「目录页版式模板库」一节）。
        toc_cards = slide.get("toc_cards") or []
        toc_template_key = select_toc_template(theme_domain, len(toc_cards))
        toc_render_fn = TOC_TEMPLATE_FUNCS.get(toc_template_key, toc_grid_matrix_html)
        inner = f'{art_layer}{toc_render_fn(toc_cards, title, blocks)}'
    elif role == "section":
        inner = f'{art_layer}<div class="outline-number">{str(slide.get("section_index") or slide.get("page")).zfill(2)}</div><div class="eyebrow">Section</div><h2 data-animate="blur-in">{title}</h2><div class="deckline" data-animate="path-draw"></div>'
    elif role == "image-hero":
        # TASK-021 A.2: 有真实语义分组时把正文升级为分组卡片，图片保持不变——
        # 变体为空或页面语义登记为不分组的段落叙事页（本项目多数 image-hero 页）
        # 时 rv["mode"] 为 None，保留原有 hero-copy 段落渲染，不强行套壳。
        # TASK-021 A.4：三段式骨架试点——标题独立进 slide-head，hero 双栏进
        # slide-body，takeaway 进 slide-foot，取代原先"标题嵌在 hero-copy 内、
        # takeaway 靠 role-image-hero>.takeaway{grid-row:3} 隐式定位"的写法。
        groups = slide.get("groups") or []
        rv = render_variant_body(slide, layout_variant, layout_pattern, groups, images)
        im = img_html(images[0] if images else None, "image-frame hero-image", "contain")
        extra = f'<div class="group-stack">{rv["left"]}</div>' if rv["mode"] == "split" and groups else ""
        # TASK-025 fix（全局排查同类问题）: rv["mode"]=="split" 时 extra 已经把
        # 语义分组渲染成独立卡片（group-stack），这些卡片的数据源就是正文列表
        # 条目；此前 hero-copy 仍然用 {blocks}（含完整列表）打底，卡片和列表原文
        # 同时出现，重复了一遍——与 kpi/gallery 是同一根因（见
        # references/page-logic-patterns.md §17.7）。extra 为空（无分组/非
        # split）时不受影响，仍保留完整正文。
        hero_copy_body = non_list_blocks_html(slide) if extra else blocks
        inner = (
            f'{art_layer}<div class="slide-head"><h2>{title}</h2></div>'
            f'<div class="slide-body"><div class="hero-copy">{hero_copy_body}{extra}</div><div class="hero-visual">{im}</div></div>'
            f'<div class="slide-foot">{takeaway}</div>'
        )
    elif role == "image-side":
        # TASK-021 A.2: image-side 的容器天生就是 .copy/.visual，split 族变体的
        # CSS（如 layout-anchor-right 的 5:7 非对称分栏 + 描边）通过 layout_cls
        # 已经无条件生效；有真实分组登记时进一步把正文重组为分组卡片。
        groups = slide.get("groups") or []
        rv = render_variant_body(slide, layout_variant, layout_pattern, groups, images)
        if rv["mode"] == "split" and groups:
            inner = f'{art_layer}<div class="copy"><h2>{title}</h2>{non_list_blocks_html(slide)}{rv["left"]}</div><div class="visual">{rv["right"] or img_html(images[0] if images else None, "image-frame side-image", "contain")}</div>{takeaway}'
        else:
            im = img_html(images[0] if images else None, "image-frame side-image", "contain")
            inner = f'{art_layer}<div class="copy"><h2>{title}</h2>{blocks}</div><div class="visual">{im}</div>{takeaway}'
    elif role == "gallery":
        # TASK-025 fix: 此前 frames（图片阵列）与 blocks（含完整正文列表）各自
        # 承载同一批"每款风格是什么"的信息，页面上先读一遍列表原文，再读一遍
        # 每张图自己的说明，纯属重复堆砌（见 references/page-logic-patterns.md
        # §17.7）。列表条目已被解析消费——核心风格短语提炼进对应图片的
        # caption-bar（img_html caption_override），正文只保留非列表段落（导语
        # 总起句），不再逐条复述每张图。
        gallery_list_items = list_items_of(slide)
        frames = "".join(
            img_html(
                img, "image-frame", "contain", i + 1,
                caption_override=gallery_style_tag(gallery_list_items[i]) if i < len(gallery_list_items) else None,
            )
            for i, img in enumerate(images[:6])
        )
        grid_cls = "gallery-grid" + (" gallery-small" if len(images[:6]) <= 3 else "")
        # TASK-022 fix: 导语段落包一层 .gallery-copy，与 role-gallery 网格合并成
        # 单个 row-2 item，不再挤占 gallery-grid 的行位导致视觉重叠（详见
        # base.css .role-gallery 注释）。
        inner = f'{art_layer}<h2>{title}</h2><div class="gallery-copy">{non_list_blocks_html(slide)}</div><div class="{grid_cls}">{frames}</div>{takeaway}'
    elif role == "two-column":
        # TASK-021 A.2: grid/chain/loop/hub/vs-split/cause-effect/layers/gather-3/
        # hub-top/hub-spoke/num-anchor/checkpoint-3/ed-strip/ascend-4 全部解耦到
        # render_variant_body 共享出口；未命中时保留原有纯文本左右分栏兜底。
        groups = slide.get("groups") or []
        rv = render_variant_body(slide, layout_variant, layout_pattern, groups, images)
        if rv["mode"] == "single":
            inner = f'{art_layer}<h2>{title}</h2>{non_list_blocks_html(slide)}{rv["single"]}{takeaway}'
        elif rv["mode"] == "split":
            # layers-N 等单列级联变体故意返回空 right（见 render_variant_body），
            # 此时不渲染 .visual 面板——否则会在页面右下角留一个内容为空、却仍有
            # 内边距/描边的"幽灵面板"（无来源视觉噪音）；layers-N 的 .copy 本身已
            # 由 layout-layers 专属 CSS 强制 grid-column:1/-1 通栏，无需 .visual 补位。
            visual_html = f'<div class="visual panel" style="padding:34px">{rv["right"]}</div>' if rv["right"] else ""
            inner = (
                f'{art_layer}<div class="copy"><h2>{title}</h2>{non_list_blocks_html(slide)}{rv["left"]}</div>'
                f'{visual_html}{takeaway}'
            )
        else:
            parts = slide.get("blocks", [])
            left = "\n".join(block_html(b) for b in parts[::2]) or blocks
            right = "\n".join(block_html(b) for b in parts[1::2]) or (img_html(images[0], "image-frame side-image", "contain") if images else "")
            inner = f'{art_layer}<div class="copy"><h2>{title}</h2>{left}</div><div class="visual panel" style="padding:34px">{right}</div>{takeaway}'
    elif role == "table":
        # TASK-027 fix: 原先 h2/blocks/takeaway 是三个 flat 直接子元素，容器
        # `align-content:start` 顶部对齐，表格本身高度固定、不会随画布拉伸，
        # 底部留出大片不协调空白（用户反馈"没有图片的情况下要让内容填充完整
        # 页面"，P16 表格页即此问题）。改用 bullets/image-hero 已验证的三段式
        # 骨架（slide-head 标题固定顶部 + slide-body 用 flex 纵向居中承载表格
        # 与导语/结论段落 + slide-foot 承载 takeaway），标题位置不变，表格作为
        # 一个整体在标题下方的剩余空间里居中，不再顶部对齐留白在底部。
        inner = (
            f'{art_layer}<div class="slide-head"><h2>{title}</h2></div>'
            f'<div class="slide-body">{blocks}</div>'
            f'<div class="slide-foot">{takeaway}</div>'
        )
    elif role == "kpi":
        # TASK-024 fix（终审 C1 命中修复）：旧实现无差别套用"目标对比/同比变化/
        # 过程效率/业务影响"+"含目标/同比/基准上下文"这套仅适配"对比型"KPI
        # （有目标值/同比/行业基准）的通用标签，对纯事实性数字（规模/规格/年份
        # 等，无目标或基准可对比）会产出与当页语义无关的模板腔文字，命中
        # final-quality-check.md C1。现在优先从"标签：口径内容"格式的正文条目
        # 自带标签与口径渲染；条目不带分隔符（如"续约率达到94%…超过85%目标线"
        # 这类连续对比句，example 项目即此写法）时保留旧的通用兜底，不影响其他
        # 已验证项目的渲染效果。
        nums = []
        list_items = []
        for b in slide.get("blocks", []):
            if b.get("type") == "list":
                list_items.extend(b.get("items", []))
        text = " ".join(str(b.get("text", "")) + " ".join(b.get("items", [])) for b in slide.get("blocks", []))
        labels_fallback = ["目标对比", "同比变化", "过程效率", "业务影响"]
        cards = []
        for item in list_items[:4]:
            sep = "：" if "：" in item else (":" if ":" in item else None)
            if not sep:
                continue
            label, rest = item.split(sep, 1)
            m = re.search(r"(\d+)([%x倍天分]?)", rest)
            if not m:
                continue
            raw_note = re.sub(r"\s+", "", rest[:m.start()] + rest[m.end():]).strip("，,。、")
            note = (raw_note[:16] + "…") if len(raw_note) > 16 else (raw_note or "关键事实口径")
            cards.append((m.group(1), m.group(2), label.strip()[:8] or "核心数字", note))
        if not cards:
            found = re.findall(r"(\d+)([%x倍天分]?)", text)[:4] or [("94", "%"), ("38", "%"), ("12", "天"), ("4", "倍")]
            cards = [(n, suffix, labels_fallback[i % len(labels_fallback)], "含目标/同比/基准上下文") for i, (n, suffix) in enumerate(found)]
        for i, (n, suffix, label, note) in enumerate(cards):
            nums.append(f'<div class="panel kpi-card" data-animate="zoom-pop" style="--i:{i}"><div class="kpi-number" data-animate="count-up" data-count-to="{esc(n)}" data-suffix="{esc(suffix)}">{esc(n)}{esc(suffix)}</div><p>{esc(label)}</p><small>{esc(note)}</small></div>')
        # TASK-025 fix: 此前用 {blocks}（含完整正文列表）+ kpi-grid 同时渲染——
        # 列表条目已经是上面 nums 大数字卡片的数据来源，二者同时出现即同一批
        # 数字先读一遍文字版、再读一遍卡片版，纯属重复堆砌（见
        # references/page-logic-patterns.md §17.7）。改为只保留导语一句话
        # （kpi_lead_html 裁到首句），数字卡片才是本页视觉焦点。
        # TASK-027 fix: 同 role=="table" 的问题——kpi-grid 高度固定（4 张卡片
        # 一行），旧写法顶部对齐后底部空出画布近一半高度（用户点名 P4 举例）。
        # 改用三段式骨架，导语 + kpi-grid 一起落进 slide-body，靠 flex 纵向
        # 居中吃满标题下方的剩余空间；kpi-card/kpi-number 尺寸同步放大（见
        # base.css .kpi-card/.kpi-number），让数字本身的视觉体量配得上整块
        # 居中后空出来的画布，而不是小卡片漂在大留白正中间。
        inner = (
            f'{art_layer}<div class="slide-head"><h2>{title}</h2></div>'
            f'<div class="slide-body">{kpi_lead_html(slide)}<div class="kpi-grid">{"".join(nums)}</div></div>'
            f'<div class="slide-foot">{takeaway}</div>'
        )
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
        cards = "".join(f'<div class="panel timeline-item" style="--i:{i}"><div class="date">{esc(item.split("｜")[0] if "｜" in item else "T+" + str(i+1))}</div><p>{esc_hl(item)}</p></div>' for i, item in enumerate(items[:6]))
        # TASK-024 fix（终审 C1 复核发现）：此前 inner 模板没有拼 blocks/
        # non_list_blocks_html，role=timeline 页面正文里任何段落（导语句、卡片
        # 之外的补充说明，如本项目 P9 的"测控网络由陆上测控站…共同覆盖"）会被
        # 静默丢弃——deck.md 里明明写了这句话，渲染结果却从未出现过。改为拼上
        # non_list_blocks_html（只取非列表块，列表条目已经由 cards 承载，不重复）。
        inner = f'<h2>{title}</h2>{non_list_blocks_html(slide)}<div class="timeline-row">{cards}</div>{takeaway}'
    elif role == "closing":
        eyebrow = esc(slide.get("eyebrow") or "NEXT STEP · 落地行动")
        echo = slide.get("echo")
        echo_html = ""
        if echo:
            # TASK-021（测试发现）：此前硬编码 "HONOR GALLERY · CONCEPT PROPOSAL" 是
            # 某个具体历史项目（荣誉展廊/概念方案类）遗留的水印文案，closing_slide()
            # 从不显式设置 echo_sub，导致每个新项目的尾页都会原样带出这句与当前项目
            # 主题完全无关的英文水印——命中 page-logic-patterns.md §17.5「水印字/
            # eyebrow/meta-line 必须与当页主题一致，禁止无意义词」。改为与 eyebrow
            # 默认值同款的中性双语标签，不预设任何具体项目语境。
            echo_sub = esc(slide.get("echo_sub") or "SUMMARY · 主题回顾")
            echo_html = f'<div class="closing-echo" data-animate="fade-up">{esc(echo)}<small>{echo_sub}</small></div>'
        art_bg = art_layer
        inner = f'{art_bg}<canvas class="fx-canvas" width="1920" height="1080"></canvas>{"" if art_dna else closing_deco()}<div class="watermark-word">NEXT</div><div class="eyebrow">{eyebrow}</div><h2>{title}</h2>{blocks}{takeaway}{echo_html}'  # TASK-017 fix: 尾页恢复生成式融合背景，仅无 art DNA 时降级经典 deco
    else:
        # TASK-021 A.2+A.4: bullets 等兜底 role 同样先尝试 render_variant_body——
        # 典型场景：closing 内容型降级来的行动页（ascend-4 等序列变体，此前只会
        # 落成"标题+竖排列表"，是本轮整改要修的核心退化场景之一）。三段式骨架
        # 试点同时落地：标题进 slide-head，结构化正文进 slide-body，takeaway 进
        # slide-foot，取代隐式子元素顺序定位。
        groups = slide.get("groups") or []
        rv = render_variant_body(slide, layout_variant, layout_pattern, groups, images)
        if rv["mode"] == "single":
            body = f'{non_list_blocks_html(slide)}{rv["single"]}'
        elif rv["mode"] == "split":
            need_split_grid = True
            # 同 role=="two-column" 分支：layers-N 故意返回空 right，不渲染空 .visual 幽灵面板。
            visual_html = f'<div class="visual panel" style="padding:34px">{rv["right"]}</div>' if rv["right"] else ""
            body = (
                f'<div class="copy">{non_list_blocks_html(slide)}{rv["left"]}</div>'
                f'{visual_html}'
            )
        elif groups:
            # TASK-003: 登记分组但无匹配变体时，仍渲染为独立卡片栅格
            cards = "".join(group_card_html(g, i) for i, g in enumerate(groups))
            body = f'{non_list_blocks_html(slide)}<div class="group-grid">{cards}</div>'
        else:
            body = blocks
        inner = (
            f'{art_layer}<div class="slide-head"><h2>{title}</h2></div>'
            f'<div class="slide-body">{body}</div>'
            f'<div class="slide-foot">{takeaway}</div>'
        )
    if art_layer and art_layer not in inner:
        inner = art_layer + inner
    split_cls = " layout-split" if need_split_grid and role not in {"two-column", "image-side", "compare"} else ""
    return f'<section class="slide role-{role}{layout_cls}{split_cls}" {common}>{quiet}{inner}{notes}</section>'


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
        asset_text("assets", "components", "motifs.css"),  # TASK-028: 主题线条插画装饰层通用外壳样式
        asset_text("assets", "components", "layouts.css"),  # TASK-009: 视觉蓝图 layout-* 变体样式
        asset_text("assets", "components", "toc-modern-card.css"),  # 旧版目录模板样式，保留以便回退，当前未激活使用
        asset_text("assets", "components", "toc-segment-strip.css"),  # 目录可选版式：分栏满版色块，深色海报风，当前未激活使用
        asset_text("assets", "components", "toc-orbit-hub.css"),  # TASK-032: toc 角色（当前激活）：中心枢纽+环形卫星节点，深色科技风
        asset_text("assets", "components", "toc-grid-matrix.css"),  # TASK-036/041: 目录调度候选：卡片网格类默认代表款，条目数自适应
        asset_text("assets", "components", "toc-magazine-index.css"),  # TASK-036/041: 目录调度候选：极简书目录风，克制正式类 domain 默认
        asset_text("assets", "components", "toc-collage-asym.css"),  # TASK-041: 目录调度候选：非对称拼贴式（头条大卡+紧凑短条列表）
    ])
    if args.theme_css and Path(args.theme_css).exists():
        css += "\n" + Path(args.theme_css).read_text(encoding="utf-8")
    js = asset_text("assets", "runtime", "runtime.js").replace("</script>", "<\\/script>")
    # TASK-021 B.2: 自适应字号收缩脚本，与 runtime.js 走同样的"读文件内容直接拼进
    # <script>"机制——inline_assets.py 只处理图片 base64，不碰脚本。
    autofit_js = asset_text("assets", "runtime", "autofit.js").replace("</script>", "<\\/script>")
    # TASK-022: 内嵌可视化编辑器（右侧面板调字号/微移位置，E 键切换编辑态），
    # 同样走"读文件内容直接拼进 <script>"机制。必须放在 autofit_js 之后，
    # 保证 editor.js 执行时 window.__deckAutofitRefit 已经就绪。
    editor_js = asset_text("assets", "runtime", "editor.js").replace("</script>", "<\\/script>")
    section_titles = [str(s.get("title")) for s in slides if s.get("role") == "section" and s.get("title")]
    # TASK-041: 读取 classify_theme_domain.py 产出的 domain，供 select_toc_template()
    # 挑选目录页版式；--theme-domain 未传或文件不存在/解析失败时一律兜底为
    # generic-fallback，不中断整个渲染流程（目录页仍会走 toc-grid-matrix 默认）。
    theme_domain = "generic-fallback"
    if args.theme_domain:
        theme_domain_path = Path(args.theme_domain)
        if theme_domain_path.exists():
            try:
                theme_domain_data = read_json(theme_domain_path)
                theme_domain = theme_domain_data.get("domain") or "generic-fallback"
            except Exception as exc:
                print(f"警告：--theme-domain 文件解析失败（{exc}），目录页版式按 generic-fallback 兜底", file=sys.stderr)
        else:
            print(f"警告：--theme-domain 指定的文件不存在（{args.theme_domain}），目录页版式按 generic-fallback 兜底", file=sys.stderr)
    art_dna = read_json(args.art_dna) if args.art_dna and Path(args.art_dna).exists() else None
    if art_dna:
        # TASK-028 fix: 主题线条插画素材用 currentColor 描边/填色，希望跟随
        # .project-art-motif 上声明的 CSS color（进而响应各主题/art DNA 的
        # accent 色）——但 <img src="xxx.svg"> 是把 SVG 当作独立文档渲染，
        # 页面 CSS 无法穿透进 <img> 内部，currentColor 只能解析成 SVG 自身
        # 默认值（黑），在深色骨架页背景上 0.08~0.15 透明度的黑色描边几乎
        # 不可见（实测截图确认）。改为读取素材原始 svg 源码、直接内联进
        # HTML（而不是 <img src>），这样 currentColor 才能真正继承外层
        # .project-art-motif 的 CSS color，随主题 accent 变化，也是让素材库
        # 保持"不写死颜色、通用可复用"设计意图的正确实现方式。
        for m in (art_dna.get("motifs") or {}).get("assets", []):
            svg_path = (Path(args.output).parent / m.get("file", "")) if m.get("file") else None
            if svg_path and svg_path.exists():
                raw = svg_path.read_text(encoding="utf-8")
                raw = re.sub(r"<\?xml[^>]*\?>\s*", "", raw)
                # 内联 <svg> 由 HTML5 前景内容解析器自动归入 SVG 命名空间，
                # xmlns 属性只在作为独立文档打开时才需要；这里的字面值
                # "http://www.w3.org/2000/svg" 会被 qa_render.py 的外链检测
                # （扫描 https?://）误判为"HTML 含外链"，去掉它既不影响内联
                # 渲染效果，也消除这个误报（此前 <img src> 方案会被
                # inline_assets.py 转成 base64，这段字面文本原本不会出现在
                # 最终 HTML 里；改成内联 svg 后需要在这里主动清理）。
                raw = re.sub(r'\s+xmlns(:\w+)?="[^"]*"', "", raw)
                m["_inline_svg"] = raw
    if art_dna:
        palette = art_dna.get("dna", {}).get("palette", [])
        if len(palette) >= 3:
            # TASK-009: 浅色视觉方向（proposal-light 等）下，art DNA 深色 token 只作用于
            # 封面/章节/尾页（生成式深色背景页）；内容页落在主题浅色 token 上，
            # 内容背景图按「内容页弱化」降为淡色纹理。
            # TASK-033 fix（用户反馈目录页背景"越来越黑"且色相跑偏排查发现的真正根因）：
            # 深色主题此前在这里把 --bg/--accent 等 token 写在 `:root`，对全 deck 每一页
            # （含目录/正文内容页）全局生效，而不只是封面/章节/尾页这类"生成式融合背景页"。
            # 两个实测坏效果：① --bg 被硬编码为固定的 #06101d/#02070d，完全盖过
            # detect_style.py 按场景图算出的、且已修过"亮度地板"的 --bg（见 detect_style.py
            # apply_luma_floor），导致目录页背景比预期更暗、色相更不可辨识；② --accent 被
            # 强制改成 art DNA 调色板第 2 色——本项目该色是徽章上的暖米色 #ccb49c（调色板
            # 语义是"画面里出现过的色块"，不等价于"deck 主题强调色"），目录页
            # toc-orbit-hub.css 的辐条/光晕/描边等装饰全部用 color-mix(var(--accent)…) 派生，
            # 于是本该呈现的"深蓝科技感"被整页染成暖灰/暖米色。改为与浅色主题分支同一套
            # 收敛纪律——art DNA 调色板 token 只作用于封面/章节/尾页这类本就用生成式融合
            # 背景、需要"这一份专属配色识别度"的骨架页；目录/正文内容页保留 detect_style.py
            # 算出的全局主题 accent/bg，不再被单张场景图的局部调色板色块顶掉。
            css += f'''\n/* TASK-033 fix: art DNA 深色 token 收敛为仅作用于生成式深色背景页（原深色主题分支曾写在 :root 全局生效，参见上方说明） */\n.role-cover,.role-section,.role-closing{{--bg:#06101d;--page-bg:#02070d;--accent:{palette[1]};--accent-2:{palette[2]};--line:color-mix(in srgb,{palette[1]} 30%,transparent);--surface:rgba(5,15,28,.70);--surface-2:rgba(9,25,44,.82);}}\n'''
            if args.theme in LIGHT_THEMES:
                css += f'''\n/* TASK-009: art DNA 深色 token 仅作用于生成式深色背景页 */\n.role-cover,.role-section,.role-closing{{--text:#f5f7fb;--muted:#aab4c8;}}\n.slide:not(.role-cover):not(.role-section):not(.role-closing) .project-art-bg{{opacity:.12;}}\n.slide:not(.role-cover):not(.role-section):not(.role-closing):has(.project-art-bg)::after{{background:var(--line);}}\n'''
            # TASK-017 fix: 首尾页生成式融合背景的对比度配套（仅 cover/closing，中间页零影响）。
            # ① 实体深色基底：.slide 本身无 background，页面底色由共享 .deck-stage 提供（浅色主题下
            #    为浅色）；封面/尾页自带 var(--bg)（#06101d 深藏蓝近黑）实底，生成背景图（opacity .82）
            #    叠在实底上 → 基底稳定在深藏蓝近黑量级，轨道圆环/轨迹线/星点低饱和融入，
            #    对标用户 v9 截图观感，不再被浅色舞台稀释成灰蓝中亮底。
            # ② --ho 系列本地重声明：CSS 自定义属性在定义处（:root）即完成 var() 替换并固化，
            #    :root 的 --ho:var(--accent) 不随首尾页局部 --accent（art DNA 金）覆盖变化；渐变标题
            #    （h1-em/closing-echo）必须按局部 accent 重推导，保证深色实底上的对比度。
            css += "\n/* TASK-017: 首尾页融合背景对比度配套 */\n.role-cover,.role-closing{background:var(--bg);--ho:var(--accent);--ho-deep:color-mix(in srgb,var(--accent) 72%,#c03505);--ho-gold:color-mix(in srgb,var(--accent) 45%,#ffd76a);}\n"
    body = "\n".join(slide_html(s, section_titles, art_dna, theme_domain) for s in slides)
    body = apply_autofit_markers(body)
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
<div class="deck-ui"><span data-current>1</span><span>/</span><span data-total>{len(slides)}</span><span>← → / Space / S / O / F / B / E</span></div>
<nav class="overview" aria-label="Slides overview"></nav>
<script>{js}</script>
<script>{autofit_js}</script>
<script>{editor_js}</script>
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
