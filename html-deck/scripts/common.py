#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

ROLES = {
    "cover", "toc", "section", "bullets", "two-column", "image-hero",
    "image-side", "gallery", "table", "kpi", "quote", "compare",
    "timeline", "closing"
}
THEMES = {
    "business-dark", "business-light", "tech-dark", "editorial",
    "warm-human", "minimal-white", "proposal-light"  # TASK-009: 默认视觉方向主题（浅色高亮/深蓝骨架/青蓝辅助）
}


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def now():
    return datetime.now(timezone.utc).isoformat()


# ── TASK-028/TASK-030: 主题线条插画装饰机制（通用能力，供 extract_art_dna.py 与
# art_dna_from_md.py 共用；机制文档见 references/ART_DNA.md「主题线条插画
# 装饰机制」）───────────────────────────────────────────────────────────
# TASK-030 fix：此前只允许叠到骨架页（封面/章节过渡/目录/尾页），内容页完全
# 没有插画。用户明确要求把封面的插画效果推广到"每一个页面"——内容页角色
# 现在也放开，允许项目在 art_motifs.json 里显式登记内容页角色。放开这道
# 白名单只是"允许登记"，不等于"内容页会被随意糊满图案"：真正的可读性纪律
# 落在 render_deck.py 侧——① 项目未显式登记的内容页角色，由 render_deck.py
# 的通用兜底机制（按页面文本关键词打分选素材、每页最多 1 个、透明度比骨架页
# 更低、位置避开正文实际占据区域）自动接管，不需要每个项目手工登记；
# ② 显式登记的角色照旧信任项目侧登记的位置/透明度/尺寸，不做二次限制。
MOTIF_ROLES = set(ROLES)
MOTIF_POSITIONS = {
    "motif-pos-tr", "motif-pos-br", "motif-pos-tl", "motif-pos-bl",
    "motif-pos-br-wide", "motif-pos-tl-wide", "motif-pos-full",
}


def attach_motifs(report, motifs_path, outdir):
    """若项目在 state/ 下提供 art_motifs.json（Agent 从项目图片/图片描述人工
    提炼的主题图形关键词 -> 线条 SVG 素材映射，schema 见 references/ART_DNA.md），
    把选中的素材复制进 art_dna 资产目录（outdir/motifs/），并把可渲染结构写进
    report["motifs"]，供 render_deck.py 逐页按角色叠加为低透明度装饰层。

    这是可选增量能力：文件不存在、无法解析、或没有任何一条素材通过校验时，
    静默跳过并原样返回 report（不阻断 art_dna 主产物生成），只在 stderr 打印
    可诊断的跳过原因，不抛异常。"""
    motifs_path = Path(motifs_path)
    if not motifs_path.exists():
        return report
    try:
        spec = read_json(motifs_path)
    except Exception as exc:
        print(f"art_motifs 读取失败，跳过主题插画装饰层：{exc}")
        return report
    assets = spec.get("assets") or []
    if not assets:
        return report
    skill_root = Path(__file__).resolve().parents[1]
    outdir = Path(outdir)
    motif_dir = outdir / "motifs"
    resolved = []
    for item in assets:
        src_rel = item.get("file")
        roles = [r for r in (item.get("roles") or []) if r in MOTIF_ROLES]
        position = item.get("position")
        if not src_rel or not roles or position not in MOTIF_POSITIONS:
            print(f"art_motifs 条目字段不完整（file/roles/position 需齐全，position 需在预设内），已跳过：{item}")
            continue
        src = Path(src_rel)
        if not src.is_absolute():
            src = skill_root / src_rel
        if not src.exists():
            print(f"art_motifs 素材文件不存在，已跳过：{src}")
            continue
        motif_dir.mkdir(parents=True, exist_ok=True)
        dest = motif_dir / src.name
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        resolved.append({
            "id": item.get("id") or src.stem,
            "label": item.get("label") or item.get("id") or src.stem,
            "file": f"{outdir.name}/motifs/{src.name}",
            "roles": roles,
            "position": position,
            "opacity": float(item.get("opacity", 0.14)),
            "size": int(item.get("size", 320)),
            # TASK-030: 内容页通用兜底选择机制用的关键词触发表（可选字段，
            # 项目未登记时按空表处理，render_deck.py 侧自动退化为按章节序号
            # 轮换，不阻断——见 render_deck.py::select_content_motif 注释）。
            "content_keywords": [str(k) for k in (item.get("content_keywords") or [])],
        })
    if resolved:
        report["motifs"] = {"keywords": spec.get("keywords") or [], "assets": resolved}
    return report


