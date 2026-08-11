#!/usr/bin/env python3
import argparse
import json
import struct
import zlib
from pathlib import Path


SPECS = [
    ("img-001", "dashboard.png", 1920, 1080, "16:9", "screenshot", "hero", "high", ["产品", "界面"], "运营驾驶舱截图，展示核心指标与趋势"),
    ("img-002", "mobile.png", 900, 1600, "9:16", "screenshot", "inline", "medium", ["移动端", "界面"], "移动端客户提醒界面"),
    ("img-003", "workflow.png", 1400, 1400, "1:1", "diagram", "inline", "medium", ["流程", "架构"], "客户旅程自动化流程图"),
    ("img-004", "customer-room.png", 1600, 1000, "16:10", "photo", "background", "high", ["客户", "现场"], "客户现场复盘会议照片"),
    ("img-005", "chart.png", 1600, 900, "16:9", "chart", "inline", "high", ["数据", "增长"], "增长趋势图"),
    ("img-006", "team.png", 1200, 900, "4:3", "photo", "gallery", "low", ["团队", "交付"], "交付团队协作场景")
]


def draw_image(path, w, h, title, subtitle, colors):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        draw_png_stdlib(path, w, h, colors)
        return
    img = Image.new("RGB", (w, h), colors[0])
    px = img.load()
    c1 = tuple(int(colors[0].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    c2 = tuple(int(colors[1].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        for x in range(w):
            px[x, y] = col
    d = ImageDraw.Draw(img)
    font_big = ImageFont.load_default()
    font_small = ImageFont.load_default()
    for i in range(6):
        x0 = int(w * .08 + i * w * .12)
        y0 = int(h * (.25 + (i % 3) * .12))
        d.rounded_rectangle([x0, y0, x0 + int(w * .18), y0 + int(h * .12)], radius=18, outline=(255,255,255), width=3)
    d.rectangle([int(w*.06), int(h*.08), int(w*.94), int(h*.18)], fill=(255,255,255))
    d.text((int(w*.08), int(h*.105)), title, fill=(20,24,32), font=font_big)
    d.text((int(w*.08), int(h*.205)), subtitle, fill=(255,255,255), font=font_small)
    d.line([int(w*.08), int(h*.78), int(w*.92), int(h*.58)], fill=(255,255,255), width=6)
    img.save(path)


def png_chunk(kind, data):
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xffffffff)


def draw_png_stdlib(path, w, h, colors):
    c1 = tuple(int(colors[0].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    c2 = tuple(int(colors[1].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    rows = []
    for y in range(h):
        t = y / max(1, h - 1)
        bg = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        row = bytearray([0])
        for x in range(w):
            stripe = ((x // max(24, w // 32)) + (y // max(24, h // 24))) % 7 == 0
            card = (w * .08 < x < w * .92 and h * .10 < y < h * .20) or any(
                w * (.08 + i * .12) < x < w * (.20 + i * .12) and h * (.28 + (i % 3) * .12) < y < h * (.38 + (i % 3) * .12)
                for i in range(6)
            )
            if card:
                pix = (245, 248, 252)
            elif stripe:
                pix = tuple(min(255, v + 28) for v in bg)
            else:
                pix = bg
            row.extend(pix)
        rows.append(bytes(row))
    raw = b"".join(rows)
    data = b"\x89PNG\r\n\x1a\n"
    data += png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += png_chunk(b"IDAT", zlib.compress(raw, 6))
    data += png_chunk(b"IEND", b"")
    path.write_bytes(data)


def main():
    p = argparse.ArgumentParser(description="Generate example scene images and manifest.")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    palette = [("#101827", "#2f7d6d"), ("#18202f", "#c7653d"), ("#f8fafc", "#2d7a9f"), ("#111827", "#4dd4ac"), ("#ffffff", "#0b6bcb"), ("#fbf7f0", "#b1362f")]
    images = []
    for idx, spec in enumerate(SPECS):
        img_id, file, w, h, ratio, ctype, role, weight, tags, desc = spec
        draw_image(out / file, w, h, img_id + " " + ctype, desc, palette[idx])
        images.append({
            "id": img_id,
            "file": file,
            "alt": desc,
            "description": desc,
            "content_type": ctype,
            "width": w,
            "height": h,
            "aspect_ratio": ratio,
            "suggested_role": role,
            "scene_tags": tags,
            "weight": weight,
        })
    (out / "manifest.json").write_text(json.dumps({"version": "1.0", "images": images}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out / "manifest.json")


if __name__ == "__main__":
    main()
