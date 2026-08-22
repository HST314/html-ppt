#!/usr/bin/env python3
"""TASK-005: 无像素输入时的 art DNA 生成路径——消费图片 md 解读清单。

适用场景：项目没有可读图片（extract_art_dna.py 的像素提取路径无法运行），
但存在图片 md 解读文档。Agent 按 references/ART_DNA.md「无像素输入：图片 md
解读路径」一节，从 md 解读中提取 8 维度视觉事实并落盘为机器可读清单
（state/art_dna_md.json），本脚本校验清单完整性后，复用 extract_art_dna.py
的同一套 svg() 生成器产出 cover/content/section/closing 四类同源 SVG 背景，
输出与图片路径同 schema 的 art_dna.json（附加 source_mode="md"）。

本脚本不修改、不替代 extract_art_dna.py 的图片像素提取路径；有可读项目图时
仍必须走 extract_art_dna.py。
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from common import read_json, write_json, attach_motifs
# TASK-005: 复用图片路径的同一套背景生成器，保证 md 路径与像素路径同风格
# TASK-041: 复用同一个 --theme-domain 解析函数，保证 md 路径与像素路径的
# domain 加载口径一致，不重复实现一遍
# 本轮新增：色彩发散检测与内容页基础色兜底也复用 extract_art_dna.py 的同一套实现，
# 保证 md 路径与像素路径判定口径完全一致，不重复实现一遍（详见该函数顶部注释）。
from extract_art_dna import svg, _load_theme_domain, color_divergence_check, content_page_base_palette
# TASK-039: md 路径没有 deck.md 正文可扫描关键词，风格选择仅走量化特征兜底
# （bg_styles.select_background_style 的 keyword_text 缺省空串）；TASK-041 起
# 若调用方传入 --theme-domain，则 domain 命中作为最高优先级信号参与选择，
# 仍记录选中风格与判断依据供追溯，见 references/BACKGROUND_STYLES.md
import bg_styles

LINE_LANGUAGES = {"纵向生长", "横向延展", "均衡网格"}
# ART_DNA.md 规范的 8 个维度，art_expression 必须全覆盖（每维度命中任一关键词即视为覆盖）
EXPRESSION_DIMS = [
    ("特色主题颜色", ("主题色", "主题颜")),
    ("线条方向", ("线条",)),
    ("形状语言", ("形状",)),
    ("构图重心", ("构图重心", "重心")),
    ("质感与留白", ("质感", "留白")),
    ("版式节奏", ("版式节奏", "节奏")),
    ("光影纹样", ("光影", "纹样")),
    ("空间层次", ("空间层次", "空间")),
]


def args():
    p = argparse.ArgumentParser(description="Build art DNA from image md-interpretation report (no pixel input).")
    p.add_argument("--md-report", required=True, help="Agent 从图片 md 解读提取的清单 JSON（state/art_dna_md.json）")
    p.add_argument("--output", required=True)
    p.add_argument("--assets-dir", required=True)
    # TASK-028: 可选——项目主题线条插画装饰映射（缺省取 --output 同目录下的 art_motifs.json）
    p.add_argument("--motifs", required=False, help="state/art_motifs.json：主题图形关键词->线条SVG素材映射")
    # TASK-041: 可选——指向 classify_theme_domain.py 产出的 state/theme_domain.json，
    # 与 extract_art_dna.py 同口径，解析 domain/confidence 传给背景风格选择
    p.add_argument("--theme-domain", required=False, help="state/theme_domain.json 路径（可选）：项目主题域判定结果，作为背景风格选择的最高优先级输入")
    return p.parse_args()


def fail(errors):
    print("md 解读清单校验失败，字段级修复清单：", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    return 1


def validate(rep):
    """按 ART_DNA.md 维度校验清单，返回错误列表（空=通过）。"""
    errors = []
    ids = rep.get("source_md_ids") or []
    if not ids:
        errors.append("source_md_ids 为空：登记 md 解读文档标识列表（阻断检查）")
    dna = rep.get("dna") or {}
    palette = dna.get("palette") or []
    if len(palette) < 3:
        errors.append("dna.palette 至少需要 3 个 hex 色（主题色/强调色/辅助色）")
    for c in palette:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(c)):
            errors.append(f"dna.palette 含非法 hex 色：{c}")
    if dna.get("line_language") not in LINE_LANGUAGES:
        errors.append(f"dna.line_language 必须为 {'/'.join(sorted(LINE_LANGUAGES))} 之一")
    for key in ("light_focus", "dark_focus"):
        v = dna.get(key)
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and 0 <= x <= 2 for x in v)):
            errors.append(f"dna.{key} 必须为九宫格坐标 [x,y]（0–2 整数）")
    for key in ("saturation", "contrast"):
        v = dna.get(key)
        if not (isinstance(v, (int, float)) and 0 <= v <= 1):
            errors.append(f"dna.{key} 必须为 0–1 数值")
    expression = rep.get("art_expression") or ""
    for dim, keywords in EXPRESSION_DIMS:
        if not any(k in expression for k in keywords):
            errors.append(f"art_expression 缺维度：{dim}")
    return errors


def _source_identity_items(rep):
    """本轮新增：可选字段 source_identity_colors——{来源标识: 该来源自身色彩身份 hex}，
    仅当项目存在多份 md 解读来源、且 Agent 在提取阶段愿意额外登记"每份解读各自的主色"
    时才建议提供（用于跨来源色彩发散检测，见 references/ART_DNA.md「无像素输入」一节
    与 color_divergence_check()）。字段缺省、格式不对、或有效条目不足 2 个时，本函数
    返回空列表——调用方据此完全跳过发散检测，不影响主产物生成（非阻断检查，不写入
    validate() 的 errors）。"""
    raw = rep.get("source_identity_colors")
    if not isinstance(raw, dict):
        return []
    items = []
    for sid, hexc in raw.items():
        if isinstance(hexc, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", hexc):
            items.append((sid, hexc))
    return items


def main():
    a = args()
    rep = read_json(a.md_report)
    errors = validate(rep)
    if errors:
        return fail(errors)
    dna = rep["dna"]
    expression = rep["art_expression"].strip()
    ids = list(rep["source_md_ids"])
    # 色彩发散兜底（md 路径）：与像素路径判定口径一致，见 color_divergence_check()
    # 顶部注释。md 路径当前 schema 里 dna 是 Agent 通读全部来源后已经合并好的单一
    # 结果，本身不带"每份来源各自的主色"——只有 Agent 额外提供了可选字段
    # source_identity_colors（见 _source_identity_items() 注释）时才有数据可比较；
    # 未提供或有效来源不足 2 个时直接跳过，dna 完全不变，不影响任何既有项目。
    identity_items = _source_identity_items(rep)
    diverged, div_reason, _camps = color_divergence_check(identity_items)
    if diverged:
        dna = dict(dna)
        dna["palette"] = content_page_base_palette(a.output)
    outdir = Path(a.assets_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    seed = "|".join(ids) + expression
    cover = outdir / "project-cover.svg"
    content = outdir / "project-content.svg"
    section = outdir / "project-section.svg"
    closing = outdir / "project-closing.svg"
    domain, domain_confidence = _load_theme_domain(a)
    style_key, style_trace = bg_styles.select_background_style(dna, "", domain, domain_confidence)
    for path, kind in ((cover, "cover"), (content, "content"), (section, "section"), (closing, "closing")):
        path.write_text(svg(dna, kind, seed, "", domain, domain_confidence), encoding="utf-8")
    report = {
        "version": "2.0",
        "source_mode": "md",  # TASK-005: QA 据此标注 art_dna=md，与图片路径区分
        "source_md_ids": ids,
        "art_expression": expression,
        "dna": dna,
        "cover_background": f"{outdir.name}/{cover.name}",
        "content_background": f"{outdir.name}/{content.name}",
        "section_background": f"{outdir.name}/{section.name}",
        "closing_background": f"{outdir.name}/{closing.name}",
        "non_template_signature": hashlib.sha256(seed.encode()).hexdigest()[:16],
        # TASK-039/TASK-041: 背景风格匹配结果——md 路径无正文关键词可扫描，但若传入
        # --theme-domain，domain 命中仍作为最高优先级信号参与选择（否则仅走量化特征）
        "background_style": style_key,
        "background_style_label": bg_styles.STYLE_LIBRARY[style_key]["label"],
        "background_style_reason": style_trace,
        # 色彩发散检测结果——无论是否触发都记录，不做静默决策。triggered=True 时
        # dna["palette"] 已替换为内容页基础色兜底，见 _source_identity_items() 注释。
        "color_divergence_triggered": diverged,
        "color_divergence_reason": div_reason,
    }
    # TASK-028: 可选主题插画装饰层——静默跳过不阻断主产物，详见 common.attach_motifs
    motifs_path = a.motifs or (Path(a.output).parent / "art_motifs.json")
    report = attach_motifs(report, motifs_path, outdir)
    write_json(a.output, report)
    print(a.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