def load_state(path):
    p = Path(path)
    if not p.exists():
        return {
            "current_phase": "init",
            "completed_pages": [],
            "qa_round": 0,
            "errors": [],
            "checkpoints": [],
            "updated_at": now(),
        }
    try:
        return read_json(p)
    except Exception:
        backup = p.with_suffix(".corrupt.json")
        p.replace(backup)
        return {
            "current_phase": "recovered",
            "completed_pages": [],
            "qa_round": 0,
            "errors": [{"at": now(), "message": "state corrupted; backed up to " + str(backup)}],
            "checkpoints": [],
            "updated_at": now(),
        }


def save_state(path, state, phase=None, checkpoint=None):
    if phase:
        state["current_phase"] = phase
    if checkpoint:
        state.setdefault("checkpoints", []).append({"at": now(), "name": checkpoint})
    state["updated_at"] = now()
    write_json(path, state)


def rel_to(base_file, maybe_relative):
    p = Path(maybe_relative)
    if p.is_absolute():
        return p
    return Path(base_file).resolve().parent / p


def no_abs_path(text):
    cwd = os.getcwd()
    return cwd not in text


# ── TASK-003: 页面语义登记（state/page_semantics.md）共享解析 ──────────────
# page_semantics.md 由「页面语义分析层」逐页落盘，表格列：
# 页码 / 主结论 / 逻辑类型 / 视觉结构 / 视觉焦点 / 信息组划分 / 选定 role / 选role理由
# 「信息组划分」单元格机器可读约定（build_ir.py / qa_render.py 共用解析）：
#   组标题：条目一、条目二；组标题：条目三、条目四
#   组之间用「；」或「;」分隔，组标题与条目之间用「：」或「:」分隔，
#   条目之间用「、」「，」「,」或「｜」分隔；组标题允许带「组1」「(1)」等枚举前缀。
#   单元格为「无」「—」「N/A」或含「不分组」时视为未登记分组。

# 非 deck 正文来源的自动页 decision 前缀（封面/目录/章节/自动拆页/兜底页等）
AUTO_DECISION_PREFIXES = (
    "level-1 title becomes cover",
    "mandatory toc",
    "new level-2 section",
    "auto-split gallery part",
    "automatic closing decision page",
    "automatic low-load closing",
    "unplaced images isolated",
    "unrelated image isolated",
)
NON_CONTENT_ROLES = {"cover", "toc", "section", "closing"}


def is_deck_content_slide(slide):
    """TASK-003: 判定 IR 页是否来自 deck.md 的 ### 正文页（需语义登记）。"""
    if slide.get("role") in NON_CONTENT_ROLES:
        return False
    decision = (slide.get("decision") or "").strip()
    return not any(decision.startswith(p) for p in AUTO_DECISION_PREFIXES)


def parse_groups_cell(cell):
    """TASK-003: 解析「信息组划分」单元格 → [{title, items[]}]；未登记分组返回 []。"""
    s = (cell or "").strip()
    if not s or s in {"N/A", "n/a", "无"} or re.fullmatch(r"[-—–/]+", s):
        return []
    if "不分组" in s or "无需分组" in s or "无需归组" in s:
        return []
    groups = []
    for chunk in re.split(r"[；;]", s):
        chunk = chunk.strip().strip("。")
        if not chunk:
            continue
        parts = re.split(r"[：:]", chunk, maxsplit=1)
        if len(parts) == 2:
            title, rest = parts
        else:
            m = re.match(r"^[「【\"'](.+?)[」】\"']\s*(.+)$", chunk)
            if not m:
                continue
            title, rest = m.group(1), m.group(2)
        # 去掉组标题的枚举前缀（组1 / (1) / G2 等），保留标题正文
        title = re.sub(r"^\s*(?:组|group|G)\s*\d+\s*[)）.、：:-]?\s*", "", title, flags=re.I)
        title = re.sub(r"^[（(]\s*\d+\s*[)）]\s*", "", title)
        title = title.strip(" 「」【】\"'")
        items = []
        for x in re.split(r"[、，,｜]", rest):
            x = re.sub(r"^\s*\d+\s*[.、)]\s*", "", x).strip(" 「」【】\"'。")
            if x:
                items.append(x)
        if title and items:
            groups.append({"title": title, "items": items})
    return groups


