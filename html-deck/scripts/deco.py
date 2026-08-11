#!/usr/bin/env python3
"""场景基因装饰层 SVG 生成器（配套 assets/components/deco.css）。

四类设计基因（几何参数取自客户项目实测效果）：
  · 奖牌圆环  rings()      —— 刻度圆环 + 高亮弧段
  · 数据光柱  stems()      —— 发光柱阵（暖色 + 冰蓝点缀，呼吸动画）
  · 流动动线  path_line()  —— 渐变 S 曲线（描边动画）
  · 铭牌矩阵  plaques()    —— 封面铭牌条 / 中间页点阵

所有颜色通过 class 上色（见 deco.css），自动跟随主题 --accent 派生色，
任何主题（dark / light / editorial…）下都保持协调。
"""

COVER_STEM_HEIGHTS = [150, 210, 120, 240, 170, 265, 140, 290, 190, 230, 110,
                      250, 175, 300, 160, 225, 130, 255, 185, 205, 95, 145]
COVER_STEM_BLUE = {2, 7, 12, 17}

CLOSING_STEM_HEIGHTS = [200, 260, 180, 300, 220, 340, 240, 360, 260, 310, 190,
                        330, 230, 370, 250, 290, 210, 320, 240, 270, 170]
CLOSING_STEM_BLUE = {3, 9, 15}


