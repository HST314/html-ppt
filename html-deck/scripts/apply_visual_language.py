#!/usr/bin/env python3
"""Bind a compiled ProjectVisualLanguage contract to SlidesPlan IR."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="将 MD 视觉语言写入 SlidesPlan，替换旧 visual_semantics 来源。")
    parser.add_argument("--ir", required=True)
    parser.add_argument("--visual-language", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.ir).read_text(encoding="utf-8"))
    language = json.loads(Path(args.visual_language).read_text(encoding="utf-8"))
    if plan.get("schema") != "SlidesPlan" or language.get("schema") != "ProjectVisualLanguage":
        raise SystemExit("输入必须是 SlidesPlan 与 ProjectVisualLanguage")
    plan["visual_language"] = language
    # This is the only semantics source for the image route.  Do not merge a
    # previous motif list: replacement prevents old/new application conflicts.
    approved = [value for value in ("rocket", "orbit", "satellite") if value in language.get("motifs", [])]
    plan["visual_semantics"] = {
        "keywords": language.get("keywords") or [],
        "motifs": approved,
        "evidence": {value: {"rocket": "火箭", "orbit": "轨道", "satellite": "卫星"}[value] for value in approved},
    }
    Path(args.output).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Bound MD visual language to {args.output}; legacy semantics replaced")


if __name__ == "__main__":
    main()
