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
    p.add_argument("--deck", required=False, help="deck.md 路径（可选）：用于扫描正文是否明确声明了强调色名称（如"
                                                     "「香槟金」），据此校正 accent_2——见下方「文本色彩语言校验」")
    return p.parse_args()


# TASK-034: 文本色彩语言校验——accent（主强调色）来自场景图像素真实分析，有
# 图像依据；但 accent_2（第二强调色）此前是纯几何色相旋转（hue+0.33，即
# aggregate() 里的 hsv_hex(hue + 0.33, ...)），不依据任何图像或文本内容，
# 只是数学上「找一个和 accent 视觉上有区分度的第二色」，本质是猜测，容易与
# deck 正文实际描述的配色语言脱节。changzheng8a 项目实测踩坑：正文反复用
# 「香槟金/18K 香槟金」描述全系列强调色（边框/线条），但 accent_2 经色相
# 旋转落在 #ff2f78（品红），与文字宣称的色彩语言完全对不上——目录页卫星
# 节点描边/编号、其余内容页的编号徽标/时间轴箭头/checkpoint 卡片描边等
# 所有引用 --accent-2 的元素全部跟着显示成不搭调的品红色。
# 治本做法：仅当正文出现明确、高频的具名强调色词（当前只登记「金」系
# 关键词，覆盖面广的一类命名法；未来如需扩展其它色系按同样模式加关键词
# 表即可）时，才用该颜色词的标准色相覆盖 accent_2 的色相推导，其余情况
# （多数 deck 正文不会明确点名强调色）保持原有色相旋转推导不变，不引入
# 额外风险。只覆盖 accent_2、不动 accent——accent 已有图像依据，比合成的
# accent_2 可信得多，没有必要用文本线索去校正一个本来就有更强证据支撑的
# 值。详细原则见 references/THEMES.md「色彩自动检测应与正文声明的色彩
# 语言交叉核对」一节。
GOLD_KEYWORDS = ("香槟金", "鎏金", "镀金", "18K金", "18K 金", "黄金色", "金边", "金色")
CHAMPAGNE_GOLD_HEX = "#d4af6a"  # 香槟金标准色相锚点（暖金色，非刺眼纯黄/土黄）
GOLD_KEYWORD_MIN_HITS = 3   # 正文命中次数达到此阈值才视为「明确声明」，避免偶发提及误触发
# 环形色相距离阈值（0-1 环形空间，0.10≈36°），低于此值说明已经落在
# 橙黄-金-黄绿这一段「视觉上就是金色系」的范围内，不必覆盖。
# 实测校准：changzheng8a 项目 accent_2 是 #ff2f78（品红，色相约 339°），
# 与香槟金标准色相（约 39°）环形距离恰好 60°——曾用 0.18(65°) 会因为
# 60°<65° 被误判为"已经够接近"而放弃覆盖，实际二者观感截然不同（金色 vs
# 品红）。改为 0.10(36°)：只把橙/黄/黄绿这一窄段视为"够金"，60° 外的
# 蓝/绿/青/紫/品红/正红都会触发覆盖，更贴合实际视觉判断。
GOLD_HUE_DISTANCE_MIN = 0.10


def _hex_to_hue(hexcolor):
    hexcolor = hexcolor.lstrip("#")
    r = int(hexcolor[0:2], 16) / 255
    g = int(hexcolor[2:4], 16) / 255
    b = int(hexcolor[4:6], 16) / 255
    h, _s, _v = colorsys.rgb_to_hsv(r, g, b)
    return h


def _circular_hue_distance(a, b):
    d = abs(a - b) % 1.0
    return min(d, 1.0 - d)


def scan_gold_keyword_hits(text):
    if not text:
        return 0
    return sum(text.count(kw) for kw in GOLD_KEYWORDS)


