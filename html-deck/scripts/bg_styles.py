#!/usr/bin/env python3
"""背景风格库：静态模板库的"参数化实现"一侧——每个风格函数产出一份**完整背景**
（基础色底/渐变 + 全部装饰元素），不再是拼进外层固定骨架的"图案层"。

## 背景（TASK-042：彻底重写，接力 TASK-039/TASK-040/TASK-041）

TASK-039/041 只把"装饰图案"从 `extract_art_dna.py::svg()` 里拆了出来，但
`svg()` 自身仍然固定画三样东西：①基于 light_focus 定位的柔光大椭圆、②18 条
随机对角线、③7 个随机同心圆环——不管选中哪种风格，这三样都会画，是"不同
主题项目背景看起来还是很像"的真正根因（用户截图看到的"一堆圆环+对角线"）。
本次把这三段固定骨架从 `svg()` 里彻底删除，`svg()` 现在只是一层很薄的胶水
（拼 viewBox/defs/flip），真正的背景内容——基础色底、渐变、全部装饰元素——
全部移入本文件的风格生成器。

## 六大风格分类（对应 `references/BACKGROUND_STYLES.md` 的设计研究）

参照对 `beautiful-html-templates-main`（28 个完整模板）与
`presentation-md-main`（`surfaces.css`）的设计研究，整理出 6 大风格分类、
7 个具体风格 key（分类 1「极简科技/网格数据」按强度拆成动感版/克制版两个
key，服务不同 domain）：

1. 极简科技/网格数据 → `tech-grid-hud`（动感，深底通铺网格+雷达角标+星点）
                        / `tech-grid-blueprint`（克制，网格更淡+空心方框角标）
2. 复古人文/印刷质感 → `print-texture`（孔版叠印色块+套印错位+暖纸底+墨线）
3. 几何色块/粗野主义 → `geo-brutalist`（圆角色块拼贴+硬描边+硬投影+细网格）
4. 有机手绘/温暖人文 → `organic-warm`（角落暖光晕+旋转空心叶形+笔触+纸纹颗粒）
5. 奢华质感/文艺克制 → `refined-literary`（纯色通铺+发丝线+批注刻度，零渐变零阴影零圆角）
6. 怀旧数字/潮流     → `retro-digital`（透视网格地平线+发光水平线+CRT扫描线）

## 三条设计原则（务必先读完这三条再改这个文件）

1. **颜色永远参数化**：每个风格函数只描述"构图逻辑"，不写死任何具体 hex
   色值——所有颜色都通过调用方传入的 `p`（即 `dna["palette"]`，来自
   `extract_art_dna.py::analyze()` 图片像素真实分析结果）取值，如
   `p[1 % len(p)]`。这是用户明确要求保留的"从图片判断主体颜色"能力。
2. **每个风格产出完整背景，不是图案层**：函数签名统一为
   `style_xxx(p, dna, kind, rnd) -> (base_svg, deco_svg)`——`base_svg` 是
   该风格自己的底色/渐变（不再依赖外层提供的柔光椭圆），`deco_svg` 是该
   风格的全部装饰元素。两者由 `generate_full_background()` 组装。
3. **kind 驱动强度差异**：cover/section/closing（骨架页）装饰饱满；
   content（内容页）通过 `generate_full_background()` 的通用弱化包装
   （缩小、挪到角落、透明度砍半）统一处理，风格函数本身不需要为
   content 单独分支，见下方「content 态弱化规则」。

## content 态弱化规则（统一实现，不需要逐个风格重写）

`_content_wrap()`：content 态时把整个装饰层（`deco_svg`）用
`translate+scale` 包一层，缩放锚点固定在画布右下角 (1920,1080)，
scale=0.42（即缩小 58%，落在用户要求的"缩小 50-70%"区间内）——缩放动作本身
就会把内容"挪到角落"（scale 以右下角为原点收缩，元素自然聚拢到该角），
再叠加一层独立的 opacity 乘数（0.45，即"透明度砍半以上"）。基础色底/渐变
（`base_svg`）不受影响，保证内容页背景仍与封面/章节页同一底色，不割裂。

同一处包装函数服务全部 7 个风格，不需要在每个 style_xxx 函数内部重复实现
"content 态要不要缩小"的判断——这也是本次重写要避免重蹈"固定骨架"覆辙的
关键：产出完整背景的自由度在风格函数手里，但"content 态怎么弱化"这条
所有风格共享的规则收在一处，不是每个风格自己发明一套。

## 与既有能力的关系（不是推倒重来）

- `detect_style.py` 的色相/明度/饱和度分析（决定主题 CSS 变量 `--accent` 等）
  **保留不变**，本次改动完全不涉及。
- `extract_art_dna.py::analyze()`/`analyze_png()` 的调色板提取
  （`semantic_palette()`）与线条/明暗统计（`line_language`/`dark_focus`/
  `light_focus`/`saturation`/`contrast`）**保留不变**，本次改动只是替换
  这些量化结果之上"背景实际画什么"这一层实现。
- `state/theme_domain.json`（`classify_theme_domain.py` 产出）驱动的三级
  风格匹配优先级（domain 命中 > 关键词 > 量化特征兜底）**保留复用**，
  详见 `select_background_style()`——本次改动只重写「画什么」，不重写
  「选哪个」的匹配算法。
- `slide_templates/toc/` 目录页模板库、`render_deck.py` 的
  `select_toc_template()` **不动**。

## 文件组织

```
scripts/bg_styles.py                # 本文件：7 个风格生成器 + STYLE_LIBRARY 注册表 + 三级匹配逻辑 + content 态弱化包装
scripts/extract_art_dna.py          # svg() 现在只是薄胶水层：拼 viewBox/defs/flip，调用 bg_styles.generate_full_background()
references/BACKGROUND_STYLES.md     # 六大风格分类体系、设计来源、domain 对接、匹配规则
references/THEME_DOMAINS.md         # 项目主题域判定，本文件消费其 domain 字段
slide_templates/backgrounds/        # 6 个风格的 cover 态静态预览文件（人工参考，不参与渲染）
slide_templates/content/            # 6 个风格的 content 态静态预览文件（人工参考，不参与渲染）
```
"""
import colorsys
import math


