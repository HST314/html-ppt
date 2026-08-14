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
    "warm-human", "minimal-white"
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
