#!/usr/bin/env python3
"""场景图风格检测：分析 manifest 图片的色相/明度/饱和度，推导整套 deck 的视觉风格。

输出：
- style_report.json：每张图的风格标签 + 全 deck 加权聚合结果（推荐主题、强调色、封面背景图）
- auto-theme.css：叠加在基础主题之后的派生 token（accent、surface、line、辉光等）

风格分类（deck 级，按图片 weight 加权）：
- tech      暗底 + 蓝青紫色相 + 中高饱和  → tech-dark
- warm      暖色相（红橙黄）+ 高饱和      → warm-human
- minimal   高明度 + 低饱和              → minimal-white
- editorial 中高明度 + 中低饱和          → editorial
- business  其他                         → business-dark
"""
import argparse
import colorsys
import json
import sys
from pathlib import Path
from common import read_json, write_json


THEME_FOR_STYLE = {
    "tech": "tech-dark",
    "warm": "warm-human",
    "minimal": "minimal-white",
    "editorial": "editorial",
    "business": "business-dark",
}
WEIGHTS = {"high": 3, "medium": 2, "low": 1}


def parse_args():
    p = argparse.ArgumentParser(description="Detect scene-image style and derive deck theme tokens.")
    p.add_argument("--manifest", required=True)
    p.add_argument("--output", required=True, help="style_report.json path")
    p.add_argument("--theme-css", required=False, help="derived theme override css path")
    return p.parse_args()


def circular_mean(hues):
    import math
    if not hues:
        return None
    sx = sum(math.cos(h * 6.283185307) for h in hues)
    sy = sum(math.sin(h * 6.283185307) for h in hues)
    return (math.atan2(sy, sx) / 6.283185307) % 1.0


def analyze_image(path):
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return None
    img.thumbnail((96, 96))
    px = list(img.getdata())
    n = max(1, len(px))
    luma = sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in px) / n / 255
    hsv = [colorsys.rgb_to_hsv(r / 255, g / 255, b / 255) for r, g, b in px[::2]]
    sat = sum(s for _, s, _ in hsv) / max(1, len(hsv))
    vivid = [h for h, s, v in hsv if s > 0.25 and v > 0.15]
    hue = circular_mean(vivid)
    return {"luma": round(luma, 3), "saturation": round(sat, 3), "hue": round(hue, 3) if hue is not None else None}


def classify(stats):
    """单图风格标签。hue 为 0-1 环形色相（0=红，0.17=黄，0.33=绿，0.5=青，0.67=蓝）。"""
    luma, sat, hue = stats["luma"], stats["saturation"], stats["hue"]
    if luma > 0.75 and sat < 0.25:
        return "minimal"
    if hue is not None and sat > 0.3 and (hue < 0.14 or hue > 0.92):
        return "warm"
    if luma < 0.45 and sat > 0.2 and hue is not None and 0.42 <= hue <= 0.78:
        return "tech"
    if luma > 0.55 and sat < 0.4:
        return "editorial"
    return "business"


def hsv_hex(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(1.0, s), min(1.0, v))
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def hsv_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(1.0, s), min(1.0, v))
    return int(r * 255), int(g * 255), int(b * 255)