# ─────────────────────────── 通用小工具 ───────────────────────────

def _hex_hue(hexcolor):
    """十六进制色 -> 0..1 环形色相；解析失败返回 0（不影响风格选择的粗粒度判断）。"""
    h = (hexcolor or "").lstrip("#")
    if len(h) != 6:
        return 0.0
    try:
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    except ValueError:
        return 0.0
    hue, _s, _v = colorsys.rgb_to_hsv(r, g, b)
    return hue


def _is_warm_hue(hue):
    """红橙黄（环形色相 0 附近两侧）视为暖色，与 detect_style.py 的 warm 判定同口径。"""
    return hue < 0.14 or hue > 0.92


def _grid_to_px(gx, gy):
    """九宫格坐标 [0-2, 0-2]（dna 的 light_focus/dark_focus）-> 1920x1080 画布像素坐标（格心）。"""
    return (gx + 0.5) * (1920 / 3), (gy + 0.5) * (1080 / 3)


def _hex_luma(hexcolor):
    """十六进制色 -> 0..1 感知亮度（Rec.709 加权），解析失败按中性 0.5 处理。
    供 `_lightest()`/`_darkest()` 从 palette 里挑"确实偏亮/偏暗"的颜色使用——
    比盲猜某个固定下标（如 p[-1]）更可靠：palette 各下标语义
    （dark/warm/cool/light/accent/dominant，见 semantic_palette()）在去重后
    可能整体偏移，固定下标不保证拿到真正浅色/深色。"""
    h = (hexcolor or "").lstrip("#")
    if len(h) != 6:
        return 0.5
    try:
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    except ValueError:
        return 0.5
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lightest(p):
    """palette 里感知亮度最高的颜色，供需要"纸底/骨白底"的风格（print-texture/
    geo-brutalist）取底色，比固定下标更可靠。"""
    return max(p, key=_hex_luma) if p else "#f3ecd9"


def _ensure_min_luma(hexcolor, floor=0.075):
    """大面积通铺底色的最低可分辨亮度安全网。

    背景：`qa_render.py::check_background_drift()` 在渲染后的四角采样亮度低于
    0.065 时判定"背景色漂移为接近纯黑"（用户固化的永久质量门禁）。真实项目
    的 `dna["palette"]`（图片像素分析结果）里，深色主题图片的主色可能低至
    luma 0.04~0.05（如军工徽章类深藏蓝底图）——若风格函数直接用这类颜色做
    大面积单色通铺（`tech-grid-hud`/`tech-grid-blueprint`/`organic-warm`/
    `refined-literary`/`retro-digital` 的整页底色），会在装饰元素覆盖不到的
    角落触发这条门禁。

    本函数只在颜色本身低于安全floor（高于 QA 阈值留安全余量，避免抗锯齿/
    压缩误差导致实测值卡在临界）时朝白色方向按最小必要比例微调混合，不改变
    色相/色度个性（仍是同一个主题色的"提亮版"，不是替换成另一个颜色），
    颜色已经足够亮时原样返回，不影响任何真实项目的正常取色。"""
    luma = _hex_luma(hexcolor)
    if luma >= floor:
        return hexcolor
    h = (hexcolor or "").lstrip("#")
    if len(h) != 6:
        return hexcolor
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return hexcolor
    t = min(0.6, max(0.0, (floor - luma) / max(1e-6, 1 - luma)))
    nr, ng, nb = (round(c + (255 - c) * t) for c in (r, g, b))
    return f"#{nr:02x}{ng:02x}{nb:02x}"


