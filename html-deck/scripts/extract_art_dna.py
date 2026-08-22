#!/usr/bin/env python3
"""从项目图片提取可复现的艺术表达 DNA，并生成非模板化封面/尾页 SVG 背景。"""
import argparse, colorsys, hashlib, json, math, struct, zlib
from pathlib import Path
from common import read_json, write_json, attach_motifs
# TASK-039: 背景风格库——把"装饰层画什么构图"从本文件硬编码里拆出来，按项目
# 内容（关键词+量化特征）匹配选择，详见 bg_styles.py 与
# references/BACKGROUND_STYLES.md。
import bg_styles

def args():
    p=argparse.ArgumentParser(description="Extract project art DNA and generate cover/closing SVG backgrounds.")
    p.add_argument("--manifest", required=True); p.add_argument("--output", required=True)
    p.add_argument("--assets-dir", required=True)
    # TASK-028: 可选——项目主题线条插画装饰映射（缺省取 --output 同目录下的 art_motifs.json）
    p.add_argument("--motifs", required=False, help="state/art_motifs.json：主题图形关键词->线条SVG素材映射")
    # TASK-039: 可选——用于背景风格匹配的关键词来源；缺省自动探测项目根目录下的
    # deck.md 与 context/brief.md（只读扫描关键词，不会修改这两个文件）
    p.add_argument("--deck", required=False, help="deck.md 路径（可选，缺省自动探测）：正文关键词用于背景风格匹配")
    p.add_argument("--brief", required=False, help="context/brief.md 路径（可选，缺省自动探测）：scene_type/style_keywords 等字段是背景风格匹配的强信号")
    # TASK-041: 可选——指向 classify_theme_domain.py 产出的 state/theme_domain.json，
    # 解析 domain/confidence 传给 bg_styles.select_background_style() 作为最高优先级
    # 信号；缺省或文件不存在/解析失败时静默退化为关键词+量化两级算法，不阻断主产物。
    p.add_argument("--theme-domain", required=False, help="state/theme_domain.json 路径（可选）：项目主题域判定结果，作为背景风格选择的最高优先级输入")
    return p.parse_args()

def hexrgb(c): return "#%02x%02x%02x" % c

# ── 色彩发散检测（本轮新增）──────────────────────────────────────────────
# 背景：用户实测案例 project-jixueyuan——原本提供 5 张并列关系的图片，其中一张
# 红色底图被命名为"主视图"，导致 main() 里"取权重最高来源"的既有逻辑只用这
# 一张图的调色板，就让红色变成了整个项目封面/章节/尾页的主题色，而实际 5 张
# 图并无主次之分、主体颜色也不是红色。
#
# 本节新增一条兜底规则：当存在多个来源时，先检测各来源"色彩身份"色（约定取
# 各来源 dna.palette[0]，即 semantic_palette() 语义里的 dark/基底色——也是
# bg_styles.py 全程当作背景基色 p[0] 使用的那个值，见 bg_styles.py 顶部注释）
# 两两之间的色相冲突程度；只有冲突大到真的无法归纳出统一主体色彩风格时，才
# 放弃"挑一个来源当赢家"的做法，改用内容页正在使用的基础色兜底（见
# content_page_base_palette()）。判定刻意从严、宁可漏判也不误判：同一色系内
# 的深浅/明暗差异、个别来源的孤立小差异都不触发；只有确实存在多个互相冲突的
# 色相阵营（如红色系 vs 蓝色系 vs 绿色系这种跨度很大的分布）才触发。
_HUE_CLUSTER_GAP_DEG = 55   # 相邻色相超过此间隔视为不同"色系阵营"边界（同色系内深浅差异不会超过此值）
_HUE_CONFLICT_DEG = 110     # 阵营间中心色相差需超过此值才判定为真冲突。原定120°，用户实测真实
                             # 案例（project-jixueyuan：同一面文化墙的红/粉紫/紫/蓝4个配色方案，
                             # 用户明确说明这些是并列可选方案而非确定色彩身份）算出阵营间色相差
                             # 114°，恰好卡在120°之下漏判，属于本规则设计初衷就该覆盖的场景；
                             # 按此真实标注数据下调阈值，仍保留一定保守余量（不下调到接近55°的
                             # 聚类边界本身，避免退化成"只要有两个来源就基本必触发"）。