def parse_page_semantics(path):
    """TASK-003: 解析 state/page_semantics.md → {页序号(int): row}；文件缺失返回 None。"""
    p = Path(path)
    if not p.exists():
        return None
    header = None
    rows = {}
    order = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            if any("页码" in c for c in cells) and any("role" in c.lower() for c in cells):
                header = cells
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        order += 1

        def col(keyword):
            for i, h in enumerate(header):
                if keyword in h.lower() and i < len(cells):
                    return cells[i]
            return ""

        page_cell = col("页码")
        m = re.search(r"\d+", page_cell)
        page_no = int(m.group()) if m else order
        rows[page_no] = {
            "page": page_no,
            "conclusion": col("主结论"),
            "logic": col("逻辑"),
            # TASK-022: 「正文关系」列（并列/递进/因果/对比/总分/层级）单独取出，
            # 供 render_deck.py 判断列表是否该用数字编号（只有真实先后顺序才编号）。
            # 用「关系」而非「逻辑」做关键字匹配，避免命中同表更靠前的「逻辑类型」列。
            "relation": col("关系"),
            "structure": col("视觉结构"),
            "focus": col("焦点"),
            "groups_cell": col("信息组"),
            "groups": parse_groups_cell(col("信息组")),
            "role": col("role").strip(" `"),
            "reason": col("理由"),
        }
    return rows


def _norm_text(s):
    """TASK-003: 归一化文本用于语义分组条目与 slide 列表条目的模糊匹配。"""
    return re.sub(r"[\s，。、：:；;,.・·\"'「」【】（）()\-—…!?！？]", "", (s or "").lower())


def match_groups_to_items(row_groups, slide_items):
    """TASK-003: 把登记分组映射到 slide 实际列表条目。

    仅当 2–4 组、每组至少匹配 1 条、且 slide 列表条目被分组全覆盖时返回
    [{title, items(实际条目文本)[]}]，否则返回 None（调用方走扁平兜底）。
    """
    remaining = list(slide_items)
    out = []
    for g in row_groups:
        picked = []
        for gi in g.get("items", []):
            ngi = _norm_text(gi)
            if not ngi:
                continue
            best = None
            for cand in remaining:
                nc = _norm_text(cand)
                if nc and (ngi in nc or nc in ngi):
                    if best is None or len(nc) > len(_norm_text(best)):
                        best = cand
            if best is not None:
                picked.append(best)
                remaining.remove(best)
        if picked:
            out.append({"title": g.get("title", ""), "items": picked})
    if len(out) != len(row_groups):
        return None
    if remaining:
        return None
    if not (2 <= len(out) <= 4):
        return None
    return out


# ── TASK-009: 视觉蓝图（state/visual_blueprints.md）共享解析 ──────────────
# visual_blueprints.md 由「视觉布局决策引擎」第②③步逐页落盘，表格列：
# 页码 / 布局pattern / 变体 / 视觉焦点 / 标题位置 / 主体区域 / 辅助信息区域 / 留白比例 / SVG需求 / 图片需求 / 选型理由
# 布局签名 = pattern + 变体；连续内容页签名相同即违反连页变体禁令（QA 判失败）。

# 12 种登记 layout pattern（key → 中文名），与 references/layout-patterns.md 一致
LAYOUT_PATTERNS = {
    "center-hub": "中心节点+分支",
    "tri-loop": "三模块闭环",
    "path-flow": "路径式流程",
    "timeline": "时间轴",
    "compare": "对比构图",
    "big-number": "数据大数字",
    "matrix": "矩阵",
    "text-image": "左文右图",
    "asym-mix": "非对称图文",
    "product-hero": "产品英雄图",
    "hero-details": "主图+细节",
    "hierarchy-space": "层级空间结构",
}