def _flat_fill(color):
    """所有风格共享的最朴素底色填充：一块纯色矩形，不含渐变/光晕/任何图形。
    风格函数需要渐变时自己在 base_svg 里追加 `<defs>`+径向/线性渐变，不强制
    使用本函数——这只是"最简单情形"的共享兜底，不是强加的统一底层骨架。"""
    return f'<rect width="1920" height="1080" fill="{color}"/>'


def _grid_lines(spacing, opacity, color, width=1, x0=0, y0=0, x1=1920, y1=1080):
    """通铺网格细线（横+纵），供「极简科技/网格数据」类风格使用。"""
    lines = []
    x = x0
    while x <= x1:
        lines.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="{color}" stroke-width="{width}" opacity="{opacity}"/>')
        x += spacing
    y = y0
    while y <= y1:
        lines.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{color}" stroke-width="{width}" opacity="{opacity}"/>')
        y += spacing
    return "".join(lines)


def _blob_path(cx, cy, r, rnd, seed_offset, points=9):
    """生成一个不规则圆角多边形的 SVG path（径向撒点 + 二次贝塞尔平滑首尾闭合），
    半径在 base r 的 72%-128% 之间抖动，模拟手工印刷/纸张边缘的不规整有机形状
    （区别于规则圆/矩形），供孔版叠印、有机叶形等风格使用。"""
    pts = []
    for i in range(points):
        ang = 2 * math.pi * i / points
        jitter = 0.72 + (rnd(seed_offset + i) % 56) / 100.0
        rad = r * jitter
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f} "
    n = len(pts)
    for i in range(n):
        p0, p1 = pts[i], pts[(i + 1) % n]
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        d += f"Q{p0[0]:.1f} {p0[1]:.1f} {mx:.1f} {my:.1f} "
    return d + "Z"


def _brush_stroke_path(x1, y1, x2, y2, rnd, seed_offset):
    """生成一段开放的手绘笔触路径（二次贝塞尔，端点间自然弓弯，不闭合），
    模拟毛笔运笔的粗细/走势变化。与 `_blob_path` 的区别：`_blob_path` 首尾
    相接闭合成一个面状形状，这里是首尾不相接的开放曲线，是"笔触"而不是
    "色块"。"""
    a = rnd(seed_offset)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    bend = (60 + a % 160) * (1 if a % 2 == 0 else -1)
    cxp, cyp = mx + nx * bend, my + ny * bend
    return f"M{x1:.1f} {y1:.1f} Q{cxp:.1f} {cyp:.1f} {x2:.1f} {y2:.1f}"


# ────────────────────── content 态统一弱化包装 ──────────────────────

def _content_wrap(deco_svg, kind, alpha_mult=1.0):
    """content 态：把装饰层整体缩小并挪到右下角（scale 以 (1920,1080) 为
    锚点收缩，天然产生"挪角落"的效果，不需要每个风格单独算平移量）+ 透明度
    在风格自身 alpha 基础上再乘一次弱化系数。cover/section/closing 原样
    返回，仅在 alpha_mult<1 时也应用（部分风格 section/closing 想用同一个
    包装做轻量弱化，见 `_KIND_ALPHA`）。"""
    if kind != "content":
        return deco_svg, alpha_mult
    scale = 0.42  # 缩小 58%，落在"缩小 50-70%"要求区间内
    anchor_x, anchor_y = 1920, 1080
    tx, ty = anchor_x * (1 - scale), anchor_y * (1 - scale)
    wrapped = f'<g transform="translate({tx:.1f} {ty:.1f}) scale({scale})">{deco_svg}</g>'
    return wrapped, alpha_mult * 0.45  # 透明度砍半以上


# kind -> 装饰层整体透明度（content 态在 _content_wrap 里再乘 0.45，此处只
# 负责 cover/section/closing 三种骨架页之间的强度节奏差异）
_KIND_ALPHA = {"cover": 1.0, "section": 0.9, "closing": 1.0, "content": 1.0}


# ═══════════════════ 风格一：极简科技/网格数据（动感版） ═══════════════════
# 参考范例：hud-grid —— 深底通铺网格细线 + 双层同心圆环角标（固定右下角，
# 像雷达瞄准镜）+ 十字准星 + 稀疏星点。适用：aerospace-defense-tech。

