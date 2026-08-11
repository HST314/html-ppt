#!/usr/bin/env python3
import argparse
import base64
import mimetypes
import re
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from common import read_json


def parse_args():
    p = argparse.ArgumentParser(description="Inline image assets as base64 or package relative-path deck zip.")
    p.add_argument("--html", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--mode", choices=["inline", "zip"], default="inline")
    p.add_argument("--output", required=True)
    return p.parse_args()


def data_uri(path):
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{raw}"


def main():
    args = parse_args()
    html_path = Path(args.html)
    manifest_path = Path(args.manifest)
    text = html_path.read_text(encoding="utf-8")
    manifest = read_json(manifest_path)
    if args.mode == "inline":
        for img in manifest.get("images", []):
            src = img["file"]
            path = manifest_path.parent / src
            if path.exists():
                text = re.sub(r'(["\'])' + re.escape(src) + r'\1', lambda m: m.group(1) + data_uri(path) + m.group(1), text)
        # 同时内联由艺术 DNA 流程生成、未登记在输入 manifest 中的本地背景。
        for src in set(re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text)):
            if src.startswith(("data:", "http://", "https://")):
                continue
            path = html_path.parent / src
            if path.is_file():
                text = text.replace(src, data_uri(path))
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(str(out))
        return 0
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(out, "w", ZIP_DEFLATED) as z:
        z.write(html_path, "deck.html")
        for img in manifest.get("images", []):
            p = manifest_path.parent / img["file"]
            if p.exists():
                z.write(p, "images/" + img["file"])
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
