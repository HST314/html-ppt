#!/usr/bin/env python3
"""生成 example-tech 科技风场景图：深蓝底 + 青色网格/电路纹理。"""
import json
import math
import sys
from pathlib import Path


def draw_tech(path, w, h, seed, c_top, c_bot, accent):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), c_top)
    d = ImageDraw.Draw(img)
    ct = tuple(int(c_top.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    cb = tuple(int(c_bot.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    ac = tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(ct[i] * (1 - t) + cb[i] * t) for i in range(3)))
    # 网格
    grid = tuple(min(255, int(v * 1.6)) for v in cb)
    step = max(40, w // 24)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=grid, width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=grid, width=1)
    # 电路线 + 节点
    rnd = seed
    def rand():
        nonlocal rnd
        rnd = (rnd * 1103515245 + 12345) % (2 ** 31)
        return rnd / (2 ** 31)
    for _ in range(14):
        x0, y0 = rand() * w, rand() * h
        x1 = x0 + (rand() - 0.3) * w * 0.4
        y1 = y0 + (rand() - 0.5) * h * 0.3
        d.line([(x0, y0), (x1, y0), (x1, y1)], fill=ac, width=3)
        r = 5 + rand() * 7
        d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], outline=ac, width=3)
    # 中心光斑
    cx, cy = w * (0.3 + rand() * 0.4), h * (0.3 + rand() * 0.4)
    for r in range(int(h * 0.36), 0, -6):
        t = r / (h * 0.36)
        col = tuple(int(cb[i] * t + ac[i] * (1 - t) * 0.5 + cb[i] * (1 - t) * 0.5) for i in range(3))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col)
    img.save(path)


SPECS = [
    ("tech-001", "hero-mainframe.png", 1920, 1080, "16:9", "diagram", "hero", "high", ["模型", "架构"], "灵犀 2.0 MoE 架构渲染图", ("#050d1f", "#0a3a5c", "#39d5f0"), 7),
    ("tech-002", "chip-npu.png", 1600, 900, "16:9", "photo", "gallery", "medium", ["芯片", "端侧"], "NPU 适配验证实拍", ("#071026", "#123a8f", "#4de3ff"), 13),
    ("tech-003", "latency-dash.png", 1600, 900, "16:9", "screenshot", "inline", "medium", ["延迟", "看板"], "端侧延迟监控看板", ("#081226", "#0e5a72", "#2fd8c8"), 29),
    ("tech-004", "cloud-edge.png", 1400, 1400, "1:1", "diagram", "inline", "medium", ["端云", "调度"], "端云协同调度拓扑图", ("#060d1c", "#1b2f7a", "#5ac8fa"), 43),
    ("tech-005", "poc-metrics.png", 1600, 900, "16:9", "chart", "inline", "high", ["POC", "验证"], "共创客户 POC 指标看板", ("#081428", "#0c4f6e", "#3fd2f5"), 61),
    ("tech-006", "sdk-tools.png", 1600, 900, "16:9", "screenshot", "inline", "medium", ["SDK", "工具链"], "SDK 2.0 工具链界面", ("#071022", "#14367e", "#66e0ff"), 83),
]


def main():
    out = Path(__file__).resolve().parent / "images"
    out.mkdir(parents=True, exist_ok=True)
    images = []
    for img_id, file, w, h, ratio, ctype, role, weight, tags, desc, colors, seed in SPECS:
        draw_tech(out / file, w, h, seed, *colors)
        images.append({
            "id": img_id, "file": file, "alt": desc, "description": desc,
            "content_type": ctype, "width": w, "height": h, "aspect_ratio": ratio,
            "suggested_role": role, "scene_tags": tags, "weight": weight,
        })
    (out / "manifest.json").write_text(
        json.dumps({"version": "1.0", "images": images}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(out / "manifest.json")


if __name__ == "__main__":
    main()