def style_tech_grid_hud(p, dna, kind, rnd):
    base_color = _ensure_min_luma(p[0])
    accent = p[min(2, len(p) - 1)]
    gx, gy = 1920 - 260, 1080 - 260  # 雷达角标固定在右下角，不居中
    base = (
        f'<defs><radialGradient id="hudGlow" cx="{gx}" cy="{gy}" r="900" gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{accent}" stop-opacity=".30"/><stop offset="1" stop-color="{base_color}" stop-opacity="0"/></radialGradient></defs>'
        f'{_flat_fill(base_color)}'
        f'<rect width="1920" height="1080" fill="url(#hudGlow)"/>'
    )
    grid = _grid_lines(40, 0.07, p[1 % len(p)])
    rings = "".join(
        f'<circle cx="{gx}" cy="{gy}" r="{60+i*46}" fill="none" stroke="{accent}" stroke-width="1.4" opacity="{.5-i*.12:.2f}"/>'
        for i in range(3)
    )
    cross = (
        f'<line x1="{gx-90}" y1="{gy}" x2="{gx+90}" y2="{gy}" stroke="{accent}" stroke-width="1" opacity=".4"/>'
        f'<line x1="{gx}" y1="{gy-90}" x2="{gx}" y2="{gy+90}" stroke="{accent}" stroke-width="1" opacity=".4"/>'
    )
    dots = "".join(
        f'<circle cx="{rnd(401+i)%1920}" cy="{rnd(451+i)%1080}" r="{1+rnd(401+i)%2}" fill="{p[1%len(p)]}" opacity="{.14+(rnd(401+i)%20)/100:.2f}"/>'
        for i in range(22)
    )
    return base, grid + rings + cross + dots


# ═══════════════════ 风格一：极简科技/网格数据（克制版） ═══════════════════
# 参考范例：blueprint-grid —— 网格更淡（约 22% 于动感版强度）、角标换成
# 空心方框而非圆环，无发光星场，像 CAD 制图纸。适用：academic-institutional
# / corporate-professional（需要"科技感但不夸张"的机构类项目）。

def style_tech_grid_blueprint(p, dna, kind, rnd):
    base_color = _ensure_min_luma(p[0])
    line_color = p[1 % len(p)]
    base = _flat_fill(base_color)
    grid = _grid_lines(52, 0.045, line_color)
    bl = 42
    corners = [(60, 60, 1, 1), (1860, 60, -1, 1), (60, 1020, 1, -1), (1860, 1020, -1, -1)]
    brackets = "".join(
        f'<path d="M{x} {y+sy*bl} L{x} {y} L{x+sx*bl} {y}" fill="none" stroke="{line_color}" stroke-width="1.6" opacity=".3"/>'
        for x, y, sx, sy in corners
    )
    bx, by = 1920 - 190, 140  # 主角标固定右上角，空心方框而非圆环
    box = (
        f'<rect x="{bx-46}" y="{by-46}" width="92" height="92" fill="none" stroke="{line_color}" stroke-width="1.3" opacity=".32"/>'
        f'<rect x="{bx-24}" y="{by-24}" width="48" height="48" fill="none" stroke="{line_color}" stroke-width="1" opacity=".24"/>'
    )
    return base, grid + brackets + box


# ═══════════════════ 风格二：复古人文/印刷质感 ═══════════════════
# 参考范例：riso-print（两个不规则圆润色块 multiply 叠印+错位套印描边）+
# Biennale Yellow（暖色纸底、极细墨线点缀）。适用：cultural-heritage-formal。

