#!/usr/bin/env python3
import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path
from common import read_json, parse_page_semantics, is_deck_content_slide, parse_visual_blueprints, LAYOUT_PATTERNS, BLUEPRINT_FIELDS


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
    p.add_argument("--blueprints", required=False, help="TASK-009: 视觉蓝图 state/visual_blueprints.md；缺省取 --history 同目录下的 visual_blueprints.md")
    p.add_argument("--round", type=int, default=1)
    return p.parse_args()


def html_sections_by_page(text):
    """TASK-003: 按 data-page 切出每页 HTML 片段，用于分组渲染核验。"""
    sections = {}
    for m in re.finditer(r'<section class="slide[^"]*"[^>]*?data-page="(\d+)"[\s\S]*?(?=<section class="slide|$)', text):
        sections[int(m.group(1))] = m.group(0)
    return sections


# ── TASK-021 A.5: 视觉符号产出下限自动化门禁 ────────────────────────────────
# 渲染产物里代理视觉符号存在的 class 清单（不含仅靠 CSS ::before/::after 生成、
# 静态文本扫描看不到的伪元素符号；这些 class 本身在 HTML 源码里始终可见）。
STRUCTURAL_SYMBOL_CLASSES = (
    "group-card", "gallery-index", "kpi-number", "timeline-item", "loop-node",
    "ed-strip", "checkpoint-node", "spoke-core", "gather-core", "hub-top-core",
    "num-big", "cp-link", "deckline", "outline-number", "li-index",
    # TASK-022: 并列/对比/层级等无先后顺序的列表条目改用不暗示顺序的类目标记
    # （li-mark，纯方块无数字），仍是真实的结构符号（标签/标记类），计入下限。
    "li-mark",
    # TASK-024 fix（终审 V5 复核发现）：toc-segment-strip.html（当年激活的目录页
    # 模板，见 render_deck.py toc_segment_strip_html）用 ss-ghost-num/mc-num 承载
    # 章节编号，语义与 outline-number/gallery-index 完全一致（编号类结构符号），
    # 此前遗漏在词表外会让目录页在 structural-fallback 模式下被误判缺符号。
    "ss-ghost-num", "mc-num",
    # TASK-032: toc-orbit-hub（现当前激活的目录页模板，见 render_deck.py
    # toc_orbit_hub_html）用 oh-node-num 承载卫星节点编号，语义同上一并计入。
    "oh-node-num",
    # TASK-036: 新增目录可选版式（矩阵网格式 tgm-num、杂志索引式 tmi-num）
    # 同样用编号承载结构符号语义，与 ss-ghost-num/mc-num/oh-node-num 一视
    # 同仁计入，避免这两个版式将来被启用时在 structural-fallback 模式下
    # 被误判缺符号。
    "tgm-num", "tmi-num",
)
# 本身即承担方向/关系职能的符号 class（部分变体的箭头由 CSS ::before/::after
# 生成，静态扫描看不到字符本身，但承载该语义的容器 class 一定在 HTML 源码里）。
DIRECTIONAL_SYMBOL_CLASSES = (
    "cp-link", "loop-node", "loop-ring", "checkpoint-node", "spoke-core",
    "gather-core", "hub-top-core", "deckline",
    # TASK-022: cause-effect 的 "→"、vs-split 的分界线/VS 徽标同样是 CSS
    # ::before/::after 生成、静态扫描看不到字符本身；但 layout-cause-effect /
    # layout-vs-split 这两个 variant class 无条件出现在 .slide 根元素上，且
    # CSS 无条件渲染对应方向符号，用 variant class 本身代理该符号的存在。
    "layout-cause-effect", "layout-vs-split",
    # 同理补齐 chain-3/chain-4：.layout-chain-3(4) .group-grid::before/::after
    # 无条件绘制横向连接线+箭头（见 assets/components/layouts.css ⑨路径式流程
    # chain-3 段），此前遗漏在词表外，导致每一个 chain-3/chain-4 页面在这项
    # 门禁下恒被误判"无方向/关系职能符号"（与实际渲染不符，非内容问题）。
    "layout-chain-3", "layout-chain-4",
    # TASK-021 测试实测修复（与上面 chain-3/4 同一类根因）：ed-strip 在
    # DIRECTION_REQUIRED_VARIANTS 里登记为"必须有方向符号"的变体，
    # `.ed-flow .ed-strip:not(:last-child)::after { content:"↓"; }`
    # （见 assets/components/layouts.css ⑨ed-strip 段）无条件在条目之间画
    # "↓"，但该 class 此前遗漏在本词表外，导致每一个 ed-strip 页面都被误判
    # "无方向/关系职能符号"（与实际渲染不符，非内容问题）。ed-strip 本身
    # 已在 STRUCTURAL_SYMBOL_CLASSES 里代理结构符号存在，这里追加代理其
    # 方向语义。
    "ed-strip",
)
DIRECTION_CHARS = "→←↓↑↺"

# 只有语义上天然承载"顺序/方向/回授"的 variant 才要求方向符号；矩阵/非对称
# 双栏（grid-2x2/asym-cards/anchor-right/num-anchor/layers-N 等）是平等并列或
# 层级结构，其符号语言是编号徽标/描边强调（多为 CSS ::before 生成，计入
# STRUCTURAL_SYMBOL_CLASSES 的 group-card 计数已经够格），不该被要求再长出一个
# 不属于其语义的箭头——实测（真实 Playwright 项目跑分）此前的一刀切判定把这些
# 页面全部打成"退化为纯文本列表"，是门禁本身校准过严，不是渲染真的退化。
DIRECTION_REQUIRED_VARIANTS = {
    "hub-radiate", "hub-return", "hub-top", "hub-spoke", "gather-3",
    "loop-3", "loop-4", "chain-3", "chain-4", "ascend-4", "checkpoint-3",
    "cause-effect", "vs-split", "ed-strip",
}
# TASK-021（测试补漏）：hub-left 从本表移出——实测（真实 Playwright 项目跑分）
# 发现 .layout-hub-left 的 CSS（layouts.css「① 中心节点+分支：hub-left」段）
# 只对首卡做 accent 实底强调（深蓝背景+白字），不像同族 hub-radiate/hub-return
# 那样在 .visual.panel 上叠加 ::before/::after 方向性渐变条，也不像 hub-top/
# hub-spoke 那样在 render_structural_variant() 里显式插入 "↓" 箭头 span——
# 三者都无条件产出可命中的方向符号，hub-left 从设计上就没有。hub-left 的符号
# 语言是"实底强调中心核"，与本文件上方注释里已经排除在外的 grid-2x2/asym-cards/
# layers-N（"编号徽标/描边强调，不该被要求再长出一个不属于其语义的箭头"）是
# 同一类别，此前把 hub-left 一并归进方向必需集合是分类过宽，不是渲染真的退化。

# kpi/gallery/timeline/table 角色自带原生符号语言（大数字计数器/编号角标/日期
# 徽标/表格行列），不需要额外方向符号；table 的 th/td 结构本身不产生可命中的
# class（无 group-card 等），单独用标签计数兜底。
SELF_SYMBOLIC_ROLES = {"kpi", "gallery", "timeline", "table"}

# A.4 三段式骨架试点范围——只有这两个角色的渲染分支实际产出 slide-head/body/foot；
# 其余角色仍保留原有 DOM 结构（详见 render_deck.py 的分阶段推广说明），门禁按
# 实际实现范围核验，不对未试点角色提出不存在的骨架要求。
SKELETON_PILOT_ROLES = {"bullets", "image-hero"}

# TASK-022: takeaway 反模式检测——粗略字符重叠率，不引入分词依赖。口径：
# 去除标点空白后，takeaway 与导语/首条 bullet 的公共字符数占（较短文本长度）
# 的比例达到阈值即判定为"同义复述、无增量信息"。这是简单近似，不是语义理解，
# 但足以拦住"So-what：直接复制导语前 52 字"这类机械复制（本项目 15 页全部
# 属于此类）。
_PUNCT_RE = re.compile(r"[\s，。、：:；;,.·\"'「」【】（）()\-—…!?！？]")
_REDUNDANCY_THRESHOLD = 0.6