_MIN_CHROMA_FOR_HUE = 0.15  # 饱和度低于此值视为中性色（黑白灰），色相无意义，不参与阵营判定

def _identity_hue(hex_color):
    """把一个来源的"色彩身份"色转成 (hue度, s, v)。"""
    hx = hex_color.lstrip("#")
    r, g, b = (int(hx[i:i+2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s, v

def _hue_circular_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def color_divergence_check(items):
    """items: [(来源标识, 该来源的色彩身份 hex), ...]，每个来源各一条。

    返回 (diverged, reason, camps)：
    - diverged=False 时不触发兜底，reason 说明原因（数据不足/未达冲突阈值），
      调用方应完全沿用既有"取权重最高/主图"逻辑，不做任何改动。
    - diverged=True 时触发兜底，reason 是可写入 report 的中文说明（含检测到
      的阵营数、色相中心、最大色相差，供人工审查），camps 是聚类调试信息。
    """
    if len(items) < 2:
        if not items:
            return False, "未提供可比较的来源色彩身份数据，跳过色彩发散检测", []
        return False, f"仅 {len(items)} 个来源，无法比较，跳过色彩发散检测", []
    chroma = []
    for sid, hexc in items:
        try:
            h, s, v = _identity_hue(hexc)
        except Exception:
            continue
        if s >= _MIN_CHROMA_FOR_HUE:
            chroma.append((sid, hexc, h, s, v))
    if len(chroma) < 2:
        return False, f"有效彩色来源不足 2 个（{len(chroma)}/{len(items)} 个饱和度达标 {_MIN_CHROMA_FOR_HUE}），跳过色彩发散检测", []
    order = sorted(chroma, key=lambda x: x[2])
    camps = [[order[0]]]
    for it in order[1:]:
        if _hue_circular_dist(it[2], camps[-1][-1][2]) > _HUE_CLUSTER_GAP_DEG:
            camps.append([it])
        else:
            camps[-1].append(it)
    # 色相是环形的，360°与 0°相邻，首尾阵营若挨得够近需合并，避免环绕处被误判为两个阵营
    if len(camps) > 1 and _hue_circular_dist(camps[-1][-1][2], camps[0][0][2]) <= _HUE_CLUSTER_GAP_DEG:
        camps[0] = camps[-1] + camps[0]
        camps.pop()
    if len(camps) < 2:
        return False, f"{len(chroma)} 个彩色来源聚为同一色系阵营，判定为深浅差异而非色彩冲突，跳过兜底", camps
    centroids = [sum(c[2] for c in camp) / len(camp) for camp in camps]
    max_gap, pair = 0, (0, 0)
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            d = _hue_circular_dist(centroids[i], centroids[j])
            if d > max_gap:
                max_gap, pair = d, (i, j)
    if max_gap < _HUE_CONFLICT_DEG:
        return False, (f"{len(camps)} 个色相阵营，最大阵营间色相差 {max_gap:.0f}°，"
                        f"未达 {_HUE_CONFLICT_DEG}° 冲突阈值，判定为同色系深浅差异，跳过兜底"), camps
    names = ["、".join(c[0] for c in camp) for camp in camps]
    detail = "、".join(f"{centroids[i]:.0f}°({names[i]})" for i in range(len(camps)))
    reason = (f"检测到 {len(chroma)} 个彩色来源分裂为 {len(camps)} 个色相阵营（{detail}），"
              f"阵营间最大色相差达 {max_gap:.0f}°（>= {_HUE_CONFLICT_DEG}° 阈值），"
              f"无法归纳出统一主体色彩风格，判定为色彩发散：放弃从冲突来源中挑选赢家色调，"
              f"改用内容页基础色兜底")
    return True, reason, camps

def _project_root(output_path):
    """由 --output（通常是 state/art_dna.json）推断项目根目录，与 _load_keyword_text()
    的探测口径一致。"""
    out_path = Path(output_path).resolve()
    return out_path.parent.parent if out_path.parent.name == "state" else out_path.parent

_SAFE_FALLBACK_DARK = "#123a6b"     # 与 assets/themes/proposal-light.css --accent 一致：深蓝信息骨架
_SAFE_FALLBACK_ACCENT2 = "#1fa8d8"  # 与该主题 --accent-2 一致：青蓝辅助
_SAFE_FALLBACK_LIGHT = "#f7fafd"    # 与该主题 --bg 一致：浅色高亮主背景
_SAFE_FALLBACK_NEUTRAL = "#55677f"  # 与该主题 --muted 一致：灰蓝辅助，不引入任何来源色相偏向

def _read_style_report(output_path):
    """定位并读取当前项目 state/style_report.json（detect_style.py 产出，按 SKILL.md
    流水线顺序，先于 art DNA 提取运行），色彩发散兜底时用它取"内容页正在使用的基础
    配色"。找不到/解析失败时返回 None，调用方退化为中性安全默认色。"""
    try:
        sr_path = _project_root(output_path) / "state" / "style_report.json"
        if sr_path.exists():
            return read_json(sr_path)
    except Exception:
        pass
    return None

def content_page_base_palette(output_path):
    """色彩发散兜底调色板：不从互相冲突的多个来源里硬挑一个"赢家"色调，改用内容页
    正在使用的基础配色 token（state/style_report.json 的 accent/accent_2）。该文件
    理论上已在流水线更早步骤生成（见 SKILL.md），此处仍做防御性兜底——文件缺失/
    字段缺失时退化为 SKILL.md「默认视觉方向设计token」的中性安全默认色（深藏蓝/
    青蓝/中性灰），不引入任何一个冲突来源自身的色相。返回值沿用 semantic_palette()
    的 [dark, warm, cool, light, accent, dominant] 6 槽位约定，保证 bg_styles.py 的
    下标消费方式（p[0]/p[1%len(p)]/... 见 bg_styles.py 顶部注释）不受影响。"""
    sr = _read_style_report(output_path) or {}
    accent = sr.get("accent") or _SAFE_FALLBACK_DARK
    accent2 = sr.get("accent_2") or _SAFE_FALLBACK_ACCENT2
    return [accent, _SAFE_FALLBACK_NEUTRAL, accent2, _SAFE_FALLBACK_LIGHT, accent, accent2]
# ── 色彩发散检测结束 ────────────────────────────────────────────────────

def semantic_palette(px):
    """保留深色基底，同时强制捕获面积较小但有识别度的金属/品牌强调色。"""
    buckets={}
    for c in px:
        key=tuple((v//24)*24+12 for v in c); buckets[key]=buckets.get(key,0)+1
    rows=[]
    for c,count in buckets.items():
        h,s,v=colorsys.rgb_to_hsv(*(x/255 for x in c)); rows.append((c,count,s,v,h))
    dark=min(rows,key=lambda r:(r[0][0]+r[0][1]+r[0][2]))[0]
    dominant=max(rows,key=lambda r:r[1])[0]
    accent=max(rows,key=lambda r:r[1]*(.25+r[2]**1.7)*(.25+r[3]))[0]
    warm=max(rows,key=lambda r:r[1]*r[2]*r[3] if .045<r[4]<.19 and r[3]>.28 else 0)[0]
    light=max(rows,key=lambda r:(sum(r[0]),r[1]))[0]
    cool=max(rows,key=lambda r:r[1]*(.2+r[2]) if .50<r[4]<.72 else 0)[0]
    result=[]
    for c in (dark,warm,cool,light,accent,dominant):
        if c not in result: result.append(c)
    return [hexrgb(c) for c in result]

def analyze(path):
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return analyze_png(path)
    im=Image.open(path).convert("RGB"); im.thumbnail((180,180)); px=list(im.getdata())
    palette=semantic_palette(px)
    g=im.convert("L"); edge=g.filter(ImageFilter.FIND_EDGES)
    cols=[sum(edge.getpixel((x,y)) for y in range(edge.height)) for x in range(edge.width)]
    rows=[sum(edge.getpixel((x,y)) for x in range(edge.width)) for y in range(edge.height)]
    vertical=sum(cols)/max(1,len(cols)); horizontal=sum(rows)/max(1,len(rows))
    thirds=[]
    for yy in range(3):
        for xx in range(3):
            crop=g.crop((xx*g.width//3,yy*g.height//3,(xx+1)*g.width//3,(yy+1)*g.height//3))
            thirds.append(sum(crop.getdata())/max(1,len(list(crop.getdata()))))
    darkest=min(range(9), key=lambda i:thirds[i]); brightest=max(range(9), key=lambda i:thirds[i])
    sat=sum(colorsys.rgb_to_hsv(r/255,g/255,b/255)[1] for r,g,b in px)/max(1,len(px))
    contrast=(max(thirds)-min(thirds))/255
    # BUGFIX（预置缺陷，与 TASK-028 改动无关，随本轮修复）：semantic_palette() 已经把
    # 色值元组转成十六进制字符串返回，这里再对字符串跑一次 hexrgb() 必崩溃（"%x" 需要
    # int，不是 str）；只在装了 Pillow 时才走这条 analyze() 路径，之前很可能一直是
    # analyze_png() 无 Pillow 兜底路径在实际生效，这条路径没有二次调用、不受影响。
    return {"palette":palette,"line_language":"纵向生长" if vertical>horizontal*1.08 else "横向延展" if horizontal>vertical*1.08 else "均衡网格","dark_focus":[darkest%3,darkest//3],"light_focus":[brightest%3,brightest//3],"saturation":round(sat,3),"contrast":round(contrast,3)}

def analyze_png(path):
    """无 Pillow 降级：用标准库解码 8-bit 非交错 RGB/RGBA PNG。"""
    raw=path.read_bytes()
    if raw[:8]!=b'\x89PNG\r\n\x1a\n': raise RuntimeError("Pillow 缺失且输入不是受支持的 PNG")
    pos=8; data=b''; width=height=ctype=None
    while pos<len(raw):
        n=struct.unpack('>I',raw[pos:pos+4])[0]; typ=raw[pos+4:pos+8]; chunk=raw[pos+8:pos+8+n]; pos+=12+n
        if typ==b'IHDR': width,height,depth,ctype,_,_,interlace=struct.unpack('>IIBBBBB',chunk)
        elif typ==b'IDAT': data+=chunk
        elif typ==b'IEND': break
    if depth!=8 or ctype not in (2,6) or interlace: raise RuntimeError("标准库降级仅支持 8-bit 非交错 RGB/RGBA PNG")
    bpp=3 if ctype==2 else 4; stream=zlib.decompress(data); stride=width*bpp; rows=[]; off=0; prev=bytearray(stride)
    def paeth(a,b,c):
        p=a+b-c; pa=abs(p-a); pb=abs(p-b); pc=abs(p-c)
        return a if pa<=pb and pa<=pc else b if pb<=pc else c
    for _ in range(height):
        ft=stream[off]; scan=bytearray(stream[off+1:off+1+stride]); off+=stride+1
        for i in range(stride):
            a=scan[i-bpp] if i>=bpp else 0; b=prev[i]; c=prev[i-bpp] if i>=bpp else 0
            if ft==1: scan[i]=(scan[i]+a)&255
            elif ft==2: scan[i]=(scan[i]+b)&255
            elif ft==3: scan[i]=(scan[i]+((a+b)//2))&255
            elif ft==4: scan[i]=(scan[i]+paeth(a,b,c))&255
        rows.append(scan); prev=scan
    step=max(1,min(width,height)//120); px=[]; lumagrid=[]
    for y in range(0,height,step):
        line=[]
        for x in range(0,width,step):
            i=x*bpp; rgb=tuple(rows[y][i:i+3]); px.append(rgb); line.append(sum(rgb)/3)
        lumagrid.append(line)
    palette=semantic_palette(px)
    thirds=[]; gh=len(lumagrid); gw=len(lumagrid[0])
    for yy in range(3):
        for xx in range(3):
            vals=[lumagrid[y][x] for y in range(yy*gh//3,(yy+1)*gh//3) for x in range(xx*gw//3,(xx+1)*gw//3)]
            thirds.append(sum(vals)/max(1,len(vals)))
    vx=sum(abs(row[x]-row[x-1]) for row in lumagrid for x in range(1,gw)); hy=sum(abs(lumagrid[y][x]-lumagrid[y-1][x]) for y in range(1,gh) for x in range(gw))
    sat=sum(colorsys.rgb_to_hsv(r/255,g/255,b/255)[1] for r,g,b in px)/max(1,len(px)); darkest=min(range(9),key=lambda i:thirds[i]); brightest=max(range(9),key=lambda i:thirds[i])
    return {"palette":palette,"line_language":"纵向生长" if vx>hy*1.08 else "横向延展" if hy>vx*1.08 else "均衡网格","dark_focus":[darkest%3,darkest//3],"light_focus":[brightest%3,brightest//3],"saturation":round(sat,3),"contrast":round((max(thirds)-min(thirds))/255,3)}

def svg(dna, kind, seed, keyword_text="", domain=None, domain_confidence=None):
    """生成同一视觉系统的页面角色变体，而不是只给首尾页换皮。

    TASK-042（彻底重写，接力 TASK-039/041）：此前本函数除了调用风格库产出
    的"图案层"（motif）外，自己还固定画三样东西——①基于 light_focus 定位的
    柔光大椭圆、②18 条完全随机位置/角度的对角直线、③7 个完全随机大小/位置
    的同心圆环——不管选中哪种风格，这三样都会画，是"不同主题项目背景看起来
    还是很像"的真正根因（用户截图看到的"一堆圆环+对角线"）。这三段固定骨架
    本次已彻底删除。

    本函数现在只是一层很薄的胶水：调用 bg_styles.select_background_style()
    按 dna 量化特征 + 关键词（keyword_text，来自 deck.md/context/brief.md）+
    domain（来自 state/theme_domain.json 的项目主题域判定，最高优先级）匹配
    选出一种背景风格，再调用 bg_styles.generate_full_background() 让该风格
    自己产出完整背景（基础色底/渐变 + 全部装饰元素），本函数只负责拼装
    viewBox/defs（一层不构成"图案"的通用噪点纹理，仅纹理不成形状，不算
    风格骨架）/镜像翻转（尾页）等最外层结构。不同项目、不同分析结果会得到
    真正不同的构图，不再是"同一套骨架换配色"。风格库详见 bg_styles.py 与
    references/BACKGROUND_STYLES.md。
    """
    p=dna["palette"] or ["#071426","#c99848","#f3e4be"]
    rnd=lambda n: int(hashlib.sha256(f"{seed}:{kind}:{n}".encode()).hexdigest()[:8],16)
    flip='translate(1920 0) scale(-1 1)' if kind=='closing' else ''
    style_key,_=bg_styles.select_background_style(dna, keyword_text, domain, domain_confidence)
    background=bg_styles.generate_full_background(style_key, p, dna, kind, rnd)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"><defs><filter id="grain"><feTurbulence baseFrequency=".8" numOctaves="2" seed="{rnd(99)%99}"/><feColorMatrix values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 .035 0"/></filter></defs><g transform="{flip}">{background}</g><rect width="1920" height="1080" filter="url(#grain)" opacity=".26"/></svg>'''

def _load_keyword_text(a):
    """TASK-039: 收集背景风格匹配用的项目关键词文本——只读扫描 deck.md 与
    context/brief.md，不修改任何一个文件。显式传 --deck/--brief 时优先使用；
    否则按 --output（通常是 state/art_dna.json）推断项目根目录自动探测。
    两个来源都缺失或读取失败时静默返回空串，风格选择退化为纯量化特征匹配，
    不阻断主产物生成。"""
    out_path=Path(a.output).resolve()
    project_root = out_path.parent.parent if out_path.parent.name=="state" else out_path.parent
    deck_path = Path(a.deck) if a.deck else project_root/"deck.md"
    brief_path = Path(a.brief) if a.brief else project_root/"context"/"brief.md"
    text=""
    for kp in (deck_path, brief_path):
        if kp.exists():
            try: text += "\n" + kp.read_text(encoding="utf-8")
            except Exception: pass
    return text

def _load_theme_domain(a):
    """TASK-041: 读取 --theme-domain 指向的 state/theme_domain.json，解析出
    domain/confidence 供背景风格选择使用。参数缺省、文件不存在、或解析失败
    时静默返回 (None, None)——select_background_style() 对 domain=None 有
    明确的向后兼容退化路径（完全退回关键词+量化两级算法），不阻断主产物。"""
    if not a.theme_domain:
        return None, None
    tp = Path(a.theme_domain)
    if not tp.exists():
        return None, None
    try:
        data = read_json(tp)
        return data.get("domain"), data.get("confidence")
    except Exception:
        return None, None

def _write_report(a, dna, expression, style_key, style_trace, seed, source_mode, source_image_ids, primary_image_id, diverged, div_reason):
    outdir=Path(a.assets_dir); outdir.mkdir(parents=True,exist_ok=True)
    keyword_text=_load_keyword_text(a)
    domain,domain_confidence=_load_theme_domain(a)
    cover=outdir/"project-cover.svg"; content=outdir/"project-content.svg"; section=outdir/"project-section.svg"; closing=outdir/"project-closing.svg"
    for path,kind in ((cover,"cover"),(content,"content"),(section,"section"),(closing,"closing")):
        path.write_text(svg(dna,kind,seed,keyword_text,domain,domain_confidence),encoding="utf-8")
    report={"version":"2.0","source_mode":source_mode,"source_image_ids":source_image_ids,"primary_image_id":primary_image_id,"art_expression":expression,"dna":dna,"cover_background":f"{outdir.name}/{cover.name}","content_background":f"{outdir.name}/{content.name}","section_background":f"{outdir.name}/{section.name}","closing_background":f"{outdir.name}/{closing.name}","non_template_signature":hashlib.sha256(seed.encode()).hexdigest()[:16],
      "background_style":style_key,"background_style_label":bg_styles.STYLE_LIBRARY[style_key]["label"],"background_style_reason":style_trace,
      "color_divergence_triggered":diverged,"color_divergence_reason":div_reason}
    motifs_path = a.motifs or (Path(a.output).parent/"art_motifs.json")
    report = attach_motifs(report, motifs_path, outdir)
    write_json(a.output,report); print(a.output)


def main():
    a=args(); mp=Path(a.manifest); m=read_json(mp); rows=[]
    for item in m.get("images",[]):
        f=item.get("file"); path=mp.parent/f if f else None
        if path and path.exists(): rows.append((item,analyze(path)))
    if not rows:
        # TASK-043: 此前无可读图片时直接 raise SystemExit 崩溃退出，导致 render_deck.py
        # 找不到 art_dna.json 后把封面/章节/尾页背景统一降级为 deco.py 里零参数、完全固定的
        # cover_deco()/closing_deco()——这两个函数不感知 theme_domain 或任何项目信号，于是
        # 任何纯文字项目（无图片、无图片 md 解读）不论主题域是什么，画出来的背景构图都一样，
        # 这正是 bg_styles.py/THEME_DOMAINS.md 要根治的"不同项目背景趋同"问题在无图路径上的
        # 原样复现（用户实测 5 个不同主题域的纯文字测试项目截图确认）。
        # 现在改为：没有像素可分析时，用 content_page_base_palette() 从 state/style_report.json
        # 的主题色 token 合成一份轻量 dna（无真实像素统计，line_language/焦点/饱和度/对比度取
        # 中性默认值），照常调用 bg_styles.select_background_style()，让纯文字项目也能按
        # theme_domain 与正文关键词分流到 7 种风格库之一，而不是退回固定骨架。QA 报告里
        # source_mode 标注为 "domain-only"，与图片像素路径（"image"）、图片 md 解读路径
        # （"md"）区分，供人工审查这份背景到底是从哪类信号合成的。
        palette=content_page_base_palette(a.output)
        dna={"palette":palette,"line_language":"均衡网格","dark_focus":[1,1],"light_focus":[1,1],"saturation":0.35,"contrast":0.3}
        keyword_text=_load_keyword_text(a)
        domain,domain_confidence=_load_theme_domain(a)
        expression=(f"无可读项目图片，按主题域判定与正文关键词合成背景；主题色为{'、'.join(palette[:4])}；"
          f"背景保留标题侧留白，以异尺度轮廓、主题色光晕和方向性线群形成版式节奏；封面展开、尾页镜像收束，禁止复用固定行业图形。")
        style_key,style_trace=bg_styles.select_background_style(dna, keyword_text, domain, domain_confidence)
        seed=hashlib.sha256((keyword_text or "no-image-project").encode()).hexdigest()[:16]+expression
        _write_report(a, dna, expression, style_key, style_trace, seed, "domain-only", [], None, False, "无可读图片，跳过色彩发散检测，直接使用 state/style_report.json 主题色 token 合成调色板")
        return
    primary=max(rows,key=lambda x:{"high":3,"medium":2,"low":1}.get(x[0].get("weight"),1))
    # 色彩发散兜底：见 color_divergence_check() 顶部注释。只有多来源色相冲突严重到
    # 无法归纳统一主体色彩风格时才触发；不触发时 dna 完全等于既有逻辑的 primary[1]，
    # 不改变任何既有行为。
    diverged,div_reason,_camps=color_divergence_check([(x[0].get("id"),x[1]["palette"][0]) for x in rows])
    if diverged:
        dna=dict(primary[1]); dna["palette"]=content_page_base_palette(a.output)
    else:
        dna=primary[1]
    expression=(f"主题色为{'、'.join(dna['palette'][:4])}；线条呈{dna['line_language']}；"
      f"亮部重心位于九宫格({dna['light_focus'][0]+1},{dna['light_focus'][1]+1})，暗部重心位于({dna['dark_focus'][0]+1},{dna['dark_focus'][1]+1})；"
      f"饱和度{dna['saturation']:.2f}、明暗层次{dna['contrast']:.2f}。背景保留标题侧留白，以异尺度轮廓、项目色光晕和方向性线群形成版式节奏；封面展开、尾页镜像收束，禁止复用固定行业图形。")
    keyword_text=_load_keyword_text(a)
    domain,domain_confidence=_load_theme_domain(a)
    style_key,style_trace=bg_styles.select_background_style(dna, keyword_text, domain, domain_confidence)
    seed=primary[0]["id"]+expression
    _write_report(a, dna, expression, style_key, style_trace, seed, "image", [x[0]["id"] for x in rows], primary[0]["id"], diverged, div_reason)
if __name__=="__main__": main()
