#!/usr/bin/env python3
"""图片覆盖审计：manifest 中的每张图片都必须出现在渲染后的 HTML 中。

用于防止"用户一次输入大量场景图要求全部融合"时的漏图风险：
- 渲染层对单页图片数有上限（gallery 6 张、hero/side/compare 仅 1 张），
  build_ir 的自动拆页负责扩容，本脚本负责最终核验。
- 退出码：0 全覆盖；1 存在漏图；2 工具错误。
"""
import argparse
import re
import sys
from pathlib import Path
from common import read_json


def parse_args():
    p = argparse.ArgumentParser(description="Audit that every manifest image appears in the rendered HTML.")
    p.add_argument("--manifest", required=True)
    p.add_argument("--html", required=True)
    p.add_argument("--output", required=False, help="Markdown audit report path (optional).")
    return p.parse_args()


def audit(manifest, html_text):
    """返回覆盖审计结果。slot 归属页码按文档顺序跟踪最近的 data-page。"""
    images = manifest.get("images", [])
    slot_pages = {}
    current_page = None
    for m in re.finditer(r'data-page="(\d+)"|data-image-slot="([^"]+)"', html_text):
        if m.group(1):
            current_page = int(m.group(1))
        else:
            slot = m.group(2)
            if slot and slot != "empty":
                slot_pages.setdefault(slot, [])
                if current_page not in slot_pages[slot]:
                    slot_pages[slot].append(current_page)
    known = {i.get("id") for i in images}
    rows, missing = [], []
    for img in images:
        iid = img.get("id")
        pages = slot_pages.get(iid, [])
        if not pages:
            missing.append(iid)
        rows.append({
            "id": iid,
            "file": img.get("file"),
            "pages": pages,
            "status": "covered" if pages else "missing",
        })
    unlisted = [{"id": k, "pages": v} for k, v in slot_pages.items() if k not in known]
    return {
        "total": len(images),
        "covered": len(images) - len(missing),
        "missing": missing,
        "rows": rows,
        "unlisted_slots": unlisted,
    }


def report_text(result, html_path, manifest_path):
    lines = [
        "# Image Coverage Audit",
        "",
        f"- html: {html_path}",
        f"- manifest: {manifest_path}",
        f"- total_images: {result['total']}",
        f"- covered: {result['covered']}",
        f"- missing: {len(result['missing'])}",
        "",
        "## Per-Image Coverage",
    ]
    for row in result["rows"]:
        pages = ", ".join(f"P{p}" for p in row["pages"]) if row["pages"] else "-"
        mark = "OK" if row["status"] == "covered" else "MISSING"
        lines.append(f"- [{mark}] {row['id']} ({row['file']}): {pages}")
    if result["unlisted_slots"]:
        lines += ["", "## Slots Not In Manifest"]
        for x in result["unlisted_slots"]:
            pages = ", ".join(f"P{p}" for p in x["pages"])
            lines.append(f"- {x['id']}: {pages}")
    if result["missing"]:
        lines += ["", "## Action Required",
                  "以上 MISSING 图片未出现在 HTML 中。请重跑 build_ir（自动拆页/汇入）后再渲染。"]
    return "\n".join(lines) + "\n"


def main():
    args = parse_args()
    manifest = read_json(args.manifest)
    html_text = Path(args.html).read_text(encoding="utf-8")
    result = audit(manifest, html_text)
    text = report_text(result, args.html, args.manifest)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(str(out))
    else:
        print(text)
    print(f"coverage: {result['covered']}/{result['total']}", file=sys.stderr)
    return 1 if result["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
