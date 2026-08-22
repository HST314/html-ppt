#!/usr/bin/env python3
"""Compile image-description Markdown into a deterministic deck visual language."""

import argparse
import json
import re
from pathlib import Path


MOTIFS = {
    "rocket": ("火箭", "尾焰", "发射"),
    "orbit": ("轨道", "同心圆", "圆形", "圆环"),
    "satellite": ("卫星", "星座", "阵列", "拓扑"),
    "starfield": ("星空", "星尘", "星点", "深空"),
    "plume": ("尾焰", "火焰", "炽白", "暖金"),
    "grid": ("网格", "坐标", "节点", "精确"),
    "cloud-wave": ("祥云", "云纹", "水纹", "破浪"),
    "seal-script": ("篆体", "魏碑", "竖排", "汉字"),
}


def parse_args():
    parser = argparse.ArgumentParser(description="从项目图片 MD 描述提取可执行视觉语言。")
    parser.add_argument("--descriptions-dir", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def first_evidence(corpus, aliases):
    for alias in aliases:
        match = re.search(rf"[^。\n]*{re.escape(alias)}[^。\n]*", corpus)
        if match:
            return match.group(0).strip(" -*：:")[:120]
    return ""


def main():
    args = parse_args()
    root = Path(args.descriptions_dir)
    files = sorted(root.glob("*.md"))
    if not files:
        raise SystemExit("描述目录中没有 Markdown 文件")
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in files)
    evidence = {key: first_evidence(corpus, aliases) for key, aliases in MOTIFS.items()}
    evidence = {key: value for key, value in evidence.items() if value}
    required = {"rocket", "orbit", "satellite", "starfield"}
    if not required.issubset(evidence):
        raise SystemExit("MD 描述不足以建立火箭/轨道/卫星/星空主题语言")
    profile = {
        "schema": "ProjectVisualLanguage",
        "version": "1.0",
        "source": {"kind": "image-description-md", "files": [path.name for path in files]},
        "narrative": "从地球点火，经轨道组网，抵达千帆星座",
        "keywords": ["长征八号甲", "千帆星座", "火箭", "卫星", "轨道"],
        "motifs": list(evidence),
        "evidence": evidence,
        "palette": {
            "deep_space": "#061A33", "space_blue": "#0B4F8A", "ion_blue": "#35B8E8",
            "champagne_gold": "#D8B56A", "silver": "#DCE7EF", "paper": "#F2F7FA",
            "plume": "#F28C3B",
        },
        "word_art": {
            "cover": "rocket-ascent", "toc": "orbital-title", "section": "vertical-seal",
            "content": "precision-cut", "closing": "stellar-convergence",
        },
        "composition": {
            "cover": "diagonal-launch-corridor", "toc": "asymmetric-orbit-map",
            "section": "split-orbit-gate", "content": "chamfered-mission-panels",
            "closing": "converging-star-trails",
        },
        "derived_components": {
            "background": ["starfield", "orbit", "grid", "plume"],
            "container": ["seal-rim", "satellite-panel", "trajectory-notch"],
            "flow": ["orbit", "satellite", "rocket"],
            "transition": ["rocket", "orbit", "seal-script"],
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {len(evidence)} MD-grounded motifs -> {output}")


if __name__ == "__main__":
    main()
