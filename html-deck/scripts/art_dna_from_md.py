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

from common import read_json, write_json
# TASK-005: 复用图片路径的同一套背景生成器，保证 md 路径与像素路径同风格
from extract_art_dna import svg

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


def main():
    a = args()
    rep = read_json(a.md_report)
    errors = validate(rep)
    if errors:
        return fail(errors)
    dna = rep["dna"]
    expression = rep["art_expression"].strip()
    ids = list(rep["source_md_ids"])
    outdir = Path(a.assets_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    seed = "|".join(ids) + expression
    cover = outdir / "project-cover.svg"
    content = outdir / "project-content.svg"
    section = outdir / "project-section.svg"
    closing = outdir / "project-closing.svg"
    for path, kind in ((cover, "cover"), (content, "content"), (section, "section"), (closing, "closing")):
        path.write_text(svg(dna, kind, seed), encoding="utf-8")
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
    }
    write_json(a.output, report)
    print(a.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