def _norm_for_similarity(s):
    return _PUNCT_RE.sub("", str(s or ""))


def _char_overlap_ratio(a, b):
    na, nb = _norm_for_similarity(a), _norm_for_similarity(b)
    if not na or not nb:
        return 0.0
    sa, sb = set(na), set(nb)
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def _takeaway_is_redundant(takeaway_text, blocks):
    """takeaway 是否和本页导语段落或首条 bullet 高度重复（同义复述）。"""
    body = re.sub(r"^So-what[：:]\s*", "", takeaway_text)
    for b in blocks:
        if b.get("type") == "paragraph" and b.get("text"):
            if _char_overlap_ratio(body, b["text"]) >= _REDUNDANCY_THRESHOLD:
                return True
        if b.get("type") == "list" and b.get("items"):
            if _char_overlap_ratio(body, b["items"][0]) >= _REDUNDANCY_THRESHOLD:
                return True
    return False


# TASK-025: 列表-视觉载体重复渲染门禁——实测发现 kpi/gallery 两个角色曾经把
# "被解析消费成视觉组件（kpi-grid 大数字卡/gallery 图片阵列/group-card 分组
# 卡片）的正文列表"，同时又以完整 `<ul class="content-list">` 原样打印一遍，
# 同一批信息讲了两遍（详见 render_deck.py TASK-025 fix 的 kpi/gallery/
# image-hero 三处改动、references/page-logic-patterns.md §17.7）。
# 判定信号：①正文列表条目数 ==（且 >=3，避免 1-2 条的偶然吻合）某类视觉单元
# 渲染实例数（强吻合信号，即"这批数字/图片/卡片就是从这份列表解析出来的"）；
# ②渲染出的该页 HTML 片段里，这份列表仍以完整 `<ul class="content-list">`
# 原文出现（未被消费替换）。两者同时成立即判定为重复渲染，硬性扣分（非提示）。
_LIST_VISUAL_CANDIDATES = (
    ("kpi-grid 大数字卡", re.compile(r'class="panel kpi-card"')),
    ("gallery 图片阵列", re.compile(r'class="image-frame(?:\s|")')),
    ("分组卡片(group-card)", re.compile(r'class="panel group-card"')),
)
_RAW_CONTENT_LIST_RE = re.compile(r'<ul class="content-list"')


def _list_visual_duplication(sect, slide):
    list_items = [
        x for b in slide.get("blocks", []) if b.get("type") == "list" and not b.get("generated")
        for x in b.get("items", [])
    ]
    if len(list_items) < 3 or not _RAW_CONTENT_LIST_RE.search(sect):
        return None
    for label, pat in _LIST_VISUAL_CANDIDATES:
        n_visual = len(pat.findall(sect))
        if n_visual > 0 and n_visual == len(list_items):
            return label, len(list_items), n_visual
    return None


def _symbol_stats(section_html, role=None, layout_variant=None):
    hits = sum(len(re.findall(r"\b" + re.escape(c) + r"\b", section_html)) for c in STRUCTURAL_SYMBOL_CLASSES)
    if role == "table":
        # 表格自身的行列结构即视觉符号：th/td 数量代理"结构化程度"
        hits += len(re.findall(r"<t[hd]\b", section_html))
    has_direction = any(ch in section_html for ch in DIRECTION_CHARS) or any(
        re.search(r"\b" + re.escape(c) + r"\b", section_html) for c in DIRECTIONAL_SYMBOL_CLASSES
    )
    direction_required = (layout_variant in DIRECTION_REQUIRED_VARIANTS) and role not in SELF_SYMBOLIC_ROLES
    return hits, has_direction, direction_required


# ── TASK-021 B.3(b): 静态兜底溢出估算——字符数/行高 × 容器已知 CSS 高度预算 ──
# 预算值按 B.1 补丁定稿后的实际 CSS 校准：画布 1080px 高、1920px 宽；
# --slide-padding 各主题 82–96px，取保守下限 82px（估算偏严格，宁可多报不漏报）；
# --fs-body 31px × --lh-body 1.36 ≈ 42px 行高；.content-list li min-height 54px。
SLIDE_W, SLIDE_H, SLIDE_PAD = 1920, 1080, 82
BODY_LINE_PX = 42
TITLE_BLOCK_PX = 130      # h2(70px×1.05≈74px) + 上边距 + 一定折行余量
TAKEAWAY_BLOCK_PX = 110   # .takeaway 面板内边距 + 一行文字
LIST_ITEM_MIN_PX = 54 + 24
CHARS_PER_100PX = 3.1     # 中文字符近似正方形，fs-body 31px 时约每 100px 容纳 3.1 字