def _fmt(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in {"-0", ""} else "0"


def stems(x0, step, heights, blue_idx, glow_ids=("cgGlow", "cgGlowB"), delay_step=0.35):
    """数据光柱阵：底部 y=1080 向上生长，柱顶发光泪滴 + 光晕，呼吸动画错峰。"""
    warm_glow, ice_glow = glow_ids
    parts = []
    for i, h in enumerate(heights):
        x = x0 + step * i
        y2 = 1080 - h
        cy = y2 - 8
        blue = i in blue_idx
        stem_cls = "deco-stem-ice" if blue else "deco-stem"
        tip_cls = "deco-tip-ice" if blue else "deco-tip-warm"
        glow = ice_glow if blue else warm_glow
        parts.append(
            f'<g class="deco-tip" style="animation-delay:{_fmt(-i * delay_step)}s">'
            f'<line class="{stem_cls}" x1="{x}" y1="1080" x2="{x}" y2="{y2}"/>'
            f'<ellipse class="{tip_cls}" cx="{x}" cy="{cy}" rx="6.5" ry="12"/>'
            f'<circle cx="{x}" cy="{cy}" r="17" fill="url(#{glow})" opacity=".7"/></g>'
        )
    return "".join(parts)


def rings(cx, cy, r_hi, bright_dash, rotate):
    """奖牌圆环：外圈金线 + 中环 + 刻度虚线环 + 高亮弧段。r_hi 为高亮弧半径。"""
    return (
        f'<g transform="translate({cx},{cy})">'
        f'<circle class="deco-ring-outer" r="{int(r_hi * 1.42)}"/>'
        f'<circle class="deco-ring-mid" r="{int(r_hi * 1.19)}"/>'
        f'<circle class="deco-ring-tick" r="{r_hi}" stroke-dasharray="2 10"/>'
        f'<circle class="deco-ring-hi" r="{r_hi}" stroke-dasharray="{bright_dash}" transform="rotate({rotate})"/>'
        f'</g>'
    )


def path_line(d_main, d_ghost, grad_id, end_xy):
    """流动动线：主线（渐变 + 描边动画）+ 平行影线和终点金珠光晕。"""
    ex, ey = end_xy
    return (
        f'<path class="deco-path-ghost" d="{d_ghost}"/>'
        f'<path class="deco-path" d="{d_main}" stroke="url(#{grad_id})"/>'
        f'<circle class="deco-dot" cx="{ex}" cy="{ey}" r="8"/>'
        f'<circle cx="{ex}" cy="{ey}" r="20" fill="url(#cgGlow)"/>'
    )


def plaques(tx=86, ty=108, count=5, active=2):
    """铭牌条：封面左上角的荣誉铭牌矩阵缩略，active 索引为'新荣誉'点亮牌。"""
    w, h, gap = 56, 76, 18
    rects, lines = [], []
    for i in range(count):
        x = i * (w + gap)
        if i == active:
            rects.append(f'<rect class="deco-plaque-on" x="{x}" y="0" width="{w}" height="{h}" rx="6"/>')
            lines.append(
                f'<line class="deco-plaque-line-on" x1="{x + 13}" y1="26" x2="{x + 43}" y2="26"/>'
                f'<line class="deco-plaque-line-on" x1="{x + 13}" y1="40" x2="{x + 36}" y2="40"/>'
            )
        else:
            rects.append(f'<rect class="deco-plaque" x="{x}" y="0" width="{w}" height="{h}" rx="6"/>')
            lines.append(
                f'<line class="deco-plaque-line" x1="{x + 13}" y1="26" x2="{x + 43}" y2="26"/>'
                f'<line class="deco-plaque-line" x1="{x + 13}" y1="40" x2="{x + 36}" y2="40"/>'
            )
    return f'<g transform="translate({tx},{ty})">{"".join(rects)}<g>{"".join(lines)}</g></g>'


def _defs(grad_id):
    return (
        f'<defs>'
        f'<linearGradient id="{grad_id}" x1="0" y1="1" x2="1" y2="0">'
        f'<stop class="gs0" offset="0"/><stop class="gs1" offset=".55"/><stop class="gs2" offset="1"/>'
        f'</linearGradient>'
        f'<radialGradient id="cgGlow"><stop class="gs-warm0" offset="0"/><stop class="gs-warm1" offset="1"/></radialGradient>'
        f'<radialGradient id="cgGlowB"><stop class="gs-ice0" offset="0"/><stop class="gs-ice1" offset="1"/></radialGradient>'
        f'</defs>'
    )


def _svg(cls, inner):
    return (
        f'<svg class="deco {cls}" viewBox="0 0 1920 1080" '
        f'preserveAspectRatio="xMidYMid slice" aria-hidden="true">{inner}</svg>'
    )


def cover_deco():
    """封面装饰层：圆环(1460,400) + 动线入环 + 底部光柱阵 + 左上铭牌条。"""
    inner = (
        _defs("covPath")
        + rings(1460, 400, 338, "330 1794", -38)
        + path_line(
            "M-40 1004 C 360 946, 540 792, 830 822 C 1080 848, 1290 700, 1460 400",
            "M-40 1028 C 360 970, 540 816, 830 846 C 1080 872, 1290 724, 1460 424",
            "covPath", (1460, 400))
        + '<g class="deco-stems">'
        + stems(1180, 32, COVER_STEM_HEIGHTS, COVER_STEM_BLUE)
        + '</g>'
        + plaques()
    )
    return _svg("cover-deco", inner)


def closing_deco():
    """结尾装饰层：与封面同语言，圆环(1660,230)、动线收官、更高光柱阵（生长完成）。"""
    inner = (
        _defs("clsPath")
        + rings(1660, 230, 176, "200 906", 110)
        + path_line(
            "M-40 1010 C 420 960, 700 872, 1020 892 C 1310 910, 1560 640, 1630 300",
            "M-40 1032 C 420 982, 700 894, 1020 914 C 1310 932, 1560 662, 1630 322",
            "clsPath", (1630, 300))
        + '<g class="deco-stems">'
        + stems(1240, 30, CLOSING_STEM_HEIGHTS, CLOSING_STEM_BLUE,
                glow_ids=("cgGlow", "cgGlowB"), delay_step=0.3)
        + '</g>'
    )
    return _svg("closing-deco", inner)


def quiet_deco(section=False):
    """中间页简洁背景：左下淡动线 + 右上铭牌点阵 + 右下光柱嫩芽；章节页追加圆环。"""
    dots = []
    for r in range(3):
        for c in range(4):
            dots.append(
                f'<rect class="deco-quiet-dot" x="{1736 + c * 30}" y="{70 + r * 29}" width="13" height="19" rx="2"/>'
            )
    inner = (
        '<path class="deco-quiet-path" d="M-30 1042 C 300 992, 430 922, 660 932 S 1010 852, 1130 800"/>'
        '<path class="deco-quiet-path2" d="M-30 1064 C 300 1014, 430 944, 660 954 S 1010 874, 1130 822"/>'
        f'<g>{"".join(dots)}</g>'
        '<g>'
        '<line class="deco-quiet-stem" x1="1780" y1="1080" x2="1780" y2="1012"/>'
        '<line class="deco-quiet-stem" x1="1816" y1="1080" x2="1816" y2="984"/>'
        '<line class="deco-quiet-stem" x1="1852" y1="1080" x2="1852" y2="1024"/>'
        '<circle class="deco-quiet-tip" cx="1780" cy="1006" r="4"/>'
        '<circle class="deco-quiet-tip-ice" cx="1816" cy="978" r="4"/>'
        '<circle class="deco-quiet-tip" cx="1852" cy="1018" r="4"/>'
        '</g>'
    )
    if section:
        inner += (
            '<g transform="translate(1500,540)">'
            '<circle class="deco-ring-outer" r="380"/>'
            '<circle class="deco-ring-mid" r="330"/>'
            '<circle class="deco-ring-tick" r="284" stroke-dasharray="2 11"/>'
            '<circle class="deco-ring-hi" r="284" stroke-dasharray="260 1524" transform="rotate(-55)"/>'
            '</g>'
        )
    return _svg("quiet-deco", inner)
