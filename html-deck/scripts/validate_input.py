#!/usr/bin/env python3
import argparse
import json
import struct
import sys
from pathlib import Path
from common import write_json

REQUIRED = {
    "id", "file", "alt", "description", "content_type", "width", "height",
    "aspect_ratio", "suggested_role", "scene_tags", "weight"
}
CONTENT_TYPES = {"screenshot", "photo", "chart", "diagram", "illustration"}
SUGGESTED = {"hero", "inline", "gallery", "background"}
WEIGHTS = {"high", "medium", "low"}


def image_size(path):
    try:
        from PIL import Image
    except Exception:
        try:
            with open(path, "rb") as f:
                head = f.read(24)
            if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
                return struct.unpack(">II", head[16:24]), None
            return None, "Pillow unavailable and file is not a readable PNG; pixel verification skipped"
        except Exception as exc:
            return None, str(exc)
    try:
        with Image.open(path) as img:
            return img.size, None
    except Exception as exc:
        return None, str(exc)


def parse_args():
    p = argparse.ArgumentParser(description="Validate deck.md and images/manifest.json.")
    p.add_argument("--deck", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def main():
    args = parse_args()
    errors, warnings = [], []
    deck = Path(args.deck)
    manifest_path = Path(args.manifest)
    if not deck.exists():
        errors.append({"path": args.deck, "message": "deck.md not found"})
    else:
        text = deck.read_text(encoding="utf-8")
        if text.count("\n# ") + (1 if text.startswith("# ") else 0) != 1:
            errors.append({"path": args.deck, "message": "deck.md must contain exactly one level-1 title"})
        if "### " not in text:
            errors.append({"path": args.deck, "message": "deck.md must contain at least one level-3 slide title"})
    if not manifest_path.exists():
        errors.append({"path": args.manifest, "message": "manifest.json not found"})
        manifest = {"images": []}
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            manifest = {"images": []}
            errors.append({"path": args.manifest, "message": "manifest JSON parse failed: " + str(exc)})
    ids = set()
    for idx, item in enumerate(manifest.get("images", [])):
        prefix = f"images[{idx}]"
        missing = sorted(REQUIRED - set(item))
        for field in missing:
            errors.append({"path": prefix + "." + field, "message": "required field missing"})
        if item.get("id") in ids:
            errors.append({"path": prefix + ".id", "message": "duplicate image id"})
        ids.add(item.get("id"))
        if item.get("content_type") and item["content_type"] not in CONTENT_TYPES:
            errors.append({"path": prefix + ".content_type", "message": "invalid content_type"})
        if item.get("suggested_role") and item["suggested_role"] not in SUGGESTED:
            errors.append({"path": prefix + ".suggested_role", "message": "invalid suggested_role"})
        if item.get("weight") and item["weight"] not in WEIGHTS:
            errors.append({"path": prefix + ".weight", "message": "invalid weight"})
        if item.get("file"):
            img_path = manifest_path.parent / item["file"]
            if not img_path.exists():
                errors.append({"path": prefix + ".file", "message": f"image file not found: {item['file']}"})
            else:
                size, warning = image_size(img_path)
                if warning:
                    warnings.append({"path": prefix + ".file", "message": warning})
                if size and ("width" in item and "height" in item) and tuple(size) != (item["width"], item["height"]):
                    errors.append({"path": prefix, "message": f"pixel size mismatch: actual {size}, manifest {(item['width'], item['height'])}"})
    report = {"ok": not errors, "errors": errors, "warnings": warnings}
    write_json(args.output, report)
    if errors:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