# role -> (可用高度 px, 可用宽度 px)；双栏角色宽度按单栏（12 列栅格的 6 列）估算
CONTAINER_HEIGHT_BUDGET = {
    "bullets": (SLIDE_H - 2 * SLIDE_PAD - TITLE_BLOCK_PX - TAKEAWAY_BLOCK_PX, SLIDE_W - 2 * SLIDE_PAD),
    "two-column": (SLIDE_H - 2 * SLIDE_PAD - TITLE_BLOCK_PX - TAKEAWAY_BLOCK_PX, (SLIDE_W - 2 * SLIDE_PAD - 34) // 2),
    "image-side": (SLIDE_H - 2 * SLIDE_PAD - TITLE_BLOCK_PX - TAKEAWAY_BLOCK_PX, (SLIDE_W - 2 * SLIDE_PAD - 34) // 2),
    "image-hero": (SLIDE_H - 2 * SLIDE_PAD - TITLE_BLOCK_PX - TAKEAWAY_BLOCK_PX, int((SLIDE_W - 2 * SLIDE_PAD - 34) * 4 / 12)),
}


def estimate_overflow(slide):
    """近似估算正文内容是否超出容器高度预算；仅覆盖有稳定宽高预算的角色。"""
    role = slide.get("role")
    budget = CONTAINER_HEIGHT_BUDGET.get(role)
    if not budget:
        return False, ""
    avail_h, avail_w = budget
    chars_per_line = max(6, int(avail_w * CHARS_PER_100PX / 100))
    total_px = 0
    for b in slide.get("blocks", []):
        t = b.get("type")
        if t == "paragraph":
            n = len(b.get("text", ""))
            lines = max(1, -(-n // chars_per_line))
            total_px += lines * BODY_LINE_PX + 26
        elif t == "list":
            for item in b.get("items", []):
                n = len(item) + 3
                lines = max(1, -(-n // chars_per_line))
                total_px += max(LIST_ITEM_MIN_PX, lines * BODY_LINE_PX + 24)
        elif t == "table":
            total_px += len(b.get("rows", [])) * 46
    for g in slide.get("groups") or []:
        total_px += 50
        for item in g.get("items", []):
            n = len(item)
            lines = max(1, -(-n // chars_per_line))
            total_px += max(LIST_ITEM_MIN_PX, lines * BODY_LINE_PX + 20)
    overflow = total_px > avail_h
    return overflow, f"预算约 {avail_h}px / 估算约 {total_px}px（基于估算，非真实像素测量）"


def structural(text, ir, art_dna=None, semantics=None, blueprints=None, skip_overflow_estimate=False):
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
    # TASK-009: 连页变体禁令——上一内容页的布局签名（pattern + 变体）
    prev_content_sig = None
    prev_content_page = None
    if art_dna:
        required = ["cover_background", "content_background", "section_background", "closing_background"]
        missing = [k for k in required if not art_dna.get(k)]
        if missing:
            deck_issues.append("项目视觉系统缺少角色背景：" + ",".join(missing))
        # TASK-017 fix: 首尾页恢复铺生成式融合背景，art DNA 背景覆盖门禁随之恢复
        # cover/content/section/closing 四类页面全核对（原范围恢复，非加强非削弱，容差不变）
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
            # TASK-022: takeaway 改为可选——缺失不再扣分（默认不渲染是新的正常态，
            # 见 render_deck.py/build_ir.py 的调整）；只有"存在但和导语/首条 bullet
            # 高度重复"（同义复述、没有增量信息）才判反模式扣分，口径见 NARRATIVE.md
            # 「页面级硬规则」与 references/final-quality-check.md C3。
            takeaway_text = str(slide.get("takeaway") or "").strip()
            if takeaway_text and _takeaway_is_redundant(takeaway_text, slide.get("blocks", [])):
                issues.append("takeaway 与导语/首条 bullet 高度重复（同义复述，无增量信息），应删除或改写为真正的新增结论")
                score -= 10
            content_blocks = sum(1 for b in slide.get("blocks", []) if b.get("type") in {"paragraph", "list", "table", "quote", "code"})
            if takeaway_text and not _takeaway_is_redundant(takeaway_text, slide.get("blocks", [])):
                content_blocks += 1
            # TASK-022: kpi/gallery/image-hero/image-side/compare/table/two-column 靠图片
            # 或专属组件（表格/大数字）承载主证据，天然不缺内容块；timeline/bullets 同样
            # 靠列表/节点结构承载主证据（不需要额外一段复述文字才算"够密"），一并计入，
            # 避免"删掉复读式收尾段落"这个质量改进反而触发"信息密度不足"的假阳性。
            # TASK-021 测试实测修复：toc 此前能凑够 3 块全靠 build_ir.py 曾经自动生成的
            # "So-what：……" 硬编码 takeaway 补位（该硬编码已在 NARRATIVE.md/build_ir.py
            # 侧删除，见该文件与 page-logic-patterns.md §17.3 的口径更新）；删除后 toc 结构性
            # 只剩 list+paragraph 两块，systematically 卡在"信息密度低于 3 个内容块"，属于
            # 那次清理产生的连带误判，而非真实内容变薄——toc 的目录卡片本身（toc_cards →
            # toc-*-html 渲染）就是承载主内容的专属组件，与 kpi-grid/gallery-grid 同理，
            # 补进本白名单而非重新造一条 So-what 式假 takeaway 回填。
            if role in {"kpi", "gallery", "image-hero", "image-side", "compare", "table", "two-column", "timeline", "bullets", "toc"} or slide.get("images"):
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
            # ── TASK-009: 布局门禁（四步链路第②③步核验）────────────────────
            if blueprints is None:
                issues.append("缺少视觉蓝图文件 state/visual_blueprints.md（四步链路第③步：生成视觉蓝图未落盘）")
                score -= 25
            else:
                bp_row = blueprints.get(deck_ordinals.get(page_no))
                if bp_row is None:
                    issues.append("缺少视觉蓝图登记：visual_blueprints.md 中无此页（四步链路第②③步缺失）")
                    score -= 25
                else:
                    if bp_row.get("pattern") not in LAYOUT_PATTERNS:
                        issues.append(f"布局 pattern 未登记于 layout-patterns.md 的 12 种模式：{bp_row.get('pattern')}")
                        score -= 20
                    missing_fields = [k for k in BLUEPRINT_FIELDS if not (bp_row.get(k) or "").strip()]
                    if missing_fields:
                        issues.append("视觉蓝图字段空缺：" + ",".join(missing_fields))
                        score -= 15
                    ir_pattern = slide.get("layout_pattern")
                    if ir_pattern != bp_row.get("pattern"):
                        issues.append(f"IR layout_pattern 与蓝图登记不一致（登记 {bp_row.get('pattern')} / IR {ir_pattern}）")
                        score -= 20
                    sig = (bp_row.get("pattern"), bp_row.get("variant") or "")
                    if prev_content_sig is not None and sig == prev_content_sig:
                        issues.append(f"与上一内容页（P{prev_content_page}）使用完全相同的布局签名（{sig[0]}/{sig[1] or '无变体'}），违反连页变体禁令")
                        score -= 20
                    prev_content_sig = sig
                    prev_content_page = page_no
                    # ── TASK-011: 节点数门禁——计数变体（ascend-N/chain-N/loop-N）渲染节点数必须等于
                    # 蓝图登记阶段数 N；超出即存在无来源幻影节点（如补位块落卡），不足即内容缺失。
                    bp_variant = (bp_row.get("variant") or "").strip()
                    vm = re.fullmatch(r"(ascend|chain|loop)-(\d+)", bp_variant)
                    if vm:
                        expected = int(vm.group(2))
                        sect = html_sections.get(page_no, "")
                        rendered = (len(re.findall(r'class="panel timeline-item"', sect))
                                    # ascend-4 节点由 render_deck.py::ascend_row_html() 生成，class 固定带
                                    # 额外的 "ascend-step" 后缀（class="panel timeline-item ascend-step"），
                                    # 上一行的精确闭引号匹配永远命中不到，导致 ascend-4 变体页恒被判"渲染 0
                                    # 节点"（TASK-011 引入节点数门禁时未覆盖 ascend-4 独有的 class 拼法）。
                                    + len(re.findall(r'class="panel timeline-item ascend-step"', sect))
                                    + len(re.findall(r'class="panel group-card"', sect))
                                    + len(re.findall(r'class="panel loop-node ', sect)))
                        if rendered != expected:
                            issues.append(f"渲染节点数与蓝图登记数不一致（{bp_variant} 登记 {expected} / 渲染 {rendered}），存在无来源幻影节点或内容缺失")
                            score -= 20
            # ── TASK-025: 列表-视觉载体重复渲染门禁（硬性扣分，非提示）──
            sect = html_sections.get(page_no, "")
            dup = _list_visual_duplication(sect, slide)
            if dup:
                label, n_list, n_visual = dup
                issues.append(
                    f"列表与视觉载体重复渲染：正文 {n_list} 条列表被解析为 {n_visual} 个{label}后，"
                    f"仍以完整 <ul class=\"content-list\"> 原样输出，同一批信息讲了两遍"
                )
                score -= 50
            # ── TASK-021 A.5: 视觉符号产出下限（渲染产物扫描，而非"声明了变体"）──
            layout_variant_cur = (slide.get("layout_variant") or "").strip()
            symbol_hits, has_direction, direction_required = _symbol_stats(sect, role, layout_variant_cur)
            if symbol_hits < 2 or (direction_required and not has_direction):
                issues.append(
                    f"结构类符号实例不足（符号命中 {symbol_hits} 个，"
                    f"{'有' if has_direction else '无'}方向/关系职能符号"
                    f"{'，该 variant 语义上要求' if direction_required else ''}），可能仍是纯文本竖排列表"
                )
                score -= 40
            # ── TASK-021 A.5: 三段式骨架检查（仅核验已试点角色，见 SKELETON_PILOT_ROLES）──
            if role in SKELETON_PILOT_ROLES:
                missing_skeleton = [
                    part for part in ("slide-head", "slide-body", "slide-foot")
                    if f'class="{part}"' not in sect
                ]
                if missing_skeleton:
                    issues.append(f"三段式骨架缺失：{','.join(missing_skeleton)}")
                    score -= 30
            # ── TASK-021 B.3(b): 静态兜底溢出估算（Playwright 缺失时的过渡防线）──
            # Playwright 模式已经有逐页真实 scrollHeight/scrollWidth 测量，比字符数
            # 估算更准确；此估算只在"没有真实测量可用"时才作为唯一依据参与评分，
            # 避免真实测量已判定不溢出时，还被近似公式的系统性高估误伤（尤其是
            # 多列格阵变体，字符数估算不按实际列数折算高度，会显著高估）。
            if not skip_overflow_estimate:
                over, budget_note = estimate_overflow(slide)
                if over:
                    issues.append(f"正文内容估算超出容器高度预算，可能溢出（{budget_note}）")
                score -= 25
        rows.append({"page": page_no, "score": max(0, score), "mode": "structural-fallback", "issues": issues})
    return rows


# ── TASK-028: 并列容器尺寸一致性自动化检测 ────────────────────────────────
# 判定口径见 references/final-quality-check.md V4「并列容器尺寸一致性专项」：
# 同一页内同一批并列展示的同类容器（目录铭牌 / 分组卡片 / KPI 卡片 / 对比卡片等）
# 必须尺寸统一，不能因为内部文字长度不同而产生大小差异。这里只能在 Playwright
# 真实渲染后用 getBoundingClientRect() 测量才有意义（HTML/IR 结构扫描拿不到实际
# 渲染尺寸），structural-fallback 模式不执行本项检查。
# 选择器只覆盖"设计上确为并列同级"的容器分组：
#   - .ss-row 内的目录铭牌（本任务的直接触发场景）
#   - .group-grid 的默认矩阵用法、gather-3 的 needs 分支列、hub-top 的 branches
#     分支列（真正的并列卡片；hub/gather 的核心节点用独立 class 承载，不落在
#     这些选择器里，天然被排除，不会被拿来跟分支卡片比较）
#   - kpi-grid / compare-grid 的数字卡 / 对比卡
# 不含 gallery-grid（图片框保留各自图片的原始宽高比，尺寸差异是保护图片不失真
# 的合理设计，不属于本检查范畴，误伤需避免）。
# TASK-028 fix（实测发现分组逻辑 bug）：三元组改为 (容器选择器, 卡片选择器, 标签)。
# 最初版本按 el.parentElement 分组同一批卡片，误判了"卡片各自包一层独立 wrapper
# div、只共享更上层容器"的真实 DOM 结构（典型如 ss-plaque 的直接父级是各自的
# .ss-seg，只有 .ss-row 才是 6 张铭牌共同的祖先）——parentElement 分组会把 6 张
# 铭牌拆成 6 个各含 1 个元素的假分组，逐个跳过"size<2"判定，永远测不出差异
# （用真实故意改坏的 CSS 实测复现过这个假阴性，不是理论推测）。改为显式声明
# 容器选择器，在每个容器内部用 querySelectorAll(卡片选择器) 取真正要比较的同组
# 卡片，不再依赖 DOM 是否直接父子。
_SIBLING_GROUP_SELECTORS = [
    (".ss-row", ".ss-plaque", "目录铭牌(ss-plaque)"),
    (".group-grid", ":scope > .group-card", "分组卡片(group-card)"),
    (".gather-needs", ":scope > .group-card", "分组卡片-汇聚分支(gather-needs)"),
    (".hub-top-branches", ":scope > .group-card", "分组卡片-中心辐射分支(hub-top-branches)"),
    (".kpi-grid", ":scope > .kpi-card", "KPI 卡片(kpi-card)"),
    (".compare-grid", ":scope > .compare-card", "对比卡片(compare-card)"),
    (".mc-grid", ":scope > .mc-card", "目录卡片(mc-card)"),
    # TASK-032: toc-orbit-hub 的卫星节点圆形容器——同一份 deck 内直径必须
    # 固定统一（compute_orbit_layout 统一计算，见 render_deck.py），不因
    # 文字长短产生大小不一致，纳入并列容器尺寸一致性自动核验。
    (".toc-orbit-hub", ":scope > .oh-node", "目录卫星节点(oh-node)"),
    # TASK-036: 新增目录可选版式（矩阵网格式/杂志索引式）的并列容器同样纳入
    # 尺寸一致性核验，与已接入版式一视同仁，不因版式新旧区别对待。
    (".tgm-grid", ":scope > .tgm-card", "目录网格卡片(tgm-card)"),
    (".tmi-list", ":scope > .tmi-row", "目录索引行(tmi-row)"),
    # TASK-041: 新增目录版式 toc-collage-asym 的短条列表——头条卡（.tca-headline）
    # 与短条本就设计为不同尺寸（非对称是该版式的核心视觉语言，不纳入一致性
    # 核验），但"同一批短条彼此之间"仍要求固定统一高度，与其余已接入版式的
    # 并列容器一视同仁。
    (".tca-list", ":scope > .tca-row", "目录拼贴短条(tca-row)"),
]

_SIBLING_UNIFORMITY_JS = """
(() => {
  const active = document.querySelector('.slide.is-active');
  if (!active) return [];
  const specs = %s;
  const out = [];
  for (const [containerSel, cardSel, label] of specs) {
    const containers = Array.from(active.querySelectorAll(containerSel));
    for (const container of containers) {
      const els = Array.from(container.querySelectorAll(cardSel));
      if (els.length < 2) continue;
      const rects = els.map(el => el.getBoundingClientRect());
      const heights = rects.map(r => r.height);
      const widths = rects.map(r => r.width);
      const maxH = Math.max(...heights), minH = Math.min(...heights);
      const maxW = Math.max(...widths), minW = Math.min(...widths);
      const hDiff = maxH - minH, wDiff = maxW - minW;
      const hThresh = Math.max(8, maxH * 0.05);
      const wThresh = Math.max(8, maxW * 0.05);
      if (hDiff > hThresh || wDiff > wThresh) {
        out.push({
          label, count: els.length,
          hDiff: Math.round(hDiff), wDiff: Math.round(wDiff),
          maxH: Math.round(maxH), minH: Math.round(minH),
          maxW: Math.round(maxW), minW: Math.round(minW),
        });
      }
    }
  }
  return out;
})()
""" % json.dumps(_SIBLING_GROUP_SELECTORS, ensure_ascii=False)


def check_sibling_uniformity(page):
    """TASK-028: 测量当前激活页内并列卡片组的实际渲染尺寸差异，返回命中列表。"""
    try:
        return page.evaluate(_SIBLING_UNIFORMITY_JS) or []
    except Exception:
        return []


# ── TASK-033：用户反馈两条硬性问题（目录页文字不够显著、背景从「深蓝色」
#    变成「接近纯黑」），要求固化为「以后任何项目都要检查」的永久质量门禁，
#    不能只写文档不落地。判定口径见 references/final-quality-check.md V1
#    第 4 条（规则A：标题级文字对比度/字号下限）与新增 V6（规则B：背景色
#    漂移检测）。以下两条规则都基于 Playwright 真实渲染像素测量，不是静态
#    解析 CSS 声明值——道理同 contrast_audit.py 文件头说明：渐变底/半透明
#    叠加/color-mix 派生这些场景，静态解析声明值很容易算错，只有量测「实际
#    画出来的像素」才可信。
#
# 规则A：标题级文字（h1/h2/目录节点标题/中心枢纽标题/大数字焦点等承担主要
# 信息传达职能的大字号元素）对比度下限从 V1 通用大标题的 3:1 上调到 6:1，
# 且 1920 画布基准下字号不得低于 20px——命中即整页扣分（终审阻断口径同 V1）。
TITLE_CONTRAST_MIN = 6.0
TITLE_MIN_FONT_PX = 20
# 范围严格对齐用户原话点名的元素：h1/h2 通用大标题 + 目录页中心枢纽标题/
# 卫星节点标题/节点编号。不含 .kpi-number/.num 等"accent 色大数字焦点"——
# 那类元素是 V1 既有 ≥3:1 门槛下的既定设计语言（accent 蓝压深色卡片，WCAG
# 相对亮度公式下蓝色本身很难天然达到 6:1），全库统一收紧到 6:1 会强行要求
# 重新配色，超出本轮"目录页不够显著"问题的实际范围，不属于本规则该管的对象。
TITLE_SELECTORS = [
    "h1", "h2", ".oh-hub-title", ".oh-node-title", ".oh-node-num",
]

_TITLE_ELEMENTS_JS = """
(() => {
  const slide = document.querySelector('.slide.is-active');
  if (!slide) return [];
  const sels = %s;
  const seen = new Set();
  const out = [];
  sels.forEach(sel => {
    slide.querySelectorAll(sel).forEach(el => {
      if (seen.has(el)) return;
      seen.add(el);
      const rect = el.getBoundingClientRect();
      if (rect.width < 4 || rect.height < 4) return;
      if (rect.bottom < 0 || rect.right < 0 || rect.left > window.innerWidth || rect.top > window.innerHeight) return;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') return;
      const text = (el.textContent || '').trim();
      if (!text) return;
      out.push({
        tag: el.tagName.toLowerCase(), cls: Array.from(el.classList || []).join('.'),
        text: text.slice(0, 24),
        x: rect.x, y: rect.y, w: rect.width, h: rect.height,
        fontSize: parseFloat(cs.fontSize) || 0,
      });
    });
  });
  return out;
})()
""" % json.dumps(TITLE_SELECTORS, ensure_ascii=False)


def check_title_prominence(page, img):
    """规则A：逐个测量当前激活页里的标题级元素，字号/对比度任一不达标即命中。
    img 为该页已截好的 Playwright 截图（PIL Image），dpr 固定为 1（与
    try_playwright 的 device_scale_factor 一致），复用 contrast_audit.py 的
    像素级测量算法（Otsu 双峰阈值分离前景/背景色，按 WCAG 相对亮度换算
    对比度），不重复实现一套新的取色逻辑。"""
    try:
        from contrast_audit import measure_element
    except Exception:
        return []
    try:
        elems = page.evaluate(_TITLE_ELEMENTS_JS) or []
    except Exception:
        return []
    hits = []
    for el in elems:
        if el["fontSize"] < TITLE_MIN_FONT_PX:
            hits.append(
                f"标题级文字字号过小：{el['tag']}.{el['cls']} \"{el['text']}\" "
                f"实测 {el['fontSize']:.1f}px < 下限 {TITLE_MIN_FONT_PX}px"
            )
            continue
        ratio = measure_element(img, 1, el)
        if ratio is not None and ratio < TITLE_CONTRAST_MIN:
            hits.append(
                f"标题级文字对比度不足：{el['tag']}.{el['cls']} \"{el['text']}\" "
                f"实测 {ratio:.2f}:1 < 下限 {TITLE_CONTRAST_MIN}:1"
            )
    return hits


# 规则B：背景色不能因多轮视觉调整、多层暗色叠加而"漂移"成接近无色相的纯黑/
# 纯灰——用户本轮实测踩坑的原始案例（目录页 --bg 曾被算到 rgb(8,10,14)，
# luma≈0.039，三通道几乎相等分辨不出色相）。在当前激活页的 .slide 四角（避开
# 中心内容区，四角大概率是纯背景，不会踩到卡片/文字）取样实际渲染像素，
# 亮度低于 BG_LUMA_FLOOR 时人眼已经分辨不出任何色相，直接判定命中；亮度处于
# 「暗但本不该完全失去色相」的中间档时，再看色度（RGB 三通道极差）是否也低于
# BG_CHROMA_FLOOR——两者都低才判「偏灰无色相」（避免误伤本来就是深蓝、深紫等
# 高饱和深色设计，那类颜色 luma 低但色度并不低）。
BG_LUMA_FLOOR = 0.065        # 低于此亮度：无论色度如何，人眼已分辨不出色相，直接命中
BG_LUMA_MIDBAND = 0.16       # 亮度处于 [FLOOR, MIDBAND) 之间时，再叠加色度判定
BG_CHROMA_FLOOR = 10         # RGB 三通道极差（max-min）低于此值视为"看起来无彩色"

_SLIDE_RECT_JS = """
(() => {
  const el = document.querySelector('.slide.is-active');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {x: r.x, y: r.y, w: r.width, h: r.height};
})()
"""


def _bg_sample_stats(img, dpr, rect):
    pts = []
    for fx, fy in ((0.03, 0.03), (0.97, 0.03), (0.03, 0.97), (0.97, 0.97)):
        x = int(round((rect["x"] + rect["w"] * fx) * dpr))
        y = int(round((rect["y"] + rect["h"] * fy) * dpr))
        x = max(0, min(img.width - 1, x))
        y = max(0, min(img.height - 1, y))
        px = img.getpixel((x, y))
        pts.append(px[:3])
    rs = sorted(p[0] for p in pts)
    gs = sorted(p[1] for p in pts)
    bs = sorted(p[2] for p in pts)
    r, g, b = rs[len(rs) // 2], gs[len(gs) // 2], bs[len(bs) // 2]
    luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    chroma = max(r, g, b) - min(r, g, b)
    return luma, chroma, (r, g, b)


def check_background_drift(page, img):
    """规则B：四角背景采样，命中返回问题描述列表（当前只会产出 0 或 1 条）。"""
    try:
        rect = page.evaluate(_SLIDE_RECT_JS)
    except Exception:
        return []
    if not rect or rect["w"] < 4 or rect["h"] < 4:
        return []
    luma, chroma, rgb = _bg_sample_stats(img, 1, rect)
    if luma < BG_LUMA_FLOOR:
        return [
            f"背景色疑似漂移为接近纯黑（四角采样中位色 rgb{rgb}，luma={luma:.3f} "
            f"< 下限 {BG_LUMA_FLOOR}，人眼在此亮度下已无法分辨具体色相）"
        ]
    if luma < BG_LUMA_MIDBAND and chroma < BG_CHROMA_FLOOR:
        return [
            f"背景色疑似漂移为无色相灰底（四角采样中位色 rgb{rgb}，luma={luma:.3f}，"
            f"三通道极差={chroma} < 下限 {BG_CHROMA_FLOOR}，看不出明确色相倾向）"
        ]
    return []


# ── TASK-036: 字体排版检查体系（用户给出的 5 条精确量化规则）──────────────
# 在规则A/B（标题级字号/对比度下限、背景色漂移）基础上扩展为覆盖标题/
# 二级标题/正文/图注四级文本的完整排版检查体系，均基于 Playwright 真实
# 渲染测量（getComputedStyle/getBoundingClientRect），不是字符数估算。
# 对应用户原话给出的 5 条规则：
#   ① 层级比例：相邻字号层级倍率 ≥1.2，禁止字号大小接近却无视觉区分。
#   ② 文本框内边距&占比：文字占框内可用高度 ≤75%，四周留白，单行标题
#      占框高 50%~70%（仅当该文本框内容基本就是这一个标题、无其它并列
#      文本子项时才适用，避免把"标题只是框内多段文字之一"的正常设计
#      误判为"标题独占过小/过大比例"）。
#   ③ 画布最小可读性底线（16:9，画布高 1080px）：正文字号 ≥画布高 2.5%、
#      图注/注释字号 ≥画布高 1.5%。
#   ④ px 硬编码静态扫描：见 scan_hardcoded_font_px（提示项，不阻断）。
#   ⑤ 行距配套：正文 1.4~1.6 倍，标题（含二级标题）1.2~1.3 倍。
TYPO_CANVAS_H = SLIDE_H  # 1080，与画布 16:9 假设一致

TYPO_LEVEL_RATIO_MIN = 1.2          # 规则①：相邻字号层级倍率下限
TYPO_BOX_OCCUPANCY_MAX = 0.75       # 规则②：文本占文本框可用高度上限
TYPO_SINGLE_LINE_TITLE_MIN = 0.5    # 规则②：单行标题占框高下限
TYPO_SINGLE_LINE_TITLE_MAX = 0.7    # 规则②：单行标题占框高上限
TYPO_PAD_MIN_PX = 4                 # 判定"无内边距/贴边"的像素阈值
TYPO_BODY_MIN_PCT = 2.5             # 规则③：正文字号 / 画布高 最低占比(%)
TYPO_CAPTION_MIN_PCT = 1.5          # 规则③：图注字号 / 画布高 最低占比(%)
TYPO_TITLE_LH_RANGE = (1.2, 1.3)    # 规则⑤：标题（含二级标题）行距倍率区间
TYPO_BODY_LH_RANGE = (1.4, 1.6)     # 规则⑤：正文行距倍率区间
TYPO_LH_TOLERANCE = 0.03            # 允许的取整/渲染误差余量

# 显式 class → 层级 覆盖表（优先于标签兜底），覆盖组件库里已知的"二级标题/
# 图注注释"类名——这些标签本身多是 h3/p/span，纯标签兜底会把它们误判成正文。
TYPO_CLASS_ROLE_MAP = {
    "subtitle": "body",  # 封面副标题：语义上是引导性正文，非独立标题层级
    "oh-hub-title": "title", "oh-node-title": "subtitle", "oh-node-desc": "caption",
    "mc-title": "title", "mc-title-row": "subtitle", "mc-desc": "caption",
    "ss-title": "title", "ss-plaque-title": "subtitle",
    "tgm-title-main": "title", "tgm-card-title": "subtitle", "tgm-desc": "caption",
    "tmi-title-main": "title", "tmi-row-title": "subtitle",
    "caption-bar": "caption", "caption-source": "caption",
    # "眉标"类小标签（CONTENTS/SECTION 等全大写短标签）语义上是装饰性标注，
    # 不是需要按正文 2.5% 底线量度的阅读正文，统一归为 caption（按图注/注释
    # 1.5% 底线量度），避免把这类刻意做小的设计元素误判成"正文字过小"。
    "eyebrow": "caption", "mc-eyebrow": "caption", "ss-eyebrow": "caption",
    "oh-hub-eyebrow": "caption", "tgm-eyebrow": "caption", "tmi-eyebrow": "caption",
    # num-anchor 变体的大数字下方口径小字（.num-note）语义上是数字面板的注释，
    # 不是独立阅读正文，按图注 1.5% 底线量度（与 mc-desc/tgm-desc 同类处理）；
    # 此前按标签兜底误判成 body（2.5% 底线），与同页 30px 导语正文的层级比值
    # 又天然 <1.2（两者都在"正文量级"区间挤在一起），是 num-anchor 组件本身
    # 的分类口径缺陷，非内容问题，故在此root-cause修复而非迁就单个项目改文案。
    "num-note": "caption",
}
# 参与"内边距是否存在/是否贴边"检查（规则②前半）的容器 class 关键词——覆盖
# 面宜广：零内边距、文字紧贴容器外边界，不论容器是"紧凑徽标盒"还是"多元素
# 内容卡"，都是真实缺陷（TASK-036 实测案例：.panel.gather-core 就属于后者，
# 零内边距文字贴边，理应命中）。不含 .tmi-row 这类"行内主要是留白引导线、
# 文字只是其中一小块"的宽松容器——那类容器本来就该有大片留白，不适用本检查。
TYPO_CONTAINER_TOKENS = (
    "panel", "card", "plaque", "node", "hub", "kpi-card", "group-card",
    "mc-card", "oh-node", "oh-hub", "ss-plaque", "tgm-card",
    "loop-node", "timeline-item", "compare-card",
)
# TASK-036 fix（Playwright 实测 project-changzheng8a P9/P13/P17/P19 发现的
# 校准问题）："文字占比 ≤75%"这条规则只对"设计上专为容纳单一简短内容而留出
# 呼吸感"的紧凑徽标盒有意义（目录卡片/KPI 数字卡/铭牌/环形节点——文字之外
# 大量留白是刻意设计）；对 group-card/compare-card/gather-core 这类"自身按
# 内容自适应高度（padding+内容撑开，无固定高度）、且天然包含标题+正文+列表
# 多元素"的内容卡片，文字接近甚至撑满可用高度是 CSS auto-size 的必然结果
# （容器本来就是照着内容的高度长出来的），套用 75% 阈值等于给几乎所有正常
# 内容卡片判假阳性——实测 P13（视觉截图确认排版正常、无拥挤无溢出）仍被
# 命中 92%/105%，P9 甚至到 107%（同样视觉正常）。占比检查只在这个更窄的
# "紧凑徽标盒"集合上执行；内边距/贴边检查仍用上面更广的 TYPO_CONTAINER_TOKENS
# （零内边距/真贴边是任何容器类型下都成立的真实缺陷，不受此收窄影响）。
TYPO_OCCUPANCY_RATIO_TOKENS = ("plaque", "oh-node", "oh-hub", "kpi-card", "mc-card", "tgm-card")
# 单行标题占框高 50%~70% 的适用范围更窄：只对"容器内容基本就是这一个标题、
# 没有编号/释义等其它子元素分享空间"的纯标题盒有意义（如 ss-plaque——铭牌内
# 只有一个 h3 标题，没有其它文本子节点）。oh-node/mc-card/tgm-card 即使某次
# 渲染因为 desc 字段为空导致"实测只测到 1 个文本元素"，容器本身的设计意图
# 仍是"编号+标题+释义"三元素共享空间，不是纯标题盒，不适用本子规则（实测
# project-changzheng8a P2 的 toc-orbit-hub 卫星节点因为 desc 字段为空触发过
# 这个误判，标题实际只占 17%~34%——但那是"这批节点这次没有释义文案"的正常
# 情况，不是标题字号过小的设计缺陷）。
TYPO_SINGLE_LINE_TITLE_TOKENS = ("plaque",)

_TYPO_ELEMENTS_JS = """
(() => {
  const slide = document.querySelector('.slide.is-active');
  if (!slide) return [];
  const classRoleMap = %s;
  const containerTokens = %s;
  const sels = 'h1,h2,h3,h4,p,li,td,figcaption,small,.body,.takeaway,.caption-bar,.caption-source';
  const seen = new Set();
  const out = [];
  function classifyRole(el) {
    for (const c of el.classList) { if (classRoleMap[c]) return classRoleMap[c]; }
    const tag = el.tagName.toLowerCase();
    if (tag === 'h1' || tag === 'h2') return 'title';
    if (tag === 'h3' || tag === 'h4') return 'subtitle';
    if (tag === 'figcaption' || tag === 'small') return 'caption';
    return 'body';
  }
  function findContainer(el) {
    let node = el.parentElement;
    let depth = 0;
    while (node && node !== slide && depth < 5) {
      const cls = Array.from(node.classList || []);
      if (cls.some(c => containerTokens.some(t => c.includes(t)))) {
        const r = node.getBoundingClientRect();
        const cs = getComputedStyle(node);
        return {
          cls: cls.join('.'),
          x: r.x, y: r.y, w: r.width, h: r.height,
          padTop: parseFloat(cs.paddingTop) || 0,
          padBottom: parseFloat(cs.paddingBottom) || 0,
          padLeft: parseFloat(cs.paddingLeft) || 0,
          padRight: parseFloat(cs.paddingRight) || 0,
        };
      }
      node = node.parentElement; depth++;
    }
    return null;
  }
  slide.querySelectorAll(sels).forEach(el => {
    if (seen.has(el)) return;
    seen.add(el);
    const text = (el.textContent || '').trim();
    if (!text) return;
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return;
    if (rect.bottom < 0 || rect.right < 0 || rect.left > window.innerWidth || rect.top > window.innerHeight) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    const fontSize = parseFloat(cs.fontSize) || 0;
    let lineHeight = parseFloat(cs.lineHeight);
    if (!lineHeight || isNaN(lineHeight)) lineHeight = fontSize * 1.2;
    out.push({
      tag: el.tagName.toLowerCase(),
      cls: Array.from(el.classList || []).join('.'),
      role: classifyRole(el),
      text: text.slice(0, 20),
      fontSize, lineHeight,
      x: rect.x, y: rect.y, w: rect.width, h: rect.height,
      container: findContainer(el),
    });
  });
  return out;
})()
""" % (json.dumps(TYPO_CLASS_ROLE_MAP, ensure_ascii=False), json.dumps(TYPO_CONTAINER_TOKENS, ensure_ascii=False))


def collect_typography_elements(page):
    try:
        return page.evaluate(_TYPO_ELEMENTS_JS) or []
    except Exception:
        return []


def check_font_hierarchy(elements):
    """规则①：本页出现的字号层级两两相邻（从大到小排序）比值需 ≥1.2；
    低于下限即视为"多个文本字号大小接近、无视觉区分"命中。"""
    sizes = sorted({round(e["fontSize"], 1) for e in elements if e["fontSize"] > 0}, reverse=True)
    hits = []
    for a, b in zip(sizes, sizes[1:]):
        if b <= 0:
            continue
        ratio = a / b
        if ratio < TYPO_LEVEL_RATIO_MIN:
            ex_a = next((e for e in elements if round(e["fontSize"], 1) == a), None)
            ex_b = next((e for e in elements if round(e["fontSize"], 1) == b), None)
            hits.append(
                f"字号层级区分不足：{a:.1f}px（如 {ex_a['tag']}.{ex_a['cls']} \"{ex_a['text']}\"）与 "
                f"{b:.1f}px（如 {ex_b['tag']}.{ex_b['cls']} \"{ex_b['text']}\"）倍率仅 {ratio:.2f} < 下限 {TYPO_LEVEL_RATIO_MIN}"
            )
    return hits


def check_textbox_occupancy(elements):
    """规则②：文本框内文字占用高度占比、内边距、贴边、单行标题占比。"""
    hits = []
    groups = {}
    for e in elements:
        c = e.get("container")
        if not c:
            continue
        key = (round(c["x"]), round(c["y"]), round(c["w"]), round(c["h"]), c["cls"])
        groups.setdefault(key, {"container": c, "elems": []})["elems"].append(e)
    for g in groups.values():
        c = g["container"]
        elems = g["elems"]
        avail_h = c["h"] - c["padTop"] - c["padBottom"]
        if avail_h <= 0:
            continue
        top = min(e["y"] for e in elems)
        bottom = max(e["y"] + e["h"] for e in elems)
        text_h = bottom - top
        ratio = text_h / avail_h
        is_compact_box = any(tok in c["cls"] for tok in TYPO_OCCUPANCY_RATIO_TOKENS)
        if is_compact_box and ratio > TYPO_BOX_OCCUPANCY_MAX:
            hits.append(
                f"文本框占比超限：{c['cls']} 内文字实测高度 {text_h:.0f}px / 可用高度 {avail_h:.0f}px "
                f"= {ratio * 100:.0f}% > 上限 {TYPO_BOX_OCCUPANCY_MAX * 100:.0f}%"
            )
        if c["padTop"] < TYPO_PAD_MIN_PX and c["padBottom"] < TYPO_PAD_MIN_PX and c["padLeft"] < TYPO_PAD_MIN_PX and c["padRight"] < TYPO_PAD_MIN_PX:
            hits.append(
                f"文本框四周无内边距：{c['cls']}（padding 实测上{c['padTop']:.0f}/右{c['padRight']:.0f}/"
                f"下{c['padBottom']:.0f}/左{c['padLeft']:.0f}px）"
            )
        else:
            # 贴边判定必须用容器"外边界"（border-box 边缘），不能用 padding 内边界——
            # 文字紧贴 padding 内边界是任何有 padding 的盒子的正常状态（padding 本身
            # 就是"文字从这里开始"的分界线，不代表"贴边"）。真正的贴边/溢出信号是
            # 文字逼近甚至超出容器外边界本身（padding 名存实亡、或内容把 padding
            # 撑没了），阈值仍用 TYPO_PAD_MIN_PX，但比较对象换成 c['y']/c['y']+c['h']。
            # 实测验证：用刻意构造的 padding:32px 合规卡片跑过本函数，此前误用
            # padding 内边界比较会对几乎所有正常加了 padding 的卡片假阳性命中。
            if top - c["y"] < TYPO_PAD_MIN_PX:
                hits.append(f"文字顶边框：{c['cls']} 文字顶部与容器外边界仅差 {top - c['y']:.1f}px")
            if (c["y"] + c["h"]) - bottom < TYPO_PAD_MIN_PX:
                hits.append(f"文字触底边框：{c['cls']} 文字底部与容器外边界仅差 {(c['y'] + c['h']) - bottom:.1f}px")
        # 单行标题占框高 50%~70%：只在该容器内被测文本元素只有这一项、且容器
        # 属于"纯标题盒"集合（TYPO_SINGLE_LINE_TITLE_TOKENS）时才检查——避免
        # "标题只是框内标题+释义两段文字之一，这次释义恰好是空字符串"的正常
        # 情况被误判（如 toc-orbit-hub 卫星节点 desc 为空时的真实案例）。
        is_title_box = any(tok in c["cls"] for tok in TYPO_SINGLE_LINE_TITLE_TOKENS)
        if is_title_box and len(elems) == 1:
            e = elems[0]
            if e["role"] in ("title", "subtitle"):
                approx_lines = max(1, round(e["h"] / max(e["lineHeight"], 1)))
                if approx_lines <= 1:
                    ratio2 = e["h"] / avail_h
                    if not (TYPO_SINGLE_LINE_TITLE_MIN <= ratio2 <= TYPO_SINGLE_LINE_TITLE_MAX):
                        hits.append(
                            f"单行标题占框高比例超出区间：{e['tag']}.{e['cls']} \"{e['text']}\" "
                            f"实测 {ratio2 * 100:.0f}%，要求 {TYPO_SINGLE_LINE_TITLE_MIN * 100:.0f}%~{TYPO_SINGLE_LINE_TITLE_MAX * 100:.0f}%"
                        )
    return hits


def check_canvas_floor(elements):
    """规则③：16:9 画布下正文/图注文字的最小可读性底线（相对画布高 1080px）。"""
    hits = []
    for e in elements:
        pct = e["fontSize"] / TYPO_CANVAS_H * 100
        if e["role"] == "body" and pct < TYPO_BODY_MIN_PCT:
            hits.append(
                f"正文文字过小：{e['tag']}.{e['cls']} \"{e['text']}\" 字号 {e['fontSize']:.1f}px "
                f"= 画布高度 {pct:.2f}% < 下限 {TYPO_BODY_MIN_PCT}%"
            )
        elif e["role"] == "caption" and pct < TYPO_CAPTION_MIN_PCT:
            hits.append(
                f"图注/注释文字过小：{e['tag']}.{e['cls']} \"{e['text']}\" 字号 {e['fontSize']:.1f}px "
                f"= 画布高度 {pct:.2f}% < 下限 {TYPO_CAPTION_MIN_PCT}%"
            )
    return hits


def check_line_spacing(elements):
    """规则⑤：正文行距 1.4~1.6 倍，标题（含二级标题）行距 1.2~1.3 倍；
    图注/注释用户未给出量化区间，不纳入本规则。"""
    hits = []
    for e in elements:
        if e["fontSize"] <= 0:
            continue
        ratio = e["lineHeight"] / e["fontSize"]
        if e["role"] in ("title", "subtitle"):
            lo, hi = TYPO_TITLE_LH_RANGE
            label = "标题"
        elif e["role"] == "body":
            lo, hi = TYPO_BODY_LH_RANGE
            label = "正文"
        else:
            continue
        if not (lo - TYPO_LH_TOLERANCE <= ratio <= hi + TYPO_LH_TOLERANCE):
            hits.append(
                f"行距超出区间：{e['tag']}.{e['cls']} \"{e['text']}\" 实测 {ratio:.2f} 倍，"
                f"要求 {lo}~{hi} 倍（{label}）"
            )
    return hits


# 规则④：px 硬编码静态扫描（提示项，不计入分数扣减）。只找真正的 font-size
# 属性声明，且未被 clamp()/vh/%/var() 相对写法包裹的情况——写死 px 在部分
# 场景是合理设计选择（如固定像素的图标类小字），由人工复核决定是否改写，
# 不做成阻断性硬失败。
FONT_SIZE_PX_RE = re.compile(r"font-size\s*:\s*[\d.]+px")


def scan_hardcoded_font_px(root_dir):
    """扫描 assets/components/*.css 与 assets/themes/*.css，返回
    "文件:行号: 代码片段" 列表，供 QA 报告登记为人工复核清单。"""
    hits = []
    for pattern in ("assets/components/*.css", "assets/themes/*.css"):
        for path in sorted(Path(root_dir).glob(pattern)):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if "font-size" not in line or "px" not in line:
                    continue
                if "clamp(" in line or "vh" in line or "%" in line or "var(--" in line:
                    continue
                if FONT_SIZE_PX_RE.search(line):
                    hits.append(f"{path.name}:{i}: {line.strip()}")
    return hits


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
                # TASK-011 fix: 溢出判定附实测像素，便于定位纵向/横向溢出（如计数变体幻影节点撑高页面）
                dims = page.evaluate(
                    "(() => { const el = document.querySelector('.slide.is-active');"
                    " if (!el) return null;"
                    " return {sh: el.scrollHeight, ch: el.clientHeight, sw: el.scrollWidth, cw: el.clientWidth}; })()"
                )
                overflow = bool(dims) and (dims["sh"] > dims["ch"] + 4 or dims["sw"] > dims["cw"] + 4)
                # TASK-028: 并列容器尺寸一致性——在禁用动画、真实布局稳定后测量
                uniformity_hits = check_sibling_uniformity(page)
                page.add_style_tag(content=".slide * { animation: none !important; }")
                shot_path = out_dir / f"slide-{i:02d}.png"
                page.screenshot(path=str(shot_path))
                visible = page.locator(".slide.is-active").count() == 1
                score = 100
                issues = []
                if not visible:
                    score -= 25
                    issues.append("当前页可见状态异常")
                if overflow:
                    score -= 20
                    issues.append(f"页面内容溢出屏幕（scrollHeight {dims['sh']} / clientHeight {dims['ch']}，scrollWidth {dims['sw']} / clientWidth {dims['cw']}）")
                if uniformity_hits:
                    score -= min(30, 15 * len(uniformity_hits))
                    for hit in uniformity_hits:
                        issues.append(
                            f"并列容器尺寸不一致：{hit['label']}（{hit['count']} 个），"
                            f"高度差 {hit['hDiff']}px（{hit['minH']}~{hit['maxH']}px）、"
                            f"宽度差 {hit['wDiff']}px（{hit['minW']}~{hit['maxW']}px），超出阈值"
                        )
                # TASK-033: 规则A（标题级文字字号/对比度下限）+ 规则B（背景色漂移检测）——
                # 用户反馈固化的永久质量门禁，基于本页刚截好的真实渲染像素测量。
                try:
                    from PIL import Image
                    shot_img = Image.open(shot_path)
                    title_hits = check_title_prominence(page, shot_img)
                    if title_hits:
                        score -= min(30, 10 * len(title_hits))
                        issues.extend(title_hits)
                    bg_hits = check_background_drift(page, shot_img)
                    if bg_hits:
                        score -= 20
                        issues.extend(bg_hits)
                except Exception as exc:
                    print(f"规则A/B像素检测跳过（{exc}）", file=sys.stderr)
                # TASK-036: 字体排版检查体系（规则①层级比例/②文本框占比/
                # ③画布相对底线/⑤行距配套），同样基于本页刚测量的真实渲染。
                try:
                    typo_elements = collect_typography_elements(page)
                    hierarchy_hits = check_font_hierarchy(typo_elements)
                    if hierarchy_hits:
                        score -= min(20, 8 * len(hierarchy_hits))
                        issues.extend(hierarchy_hits)
                    box_hits = check_textbox_occupancy(typo_elements)
                    if box_hits:
                        score -= min(25, 8 * len(box_hits))
                        issues.extend(box_hits)
                    floor_hits = check_canvas_floor(typo_elements)
                    if floor_hits:
                        score -= min(25, 10 * len(floor_hits))
                        issues.extend(floor_hits)
                    lh_hits = check_line_spacing(typo_elements)
                    if lh_hits:
                        score -= min(15, 4 * len(lh_hits))
                        issues.extend(lh_hits)
                except Exception as exc:
                    print(f"字体排版检查跳过（{exc}）", file=sys.stderr)
                rows.append({"page": slide.get("page"), "score": max(0, score), "mode": "playwright", "issues": issues})
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
    # TASK-009: 布局门禁读取 state/visual_blueprints.md（默认与 --history 同目录）
    bp_path = args.blueprints or (Path(args.history).parent / "visual_blueprints.md")
    blueprints = parse_visual_blueprints(bp_path)
    rows = try_playwright(args, ir)
    if rows is None:
        rows = structural(text, ir, art_dna, semantics, blueprints)
    else:
        # playwright 模式同样执行内容容量规则，两种检查取并集；B.3(b) 的估算溢出
        # 检查跳过（skip_overflow_estimate=True）——真实 scrollHeight/scrollWidth
        # 测量已经存在于 rows 里，不需要近似公式再重复判一次，避免估算系统性
        # 高估（尤其多列格阵变体）在有真实数据时反而误伤已验证不溢出的页面。
        struct_map = {r["page"]: r for r in structural(text, ir, art_dna, semantics, blueprints, skip_overflow_estimate=True)}
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
    # TASK-005/TASK-043: art DNA 来源标注，区分 像素提取 / md 解读 / 主题域合成 / 降级
    if art_dna is None:
        art_dna_label = "fallback（无项目视觉 DNA，基础主题装饰降级）"
    elif art_dna.get("source_mode") == "md":
        art_dna_label = "md（图片 md 解读路径，生成式融合背景）"
    elif art_dna.get("source_mode") == "domain-only":
        art_dna_label = "domain-only（无图片，按主题域+关键词合成背景，非固定骨架降级）"
    else:
        art_dna_label = "image（图片像素提取路径）"
    mode = rows[0]["mode"] if rows else "none"
    report = ["# QA Report", "", f"- mode: {mode}", f"- art_dna: {art_dna_label}", f"- pages: {len(rows)}", f"- average_score: {avg:.1f}", f"- failed_pages: {len(failed)}"]
    if mode == "structural-fallback":
        # TASK-021 B.3(a): 降级路径的报告内醒目警告——避免"分数很高但其实没做真实
        # 像素测量"的假通过重演（此前 98.5 分假通过的根因）。
        report += [
            "",
            "## ⚠️ WARNING: 本轮 QA 未使用 Playwright 真实像素测量 ⚠️",
            "- 当前结果全部来自 structural-fallback 静态兜底（正则扫描 HTML 源码 + 字符数估算），",
            "  **不代表**逐页 scrollHeight/scrollWidth 真实测量结果，不能作为最终交付依据。",
            "- 请先执行：`pip install playwright` 与 `python -m playwright install chromium`，",
            "  再重跑本脚本，直到 `mode: playwright` 才可信任分数与 failed_pages 结论。",
        ]
    report += ["", "## Page Scores"]
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
    # TASK-036 规则④：px 硬编码字号静态扫描——提示项，不计入分数/失败判定，
    # 供人工复核是否需要改为 clamp()/vh/%/var() 相对单位。
    px_hits = scan_hardcoded_font_px(Path(__file__).resolve().parent.parent)
    report += ["", "## Typography Px Audit（规则④·提示项，不计入失败判定）"]
    if px_hits:
        report.append(f"- 命中 {len(px_hits)} 处 font-size 硬编码 px（未用 clamp()/vh/%/var() 相对单位包裹），建议人工复核：")
        report.extend(f"  - {h}" for h in px_hits)
    else:
        report.append("- 未发现硬编码 px 字号声明（或均已使用 clamp()/vh/%/var() 相对单位）。")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(str(out))
    return 1 if failed or (coverage and coverage["missing"]) else 0


if __name__ == "__main__":
    sys.exit(main())