def style_print_texture(p, dna, kind, rnd):
    paper = _lightest(p)
    ink1, ink2 = p[1 % len(p)], p[2 % len(p)]
    base = _flat_fill(paper)
    dfx, dfy = dna.get("dark_focus", [1, 1])
    lfx, lfy = dna.get("light_focus", [1, 1])
    x1, y1 = _grid_to_px(dfx, dfy)
    x2, y2 = _grid_to_px(lfx, lfy)
    a = rnd(500)
    r1 = 230 + a % 200
    r2 = 190 + (a // 200) % 180
    blob1 = _blob_path(x1, y1, r1, rnd, 510)
    blob2 = _blob_path(x2 + 40, y2 - 30, r2, rnd, 530)
    misprint = _blob_path(x1 + 6, y1 + 5, r1, rnd, 510)  # 4-6px 位移，模拟套印不准
    prints = (
        f'<path d="{blob1}" fill="{ink1}" opacity=".4" style="mix-blend-mode:multiply"/>'
        f'<path d="{blob2}" fill="{ink2}" opacity=".36" style="mix-blend-mode:multiply"/>'
        f'<path d="{misprint}" fill="none" stroke="{ink1}" stroke-width="1.4" opacity=".35"/>'
    )
    inkline = f'<line x1="120" y1="960" x2="900" y2="960" stroke="{ink1}" stroke-width="1" opacity=".5"/>'
    return base, prints + inkline


# ═══════════════════ 风格三：几何色块/粗野主义 ═══════════════════
# 参考范例：Stencil & Tablet —— 骨白底上平铺多个圆角高饱和色块拼贴（无渐变
# 无阴影，像贴纸）；acid-block —— 纯色块+粗描边+硬投影(无模糊)+背景细网格。
# 适用：product-launch-design。

def style_geo_brutalist(p, dna, kind, rnd):
    # TASK-021 测试实测修复：此前 bone 恒取 _lightest(p)（骨白底），不区分 kind。
    # 但 render_deck.py 对 role-cover/section/closing 无条件把 .slide 的 --bg
    # 写死为 #06101d（深藏蓝近黑，见该文件 TASK-033/TASK-017 段），并把标题文字
    # 强制设为 --text:#f5f7fb（近白）——这是 SKILL.md 运行原则明确要求的"首尾页
    # 深藏蓝近黑实底"设计。geo-brutalist 的背景图以 82% 不透明度叠加在这个深色
    # 实底之上（见 deco.css .project-art-bg），若图本身还是骨白色，视觉上会把
    # 深色实底基本盖掉、呈现浅灰蓝色调，导致近白标题文字在这层浅底上对比度
    # 实测跌到 4-5.5:1（<QA 门禁 6:1）。骨架页（cover/section/closing）改用
    # _ensure_min_luma(p[0]) 深色底，配套把网格线/色块描边换成浅色（在深底上
    # 才可见），维持"硬边色块拼贴"的粗野主义语言不变，只是明暗基调随 kind
    # 切换；content 态维持原骨白底（浅色高亮的默认内容页设计方向不变）。
    is_skeleton = kind != "content"
    bone = _ensure_min_luma(p[0]) if is_skeleton else _lightest(p)
    line_color = _lightest(p) if is_skeleton else p[0]
    base = _flat_fill(bone) + _grid_lines(60, 0.03, line_color)
    positions = [(1500, 120), (1620, 420), (1440, 760), (220, 860), (160, 180), (560, 760)]
    blocks = []
    for i, (bx, by) in enumerate(positions):
        size = 110 + rnd(600 + i) % 90
        fill = p[(i + 1) % len(p)]
        dxs, dys = 10, 10  # 硬投影：方向性偏移，无模糊
        shadow_color = line_color if is_skeleton else p[0]
        blocks.append(f'<rect x="{bx+dxs}" y="{by+dys}" width="{size}" height="{size}" rx="24" fill="{shadow_color}" opacity=".18"/>')
        blocks.append(f'<rect x="{bx}" y="{by}" width="{size}" height="{size}" rx="24" fill="{fill}" stroke="{line_color}" stroke-width="3" opacity=".92"/>')
    return base, "".join(blocks)


# ═══════════════════ 风格四：有机手绘/温暖人文 ═══════════════════
# 参考范例：botanical-leaf —— 角落柔和椭圆光晕(暖色调) + 旋转空心叶形不对称
# 圆角图形；brush-sweep —— 开放式笔触扫痕。适用：cultural-heritage-warm。

def style_organic_warm(p, dna, kind, rnd):
    warm_base = _ensure_min_luma(p[0])
    glow_color = p[1 % len(p)]
    base = (
        f'<defs><radialGradient id="warmGlow" cx="220" cy="860" r="760" gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{glow_color}" stop-opacity=".38"/><stop offset="1" stop-color="{warm_base}" stop-opacity="0"/></radialGradient></defs>'
        f'{_flat_fill(warm_base)}'
        f'<rect width="1920" height="1080" fill="url(#warmGlow)"/>'
    )
    leaf_cx, leaf_cy = 1680, 260
    leaf_path = _blob_path(leaf_cx, leaf_cy, 190, rnd, 650, points=7)
    leaf = f'<path d="{leaf_path}" fill="none" stroke="{p[2%len(p)]}" stroke-width="2" opacity=".4" transform="rotate(18 {leaf_cx} {leaf_cy})"/>'
    strokes = []
    for i in range(2):
        a = rnd(660 + i)
        sx, sy = 300 + a % 200, 300 + (a // 200) % 200
        ex, ey = sx + 260 + a % 180, sy + 120
        path = _brush_stroke_path(sx, sy, ex, ey, rnd, 665 + i)
        strokes.append(f'<path d="{path}" fill="none" stroke="{p[(i+1)%len(p)]}" stroke-width="{7-i*2}" stroke-linecap="round" opacity="{.18+i*.05:.2f}"/>')
    grains = "".join(
        f'<circle cx="{rnd(670+i)%1920}" cy="{rnd(680+i)%1080}" r="1" fill="{glow_color}" opacity=".08"/>'
        for i in range(28)
    )
    return base, leaf + "".join(strokes) + grains


# ═══════════════════ 风格五：奢华质感/文艺克制 ═══════════════════
# 参考范例：Vellum —— 单一深色通铺全屏，画面角落固定一小段极简批注文字/
# 一条极细发丝线，零渐变、零阴影、零圆角，极度安静。适用：corporate-
# professional 高端定位项目（keyword/quant 驱动，不强占 domain 名额）。

def style_refined_literary(p, dna, kind, rnd):
    deep = _ensure_min_luma(p[0])
    line_color = p[1 % len(p)]
    base = _flat_fill(deep)  # 单一纯色通铺，无渐变
    hairline = f'<line x1="140" y1="960" x2="640" y2="960" stroke="{line_color}" stroke-width="1" opacity=".2"/>'
    tick = f'<line x1="140" y1="945" x2="140" y2="975" stroke="{line_color}" stroke-width="1" opacity=".3"/>'
    return base, hairline + tick


# ═══════════════════ 风格六：怀旧数字/潮流 ═══════════════════
# 参考范例：vapor-horizon —— 画面下方透视网格地平线(旋转延伸消失感)向上
# 渐变到深色天空，中间一条发光水平线；8-Bit Orbit 的 CRT 扫描线质感并入。
# 适用：consumer-lifestyle-future。

def style_retro_digital(p, dna, kind, rnd):
    sky_top = _ensure_min_luma(p[0])
    sky_bottom = _ensure_min_luma(p[1 % len(p)])
    glow = p[2 % len(p)]
    base = (
        f'<defs><linearGradient id="skyGrad" x2="0" y2="1"><stop stop-color="{sky_top}"/><stop offset="1" stop-color="{sky_bottom}"/></linearGradient></defs>'
        f'<rect width="1920" height="1080" fill="url(#skyGrad)"/>'
    )
    horizon_y = 680
    vp_x = 960
    perspective = [
        f'<line x1="{i*240}" y1="1080" x2="{vp_x}" y2="{horizon_y}" stroke="{glow}" stroke-width="1" opacity=".22"/>'
        for i in range(9)
    ]
    for j in range(5):
        y = horizon_y + 30 + j * j * 14
        perspective.append(f'<line x1="0" y1="{y}" x2="1920" y2="{y}" stroke="{glow}" stroke-width="1" opacity="{max(.28-j*.045,.03):.2f}"/>')
    horizon_line = f'<line x1="0" y1="{horizon_y}" x2="1920" y2="{horizon_y}" stroke="{glow}" stroke-width="2.5" opacity=".6"/>'
    scanlines = "".join(f'<line x1="0" y1="{y}" x2="1920" y2="{y}" stroke="{sky_top}" stroke-width="1" opacity=".05"/>' for y in range(0, 1080, 6))
    return base, "".join(perspective) + horizon_line + scanlines


# ─────────────────────────── 风格注册表 ───────────────────────────

STYLE_LIBRARY = {
    "tech-grid-hud": {
        "label": "极简科技/网格数据·动感版",
        "category": "极简科技/网格数据",
        "generator": style_tech_grid_hud,
        "keywords": ("科技", "航天", "数据", "仪表", "精密", "系统", "智能", "芯片", "算法", "工程", "蓝图", "坐标", "卫星", "雷达", "导弹", "火箭", "发射", "军工", "国防"),
        "description": "深底通铺网格细线(40px间距)+双层同心圆环角标(固定右下角,像雷达瞄准镜)+十字准星+稀疏星点。",
        "domains": ("aerospace-defense-tech",),
        "reference": "hud-grid",
    },
    "tech-grid-blueprint": {
        "label": "极简科技/网格数据·克制版",
        "category": "极简科技/网格数据",
        "generator": style_tech_grid_blueprint,
        "keywords": ("规程", "文牍", "档案", "制度", "规范", "机构", "科研", "学术", "合规", "流程", "标准", "评审", "评估", "报告"),
        "description": "网格更淡(约22%于动感版强度)+空心方框角标(非圆环)+四角CAD式括号,无发光星场,像制图纸。",
        "domains": ("academic-institutional", "corporate-professional"),
        "reference": "blueprint-grid",
    },
    "print-texture": {
        "label": "复古人文/印刷质感",
        "category": "复古人文/印刷质感",
        "generator": style_print_texture,
        "keywords": ("历史", "展览", "文物", "印刷", "版画", "档案", "博物", "考古", "民俗", "出版", "古籍"),
        "description": "两枚不规则圆润色块multiply叠印(4-6px错位模拟套印不准)+暖色纸底+一条极细墨线点缀。",
        "domains": ("cultural-heritage-formal",),
        "reference": "riso-print / Biennale Yellow",
    },
    "geo-brutalist": {
        "label": "几何色块/粗野主义",
        "category": "几何色块/粗野主义",
        "generator": style_geo_brutalist,
        "keywords": ("设计", "品牌", "极简", "现代", "发布", "产品", "几何", "建筑", "模块化", "包豪斯", "潮流", "新品"),
        "description": "骨白底平铺多个圆角高饱和色块拼贴(硬描边+方向性硬投影,无渐变无模糊)+背景细网格。",
        "domains": ("product-launch-design",),
        "reference": "Stencil & Tablet / acid-block",
    },
    "organic-warm": {
        "label": "有机手绘/温暖人文",
        "category": "有机手绘/温暖人文",
        "generator": style_organic_warm,
        "keywords": ("传统", "文化", "纪念", "手工", "纸", "复古", "书法", "篆刻", "匠人", "温暖", "非遗", "草木", "自然", "乡土"),
        "description": "角落柔和暖色椭圆光晕+一枚旋转的空心叶形不对称圆角图形+开放式笔触扫痕+纸纤维颗粒。",
        "domains": ("cultural-heritage-warm",),
        "reference": "botanical-leaf / brush-sweep",
    },
    "refined-literary": {
        "label": "奢华质感/文艺克制",
        "category": "奢华质感/文艺克制",
        "generator": style_refined_literary,
        "keywords": ("奢华", "尊享", "高端", "文艺", "雅致", "静谧", "克制", "品鉴", "典藏", "美学"),
        "description": "单一深色通铺全屏(零渐变零阴影零圆角)+一条极细发丝线+一段极简批注刻度,角落极度安静。",
        "domains": (),  # 不占用 domain 名额，纯 keyword/quant 驱动，作为 corporate-professional 高端场景的可选补充
        "reference": "Vellum",
    },
    "retro-digital": {
        "label": "怀旧数字/潮流",
        "category": "怀旧数字/潮流",
        "generator": style_retro_digital,
        "keywords": ("科幻", "未来", "沉浸", "梦幻", "电子", "潮流", "炫彩", "虚拟", "元宇宙", "赛博", "游戏", "数字", "像素"),
        "description": "下方40%透视网格地平线(旋转延伸消失感)向上渐变到深色天空,中间一条发光水平线+CRT扫描线。",
        "domains": ("consumer-lifestyle-future",),
        "reference": "vapor-horizon / 8-Bit Orbit",
    },
}

FALLBACK_STYLE = "tech-grid-blueprint"  # 全部信号都为 0 时的兜底：克制、任意 dna 输入都能产出合理结果


def _keyword_scores(keyword_text):
    text = keyword_text or ""
    return {key: sum(text.count(kw) for kw in spec["keywords"]) for key, spec in STYLE_LIBRARY.items()}


def _quant_scores(dna):
    """基于 detect_style.py/extract_art_dna.py 已算出的量化特征
    （饱和度/明暗对比/线条方向/暖色倾向）给每种风格打分——关键词信号和
    domain 信号都缺失或打平手时的兜底依据；有明确关键词/domain 命中时仍
    参与小权重修正（见 select_background_style 的合成公式），不会单独
    决定结果。判据均可解释：
    - tech-grid-hud：有明确方向性的线条语言 + 中高对比度 → 网格+角标需要
      "有方向感"的构图语言才不显得随意。
    - tech-grid-blueprint：均衡网格线条 + 中等饱和度 → 克制文牍气质需要
      不过分鲜艳、不过分强烈方向性的底子。
    - print-texture：均衡网格(不偏向任何一个方向) + 中等饱和度 + 偏暖 →
      孔版印刷传统上是中低饱和暖色调。
    - geo-brutalist：高对比度 + 中低饱和度 → 硬边色块需要足够的明暗区分度
      才不会糊成一团，饱和度太高反而抢戏。
    - organic-warm：低饱和度 + 低对比度 + 偏暖色相 → 柔和温暖的笔触/纸质感。
    - refined-literary：低饱和度 + 中高对比度 → 单色通铺需要足够的明暗
      区分度让文字仍可读，饱和度低才"安静"。
    - retro-digital：高饱和度 + 低对比度 → 霓虹/光雾感需要鲜艳但不需要强反差。
    """
    sat = dna.get("saturation", 0.4)
    contrast = dna.get("contrast", 0.3)
    line = dna.get("line_language", "均衡网格")
    palette = dna.get("palette") or ["#888888"]
    warm = _is_warm_hue(_hex_hue(palette[min(1, len(palette) - 1)]))
    scores = {k: 0.0 for k in STYLE_LIBRARY}
    scores["tech-grid-hud"] += (1.5 if line in ("纵向生长", "横向延展") else 0) + (1 if contrast > 0.32 else 0) + (1 if 0.35 <= sat <= 0.68 else 0)
    scores["tech-grid-blueprint"] += (1.5 if line == "均衡网格" else 0) + (1 if 0.25 <= sat <= 0.55 else 0)
    scores["print-texture"] += (1 if line == "均衡网格" else 0) + (1.5 if 0.25 <= sat <= 0.55 else 0) + (1 if warm else 0)
    scores["geo-brutalist"] += (1.5 if contrast > 0.38 else 0) + (1 if sat < 0.5 else 0)
    scores["organic-warm"] += (1.5 if sat < 0.35 else 0) + (1 if contrast < 0.30 else 0) + (1 if warm else 0)
    scores["refined-literary"] += (1.3 if sat < 0.3 else 0) + (1 if contrast > 0.3 else 0)
    scores["retro-digital"] += (1.5 if sat > 0.55 else 0) + (1 if contrast < 0.28 else 0)
    return scores


# domain 命中加成权重（沿用 TASK-041 三级优先级设计，未改动）。分级理由：
# - keyword-strong（deck.md/brief.md 体裁词断层领先，见 THEME_DOMAINS.md）
#   是项目级、跨全文统计的强信号，权重必须明显大于"局部关键词x10"能达到的
#   现实上限。
# - keyword-weak（domain 判断本身竞争激烈）给中等加成。
# - quant-fallback（domain 完全靠量化特征兜底得出，置信度最低）只给很小的
#   加成。
_DOMAIN_CONFIDENCE_BONUS = {
    "keyword-strong": 5000.0,
    "keyword-weak": 800.0,
    "quant-fallback": 150.0,
}


def _domain_bonus(domain, domain_confidence):
    """domain 命中加成：只对 STYLE_LIBRARY[k]["domains"] 包含该 domain 的
    风格加分，其余风格加 0。domain=None 时返回全 0，select_background_style
    完全退化为"关键词x10+量化"两级算法，不报错、不改变旧行为。"""
    scores = {k: 0.0 for k in STYLE_LIBRARY}
    if not domain:
        return scores
    bonus = _DOMAIN_CONFIDENCE_BONUS.get(domain_confidence, _DOMAIN_CONFIDENCE_BONUS["quant-fallback"])
    for key, spec in STYLE_LIBRARY.items():
        if domain in spec.get("domains", ()):
            scores[key] = bonus
    return scores


def select_background_style(dna, keyword_text="", domain=None, domain_confidence=None):
    """从背景风格库里选出最贴合当前项目的一种。三级优先级（与 TASK-041 一致，
    未改动匹配算法本身，只是风格库内容本次做了彻底重写）：

    1. **domain 命中（最高优先级）**：`state/theme_domain.json` 给出的项目级
       主题域判断，命中该 domain 的风格获得固定大权重加成
       （`_DOMAIN_CONFIDENCE_BONUS`）。`domain=None` 时该项加成全部为 0，
       完全退化为下面两级算法。
    2. **关键词信号**：deck.md 正文 + context/brief.md 项目简报里出现的
       STYLE_LIBRARY 风格关键词，命中权重 ×10。
    3. **量化特征信号兜底/修正**：见 `_quant_scores` 注释。

    三者相加取最高分风格；全部风格得分都是 0 时退回 `FALLBACK_STYLE`
    （`tech-grid-blueprint`，克制、任意 dna 输入都能产出合理结果的兜底选择）。

    返回 (style_key, trace)：trace 是可读的判断依据列表，写入 art_dna.json
    的 background_style_reason 字段供人工/QA 追溯，不做黑箱决策。
    """
    kw_scores = _keyword_scores(keyword_text)
    quant_scores = _quant_scores(dna)
    domain_scores = _domain_bonus(domain, domain_confidence)
    total = {k: domain_scores[k] + kw_scores[k] * 10 + quant_scores[k] for k in STYLE_LIBRARY}
    best = max(total, key=lambda k: total[k])
    if total[best] == 0:
        best = FALLBACK_STYLE
    kw_hits = {k: v for k, v in kw_scores.items() if v}
    quant_rounded = {k: round(v, 2) for k, v in quant_scores.items()}
    total_rounded = {k: round(v, 2) for k, v in total.items()}
    trace = [
        f"domain 命中：{domain}（置信度 {domain_confidence}）" if domain else "domain 命中：无（未传 domain 参数，退化为两级算法）",
        f"domain 加成：{ {k: v for k, v in domain_scores.items() if v} or '无'}",
        f"关键词命中：{kw_hits if kw_hits else '无'}",
        f"量化特征评分：{quant_rounded}",
        f"合成得分（domain加成+关键词x10+量化）：{total_rounded}",
        f"选定风格：{best}（{STYLE_LIBRARY[best]['label']}）",
    ]
    return best, trace


def generate_full_background(style_key, p, dna, kind, rnd):
    """按选定风格 key 组装一份完整背景 SVG 片段（供 extract_art_dna.py::svg()
    直接插入 `<svg>` 根元素内）：`base_svg`（该风格自己的底色/渐变）+ 一层
    `<g opacity=...>` 包裹的 `deco_svg`（该风格的全部装饰元素，cover/section/
    closing 按 `_KIND_ALPHA` 节奏取值；content 态额外走 `_content_wrap()`
    统一弱化）。未知 key 兜底走 FALLBACK_STYLE，不抛异常（art_dna.json 是
    流水线核心产物，防御性兜底优先于严格校验）。"""
    spec = STYLE_LIBRARY.get(style_key) or STYLE_LIBRARY[FALLBACK_STYLE]
    base_svg, deco_svg = spec["generator"](p, dna, kind, rnd)
    alpha = _KIND_ALPHA.get(kind, 1.0)
    deco_svg, alpha = _content_wrap(deco_svg, kind, alpha)
    return f'{base_svg}<g opacity="{alpha:.3f}">{deco_svg}</g>'