def aggregate(per_image, images):
    """按 weight 加权投票出 deck 主风格，返回推荐主题与派生色。"""
    votes = {}
    cover_candidate = None
    cover_score = -1
    for img_id, cls in per_image.items():
        meta = next((i for i in images if i.get("id") == img_id), {})
        w = WEIGHTS.get(meta.get("weight"), 1)
        votes[cls["style"]] = votes.get(cls["style"], 0) + w
        score = w + (2 if meta.get("suggested_role") in {"hero", "background"} else 0)
        if score > cover_score:
            cover_score = score
            cover_candidate = img_id
    # TASK-009: 无可分析场景图时落入默认视觉方向（浅色高亮/深蓝骨架/青蓝辅助），
    # 不再默认 business-dark 深色霓虹 token；有图 deck 的推导行为不变。
    if not votes:
        return {
            "style": "business",
            "recommended_theme": "proposal-light",
            "hue": 0.58,
            "accent": "#123a6b",
            "accent_2": "#1fa8d8",
            "dark_base": False,
            "cover_image_id": None,
            "votes": votes,
        }
    style = max(votes, key=votes.get) if votes else "business"
    # 聚合色相：取主风格图片的 vivid 色相
    hues = [per_image[i]["hue"] for i in per_image if per_image[i]["style"] == style and per_image[i]["hue"] is not None]
    hue = circular_mean(hues)
    sats = [per_image[i]["saturation"] for i in per_image if per_image[i]["style"] == style]
    sat = sum(sats) / max(1, len(sats)) if sats else 0.4
    dark_base = THEME_FOR_STYLE[style] in {"tech-dark", "business-dark", "warm-human", "editorial"}
    if hue is None:
        hue = 0.52
    accent_v = 1.0 if dark_base else 0.72
    accent_s = min(1.0, max(0.55, sat + 0.25))
    accent = hsv_hex(hue, accent_s, accent_v)
    accent2 = hsv_hex(hue + 0.33, min(1.0, accent_s * 0.9), accent_v)
    return {
        "style": style,
        "recommended_theme": THEME_FOR_STYLE[style],
        "hue": round(hue, 3),
        "accent": accent,
        "accent_2": accent2,
        "dark_base": dark_base,
        "cover_image_id": cover_candidate,
        "votes": votes,
    }


def derived_css(agg):
    r, g, b = hsv_rgb(agg["hue"], min(1.0, max(0.55, 0.8)), 0.95)
    lines = [
        "/* auto-derived from scene images by detect_style.py */",
        ":root {",
        f"  --accent: {agg['accent']};",
        f"  --accent-2: {agg['accent_2']};",
        f"  --line: rgba({r},{g},{b},.22);",
        f"  --surface: rgba({r},{g},{b},.07);",
        f"  --surface-2: rgba({r},{g},{b},.12);",
    ]
    if agg["dark_base"]:
        bg_r, bg_g, bg_b = hsv_rgb(agg["hue"], 0.38, 0.055)
        pg_r, pg_g, pg_b = hsv_rgb(agg["hue"], 0.42, 0.035)
        lines += [
            f"  --bg: rgb({bg_r},{bg_g},{bg_b});",
            f"  --page-bg: rgb({pg_r},{pg_g},{pg_b});",
        ]
    lines += [
        "}",
        f".slide h2, .eyebrow, .kpi-number {{ text-shadow: 0 0 24px rgba({r},{g},{b},.24); }}",
        f".panel, .content-list li {{ border-color: rgba({r},{g},{b},.28); }}",
        f".gallery-index {{ background: {agg['accent']}; }}",
    ]
    if agg["style"] == "tech":
        lines += [
            ":root {",
            f"  --texture: linear-gradient(rgba({r},{g},{b},.06) 1px, transparent 1px), linear-gradient(90deg, rgba({r},{g},{b},.05) 1px, transparent 1px);",
            "  --texture-size: 54px 54px, 54px 54px;",
            "}",
        ]
    return "\n".join(lines) + "\n"


def main():
    args = parse_args()
    manifest_path = Path(args.manifest)
    manifest = read_json(manifest_path)
    images = manifest.get("images", [])
    per_image = {}
    for img in images:
        src = img.get("file")
        if not src:
            continue
        path = manifest_path.parent / src
        if not path.exists():
            continue
        stats = analyze_image(path)
        if stats is None:
            continue
        stats["style"] = classify(stats)
        per_image[img["id"]] = stats
    agg = aggregate(per_image, images)
    report = {
        "deck_style": agg["style"],
        "recommended_theme": agg["recommended_theme"],
        "accent": agg["accent"],
        "accent_2": agg["accent_2"],
        "cover_image_id": agg["cover_image_id"],
        "votes": agg["votes"],
        "per_image": per_image,
    }
    write_json(args.output, report)
    if args.theme_css:
        out = Path(args.theme_css)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(derived_css(agg), encoding="utf-8")
        print(str(out))
    print(str(args.output))
    print(f"style={agg['style']} theme={agg['recommended_theme']} accent={agg['accent']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