# 蓝图「布局pattern」单元格别名归一（中文名/序号/英文别名 → key）
_PATTERN_ALIASES = {
    "中心节点+分支": "center-hub", "中心节点与分支": "center-hub", "中心节点": "center-hub",
    "三模块闭环": "tri-loop", "三环闭环": "tri-loop",
    "路径式流程": "path-flow", "路径流程": "path-flow",
    "时间轴": "timeline",
    "对比构图": "compare",
    "数据大数字": "big-number", "大数字": "big-number",
    "矩阵": "matrix",
    "左文右图": "text-image",
    "非对称图文": "asym-mix",
    "产品英雄图": "product-hero", "英雄图": "product-hero",
    "一张主图+1-3个细节": "hero-details", "一张主图+1–3个细节": "hero-details",
    "主图+细节": "hero-details", "主图加细节": "hero-details",
    # TASK-021（测试补漏）：LAYOUT_PATTERNS 唯一遗漏的中文名别名——12 种 pattern
    # 里其余 11 种的中文名都在本表登记了反查别名，只有「层级空间结构」缺失，
    # 导致蓝图按文档字面写法登记该 pattern 时被误判为「未登记于 12 种模式」。
    "层级空间结构": "hierarchy-space", "层级结构": "hierarchy-space", "分层结构": "hierarchy-space",
}

# 蓝图八字段（空缺即 QA 判失败）：内部键 → 表头关键字
BLUEPRINT_FIELDS = {
    "focus": "焦点",
    "title_pos": "标题位置",
    "main_area": "主体区域",
    "aux_area": "辅助信息",
    "whitespace": "留白比例",
    "svg_need": "SVG",
    "image_need": "图片需求",
    "reason": "选型理由",
}

# 蓝图「图片需求」声明需要图片的取值（无图项目命中时按冲突裁决降级）
_IMAGE_REQUIRED_TOKENS = ("是", "必需", "必须", "需要")


# ── TASK-021: 视觉变体固定词表 + 语义归一映射 ──────────────────────────────
# layouts.css 里真实注册的 layout-<variant> 选择器词表（渲染/QA 的唯一校验依据）。
# 22 个 slug，覆盖 references/layout-patterns.md §12.5 结构级变体 + 原有 9 类变体族。
# 注：hub-radiate 的 .layout-hub-radiate CSS 规则仍物理保留在 layouts.css 里
# （未删除，供历史内容/未来恢复引用），但归一逻辑已并入 hub-left（见下方
# _VARIANT_ALIASES）——两者共用 split_generic_html() 渲染出口，DOM 结构完全
# 相同，差异只在描边/光晕这类纯样式层面，不构成 §9 四元组签名意义上的结构
# 差异，因此不再作为独立注册词保留在校验词表里，避免归一时被精确匹配短路。
LAYOUT_VARIANTS = {
    "grid-2x2", "grid-2x3",
    "asym-cards", "anchor-right", "cause-effect", "num-anchor",
    "hub-left", "hub-return", "hub-top", "hub-spoke", "gather-3",
    "vs-split",
    "loop-3", "loop-4",
    "ascend-4", "chain-3", "chain-4", "ed-strip",
    "checkpoint-3",
    "layers-3", "layers-4", "layers-5",
}

# 变体族数字上限（原始 variant 带数字但超出注册词表时，夹到族内最大已注册值）
_VARIANT_FAMILY_CLAMP = {
    "chain": (3, 4), "loop": (3, 4), "ascend": (4, 4),
    "checkpoint": (3, 3), "layers": (3, 5),
}

# 已知自由文本漂移 → 固定词表 slug 的精确别名（历史蓝图里出现过的写法）
_VARIANT_ALIASES = {
    "grid-2col": "grid-2x2", "grid-2-col": "grid-2x2", "grid-2column": "grid-2x2",
    "grid-3x1": "grid-2x2", "grid-3col": "grid-2x2", "grid-3-col": "grid-2x2",
    "grid-2group": "grid-2x3", "grid-2group-warm-cool": "grid-2x3",
    "img-anchor-right": "anchor-right", "img-anchor-right-layered": "anchor-right",
    # hub-radiate 与 hub-left 共用同一套渲染出口（split_generic_html），DOM 结构
    # 完全相同，仅描边/光晕这类纯样式差异，不构成结构签名意义上的独立变体，
    # 归一到 hub-left；.layout-hub-radiate CSS 规则本身不删，只是不再被产出。
    "hub-radiate": "hub-left",
    "hero-left-info-right": "", "hero-right-info-left": "",
    "details-3": "", "table-5x4": "", "kpi-4col": "", "gallery-5": "",
}

