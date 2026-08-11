#!/usr/bin/env python3
"""联网素材获取：把 manifest 中带 url 的图片下载到本地，并回写 file 字段。

用途：Agent 联网检索到合适的风格背景/场景素材后，把 URL 写入 manifest：
  {"id": "bg-001", "url": "https://example.com/tech-bg.jpg", "weight": "high", ...}
本脚本下载到 images/downloaded/ 并回写 file，后续 build_ir/render/inline 无需感知 URL。
下载失败不阻断：保留 url、跳过，渲染层按缺图降级。
"""
import argparse
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from common import read_json, write_json


def parse_args():
    p = argparse.ArgumentParser(description="Download url-based manifest images to local files.")
    p.add_argument("--manifest", required=True)
    p.add_argument("--timeout", type=int, default=20)
    return p.parse_args()


def main():
    args = parse_args()
    manifest_path = Path(args.manifest)
    manifest = read_json(manifest_path)
    cache = manifest_path.parent / "downloaded"
    ok, failed = 0, []
    for img in manifest.get("images", []):
        url = img.get("url")
        if not url or img.get("file"):
            continue
        suffix = Path(urllib.parse.urlparse(url).path).suffix
        if suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
            suffix = ".png"
        cache.mkdir(parents=True, exist_ok=True)
        dest = cache / f"{img.get('id', 'img')}{suffix}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "html-deck/2.1"})
            with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                dest.write_bytes(resp.read())
            img["file"] = str(dest.relative_to(manifest_path.parent)).replace("\\", "/")
            ok += 1
        except Exception as exc:
            failed.append({"id": img.get("id"), "url": url, "error": str(exc)})
    write_json(manifest_path, manifest)
    print(f"downloaded: {ok}, failed: {len(failed)}")
    for f in failed:
        print(f"FAILED {f['id']}: {f['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