def apply_text_color_override(agg, deck_text):
    """正文若高频、明确声明「香槟金」一类具名金色强调色，且当前 accent_2 的
    色相与金色相去甚远，用统一调校过的香槟金色值覆盖 accent_2；否则原样返回
    （不触发时 agg 不变、override 说明为 None）。"""
    hits = scan_gold_keyword_hits(deck_text)
    if hits < GOLD_KEYWORD_MIN_HITS:
        return agg, None
    gold_hue = _hex_to_hue(CHAMPAGNE_GOLD_HEX)
    cur_hue = _hex_to_hue(agg["accent_2"])
    dist = _circular_hue_distance(gold_hue, cur_hue)
    if dist < GOLD_HUE_DISTANCE_MIN:
        return agg, None
    agg = dict(agg)
    agg["accent_2"] = CHAMPAGNE_GOLD_HEX
    note = {
        "keyword": "gold",
        "keyword_hits": hits,
        "hue_before": round(cur_hue, 3),
        "hue_after": round(gold_hue, 3),
        "hue_distance": round(dist, 3),
        "reason": "deck.md 正文高频出现香槟金/鎏金等具名金色强调色描述，"
                  "原色相旋转推导出的 accent_2 与之明显不符，改用香槟金锚点色",
    }
    return agg, note


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


def _luma(r, g, b):
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


# TASK-033：深色背景「亮度地板」。用户反馈目录页背景从记忆中的「深蓝色」
# 逐轮变成「接近纯黑」，实测根因是本文件此前给 dark_base 主题的 --bg/--page-bg
# 固定用极低的 v（如 0.055/0.035）——此时即使饱和度不低（0.38+），RGB 三通道
# 绝对值也只有个位数到十几（如 rgb(8,10,14)），人眼在这么低的亮度下已经分辨
# 不出色相差异，视觉上只剩「黑」，与色相本身是否为蓝色无关。
# 治本做法：不改变饱和度/色相的推导来源（仍来自场景图 vivid 色相），只在最终
# v 会导致 luma 低于下限时，沿亮度轴二分抬升到刚好达到下限，同时适度提升
# 饱和度（而非只调亮变灰）强化色相辨识度——确保"深色但看得出是某个颜色"，
# 不是"看起来是黑"。已经达标的项目原样返回，不改变其既有深色观感。
BG_MIN_LUMA = 0.12        # --bg（画布主背景）亮度下限
PAGE_BG_MIN_LUMA = 0.075  # --page-bg（画布外围 letterbox）亮度下限，允许比 --bg 更深


def apply_luma_floor(h, s, v, min_luma, sat_boost=0.14):
    r, g, b = hsv_rgb(h, s, v)
    if _luma(r, g, b) >= min_luma:
        return h, s, v
    lo, hi = v, 1.0
    for _ in range(24):
        mid = (lo + hi) / 2
        r, g, b = hsv_rgb(h, s, mid)
        if _luma(r, g, b) < min_luma:
            lo = mid
        else:
            hi = mid
    return h, min(1.0, s + sat_boost), hi


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
        bh, bs, bv = apply_luma_floor(agg["hue"], 0.38, 0.055, BG_MIN_LUMA)
        ph, ps, pv = apply_luma_floor(agg["hue"], 0.42, 0.035, PAGE_BG_MIN_LUMA)
        bg_r, bg_g, bg_b = hsv_rgb(bh, bs, bv)
        pg_r, pg_g, pg_b = hsv_rgb(ph, ps, pv)
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
    # TASK-034: 文本色彩语言校验（见 parse_args 上方长注释）——deck.md 正文若
    # 高频明确声明具名金色强调色，优先参考这一文本线索校正没有图像依据的
    # accent_2 合成色相；未传 --deck 或未命中阈值时行为与此前完全一致。
    color_override = None
    if args.deck:
        deck_path = Path(args.deck)
        if deck_path.exists():
            deck_text = deck_path.read_text(encoding="utf-8")
            agg, color_override = apply_text_color_override(agg, deck_text)
    report = {
        "deck_style": agg["style"],
        "recommended_theme": agg["recommended_theme"],
        "accent": agg["accent"],
        "accent_2": agg["accent_2"],
        "cover_image_id": agg["cover_image_id"],
        "votes": agg["votes"],
        "per_image": per_image,
        "accent_2_text_override": color_override,
    }
    write_json(args.output, report)
    if args.theme_css:
        out = Path(args.theme_css)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(derived_css(agg), encoding="utf-8")
        print(str(out))
    print(str(args.output))
    print(f"style={agg['style']} theme={agg['recommended_theme']} accent={agg['accent']}", file=sys.stderr)
    if color_override:
        print(f"accent_2 text-override applied: {color_override['hue_before']} -> {color_override['hue_after']} "
              f"(hits={color_override['keyword_hits']})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