# 语义归一子串匹配（顺序敏感，先匹配到先返回）：raw variant 里出现该子串即归一到目标 slug
# 注：checkpoint/ascend/chain/loop/layers 优先走上面的族数字夹取；此处兜底命中
# 无数字或数字解析失败的写法（如 "hub-top-split" 之类的自由发挥后缀）。
_VARIANT_SUBSTRING_HINTS = (
    ("hub-top", "hub-top"),
    ("hub-spoke", "hub-spoke"),
    ("hub-radiate", "hub-left"),
    ("hub-return", "hub-return"),
    ("hub-left", "hub-left"),
    ("hub", "hub-left"),
    ("gather", "gather-3"),
    ("num-anchor", "num-anchor"),
    ("anchor-right", "anchor-right"),
    ("cause-effect", "cause-effect"),
    ("vs-split", "vs-split"),
    ("vs", "vs-split"),
    ("asym", "asym-cards"),
    ("ed-strip", "ed-strip"),
    ("grid-2x3", "grid-2x3"),
    ("grid-2x2", "grid-2x2"),
    ("grid", "grid-2x2"),
)


def normalize_layout_variant(pattern_key, raw_variant):
    """TASK-021: 归一蓝图「变体」自由文本 → LAYOUT_VARIANTS 固定词表 slug。

    不是精确匹配失败就置空——先精确匹配，再查已知别名表，再按变体族解析数字
    （如 chain-6 的 6 先解析出来，再夹到该族已注册的最大值 chain-4），最后按
    子串语义提示归一（如 hero-left-info-right 里出现 hub 相关词根）。
    仍无法合理归一时返回空字符串（调用方保留原角色默认渲染，不强行套壳），
    调用方需把归一过程记入 decision，供 QA 追溯，不静默丢弃。
    """
    s = (raw_variant or "").strip().strip("` ").lower()
    if not s:
        return "", "empty"
    if s in LAYOUT_VARIANTS:
        return s, "exact"
    if s in _VARIANT_ALIASES:
        return _VARIANT_ALIASES[s], "alias"
    # 变体族 + 数字：先解析家族前缀与数字，再夹到该族已注册的上限
    m = re.match(r"^([a-z]+)-(\d+)", s)
    if m:
        family, num = m.group(1), int(m.group(2))
        if family in _VARIANT_FAMILY_CLAMP:
            lo, hi = _VARIANT_FAMILY_CLAMP[family]
            clamped = max(lo, min(hi, num))
            candidate = f"{family}-{clamped}"
            if candidate in LAYOUT_VARIANTS:
                return candidate, f"family-clamp({num}->{clamped})"
    # 子串语义提示（顺序敏感，跳过占位 None 目标——这些已在族数字夹取里处理过）
    for needle, target in _VARIANT_SUBSTRING_HINTS:
        if target and needle in s:
            return target, f"substring-hint({needle})"
    return "", "unmapped"


def normalize_layout_pattern(cell):
    """TASK-009: 归一布局 pattern 单元格 → 登记 key；未登记返回归一后的原文。"""
    s = (cell or "").strip().strip("` ")
    s = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫]\s*", "", s)
    s = re.sub(r"^\d+\s*[.、)）]\s*", "", s)
    if s in LAYOUT_PATTERNS:
        return s
    if s in _PATTERN_ALIASES:
        return _PATTERN_ALIASES[s]
    low = s.lower()
    if low in LAYOUT_PATTERNS:
        return low
    for name, key in _PATTERN_ALIASES.items():
        if name in s:
            return key
    return s


def blueprint_image_required(row):
    """TASK-009: 蓝图是否声明需要图片（冲突裁决：无图项目须降级）。"""
    v = (row.get("image_need") or "").strip()
    return any(t in v for t in _IMAGE_REQUIRED_TOKENS) and not v.startswith(("否", "不"))


def parse_visual_blueprints(path):
    """TASK-009: 解析 state/visual_blueprints.md → {页序号(int): row}；文件缺失返回 None。"""
    p = Path(path)
    if not p.exists():
        return None
    header = None
    rows = {}
    order = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            if any("页码" in c for c in cells) and any("pattern" in c.lower() or "布局" in c for c in cells):
                header = cells
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        order += 1

        def col(keyword):
            for i, h in enumerate(header):
                if keyword.lower() in h.lower() and i < len(cells):
                    return cells[i]
            return ""

        page_cell = col("页码")
        m = re.search(r"\d+", page_cell)
        page_no = int(m.group()) if m else order
        row = {
            "page": page_no,
            "pattern": normalize_layout_pattern(col("pattern") or col("布局")),
            "variant": (col("变体") or "").strip().strip("` ").lower(),
        }
        for key, kw in BLUEPRINT_FIELDS.items():
            row[key] = col(kw)
        rows[page_no] = row
    return rows
